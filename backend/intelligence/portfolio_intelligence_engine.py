# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/portfolio_intelligence_engine.py

Phase 16 — Portfolio Intelligence

Ranks active campaigns against each other and converts campaign/outcome
intelligence into portfolio priority and capital weights.

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
    "A": 95.0,
    "B": 85.0,
    "C": 75.0,
    "WATCH": 55.0,
    "AVOID": 20.0,
    "UNKNOWN": 40.0,
}

STATE_BIAS_MAP = {
    "ADVANCE_LIKELY": 95.0,
    "ADVANCE_EDGE": 90.0,
    "HOLDING_PATTERN": 65.0,
    "MIXED": 55.0,
    "FAILURE_RISK": 20.0,
    "UNKNOWN": 45.0,
}

LIFECYCLE_MAP = {
    "BIRTH": 50.0,
    "CONFIRMED": 68.0,
    "SURVIVING": 76.0,
    "EXPANDING": 85.0,
    "MATURING": 58.0,
    "DISTRIBUTION_RISK": 20.0,
    "CLOSED": 0.0,
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
    return requests.request(
        method=method,
        url=f"{url}/rest/v1/{path.lstrip('/')}",
        headers=_headers("return=representation" if method.upper() in {"POST", "PATCH"} else None),
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


def _fetch_active_campaigns(limit: int = 3000) -> list[dict[str, Any]]:
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


def _priority_band(score: float) -> str:
    if score >= 85:
        return "ELITE"
    if score >= 70:
        return "HIGH"
    if score >= 55:
        return "STANDARD"
    if score >= 40:
        return "WATCH"
    return "AVOID"


def _campaign_strength_score(c: dict[str, Any]) -> float:
    lifecycle = str(c.get("current_state") or c.get("state_enum") or "BIRTH").upper()
    base = LIFECYCLE_MAP.get(lifecycle, 50.0)
    return_pct = _f(c.get("return_pct"), 0.0)
    pnf_progress = _f(c.get("pnf_progress_pct"), 0.0)
    decay_score = _f(c.get("decay_score"), 0.0)

    score = (
        base * 0.55
        + _clamp(50 + return_pct * 2.0, 0, 100) * 0.20
        + _clamp(pnf_progress, 0, 100) * 0.15
        + _clamp(100 - decay_score, 0, 100) * 0.10
    )
    return _clamp(score)


def _analog_score(c: dict[str, Any]) -> float:
    for key in ("analog_score", "analog_confidence", "historical_match_score", "historical_confidence_score"):
        if c.get(key) is not None:
            return _clamp(_f(c.get(key), 50.0))
    tier = str(c.get("historical_confidence") or "").upper()
    return {"TIER_1": 85.0, "TIER_2": 72.0, "TIER_3": 58.0, "TIER_4": 42.0}.get(tier, 50.0)


def _risk_score(c: dict[str, Any]) -> float:
    failure_probability = _f(c.get("outcome_failure_prob"), 50.0)
    rr = _f(c.get("outcome_risk_reward"), 1.0)
    decay = _f(c.get("decay_score"), 0.0)
    ods = _f(c.get("operator_dominance"), 50.0)
    rr_penalty = max(0.0, 100.0 - rr * 20.0)

    risk = (
        failure_probability * 0.55
        + rr_penalty * 0.25
        + decay * 0.15
        + max(0.0, 50.0 - ods) * 0.05
    )
    return _clamp(risk)


def _score_campaign(c: dict[str, Any]) -> dict[str, Any]:
    outcome_quality = str(c.get("outcome_quality") or "UNKNOWN").upper()
    transition_bias = str(c.get("transition_bias") or "UNKNOWN").upper()

    outcome_score = _f(c.get("outcome_quality_score"), OUTCOME_MAP.get(outcome_quality, 40.0))
    outcome_score = _clamp(outcome_score)

    ods_score = _clamp(_f(c.get("operator_dominance"), 50.0))
    campaign_score = _campaign_strength_score(c)
    state_score = STATE_BIAS_MAP.get(transition_bias, 45.0)
    analog_score = _analog_score(c)
    risk_score = _risk_score(c)

    raw_score = (
        outcome_score * 0.30
        + ods_score * 0.25
        + campaign_score * 0.20
        + state_score * 0.15
        + analog_score * 0.10
    )

    risk_adjusted = raw_score - max(0.0, risk_score - 45.0) * 0.18

    if outcome_quality == "AVOID":
        risk_adjusted = min(risk_adjusted, 39.0)
    if transition_bias == "FAILURE_RISK":
        risk_adjusted = min(risk_adjusted, 45.0)
    if bool(c.get("exit_signal")) or bool(c.get("conjunction_exit")):
        risk_adjusted = min(risk_adjusted, 25.0)

    portfolio_score = _clamp(risk_adjusted)

    return {
        "campaign_id": c.get("campaign_id"),
        "symbol": str(c.get("symbol") or "").upper(),
        "portfolio_score": round(portfolio_score, 2),
        "portfolio_rank": None,
        "priority_band": _priority_band(portfolio_score),
        "capital_weight": 0.0,
        "expected_return": round(_f(c.get("outcome_expected_return"), 0.0), 2),
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
        campaigns = _fetch_active_campaigns()
    except Exception as exc:
        log.error("PORTFOLIO INTELLIGENCE: failed to load campaigns — %s", exc)
        return {"status": "error", "reason": str(exc), "processed": 0, "written": 0, "errors": 1, "as_of": _utc_now_iso()}

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

    eligible_total = sum(max(0.0, r.get("portfolio_score", 0.0)) for r in rows if r.get("priority_band") != "AVOID")
    if eligible_total <= 0:
        eligible_total = sum(max(0.0, r.get("portfolio_score", 0.0)) for r in rows) or 1.0

    band_counts: dict[str, int] = {}
    for idx, r in enumerate(rows, start=1):
        r["portfolio_rank"] = idx
        if r.get("priority_band") == "AVOID":
            r["capital_weight"] = 0.0
        else:
            r["capital_weight"] = round(max(0.0, r.get("portfolio_score", 0.0)) / eligible_total * 100.0, 2)
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
        "processed": len(rows),
        "written": written,
        "errors": errors,
        "band_counts": band_counts,
        "top_symbols": [r.get("symbol") for r in top],
        "elapsed_secs": round(elapsed, 1),
        "as_of": _utc_now_iso(),
    }

    log.info(
        "PORTFOLIO INTELLIGENCE ENGINE complete in %.1fs | processed=%s written=%s errors=%s bands=%s",
        elapsed,
        len(rows),
        written,
        errors,
        band_counts,
    )

    return result
