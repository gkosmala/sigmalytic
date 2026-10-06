# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_intelligence_api.py
----------------------------------
FastAPI router for Broker Behavioural Intelligence.

    GET    /api/broker-vaults                      five vault slots + counts
    PUT    /api/broker-vaults/{slot}               name / broker label
    POST   /api/broker-vaults/{slot}/statements    upload a CSV (form: file, kind)
    GET    /api/broker-vaults/{slot}/statements    list statements
    DELETE /api/broker-vaults/statements/{id}      remove one statement
    DELETE /api/broker-vaults/{slot}               empty a vault
    GET    /api/broker-vaults/{slot}/review        full review for one vault
    GET    /api/broker-vaults/compare              behaviour grade of all five

The shared demo account is refused: vault data must belong to a real user.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

try:
    from backend.supabase_isolation import get_user_id_from_request, DEMO_USER_ID
except Exception:  # pragma: no cover
    from supabase_isolation import get_user_id_from_request, DEMO_USER_ID

try:
    import import_history_restore_api as imp
    import broker_review
    import broker_vault_store as store_mod
    import broker_market_data as market
    import broker_intelligence as bi
except ImportError:  # pragma: no cover
    from backend import import_history_restore_api as imp
    from backend import broker_review, broker_vault_store as store_mod
    from backend import broker_market_data as market, broker_intelligence as bi

broker_router = APIRouter(prefix="/api/broker-vaults", tags=["broker-behavioural-intelligence"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
_STORE: Any = None


def get_store() -> Any:
    global _STORE
    if _STORE is None:
        try:
            _STORE = store_mod.default_store()
        except store_mod.VaultError as exc:
            raise HTTPException(503, str(exc))
    return _STORE


def set_store_for_tests(store: Any) -> None:
    global _STORE
    _STORE = store


def _user(request: Request) -> str:
    uid = get_user_id_from_request(request)
    if uid == DEMO_USER_ID:
        raise HTTPException(403, "Sign in to use broker vaults. The demo account cannot store statements.")
    return uid


def _slot(slot: int) -> int:
    try:
        return store_mod.check_slot(slot)
    except store_mod.VaultError as exc:
        raise HTTPException(400, str(exc))


class VaultLabel(BaseModel):
    name: str = ""
    broker: str = ""


def parse_statement(filename: str, raw: bytes, kind: str) -> Dict[str, Any]:
    """Turn an uploaded CSV into a stored statement record."""
    if kind not in ("trades", "positions"):
        raise HTTPException(400, "kind must be 'trades' or 'positions'.")
    text = imp._decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV has no header row.")

    rows: List[Dict[str, Any]] = []
    if kind == "trades":
        key_map = imp._build_key_map(reader.fieldnames)
        if "symbol" not in key_map:
            raise HTTPException(400, "A transactions CSV must include a symbol/ticker column.")
        for row in reader:
            sym = imp._safe_text(row.get(key_map["symbol"])).upper()
            if not sym:
                continue
            rows.append({
                "date": imp._safe_text(row.get(key_map.get("date", ""))),
                "symbol": sym,
                "side": imp._normalize_side(row.get(key_map.get("side", ""))),
                "quantity": imp._safe_float(row.get(key_map.get("quantity", ""))),
                "price": imp._safe_float(row.get(key_map.get("price", ""))),
                "fees": imp._safe_float(row.get(key_map.get("fees", ""))),
            })
        usable = [r for r in rows if r["side"] in ("BUY", "SELL") and r["quantity"] and r["price"]]
        if not usable:
            raise HTTPException(400, "No buy/sell rows with a quantity and price were found in this CSV.")
        dates = sorted(d for d in (market.parse_date(r["date"]) for r in rows) if d)
    else:
        rows = [{str(k): v for k, v in r.items() if k is not None} for r in reader]
        if not rows:
            raise HTTPException(400, "The positions CSV has no rows.")
        dates = []

    return {
        "filename": filename[:200], "kind": kind, "row_count": len(rows), "rows": rows,
        "period_start": dates[0].strftime("%Y-%m-%d") if dates else None,
        "period_end": dates[-1].strftime("%Y-%m-%d") if dates else None,
    }


@broker_router.get("")
async def list_vaults(request: Request) -> Dict[str, Any]:
    return {"ok": True, "vaults": get_store().list_vaults(_user(request))}


@broker_router.get("/compare")
async def compare(request: Request) -> Dict[str, Any]:
    uid, st = _user(request), get_store()
    out = []
    for v in st.list_vaults(uid):
        item = {**v, "grade": "N/A", "score": None}
        if v["statements"]:
            sts = st.list_statements(uid, v["slot"], with_rows=True)
            batches = [s.get("rows") or [] for s in sts if s.get("kind") == "trades"]
            ex = bi.merge_executions(batches)
            if ex:
                g = bi.grade_behavior(imp._analyze_trades(ex))
                item.update(grade=g.get("overall_grade", "N/A"), score=g.get("overall_score"),
                            components={k: c["grade"] for k, c in (g.get("components") or {}).items()})
        out.append(item)
    return {"ok": True, "vaults": out}


@broker_router.put("/{slot}")
async def label_vault(slot: int, body: VaultLabel, request: Request) -> Dict[str, Any]:
    uid = _user(request)
    get_store().upsert_vault(uid, _slot(slot), body.name.strip()[:60], body.broker.strip()[:60])
    return {"ok": True}


@broker_router.post("/{slot}/statements")
async def upload_statement(slot: int, request: Request) -> Dict[str, Any]:
    uid, _ = _user(request), _slot(slot)
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(400, "Missing file.")
    raw = await upload.read()
    if not raw:
        raise HTTPException(400, "Uploaded CSV is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 8 MB.")
    record = parse_statement(getattr(upload, "filename", "") or "statement.csv", raw,
                             str(form.get("kind") or "trades"))
    try:
        sid = get_store().add_statement(uid, slot, record)
    except store_mod.VaultError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "statement_id": sid, "kind": record["kind"], "rows": record["row_count"],
            "period_start": record["period_start"], "period_end": record["period_end"]}


@broker_router.get("/{slot}/statements")
async def list_statements(slot: int, request: Request) -> Dict[str, Any]:
    uid = _user(request)
    return {"ok": True, "statements": get_store().list_statements(uid, _slot(slot))}


@broker_router.delete("/statements/{statement_id}")
async def delete_statement(statement_id: str, request: Request) -> Dict[str, Any]:
    if not get_store().delete_statement(_user(request), statement_id):
        raise HTTPException(404, "Statement not found.")
    return {"ok": True}


@broker_router.delete("/{slot}")
async def clear_vault(slot: int, request: Request) -> Dict[str, Any]:
    uid = _user(request)
    return {"ok": True, "removed": get_store().clear_vault(uid, _slot(slot))}


@broker_router.get("/{slot}/review")
async def review(slot: int, request: Request) -> Dict[str, Any]:
    uid, st = _user(request), get_store()
    _slot(slot)
    vault = next(v for v in st.list_vaults(uid) if v["slot"] == slot)
    statements = st.list_statements(uid, slot, with_rows=True)
    if not statements:
        raise HTTPException(404, "This vault has no statements yet.")
    return {"ok": True, "review": broker_review.build_review(vault, statements, market)}
