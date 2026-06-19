# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/campaign_outcome_engine.py

Phase 15 — Campaign Outcome Intelligence
----------------------------------------
Converts campaign lifecycle intelligence into expected trade economics.

This engine uses:
    current_state
    operator_dominance
    decay_score
    transition_advance_prob
    transition_failure_prob
    transition_bias
    return_pct
    pnf_progress_pct
    mfe90_expected
    pnf_target
    entry_price
    current_price

It writes:
    outcome_expected_return
    outcome_expected_mfe
    outcome_expected_mae
    outcome_expected_duration_days
    outcome_target1_prob
    outcome_target2_prob
    outcome_failure_prob
    outcome_risk_reward
    outcome_quality
    outcome_summary
    outcome_updated_at
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("campaign_outcome_engine")


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _fetch_active_campaigns(limit: int = 2000) -> list[dict[str, Any]]:
    r = _rest(
        "GET",
        "campaigns",
        params={
            "select": "*",
            "status": "eq.ACTIVE",
            "order": "campaign_id.asc",
            "limit": str(limit),
        },
    )
    if r.status_code not in (200, 206):
        raise RuntimeError(f"Outcome fetch failed: {r.status_code} {r.text[:300]}")
    data = r.json()
    return data if isinstance(data, list) else []


def _quality(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "WATCH"
    return "AVOID"


def _state_base(state: str) -> dict[str, float]:
    state = str(state or "BIRTH").upper()
    return {
        "BIRTH":             {"ret": 3.0, "mfe": 7.0,  "mae": -4.5, "days": 18, "t1": 46, "t2": 24},
        "CONFIRMED":         {"ret": 6.0, "mfe": 11.0, "mae": -4.0, "days": 22, "t1": 58, "t2": 34},
        "SURVIVING":         {"ret": 8.0, "mfe": 14.0, "mae": -3.8, "days": 26, "t1": 66, "t2": 42},
        "EXPANDING":         {"ret": 9.5, "mfe": 17.0, "mae": -5.0, "days": 20, "t1": 64, "t2": 45},
        "MATURING":          {"ret": 4.0, "mfe": 8.0,  "mae": -6.0, "days": 12, "t1": 42, "t2": 22},
        "DISTRIBUTION_RISK": {"ret": -3.0,"mfe": 3.0,  "mae": -10.0,"days": 5,  "t1": 12, "t2": 4},
    }.get(state, {"ret": 3.0, "mfe": 7.0, "mae": -5.0, "days": 18, "t1": 45, "t2": 22})


def _score_outcome(c: dict[str, Any]) -> dict[str, Any]:
    state = str(c.get("current_state") or c.get("state_enum") or "BIRTH").upper()
    bias = str(c.get("transition_bias") or "MIXED").upper()

    ods = _f(c.get("operator_dominance"), 50.0)
    decay = _f(c.get("decay_score"), 0.0)
    dist = _f(c.get("distribution_risk"), max(0, 100 - ods))
    ret_now = _f(c.get("return_pct"), 0.0)
    pnf = _f(c.get("pnf_progress_pct"), 0.0)
    mfe90 = _f(c.get("mfe90_expected"), 10.0)
    adv = _f(c.get("transition_advance_prob"), 35.0)
    fail = _f(c.get("transition_failure_prob"), 35.0)
    exp_trans_ret = _f(c.get("transition_expected_return"), 0.0)
    exp_trans_mfe = _f(c.get("transition_expected_mfe"), 0.0)
    exp_trans_mae = _f(c.get("transition_expected_mae"), -5.0)
    trans_days = _i(c.get("transition_expected_days"), 10)

    entry = _f(c.get("entry_price"), 0.0)
    current = _f(c.get("current_price"), 0.0)
    target = _f(c.get("pnf_target"), 0.0)

    base = _state_base(state)

    # Economics blend: state prior + transition projection + current evidence.
    expected_return = (
        base["ret"] * 0.45
        + exp_trans_ret * 0.30
        + (ods - 50.0) * 0.08
        - decay * 0.045
        - max(0.0, dist - 45.0) * 0.035
        + min(pnf, 100.0) * 0.025
        + ret_now * 0.20
    )

    expected_mfe = (
        base["mfe"] * 0.45
        + exp_trans_mfe * 0.25
        + min(mfe90, 35.0) * 0.18
        + max(0.0, ods - 50.0) * 0.07
        - decay * 0.025
    )

    expected_mae = (
        base["mae"] * 0.55
        + exp_trans_mae * 0.25
        - max(0.0, decay - 30.0) * 0.05
        - max(0.0, fail - 35.0) * 0.04
        - max(0.0, 45.0 - ods) * 0.04
    )

    duration = int(round(base["days"] * 0.55 + trans_days * 0.45))
    duration = max(2, min(90, duration))

    target1_prob = (
        base["t1"]
        + (adv - 35.0) * 0.45
        - (fail - 30.0) * 0.25
        + (ods - 50.0) * 0.35
        - decay * 0.18
        + min(pnf, 100.0) * 0.10
    )

    target2_prob = (
        base["t2"]
        + (adv - 35.0) * 0.35
        - (fail - 30.0) * 0.18
        + (ods - 50.0) * 0.25
        - decay * 0.12
        + min(pnf, 100.0) * 0.08
    )

    failure_prob = (
        fail
        + decay * 0.30
        + max(0.0, dist - 45.0) * 0.20
        - max(0.0, ods - 55.0) * 0.20
    )

    if bias == "ADVANCE_LIKELY":
        target1_prob += 10
        target2_prob += 7
        failure_prob -= 8
    elif bias == "ADVANCE_EDGE":
        target1_prob += 6
        target2_prob += 4
        failure_prob -= 4
    elif bias == "FAILURE_RISK":
        target1_prob -= 16
        target2_prob -= 10
        failure_prob += 18
    elif bias == "HOLDING_PATTERN":
        target1_prob -= 2
        target2_prob -= 2

    if state == "DISTRIBUTION_RISK":
        expected_return = min(expected_return, -1.0)
        expected_mfe = min(expected_mfe, 4.0)
        expected_mae = min(expected_mae, -8.0)
        target1_prob = min(target1_prob, 20)
        target2_prob = min(target2_prob, 8)
        failure_prob = max(failure_prob, 75)

    # If P&F target is visible, cap/anchor expected MFE to distance available.
    if current > 0 and target > current:
        target_distance = ((target - current) / current) * 100
        expected_mfe = min(max(expected_mfe, target_distance * 0.35), max(target_distance, expected_mfe))

    target1_prob = _clamp(target1_prob, 1, 95)
    target2_prob = _clamp(target2_prob, 1, 90)
    failure_prob = _clamp(failure_prob, 1, 98)

    upside = max(expected_mfe, expected_return, 0.1)
    downside = abs(expected_mae) if expected_mae else 1.0
    risk_reward = upside / max(downside, 0.1)

    quality_score = (
        target1_prob * 0.28
        + target2_prob * 0.18
        + adv * 0.16
        + max(0.0, ods) * 0.14
        + min(max(risk_reward, 0.0), 5.0) * 6.0
        - failure_prob * 0.22
        - decay * 0.12
    )
    quality_score = _clamp(quality_score, 0, 100)
    quality = _quality(quality_score)

    summary = (
        f"{quality} outcome | T1 {target1_prob:.0f}% | T2 {target2_prob:.0f}% | "
        f"Fail {failure_prob:.0f}% | ER {expected_return:+.1f}% | "
        f"RR {risk_reward:.2f}"
    )

    return {
        "outcome_expected_return": round(expected_return, 2),
        "outcome_expected_mfe": round(expected_mfe, 2),
        "outcome_expected_mae": round(expected_mae, 2),
        "outcome_expected_duration_days": duration,
        "outcome_target1_prob": round(target1_prob, 1),
        "outcome_target2_prob": round(target2_prob, 1),
        "outcome_failure_prob": round(failure_prob, 1),
        "outcome_risk_reward": round(risk_reward, 2),
        "outcome_quality": quality,
        "outcome_quality_score": round(quality_score, 1),
        "outcome_summary": summary,
        "outcome_updated_at": _utc_now_iso(),
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

    log.warning("OUTCOME write failed campaign_id=%s status=%s body=%s", campaign_id, r.status_code, r.text[:250])
    return False


def _insert_observation(campaign: dict[str, Any], updates: dict[str, Any]) -> None:
    row = {
        "campaign_id": campaign.get("campaign_id"),
        "symbol": campaign.get("symbol"),
        "observed_at": _utc_now_iso(),
        "current_state": campaign.get("current_state") or campaign.get("state_enum"),
        "transition_bias": campaign.get("transition_bias"),
        "operator_dominance": campaign.get("operator_dominance"),
        "decay_score": campaign.get("decay_score"),
        "expected_return": updates.get("outcome_expected_return"),
        "expected_mfe": updates.get("outcome_expected_mfe"),
        "expected_mae": updates.get("outcome_expected_mae"),
        "expected_duration_days": updates.get("outcome_expected_duration_days"),
        "target1_prob": updates.get("outcome_target1_prob"),
        "target2_prob": updates.get("outcome_target2_prob"),
        "failure_prob": updates.get("outcome_failure_prob"),
        "risk_reward": updates.get("outcome_risk_reward"),
        "quality": updates.get("outcome_quality"),
        "quality_score": updates.get("outcome_quality_score"),
        "summary": updates.get("outcome_summary"),
    }

    r = _rest("POST", "campaign_outcome_observations", json=row, timeout=20)
    if r.status_code not in (200, 201, 204):
        log.warning("OUTCOME observation insert skipped: %s %s", r.status_code, r.text[:250])


async def run_campaign_outcome_cycle() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("CAMPAIGN OUTCOME ENGINE starting — %s", started.isoformat())
    log.info("=" * 60)

    try:
        campaigns = _fetch_active_campaigns()
    except Exception as exc:
        log.error("CAMPAIGN OUTCOME ENGINE failed to load campaigns — %s", exc)
        return {"status": "error", "reason": str(exc), "processed": 0, "written": 0, "errors": 1}

    processed = 0
    written = 0
    errors = 0
    quality_counts: dict[str, int] = {}

    for c in campaigns:
        campaign_id = c.get("campaign_id")
        symbol = str(c.get("symbol") or "").upper()

        if not campaign_id or not symbol:
            continue

        try:
            updates = _score_outcome(c)

            if _patch_campaign(campaign_id, updates):
                written += 1

            _insert_observation(c, updates)

            q = str(updates.get("outcome_quality") or "UNKNOWN")
            quality_counts[q] = quality_counts.get(q, 0) + 1
            processed += 1

            log.info(
                "CAMPAIGN OUTCOME: %s campaign_id=%s quality=%s er=%s mfe=%s mae=%s t1=%s t2=%s fail=%s rr=%s",
                symbol,
                campaign_id,
                updates.get("outcome_quality"),
                updates.get("outcome_expected_return"),
                updates.get("outcome_expected_mfe"),
                updates.get("outcome_expected_mae"),
                updates.get("outcome_target1_prob"),
                updates.get("outcome_target2_prob"),
                updates.get("outcome_failure_prob"),
                updates.get("outcome_risk_reward"),
            )

        except Exception as exc:
            errors += 1
            log.error("CAMPAIGN OUTCOME error %s campaign_id=%s — %s", symbol, campaign_id, exc)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    result = {
        "status": "ok" if errors == 0 else "partial",
        "processed": processed,
        "written": written,
        "errors": errors,
        "quality_counts": quality_counts,
        "elapsed_secs": round(elapsed, 1),
        "as_of": _utc_now_iso(),
    }

    log.info(
        "CAMPAIGN OUTCOME ENGINE complete in %.1fs | processed=%s written=%s errors=%s quality=%s",
        elapsed,
        processed,
        written,
        errors,
        quality_counts,
    )

    return result

