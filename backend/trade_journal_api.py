# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/trade_journal_api.py
-----------------------------
FastAPI router for the Trade Journal.

Mount in main.py:
    from trade_journal_api import journal_router
    app.include_router(journal_router)

Endpoints:
    POST /api/journal/entry          — log a new trade entry
    POST /api/journal/exit/{id}      — log a trade exit
    GET  /api/journal/trades         — get all trades for a user
    GET  /api/journal/profile        — get trader behavioral profile
    GET  /api/journal/open           — get open trades only

NOTE (2026-08-07): confirmed journal_router is genuinely never
mounted in main.py -- only a comment references it (see main.py's
"FIX (2026-07-28)" note), which added GET-only compatibility routes
for /trades and /profile, but never added an equivalent for the real
POST /entry and /exit/{id} endpoints here.

Confirmed this is NOT the same system the live "Log Trade Entry" /
"Exit Trade" UI buttons actually call -- those call behavior_router.py's
POST /api/behavior/trade-entry and /trade-exit, which IS genuinely
mounted and working. This file is a separate, parallel, more
sophisticated system: log_trade_entry()/log_trade_exit() in
trade_journal_service.py compute real signal-relative grading
(entry FOMO score based on how late the entry was relative to when
the original signal fired, sizing-quality grade against recommended
tier sizing) that behavior_router.py's simpler flow does not.

Not wired up here deliberately -- this uses raw psycopg2/DATABASE_URL
access directly (the same pattern flagged elsewhere in this codebase
as having caused real, historical production trouble), and mounting
it would create two parallel "log a trade" systems rather than one.
A genuine, valuable feature worth a deliberate integration decision
later (e.g. merging its grading logic into the already-working
behavior_router.py flow), not something to wire up casually.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.trade_journal_service import (
    log_trade_entry,
    log_trade_exit,
    get_journal_entries,
    get_trader_profile,
)
from backend.supabase_isolation import get_user_id_from_request

log = logging.getLogger("trade_journal_api")

journal_router = APIRouter(prefix="/api/journal", tags=["journal"])


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
