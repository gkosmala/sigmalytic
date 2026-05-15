"""
backend/billing_stub.py
-----------------------
Beta billing place-setting — zero Stripe, zero DB tables.
All state lives in BETA_USER_DB (in-memory dict).

Endpoints (register in main.py):
  GET  /api/v1/billing/{user_id}         — fetch billing state
  POST /api/v1/billing/{user_id}/upgrade — simulate upgrade, log intent

Tiers:
  free_trial    — limited access, upgrade prompt shown
  premium_beta  — full access, waived payment during beta
  past_due      — read-only, payment banner shown
"""

import logging
from datetime import datetime, timedelta
from typing import Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

log = logging.getLogger("billing_stub")

billing_router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

# ── Pydantic schemas ───────────────────────────────────────────────────────────

class BillingResponse(BaseModel):
    user_id:            str
    tier:               str       # free_trial | premium_beta | past_due
    plan_name:          str
    current_period_end: str
    amount_due:         float
    is_beta_account:    bool = True

class UpgradeRequest(BaseModel):
    requested_tier: str           # e.g. "premium_beta"

# ── In-memory beta user DB ─────────────────────────────────────────────────────
# Shared with access_control.py — update both if you add users here.

BETA_USER_DB: Dict[str, dict] = {
    "demo_user_001": {
        "tier":               "premium_beta",
        "plan_name":          "Beta Premium Tier",
        "current_period_end": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "amount_due":         0.00,
    },
    "user_123": {
        "tier":               "free_trial",
        "plan_name":          "Beta Free Tier",
        "current_period_end": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
        "amount_due":         0.00,
    },
    "user_456": {
        "tier":               "past_due",
        "plan_name":          "Beta Premium Tier",
        "current_period_end": datetime.now().strftime("%Y-%m-%d"),
        "amount_due":         29.99,
    },
}

# ── Endpoints ──────────────────────────────────────────────────────────────────

@billing_router.get("/{user_id}", response_model=BillingResponse)
async def get_billing(user_id: str):
    """Returns the billing state for a user."""
    user = BETA_USER_DB.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    return BillingResponse(user_id=user_id, **user)


@billing_router.post("/{user_id}/upgrade")
async def upgrade_billing(user_id: str, payload: UpgradeRequest):
    """
    Simulates an upgrade/payment flow.
    Logs intent to terminal, mutates in-memory state instantly.
    """
    user = BETA_USER_DB.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")

    # ── Analytics: log upgrade intent ─────────────────────────────────────────
    log.info(
        f"[BETA ANALYTICS] Intent Captured — "
        f"Timestamp: {datetime.utcnow().isoformat()} | "
        f"User: {user_id} requested upgrade to '{payload.requested_tier}' "
        f"from '{user['tier']}'"
    )

    # ── Mutate in-memory state ─────────────────────────────────────────────────
    BETA_USER_DB[user_id]["tier"]               = payload.requested_tier
    BETA_USER_DB[user_id]["plan_name"]          = "Beta Premium Tier (Active)"
    BETA_USER_DB[user_id]["current_period_end"] = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    BETA_USER_DB[user_id]["amount_due"]         = 0.00   # waived for beta

    return {
        "status":     "success",
        "message":    f"Simulated upgrade to {payload.requested_tier}.",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
