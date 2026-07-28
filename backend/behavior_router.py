# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/behavior_router.py
---------------------------
Behavioral Intelligence — trade planning, entry, exit, and scoring.

FIX (2026-07-28): the frontend's "Behavioral Intelligence" tab and its
supporting trade-plan/entry/exit workflow (frontend/app.py) call five
endpoints that never existed anywhere in the backend:
  POST /api/behavior/trade-plan
  POST /api/behavior/trade-entry
  POST /api/behavior/trade-exit
  POST /api/behavior/event
  GET  /api/behavior/dashboard/{user_id}
This is not a wiring bug like Journal/Preferences were -- there was no
router, no table, no scoring logic anywhere to wire in. This file is a
new, working implementation of that feature, using the Supabase client
pattern already proven reliable for Journal and Preferences tonight
(rather than the raw DATABASE_URL/psycopg2 pattern that caused hours of
trouble earlier).

Tables (see supabase/migrations/20260728_create_behavior_tables.sql):
  behavior_trade_plans   -- one row per "Plan Trade" click
  behavior_trades        -- one row per entry, updated on exit
  behavior_events        -- lightweight fire-and-forget telemetry log

SCORING MODEL (documented here since there's no prior spec to follow):
  Each completed trade gets a composite_score starting at 100, with a
  fixed penalty subtracted for each real-time behavioral deviation the
  trader flagged at exit (no_plan, stop_moved_wider, target_moved,
  premature_exit, added_size_adverse, timeframe_changed -- these come
  directly from the exit-flags checklist already in the frontend UI).
  behavior_flag is the single most severe deviation found, or
  "disciplined_execution" / "plan_followed" if none were flagged.
  Dashboard sub-scores (discipline/timing/risk/execution) are each the
  fraction of a user's trades free of the deviations relevant to that
  category, scaled to 0-100. This is a simple, explainable first version
  -- not a claim of psychological precision.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.supabase_isolation import get_user_id_from_request

log = logging.getLogger("behavior")

behavior_router = APIRouter(prefix="/api/behavior", tags=["behavior"])

# ── Supabase client helper (same pattern as preferences_router.py) ──────────────
import os

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


# ── Request models ───────────────────────────────────────────────────────────────

class TradePlanRequest(BaseModel):
    user_id: str
    symbol: str
    direction: str
    planned_entry: float
    planned_stop: Optional[float] = None
    planned_target: Optional[float] = None
    planned_size: float
    setup_reason: str = ""
    signal_score_at_plan: float = 0
    regime_at_plan: str = "neutral"


class TradeEntryRequest(BaseModel):
    user_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    size: float
    plan_id: Optional[str] = None
    market_regime_entry: str = "neutral"
    signal_score_entry: float = 0


class TradeExitRequest(BaseModel):
    trade_id: str
    exit_price: float
    market_regime_exit: str = "neutral"
    signal_score_exit: float = 0
    notes: str = ""
    no_plan: bool = False
    stop_moved_wider: bool = False
    target_moved: bool = False
    premature_exit: bool = False
    added_size_adverse: bool = False
    timeframe_changed: bool = False


class BehaviorEventRequest(BaseModel):
    user_id: str
    event_type: str
    symbol: Optional[str] = None
    price: Optional[float] = None
    timeframe: Optional[str] = None
    market_regime: Optional[str] = None
    decision_score: Optional[float] = None
    decision_status: Optional[str] = None
    metadata: Dict[str, Any] = {}


# ── Scoring ──────────────────────────────────────────────────────────────────────

_PENALTIES = {
    "no_plan": 20,
    "stop_moved_wider": 15,
    "target_moved": 10,
    "premature_exit": 15,
    "added_size_adverse": 20,
    "timeframe_changed": 10,
}

# Which flag "wins" as the single displayed behavior_flag, in priority order.
_FLAG_PRIORITY = [
    ("added_size_adverse", "over_sized"),
    ("premature_exit", "premature_exit"),
    ("no_plan", "plan_violated"),
    ("stop_moved_wider", "plan_violated"),
    ("target_moved", "plan_violated"),
    ("timeframe_changed", "late_chase"),
]


def _score_and_flag(payload: TradeExitRequest, pnl: float) -> tuple[float, str]:
    flags = {
        "no_plan": payload.no_plan,
        "stop_moved_wider": payload.stop_moved_wider,
        "target_moved": payload.target_moved,
        "premature_exit": payload.premature_exit,
        "added_size_adverse": payload.added_size_adverse,
        "timeframe_changed": payload.timeframe_changed,
    }
    score = 100.0
    for key, active in flags.items():
        if active:
            score -= _PENALTIES[key]
    score = max(0.0, min(100.0, score))

    for key, flag_name in _FLAG_PRIORITY:
        if flags[key]:
            return score, flag_name

    return score, ("disciplined_execution" if pnl >= 0 else "plan_followed")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@behavior_router.post("/trade-plan")
def create_trade_plan(payload: TradePlanRequest, authenticated_user_id: str = Depends(get_user_id_from_request)):
    # SECURITY FIX (2026-07-28): use the verified identity from the session,
    # not whatever user_id the client happened to put in the request body --
    # a client could otherwise write trade plans into any other user's account.
    plan_id = str(uuid.uuid4())
    row = {
        "plan_id": plan_id,
        "user_id": authenticated_user_id,
        "symbol": payload.symbol,
        "direction": payload.direction,
        "planned_entry": payload.planned_entry,
        "planned_stop": payload.planned_stop,
        "planned_target": payload.planned_target,
        "planned_size": payload.planned_size,
        "setup_reason": payload.setup_reason,
        "signal_score_at_plan": payload.signal_score_at_plan,
        "regime_at_plan": payload.regime_at_plan,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _supabase().table("behavior_trade_plans").insert(row).execute()
    except Exception as e:
        log.warning(f"create_trade_plan error: {e}")
        raise HTTPException(500, str(e))
    return {"ok": True, "plan_id": plan_id}


@behavior_router.post("/trade-entry")
def create_trade_entry(payload: TradeEntryRequest, authenticated_user_id: str = Depends(get_user_id_from_request)):
    trade_id = str(uuid.uuid4())
    row = {
        "trade_id": trade_id,
        "plan_id": payload.plan_id,
        "user_id": authenticated_user_id,
        "symbol": payload.symbol,
        "direction": payload.direction,
        "entry_price": payload.entry_price,
        "stop_price": payload.stop_price,
        "target_price": payload.target_price,
        "size": payload.size,
        "market_regime_entry": payload.market_regime_entry,
        "signal_score_entry": payload.signal_score_entry,
        "entered_at": datetime.now(timezone.utc).isoformat(),
        "exited_at": None,
    }
    try:
        _supabase().table("behavior_trades").insert(row).execute()
    except Exception as e:
        log.warning(f"create_trade_entry error: {e}")
        raise HTTPException(500, str(e))
    return {"ok": True, "trade_id": trade_id}


@behavior_router.post("/trade-exit")
def exit_trade(payload: TradeExitRequest, authenticated_user_id: str = Depends(get_user_id_from_request)):
    sb = _supabase()
    try:
        existing = (
            sb.table("behavior_trades")
            .select("*")
            .eq("trade_id", payload.trade_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        log.warning(f"exit_trade lookup error: {e}")
        raise HTTPException(500, str(e))

    rows = existing.data or []
    if not rows:
        raise HTTPException(404, "Trade not found")
    trade = rows[0]

    # SECURITY FIX (2026-07-28): confirm this trade actually belongs to the
    # authenticated caller before letting them modify it -- otherwise any
    # user who learned or guessed a trade_id could close out someone else's
    # open trade and write over their exit data.
    if trade.get("user_id") != authenticated_user_id:
        raise HTTPException(404, "Trade not found")

    entry_price = float(trade.get("entry_price") or 0)
    size = float(trade.get("size") or 0)
    direction = (trade.get("direction") or "long").lower()
    sign = 1 if direction == "long" else -1

    pnl = round((payload.exit_price - entry_price) * size * sign, 2)
    pnl_percent = round(
        ((payload.exit_price - entry_price) / entry_price * 100 * sign) if entry_price else 0, 2
    )

    composite, behavior_flag = _score_and_flag(payload, pnl)

    update_row = {
        "exit_price": payload.exit_price,
        "market_regime_exit": payload.market_regime_exit,
        "signal_score_exit": payload.signal_score_exit,
        "notes": payload.notes,
        "no_plan": payload.no_plan,
        "stop_moved_wider": payload.stop_moved_wider,
        "target_moved": payload.target_moved,
        "premature_exit": payload.premature_exit,
        "added_size_adverse": payload.added_size_adverse,
        "timeframe_changed": payload.timeframe_changed,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "behavior_flag": behavior_flag,
        "composite_score": composite,
        "exited_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sb.table("behavior_trades").update(update_row).eq("trade_id", payload.trade_id).execute()
    except Exception as e:
        log.warning(f"exit_trade update error: {e}")
        raise HTTPException(500, str(e))

    return {
        "ok": True,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "behavior_flag": behavior_flag,
        "scores": {"composite": composite},
    }


@behavior_router.post("/event")
def log_behavior_event(payload: BehaviorEventRequest, authenticated_user_id: str = Depends(get_user_id_from_request)):
    """Fire-and-forget telemetry. Failures here should never break the caller
    (the frontend already wraps this call in try/except), but we still try
    to persist it for real, rather than silently discarding it."""
    row = {
        "user_id": authenticated_user_id,
        "event_type": payload.event_type,
        "symbol": payload.symbol,
        "price": payload.price,
        "timeframe": payload.timeframe,
        "market_regime": payload.market_regime,
        "decision_score": payload.decision_score,
        "decision_status": payload.decision_status,
        "metadata": payload.metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _supabase().table("behavior_events").insert(row).execute()
    except Exception as e:
        log.warning(f"log_behavior_event error: {e}")
        return {"ok": False}
    return {"ok": True}


@behavior_router.get("/dashboard/{user_id}")
def get_behavior_dashboard(user_id: str, authenticated_user_id: str = Depends(get_user_id_from_request)):
    if user_id != authenticated_user_id:
        raise HTTPException(403, "Not authorized to view this user's dashboard")
    try:
        result = (
            _supabase()
            .table("behavior_trades")
            .select("*")
            .eq("user_id", user_id)
            .not_.is_("exited_at", "null")
            .order("exited_at", desc=True)
            .limit(200)
            .execute()
        )
    except Exception as e:
        log.warning(f"get_behavior_dashboard error: {e}")
        raise HTTPException(500, str(e))

    trades = result.data or []
    total = len(trades)
    if total == 0:
        return {}

    def _pct_clean(flag_keys: List[str]) -> float:
        clean = sum(1 for t in trades if not any(t.get(k) for k in flag_keys))
        return round(clean / total * 100, 1)

    avg_decision_score = round(
        sum(float(t.get("signal_score_entry") or 0) for t in trades) / total, 1
    )
    execution_score = _pct_clean(["stop_moved_wider", "target_moved", "added_size_adverse"])
    discipline_score = _pct_clean(["no_plan", "premature_exit"])
    timing_score = _pct_clean(["premature_exit", "timeframe_changed"])
    risk_score = _pct_clean(["added_size_adverse", "stop_moved_wider"])

    flag_counts = Counter(t.get("behavior_flag") or "unknown" for t in trades)
    common_behavior_flag = flag_counts.most_common(1)[0][0] if flag_counts else "neutral"

    by_regime: Dict[str, List[dict]] = defaultdict(list)
    for t in trades:
        by_regime[t.get("market_regime_entry") or "neutral"].append(t)

    regime_performance = []
    for regime, rows in by_regime.items():
        wins = sum(1 for r in rows if float(r.get("pnl") or 0) > 0)
        regime_performance.append({
            "regime": regime,
            "trades": len(rows),
            "win_rate": round(wins / len(rows) * 100, 1),
            "avg_pnl": round(sum(float(r.get("pnl") or 0) for r in rows) / len(rows), 2),
        })
    regime_performance.sort(key=lambda r: r["win_rate"], reverse=True)
    best_regime = regime_performance[0]["regime"] if regime_performance else None
    worst_regime = regime_performance[-1]["regime"] if regime_performance else None

    recent_scorecards = [
        {
            "symbol": t.get("symbol"),
            "exited_at": t.get("exited_at"),
            "pnl": t.get("pnl"),
            "pnl_percent": t.get("pnl_percent"),
            "behavior_flag": t.get("behavior_flag"),
            "composite_score": t.get("composite_score"),
        }
        for t in trades[:10]
    ]

    adaptive_warnings = []
    recent5 = trades[:5]
    if sum(1 for t in recent5 if t.get("behavior_flag") == "premature_exit") >= 2:
        adaptive_warnings.append("You've exited early on 2+ of your last 5 trades.")
    if sum(1 for t in recent5 if t.get("added_size_adverse")) >= 2:
        adaptive_warnings.append("You've sized up against your plan on 2+ of your last 5 trades.")

    return {
        "total_trades": total,
        "avg_decision_score": avg_decision_score,
        "execution_score": execution_score,
        "discipline_score": discipline_score,
        "timing_score": timing_score,
        "risk_score": risk_score,
        "common_behavior_flag": common_behavior_flag,
        "best_regime": best_regime,
        "worst_regime": worst_regime,
        "regime_performance": regime_performance,
        "recent_scorecards": recent_scorecards,
        "adaptive_warnings": adaptive_warnings,
    }
