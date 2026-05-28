# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/access_control.py
--------------------------
Role-based feature locking for Sigmalytic (beta stub phase).

HOW IT WORKS
────────────
Each user has a tier stored in the in-memory BETA_USER_DB (from billing_stub.py).
This module defines:

  1. FEATURE_MAP   — which tiers can access which features.
  2. check_access  — FastAPI dependency that gates any endpoint by feature name.
  3. get_user_permissions — returns the full permission set for a user (used by
                            the Dash frontend to show/hide UI elements).

TIERS (beta phase)
──────────────────
  free_trial    — limited access, upgrade prompts visible
  premium_beta  — full access, no upgrade prompts
  past_due      — read-only access, payment banner shown

ADDING A NEW FEATURE
────────────────────
  1. Add its key to FEATURE_MAP with the list of allowed tiers.
  2. Decorate your FastAPI endpoint with:
         Depends(check_access("your_feature_key"))
  3. In Dash, call GET /api/v1/permissions/{user_id} on page load and
     use the returned dict to conditionally render components.
"""

from fastapi import HTTPException, status
from typing import Dict, List

# ── Tier hierarchy (order matters for display; not used for logic) ─────────────

TIERS = ["free_trial", "past_due", "premium_beta"]

# ── Feature → allowed tiers map ───────────────────────────────────────────────
# Add every gated feature here. A feature NOT listed = open to all tiers.

FEATURE_MAP: Dict[str, List[str]] = {
    # Command Center
    "command_center_view":          ["free_trial", "premium_beta", "past_due"],
    "live_feed_view":               ["free_trial", "premium_beta", "past_due"],

    # Behavioral Intelligence — CSV upload gated to premium
    "behavioral_intel_view":        ["free_trial", "premium_beta", "past_due"],
    "behavioral_intel_csv_upload":  ["premium_beta"],          # upgrade prompt for free_trial
    "behavioral_intel_history":     ["premium_beta"],          # per-user history (roadmap item)

    # Performance tab — basic metrics free, deep analytics premium
    "performance_basic":            ["free_trial", "premium_beta", "past_due"],
    "performance_advanced":         ["premium_beta"],

    # Radar Screen (not yet built — stubbed here for future gating)
    "radar_screen":                 ["premium_beta"],

    # Options Window (not yet built)
    "options_window":               ["premium_beta"],

    # Alpaca Paper Trading (not yet built)
    "paper_trading":                ["premium_beta"],

    # Billing page — all tiers can see it (it adapts based on tier)
    "billing_view":                 ["free_trial", "premium_beta", "past_due"],

    # Admin / reset — internal only; not exposed via user-facing endpoints
    "admin_reset_history":          ["premium_beta"],          # tighten this in production
}

# ── In-memory user store (shared with billing_stub.py) ────────────────────────
# Import from billing_stub in your actual integration:
#   from backend.billing_stub import BETA_USER_DB
# Duplicated here so this module is self-contained during development.

BETA_USER_DB: Dict[str, dict] = {
    "demo_user_001": {"tier": "premium_beta"},
    "user_123":      {"tier": "free_trial"},
    "user_456":      {"tier": "past_due"},
}


# ── Core access check ──────────────────────────────────────────────────────────

def check_access(feature: str):
    """
    FastAPI dependency factory.

    Usage on any endpoint:
        @app.get("/api/v1/behavioral/upload")
        async def upload_csv(
            user_id: str,
            _: None = Depends(check_access("behavioral_intel_csv_upload"))
        ):
            ...

    NOTE: In production, user_id will come from your JWT / Supabase auth token,
    not a query param. Swap the lookup logic then — the rest stays identical.
    """
    def dependency(user_id: str):
        tier = _resolve_tier(user_id)
        allowed = FEATURE_MAP.get(feature, TIERS)   # unlisted feature = open
        if tier not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error":   "access_denied",
                    "feature": feature,
                    "tier":    tier,
                    "upgrade_required": tier == "free_trial",
                    "payment_required": tier == "past_due",
                }
            )
    return dependency


def get_permissions(user_id: str) -> Dict[str, bool]:
    """
    Returns a flat dict of feature → bool for a given user.
    The Dash frontend calls this once on login / page load and uses the
    result to show, hide, or disable UI components without making per-feature
    round-trips.

    Example response:
        {
          "command_center_view": true,
          "behavioral_intel_csv_upload": false,
          "radar_screen": false,
          ...
        }
    """
    tier = _resolve_tier(user_id)
    return {
        feature: (tier in allowed_tiers)
        for feature, allowed_tiers in FEATURE_MAP.items()
    }


def _resolve_tier(user_id: str) -> str:
    """Look up a user's tier. Raises 404 if user not found."""
    user = BETA_USER_DB.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found."
        )
    return user["tier"]


# ── FastAPI endpoint to wire into main.py ──────────────────────────────────────
# Copy these two routes into your FastAPI app (backend/main.py):
#
#   from backend.access_control import get_permissions, check_access
#
#   @app.get("/api/v1/permissions/{user_id}")
#   async def user_permissions(user_id: str):
#       """Called by Dash on login. Returns full feature permission map."""
#       return get_permissions(user_id)
#
#   # Example: gate the CSV upload endpoint
#   @app.post("/api/v1/behavioral/upload/{user_id}")
#   async def upload_csv(
#       user_id: str,
#       _: None = Depends(check_access("behavioral_intel_csv_upload"))
#   ):
#       ...your existing upload logic...


# ── Dash-side integration pattern ─────────────────────────────────────────────
# In frontend/app.py, after a successful login:
#
#   import requests, os
#   BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
#
#   @app.callback(
#       Output("permissions-store", "data"),
#       Input("session-store", "data")
#   )
#   def load_permissions(session):
#       if not session or not session.get("user_id"):
#           return {}
#       r = requests.get(f"{BACKEND_URL}/api/v1/permissions/{session['user_id']}")
#       return r.json() if r.status_code == 200 else {}
#
#   # Then gate any component using the store:
#   @app.callback(
#       Output("csv-upload-section", "style"),
#       Input("permissions-store", "data")
#   )
#   def toggle_csv_upload(perms):
#       if perms and perms.get("behavioral_intel_csv_upload"):
#           return {"display": "block"}
#       return {"display": "none"}   # or render an upgrade prompt instead
