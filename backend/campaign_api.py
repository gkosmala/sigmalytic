# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_api.py
------------------------
FastAPI router serving campaign data to the frontend.

Mount in main.py:
    from campaign_api import campaign_router
    app.include_router(campaign_router)

Endpoints:
    GET  /api/campaigns/active        — all active campaigns
    GET  /api/campaigns/{id}          — single campaign detail
    POST /api/campaigns/{id}/close    — manually close a campaign
    GET  /api/campaigns/summary       — portfolio-level stats
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests as _rq
from fastapi import APIRouter, HTTPException

log = logging.getLogger("campaign_api")

campaign_router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

# ── Supabase connection ───────────────────────────────────────────────────────

def _sb_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")

def _sb_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

def _headers() -> dict:
    key = _sb_key()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }

def _sb_get(table: str, params: dict) -> list[dict]:
    """Generic Supabase REST GET."""
    try:
        r = _rq.get(
            f"{_sb_url()}/rest/v1/{table}",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        log.error("Supabase GET %s failed: %s %s", table, r.status_code, r.text[:200])
    except Exception as exc:
        log.error("Supabase GET %s error: %s", table, exc)
    return []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@campaign_router.get("/active")
async def get_active_campaigns() -> dict[str, Any]:
    """
    Return all active campaigns sorted by tier then days open.
    Used by the Campaign Intelligence tab in the frontend.
    """
    campaigns = _sb_get("campaigns", {
        "select": (
            "campaign_id,display_label,symbol,timeframe,birth_date,"
            "campaign_age_days,current_state,state_enum,"
            "entry_price,stop_price,current_price,pnf_target,"
            "mfe90_expected,obstacle_score,progress_score,d_score,"
            "duration_days,layer,operator_dominance,distribution_risk,"
            "decay_score,decay_band,decay_reason,decay_recommendation,"
            "conjunction_exit,exit_signal,"
            "historical_confidence,status,close_notes,updated_at"
        ),
        "status": "eq.ACTIVE",
        "order":  "campaign_age_days.desc",
        "limit":  "200",
    })

    # Compute derived fields
    for c in campaigns:
        try:
            entry   = float(c.get("entry_price") or 0)
            current = float(c.get("current_price") or 0)
            pnf     = float(c.get("pnf_target") or 0)

            c["return_pct"] = round(
                (current - entry) / entry * 100, 2
            ) if entry > 0 else 0.0

            pnf_span = pnf - entry
            c["pnf_progress_pct"] = round(
                (current - entry) / pnf_span * 100, 1
            ) if pnf_span > 0 else 0.0

            stored_conjunction = bool(c.get("conjunction_exit"))
            stored_exit = bool(c.get("exit_signal"))
            fallback_conjunction = (
                float(c.get("operator_dominance") or 100) < 40
                and c.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}
            )
            c["conjunction_exit"] = stored_conjunction or stored_exit or fallback_conjunction
            c["exit_signal"] = stored_exit or c["conjunction_exit"]
        except Exception:
            c["return_pct"]       = 0.0
            c["pnf_progress_pct"] = 0.0
            c["conjunction_exit"] = False

    return {
        "campaigns": campaigns,
        "count":     len(campaigns),
        "as_of":     datetime.now(timezone.utc).isoformat(),
    }


@campaign_router.get("/summary")
async def get_campaign_summary() -> dict[str, Any]:
    """
    Portfolio-level campaign statistics.
    Used by the Status Center.
    """
    campaigns = _sb_get("campaigns", {
        "select": (
            "current_state,historical_confidence,"
            "operator_dominance,distribution_risk,"
            "decay_score,decay_band,conjunction_exit,exit_signal,"
            "entry_price,current_price,mfe90_expected"
        ),
        "status": "eq.ACTIVE",
        "limit":  "500",
    })

    total = len(campaigns)
    if total == 0:
        return {
            "total_active":    0,
            "tier_1":          0,
            "tier_2":          0,
            "avg_ods":         0,
            "conjunction_exits": 0,
            "avg_return_pct":  0,
            "state_breakdown": {},
        }

    tier_1    = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier_2    = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    avg_ods   = sum(float(c.get("operator_dominance") or 0) for c in campaigns) / total
    exits     = sum(
        1 for c in campaigns
        if bool(c.get("exit_signal"))
        or bool(c.get("conjunction_exit"))
        or (
            float(c.get("operator_dominance") or 100) < 40
            and c.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}
        )
    )

    decay_counts = {
        "HEALTHY": 0,
        "MONITOR": 0,
        "WEAKENING": 0,
        "EXIT_CANDIDATE": 0,
        "UNKNOWN": 0,
    }
    for c in campaigns:
        band = str(c.get("decay_band") or "UNKNOWN").upper()
        decay_counts[band] = decay_counts.get(band, 0) + 1

    returns = []
    for c in campaigns:
        try:
            entry   = float(c.get("entry_price") or 0)
            current = float(c.get("current_price") or 0)
            if entry > 0:
                returns.append((current - entry) / entry * 100)
        except Exception:
            pass

    avg_return = sum(returns) / len(returns) if returns else 0.0

    state_breakdown: dict[str, int] = {}
    for c in campaigns:
        s = c.get("current_state", "BIRTH")
        state_breakdown[s] = state_breakdown.get(s, 0) + 1

    return {
        "total_active":      total,
        "tier_1":            tier_1,
        "tier_2":            tier_2,
        "avg_ods":           round(avg_ods, 1),
        "conjunction_exits": exits,
        "avg_return_pct":    round(avg_return, 2),
        "state_breakdown":   state_breakdown,
        "decay_breakdown":   decay_counts,
        "exit_candidates":   exits,
        "as_of":             datetime.now(timezone.utc).isoformat(),
    }


@campaign_router.get("/{campaign_id}")
async def get_campaign(campaign_id: str) -> dict[str, Any]:
    """Return full detail for a single campaign by display_label (UUID)."""
    results = _sb_get("campaigns", {
        "select":        "*",
        "display_label": f"eq.{campaign_id}",
        "limit":         "1",
    })
    if not results:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")

    c = results[0]

    # Fetch state history
    history = []
    if c.get("campaign_id"):
        history = _sb_get("campaign_state_history", {
            "select":      "transition_date,prior_state,new_state,transition_reason",
            "campaign_id": f"eq.{c['campaign_id']}",
            "order":       "created_at.asc",
        })

    c["state_history"] = history
    return c


@campaign_router.post("/{campaign_id}/close")
async def close_campaign_manually(campaign_id: str) -> dict[str, Any]:
    """
    Manually close a campaign from the UI.
    Updates status to CLOSED and sets close_reason to MANUAL.
    """
    try:
        key = _sb_key()
        hdrs = {
            **_headers(),
            "Prefer": "return=minimal",
        }
        r = _rq.patch(
            f"{_sb_url()}/rest/v1/campaigns",
            headers=hdrs,
            params={"display_label": f"eq.{campaign_id}"},
            json={
                "status":       "CLOSED",
                "close_reason": "MANUAL",
                "close_notes":  "Manually closed via UI",
                "closed_at":    datetime.now(timezone.utc).isoformat(),
                "updated_at":   datetime.now(timezone.utc).isoformat(),
            },
            timeout=15,
        )
        if r.status_code in (200, 204):
            return {"ok": True, "campaign_id": campaign_id, "status": "CLOSED"}
        raise HTTPException(status_code=500, detail=f"Supabase error: {r.status_code}")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Manual close error for %s: %s", campaign_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
