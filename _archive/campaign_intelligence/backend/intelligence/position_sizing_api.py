# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/position_sizing_api.py
--------------------------------------------
FastAPI router for position sizing.

Mount in main.py:
    from intelligence.position_sizing_api import sizing_router
    app.include_router(sizing_router)

Endpoints:
    POST /api/sizing/compute     — size a single signal
    POST /api/sizing/batch       — size a batch of signals
    GET  /api/sizing/portfolio   — current portfolio state
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import requests as _rq
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from intelligence.position_sizing_engine import (
    PortfolioContext,
    compute_position_size,
    size_campaign_batch,
    sizing_result_to_dict,
)

log = logging.getLogger("position_sizing_api")

sizing_router = APIRouter(prefix="/api/sizing", tags=["sizing"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class SizingRequest(BaseModel):
    symbol:      str
    tier:        str               # TIER_1 or TIER_2
    entry_price: float
    asym_ratio:  float = 1.0
    entry_date:  Optional[str] = None   # ISO date string, defaults to today


class PortfolioInput(BaseModel):
    total_value:       float
    available_capital: float
    active_positions:  int   = 0
    deployed_capital:  float = 0.0


class BatchSizingRequest(BaseModel):
    signals:   list[SizingRequest]
    portfolio: PortfolioInput


# ── Supabase helpers ──────────────────────────────────────────────────────────

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@sizing_router.post("/compute")
async def compute_sizing(
    request:   SizingRequest,
    portfolio: PortfolioInput,
) -> dict[str, Any]:
    """
    Compute position size for a single signal.
    Returns full SizingResult including ASYM filter decision.
    """
    try:
        entry_date = (
            date.fromisoformat(request.entry_date)
            if request.entry_date else date.today()
        )

        port = PortfolioContext(
            total_value       = Decimal(str(portfolio.total_value)),
            available_capital = Decimal(str(portfolio.available_capital)),
            active_positions  = portfolio.active_positions,
            deployed_capital  = Decimal(str(portfolio.deployed_capital)),
        )

        result = compute_position_size(
            symbol      = request.symbol,
            tier        = request.tier,
            entry_price = Decimal(str(request.entry_price)),
            asym_ratio  = Decimal(str(request.asym_ratio)),
            portfolio   = port,
            entry_date  = entry_date,
        )

        return sizing_result_to_dict(result)

    except Exception as exc:
        log.error("Sizing compute error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@sizing_router.post("/batch")
async def batch_sizing(request: BatchSizingRequest) -> dict[str, Any]:
    """
    Size a batch of signals in priority order.
    TIER_1 signals consume capital first, then TIER_2.
    """
    try:
        port = PortfolioContext(
            total_value       = Decimal(str(request.portfolio.total_value)),
            available_capital = Decimal(str(request.portfolio.available_capital)),
            active_positions  = request.portfolio.active_positions,
            deployed_capital  = Decimal(str(request.portfolio.deployed_capital)),
        )

        signals = [
            {
                "symbol":      s.symbol,
                "tier":        s.tier,
                "entry_price": s.entry_price,
                "asym_ratio":  s.asym_ratio,
            }
            for s in request.signals
        ]

        results = size_campaign_batch(signals, port)

        approved = [r for r in results if r.is_approved]
        blocked  = [r for r in results if not r.is_approved]

        return {
            "total":    len(results),
            "approved": len(approved),
            "blocked":  len(blocked),
            "results":  [sizing_result_to_dict(r) for r in results],
        }

    except Exception as exc:
        log.error("Batch sizing error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@sizing_router.get("/portfolio")
async def get_portfolio_state() -> dict[str, Any]:
    """
    Return current portfolio state from active campaigns in Supabase.
    Used to pre-populate the portfolio context for sizing requests.
    """
    try:
        r = _rq.get(
            f"{_sb_url()}/rest/v1/campaigns",
            headers=_headers(),
            params={
                "select": "entry_price,current_price,campaign_age_days",
                "status": "eq.ACTIVE",
                "limit":  "500",
            },
            timeout=15,
        )

        campaigns = r.json() if r.status_code == 200 else []
        active_count = len(campaigns)

        deployed = sum(
            float(c.get("current_price") or c.get("entry_price") or 0)
            for c in campaigns
        )

        return {
            "active_positions": active_count,
            "deployed_capital": round(deployed, 2),
            "note": (
                "Provide total_value and available_capital from your "
                "broker account to complete the portfolio context."
            ),
        }

    except Exception as exc:
        log.error("Portfolio state error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

