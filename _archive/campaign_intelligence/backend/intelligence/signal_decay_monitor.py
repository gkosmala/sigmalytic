# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/signal_decay_monitor.py

Phase 14B — Campaign Decay Monitor
----------------------------------
Scores active campaigns for degradation after the Campaign Pipeline and ODS
engine have populated:

    current_state
    operator_dominance
    distribution_risk
    return_pct
    pnf_progress_pct
    days_in_state
    campaign_age_days
    current_price
    entry_price
    pnf_target

Decay Score:
    0-29   HEALTHY
    30-59  MONITOR
    60-79  WEAKENING
    80-100 EXIT_CANDIDATE

Design:
    This monitor does not replace ODS.
    It combines ODS, lifecycle state, progress failure, downside pressure,
    target failure, and age/time risk into one campaign-health score.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("signal_decay_monitor")


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


def _rest(method: str, path: str, *, params: Optional[dict[str, str]] = None, json: Any = None, timeout: int = 25) -> requests.Response:
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


def _i(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _fetch_active_campaigns(limit: int = 2000) -> list[dict[str, Any]]:
    params = {
        "select": "*",
        "status": "eq.ACTIVE",
        "order": "campaign_id.asc",
        "limit": str(limit),
    }
    r = _rest("GET", "campaigns", params=params)
    if r.status_code not in (200, 206):
        raise RuntimeError(f"Decay fetch failed: {r.status_code} {r.text[:300]}")
    data = r.json()
    return data if isinstance(data, list) else []


def _decay_band(score: float) -> str:
    if score >= 80:
        return "EXIT_CANDIDATE"
    if score >= 60:
        return "WEAKENING"
    if score >= 30:
        return "MONITOR"
    return "HEALTHY"


def _recommendation(score: float, state: str, ods: float, return_pct: float, pnf_progress: float) -> str:
    if score >= 80:
        return "Exit candidate: review immediately; require recovery confirmation before holding."
    if score >= 60:
        return "Weakening: reduce priority, monitor for failed rally or additional ODS deterioration."
    if score >= 30:
        return "Monitor: campaign is not failing, but progress/ODS is not strong enough for complacency."
    if state in {"CONFIRMED", "SURVIVING", "EXPANDING"} and ods >= 55:
        return "Healthy: operator support remains acceptable; continue lifecycle monitoring."
    return "Healthy/early: insufficient deterioration evidence."


def _score_campaign(c: dict[str, Any]) -> dict[str, Any]:
    state = str(c.get("current_state") or c.get("state_enum") or "BIRTH").upper()
    ods = _f(c.get("operator_dominance"), 50.0)
    risk = _f(c.get("distribution_risk"), max(0.0, 100.0 - ods))
    ret = _f(c.get("return_pct"), 0.0)
    progress = _f(c.get("pnf_progress_pct"), 0.0)
    days_in_state = _i(c.get("days_in_state"), 0)
    age = _i(c.get("campaign_age_days") or c.get("duration_days"), 0)
    mfe90_expected = _f(c.get("mfe90_expected"), 10.0)

    score = 0.0
    reasons: list[str] = []

    # 1. Operator Dominance degradation.
    if ods < 35:
        score += 35
        reasons.append(f"ODS very weak ({ods:.0f})")
    elif ods < 45:
        score += 25
        reasons.append(f"ODS below control threshold ({ods:.0f})")
    elif ods < 55:
        score += 12
        reasons.append(f"ODS mixed/soft ({ods:.0f})")

    # 2. Distribution risk.
    if risk >= 65:
        score += 25
        reasons.append(f"Distribution risk elevated ({risk:.0f})")
    elif risk >= 45:
        score += 12
        reasons.append(f"Distribution risk rising ({risk:.0f})")

    # 3. Lifecycle state penalty.
    if state == "DISTRIBUTION_RISK":
        score += 28
        reasons.append("State is DISTRIBUTION_RISK")
    elif state == "MATURING":
        score += 10
        reasons.append("Maturing campaign requires tighter monitoring")
    elif state == "BIRTH" and age >= 10 and progress <= 5:
        score += 12
        reasons.append("Birth campaign aging without progress")

    # 4. Return / drawdown.
    if ret <= -8:
        score += 25
        reasons.append(f"Open return materially negative ({ret:.1f}%)")
    elif ret <= -4:
        score += 15
        reasons.append(f"Open return negative ({ret:.1f}%)")
    elif ret < 0:
        score += 5
        reasons.append(f"Open return slightly negative ({ret:.1f}%)")

    # 5. Progress failure versus expected lifecycle.
    if age >= 20 and progress < 10:
        score += 22
        reasons.append(f"No meaningful P&F progress after {age} days")
    elif age >= 10 and progress < 5:
        score += 12
        reasons.append(f"Slow P&F progress after {age} days")

    if state in {"CONFIRMED", "SURVIVING", "EXPANDING"} and progress < 5 and days_in_state >= 7:
        score += 12
        reasons.append(f"Stalled {state} state for {days_in_state} days")

    # 6. Underperformance relative to expected 90-day MFE.
    if mfe90_expected > 0 and age >= 15:
        expected_capture = min(mfe90_expected, age / 90.0 * mfe90_expected)
        if ret < expected_capture * 0.20:
            score += 8
            reasons.append("Return lagging expected MFE90 path")

    score = round(min(100.0, max(0.0, score)), 1)
    band = _decay_band(score)

    # Keep conjunction exit strict.
    conjunction_exit = (
        score >= 80
        or (state in {"MATURING", "DISTRIBUTION_RISK"} and ods < 40)
        or (state == "DISTRIBUTION_RISK" and ret <= -4)
    )

    if not reasons:
        reasons.append("No material decay evidence")

    return {
        "decay_score": score,
        "decay_band": band,
        "decay_reason": "; ".join(reasons[:5]),
        "decay_recommendation": _recommendation(score, state, ods, ret, progress),
        "conjunction_exit": conjunction_exit,
        "exit_signal": conjunction_exit,
    }


def _patch_campaign(campaign_id: Any, updates: dict[str, Any]) -> bool:
    payload = dict(updates)
    payload["updated_at"] = _utc_now_iso()

    r = _rest(
        "PATCH",
        "campaigns",
        params={"campaign_id": f"eq.{campaign_id}"},
        json=payload,
        timeout=20,
    )
    if r.status_code in (200, 204):
        return True

    log.warning("Decay write failed campaign_id=%s status=%s body=%s", campaign_id, r.status_code, r.text[:250])
    return False


def _insert_decay_observation(campaign: dict[str, Any], updates: dict[str, Any]) -> None:
    row = {
        "campaign_id": campaign.get("campaign_id"),
        "symbol": campaign.get("symbol"),
        "observed_at": _utc_now_iso(),
        "decay_score": updates.get("decay_score"),
        "decay_band": updates.get("decay_band"),
        "decay_reason": updates.get("decay_reason"),
        "operator_dominance": campaign.get("operator_dominance"),
        "distribution_risk": campaign.get("distribution_risk"),
        "return_pct": campaign.get("return_pct"),
        "pnf_progress_pct": campaign.get("pnf_progress_pct"),
        "current_state": campaign.get("current_state") or campaign.get("state_enum"),
        "conjunction_exit": updates.get("conjunction_exit"),
    }

    r = _rest("POST", "campaign_decay_observations", json=row, timeout=20)
    if r.status_code not in (200, 201, 204):
        # Optional table. Do not fail the monitor if it is absent.
        log.warning("Decay observation insert skipped: %s %s", r.status_code, r.text[:250])


async def run_decay_monitoring_cycle() -> dict[str, Any]:
    """
    Main entrypoint used by backend/main.py scheduler and manual full-nightly flow.
    """
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("DECAY MONITOR starting — %s", started.isoformat())
    log.info("=" * 60)

    try:
        campaigns = _fetch_active_campaigns()
    except Exception as exc:
        log.error("DECAY MONITOR failed to load campaigns — %s", exc)
        return {"status": "error", "reason": str(exc), "processed": 0}

    processed = 0
    written = 0
    errors = 0
    counts = {"HEALTHY": 0, "MONITOR": 0, "WEAKENING": 0, "EXIT_CANDIDATE": 0}
    exits: list[str] = []

    for c in campaigns:
        campaign_id = c.get("campaign_id")
        symbol = str(c.get("symbol") or "").upper()

        if not campaign_id or not symbol:
            continue

        try:
            updates = _score_campaign(c)
            if _patch_campaign(campaign_id, updates):
                written += 1

            _insert_decay_observation(c, updates)

            band = str(updates.get("decay_band") or "HEALTHY")
            counts[band] = counts.get(band, 0) + 1

            if updates.get("conjunction_exit"):
                exits.append(symbol)

            processed += 1

            log.info(
                "DECAY MONITOR: %s campaign_id=%s score=%s band=%s exit=%s reason=%s",
                symbol,
                campaign_id,
                updates.get("decay_score"),
                updates.get("decay_band"),
                updates.get("conjunction_exit"),
                updates.get("decay_reason"),
            )

        except Exception as exc:
            errors += 1
            log.error("DECAY MONITOR error %s campaign_id=%s — %s", symbol, campaign_id, exc)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    result = {
        "status": "ok" if errors == 0 else "partial",
        "processed": processed,
        "written": written,
        "errors": errors,
        "exit_candidates": len(exits),
        "exit_symbols": exits[:50],
        "bands": counts,
        "elapsed_secs": round(elapsed, 1),
        "as_of": _utc_now_iso(),
    }

    log.info(
        "DECAY MONITOR complete in %.1fs | processed=%s written=%s exits=%s errors=%s bands=%s",
        elapsed,
        processed,
        written,
        len(exits),
        errors,
        counts,
    )

    return result

