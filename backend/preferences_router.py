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
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger("preferences")

DATABASE_URL = os.getenv("DATABASE_URL", "")

preferences_router = APIRouter(prefix="/api/preferences", tags=["preferences"])

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


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    if not DATABASE_URL:
        raise HTTPException(503, "Database not configured")
    return psycopg2.connect(DATABASE_URL)


def _row_to_dict(row: dict) -> dict:
    """Convert psycopg2 RealDictRow to plain dict."""
    d = dict(row)
    # Ensure JSONB fields are proper Python objects
    for field in ("alert_types", "watchlist"):
        if isinstance(d.get(field), str):
            import json
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d


# ── Endpoints ──────────────────────────────────────────────────────────────────

@preferences_router.get("/{user_id}")
def get_preferences(user_id: str):
    """Get preferences for a user. Returns defaults if not found."""
    try:
        conn = _get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM user_preferences WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            # Return defaults
            return {
                "user_id":           user_id,
                "delivery_mode":     "realtime",
                "min_score":         60,
                "alert_types":       {"wyckoff": True, "gann": True, "ab_score": True,
                                      "elliott": False, "fibonacci": False},
                "watchlist":         [],
                "market_hours_only": True,
                "hurst_profile":     "MEDIUM",
                "weis_threshold":    0.5,
                "updated_at":        None,
            }

        return _row_to_dict(row)

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Get preferences error: {e}")
        raise HTTPException(500, str(e))


@preferences_router.post("/{user_id}")
def create_preferences(user_id: str, payload: PreferencesCreate):
    """Create preferences for a user."""
    import json
    try:
        conn = _get_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO user_preferences
            (user_id, email, delivery_mode, min_score, alert_types,
             watchlist, market_hours_only, hurst_profile, weis_threshold, updated_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
                email             = EXCLUDED.email,
                delivery_mode     = EXCLUDED.delivery_mode,
                min_score         = EXCLUDED.min_score,
                alert_types       = EXCLUDED.alert_types,
                watchlist         = EXCLUDED.watchlist,
                market_hours_only = EXCLUDED.market_hours_only,
                hurst_profile     = EXCLUDED.hurst_profile,
                weis_threshold    = EXCLUDED.weis_threshold,
                updated_at        = EXCLUDED.updated_at
        """, (
            user_id,
            payload.email,
            payload.delivery_mode,
            payload.min_score,
            json.dumps(payload.alert_types),
            json.dumps(payload.watchlist),
            payload.market_hours_only,
            payload.hurst_profile,
            payload.weis_threshold,
            datetime.now(timezone.utc),
        ))
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "user_id": user_id}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Create preferences error: {e}")
        raise HTTPException(500, str(e))


@preferences_router.patch("/{user_id}")
def update_preferences(user_id: str, payload: PreferencesUpdate):
    """Patch preferences — only updates provided fields."""
    import json

    updates = {}
    if payload.delivery_mode     is not None: updates["delivery_mode"]     = payload.delivery_mode
    if payload.min_score         is not None: updates["min_score"]         = payload.min_score
    if payload.alert_types is not None:
        at = payload.alert_types
        # Normalize list ["wyckoff","gann"] → {"wyckoff":true,"gann":true,...}
        if isinstance(at, list):
            all_types = ["wyckoff","gann","ab_score","elliott","fibonacci"]
            at = {k: (k in at) for k in all_types}
        updates["alert_types"] = json.dumps(at)
    if payload.watchlist         is not None: updates["watchlist"]         = json.dumps(payload.watchlist)
    if payload.market_hours_only is not None: updates["market_hours_only"] = payload.market_hours_only
    if payload.hurst_profile     is not None: updates["hurst_profile"]     = payload.hurst_profile
    if payload.weis_threshold    is not None: updates["weis_threshold"]    = payload.weis_threshold

    if not updates:
        raise HTTPException(400, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc)

    try:
        conn = _get_conn()
        cur  = conn.cursor()

        # Check if row exists
        cur.execute("SELECT 1 FROM user_preferences WHERE user_id = %s", (user_id,))
        exists = cur.fetchone()

        if not exists:
            # Create with defaults then apply updates
            cur.execute("""
                INSERT INTO user_preferences
                (user_id, delivery_mode, min_score, alert_types, watchlist,
                 market_hours_only, hurst_profile, weis_threshold, updated_at)
                VALUES (%s,'realtime',60,%s::jsonb,%s::jsonb,true,'MEDIUM',0.5,%s)
            """, (
                user_id,
                json.dumps({"wyckoff": True, "gann": True, "ab_score": True,
                            "elliott": False, "fibonacci": False}),
                json.dumps([]),
                datetime.now(timezone.utc),
            ))

        # Apply patch
        jsonb_fields = {"alert_types", "watchlist"}
        set_clause = ", ".join(
            f"{k} = %s::jsonb" if k in jsonb_fields else f"{k} = %s"
            for k in updates
        )
        values     = list(updates.values()) + [user_id]
        cur.execute(
            f"UPDATE user_preferences SET {set_clause} WHERE user_id = %s",
            values
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "user_id": user_id, "updated": list(updates.keys())}

    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Update preferences error: {e}")
        raise HTTPException(500, str(e))

