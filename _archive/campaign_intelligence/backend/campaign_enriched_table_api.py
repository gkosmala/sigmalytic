from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/campaigns/read-only", tags=["read-only-campaign-enrichment"])

STEP87B_R2_MARKER = "SIGMALYTIC_STEP87B_R2_READ_ONLY_ENRICHED_CAMPAIGN_TABLE"

BACKEND_BASE = os.environ.get("SIGMALYTIC_BACKEND_BASE", "https://sigmalytic-backend.onrender.com").rstrip("/")
ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = v.replace("$", "").replace(",", "").replace("%", "").strip()
            if v in {"", "-", "—", "NA", "N/A", "None", "null"}:
                return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def _get(row: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return None


def _json_get(path: str, timeout: int = 35) -> Tuple[bool, Dict[str, Any], str]:
    url = BACKEND_BASE + path
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Sigmalytic-Step87B-R2/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, json.loads(r.read().decode("utf-8", errors="replace")), ""
    except Exception as e:
        return False, {}, repr(e)


def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = str(_get(row, ["symbol", "ticker"]) or "").upper().strip()
    price = _num(_get(row, ["current_price", "market_price", "price", "last_price", "close"]))
    age = _num(_get(row, ["campaign_age_days", "duration_days", "age_days", "duration"]))
    state = _get(row, ["state", "status", "campaign_state"])
    status = _get(row, ["status", "state", "campaign_state"])
    bias = _get(row, ["bias", "direction", "side"]) or "UNKNOWN"

    return {
        "symbol": symbol,
        "campaign_id": _get(row, ["campaign_id", "id"]),
        "timeframe": _get(row, ["timeframe"]) or "DAILY",
        "state": state,
        "status": status,
        "bias": bias,
        "grade": _get(row, ["grade"]),
        "regime": _get(row, ["regime"]),
        "layer": _get(row, ["layer"]),
        "source": _get(row, ["source"]),
        "display_label": _get(row, ["display_label"]) or f"{symbol} DAILY Campaign",
        "score": _num(_get(row, ["score", "composite_score"])),
        "composite_score": _num(_get(row, ["composite_score", "score"])),
        "progress_score": _num(_get(row, ["progress_score"])),
        "obstacle_score": _num(_get(row, ["obstacle_score"])),
        "current_price": price,
        "price": price,
        "campaign_age_days": int(age) if age is not None else None,
    }


def _seed_rows(limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    paths = [
        "/api/intelligence/rankings",
        "/api/intelligence/opportunities",
        "/api/radar/intelligence",
        "/api/intelligence/dashboard",
        "/api/radar/scores",
    ]

    by_symbol: Dict[str, Dict[str, Any]] = {}
    status: List[Dict[str, Any]] = []

    for path in paths:
        ok, payload, err = _json_get(path)
        status.append({"endpoint": path, "ok": ok, "error": err})
        if not ok:
            continue

        items: List[Any] = []
        for key in ["rankings", "opportunities", "symbols", "top_campaigns", "data", "scores"]:
            v = payload.get(key)
            if isinstance(v, list):
                items.extend(v)

        for item in items:
            if not isinstance(item, dict):
                continue
            r = _normalize(item)
            if not r["symbol"]:
                continue
            if r["symbol"] not in by_symbol:
                by_symbol[r["symbol"]] = r

    return list(by_symbol.values())[: max(1, min(limit, 200))], status


def _alpaca_env() -> Tuple[Optional[str], Optional[str]]:
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY") or os.environ.get("ALPACA_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    return key, secret


def _bars(symbols: List[str]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    key, secret = _alpaca_env()
    out: Dict[str, List[Dict[str, Any]]] = {s: [] for s in symbols}
    meta: Dict[str, Any] = {
        "provider": "alpaca",
        "has_key": bool(key),
        "has_secret": bool(secret),
        "attempted": False,
        "ok": False,
        "symbols_requested": len(symbols),
        "symbols_with_bars": 0,
        "feed_used": None,
        "errors": [],
    }

    if not symbols or not key or not secret:
        if not key or not secret:
            meta["errors"].append("alpaca credentials missing")
        return out, meta

    meta["attempted"] = True
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=280)

    for i in range(0, len(symbols), 40):
        batch = symbols[i : i + 40]
        for feed in ["sip", "iex"]:
            q = urllib.parse.urlencode(
                {
                    "symbols": ",".join(batch),
                    "timeframe": "1Day",
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "adjustment": "split",
                    "feed": feed,
                    "limit": "10000",
                    "sort": "asc",
                }
            )
            req = urllib.request.Request(
                ALPACA_BARS_URL + "?" + q,
                headers={
                    "APCA-API-KEY-ID": key,
                    "APCA-API-SECRET-KEY": secret,
                    "Accept": "application/json",
                    "User-Agent": "Sigmalytic-Step87B-R2-Alpaca-ReadOnly/1.0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    payload = json.loads(r.read().decode("utf-8", errors="replace"))
                raw = payload.get("bars", {})
                if isinstance(raw, dict):
                    for s in batch:
                        if isinstance(raw.get(s), list):
                            out[s].extend(raw[s])
                meta["feed_used"] = feed
                break
            except Exception as e:
                meta["errors"].append(f"{feed}: {repr(e)[:180]}")

    meta["symbols_with_bars"] = sum(1 for v in out.values() if v)
    meta["ok"] = meta["symbols_with_bars"] > 0
    return out, meta


def _close(b: Dict[str, Any]) -> Optional[float]:
    return _num(b.get("c") or b.get("close"))


def _high(b: Dict[str, Any]) -> Optional[float]:
    return _num(b.get("h") or b.get("high"))


def _low(b: Dict[str, Any]) -> Optional[float]:
    return _num(b.get("l") or b.get("low"))


def _last_close(bs: List[Dict[str, Any]]) -> Optional[float]:
    for b in reversed(bs):
        c = _close(b)
        if c is not None:
            return c
    return None


def _atr14(bs: List[Dict[str, Any]]) -> Optional[float]:
    tr: List[float] = []
    for i in range(1, len(bs)):
        pc, h, l = _close(bs[i - 1]), _high(bs[i]), _low(bs[i])
        if pc is None or h is None or l is None:
            continue
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(tr[-14:]) / 14.0 if len(tr) >= 14 else None


def _window(bs: List[Dict[str, Any]], age: Optional[int]) -> List[Dict[str, Any]]:
    if not bs:
        return []
    n = 3 if age is None or age <= 0 else max(3, min(age + 1, len(bs)))
    return bs[-n:]


def _mfe_mae(row: Dict[str, Any], bs: List[Dict[str, Any]]) -> Dict[str, Any]:
    w = _window(bs, row.get("campaign_age_days"))
    if len(w) < 2:
        return {"mfe_pct": None, "mae_pct": None, "mfe_price": None, "mae_price": None, "outcome_status": "IMMATURE_NO_FORWARD_WINDOW", "outcome_window_days": row.get("campaign_age_days") or 0}

    start = _close(w[0]) or row.get("current_price")
    highs = [_high(x) for x in w[1:]]
    lows = [_low(x) for x in w[1:]]
    highs = [x for x in highs if x is not None]
    lows = [x for x in lows if x is not None]

    if start is None or not highs or not lows:
        return {"mfe_pct": None, "mae_pct": None, "mfe_price": None, "mae_price": None, "outcome_status": "NO_FORWARD_HIGH_LOW", "outcome_window_days": row.get("campaign_age_days") or 0}

    bull = "BEAR" not in str(row.get("bias") or "").upper() and "SHORT" not in str(row.get("bias") or "").upper()
    mfe_price = max(highs) if bull else min(lows)
    mae_price = min(lows) if bull else max(highs)

    return {
        "mfe_pct": _pct(mfe_price, start) if bull else _pct(start, mfe_price),
        "mae_pct": _pct(mae_price, start) if bull else _pct(start, mae_price),
        "mfe_price": mfe_price,
        "mae_price": mae_price,
        "outcome_status": "TRACKING" if (row.get("campaign_age_days") or 0) >= 3 else "IMMATURE_TRACKING",
        "outcome_window_days": row.get("campaign_age_days") or len(w) - 1,
    }


def _targets(row: Dict[str, Any], bs: List[Dict[str, Any]]) -> Dict[str, Any]:
    price = _last_close(bs) or row.get("current_price")
    atr = _atr14(bs)
    if price is None:
        return {"target_1_price": None, "target_1_pct": None, "target_2_price": None, "target_2_pct": None, "target_basis": "NO_CURRENT_PRICE", "failure_price": None, "failure_pct": None, "risk_reward_1": None, "risk_reward_2": None, "failure_basis": "NO_CURRENT_PRICE"}
    if atr is None or atr <= 0:
        return {"target_1_price": None, "target_1_pct": None, "target_2_price": None, "target_2_pct": None, "target_basis": "INSUFFICIENT_BARS_FOR_ATR14", "failure_price": None, "failure_pct": None, "risk_reward_1": None, "risk_reward_2": None, "failure_basis": "INSUFFICIENT_BARS_FOR_ATR14"}

    bull = "BEAR" not in str(row.get("bias") or "").upper() and "SHORT" not in str(row.get("bias") or "").upper()
    if bull:
        t1, t2, fail = price + 1.5 * atr, price + 3.0 * atr, price - 1.5 * atr
        risk = price - fail
        r1, r2 = t1 - price, t2 - price
    else:
        t1, t2, fail = price - 1.5 * atr, price - 3.0 * atr, price + 1.5 * atr
        risk = fail - price
        r1, r2 = price - t1, price - t2

    return {
        "target_1_price": t1,
        "target_1_pct": _pct(t1, price),
        "target_2_price": t2,
        "target_2_pct": _pct(t2, price),
        "target_basis": "READ_ONLY_ATR14_REVIEW_LEVELS_NOT_TRADE_SIGNAL",
        "failure_price": fail,
        "failure_pct": _pct(fail, price),
        "risk_reward_1": r1 / risk if risk else None,
        "risk_reward_2": r2 / risk if risk else None,
        "failure_basis": "READ_ONLY_ATR14_REVIEW_LEVEL_NOT_TRADE_SIGNAL",
    }


def _decay(row: Dict[str, Any]) -> Dict[str, Any]:
    age = row.get("campaign_age_days")
    if age is None:
        return {"ods_label": "NOT_CONFIRMED_BY_STEP87B_R2", "ods_score": None, "decay_label": "AGE_UNAVAILABLE", "decay_score": None, "decay_reason": "campaign age unavailable"}
    label = "FRESH" if age <= 5 else "ACTIVE" if age <= 20 else "AGING" if age <= 45 else "STALE"
    return {"ods_label": "NOT_CONFIRMED_BY_STEP87B_R2", "ods_score": None, "decay_label": label, "decay_score": max(0.0, min(100.0, 100.0 - age * 2.0)), "decay_reason": "age-based evidence freshness only; not operator-control confirmation"}


def _enrich(row: Dict[str, Any], bs: List[Dict[str, Any]]) -> Dict[str, Any]:
    last = _last_close(bs)
    if last is not None:
        row["current_price"] = last
        row["price"] = last

    out = dict(row)
    out.update(_decay(row))
    out.update(_mfe_mae(row, bs))
    out.update(_targets(row, bs))

    mfe = _num(out.get("mfe_pct"))
    mae = _num(out.get("mae_pct"))
    out["outcome_score"] = abs(mfe) / (abs(mfe) + abs(mae)) * 100.0 if mfe is not None and mae is not None and (abs(mfe) + abs(mae)) else None

    out["expected_return_pct"] = None
    out["expected_return_status"] = "PENDING_COHORT_ENGINE"
    out["expected_return_basis"] = "historical cohort/analog distribution not attached in Step87B-R2"

    state = str(out.get("state") or out.get("status") or "STATE_UNKNOWN").upper()
    bias = str(out.get("bias") or "BIAS_UNKNOWN").upper()
    grade = str(out.get("grade") or "").upper()

    out["signal_tags"] = [x for x in [state, bias, f"GRADE_{grade}" if grade else None] if x]
    out["summary"] = f"{out.get('symbol')} {out.get('timeframe')} campaign; {state}; {bias}"
    out["enrichment_status"] = "ENRICHED_READ_ONLY" if bs else "PARTIAL_NO_BARS"
    out["market_data_status"] = "OK" if bs else "NO_BARS_AVAILABLE"
    out["bar_count"] = len(bs)
    out["last_bar_time"] = bs[-1].get("t") if bs else None
    out["step87b_r2_marker"] = STEP87B_R2_MARKER
    return out


@router.get("/enriched-campaign-table")
def enriched_campaign_table(limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    seed, source_status = _seed_rows(limit)
    symbols = sorted({r["symbol"] for r in seed if r.get("symbol")})
    bars_by_symbol, market_status = _bars(symbols)
    rows = [_enrich(r, bars_by_symbol.get(r["symbol"], [])) for r in seed]

    return {
        "status": "PASS",
        "mode": "READ_ONLY_ENRICHED_CAMPAIGN_TABLE",
        "step87b_r2_marker": STEP87B_R2_MARKER,
        "created_utc": _utc_now(),
        "row_count": len(rows),
        "source_status": source_status,
        "market_data_status": market_status,
        "rows": rows,
        "field_contract": {
            "ods_decay": ["ods_label", "ods_score", "decay_label", "decay_score", "decay_reason"],
            "outcome": ["outcome_status", "outcome_score", "outcome_window_days"],
            "expected_return": ["expected_return_pct", "expected_return_status", "expected_return_basis"],
            "mfe_mae": ["mfe_pct", "mae_pct", "mfe_price", "mae_price"],
            "target_1_2": ["target_1_price", "target_1_pct", "target_2_price", "target_2_pct", "target_basis"],
            "failure_rr": ["failure_price", "failure_pct", "risk_reward_1", "risk_reward_2", "failure_basis"],
            "signal_summary": ["signal_tags", "summary", "enrichment_status"],
        },
        "safety": {
            "read_only": True,
            "database_write": False,
            "supabase_write": False,
            "campaign_mutation": False,
            "daily_bars_mutation": False,
            "d3d": False,
            "operator_control_confirmation": False,
            "operator_control_from_score": False,
            "trade_signal": False,
            "stripe": False,
            "broker_execution": False,
        },
    }