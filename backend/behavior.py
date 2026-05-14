"""
SigmAlytic — Behavioral Intelligence API
Postgres (Supabase) version — replaces SQLite.
Attach to existing FastAPI app via: app.include_router(behavior_router)
"""

from __future__ import annotations
import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import psycopg2
import psycopg2.extras

DATABASE_URL = os.getenv("DATABASE_URL", "")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn

def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id    TEXT PRIMARY KEY,
        name       TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS behavioral_events (
        event_id        TEXT PRIMARY KEY,
        user_id         TEXT,
        event_type      TEXT NOT NULL,
        symbol          TEXT NOT NULL,
        price           REAL,
        timeframe       TEXT,
        market_regime   TEXT,
        decision_score  REAL,
        decision_status TEXT,
        timestamp       TIMESTAMP DEFAULT NOW(),
        metadata        TEXT
    );

    CREATE TABLE IF NOT EXISTS market_snapshots (
        snapshot_id      TEXT PRIMARY KEY,
        symbol           TEXT NOT NULL,
        price            REAL,
        volume           REAL,
        timeframe        TEXT,
        decision_score   REAL,
        decision_status  TEXT,
        decision_bias    TEXT,
        confidence       TEXT,
        regime           TEXT,
        confluence_nodes TEXT,
        timestamp        TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS trade_plans (
        plan_id              TEXT PRIMARY KEY,
        user_id              TEXT,
        symbol               TEXT NOT NULL,
        direction            TEXT,
        planned_entry        REAL,
        planned_stop         REAL,
        planned_target       REAL,
        planned_size         REAL,
        setup_reason         TEXT,
        signal_score_at_plan REAL,
        regime_at_plan       TEXT,
        created_at           TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS trades (
        trade_id              TEXT PRIMARY KEY,
        user_id               TEXT,
        plan_id               TEXT,
        symbol                TEXT NOT NULL,
        direction             TEXT,
        entry_price           REAL,
        exit_price            REAL,
        stop_price            REAL,
        target_price          REAL,
        size                  REAL,
        entry_time            TIMESTAMP,
        exit_time             TIMESTAMP,
        pnl                   REAL,
        pnl_percent           REAL,
        market_regime_entry   TEXT,
        market_regime_exit    TEXT,
        signal_score_entry    REAL,
        signal_score_exit     REAL,
        status                TEXT DEFAULT 'open'
    );

    CREATE TABLE IF NOT EXISTS decision_scorecards (
        scorecard_id                 TEXT PRIMARY KEY,
        user_id                      TEXT,
        trade_id                     TEXT,
        symbol                       TEXT NOT NULL,
        setup_quality_score          REAL,
        execution_quality_score      REAL,
        discipline_score             REAL,
        timing_score                 REAL,
        risk_management_score        REAL,
        confidence_calibration_score REAL,
        composite_decision_score     REAL,
        primary_behavior_flag        TEXT,
        notes                        TEXT,
        timestamp                    TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS regime_memory (
        id                   TEXT PRIMARY KEY,
        user_id              TEXT,
        regime               TEXT,
        symbol               TEXT,
        total_trades         INTEGER DEFAULT 0,
        win_rate             REAL DEFAULT 0,
        avg_decision_score   REAL DEFAULT 0,
        avg_pnl_percent      REAL DEFAULT 0,
        common_behavior_flag TEXT,
        updated_at           TIMESTAMP DEFAULT NOW()
    );

    INSERT INTO users (user_id, name)
    VALUES ('demo_user_001', 'Demo Trader')
    ON CONFLICT (user_id) DO NOTHING;
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ── Types ─────────────────────────────────────────────────────────────────────

MarketRegime = Literal[
    "expansion", "compression", "reversal", "trend_continuation",
    "panic", "euphoria", "absorption", "exhaustion", "neutral"
]

BehaviorFlag = Literal[
    "disciplined_execution", "late_chase", "premature_exit", "panic_exit",
    "over_sized", "under_sized", "ignored_high_quality_signal",
    "revenge_trade", "plan_followed", "plan_violated", "neutral"
]

# ── Pydantic models ───────────────────────────────────────────────────────────

class BehavioralEventIn(BaseModel):
    user_id:         str = "demo_user_001"
    event_type:      str
    symbol:          str
    price:           Optional[float] = None
    timeframe:       Optional[str]   = None
    market_regime:   Optional[str]   = None
    decision_score:  Optional[float] = None
    decision_status: Optional[str]   = None
    metadata:        Optional[dict]  = None

class MarketSnapshotIn(BaseModel):
    symbol:           str
    price:            float
    volume:           float
    timeframe:        str
    decision_score:   float
    decision_status:  str
    decision_bias:    str
    confidence:       str
    regime:           str
    confluence_nodes: list = []

class TradePlanIn(BaseModel):
    user_id:              str   = "demo_user_001"
    symbol:               str
    direction:            Literal["long", "short", "neutral"]
    planned_entry:        float
    planned_stop:         float
    planned_target:       float
    planned_size:         float
    setup_reason:         str   = ""
    signal_score_at_plan: float = 0
    regime_at_plan:       str   = "neutral"

class TradeEntryIn(BaseModel):
    user_id:             str   = "demo_user_001"
    plan_id:             Optional[str] = None
    symbol:              str
    direction:           Literal["long", "short"]
    entry_price:         float
    stop_price:          Optional[float] = None
    target_price:        Optional[float] = None
    size:                float
    market_regime_entry: str   = "neutral"
    signal_score_entry:  float = 0

class TradeExitIn(BaseModel):
    trade_id:            str
    exit_price:          float
    market_regime_exit:  str  = "neutral"
    signal_score_exit:   float = 0
    notes:               str  = ""
    no_plan:             bool = False
    stop_moved_wider:    bool = False
    target_moved:        bool = False
    premature_exit:      bool = False
    added_size_adverse:  bool = False
    timeframe_changed:   bool = False

# ── Scoring engine ────────────────────────────────────────────────────────────

def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def calculate_setup_quality(decision_score: float, confidence: str, regime: str) -> float:
    score = decision_score
    if confidence == "HIGH":  score += 5
    if regime == "expansion": score += 5
    if regime == "neutral":   score -= 5
    if regime == "panic":     score -= 10
    return clamp(score)

def calculate_timing_score(signal_price: float, entry_price: float, direction: str) -> float:
    if direction == "long":
        move_pct = ((entry_price - signal_price) / signal_price) * 100
    else:
        move_pct = ((signal_price - entry_price) / signal_price) * 100
    if move_pct <= 0.25: return 100
    if move_pct <= 0.50: return 85
    if move_pct <= 0.75: return 70
    if move_pct <= 1.00: return 55
    return 35

def calculate_discipline_score(
    no_plan=False, stop_moved_wider=False, target_moved=False,
    premature_exit=False, added_size_adverse=False, timeframe_changed=False
) -> float:
    score = 100.0
    if no_plan:            score -= 20
    if stop_moved_wider:   score -= 15
    if target_moved:       score -= 15
    if premature_exit:     score -= 20
    if added_size_adverse: score -= 20
    if timeframe_changed:  score -= 10
    return clamp(score)

def calculate_risk_score(
    stop_price: Optional[float], entry_price: float, target_price: Optional[float],
    size: float, direction: str, max_risk_pct: float = 2.0
) -> float:
    score = 100.0
    if not stop_price:
        return 75.0
    if target_price and stop_price:
        if direction == "long":
            risk   = abs(entry_price - stop_price)
            reward = abs(target_price - entry_price)
        else:
            risk   = abs(stop_price - entry_price)
            reward = abs(entry_price - target_price)
        if risk > 0:
            rr = reward / risk
            if rr < 1.5: score -= 20
    stop_dist_pct = abs(entry_price - stop_price) / entry_price * 100
    if stop_dist_pct > 2.0: score -= 15
    return clamp(score)

def calculate_execution_quality(timing: float, discipline: float, risk: float) -> float:
    return clamp(timing * 0.35 + discipline * 0.35 + risk * 0.30)

def calculate_composite(setup: float, execution: float, discipline: float, risk: float) -> float:
    return clamp(setup * 0.30 + execution * 0.30 + discipline * 0.20 + risk * 0.20)

def determine_behavior_flag(
    timing_score: float, discipline_score: float,
    premature_exit: bool, no_plan: bool, decision_score: float
) -> str:
    if timing_score <= 35:     return "late_chase"
    if premature_exit:         return "premature_exit"
    if no_plan:                return "plan_violated"
    if discipline_score >= 90: return "plan_followed"
    if discipline_score <= 60: return "plan_violated"
    if decision_score >= 80 and no_plan: return "ignored_high_quality_signal"
    return "disciplined_execution"

# ── Regime memory ─────────────────────────────────────────────────────────────

def update_regime_memory(conn, user_id: str, regime: str, symbol: str,
                          pnl_pct: float, decision_score: float, flag: str):
    row_id = f"{user_id}_{regime}_{symbol}"
    cur = dict_cursor(conn)
    cur.execute("SELECT * FROM regime_memory WHERE id=%s", (row_id,))
    existing = cur.fetchone()

    if existing:
        n     = existing["total_trades"] + 1
        wins  = round(existing["win_rate"] * existing["total_trades"] / 100)
        if pnl_pct > 0: wins += 1
        new_wr      = round(wins / n * 100, 1)
        new_avg_dec = round((existing["avg_decision_score"] * (n-1) + decision_score) / n, 1)
        new_avg_pnl = round((existing["avg_pnl_percent"]   * (n-1) + pnl_pct)        / n, 2)
        cur.execute("""
            UPDATE regime_memory
            SET total_trades=%s, win_rate=%s, avg_decision_score=%s,
                avg_pnl_percent=%s, common_behavior_flag=%s, updated_at=NOW()
            WHERE id=%s
        """, (n, new_wr, new_avg_dec, new_avg_pnl, flag, row_id))
    else:
        win_rate = 100.0 if pnl_pct > 0 else 0.0
        cur.execute("""
            INSERT INTO regime_memory
            (id, user_id, regime, symbol, total_trades, win_rate,
             avg_decision_score, avg_pnl_percent, common_behavior_flag)
            VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s)
        """, (row_id, user_id, regime, symbol, win_rate,
              round(decision_score, 1), round(pnl_pct, 2), flag))
    conn.commit()
    cur.close()

# ── Adaptive warnings ─────────────────────────────────────────────────────────

def build_adaptive_warnings(user_id: str, conn) -> list[dict]:
    cur = dict_cursor(conn)
    warnings = []

    cur.execute("""
        SELECT primary_behavior_flag FROM decision_scorecards
        WHERE user_id=%s ORDER BY timestamp DESC LIMIT 10
    """, (user_id,))
    recent_flags = cur.fetchall()
    chase_count = sum(1 for r in recent_flags if r["primary_behavior_flag"] == "late_chase")
    if chase_count >= 3:
        warnings.append({"type":"warning","rule":"late_chase",
            "message":"Behavioral Alert: You have recently chased entries after expansion moves. Consider waiting for retest confirmation."})

    cur.execute("SELECT avg_decision_score FROM regime_memory WHERE user_id=%s AND regime='panic'", (user_id,))
    panic_mem = cur.fetchone()
    if panic_mem and panic_mem["avg_decision_score"] < 60:
        warnings.append({"type":"warning","rule":"panic_regime",
            "message":"Regime Alert: Your historical performance weakens during panic volatility. Reduce size or require stronger confirmation."})

    cur.execute("SELECT avg_decision_score FROM regime_memory WHERE user_id=%s AND regime='trend_continuation'", (user_id,))
    trend_mem = cur.fetchone()
    if trend_mem and trend_mem["avg_decision_score"] >= 75:
        warnings.append({"type":"strength","rule":"trend_strength",
            "message":"Strength Zone: Your best historical decision quality occurs during trend continuation setups."})

    cur.close()
    return warnings

# ── Router ────────────────────────────────────────────────────────────────────

behavior_router = APIRouter(prefix="/api/behavior", tags=["behavior"])

@behavior_router.post("/event")
def log_event(ev: BehavioralEventIn):
    event_id = "evt_" + uuid.uuid4().hex[:12]
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO behavioral_events
        (event_id, user_id, event_type, symbol, price, timeframe,
         market_regime, decision_score, decision_status, timestamp, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
    """, (event_id, ev.user_id, ev.event_type, ev.symbol,
          ev.price, ev.timeframe, ev.market_regime,
          ev.decision_score, ev.decision_status,
          json.dumps(ev.metadata or {})))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "event_id": event_id}

@behavior_router.get("/events/{user_id}")
def get_events(user_id: str, limit: int = 50):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("SELECT * FROM behavioral_events WHERE user_id=%s ORDER BY timestamp DESC LIMIT %s", (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@behavior_router.post("/snapshot")
def save_snapshot(snap: MarketSnapshotIn):
    snap_id = "snap_" + uuid.uuid4().hex[:12]
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO market_snapshots
        (snapshot_id, symbol, price, volume, timeframe, decision_score,
         decision_status, decision_bias, confidence, regime, confluence_nodes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (snap_id, snap.symbol, snap.price, snap.volume, snap.timeframe,
          snap.decision_score, snap.decision_status, snap.decision_bias,
          snap.confidence, snap.regime, json.dumps(snap.confluence_nodes)))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "snapshot_id": snap_id}

@behavior_router.post("/trade-plan")
def create_trade_plan(plan: TradePlanIn):
    plan_id = "plan_" + uuid.uuid4().hex[:12]
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO trade_plans
        (plan_id, user_id, symbol, direction, planned_entry, planned_stop,
         planned_target, planned_size, setup_reason, signal_score_at_plan, regime_at_plan)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (plan_id, plan.user_id, plan.symbol, plan.direction,
          plan.planned_entry, plan.planned_stop, plan.planned_target,
          plan.planned_size, plan.setup_reason,
          plan.signal_score_at_plan, plan.regime_at_plan))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "plan_id": plan_id}

@behavior_router.get("/trade-plans/{user_id}")
def get_trade_plans(user_id: str):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("SELECT * FROM trade_plans WHERE user_id=%s ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@behavior_router.post("/trade-entry")
def enter_trade(t: TradeEntryIn):
    trade_id = "trade_" + uuid.uuid4().hex[:12]
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO trades
        (trade_id, user_id, plan_id, symbol, direction, entry_price,
         stop_price, target_price, size, entry_time,
         market_regime_entry, signal_score_entry, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,'open')
    """, (trade_id, t.user_id, t.plan_id, t.symbol, t.direction,
          t.entry_price, t.stop_price, t.target_price, t.size,
          t.market_regime_entry, t.signal_score_entry))
    conn.commit()
    cur.close(); conn.close()
    return {"ok": True, "trade_id": trade_id}

@behavior_router.get("/trades/{user_id}")
def get_trades(user_id: str):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("SELECT * FROM trades WHERE user_id=%s ORDER BY entry_time DESC", (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]

@behavior_router.get("/open-trade/{user_id}")
def get_open_trade(user_id: str):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("SELECT * FROM trades WHERE user_id=%s AND status='open' ORDER BY entry_time DESC LIMIT 1", (user_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else {}

@behavior_router.post("/trade-exit")
def exit_trade(ex: TradeExitIn):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("SELECT * FROM trades WHERE trade_id=%s", (ex.trade_id,))
    trade = cur.fetchone()
    if not trade:
        raise HTTPException(404, "Trade not found")
    trade = dict(trade)

    direction   = trade["direction"]
    entry_price = trade["entry_price"]
    exit_price  = ex.exit_price
    size        = trade["size"]

    if direction == "long":
        pnl     = (exit_price - entry_price) * size
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
    else:
        pnl     = (entry_price - exit_price) * size
        pnl_pct = ((entry_price - exit_price) / entry_price) * 100

    plan = None
    if trade.get("plan_id"):
        cur.execute("SELECT * FROM trade_plans WHERE plan_id=%s", (trade["plan_id"],))
        plan = cur.fetchone()

    signal_price = dict(plan)["planned_entry"] if plan else entry_price

    timing     = calculate_timing_score(signal_price, entry_price, direction)
    discipline = calculate_discipline_score(
        no_plan=ex.no_plan, stop_moved_wider=ex.stop_moved_wider,
        target_moved=ex.target_moved, premature_exit=ex.premature_exit,
        added_size_adverse=ex.added_size_adverse, timeframe_changed=ex.timeframe_changed)
    risk = calculate_risk_score(
        trade.get("stop_price"), entry_price, trade.get("target_price"), size, direction)
    setup = calculate_setup_quality(
        trade["signal_score_entry"] or 50, "MEDIUM", trade["market_regime_entry"] or "neutral")
    execution = calculate_execution_quality(timing, discipline, risk)
    composite = calculate_composite(setup, execution, discipline, risk)
    flag      = determine_behavior_flag(timing, discipline, ex.premature_exit,
                                        ex.no_plan, trade["signal_score_entry"] or 50)

    cur.execute("""
        UPDATE trades
        SET exit_price=%s, exit_time=NOW(), pnl=%s, pnl_percent=%s,
            market_regime_exit=%s, signal_score_exit=%s, status='closed'
        WHERE trade_id=%s
    """, (exit_price, round(pnl,2), round(pnl_pct,2),
          ex.market_regime_exit, ex.signal_score_exit, ex.trade_id))

    sc_id = "sc_" + uuid.uuid4().hex[:12]
    cur.execute("""
        INSERT INTO decision_scorecards
        (scorecard_id, user_id, trade_id, symbol,
         setup_quality_score, execution_quality_score, discipline_score,
         timing_score, risk_management_score, confidence_calibration_score,
         composite_decision_score, primary_behavior_flag, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (sc_id, trade["user_id"], ex.trade_id, trade["symbol"],
          round(setup,1), round(execution,1), round(discipline,1),
          round(timing,1), round(risk,1), round(discipline,1),
          round(composite,1), flag, ex.notes))

    conn.commit()
    update_regime_memory(conn, trade["user_id"],
                         trade["market_regime_entry"] or "neutral",
                         trade["symbol"], pnl_pct,
                         trade["signal_score_entry"] or 50, flag)
    cur.close(); conn.close()

    return {
        "ok": True, "scorecard_id": sc_id,
        "pnl": round(pnl,2), "pnl_percent": round(pnl_pct,2),
        "scores": {
            "setup_quality":     round(setup,1),
            "timing":            round(timing,1),
            "discipline":        round(discipline,1),
            "risk_management":   round(risk,1),
            "execution_quality": round(execution,1),
            "composite":         round(composite,1),
        },
        "behavior_flag": flag,
    }

@behavior_router.get("/dashboard/{user_id}")
def get_dashboard(user_id: str):
    conn = get_db()
    cur  = dict_cursor(conn)

    cur.execute("SELECT * FROM decision_scorecards WHERE user_id=%s ORDER BY timestamp DESC", (user_id,))
    scorecards = [dict(r) for r in cur.fetchall()]
    total = len(scorecards)

    avg_composite  = round(sum(s["composite_decision_score"]     for s in scorecards) / total, 1) if total else 0
    avg_execution  = round(sum(s["execution_quality_score"]      for s in scorecards) / total, 1) if total else 0
    avg_discipline = round(sum(s["discipline_score"]             for s in scorecards) / total, 1) if total else 0
    avg_timing     = round(sum(s["timing_score"]                 for s in scorecards) / total, 1) if total else 0
    avg_risk       = round(sum(s["risk_management_score"]        for s in scorecards) / total, 1) if total else 0

    from collections import Counter
    flag_counts = Counter(s["primary_behavior_flag"] for s in scorecards)
    common_flag = flag_counts.most_common(1)[0][0] if flag_counts else "neutral"

    cur.execute("SELECT * FROM regime_memory WHERE user_id=%s ORDER BY total_trades DESC", (user_id,))
    regime_rows = [dict(r) for r in cur.fetchall()]
    best_regime  = max(regime_rows, key=lambda r: r["win_rate"], default=None)
    worst_regime = min(regime_rows, key=lambda r: r["win_rate"], default=None)

    warnings = build_adaptive_warnings(user_id, conn)
    cur.close(); conn.close()

    return {
        "user_id":              user_id,
        "total_trades":         total,
        "avg_decision_score":   avg_composite,
        "execution_score":      avg_execution,
        "discipline_score":     avg_discipline,
        "timing_score":         avg_timing,
        "risk_score":           avg_risk,
        "common_behavior_flag": common_flag,
        "best_regime":          best_regime["regime"]  if best_regime  else None,
        "worst_regime":         worst_regime["regime"] if worst_regime else None,
        "regime_performance":   regime_rows,
        "recent_scorecards":    scorecards[:10],
        "adaptive_warnings":    warnings,
    }

@behavior_router.get("/scorecards/{user_id}")
def get_scorecards(user_id: str, limit: int = 20):
    conn = get_db()
    cur  = dict_cursor(conn)
    cur.execute("""
        SELECT ds.*, t.symbol, t.direction, t.pnl, t.pnl_percent
        FROM decision_scorecards ds
        LEFT JOIN trades t ON ds.trade_id = t.trade_id
        WHERE ds.user_id=%s ORDER BY ds.timestamp DESC LIMIT %s
    """, (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]