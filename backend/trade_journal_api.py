# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/trade_journal_api.py
-----------------------------
FastAPI router for the Trade Journal.

Mounted in main.py via app.include_router(journal_router).

Endpoints:
    POST   /api/journal/entry          — log a new trade entry
    POST   /api/journal/exit/{id}      — log a trade exit
    DELETE /api/journal/entry/{id}     — admin-only: clear a mistaken entry
    GET    /api/journal/trades         — get all trades for a user
    GET    /api/journal/profile        — get trader behavioral profile
    GET    /api/journal/open           — get open trades only

UPDATE (2026-08-07): this router is now genuinely, actively mounted
in main.py (confirmed) -- an earlier note here claiming it was never
mounted is now stale/incorrect and has been removed. log_trade_entry()/
log_trade_exit() have also since been migrated off the previously-
broken raw psycopg2/DATABASE_URL access to the same Supabase client
used elsewhere in this codebase.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Depends, Header
from pydantic import BaseModel

from backend.trade_journal_service import (
    log_trade_entry,
    log_trade_exit,
    delete_trade_entry,
    get_journal_entries,
    get_trader_profile,
)
from backend.supabase_isolation import get_user_id_from_request

log = logging.getLogger("trade_journal_api")

journal_router = APIRouter(prefix="/api/journal", tags=["journal"])


def _require_admin_lazy(authorization: str = Header(default="")):
    """
    Lazy import of require_admin from backend.main -- avoids a
    circular import (main.py mounts this router, so importing
    require_admin at this file's top level would import main.py
    before it has finished loading). Mirrors require_admin's own
    Header(...) signature so FastAPI's dependency injection actually
    pulls the real Authorization header at request time.
    """
    from backend.main import require_admin as _real_require_admin
    return _real_require_admin(authorization)


# ── Pydantic models ───────────────────────────────────────────────────────────

class TradeEntryRequest(BaseModel):
    symbol:          str
    entry_date:      str          # ISO date string
    entry_price:     float
    shares:          int
    direction:       str   = "LONG"
    signal_id:       Optional[str] = None
    campaign_id:     Optional[str] = None
    tier:            Optional[str] = None
    notes:           Optional[str] = None
    portfolio_value: float = 0.0


class TradeExitRequest(BaseModel):
    exit_date:   str
    exit_price:  float
    exit_reason: str           = "MANUAL"
    notes:       Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@journal_router.post("/entry")
async def create_trade_entry(
    payload: TradeEntryRequest,
    request: Request,
) -> dict:
    """Log a new trade entry."""
    user_id = get_user_id_from_request(request)

    try:
        entry_date = date.fromisoformat(payload.entry_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid entry_date format. Use YYYY-MM-DD.")

    journal_id = log_trade_entry(
        user_id         = user_id,
        symbol          = payload.symbol.upper().strip(),
        entry_date      = entry_date,
        entry_price     = Decimal(str(payload.entry_price)),
        shares          = payload.shares,
        direction       = payload.direction.upper(),
        signal_id       = payload.signal_id,
        campaign_id     = payload.campaign_id,
        tier            = payload.tier,
        notes           = payload.notes,
        portfolio_value = payload.portfolio_value,
    )

    if not journal_id:
        raise HTTPException(status_code=500, detail="Failed to log trade entry.")

    return {"ok": True, "journal_id": journal_id, "user_id": user_id}


@journal_router.post("/exit/{journal_id}")
async def create_trade_exit(
    journal_id: str,
    payload:    TradeExitRequest,
    request:    Request,
) -> dict:
    """Log the exit for an open trade."""
    try:
        exit_date = date.fromisoformat(payload.exit_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid exit_date format. Use YYYY-MM-DD.")

    success = log_trade_exit(
        journal_id  = journal_id,
        exit_date   = exit_date,
        exit_price  = Decimal(str(payload.exit_price)),
        exit_reason = payload.exit_reason,
        notes       = payload.notes,
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Journal entry {journal_id} not found.")

    return {"ok": True, "journal_id": journal_id}


@journal_router.delete("/entry/{journal_id}")
async def delete_journal_entry(
    journal_id: str,
    _admin: str = Depends(_require_admin_lazy),
) -> dict:
    """
    Clear a subscriber's mistaken journal entry. Admin-only -- meant
    for support use when a subscriber reports a mistake in their
    journal (wrong symbol, price, shares, etc.) and needs it cleared
    so they can re-log a corrected entry.
    """
    deleted = delete_trade_entry(journal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Journal entry {journal_id} not found.")
    return {"ok": True, "deleted": deleted}


@journal_router.get("/trades")
async def get_trades(request: Request, status: Optional[str] = None, limit: int = 100) -> dict:
    """Get all journal entries for the current user."""
    user_id = get_user_id_from_request(request)
    trades  = get_journal_entries(user_id, status=status, limit=limit)
    return {"trades": trades, "count": len(trades), "user_id": user_id}


@journal_router.get("/open")
async def get_open_trades(request: Request) -> dict:
    """Get open trades only."""
    user_id = get_user_id_from_request(request)
    trades  = get_journal_entries(user_id, status="OPEN")
    return {"trades": trades, "count": len(trades)}


@journal_router.get("/profile")
async def get_profile(request: Request) -> dict:
    """Get the trader behavioral profile."""
    user_id = get_user_id_from_request(request)
    profile = get_trader_profile(user_id)
    return profile
