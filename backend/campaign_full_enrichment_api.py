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
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Query


# SIGMALYTIC_STEP93E_READ_ONLY_GAMMA_OVERLAY
try:
    from backend.gex_engine import score_gex as _sigmalytic_score_gex
except Exception:
    _sigmalytic_score_gex = None

router = APIRouter()

STEP90B_MARKER = "SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE"

BACKEND_BASE = os.getenv("BACKEND_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
ALPACA_DATA_BASE = "https://data.alpaca.markets/v2/stocks/bars"

# SIGMALYTIC_STEP90C_SEVEN_YEAR_ALPACA_CAMPAIGN_HISTORY
CAMPAIGN_HISTORY_YEARS = 7
CAMPAIGN_HISTORY_DAYS = 365 * CAMPAIGN_HISTORY_YEARS + 3
ALPACA_PAGE_LIMIT = 10000
ALPACA_BATCH_SIZE = 25
ALPACA_MAX_PAGES_PER_BATCH = 40


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

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=CAMPAIGN_HISTORY_DAYS)
    start_date = start_dt.date().isoformat()
    end_date = end_dt.date().isoformat()

    status: Dict[str, Any] = {
        "provider": "alpaca",
        "history_years": CAMPAIGN_HISTORY_YEARS,
        "history_days_requested": CAMPAIGN_HISTORY_DAYS,
        "start": start_date,
        "end": end_date,
        "timeframe": "1Day",
        "page_limit": ALPACA_PAGE_LIMIT,
        "batch_size": ALPACA_BATCH_SIZE,
        "max_pages_per_batch": ALPACA_MAX_PAGES_PER_BATCH,
        "has_key": bool(key),
        "has_secret": bool(secret),
        "attempted": False,
        "ok": False,
        "symbols_requested": len(symbols),
        "symbols_with_bars": 0,
        "total_bars": 0,
        "pages_fetched": 0,
        "feed_used": "sip",
        "pagination_used": True,
        "errors": [],
    }

    if not key or not secret or not symbols:
        status["errors"].append("missing_alpaca_credentials_or_symbols")
        return {}, status

    bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    status["attempted"] = True

    unique_symbols = []
    seen = set()
    for sym in symbols:
        clean = str(sym or "").upper().strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique_symbols.append(clean)

    for i in range(0, len(unique_symbols), ALPACA_BATCH_SIZE):
        batch = unique_symbols[i:i + ALPACA_BATCH_SIZE]
        page_token: Optional[str] = None
        pages_for_batch = 0

        while True:
            pages_for_batch += 1

            params_dict = {
                "symbols": ",".join(batch),
                "timeframe": "1Day",
                "start": start_date,
                "end": end_date,
                "limit": str(ALPACA_PAGE_LIMIT),
                "adjustment": "raw",
                "feed": "sip",
                "sort": "asc",
            }

            if page_token:
                params_dict["page_token"] = page_token

            params = urllib.parse.urlencode(params_dict)
            url = f"{ALPACA_DATA_BASE}?{params}"

            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "APCA-API-KEY-ID": key,
                        "APCA-API-SECRET-KEY": secret,
                        "User-Agent": "Sigmalytic-Step90C-Seven-Year-Alpaca-Paginated",
                    },
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))

                status["pages_fetched"] += 1

                raw_bars = data.get("bars") if isinstance(data, dict) else {}
                if isinstance(raw_bars, dict):
                    for sym, bars in raw_bars.items():
                        clean_sym = str(sym).upper()
                        if isinstance(bars, list) and bars:
                            existing = bars_by_symbol.setdefault(clean_sym, [])
                            existing.extend(bars)

                next_token = data.get("next_page_token") if isinstance(data, dict) else None
                if not next_token:
                    break

                page_token = str(next_token)

                if pages_for_batch >= ALPACA_MAX_PAGES_PER_BATCH:
                    status["errors"].append(
                        f"pagination_capped_batch_{i // ALPACA_BATCH_SIZE + 1}_after_{ALPACA_MAX_PAGES_PER_BATCH}_pages"
                    )
                    break

            except Exception as exc:
                status["errors"].append(f"batch_{i // ALPACA_BATCH_SIZE + 1}_page_{pages_for_batch}: {exc}")
                break

    # Deduplicate by timestamp and sort each symbol.
    for sym, bars in list(bars_by_symbol.items()):
        dedup: Dict[str, Dict[str, Any]] = {}
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            t = str(bar.get("t") or "")
            if t:
                dedup[t] = bar
        sorted_bars = sorted(dedup.values(), key=lambda b: str(b.get("t") or ""))
        bars_by_symbol[sym] = sorted_bars

    status["symbols_with_bars"] = len([sym for sym, bars in bars_by_symbol.items() if bars])
    status["total_bars"] = sum(len(bars) for bars in bars_by_symbol.values())
    status["ok"] = status["symbols_with_bars"] > 0
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



# SIGMALYTIC_STEP90E_LIFECYCLE_COHORT_MATURITY_FROM_7YR_HISTORY
def _parse_bar_day(bar: Dict[str, Any]) -> Optional[str]:
    raw = str(bar.get("t") or "").strip()
    if not raw:
        return None
    return raw[:10]


def _parse_row_anchor_day(row: Dict[str, Any]) -> Optional[str]:
    for key in (
        "campaign_anchor_date",
        "anchor_date",
        "birth_date",
        "campaign_birth_date",
        "campaign_start_date",
        "started_at",
        "start_date",
        "created_at",
        "detected_at",
        "first_seen_at",
    ):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        day = str(raw).strip()[:10]
        if len(day) == 10 and day[4] == "-" and day[7] == "-":
            return day
    return None


def _close_at(bars: List[Dict[str, Any]], index: int) -> Optional[float]:
    if index < 0 or index >= len(bars):
        return None
    return _safe_float(bars[index].get("c"))


def _find_bar_index_on_or_after_day(bars: List[Dict[str, Any]], day: str) -> Optional[int]:
    for i, bar in enumerate(bars):
        bar_day = _parse_bar_day(bar)
        if bar_day and bar_day >= day:
            return i
    return None


def _infer_campaign_anchor(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not bars:
        return {
            "campaign_anchor_status": "NO_BARS",
            "campaign_anchor_source": "none",
            "campaign_anchor_index": None,
            "campaign_anchor_date": None,
            "campaign_age_bars": None,
            "campaign_age_days_inferred": None,
            "campaign_anchor_price": None,
            "campaign_anchor_reason": "No daily bars available.",
        }

    explicit_day = _parse_row_anchor_day(row)
    if explicit_day:
        explicit_index = _find_bar_index_on_or_after_day(bars, explicit_day)
        if explicit_index is not None:
            return {
                "campaign_anchor_status": "EXPLICIT_ANCHOR",
                "campaign_anchor_source": "row_date_field",
                "campaign_anchor_index": explicit_index,
                "campaign_anchor_date": _parse_bar_day(bars[explicit_index]),
                "campaign_age_bars": max(0, len(bars) - 1 - explicit_index),
                "campaign_age_days_inferred": max(0, len(bars) - 1 - explicit_index),
                "campaign_anchor_price": _round(_close_at(bars, explicit_index), 4),
                "campaign_anchor_reason": "Campaign anchor date was present in the campaign row.",
            }

    n = len(bars)
    if n < 20:
        idx = 0
        return {
            "campaign_anchor_status": "PROVISIONAL_SHORT_HISTORY",
            "campaign_anchor_source": "short_history_first_bar",
            "campaign_anchor_index": idx,
            "campaign_anchor_date": _parse_bar_day(bars[idx]),
            "campaign_age_bars": max(0, n - 1 - idx),
            "campaign_age_days_inferred": max(0, n - 1 - idx),
            "campaign_anchor_price": _round(_close_at(bars, idx), 4),
            "campaign_anchor_reason": "Too few bars for structural anchor inference; first available bar used provisionally.",
        }

    current_close = _close_at(bars, n - 1)
    search_start = max(5, n - min(252, n))
    search_end = max(search_start, n - 5)

    pivot_candidates: List[int] = []
    for i in range(search_start, search_end):
        c = _close_at(bars, i)
        if c is None or c <= 0:
            continue

        window_start = max(0, i - 5)
        window_end = min(n, i + 6)
        window_values = [_close_at(bars, j) for j in range(window_start, window_end)]
        window_values = [x for x in window_values if x is not None]

        if not window_values:
            continue

        is_local_low = c <= min(window_values)
        current_advanced = current_close is not None and current_close >= c * 1.03

        if is_local_low and current_advanced:
            pivot_candidates.append(i)

    if pivot_candidates:
        idx = pivot_candidates[-1]
        source = "recent_confirmed_pivot_low"
        status = "INFERRED_STRUCTURAL_ANCHOR"
        reason = "Most recent local pivot low with at least 3 percent advance into current structure."
    else:
        lookback = min(126, n)
        candidate_indexes = list(range(n - lookback, n))
        candidate_indexes = [i for i in candidate_indexes if _close_at(bars, i) is not None]
        if candidate_indexes:
            idx = min(candidate_indexes, key=lambda i: _close_at(bars, i) or float("inf"))
            source = "recent_low_fallback"
            status = "PROVISIONAL_INFERRED_ANCHOR"
            reason = "No confirmed local-pivot campaign anchor; recent 126-bar low used provisionally."
        else:
            idx = max(0, n - 20)
            source = "fallback_recent_window"
            status = "UNKNOWN_ANCHOR_PROVISIONAL"
            reason = "Could not identify a reliable structural anchor; fallback recent window used."

    return {
        "campaign_anchor_status": status,
        "campaign_anchor_source": source,
        "campaign_anchor_index": idx,
        "campaign_anchor_date": _parse_bar_day(bars[idx]),
        "campaign_age_bars": max(0, n - 1 - idx),
        "campaign_age_days_inferred": max(0, n - 1 - idx),
        "campaign_anchor_price": _round(_close_at(bars, idx), 4),
        "campaign_anchor_reason": reason,
    }


def _lifecycle_status_from_anchor(anchor: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    age_bars = anchor.get("campaign_age_bars")

    if age_bars is None:
        return {
            "outcome_status": "UNKNOWN_ANCHOR",
            "lifecycle_stage": "UNKNOWN",
            "lifecycle_maturity": "UNKNOWN",
            "outcome_window_days": None,
            "outcome_score": None,
            "lifecycle_reason": "Campaign anchor could not be established.",
        }

    age = int(age_bars)
    score_value = None

    if age < 10:
        status = "IMMATURE_TRACKING"
        stage = "EARLY_CAMPAIGN"
        maturity = "IMMATURE"
        reason = "Fewer than 10 post-anchor daily bars."
    elif age < 30:
        status = "ACTIVE_TRACKING"
        stage = "ACTIVE_EARLY_CAMPAIGN"
        maturity = "DEVELOPING"
        reason = "At least 10 but fewer than 30 post-anchor daily bars."
    elif age < 90:
        status = "MATURE_TRACKING"
        stage = "MATURE_CAMPAIGN"
        maturity = "MATURE"
        reason = "At least 30 post-anchor daily bars."
    else:
        status = "LONG_MATURE_TRACKING"
        stage = "LONG_DURATION_CAMPAIGN"
        maturity = "LONG_MATURE"
        reason = "At least 90 post-anchor daily bars."

    return {
        "outcome_status": status,
        "lifecycle_stage": stage,
        "lifecycle_maturity": maturity,
        "outcome_window_days": age,
        "outcome_score": score_value,
        "lifecycle_reason": reason,
    }


def _window_close_values(bars: List[Dict[str, Any]], start: int, end: int) -> List[float]:
    values: List[float] = []
    for i in range(max(0, start), min(len(bars), end)):
        c = _close_at(bars, i)
        if c is not None:
            values.append(c)
    return values


def _metric_snapshot(bars: List[Dict[str, Any]], index: int) -> Optional[Dict[str, float]]:
    if index < 80 or index >= len(bars):
        return None

    c = _close_at(bars, index)
    c20 = _close_at(bars, index - 20)
    c60 = _close_at(bars, index - 60)

    if c is None or c20 is None or c60 is None or c20 == 0 or c60 == 0:
        return None

    recent20 = _window_close_values(bars, index - 19, index + 1)
    recent50 = _window_close_values(bars, index - 49, index + 1)

    if len(recent20) < 15 or len(recent50) < 35:
        return None

    low20 = min(recent20)
    high20 = max(recent20)
    span20 = high20 - low20
    pos20 = ((c - low20) / span20) if span20 > 0 else 0.5

    sma20 = statistics.mean(recent20)
    sma50 = statistics.mean(recent50)

    ranges: List[float] = []
    for i in range(max(0, index - 19), index + 1):
        h = _safe_float(bars[i].get("h"))
        l = _safe_float(bars[i].get("l"))
        if h is not None and l is not None and c != 0:
            ranges.append(((h - l) / c) * 100.0)

    range20_pct = statistics.mean(ranges) if ranges else 0.0

    return {
        "momentum_20_pct": ((c - c20) / c20) * 100.0,
        "momentum_60_pct": ((c - c60) / c60) * 100.0,
        "position_20": pos20,
        "sma20_sma50_spread_pct": ((sma20 - sma50) / sma50) * 100.0 if sma50 else 0.0,
        "range20_pct": range20_pct,
    }


def _forward_return(bars: List[Dict[str, Any]], index: int, forward: int) -> Optional[float]:
    c0 = _close_at(bars, index)
    c1 = _close_at(bars, index + forward)
    if c0 is None or c1 is None or c0 == 0:
        return None
    return round(((c1 - c0) / c0) * 100.0, 4)


def _median(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(statistics.median(clean), 4)


def _win_rate(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round((len([v for v in clean if v > 0]) / len(clean)) * 100.0, 2)


def _cohort_readiness(row: Dict[str, Any], bars: List[Dict[str, Any]], outcome: Dict[str, Any]) -> Dict[str, Any]:
    if len(bars) < 160:
        return {
            "expected_return_status": "COHORT_INSUFFICIENT_HISTORY",
            "expected_return_pct": None,
            "cohort_status": "COHORT_INSUFFICIENT_HISTORY",
            "cohort_match_count": 0,
            "cohort_method": "seven_year_daily_structural_analogs",
            "cohort_reason": "Fewer than 160 daily bars available for historical analog matching.",
        }

    current_index = len(bars) - 1
    current = _metric_snapshot(bars, current_index)

    if current is None:
        return {
            "expected_return_status": "COHORT_CURRENT_METRICS_UNAVAILABLE",
            "expected_return_pct": None,
            "cohort_status": "COHORT_CURRENT_METRICS_UNAVAILABLE",
            "cohort_match_count": 0,
            "cohort_method": "seven_year_daily_structural_analogs",
            "cohort_reason": "Current structural metrics could not be computed.",
        }

    matches: List[Dict[str, Any]] = []

    # Leave 60 bars forward so analogs have real post-signal outcomes.
    for i in range(80, len(bars) - 61):
        snap = _metric_snapshot(bars, i)
        if snap is None:
            continue

        same_trend = (
            (current["sma20_sma50_spread_pct"] >= 0 and snap["sma20_sma50_spread_pct"] >= 0)
            or (current["sma20_sma50_spread_pct"] < 0 and snap["sma20_sma50_spread_pct"] < 0)
        )

        if not same_trend:
            continue

        if abs(current["momentum_20_pct"] - snap["momentum_20_pct"]) > 6.0:
            continue
        if abs(current["momentum_60_pct"] - snap["momentum_60_pct"]) > 12.0:
            continue
        if abs(current["position_20"] - snap["position_20"]) > 0.30:
            continue
        if abs(current["range20_pct"] - snap["range20_pct"]) > 3.0:
            continue

        r20 = _forward_return(bars, i, 20)
        r40 = _forward_return(bars, i, 40)
        r60 = _forward_return(bars, i, 60)

        if r20 is None or r40 is None or r60 is None:
            continue

        matches.append({
            "index": i,
            "date": _parse_bar_day(bars[i]),
            "forward_20d_pct": r20,
            "forward_40d_pct": r40,
            "forward_60d_pct": r60,
        })

    returns20 = [m["forward_20d_pct"] for m in matches]
    returns40 = [m["forward_40d_pct"] for m in matches]
    returns60 = [m["forward_60d_pct"] for m in matches]

    match_count = len(matches)

    if match_count >= 15:
        cohort_status = "COHORT_READY"
        expected_status = "COHORT_READY"
        reason = "At least 15 historical daily analogs found in the 7-year record."
    elif match_count >= 5:
        cohort_status = "COHORT_LIMITED"
        expected_status = "COHORT_LIMITED_SAMPLE"
        reason = "Historical analogs found, but sample size is limited."
    elif match_count > 0:
        cohort_status = "COHORT_INSUFFICIENT_MATCHES"
        expected_status = "COHORT_INSUFFICIENT_MATCHES"
        reason = "Too few historical analogs for a reliable cohort expectation."
    else:
        cohort_status = "COHORT_NO_MATCHES"
        expected_status = "COHORT_NO_MATCHES"
        reason = "No sufficiently similar historical analogs were found."

    median20 = _median(returns20)
    median40 = _median(returns40)
    median60 = _median(returns60)

    return {
        "expected_return_status": expected_status,
        "expected_return_pct": median20,
        "cohort_status": cohort_status,
        "cohort_match_count": match_count,
        "cohort_method": "seven_year_daily_structural_analogs",
        "cohort_reason": reason,
        "cohort_forward_window_days": 20,
        "cohort_expected_return_20d_pct": median20,
        "cohort_expected_return_40d_pct": median40,
        "cohort_expected_return_60d_pct": median60,
        "cohort_win_rate_20d_pct": _win_rate(returns20),
        "cohort_win_rate_40d_pct": _win_rate(returns40),
        "cohort_win_rate_60d_pct": _win_rate(returns60),
        "cohort_current_momentum_20_pct": round(current["momentum_20_pct"], 4),
        "cohort_current_momentum_60_pct": round(current["momentum_60_pct"], 4),
        "cohort_current_position_20": round(current["position_20"], 4),
        "cohort_current_sma20_sma50_spread_pct": round(current["sma20_sma50_spread_pct"], 4),
        "cohort_current_range20_pct": round(current["range20_pct"], 4),
    }


def _outcome(row: Dict[str, Any], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    anchor = _infer_campaign_anchor(row, bars)
    lifecycle = _lifecycle_status_from_anchor(anchor, bars)
    score_value = _round(_score(row), 2)

    lifecycle["outcome_score"] = score_value
    lifecycle.update(anchor)

    return lifecycle


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



# SIGMALYTIC_STEP92E_REAL_PNF_ENGINE_COMPLETE
def _pnf(row: Dict[str, Any], targets: Dict[str, Any], bars: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Real read-only Point-and-Figure overlay.

    This is an evidence overlay only. It does not create a trade signal, does not
    confirm operator control, and does not mutate campaigns. The calculation uses
    daily close movement to build X/O columns with a 3-box reversal rule.
    """
    raw_bars = bars or []
    closes: List[float] = []

    for bar in raw_bars:
        if not isinstance(bar, dict):
            continue
        close = _safe_float(bar.get("c") or bar.get("close"))
        if close is not None and close > 0:
            closes.append(float(close))

    if len(closes) < 20:
        return {
            "pnf_status": "PNF_INSUFFICIENT_HISTORY",
            "pnf_target": None,
            "pnf_objective_price": None,
            "pnf_failure_price": None,
            "pnf_box_size": None,
            "pnf_reversal_boxes": 3,
            "pnf_column_count": 0,
            "pnf_current_column": None,
            "pnf_last_column_boxes": None,
            "pnf_breakout_status": "INSUFFICIENT_HISTORY",
            "pnf_reason": "Insufficient close history for dedicated Point-and-Figure column construction.",
            "pnf_evidence": {
                "history_closes": len(closes),
                "method": "close_based_point_and_figure",
                "reversal_boxes": 3,
                "read_only": True,
            },
        }

    latest_close = closes[-1]
    recent = closes[-252:] if len(closes) >= 252 else closes[:]

    recent_ranges: List[float] = []
    for i in range(1, len(recent)):
        prev = recent[i - 1]
        cur = recent[i]
        if prev > 0 and cur > 0:
            recent_ranges.append(abs(cur - prev))

    avg_abs_move = sum(recent_ranges[-20:]) / len(recent_ranges[-20:]) if recent_ranges else latest_close * 0.01
    percent_box = latest_close * 0.01
    raw_box_size = max(percent_box, avg_abs_move * 0.50, 0.01)

    if latest_close >= 100:
        rounding_unit = 0.25
    elif latest_close >= 25:
        rounding_unit = 0.10
    elif latest_close >= 5:
        rounding_unit = 0.05
    else:
        rounding_unit = 0.01

    box_size = max(round(raw_box_size / rounding_unit) * rounding_unit, rounding_unit)
    reversal_boxes = 3
    reversal_amount = box_size * reversal_boxes

    columns: List[Dict[str, Any]] = []
    base = closes[0]
    current_type: Optional[str] = None
    col_high = base
    col_low = base

    for price in closes[1:]:
        if current_type is None:
            if price >= base + box_size:
                current_type = "X"
                col_low = base
                col_high = price
            elif price <= base - box_size:
                current_type = "O"
                col_high = base
                col_low = price
            continue

        if current_type == "X":
            if price >= col_high + box_size:
                col_high = price
            elif price <= col_high - reversal_amount:
                boxes = max(1, int(round((col_high - col_low) / box_size)))
                columns.append({
                    "type": "X",
                    "high": col_high,
                    "low": col_low,
                    "boxes": boxes,
                })
                current_type = "O"
                col_high = col_high - box_size
                col_low = price
        else:
            if price <= col_low - box_size:
                col_low = price
            elif price >= col_low + reversal_amount:
                boxes = max(1, int(round((col_high - col_low) / box_size)))
                columns.append({
                    "type": "O",
                    "high": col_high,
                    "low": col_low,
                    "boxes": boxes,
                })
                current_type = "X"
                col_low = col_low + box_size
                col_high = price

    if current_type is None:
        return {
            "pnf_status": "PNF_RANGE_UNFORMED",
            "pnf_target": None,
            "pnf_objective_price": None,
            "pnf_failure_price": None,
            "pnf_box_size": round(box_size, 4),
            "pnf_reversal_boxes": reversal_boxes,
            "pnf_column_count": 0,
            "pnf_current_column": None,
            "pnf_last_column_boxes": None,
            "pnf_breakout_status": "NO_ONE_BOX_DIRECTIONAL_MOVE",
            "pnf_reason": "Price history did not form a directional Point-and-Figure column.",
            "pnf_evidence": {
                "history_closes": len(closes),
                "latest_close": round(latest_close, 4),
                "box_size": round(box_size, 4),
                "reversal_amount": round(reversal_amount, 4),
                "method": "close_based_point_and_figure",
                "read_only": True,
            },
        }

    boxes = max(1, int(round((col_high - col_low) / box_size)))
    columns.append({
        "type": current_type,
        "high": col_high,
        "low": col_low,
        "boxes": boxes,
    })

    last = columns[-1]
    prior = columns[:-1]
    last_type = str(last["type"])
    last_high = float(last["high"])
    last_low = float(last["low"])
    last_boxes = int(last["boxes"])

    prior_x_highs = [float(c["high"]) for c in prior if c.get("type") == "X"]
    prior_o_lows = [float(c["low"]) for c in prior if c.get("type") == "O"]

    if last_type == "X":
        breakout = bool(prior_x_highs and last_high > max(prior_x_highs))
        breakout_status = "BULLISH_PNF_BREAKOUT" if breakout else "BULLISH_PNF_COLUMN"
        objective = last_high + max(last_boxes, reversal_boxes) * box_size
        failure = last_high - reversal_amount
        status = "PNF_BULLISH_OBJECTIVE_COMPUTED"
    else:
        breakout = bool(prior_o_lows and last_low < min(prior_o_lows))
        breakout_status = "BEARISH_PNF_BREAKDOWN" if breakout else "BEARISH_PNF_COLUMN"
        objective = last_low - max(last_boxes, reversal_boxes) * box_size
        failure = last_low + reversal_amount
        status = "PNF_BEARISH_OBJECTIVE_COMPUTED"

    objective = max(objective, 0.01)
    failure = max(failure, 0.01)

    return {
        "pnf_status": status,
        "pnf_target": round(objective, 4),
        "pnf_objective_price": round(objective, 4),
        "pnf_failure_price": round(failure, 4),
        "pnf_box_size": round(box_size, 4),
        "pnf_reversal_boxes": reversal_boxes,
        "pnf_column_count": len(columns),
        "pnf_current_column": last_type,
        "pnf_last_column_boxes": last_boxes,
        "pnf_last_column_high": round(last_high, 4),
        "pnf_last_column_low": round(last_low, 4),
        "pnf_breakout_status": breakout_status,
        "pnf_reason": "Dedicated close-based Point-and-Figure overlay computed from historical daily closes.",
        "pnf_evidence": {
            "history_closes": len(closes),
            "latest_close": round(latest_close, 4),
            "box_size": round(box_size, 4),
            "reversal_boxes": reversal_boxes,
            "reversal_amount": round(reversal_amount, 4),
            "column_count": len(columns),
            "current_column": last_type,
            "last_column_boxes": last_boxes,
            "breakout": breakout,
            "breakout_status": breakout_status,
            "objective_price": round(objective, 4),
            "failure_price": round(failure, 4),
            "method": "close_based_point_and_figure",
            "read_only": True,
        },
    }





# SIGMALYTIC_STEP93E_READ_ONLY_GAMMA_OVERLAY
def _gamma_overlay(symbol: str, price: Optional[float], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Read-only Gamma / GEX movement-risk overlay.

    This uses the existing GEX engine when available. It is an overlay only:
    it does not create a trade signal, does not confirm operator control, and
    does not mutate campaigns.
    """
    base = {
        "gamma_status": "GAMMA_UNAVAILABLE",
        "gamma_source": "backend.gex_engine.score_gex",
        "gamma_reason": None,
        "gamma_available": False,
        "gamma_score": None,
        "gamma_regime": "UNKNOWN",
        "gamma_wall": None,
        "gamma_invalidation": None,
        "gamma_iv_rank": None,
        "gamma_net_market_gex": None,
        "gamma_strategy": None,
        "gamma_sot": None,
        "gamma_sweep_bias": None,
        "gamma_system_tier": None,
        "gamma_macro_aligned": None,
        "gamma_notes": None,
        "gamma_movement_risk_overlay": "UNAVAILABLE",
        "gamma_operator_control_source": False,
        "gamma_trade_signal": False,
        "gamma_read_only": True,
    }

    clean_symbol = str(symbol or "").upper().strip()
    if not clean_symbol:
        base["gamma_reason"] = "Missing symbol; Gamma overlay cannot be evaluated."
        return base

    if price is None or price <= 0:
        base["gamma_reason"] = "Missing current price; Gamma overlay cannot be evaluated."
        return base

    if _sigmalytic_score_gex is None:
        base["gamma_reason"] = "GEX engine import unavailable in this runtime."
        return base

    try:
        result = _sigmalytic_score_gex(
            clean_symbol,
            float(price),
            bars or [],
            is_intelligence_layer=True,
        )
    except Exception as exc:
        base["gamma_reason"] = f"GEX engine unavailable or provider call failed: {type(exc).__name__}: {exc}"
        return base

    if not isinstance(result, dict):
        base["gamma_reason"] = f"GEX engine returned non-dict result: {type(result).__name__}"
        return base

    gex_available = bool(result.get("gex_available") or result.get("available"))
    gex_score = _safe_float(result.get("gex_score") or result.get("score"))
    gex_regime = str(result.get("gex_regime") or result.get("regime") or "UNKNOWN").upper()
    gex_wall = result.get("gex_wall") or result.get("nearest_wall") or result.get("wall")
    gex_invalidation = result.get("gex_invalidation") or result.get("invalidation")
    gex_iv_rank = _safe_float(result.get("gex_iv_rank") or result.get("iv_rank"))
    net_market_gex = _safe_float(result.get("net_market_gex") or result.get("net_gex") or result.get("net_gamma"))
    gex_strategy = result.get("gex_strategy") or result.get("strategy")
    gex_sot = result.get("gex_sot") or result.get("sot")
    gex_sweep_bias = result.get("gex_sweep_bias") or result.get("sweep_bias")
    gex_system_tier = result.get("gex_system_tier") or result.get("system_tier")
    gex_macro_aligned = result.get("gex_macro_aligned") or result.get("macro_aligned")
    gex_notes = result.get("gex_notes") or result.get("notes")

    if gex_available:
        movement_risk = "GAMMA_STABILIZING" if "POSITIVE" in gex_regime else "GAMMA_DESTABILIZING" if "NEGATIVE" in gex_regime else "GAMMA_CONTEXT_AVAILABLE"
        gamma_status = "GAMMA_OVERLAY_COMPUTED"
        reason = "Live read-only GEX/Gamma overlay computed from existing GEX engine."
    else:
        movement_risk = "GAMMA_SOURCE_RETURNED_UNAVAILABLE"
        gamma_status = "GAMMA_SOURCE_UNAVAILABLE"
        reason = str(result.get("gex_notes") or result.get("reason") or "GEX engine returned unavailable status.")

    base.update({
        "gamma_status": gamma_status,
        "gamma_reason": reason,
        "gamma_available": gex_available,
        "gamma_score": _round(gex_score, 4),
        "gamma_regime": gex_regime,
        "gamma_wall": gex_wall,
        "gamma_invalidation": gex_invalidation,
        "gamma_iv_rank": _round(gex_iv_rank, 4),
        "gamma_net_market_gex": _round(net_market_gex, 4),
        "gamma_strategy": gex_strategy,
        "gamma_sot": gex_sot,
        "gamma_sweep_bias": gex_sweep_bias,
        "gamma_system_tier": gex_system_tier,
        "gamma_macro_aligned": gex_macro_aligned,
        "gamma_notes": gex_notes,
        "gamma_movement_risk_overlay": movement_risk,
        "gamma_raw_keys": sorted([str(k) for k in result.keys()])[:80],
    })
    return base





# SIGMALYTIC_STEP94C_READ_ONLY_DIVERGENCE_OVERLAY
def _divergence_overlay(symbol: str, price: Optional[float], bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Read-only Divergence Intelligence overlay.

    This is computed from price, volume, and momentum behavior in the existing
    daily bar history. It is diagnostic only. It does not create a trade signal,
    does not confirm operator control, and does not mutate campaigns.
    """
    base = {
        "divergence_status": "DIVERGENCE_UNAVAILABLE",
        "divergence_source": "seven_year_daily_price_volume_history",
        "divergence_reason": None,
        "divergence_available": False,
        "divergence_detected": False,
        "divergence_bias": "NEUTRAL",
        "divergence_type": "NO_MATERIAL_DIVERGENCE",
        "divergence_strength": 0,
        "divergence_window": "20D_60D",
        "divergence_price_change_20_pct": None,
        "divergence_price_change_60_pct": None,
        "divergence_prior_20_pct": None,
        "divergence_volume_ratio": None,
        "divergence_effort_result": "UNKNOWN",
        "divergence_price_structure": "UNKNOWN",
        "divergence_momentum_structure": "UNKNOWN",
        "divergence_volume_structure": "UNKNOWN",
        "divergence_movement_risk_overlay": "NO_DIVERGENCE_EVIDENCE",
        "divergence_operator_control_source": False,
        "divergence_trade_signal": False,
        "divergence_read_only": True,
        "divergence_evidence": {},
    }

    clean_symbol = str(symbol or "").upper().strip()
    raw_bars = bars or []

    closes: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    volumes: List[float] = []

    for bar in raw_bars:
        if not isinstance(bar, dict):
            continue
        c = _safe_float(bar.get("c") or bar.get("close"))
        h = _safe_float(bar.get("h") or bar.get("high"))
        l = _safe_float(bar.get("l") or bar.get("low"))
        v = _safe_float(bar.get("v") or bar.get("volume"))
        if c is not None and c > 0:
            closes.append(float(c))
        if h is not None and h > 0:
            highs.append(float(h))
        if l is not None and l > 0:
            lows.append(float(l))
        if v is not None and v >= 0:
            volumes.append(float(v))

    if not clean_symbol:
        base["divergence_reason"] = "Missing symbol; divergence overlay cannot be evaluated."
        return base

    if len(closes) < 80 or len(highs) < 80 or len(lows) < 80:
        base.update({
            "divergence_status": "DIVERGENCE_INSUFFICIENT_HISTORY",
            "divergence_reason": "Fewer than 80 daily bars available for divergence analysis.",
            "divergence_evidence": {
                "close_count": len(closes),
                "high_count": len(highs),
                "low_count": len(lows),
                "volume_count": len(volumes),
                "read_only": True,
            },
        })
        return base

    def pct_change(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None or a <= 0:
            return None
        return ((b - a) / a) * 100.0

    def avg(values: List[float]) -> Optional[float]:
        clean = [x for x in values if x is not None]
        if not clean:
            return None
        return sum(clean) / len(clean)

    latest = closes[-1]
    price_20 = pct_change(closes[-21], closes[-1]) if len(closes) >= 21 else None
    price_60 = pct_change(closes[-61], closes[-1]) if len(closes) >= 61 else None
    prior_20 = pct_change(closes[-41], closes[-21]) if len(closes) >= 41 else None

    recent_high = max(highs[-20:])
    prior_high = max(highs[-60:-20])
    recent_low = min(lows[-20:])
    prior_low = min(lows[-60:-20])

    recent_volume = avg(volumes[-20:]) if len(volumes) >= 20 else None
    prior_volume = avg(volumes[-80:-20]) if len(volumes) >= 80 else None
    volume_ratio = None
    if recent_volume is not None and prior_volume is not None and prior_volume > 0:
        volume_ratio = recent_volume / prior_volume

    lower_low = recent_low < prior_low * 0.995
    higher_low = recent_low > prior_low * 1.005
    higher_high = recent_high > prior_high * 1.005
    lower_high = recent_high < prior_high * 0.995

    momentum_improving = (
        price_20 is not None
        and prior_20 is not None
        and price_20 > prior_20 + 2.0
    )
    momentum_deteriorating = (
        price_20 is not None
        and prior_20 is not None
        and price_20 < prior_20 - 2.0
    )

    volume_not_confirming = (
        volume_ratio is not None
        and volume_ratio < 0.90
    )
    high_effort = (
        volume_ratio is not None
        and volume_ratio >= 1.35
    )
    low_result = (
        price_20 is not None
        and abs(price_20) <= 2.5
    )
    high_effort_low_result = high_effort and low_result

    evidence_flags = []
    bias = "NEUTRAL"
    div_type = "NO_MATERIAL_DIVERGENCE"
    movement_risk = "NO_DIVERGENCE_EVIDENCE"
    strength = 0

    if lower_low and momentum_improving:
        evidence_flags.append("LOWER_LOW_WITH_IMPROVING_MOMENTUM")
        bias = "BULLISH"
        div_type = "BULLISH_MOMENTUM_DIVERGENCE"
        movement_risk = "BULLISH_REVERSAL_RISK"
        strength += 40

    if lower_low and volume_not_confirming:
        evidence_flags.append("LOWER_LOW_WITH_WEAKER_VOLUME_CONFIRMATION")
        if bias == "NEUTRAL":
            bias = "BULLISH"
            div_type = "BULLISH_VOLUME_DIVERGENCE"
            movement_risk = "BULLISH_REVERSAL_RISK"
        strength += 25

    if higher_high and momentum_deteriorating:
        evidence_flags.append("HIGHER_HIGH_WITH_DETERIORATING_MOMENTUM")
        bias = "BEARISH"
        div_type = "BEARISH_MOMENTUM_DIVERGENCE"
        movement_risk = "BEARISH_REVERSAL_RISK"
        strength += 40

    if higher_high and volume_not_confirming:
        evidence_flags.append("HIGHER_HIGH_WITH_WEAKER_VOLUME_CONFIRMATION")
        if bias == "NEUTRAL":
            bias = "BEARISH"
            div_type = "BEARISH_VOLUME_DIVERGENCE"
            movement_risk = "BEARISH_REVERSAL_RISK"
        strength += 25

    if high_effort_low_result:
        evidence_flags.append("HIGH_EFFORT_LOW_RESULT")
        if price_20 is not None and price_20 < 0:
            if bias == "NEUTRAL":
                bias = "BULLISH"
                div_type = "DOWNSIDE_EFFORT_RESULT_DIVERGENCE"
                movement_risk = "SELLING_PRESSURE_INEFFICIENT"
            strength += 20
        elif price_20 is not None and price_20 >= 0:
            if bias == "NEUTRAL":
                bias = "BEARISH"
                div_type = "UPSIDE_EFFORT_RESULT_DIVERGENCE"
                movement_risk = "BUYING_EFFORT_INEFFICIENT"
            strength += 20

    if higher_low and price_20 is not None and price_20 > 0:
        evidence_flags.append("HIGHER_LOW_WITH_POSITIVE_20D_MOMENTUM")
        if bias == "NEUTRAL":
            div_type = "NO_BEARISH_DIVERGENCE_SUPPORTIVE_STRUCTURE"
            movement_risk = "STRUCTURE_SUPPORTIVE_NO_DIVERGENCE"
        strength += 5

    strength = int(max(0, min(100, strength)))

    price_structure = (
        "LOWER_LOW" if lower_low else
        "HIGHER_HIGH" if higher_high else
        "HIGHER_LOW" if higher_low else
        "LOWER_HIGH" if lower_high else
        "RANGE_OR_MIXED"
    )

    momentum_structure = (
        "IMPROVING" if momentum_improving else
        "DETERIORATING" if momentum_deteriorating else
        "STABLE_OR_MIXED"
    )

    volume_structure = (
        "WEAKER_CONFIRMATION" if volume_not_confirming else
        "HIGH_EFFORT" if high_effort else
        "NORMAL_OR_MIXED"
    )

    effort_result = (
        "HIGH_EFFORT_LOW_RESULT" if high_effort_low_result else
        "HIGH_EFFORT_DIRECTIONAL_RESULT" if high_effort else
        "NORMAL_EFFORT_RESULT"
    )

    detected = div_type not in {
        "NO_MATERIAL_DIVERGENCE",
        "NO_BEARISH_DIVERGENCE_SUPPORTIVE_STRUCTURE",
    }

    base.update({
        "divergence_status": "DIVERGENCE_OVERLAY_COMPUTED",
        "divergence_reason": "Read-only divergence overlay computed from price, volume, and momentum behavior.",
        "divergence_available": True,
        "divergence_detected": detected,
        "divergence_bias": bias,
        "divergence_type": div_type,
        "divergence_strength": strength,
        "divergence_price_change_20_pct": _round(price_20, 4),
        "divergence_price_change_60_pct": _round(price_60, 4),
        "divergence_prior_20_pct": _round(prior_20, 4),
        "divergence_volume_ratio": _round(volume_ratio, 4),
        "divergence_effort_result": effort_result,
        "divergence_price_structure": price_structure,
        "divergence_momentum_structure": momentum_structure,
        "divergence_volume_structure": volume_structure,
        "divergence_movement_risk_overlay": movement_risk,
        "divergence_evidence": {
            "symbol": clean_symbol,
            "latest_close": _round(latest, 4),
            "recent_high_20": _round(recent_high, 4),
            "prior_high_60_to_20": _round(prior_high, 4),
            "recent_low_20": _round(recent_low, 4),
            "prior_low_60_to_20": _round(prior_low, 4),
            "recent_volume_20_avg": _round(recent_volume, 4),
            "prior_volume_80_to_20_avg": _round(prior_volume, 4),
            "evidence_flags": evidence_flags,
            "read_only": True,
            "operator_control_source": False,
            "trade_signal": False,
        },
    })

    return base




# SIGMALYTIC_STEP90G_FORMAL_ODS_FROM_7YR_PRICE_VOLUME_EVIDENCE
# SIGMALYTIC_STEP91F_ODS_VOLUME_GATE_AND_MISSING_COMPONENT_REPAIR
def _bar_low(bar: Dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("l") or bar.get("low"))


def _bar_high(bar: Dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("h") or bar.get("high"))


def _bar_close(bar: Dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("c") or bar.get("close"))


def _bar_volume(bar: Dict[str, Any]) -> Optional[float]:
    return _safe_float(bar.get("v") or bar.get("volume"))


def _avg(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return statistics.mean(clean)


def _ods_from_7yr_history(
    row: Dict[str, Any],
    bars: List[Dict[str, Any]],
    outcome: Dict[str, Any],
    direct_ods: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Formal ODS evidence builder from 7-year price/volume history.

    This confirms ODS only when the historical record supplies all required evidence components:
    tested supply exhaustion, active demand/support validation, structurally meaningful location,
    and absence of contrary failure. It does not use rank, score, cohort expected return, future
    return, or probability as operator-control confirmation.
    """

    direct_status = str(direct_ods.get("ods_status") or "").upper()
    direct_label = str(direct_ods.get("ods_label") or "").upper()

    if direct_status == "CONFIRMED":
        direct_ods["ods_evidence_source"] = "direct_row_operator_control_field"
        direct_ods["ods_history_evaluated"] = False
        direct_ods["ods_reason"] = direct_ods.get("ods_reason") or "Direct row-level operator-control evidence already confirmed ODS."
        return direct_ods

    if direct_status == "NOT_CONFIRMED" and "CONTRARY" in direct_label:
        direct_ods["ods_evidence_source"] = "direct_row_contrary_evidence_field"
        direct_ods["ods_history_evaluated"] = False
        return direct_ods

    if not bars:
        return {
            "ods_label": "PENDING_NO_MARKET_HISTORY",
            "ods_score": None,
            "ods_status": "PENDING",
            "ods_reason": "No 7-year daily price/volume history was available for this row.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": False,
            "demand_support_confirmed": False,
            "structural_location_confirmed": False,
            "contrary_failure_absent": None,
            "ods_missing_components": ['market_history_unavailable'],
        }

    if len(bars) < 160:
        return {
            "ods_label": "PENDING_INSUFFICIENT_HISTORY",
            "ods_score": None,
            "ods_status": "PENDING",
            "ods_reason": "Fewer than 160 daily bars were available; ODS cannot be formally confirmed.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": False,
            "demand_support_confirmed": False,
            "structural_location_confirmed": False,
            "contrary_failure_absent": None,
            "ods_missing_components": ['insufficient_market_history'],
        }

    lows = [_bar_low(b) for b in bars]
    highs = [_bar_high(b) for b in bars]
    closes = [_bar_close(b) for b in bars]
    volumes = [_bar_volume(b) for b in bars]

    latest_close = closes[-1]
    if latest_close is None or latest_close <= 0:
        return {
            "ods_label": "PENDING_NO_LATEST_CLOSE",
            "ods_score": None,
            "ods_status": "PENDING",
            "ods_reason": "Latest close is unavailable; ODS cannot be evaluated.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": False,
            "demand_support_confirmed": False,
            "structural_location_confirmed": False,
            "contrary_failure_absent": None,
            "ods_missing_components": ['latest_close_unavailable'],
        }

    n = len(bars)
    anchor_index = outcome.get("campaign_anchor_index")
    try:
        anchor_index = int(anchor_index)
    except Exception:
        anchor_index = None

    if anchor_index is None or anchor_index < 0 or anchor_index >= n:
        recent_start = max(0, n - 252)
        candidates = [
            i for i in range(recent_start, n)
            if lows[i] is not None
        ]
        anchor_index = min(candidates, key=lambda i: lows[i]) if candidates else max(0, n - 60)

    support_window_start = max(0, anchor_index - 5)
    support_window_end = min(n, anchor_index + 6)
    support_lows = [l for l in lows[support_window_start:support_window_end] if l is not None]
    support_level = min(support_lows) if support_lows else lows[anchor_index]

    if support_level is None or support_level <= 0:
        return {
            "ods_label": "PENDING_NO_SUPPORT_LEVEL",
            "ods_score": None,
            "ods_status": "PENDING",
            "ods_reason": "Could not compute a support level from the 7-year record.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": False,
            "demand_support_confirmed": False,
            "structural_location_confirmed": False,
            "contrary_failure_absent": None,
            "ods_missing_components": ['support_level_unavailable'],
        }

    post_start = anchor_index
    post_bars = bars[post_start:]
    post_closes = [c for c in closes[post_start:] if c is not None]

    post_anchor_bars = max(0, n - 1 - anchor_index)
    if post_anchor_bars < 20:
        return {
            "ods_label": "PENDING_INSUFFICIENT_POST_ANCHOR_EVIDENCE",
            "ods_score": None,
            "ods_status": "PENDING",
            "ods_reason": "Fewer than 20 post-anchor daily bars; ODS cannot be formally confirmed yet.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": False,
            "demand_support_confirmed": False,
            "structural_location_confirmed": False,
            "contrary_failure_absent": None,
            "ods_post_anchor_bars": post_anchor_bars,
            "ods_missing_components": ['insufficient_post_anchor_evidence'],
        }

    recent60_start = max(post_start, n - 60)
    recent20_start = max(post_start, n - 20)
    prior60_start = max(post_start, n - 120)
    prior60_end = max(post_start, n - 60)

    recent_closes_60 = [c for c in closes[recent60_start:] if c is not None]
    recent_closes_20 = [c for c in closes[recent20_start:] if c is not None]

    support_touch_count = 0
    support_rebound_count = 0
    for i in range(post_start, n):
        low_i = lows[i]
        close_i = closes[i]
        if low_i is None or close_i is None:
            continue

        touched = low_i <= support_level * 1.06
        rebounded = close_i >= support_level * 1.03

        if touched:
            support_touch_count += 1
            if rebounded:
                support_rebound_count += 1

    recent_support_breaks = [
        c for c in recent_closes_60
        if c < support_level * 0.97
    ]

    latest_recovery_pct = ((latest_close - support_level) / support_level) * 100.0

    recent_down_volumes: List[float] = []
    prior_down_volumes: List[float] = []

    for i in range(max(1, recent20_start), n):
        c0 = closes[i - 1]
        c1 = closes[i]
        v = volumes[i]
        if c0 is not None and c1 is not None and c1 < c0 and v is not None:
            recent_down_volumes.append(v)

    for i in range(max(1, prior60_start), prior60_end):
        c0 = closes[i - 1]
        c1 = closes[i]
        v = volumes[i]
        if c0 is not None and c1 is not None and c1 < c0 and v is not None:
            prior_down_volumes.append(v)

    recent_down_avg = _avg(recent_down_volumes)
    prior_down_avg = _avg(prior_down_volumes)

    volume_ratio = None
    if recent_down_avg is not None and prior_down_avg is not None and prior_down_avg > 0:
        volume_ratio = recent_down_avg / prior_down_avg
        selling_pressure_not_expanding = volume_ratio <= 1.25
        if selling_pressure_not_expanding:
            volume_evidence_status = "VOLUME_EVIDENCE_AVAILABLE_NOT_EXPANDING"
        else:
            volume_evidence_status = "VOLUME_EVIDENCE_AVAILABLE_EXPANDING_SELL_PRESSURE"
    elif recent_down_avg is not None and (prior_down_avg is None or prior_down_avg <= 0):
        # No valid prior comparison exists. This is neutral/inconclusive, not contrary evidence.
        selling_pressure_not_expanding = None
        volume_evidence_status = "VOLUME_EVIDENCE_UNCOMPARABLE_NO_PRIOR_DOWNTICKS"
    else:
        # Insufficient volume comparison is neutral/inconclusive, not a hard ODS failure.
        selling_pressure_not_expanding = None
        volume_evidence_status = "VOLUME_EVIDENCE_INSUFFICIENT_NEUTRAL"

    recent20 = [c for c in closes[max(0, n - 20):] if c is not None]
    recent50 = [c for c in closes[max(0, n - 50):] if c is not None]
    sma20 = _avg(recent20)
    sma50 = _avg(recent50)

    demand_above_sma20 = bool(sma20 is not None and latest_close >= sma20)
    demand_above_sma50 = bool(sma50 is not None and latest_close >= sma50)

    lookback252_start = max(0, n - 252)
    lows252 = [l for l in lows[lookback252_start:] if l is not None]
    highs252 = [h for h in highs[lookback252_start:] if h is not None]

    if lows252 and highs252 and max(highs252) > min(lows252):
        low252 = min(lows252)
        high252 = max(highs252)
        support_position_252 = (support_level - low252) / (high252 - low252)
        current_position_252 = (latest_close - low252) / (high252 - low252)
    else:
        low252 = None
        high252 = None
        support_position_252 = None
        current_position_252 = None

    structurally_meaningful_location = bool(
        support_position_252 is not None
        and support_position_252 <= 0.50
        and current_position_252 is not None
        and current_position_252 <= 1.15
    )

    support_defended = len(recent_support_breaks) == 0
    tested_support = support_touch_count >= 2
    recovered_from_support = latest_recovery_pct >= 5.0

    volume_does_not_contradict_supply = (
        selling_pressure_not_expanding is True
        or selling_pressure_not_expanding is None
    )

    supply_exhaustion_confirmed = bool(
        tested_support
        and support_defended
        and recovered_from_support
        and volume_does_not_contradict_supply
    )

    demand_support_confirmed = bool(
        support_rebound_count >= 2
        and support_defended
        and recovered_from_support
        and (demand_above_sma20 or demand_above_sma50)
    )

    contrary_failure_absent = bool(
        support_defended
        and latest_close >= support_level * 0.97
    )

    component_count = len([
        x for x in (
            supply_exhaustion_confirmed,
            demand_support_confirmed,
            structurally_meaningful_location,
            contrary_failure_absent,
        )
        if x
    ])

    ods_score = component_count * 25

    evidence_payload = {
        "support_level": _round(support_level, 4),
        "latest_close": _round(latest_close, 4),
        "latest_recovery_pct": round(latest_recovery_pct, 4),
        "support_touch_count": support_touch_count,
        "support_rebound_count": support_rebound_count,
        "recent_support_break_count": len(recent_support_breaks),
        "post_anchor_bars": post_anchor_bars,
        "volume_evidence_status": volume_evidence_status,
        "recent_down_volume_avg": _round(recent_down_avg, 4),
        "prior_down_volume_avg": _round(prior_down_avg, 4),
        "volume_ratio_recent_to_prior_down": _round(volume_ratio, 4),
        "selling_pressure_not_expanding": selling_pressure_not_expanding,
        "volume_does_not_contradict_supply": volume_does_not_contradict_supply,
        "demand_above_sma20": demand_above_sma20,
        "demand_above_sma50": demand_above_sma50,
        "support_position_252": _round(support_position_252, 4),
        "current_position_252": _round(current_position_252, 4),
    }

    if not contrary_failure_absent:
        return {
            "ods_label": "NOT_CONFIRMED_CONTRARY_HISTORY",
            "ods_score": ods_score,
            "ods_status": "NOT_CONFIRMED",
            "ods_reason": "Contrary historical evidence exists: support/failure level was violated.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": False,
            "supply_exhaustion_confirmed": supply_exhaustion_confirmed,
            "demand_support_confirmed": demand_support_confirmed,
            "structural_location_confirmed": structurally_meaningful_location,
            "contrary_failure_absent": contrary_failure_absent,
            "ods_evidence_payload": evidence_payload,
        }

    if (
        supply_exhaustion_confirmed
        and demand_support_confirmed
        and structurally_meaningful_location
        and contrary_failure_absent
    ):
        return {
            "ods_label": "FORMALLY_CONFIRMED_FROM_7YR_HISTORY",
            "ods_score": 100,
            "ods_status": "CONFIRMED",
            "ods_reason": "7-year daily price/volume evidence confirms tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure.",
            "ods_evidence_source": "seven_year_daily_price_volume_history",
            "ods_history_evaluated": True,
            "operator_control_confirmed": True,
            "supply_exhaustion_confirmed": True,
            "demand_support_confirmed": True,
            "structural_location_confirmed": True,
            "contrary_failure_absent": True,
            "ods_evidence_payload": evidence_payload,
        }

    missing = []
    if not supply_exhaustion_confirmed:
        missing.append("supply_exhaustion")
    if not demand_support_confirmed:
        missing.append("demand_support_validation")
    if not structurally_meaningful_location:
        missing.append("structurally_meaningful_location")
    if not contrary_failure_absent:
        missing.append("absence_of_contrary_failure")

    return {
        "ods_label": "PENDING_INCOMPLETE_7YR_EVIDENCE",
        "ods_score": ods_score,
        "ods_status": "PENDING",
        "ods_reason": "7-year history was evaluated, but formal ODS is missing: " + ", ".join(missing),
        "ods_evidence_source": "seven_year_daily_price_volume_history",
        "ods_history_evaluated": True,
        "operator_control_confirmed": False,
        "supply_exhaustion_confirmed": supply_exhaustion_confirmed,
        "demand_support_confirmed": demand_support_confirmed,
        "structural_location_confirmed": structurally_meaningful_location,
        "contrary_failure_absent": contrary_failure_absent,
        "ods_missing_components": missing,
        "ods_evidence_payload": evidence_payload,
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
    direct_ods = _formal_ods(c)
    outcome = _outcome(c, bars)
    cohort = _cohort_readiness(c, bars, outcome)
    ods = _ods_from_7yr_history(c, bars, outcome, direct_ods)
    decay = _decay(c)
    # SIGMALYTIC_STEP92H_PNF_BAR_HISTORY_WIRING_FIX
    pnf = _pnf(c, targets, bars)
    gamma = _gamma_overlay(symbol, price, bars)
    divergence = _divergence_overlay(symbol, price, bars)

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
    c.update(cohort)
    c.update(path)
    c.update(targets)
    c.update(pnf)
    c.update(gamma)
    c.update(divergence)
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


