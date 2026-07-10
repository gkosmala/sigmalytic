from __future__ import annotations

import csv
import io
import json
import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["import-history-restore"])

STORE_DIR = Path(__file__).resolve().parent / "data" / "import_history"
LAST_IMPORT_PATH = STORE_DIR / "last_import.json"

COLUMN_ALIASES = {
    "date": ["date", "time", "datetime", "trade_date", "transaction_date", "executed_at", "fill_time"],
    "symbol": ["symbol", "ticker", "asset", "underlying", "instrument"],
    "side": ["side", "action", "type", "transaction_type", "buy_sell", "instruction"],
    "quantity": ["quantity", "qty", "shares", "filled_qty", "filled_quantity", "amount"],
    "price": ["price", "avg_price", "average_price", "fill_price", "execution_price", "trade_price"],
    "fees": ["fees", "fee", "commission", "commissions"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _build_key_map(fieldnames: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    normalized = {_clean_key(name): name for name in fieldnames if name is not None}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            hit = normalized.get(_clean_key(alias))
            if hit:
                out[canonical] = hit
                break
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
    if text == "":
        return default
    try:
        number = float(text)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_side(value: Any) -> str:
    text = _safe_text(value).lower()
    if text in {"b", "buy", "bought", "bot", "long", "open buy"}:
        return "BUY"
    if text in {"s", "sell", "sold", "short", "open sell", "close sell"}:
        return "SELL"
    if "buy" in text:
        return "BUY"
    if "sell" in text or "sold" in text:
        return "SELL"
    return text.upper() if text else "UNKNOWN"


def _analyze_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(trades)
    symbols = Counter(t["symbol"] for t in trades if t.get("symbol"))
    sides = Counter(t["side"] for t in trades if t.get("side"))
    notional_by_symbol: Dict[str, float] = defaultdict(float)

    total_notional = 0.0
    for t in trades:
        notional = abs(_safe_float(t.get("notional")))
        total_notional += notional
        if t.get("symbol"):
            notional_by_symbol[t["symbol"]] += notional

    largest_symbol = None
    largest_symbol_notional = 0.0
    if notional_by_symbol:
        largest_symbol, largest_symbol_notional = max(notional_by_symbol.items(), key=lambda item: item[1])

    behavioral_flags: List[str] = []
    if total == 0:
        behavioral_flags.append("NO_TRADES_PARSED")
    if total > 0 and len(symbols) <= 2:
        behavioral_flags.append("CONCENTRATED_SYMBOL_ACTIVITY")
    if total > 0 and sides.get("BUY", 0) > 0 and sides.get("SELL", 0) == 0:
        behavioral_flags.append("BUY_ONLY_HISTORY_NO_SELL_DISCIPLINE_OBSERVED")
    if total > 0 and sides.get("SELL", 0) > sides.get("BUY", 0) * 2:
        behavioral_flags.append("SELL_HEAVY_HISTORY")
    if total < 10:
        behavioral_flags.append("SMALL_SAMPLE_SIZE")

    avg_notional = total_notional / total if total else 0.0

    if "NO_TRADES_PARSED" in behavioral_flags:
        behavioral_profile = "No behavioral profile available because no valid trades were parsed."
    elif "CONCENTRATED_SYMBOL_ACTIVITY" in behavioral_flags:
        behavioral_profile = "Imported history shows concentrated activity; review whether decisions were clustered around a small number of symbols."
    elif "BUY_ONLY_HISTORY_NO_SELL_DISCIPLINE_OBSERVED" in behavioral_flags:
        behavioral_profile = "Imported history shows buying activity without matching sell records; exit discipline cannot yet be evaluated."
    else:
        behavioral_profile = "Imported history is sufficient for a preliminary behavioral snapshot."

    return {
        "total_trades": total,
        "unique_symbols": len(symbols),
        "symbols": dict(symbols.most_common(25)),
        "sides": dict(sides),
        "total_notional": round(total_notional, 2),
        "average_trade_notional": round(avg_notional, 2),
        "largest_symbol": largest_symbol,
        "largest_symbol_notional": round(largest_symbol_notional, 2),
        "behavioral_flags": behavioral_flags,
        "behavioral_profile": behavioral_profile,
        "summary": {
            "trades_imported": total,
            "symbols_detected": len(symbols),
            "largest_symbol": largest_symbol,
            "behavioral_flag_count": len(behavioral_flags),
        },
    }


def _parse_csv_bytes(filename: str, raw: bytes) -> Dict[str, Any]:
    text = _decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")

    key_map = _build_key_map(reader.fieldnames)
    if "symbol" not in key_map:
        raise HTTPException(status_code=400, detail="CSV must include a symbol/ticker column.")

    trades: List[Dict[str, Any]] = []
    ignored_rows = 0
    total_rows = 0

    for row in reader:
        total_rows += 1

        symbol = _safe_text(row.get(key_map.get("symbol", ""))).upper()
        if not symbol:
            ignored_rows += 1
            continue

        quantity = _safe_float(row.get(key_map.get("quantity", "")))
        price = _safe_float(row.get(key_map.get("price", "")))
        side = _normalize_side(row.get(key_map.get("side", "")))
        date_value = _safe_text(row.get(key_map.get("date", "")))
        fees = _safe_float(row.get(key_map.get("fees", "")))

        notional = abs(quantity * price) if quantity and price else 0.0

        trades.append({
            "date": date_value,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "notional": round(notional, 2),
            "raw": row,
        })

    analysis = _analyze_trades(trades)

    return {
        "ok": True,
        "success": True,
        "status": "PASS",
        "message": f"Imported {len(trades)} trades from {filename}.",
        "import_id": str(uuid.uuid4()),
        "filename": filename,
        "received_at_utc": _now_iso(),
        "rows_received": total_rows,
        "parsed_rows": len(trades),
        "ignored_rows": ignored_rows,
        "column_map": key_map,
        "trades_imported": len(trades),
        "analysis": analysis,
        "behavioral_analysis": analysis,
        "behavioral_flags": analysis.get("behavioral_flags", []),
        "summary": analysis.get("summary", {}),
        "trades_preview": trades[:50],
    }


def _save_import(payload: Dict[str, Any]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_IMPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@router.post("/api/import/upload-generic")
async def upload_generic_import_history(request: Request) -> Dict[str, Any]:
    form = await request.form()
    upload = form.get("file")

    if upload is None:
        raise HTTPException(status_code=400, detail="Missing multipart file field named 'file'.")

    filename = getattr(upload, "filename", None) or "uploaded_brokerage_history.csv"
    raw = await upload.read()

    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty.")

    payload = _parse_csv_bytes(filename, raw)
    _save_import(payload)
    return payload


@router.get("/api/trades/history")
async def get_trade_import_history() -> Dict[str, Any]:
    if not LAST_IMPORT_PATH.exists():
        return {
            "ok": True,
            "success": True,
            "has_history": False,
            "message": "No import history found.",
            "analysis": None,
            "behavioral_analysis": None,
        }

    return json.loads(LAST_IMPORT_PATH.read_text(encoding="utf-8"))


@router.post("/api/trades/reset")
@router.delete("/api/trades/reset")
async def reset_trade_import_history() -> Dict[str, Any]:
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    removed = []
    for path in STORE_DIR.glob("*.json"):
        removed.append(path.name)
        path.unlink()

    return {
        "ok": True,
        "success": True,
        "reset": True,
        "removed_files": removed,
        "message": "Import history reset. Upload a new brokerage CSV to rebuild behavioral intelligence.",
        "doctrine": {
            "scoped_import_reset_only": True,
            "no_campaign_delete": True,
            "no_universe_delete": True,
            "no_supabase_write": True,
            "no_billing": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
        },
    }
