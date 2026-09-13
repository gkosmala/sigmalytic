# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/state_transition_engine.py

Phase 14D — State Transition Intelligence
-----------------------------------------
Production-ready campaign lifecycle transition engine.

Purpose:
    Predict what is most likely to happen next to each ACTIVE campaign after
    the nightly lifecycle, ODS, analog, and decay engines have populated the
    campaign row.

Inputs expected on public.campaigns:
    campaign_id
    symbol
    current_state / state_enum
    operator_dominance
    distribution_risk
    decay_score
    return_pct
    pnf_progress_pct
    days_in_state
    campaign_age_days / duration_days
    mfe90_expected
    current_price
    entry_price
    pnf_target

Outputs written back to public.campaigns:
    transition_next_state
    transition_advance_prob
    transition_failure_prob
    transition_continuation_prob
    transition_expected_days
    transition_expected_return
    transition_expected_mfe
    transition_expected_mae
    transition_bias
    transition_updated_at

Optional observation table:
    public.campaign_transition_observations

The engine is schema-tolerant for the observation table: if that table is
missing or its schema is stale, the monitor logs a warning and continues.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("state_transition_engine")


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------

STATE_ORDER = [
    "BIRTH",
    "CONFIRMED",
    "SURVIVING",
    "EXPANDING",
    "MATURING",
    "DISTRIBUTION_RISK",
    "CLOSED",
]

NEXT_STATE = {
    "BIRTH": "CONFIRMED",
    "CONFIRMED": "SURVIVING",
    "SURVIVING": "EXPANDING",
    "EXPANDING": "MATURING",
    "MATURING": "DISTRIBUTION_RISK",
    "DISTRIBUTION_RISK": "CLOSED",
    "CLOSED": "CLOSED",
}

BASE_EXPECTATIONS = {
    "BIRTH": {
        "advance": 0.42,
        "failure": 0.22,
        "days": 6,
        "ret": 2.0,
        "mfe": 5.0,
        "mae": -3.5,
    },
    "CONFIRMED": {
        "advance": 0.55,
        "failure": 0.16,
        "days": 8,
        "ret": 4.5,
        "mfe": 8.5,
        "mae": -3.2,
    },
    "SURVIVING": {
        "advance": 0.63,
        "failure": 0.12,
        "days": 10,
        "ret": 7.0,
        "mfe": 12.0,
        "mae": -3.0,
    },
    "EXPANDING": {
        "advance": 0.58,
        "failure": 0.14,
        "days": 12,
        "ret": 8.5,
        "mfe": 15.0,
        "mae": -4.0,
    },
    "MATURING": {
        "advance": 0.25,
        "failure": 0.28,
        "days": 7,
        "ret": 3.0,
        "mfe": 7.0,
        "mae": -5.0,
    },
    "DISTRIBUTION_RISK": {
        "advance": 0.05,
        "failure": 0.65,
        "days": 3,
        "ret": -2.0,
        "mfe": 2.5,
        "mae": -8.0,
    },
    "CLOSED": {
        "advance": 0.0,
        "failure": 1.0,
        "days": 0,
        "ret": 0.0,
        "mfe": 0.0,
        "mae": 0.0,
    },
}


# ---------------------------------------------------------------------------
# Supabase REST helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY are required"
        )

    return url, key


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    _, key = _supabase_config()

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def _rest(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, str]] = None,
    json: Any = None,
    timeout: int = 25,
) -> requests.Response:
    url, _ = _supabase_config()

    return requests.request(
        method=method,
        url=f"{url}/rest/v1/{path.lstrip('/')}",
        headers=_headers("return=representation" if method.upper() in {"POST", "PATCH"} else None),
        params=params,
        json=json,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Safe coercion
# ---------------------------------------------------------------------------

def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _state(value: Any) -> str:
    raw = str(value or "BIRTH").upper().strip()
    return raw if raw in STATE_ORDER else "BIRTH"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _fetch_active_campaigns(limit: int = 2000) -> list[dict[str, Any]]:
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
        raise RuntimeError(
            f"State transition fetch failed: {response.status_code} {response.text[:300]}"
        )

    data = response.json()
    return data if isinstance(data, list) else []


def _historical_transition_rates() -> dict[str, dict[str, float]]:
    """
    Optional calibration from campaign_state_history.

    If that table or its columns do not exist yet, the function returns an empty
    dict and the engine falls back to priors. This lets Phase 14D run immediately
    even before the history table is fully normalized.
    """
    response = _rest(
        "GET",
        "campaign_state_history",
        params={
            "select": "old_state,new_state",
            "limit": "5000",
        },
        timeout=15,
    )

    if response.status_code not in (200, 206):
        log.info(
            "STATE TRANSITION: history unavailable, using priors — %s %s",
            response.status_code,
            response.text[:180],
        )
        return {}

    try:
        rows = response.json()
    except Exception:
        return {}

    if not isinstance(rows, list):
        return {}

    totals: dict[str, int] = {}
    advances: dict[str, int] = {}
    failures: dict[str, int] = {}

    for row in rows:
        old = _state(row.get("old_state"))
        new = _state(row.get("new_state"))

        if old == "CLOSED":
            continue

        totals[old] = totals.get(old, 0) + 1

        if new == NEXT_STATE.get(old):
            advances[old] = advances.get(old, 0) + 1

        if new in {"DISTRIBUTION_RISK", "CLOSED"} and old not in {
            "DISTRIBUTION_RISK",
            "CLOSED",
        }:
            failures[old] = failures.get(old, 0) + 1

    rates: dict[str, dict[str, float]] = {}

    for state, total in totals.items():
        # Minimum count prevents very small samples from overfitting.
        if total >= 5:
            rates[state] = {
                "advance": advances.get(state, 0) / total,
                "failure": failures.get(state, 0) / total,
                "n": float(total),
            }

    if rates:
        log.info("STATE TRANSITION: calibrated from history for states=%s", sorted(rates.keys()))

    return rates


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_transition(
    campaign: dict[str, Any],
    historical_rates: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """
    Score a single campaign.

    Probability values are stored as percentages for dashboard readability.
    """
    state = _state(campaign.get("current_state") or campaign.get("state_enum"))
    base = dict(BASE_EXPECTATIONS.get(state, BASE_EXPECTATIONS["BIRTH"]))

    advance = float(base["advance"])
    failure = float(base["failure"])

    # Optional empirical calibration.
    if state in historical_rates:
        advance = advance * 0.65 + historical_rates[state].get("advance", advance) * 0.35
        failure = failure * 0.65 + historical_rates[state].get("failure", failure) * 0.35

    ods = _f(campaign.get("operator_dominance"), 50.0)
    distribution_risk = _f(campaign.get("distribution_risk"), max(0.0, 100.0 - ods))
    decay_score = _f(campaign.get("decay_score"), 0.0)
    return_pct = _f(campaign.get("return_pct"), 0.0)
    pnf_progress_pct = _f(campaign.get("pnf_progress_pct"), 0.0)
    days_in_state = _i(campaign.get("days_in_state"), 0)
    age_days = _i(campaign.get("campaign_age_days") or campaign.get("duration_days"), 0)
    mfe90_expected = _f(campaign.get("mfe90_expected"), 10.0)

    # Operator Dominance.
    if ods >= 75:
        advance += 0.18
        failure -= 0.08
    elif ods >= 65:
        advance += 0.12
        failure -= 0.05
    elif ods >= 55:
        advance += 0.07
        failure -= 0.03
    elif ods < 35:
        advance -= 0.16
        failure += 0.18
    elif ods < 45:
        advance -= 0.10
        failure += 0.12
    elif ods < 50:
        advance -= 0.05
        failure += 0.06

    # Decay Monitor.
    if decay_score >= 80:
        advance -= 0.28
        failure += 0.38
    elif decay_score >= 60:
        advance -= 0.18
        failure += 0.24
    elif decay_score >= 30:
        advance -= 0.07
        failure += 0.09
    elif decay_score <= 10 and state in {"CONFIRMED", "SURVIVING", "EXPANDING"}:
        advance += 0.04
        failure -= 0.02

    # Distribution risk.
    if distribution_risk >= 70:
        advance -= 0.12
        failure += 0.20
    elif distribution_risk >= 55:
        advance -= 0.08
        failure += 0.12
    elif distribution_risk >= 45:
        advance -= 0.04
        failure += 0.07

    # Open return and progress.
    if return_pct >= 10 or pnf_progress_pct >= 45:
        advance += 0.14
        failure -= 0.06
    elif return_pct >= 5 or pnf_progress_pct >= 25:
        advance += 0.09
        failure -= 0.04
    elif return_pct >= 2 or pnf_progress_pct >= 10:
        advance += 0.04
        failure -= 0.02
    elif return_pct <= -8:
        advance -= 0.14
        failure += 0.20
    elif return_pct <= -4:
        advance -= 0.09
        failure += 0.14
    elif return_pct < 0:
        advance -= 0.03
        failure += 0.05

    # Time and stagnation.
    if days_in_state >= 10 and pnf_progress_pct < 10 and state in {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
    }:
        advance -= 0.08
        failure += 0.08

    if days_in_state >= 15 and state in {"EXPANDING", "MATURING"}:
        failure += 0.08

    if age_days >= 30 and pnf_progress_pct < 15:
        advance -= 0.05
        failure += 0.07

    # State-specific overrides.
    if state == "DISTRIBUTION_RISK":
        advance = min(advance, 0.18)
        failure = max(failure, 0.48)

    if state == "MATURING" and decay_score >= 30:
        failure += 0.10

    # Final probability hygiene.
    advance = _clamp(advance, 0.01, 0.95)
    failure = _clamp(failure, 0.01, 0.95)

    if advance + failure > 0.98:
        scale = 0.98 / (advance + failure)
        advance *= scale
        failure *= scale

    continuation = max(0.0, 1.0 - advance - failure)

    # Expected values.
    expected_days = max(1, int(round(float(base["days"]) + days_in_state * 0.20)))

    expected_return = (
        float(base["ret"])
        + (ods - 50.0) * 0.08
        - decay_score * 0.04
        + return_pct * 0.15
        + min(pnf_progress_pct, 100.0) * 0.025
    )

    expected_mfe = (
        float(base["mfe"])
        + max(0.0, ods - 50.0) * 0.06
        - decay_score * 0.025
        + min(mfe90_expected, 30.0) * 0.08
    )

    expected_mae = (
        float(base["mae"])
        - max(0.0, decay_score - 30.0) * 0.05
        - max(0.0, 45.0 - ods) * 0.04
        - max(0.0, distribution_risk - 50.0) * 0.035
    )

    # Bias.
    if failure >= 0.50:
        bias = "FAILURE_RISK"
    elif advance >= 0.68:
        bias = "ADVANCE_LIKELY"
    elif advance >= 0.52:
        bias = "ADVANCE_EDGE"
    elif continuation >= 0.45:
        bias = "HOLDING_PATTERN"
    else:
        bias = "MIXED"

    next_state = NEXT_STATE.get(state, "CLOSED")

    return {
        "transition_next_state": next_state,
        "transition_advance_prob": round(advance * 100.0, 1),
        "transition_failure_prob": round(failure * 100.0, 1),
        "transition_continuation_prob": round(continuation * 100.0, 1),
        "transition_expected_days": expected_days,
        "transition_expected_return": round(expected_return, 2),
        "transition_expected_mfe": round(expected_mfe, 2),
        "transition_expected_mae": round(expected_mae, 2),
        "transition_bias": bias,
        "transition_updated_at": _utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _patch_campaign(campaign_id: Any, updates: dict[str, Any]) -> bool:
    payload = dict(updates)
    payload["updated_at"] = _utc_now_iso()

    response = _rest(
        "PATCH",
        "campaigns",
        params={"campaign_id": f"eq.{campaign_id}"},
        json=payload,
        timeout=20,
    )

    if response.status_code in (200, 204):
        return True

    log.warning(
        "STATE TRANSITION write failed campaign_id=%s status=%s body=%s",
        campaign_id,
        response.status_code,
        response.text[:250],
    )
    return False


def _insert_observation(campaign: dict[str, Any], updates: dict[str, Any]) -> None:
    row = {
        "campaign_id": campaign.get("campaign_id"),
        "symbol": campaign.get("symbol"),
        "observed_at": _utc_now_iso(),
        "current_state": campaign.get("current_state") or campaign.get("state_enum"),
        "next_state": updates.get("transition_next_state"),
        "advance_prob": updates.get("transition_advance_prob"),
        "failure_prob": updates.get("transition_failure_prob"),
        "continuation_prob": updates.get("transition_continuation_prob"),
        "expected_days": updates.get("transition_expected_days"),
        "expected_return": updates.get("transition_expected_return"),
        "expected_mfe": updates.get("transition_expected_mfe"),
        "expected_mae": updates.get("transition_expected_mae"),
        "transition_bias": updates.get("transition_bias"),
        "operator_dominance": campaign.get("operator_dominance"),
        "decay_score": campaign.get("decay_score"),
        "return_pct": campaign.get("return_pct"),
        "pnf_progress_pct": campaign.get("pnf_progress_pct"),
    }

    response = _rest(
        "POST",
        "campaign_transition_observations",
        json=row,
        timeout=20,
    )

    if response.status_code not in (200, 201, 204):
        log.warning(
            "STATE TRANSITION observation insert skipped: %s %s",
            response.status_code,
            response.text[:250],
        )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def run_state_transition_cycle() -> dict[str, Any]:
    """
    Entrypoint for backend/main.py scheduler and manual admin trigger.
    """
    started = datetime.now(timezone.utc)

    log.info("=" * 60)
    log.info("STATE TRANSITION ENGINE starting — %s", started.isoformat())
    log.info("=" * 60)

    try:
        campaigns = _fetch_active_campaigns()
        historical_rates = _historical_transition_rates()
    except Exception as exc:
        log.error("STATE TRANSITION ENGINE failed to initialize — %s", exc)
        return {
            "status": "error",
            "reason": str(exc),
            "processed": 0,
            "written": 0,
            "errors": 1,
            "as_of": _utc_now_iso(),
        }

    processed = 0
    written = 0
    errors = 0
    bias_counts: dict[str, int] = {}

    for campaign in campaigns:
        campaign_id = campaign.get("campaign_id")
        symbol = str(campaign.get("symbol") or "").upper().strip()

        if not campaign_id or not symbol:
            continue

        try:
            updates = _score_transition(campaign, historical_rates)

            if _patch_campaign(campaign_id, updates):
                written += 1

            _insert_observation(campaign, updates)

            bias = str(updates.get("transition_bias") or "UNKNOWN")
            bias_counts[bias] = bias_counts.get(bias, 0) + 1
            processed += 1

            log.info(
                "STATE TRANSITION: %s campaign_id=%s state=%s next=%s adv=%s fail=%s cont=%s bias=%s",
                symbol,
                campaign_id,
                campaign.get("current_state") or campaign.get("state_enum"),
                updates.get("transition_next_state"),
                updates.get("transition_advance_prob"),
                updates.get("transition_failure_prob"),
                updates.get("transition_continuation_prob"),
                updates.get("transition_bias"),
            )

        except Exception as exc:
            errors += 1
            log.error(
                "STATE TRANSITION error %s campaign_id=%s — %s",
                symbol,
                campaign_id,
                exc,
            )

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    result = {
        "status": "ok" if errors == 0 else "partial",
        "processed": processed,
        "written": written,
        "errors": errors,
        "bias_counts": bias_counts,
        "elapsed_secs": round(elapsed, 1),
        "as_of": _utc_now_iso(),
    }

    log.info(
        "STATE TRANSITION ENGINE complete in %.1fs | processed=%s written=%s errors=%s bias=%s",
        elapsed,
        processed,
        written,
        errors,
        bias_counts,
    )

    return result

