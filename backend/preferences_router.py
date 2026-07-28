# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/preferences_router.py
------------------------------
Sigmalytic — User Preferences API
Handles GET / POST / PATCH for alert preferences stored in Supabase.

Table: user_preferences
  user_id          TEXT PRIMARY KEY
  email            TEXT
  delivery_mode    TEXT    -- realtime | hourly | daily
  min_score        INTEGER -- 0-100
  alert_types      JSONB   -- {"wyckoff": true, "gann": true, ...}
  watchlist        JSONB   -- ["AAPL", "NVDA", ...]
  market_hours_only BOOLEAN
  hurst_profile    TEXT    -- SHORT | MEDIUM | LONG
  weis_threshold   NUMERIC -- 0.1 - 3.0
  updated_at       TIMESTAMPTZ

FIX (2026-07-28): this used to connect via raw psycopg2 + DATABASE_URL --
the exact same credential path that took hours to resolve for the trade
journal tonight (pooler vs direct connection, IPv4 vs IPv6, password
mismatches). Converted to the Supabase client (SUPABASE_URL +
SUPABASE_SERVICE_ROLE_KEY) instead, matching the method already proven
reliable everywhere else in this app.

ALSO FIX: this router was defined but never actually included in the
FastAPI app at all (confirmed via a full audit of every router in the
backend) -- every request to /api/preferences/{user_id} has been hitting
a 404 the whole time, despite the frontend actively calling it in three
separate places. Compatibility routes matching this router's real logic
are added directly in backend/main.py, the same pattern already used for
journal/divergence.
"""

from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.supabase_isolation import get_user_id_from_request

log = logging.getLogger("preferences")

preferences_router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def _require_self(user_id: str, authenticated_user_id: str) -> None:
    """
    SECURITY FIX (2026-07-28): these endpoints used to take user_id
    straight from the URL with no check at all that the caller actually
    *is* that user -- anyone could read or overwrite anyone else's alert
    preferences and watchlist just by knowing their user_id. Now every
    endpoint requires a verified session (see supabase_isolation.py) and
    confirms the path's user_id matches the authenticated identity before
    doing anything.
    """
    if user_id != authenticated_user_id:
        raise HTTPException(403, "Not authorized to access this user's preferences")

# ── Pydantic models ────────────────────────────────────────────────────────────

class PreferencesCreate(BaseModel):
    user_id:           str
    email:             str = ""
    delivery_mode:     str = "realtime"
    min_score:         int = 60
    alert_types:       Dict[str, bool] = {
        "wyckoff": True, "gann": True, "ab_score": True,
        "elliott": False, "fibonacci": False
    }
    watchlist:         List[str] = []
    market_hours_only: bool = True
    hurst_profile:     str = "MEDIUM"
    weis_threshold:    float = 0.5


class PreferencesUpdate(BaseModel):
    delivery_mode:     Optional[str]            = None
    min_score:         Optional[int]            = None
    alert_types:       Optional[Any]            = None  # accepts dict or list
    watchlist:         Optional[List[str]]      = None
    market_hours_only: Optional[bool]           = None
    hurst_profile:     Optional[str]            = None
    weis_threshold:    Optional[float]          = None


_DEFAULT_PREFERENCES = {
    "delivery_mode":     "realtime",
    "min_score":         60,
    "alert_types":       {"wyckoff": True, "gann": True, "ab_score": True,
                          "elliott": False, "fibonacci": False},
    "watchlist":         [],
    "market_hours_only": True,
    "hurst_profile":     "MEDIUM",
    "weis_threshold":    0.5,
}


# ── Supabase client helper ──────────────────────────────────────────────────────

_supabase_client = None


def _supabase():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    if not supabase_url or not supabase_key:
        raise HTTPException(503, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    from supabase import create_client
    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


# ── Endpoints ──────────────────────────────────────────────────────────────────

@preferences_router.get("/{user_id}")
def get_preferences(user_id: str, authenticated_user_id: str = Depends(get_user_id_from_request)):
    """Get preferences for a user. Returns defaults if not found."""
    _require_self(user_id, authenticated_user_id)
    try:
        response = (
            _supabase()
            .table("user_preferences")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []

        if not rows:
            return {"user_id": user_id, "updated_at": None, **_DEFAULT_PREFERENCES}

        return rows[0]

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Get preferences error: {e}")
        raise HTTPException(500, str(e))


@preferences_router.post("/{user_id}")
def create_preferences(user_id: str, payload: PreferencesCreate, authenticated_user_id: str = Depends(get_user_id_from_request)):
    """Create (or fully replace) preferences for a user."""
    _require_self(user_id, authenticated_user_id)
    try:
        row = {
            "user_id":           user_id,
            "email":             payload.email,
            "delivery_mode":     payload.delivery_mode,
            "min_score":         payload.min_score,
            "alert_types":       payload.alert_types,
            "watchlist":         payload.watchlist,
            "market_hours_only": payload.market_hours_only,
            "hurst_profile":     payload.hurst_profile,
            "weis_threshold":    payload.weis_threshold,
            "updated_at":        datetime.now(timezone.utc).isoformat(),
        }
        _supabase().table("user_preferences").upsert(row, on_conflict="user_id").execute()
        return {"ok": True, "user_id": user_id}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Create preferences error: {e}")
        raise HTTPException(500, str(e))


@preferences_router.patch("/{user_id}")
def update_preferences(user_id: str, payload: PreferencesUpdate, authenticated_user_id: str = Depends(get_user_id_from_request)):
    """Patch preferences -- only updates provided fields."""
    _require_self(user_id, authenticated_user_id)
    updates: Dict[str, Any] = {}

    if payload.delivery_mode     is not None: updates["delivery_mode"]     = payload.delivery_mode
    if payload.min_score         is not None: updates["min_score"]         = payload.min_score
    if payload.alert_types is not None:
        at = payload.alert_types
        # Normalize list ["wyckoff","gann"] -> {"wyckoff":true,"gann":true,...}
        if isinstance(at, list):
            all_types = ["wyckoff", "gann", "ab_score", "elliott", "fibonacci"]
            at = {k: (k in at) for k in all_types}
        updates["alert_types"] = at
    if payload.watchlist         is not None: updates["watchlist"]         = payload.watchlist
    if payload.market_hours_only is not None: updates["market_hours_only"] = payload.market_hours_only
    if payload.hurst_profile     is not None: updates["hurst_profile"]     = payload.hurst_profile
    if payload.weis_threshold    is not None: updates["weis_threshold"]    = payload.weis_threshold

    if not updates:
        raise HTTPException(400, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        client = _supabase()

        existing = (
            client.table("user_preferences")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        if not existing.data:
            # Create with defaults, then apply the patch on top
            base_row = {"user_id": user_id, **_DEFAULT_PREFERENCES}
            base_row.update(updates)
            client.table("user_preferences").upsert(base_row, on_conflict="user_id").execute()
        else:
            client.table("user_preferences").update(updates).eq("user_id", user_id).execute()

        return {"ok": True, "user_id": user_id, "updated": list(updates.keys())}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Update preferences error: {e}")
        raise HTTPException(500, str(e))
