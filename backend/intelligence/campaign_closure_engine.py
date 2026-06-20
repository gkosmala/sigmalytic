# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/campaign_closure_engine.py

Campaign Exit & Closure Confirmation Engine
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from supabase import create_client

log = logging.getLogger("campaign_closure_engine")

CLOSURE_ENGINE_VERSION = "13A.1"

ACTIVE_STATES = [
    "BIRTH",
    "CONFIRMED",
    "SURVIVING",
    "EXPANDING",
    "MATURING",
    "DISTRIBUTION_RISK",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE key")

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


def _rest(method: str, table: str, params=None, json=None, timeout: int = 30):
    url, _ = _supabase_config()
    return requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=_headers(prefer="return=representation"),
        params=params or {},
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


def _s(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).upper().strip()


def _fetch_active_campaigns(limit: int = 2000) -> list[dict[str, Any]]:
    params = {
        "select": "*",
        "status": "eq.ACTIVE",
        "current_state": f"in.({','.join(ACTIVE_STATES)})",
        "limit": str(limit),
        "order": "campaign_id.asc",
    }

    r = _rest("GET", "campaigns", params=params)

    if r.status_code != 200:
        raise RuntimeError(f"Campaign fetch failed: {r.status_code} {r.text[:250]}")

    return r.json() or []


def _wyckoff_exit_score(c: dict[str, Any]) -> float:
    score = 0.0
    state = _s(c.get("current_state") or c.get("state_enum"))
    distribution_risk = _f(c.get("distribution_risk"))
    ods = _f(c.get("operator_dominance"))
    progress = _f(c.get("progress_score"), 50.0)
    return_pct = _f(c.get("return_pct"))

    if state == "DISTRIBUTION_RISK":
        score += 35
    if distribution_risk >= 70:
        score += 30
    elif distribution_risk >= 50:
        score += 15
    if ods < 35:
        score += 20
    elif ods < 45:
        score += 10
    if progress < 35:
        score += 10
    if return_pct < -5:
        score += 15
    elif return_pct < 0:
        score += 5

    return min(score, 100.0)


def _weis_exit_score(c: dict[str, Any]) -> float:
    score = 0.0
    decay_score = _f(c.get("decay_score"))
    pnf_progress = _f(c.get("pnf_progress_pct"))
    return_pct = _f(c.get("return_pct"))
    outcome_mae = abs(_f(c.get("outcome_expected_mae")))

    if decay_score >= 85:
        score += 40
    elif decay_score >= 70:
        score += 30
    elif decay_score >= 55:
        score += 15
    if pnf_progress <= 5:
        score += 25
    elif pnf_progress <= 20:
        score += 10
    if return_pct <= -5:
        score += 25
    elif return_pct <= 0:
        score += 15
    if outcome_mae >= 10:
        score += 10

    return min(score, 100.0)


def _livermore_exit_score(c: dict[str, Any]) -> float:
    score = 0.0
    outcome_failure = _f(c.get("outcome_failure_prob"))
    transition_failure = _f(c.get("transition_failure_prob"))
    exit_signal = bool(c.get("exit_signal"))
    conjunction_exit = bool(c.get("conjunction_exit"))
    return_pct = _f(c.get("return_pct"))

    if outcome_failure >= 95:
        score += 40
    elif outcome_failure >= 80:
        score += 30
    elif outcome_failure >= 60:
        score += 15
    if transition_failure >= 90:
        score += 30
    elif transition_failure >= 70:
        score += 20
    elif transition_failure >= 55:
        score += 10
    if exit_signal:
        score += 15
    if conjunction_exit:
        score += 15
    if return_pct <= -10:
        score += 15
    elif return_pct <= -5:
        score += 10

    return min(score, 100.0)


def _closure_reason(c: dict[str, Any], closure_score: float) -> tuple[str, str]:
    if bool(c.get("conjunction_exit")):
        return (
            "CONFIRMED_CONJUNCTION_EXIT",
            "Exit confirmed by conjunction_exit, high failure risk, and campaign deterioration.",
        )

    if _f(c.get("decay_score")) >= 85:
        return (
            "DECAY_EXIT",
            "Decay score reached exit threshold with weak campaign behavior.",
        )

    if _s(c.get("current_state")) == "DISTRIBUTION_RISK":
        return (
            "DISTRIBUTION_CONFIRMED",
            "Campaign in distribution risk with confirmed deterioration evidence.",
        )

    if _f(c.get("outcome_failure_prob")) >= 95:
        return (
            "FAILURE_PROBABILITY",
            "Outcome engine shows extreme failure probability.",
        )

    return (
        "CAMPAIGN_TERMINATION",
        f"Composite closure score reached {round(closure_score, 2)}.",
    )


def score_campaign_closure(c: dict[str, Any]) -> dict[str, Any]:
    wyckoff = _wyckoff_exit_score(c)
    weis = _weis_exit_score(c)
    livermore = _livermore_exit_score(c)

    closure_score = round(
        wyckoff * 0.40 + weis * 0.30 + livermore * 0.30,
        2,
    )

    exit_candidate = closure_score >= 60
    exit_confirmed = closure_score >= 75

    should_close = (
        closure_score >= 90
        or (
            exit_confirmed
            and bool(c.get("conjunction_exit"))
            and _f(c.get("outcome_failure_prob")) >= 90
        )
        or (
            _s(c.get("current_state")) == "DISTRIBUTION_RISK"
            and _f(c.get("decay_score")) >= 85
            and _f(c.get("outcome_failure_prob")) >= 90
        )
    )

    close_reason = None
    reason_detail = None

    if should_close:
        close_reason, reason_detail = _closure_reason(c, closure_score)

    return {
        "wyckoff_exit_score": round(wyckoff, 2),
        "weis_exit_score": round(weis, 2),
        "livermore_exit_score": round(livermore, 2),
        "closure_score": closure_score,
        "exit_candidate": exit_candidate,
        "exit_confirmed": exit_confirmed,
        "should_close": should_close,
        "close_reason": close_reason,
        "closure_reason_detail": reason_detail,
    }


def _patch_campaign(campaign_id: Any, updates: dict[str, Any]) -> bool:
    url, key = _supabase_config()

    payload = dict(updates)
    payload["updated_at"] = _utc_now_iso()

    client = create_client(url, key)

    result = (
        client
        .table("campaigns")
        .update(payload)
        .eq("campaign_id", campaign_id)
        .execute()
    )

    data = getattr(result, "data", None)

    if isinstance(data, list) and len(data) > 0:
        return True

    log.warning(
        "Closure write returned no updated rows campaign_id=%s result=%s",
        campaign_id,
        result,
    )
    return False


def run_campaign_closure_cycle() -> dict[str, Any]:
    started = _utc_now_iso()
    campaigns = _fetch_active_campaigns()

    processed = 0
    written = 0
    closed = 0
    exit_candidates = 0
    exit_confirmed = 0
    errors = 0
    results = []

    for c in campaigns:
        campaign_id = c.get("campaign_id")
        symbol = c.get("symbol")

        if not campaign_id:
            continue

        try:
            scored = score_campaign_closure(c)

            updates = {
                "wyckoff_exit_score": scored["wyckoff_exit_score"],
                "weis_exit_score": scored["weis_exit_score"],
                "livermore_exit_score": scored["livermore_exit_score"],
                "closure_score": scored["closure_score"],
                "exit_candidate": scored["exit_candidate"],
                "exit_confirmed": scored["exit_confirmed"],
                "closure_engine_version": CLOSURE_ENGINE_VERSION,
                "closure_updated_at": _utc_now_iso(),
            }

            if scored["should_close"]:
                updates.update(
                    {
                        "current_state": "CLOSED",
                        "state_enum": "CLOSED",
                        "status": "CLOSED",
                        "closed_at": _utc_now_iso(),
                        "close_reason": scored["close_reason"],
                        "closure_reason_detail": scored["closure_reason_detail"],
                    }
                )
                closed += 1

            if scored["exit_candidate"]:
                exit_candidates += 1

            if scored["exit_confirmed"]:
                exit_confirmed += 1

            did_write = _patch_campaign(campaign_id, updates)

            if did_write:
                written += 1

            processed += 1

            results.append(
                {
                    "campaign_id": campaign_id,
                    "symbol": symbol,
                    "closure_score": scored["closure_score"],
                    "exit_candidate": scored["exit_candidate"],
                    "exit_confirmed": scored["exit_confirmed"],
                    "closed": scored["should_close"],
                    "written": did_write,
                    "close_reason": scored["close_reason"],
                }
            )

        except Exception as exc:
            errors += 1
            log.error(
                "Closure engine error campaign_id=%s symbol=%s: %s",
                campaign_id,
                symbol,
                exc,
            )

    return {
        "ok": errors == 0,
        "engine": "campaign_closure_engine",
        "version": CLOSURE_ENGINE_VERSION,
        "started_at": started,
        "finished_at": _utc_now_iso(),
        "processed": processed,
        "written": written,
        "closed": closed,
        "exit_candidates": exit_candidates,
        "exit_confirmed": exit_confirmed,
        "errors": errors,
        "results": results[:100],
    }


def run_closure_engine() -> dict[str, Any]:
    return run_campaign_closure_cycle()


def run_campaign_closure_engine() -> dict[str, Any]:
    return run_campaign_closure_cycle()


def main() -> dict[str, Any]:
    return run_campaign_closure_cycle()