"""
preferences_router.py — Sigmalytic Quant
FastAPI router for reading and updating user alert preferences.

Mount in main.py:
    from preferences_router import router as preferences_router
    app.include_router(preferences_router, prefix="/api/preferences", tags=["preferences"])
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr, Field
from supabase import create_client, Client

logger = logging.getLogger(__name__)

router = APIRouter()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PreferencesUpdate(BaseModel):
    delivery_mode:      Optional[str]       = Field(None, pattern="^(realtime|hourly|daily)$")
    min_score:          Optional[int]       = Field(None, ge=0, le=100)
    alert_types:        Optional[list[str]] = None
    watchlist:          Optional[list[str]] = None
    market_hours_only:  Optional[bool]      = None
    quiet_start_utc:    Optional[int]       = Field(None, ge=0, le=23)
    quiet_end_utc:      Optional[int]       = Field(None, ge=0, le=23)


class PreferencesCreate(PreferencesUpdate):
    user_id:    str
    email:      EmailStr


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_prefs(user_id: str) -> dict | None:
    result = _supabase.table("user_preferences").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{user_id}")
async def get_preferences(user_id: str):
    """Return the alert preferences for a user."""
    prefs = _get_prefs(user_id)
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return prefs


@router.post("/{user_id}")
async def create_preferences(user_id: str, body: PreferencesCreate):
    """Create preferences for a new user (called on signup)."""
    existing = _get_prefs(user_id)
    if existing:
        raise HTTPException(status_code=409, detail="Preferences already exist — use PATCH to update")

    payload = body.model_dump(exclude_none=True)
    payload["user_id"] = user_id

    result = _supabase.table("user_preferences").insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create preferences")

    return result.data[0]


@router.patch("/{user_id}")
async def update_preferences(user_id: str, body: PreferencesUpdate):
    """Partially update alert preferences for a user."""
    existing = _get_prefs(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Preferences not found — POST to create first")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # Uppercase all watchlist symbols
    if "watchlist" in updates:
        updates["watchlist"] = [s.upper() for s in updates["watchlist"]]

    result = (
        _supabase.table("user_preferences")
        .update(updates)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update preferences")

    return result.data[0]


@router.delete("/{user_id}")
async def reset_preferences(user_id: str):
    """Reset a user's preferences to defaults by deleting and letting them recreate."""
    _supabase.table("user_preferences").delete().eq("user_id", user_id).execute()
    return {"status": "deleted", "user_id": user_id}
