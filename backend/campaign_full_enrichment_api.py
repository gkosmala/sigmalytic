# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_full_enrichment_api.py
---------------------------------------
Step90B full campaign-universe enrichment route.

Purpose:
- Expand Campaign Engine enrichment from the first live-safe display batch to the broader visible campaign universe.
- Preserve evidence doctrine: ODS / operator control is formally confirmed only from direct evidence fields.
- Fill Adv / Fail, MFE / MAE, targets, failure levels, and risk/reward wherever sufficient market data exists.
- Return explicit reasons where enrichment cannot be completed.

Display/intelligence route only. This route does not write to Supabase, mutate campaigns, authorize D3D,
confirm operator control from scores, create trade signals, send email, or touch Stripe billing
"""

from __future__ import annotations

import json
import math
import os
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Query

router = APIRouter()

STEP90B_MARKER = "SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE"

BACKEND_BASE = os.getenv("BACKEND_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
ALPACA_DATA_BASE = "https://data.alpaca.markets/v2/stocks/bars"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _round(value: Any, digits: int = 4) -> Optional[float]:
    x = _safe_float(value)
    if x is None:
        return None
    return round(x, digits)


def _pct(base: Optional[float], value: Optional[float]) -> Optional[float]:
    if base is None or value is None or base == 0:
        return None
    return round(((value - base) / base) * 100.0, 4)


def _get_json(url: str, timeout: int = 45) -> Tuple[Optional[Any], str]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Sigmalytic-Step90B-Full-Enrichment",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw), ""
    except Exception as exc:
        return None, str(exc)


def _rows_from_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    for key in ("rankings", "campaigns", "rows", "opportunities", "items", "symbols", "data"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]

    return []


def _fetch_base_universe(limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    endpoints = [
        f"/api/intelligence/rankings?limit={limit}",
        f"/api/campaigns/active?limit={limit}",
        f"/api/radar/intelligence?limit={limit}",
        "/api/intelligence/rankings",
        "/api/campaigns/active",
        "/api/radar/intelligence",
    ]

    seen: set[Tuple[str, str, str]] = set()
    rows: List[Dict[str, Any]] = []
    status: List[Dict[str, Any]] = []

    for endpoint in endpoints:
        data, err = _get_json(f"{BACKEND_BASE}{endpoint}", timeout=60)
        ok = err == ""
        endpoint_rows = _rows_from_payload(data)
        status.append({
            "endpoint": endpoint,
            "ok": ok,
            "error": err,
            "rows": len(endpoint_rows),
        })

        for r in endpoint_rows:
            symbol = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
            if not symbol:
                continue
            timeframe = str(r.get("timeframe") or "DAILY").upper().strip()
            campaign_id = str(r.get("campaign_id") or r.get("id") or "")
            key = (campaign_id, symbol, timeframe)
            alt_key = ("", symbol, timeframe)

            if key in seen or alt_key in seen:
                continue

            seen.add(key)
            if campaign_id:
                seen.add(alt_key)

            rows.append(dict(r))

            if len(rows) >= limit:
                return rows, status

    return rows[:limit], status


def _symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").upper().strip()


def _state(row: Dict[str, Any]) -> str:
    return str(row.get("state") or row.get("status") or row.get("current_state") or "SPARK").upper().strip()


def _bias(row: Dict[str, Any]) -> str:
    return str(row.get("bias") or row.get("watch_bias") or "WATCH").upper().strip()


def _score(row: Dict[str, Any]) -> Optional[float]:
    return _safe_float(
        row.get("score")
        or row.get("composite_score")
        or row.get("evidence")
        or row.get("evidence_score")
        or row.get("campaign_score")
    )


def _current_price(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Optional[float]:
    for key in ("current_price", "price", "market_price", "latest_close", "close"):
        x = _safe_float(row.get(key))
        if x is not None:
            return x
    if bars:
        return _safe_float(bars[-1].get("c"))
    return None


def _fetch_alpaca_bars(symbols: List[str]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    key = os.getenv("ALPACA_API_KEY") or os.getenv("ALPACA_KEY_ID") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")

    status: Dict[str, Any] = {
        "provider": "alpaca",
        "has_key": bool(key),
        "has_secret": bool(secret),
        "attempted": False,
        "ok": False,
        "symbols_requested": len(symbols),
        "symbols_with_bars": 0,
        "feed_used": "sip",
        "errors": [],
    }

    if not key or not secret or not symbols:
        status["errors"].append("missing_alpaca_credentials_or_symbols")
        return {}, status

    bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    status["attempted"] = True

    # Batch symbols to avoid the previous per-row timeout behavior.
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        params = urllib.parse.urlencode({
            "symbols": ",".join(batch),
            "timeframe": "1Day",
            "limit": "260",
            "adjustment": "raw",
            "feed": "sip",
        })
        url = f"{ALPACA_DATA_BASE}?{params}"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "APCA-API-KEY-ID": key,
                    "APCA-API-SECRET-KEY": secret,
                    "User-Agent": "Sigmalytic-Step90B-Alpaca-Batch",
                },
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            raw_bars = data.get("bars") if isinstance(data, dict) else {}
            if isinstance(raw_bars, dict):
                for sym, bars in raw_bars.items():
                    if isinstance(bars, list) and bars:
                        bars_by_symbol[str(sym).upper()] = bars

        except Exception as exc:
            status["errors"].append(f"batch_{i // batch_size + 1}: {exc}")

    status["symbols_with_bars"] = len(bars_by_symbol)
    status["ok"] = len(bars_by_symbol) > 0
    return bars_by_symbol, status


def _formal_ods(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formal ODS / operator-control status.

    CONFIRMED requires direct evidence fields. It cannot be inferred from rank, score, expected return,
    MFE, MAE, gamma, or price movement.
    """
    true_fields = [
        "operator_control_confirmed",
        "composite_operator_control_confirmed",
        "d3d_operator_control_confirmed",
        "d3d_confirmed",
        "supply_exhaustion_confirmed",
        "demand_support_confirmed",
    ]

    contrary_fields = [
        "operator_control_failed",
        "contrary_failure",
        "distribution_failure",
        "supply_failure",
        "demand_failure",
    ]

    if any(row.get(k) is True for k in contrary_fields):
        return {
            "ods_label": "NOT_CONFIRMED_CONTRARY_EVIDENCE",
            "ods_score": None,
            "ods_status": "NOT_CONFIRMED",
            "ods_reason": "Contrary/failure evidence present.",
            "operator_control_confirmed": False,
        }

    if any(row.get(k) is True for k in true_fields):
        return {
            "ods_label": "FORMALLY_CONFIRMED",
            "ods_score": 100,
            "ods_status": "CONFIRMED",
            "ods_reason": "Direct operator-control evidence field is present.",
            "operator_control_confirmed": True,
        }

    # Composite evidence can be declared pending, but not confirmed.
    has_partial_evidence = any(
        row.get(k) not in (None, "", False)
        for k in (
            "progress_score",
            "obstacle_score",
            "support_validation",
            "demand_validation",
            "supply_exhaustion",
            "structural_location",
            "evidence_payload",
        )
    )

    return {
        "ods_label": "PENDING_EVIDENCE",
        "ods_score": None,
        "ods_status": "PENDING",
        "ods_reason": "Visible campaign row lacks complete formal D3D/operator-control confirmation evidence.",
        "operator_control_confirmed": False,
        "operator_control_pending": has_partial_evidence,
    }


def _path_metrics(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    price = _current_price(row, bars)
    if price is None or not bars:
        return {
            "market_data_status": "NO_MARKET_BARS",
            "bar_count": len(bars),
            "mfe_pct": None,
            "mae_pct": None,
            "mfe_status": "NOT_AVAILABLE_NO_BARS",
            "mae_status": "NOT_AVAILABLE_NO_BARS",
        }

    closes = [_safe_float(b.get("c")) for b in bars if _safe_float(b.get("c")) is not None]
    highs = [_safe_float(b.get("h")) for b in bars if _safe_float(b.get("h")) is not None]
    lows = [_safe_float(b.get("l")) for b in bars if _safe_float(b.get("l")) is not None]

    if not closes or not highs or not lows:
        return {
            "market_data_status": "INSUFFICIENT_BAR_FIELDS",
            "bar_count": len(bars),
            "mfe_pct": None,
            "mae_pct": None,
            "mfe_status": "NOT_AVAILABLE_INSUFFICIENT_BARS",
            "mae_status": "NOT_AVAILABLE_INSUFFICIENT_BARS",
        }

    anchor = _safe_float(row.get("anchor_price") or row.get("birth_price") or row.get("entry_price"))
    if anchor is None:
        # Use a conservative recent anchor so every visible row receives an attempt.
        anchor = closes[0] if closes else price

    max_high = max(highs)
    min_low = min(lows)

    return {
        "market_data_status": "OK",
        "bar_count": len(bars),
        "last_bar_time": bars[-1].get("t"),
        "anchor_price": _round(anchor, 4),
        "mfe_price": _round(max_high, 4),
        "mae_price": _round(min_low, 4),
        "mfe_pct": _pct(anchor, max_high),
        "mae_pct": _pct(anchor, min_low),
        "mfe_status": "ENRICHED",
        "mae_status": "ENRICHED",
    }


def _targets_and_failure(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    price = _current_price(row, bars)

    if price is None or not bars:
        return {
            "target_status": "NOT_AVAILABLE_NO_PRICE",
            "failure_status": "NOT_AVAILABLE_NO_PRICE",
            "target_1_price": None,
            "target_2_price": None,
            "failure_price": None,
            "risk_reward_1": None,
            "risk_reward_2": None,
            "advance_condition": "PENDING_PRICE_DATA",
            "fail_condition": "PENDING_PRICE_DATA",
        }

    highs = [_safe_float(b.get("h")) for b in bars if _safe_float(b.get("h")) is not None]
    lows = [_safe_float(b.get("l")) for b in bars if _safe_float(b.get("l")) is not None]
    closes = [_safe_float(b.get("c")) for b in bars if _safe_float(b.get("c")) is not None]

    if len(highs) < 5 or len(lows) < 5 or len(closes) < 5:
        return {
            "target_status": "NOT_AVAILABLE_INSUFFICIENT_BARS",
            "failure_status": "NOT_AVAILABLE_INSUFFICIENT_BARS",
            "target_1_price": None,
            "target_2_price": None,
            "failure_price": None,
            "risk_reward_1": None,
            "risk_reward_2": None,
            "advance_condition": "NEEDS_MORE_BARS",
            "fail_condition": "NEEDS_MORE_BARS",
        }

    recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)

    ranges = [(h - l) for h, l in zip(highs[-20:], lows[-20:]) if h is not None and l is not None and h >= l]
    avg_range = statistics.mean(ranges) if ranges else max(price * 0.01, 0.01)

    direction = _bias(row)
    if direction in ("BEARISH", "SHORT", "AVOID"):
        target_1 = price - avg_range
        target_2 = price - (2.0 * avg_range)
        failure = min(recent_high, price + avg_range)
        reward_1 = abs(price - target_1)
        reward_2 = abs(price - target_2)
        risk = abs(failure - price)
    else:
        target_1 = price + avg_range
        target_2 = price + (2.0 * avg_range)
        failure = max(recent_low, price - avg_range)
        reward_1 = abs(target_1 - price)
        reward_2 = abs(target_2 - price)
        risk = abs(price - failure)

    rr1 = round(reward_1 / risk, 2) if risk > 0 else None
    rr2 = round(reward_2 / risk, 2) if risk > 0 else None

    return {
        "target_status": "ENRICHED",
        "failure_status": "ENRICHED",
        "target_1_price": _round(target_1, 4),
        "target_1_pct": _pct(price, target_1),
        "target_2_price": _round(target_2, 4),
        "target_2_pct": _pct(price, target_2),
        "failure_price": _round(failure, 4),
        "failure_pct": _pct(price, failure),
        "risk_reward_1": rr1,
        "risk_reward_2": rr2,
        "target_basis": "recent_average_range",
        "failure_basis": "recent_structural_low_high_or_average_range",
        "advance_condition": "Advance requires follow-through beyond target/structure with support defense.",
        "fail_condition": "Failure triggers if price violates computed failure level or contrary campaign evidence appears.",
    }


def _outcome(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not bars:
        return {
            "outcome_status": "PENDING_NO_BARS",
            "outcome_score": None,
            "outcome_window_days": None,
        }

    age = _safe_float(row.get("campaign_age_days") or row.get("duration_days"))
    if age is None:
        age = 0

    if age < 3:
        return {
            "outcome_status": "IMMATURE_TRACKING",
            "outcome_score": _round(_score(row), 2),
            "outcome_window_days": int(age),
        }

    return {
        "outcome_status": "ACTIVE_TRACKING",
        "outcome_score": _round(_score(row), 2),
        "outcome_window_days": int(age),
    }


def _decay(row: Dict[str, Any]) -> Dict[str, Any]:
    age = _safe_float(row.get("campaign_age_days") or row.get("duration_days"), 0) or 0
    score = _score(row)

    if age <= 1:
        label = "FRESH"
        decay_score = 100
    elif score is not None and score >= 60:
        label = "HEALTHY"
        decay_score = max(65, 100 - int(age))
    elif score is not None and score >= 55:
        label = "MONITOR"
        decay_score = max(50, 90 - int(age))
    else:
        label = "WEAKENING"
        decay_score = max(25, 80 - int(age))

    return {
        "decay_label": label,
        "decay_score": decay_score,
        "decay_reason": "age_score_decay_contract",
    }


def _pnf(row: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
    # Until a dedicated P&F engine is wired, provide explicit status instead of blank/no info.
    if targets.get("target_1_price") is not None:
        return {
            "pnf_status": "PROXY_TARGET_AVAILABLE",
            "pnf_target": targets.get("target_1_price"),
            "pnf_reason": "P&F engine not directly wired; using computed campaign target as display proxy.",
        }
    return {
        "pnf_status": "PENDING_PNF_ENGINE",
        "pnf_target": None,
        "pnf_reason": "Dedicated Point & Figure structure not available for this row.",
    }


def _enrich_row(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    c = dict(row)
    symbol = _symbol(c)
    state = _state(c)
    bias = _bias(c)
    score = _score(c)
    price = _current_price(c, bars)

    path = _path_metrics(c, bars)
    targets = _targets_and_failure(c, bars)
    ods = _formal_ods(c)
    outcome = _outcome(c, bars)
    decay = _decay(c)
    pnf = _pnf(c, targets)

    c.update({
        "symbol": symbol,
        "timeframe": str(c.get("timeframe") or "DAILY").upper(),
        "state": state,
        "status": state,
        "bias": bias,
        "score": _round(score, 2),
        "composite_score": _round(score, 2),
        "current_price": _round(price, 4),
        "price": _round(price, 4),
        "enrichment_status": "FULL_UNIVERSE_ENRICHMENT_ATTEMPTED",
        "step90b_marker": STEP90B_MARKER,
    })

    c.update(ods)
    c.update(decay)
    c.update(outcome)
    c.update(path)
    c.update(targets)
    c.update(pnf)

    c["expected_return_status"] = "PENDING_COHORT_ENGINE"
    c["expected_return_pct"] = c.get("expected_return_pct")
    c["summary"] = f"{symbol} {c.get('timeframe', 'DAILY')} campaign; {state}; {bias}; {c.get('enrichment_status')}"

    return c


@router.get("/api/campaigns/read-only/full-universe-enriched-campaign-table")
def full_universe_enriched_campaign_table(
    limit: int = Query(100, ge=1, le=250),
) -> Dict[str, Any]:
    rows, source_status = _fetch_base_universe(limit)
    symbols = [_symbol(r) for r in rows if _symbol(r)]
    bars_by_symbol, market_status = _fetch_alpaca_bars(symbols)

    enriched_rows = []
    for row in rows:
        sym = _symbol(row)
        bars = bars_by_symbol.get(sym, [])
        enriched_rows.append(_enrich_row(row, bars))

    coverage = {
        "requested_limit": limit,
        "base_rows": len(rows),
        "enriched_rows": len(enriched_rows),
        "symbols_requested": len(symbols),
        "symbols_with_bars": market_status.get("symbols_with_bars"),
        "coverage_pct": round((len(enriched_rows) / len(rows)) * 100, 2) if rows else 0,
    }

    return {
        "status": "PASS",
        "mode": "FULL_UNIVERSE_ENRICHED_CAMPAIGN_TABLE",
        "step90b_marker": STEP90B_MARKER,
        "created_utc": _now(),
        "row_count": len(enriched_rows),
        "coverage": coverage,
        "source_status": source_status,
        "market_data_status": market_status,
        "rows": enriched_rows,
        "safety": {
            "read_only": True,
            "database_write": False,
            "supabase_write": False,
            "campaign_mutation": False,
            "daily_bars_mutation": False,
            "d3d": False,
            "operator_control_confirmation_from_score": False,
            "operator_control_confirmation_requires_direct_evidence": True,
            "trade_signal": False,
            "stripe": False,
            "broker_execution": False,
        },
    }

