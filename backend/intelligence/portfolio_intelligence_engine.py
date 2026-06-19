# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/portfolio_intelligence_engine.py

Phase 16 — Portfolio Intelligence

16A:
    Consolidates duplicate active campaigns into one current campaign per symbol.

16B:
    Recalibrates portfolio scores so rankings separate into actionable bands.

Reads:
    public.campaigns

Writes:
    public.portfolio_rankings
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("portfolio_intelligence_engine")


OUTCOME_MAP = {
    "A": 96.0,
    "B": 88.0,
    "C": 76.0,
    "WATCH": 60.0,
    "AVOID": 25.0,
    "UNKNOWN": 45.0,
}

STATE_BIAS_MAP = {
    "ADVANCE_LIKELY": 96.0,
    "ADVANCE_EDGE": 90.0,
    "HOLDING_PATTERN": 68.0,
    "MIXED": 58.0,
    "FAILURE_RISK": 25.0,
    "UNKNOWN": 48.0,
}

LIFECYCLE_MAP = {
    "BIRTH": 58.0,
    "CONFIRMED": 72.0,
    "SURVIVING": 80.0,
    "EXPANDING": 90.0,
    "MATURING": 65.0,
    "DISTRIBUTION_RISK": 25.0,
    "CLOSED": 0.0,
}

TIER_MAP = {
    "TIER_1": 90.0,
    "TIER_2": 78.0,
    "TIER_3": 62.0,
    "TIER_4": 45.0,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY are required")
    return url, key


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    _, key = _supabase_config()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _rest(method: str, path: str, *, params: Optional[dict[str, str]] = None, json: Any = None, timeout: int = 30) -> requests.Response:
    url, _ = _supabase_config()
    prefer = "return=representation" if method.upper() in {"POST", "PATCH"} else None
    return requests.request(
        method=method,
        url=f"{url}/rest/v1/{path.lstrip('/')}",
        headers=_headers(prefer),
        params=params,
        json=json,
        timeout=timeout,
    )


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _fetch_active_campaigns(limit: int = 5000) -> list[dict[str, Any]]:
    response = _rest(
        "GET",
        "campaigns",
        params={
            "select": "*",
            "status": "eq.ACTIVE",
            "order": "campaign_id.asc",
            "limit": str(limit),
        },
    )
    if response.status_code not in (200, 206):
        raise RuntimeError(f"Portfolio campaign fetch failed: {response.status_code} {response.text[:300]}")
    data = response.json()
    return data if isinstance(data, list) else []


def _row_recency_score(c: dict[str, Any]) -> float:
    """
    Used only for duplicate-symbol consolidation.
    Prefer higher campaign_id, newer updated_at, and non-exit records.
    """
    score = _f(c.get("campaign_id"), 0.0)

    if bool(c.get("exit_signal")) or bool(c.get("conjunction_exit")):
        score -= 1_000_000

    # Nudge records with Phase 15 data higher.
    if c.get("outcome_updated_at"):
        score += 10_000

    if c.get("transition_updated_at"):
        score += 5_000

    return score


def _dedupe_campaigns(campaigns: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """
    Keep one active campaign per symbol.
    This prevents duplicated symbols from consuming multiple portfolio ranks.
    """
    by_symbol: dict[str, dict[str, Any]] = {}
    duplicates = 0

    for c in campaigns:
        sym = str(c.get("symbol") or "").upper().strip()
        if not sym:
            continue

        existing = by_symbol.get(sym)
        if existing is None:
            by_symbol[sym] = c
            continue

        duplicates += 1
        if _row_recency_score(c) >= _row_recency_score(existing):
            by_symbol[sym] = c

    return list(by_symbol.values()), duplicates


def _priority_band(score: float) -> str:
    if score >= 80:
        return "ELITE"
    if score >= 68:
        return "HIGH"
    if score >= 55:
        return "STANDARD"
    if score >= 42:
        return "WATCH"
    return "AVOID"


def _campaign_strength_score(c: dict[str, Any]) -> float:
    lifecycle = str(c.get("current_state") or c.get("state_enum") or "BIRTH").upper()
    lifecycle_score = LIFECYCLE_MAP.get(lifecycle, 58.0)

    return_pct = _f(c.get("return_pct"), 0.0)
    pnf_progress = _f(c.get("pnf_progress_pct"), 0.0)
    decay_score = _f(c.get("decay_score"), 0.0)

    progress_component = _clamp(50 + return_pct * 4.0, 0, 100)
    pnf_component = _clamp(pnf_progress, 0, 100)
    decay_health = _clamp(100 - decay_score, 0, 100)

    return _clamp(
        lifecycle_score * 0.45
        + progress_component * 0.25
        + pnf_component * 0.15
        + decay_health * 0.15
    )


def _analog_score(c: dict[str, Any]) -> float:
    for key in ("analog_score", "analog_confidence", "historical_match_score", "historical_confidence_score"):
        if c.get(key) is not None:
            return _clamp(_f(c.get(key), 50.0))

    tier = str(c.get("historical_confidence") or "").upper()
    return TIER_MAP.get(tier, 55.0)


def _risk_score(c: dict[str, Any]) -> float:
    """
    Lower is better.
    """
    failure_probability = _f(c.get("outcome_failure_prob"), 50.0)
    rr = _f(c.get("outcome_risk_reward"), 1.0)
    decay = _f(c.get("decay_score"), 0.0)
    ods = _f(c.get("operator_dominance"), 50.0)
    expected_mae = abs(_f(c.get("outcome_expected_mae"), 3.5))

    rr_penalty = max(0.0, 100.0 - rr * 25.0)
    mae_penalty = _clamp(expected_mae * 8.0, 0, 100)

    risk = (
        failure_probability * 0.45
        + rr_penalty * 0.22
        + decay * 0.15
        + mae_penalty * 0.13
        + max(0.0, 50.0 - ods) * 0.05
    )

    return _clamp(risk)


def _score_campaign(c: dict[str, Any]) -> dict[str, Any]:
    outcome_quality = str(c.get("outcome_quality") or "UNKNOWN").upper()
    transition_bias = str(c.get("transition_bias") or "UNKNOWN").upper()

    outcome_score = _clamp(_f(c.get("outcome_quality_score"), OUTCOME_MAP.get(outcome_quality, 45.0)))
    ods_score = _clamp(_f(c.get("operator_dominance"), 50.0))
    campaign_score = _campaign_strength_score(c)
    state_score = STATE_BIAS_MAP.get(transition_bias, 48.0)
    analog_score = _analog_score(c)

    expected_return = _f(c.get("outcome_expected_return"), 0.0)
    expected_mfe = _f(c.get("outcome_expected_mfe"), 0.0)
    target1_prob = _f(c.get("outcome_target1_prob"), 0.0)
    target2_prob = _f(c.get("outcome_target2_prob"), 0.0)
    rr = _f(c.get("outcome_risk_reward"), 1.0)
    risk_score = _risk_score(c)

    expectancy_score = _clamp(
        50
        + expected_return * 5.0
        + max(0.0, expected_mfe) * 1.2
        + (target1_prob - 50.0) * 0.35
        + (target2_prob - 25.0) * 0.25
        + (rr - 1.5) * 8.0,
        0,
        100,
    )

    raw_score = (
        outcome_score * 0.26
        + ods_score * 0.20
        + campaign_score * 0.18
        + state_score * 0.12
        + analog_score * 0.09
        + expectancy_score * 0.15
    )

    # Risk adjustment, but do not over-compress good campaigns.
    risk_adjusted = raw_score - max(0.0, risk_score - 55.0) * 0.22

    # Explicit penalty gates.
    if outcome_quality == "AVOID":
        risk_adjusted = min(risk_adjusted, 41.0)
    elif outcome_quality == "WATCH":
        risk_adjusted = min(risk_adjusted, 67.0)

    if transition_bias == "FAILURE_RISK":
        risk_adjusted = min(risk_adjusted, 46.0)

    if bool(c.get("exit_signal")) or bool(c.get("conjunction_exit")):
        risk_adjusted = min(risk_adjusted, 25.0)

    portfolio_score = _clamp(risk_adjusted)
    band = _priority_band(portfolio_score)

    return {
        "campaign_id": c.get("campaign_id"),
        "symbol": str(c.get("symbol") or "").upper(),
        "portfolio_score": round(portfolio_score, 2),
        "portfolio_rank": None,
        "priority_band": band,
        "capital_weight": 0.0,
        "expected_return": round(expected_return, 2),
        "risk_score": round(risk_score, 2),
        "outcome_quality": outcome_quality,
        "updated_at": _utc_now_iso(),
    }


def _clear_rankings() -> None:
    response = _rest("DELETE", "portfolio_rankings", params={"id": "gte.0"}, timeout=30)
    if response.status_code not in (200, 204):
        log.warning("PORTFOLIO INTELLIGENCE: ranking clear failed %s %s", response.status_code, response.text[:250])


def _insert_rankings(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    writable = []
    now = _utc_now_iso()
    for r in rows:
        writable.append({
            "campaign_id": r.get("campaign_id"),
            "symbol": r.get("symbol"),
            "portfolio_score": r.get("portfolio_score"),
            "portfolio_rank": r.get("portfolio_rank"),
            "priority_band": r.get("priority_band"),
            "capital_weight": r.get("capital_weight"),
            "expected_return": r.get("expected_return"),
            "risk_score": r.get("risk_score"),
            "outcome_quality": r.get("outcome_quality"),
            "updated_at": now,
        })

    written = 0
    for i in range(0, len(writable), 100):
        batch = writable[i:i + 100]
        response = _rest("POST", "portfolio_rankings", json=batch, timeout=30)
        if response.status_code in (200, 201, 204):
            written += len(batch)
        else:
            log.warning("PORTFOLIO INTELLIGENCE: batch insert failed %s %s", response.status_code, response.text[:300])
    return written


async def run_portfolio_intelligence_cycle() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("PORTFOLIO INTELLIGENCE ENGINE starting — %s", started.isoformat())
    log.info("=" * 60)

    try:
        raw_campaigns = _fetch_active_campaigns()
    except Exception as exc:
        log.error("PORTFOLIO INTELLIGENCE: failed to load campaigns — %s", exc)
        return {"status": "error", "reason": str(exc), "processed": 0, "written": 0, "errors": 1, "as_of": _utc_now_iso()}

    campaigns, duplicates_removed = _dedupe_campaigns(raw_campaigns)

    rows = []
    errors = 0
    for c in campaigns:
        try:
            campaign_id = c.get("campaign_id")
            symbol = str(c.get("symbol") or "").upper().strip()
            if not campaign_id or not symbol:
                continue
            rows.append(_score_campaign(c))
        except Exception as exc:
            errors += 1
            log.error("PORTFOLIO INTELLIGENCE: scoring error symbol=%s campaign_id=%s — %s", c.get("symbol"), c.get("campaign_id"), exc)

    rows.sort(key=lambda x: (x.get("portfolio_score", 0), x.get("expected_return", 0), -x.get("risk_score", 100)), reverse=True)

    band_counts: dict[str, int] = {}
    eligible_rows = [r for r in rows if r.get("priority_band") not in ("AVOID",) and r.get("portfolio_score", 0) >= 42]
    eligible_total = sum(max(0.0, r.get("portfolio_score", 0.0)) for r in eligible_rows) or 1.0

    for idx, r in enumerate(rows, start=1):
        r["portfolio_rank"] = idx
        if r in eligible_rows:
            r["capital_weight"] = round(max(0.0, r.get("portfolio_score", 0.0)) / eligible_total * 100.0, 2)
        else:
            r["capital_weight"] = 0.0

        band = str(r.get("priority_band") or "UNKNOWN")
        band_counts[band] = band_counts.get(band, 0) + 1

    try:
        _clear_rankings()
        written = _insert_rankings(rows)
    except Exception as exc:
        log.error("PORTFOLIO INTELLIGENCE: write failed — %s", exc)
        written = 0
        errors += 1

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    top = rows[:10]

    for r in top:
        log.info(
            "PORTFOLIO RANK: #%s %s score=%s band=%s weight=%s er=%s risk=%s quality=%s",
            r.get("portfolio_rank"),
            r.get("symbol"),
            r.get("portfolio_score"),
            r.get("priority_band"),
            r.get("capital_weight"),
            r.get("expected_return"),
            r.get("risk_score"),
            r.get("outcome_quality"),
        )

    result = {
        "status": "ok" if errors == 0 else "partial",
        "raw_campaigns": len(raw_campaigns),
        "duplicates_removed": duplicates_removed,
        "processed": len(rows),
        "written": written,
        "errors": errors,
        "band_counts": band_counts,
        "top_symbols": [r.get("symbol") for r in top],
        "elapsed_secs": round(elapsed, 1),
        "as_of": _utc_now_iso(),
    }

    log.info(
        "PORTFOLIO INTELLIGENCE ENGINE complete in %.1fs | raw=%s deduped=%s duplicates_removed=%s written=%s errors=%s bands=%s",
        elapsed,
        len(raw_campaigns),
        len(rows),
        duplicates_removed,
        written,
        errors,
        band_counts,
    )

    return result

