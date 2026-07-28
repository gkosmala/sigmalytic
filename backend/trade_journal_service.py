# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/trade_journal_service.py
---------------------------------
Trade Journal — Layer 5 (Trader Intelligence).

Records every trade a subscriber actually takes, grades the decision
quality, and builds a behavioral profile over time.

Per the blueprint (Part XI):
  The Journal measures:
    Entry Quality      — did you enter at the right time?
    Exit Quality       — did you exit at the right time?
    Patience           — did you hold through noise?
    FOMO               — did you chase?
    Position Sizing    — did you size correctly?
    Rule Compliance    — did you follow the system?
    Behavioral Consistency — are you improving?

  The Platform Learns The Trader.

DATABASE
--------
Uses the same psycopg2 / DATABASE_URL pattern as scoreboard_service.py.
Two tables:
  trade_journal        — one row per trade
  trader_profile       — one row per user, rolling behavioral grades

BEHAVIORAL GRADES
-----------------
Entry Quality:
  A — Entered within 0.5% of signal entry price on signal day
  B — Entered within 1% or within 1 day
  C — Entered within 2% or within 3 days
  D — Entered late or away from signal
  F — No corresponding signal found

Exit Quality:
  A — Exited at or above target, or held full 90 days
  B — Exited within 5% of target
  C — Exited profitable but before target
  D — Exited at breakeven or small loss
  F — Stopped out

Patience Score (0-100):
  Measures whether the trader held through normal campaign noise
  without premature exits. Computed from hold duration vs campaign age.

FOMO Score (0-100, lower is better):
  Detects chasing — entering after a large single-day move,
  sizing up on winning streaks, or trading outside signal windows.

CLAUDE.md compliance
--------------------
• Credentials via os.environ only (DATABASE_URL).
• Decimal for all prices.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("trade_journal")

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def _db():
    import psycopg2
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(DATABASE_URL)


# FIX (2026-07-28): get_journal_entries() and get_trader_profile() below
# used to go through _db() (raw psycopg2 + DATABASE_URL) -- the one
# credential path that resisted every fix attempt tonight (fresh
# passwords, pooler vs direct connection, IPv4 vs IPv6), while every
# other part of this app reads/writes Supabase successfully via the
# Supabase client (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY), which has
# worked reliably all session. Rather than keep chasing that one
# specific credential, these two read functions now use the same proven
# client method as everything else. This also means, if these tables
# don't exist yet in Supabase (very possible -- no trade has ever
# actually been logged in this environment), the resulting error will be
# a clear, specific PostgREST message instead of an opaque connection
# failure.
_supabase_client = None


def _supabase():
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    from supabase import create_client
    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


def _ensure_tables():
    """Create trade_journal and trader_profile tables if they don't exist."""
    try:
        conn = _db()
        cur  = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS trade_journal (
                journal_id          TEXT PRIMARY KEY,
                user_id             TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                direction           TEXT NOT NULL DEFAULT 'LONG',
                entry_date          DATE,
                entry_price         NUMERIC(18,6),
                exit_date           DATE,
                exit_price          NUMERIC(18,6),
                shares              INTEGER,
                position_value      NUMERIC(18,2),
                pnl                 NUMERIC(18,2),
                pnl_pct             NUMERIC(10,4),
                hold_days           INTEGER,
                signal_id           TEXT,
                campaign_id         TEXT,
                tier                TEXT,
                entry_quality_grade TEXT,
                exit_quality_grade  TEXT,
                patience_score      NUMERIC(6,2),
                fomo_score          NUMERIC(6,2),
                sizing_grade        TEXT,
                rule_compliance     BOOLEAN DEFAULT TRUE,
                notes               TEXT,
                status              TEXT DEFAULT 'OPEN',
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_user
            ON trade_journal(user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_symbol
            ON trade_journal(symbol)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_status
            ON trade_journal(status)
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS trader_profile (
                user_id                 TEXT PRIMARY KEY,
                total_trades            INTEGER DEFAULT 0,
                open_trades             INTEGER DEFAULT 0,
                win_rate                NUMERIC(6,2),
                avg_pnl_pct             NUMERIC(10,4),
                avg_hold_days           NUMERIC(8,2),
                avg_entry_quality       NUMERIC(6,2),
                avg_exit_quality        NUMERIC(6,2),
                avg_patience_score      NUMERIC(6,2),
                avg_fomo_score          NUMERIC(6,2),
                entry_grade_dist        JSONB,
                exit_grade_dist         JSONB,
                behavioral_trend        TEXT,
                strongest_pattern       TEXT,
                weakest_pattern         TEXT,
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        conn.commit()
        cur.close()
        conn.close()

    except Exception as exc:
        log.error("Table creation error: %s", exc)


# ---------------------------------------------------------------------------
# Behavioral grading
# ---------------------------------------------------------------------------

def _grade_entry_quality(
    actual_entry:   float,
    signal_entry:   Optional[float],
    signal_date:    Optional[date],
    actual_date:    date,
) -> str:
    """Grade how well the trader executed the entry vs the signal."""
    if not signal_entry or signal_entry <= 0:
        return "N/A"

    price_diff_pct = abs(actual_entry - signal_entry) / signal_entry * 100
    days_late      = (actual_date - signal_date).days if signal_date else 999

    if price_diff_pct <= 0.5 and days_late <= 1:
        return "A"
    if price_diff_pct <= 1.0 or days_late <= 1:
        return "B"
    if price_diff_pct <= 2.0 or days_late <= 3:
        return "C"
    if price_diff_pct <= 5.0 or days_late <= 7:
        return "D"
    return "F"


def _grade_exit_quality(
    exit_price:    float,
    entry_price:   float,
    target_price:  Optional[float],
    stop_price:    Optional[float],
    hold_days:     int,
) -> str:
    """Grade how well the trader executed the exit."""
    if entry_price <= 0:
        return "N/A"

    pnl_pct = (exit_price - entry_price) / entry_price * 100

    # Held full campaign duration
    if hold_days >= 85:
        return "A" if pnl_pct > 0 else "B"

    # Exited at or above target
    if target_price and exit_price >= target_price * 0.95:
        return "A"

    # Exited profitably near target
    if target_price and exit_price >= target_price * 0.80:
        return "B"

    # Exited profitable but well before target
    if pnl_pct > 5:
        return "C"

    # Breakeven or small loss
    if pnl_pct >= -2:
        return "D"

    # Stopped out
    return "F"


def _compute_patience_score(
    hold_days:    int,
    campaign_age: int,
    exit_reason:  str,
) -> float:
    """
    Patience score 0-100.
    Higher = held through noise appropriately.
    """
    if campaign_age <= 0:
        return 50.0

    # Base: proportion of campaign held
    hold_ratio = min(1.0, hold_days / 90.0)
    base       = hold_ratio * 60.0

    # Bonus for holding through campaign maturity stages
    if hold_days >= 60:
        base += 20.0
    elif hold_days >= 30:
        base += 10.0

    # Penalty for early exits (before day 20)
    if hold_days < 20 and exit_reason != "STOP_HIT":
        base -= 20.0

    return round(min(100.0, max(0.0, base)), 1)


def _compute_fomo_score(
    entry_price:      float,
    prior_close:      Optional[float],
    signal_entry:     Optional[float],
    days_after_signal: int,
) -> float:
    """
    FOMO score 0-100. Lower is better.
    Detects chasing — entering after a big move or very late.
    """
    score = 0.0

    # Entering after a large single-day move
    if prior_close and prior_close > 0:
        day_move = (entry_price - prior_close) / prior_close * 100
        if day_move > 3:
            score += 30.0
        elif day_move > 1.5:
            score += 15.0

    # Entering significantly above signal price
    if signal_entry and signal_entry > 0:
        above_signal = (entry_price - signal_entry) / signal_entry * 100
        if above_signal > 3:
            score += 40.0
        elif above_signal > 1:
            score += 20.0

    # Entering very late
    if days_after_signal > 7:
        score += 30.0
    elif days_after_signal > 3:
        score += 15.0

    return round(min(100.0, max(0.0, score)), 1)


def _grade_sizing(
    position_value: float,
    portfolio_value: float,
    recommended_pct: float,
) -> str:
    """Grade position sizing vs the Half-Kelly recommendation."""
    if portfolio_value <= 0 or recommended_pct <= 0:
        return "N/A"

    actual_pct   = position_value / portfolio_value * 100
    deviation    = abs(actual_pct - recommended_pct) / recommended_pct

    if deviation <= 0.10:
        return "A"   # within 10% of recommendation
    if deviation <= 0.25:
        return "B"   # within 25%
    if deviation <= 0.50:
        return "C"   # within 50%
    if actual_pct > recommended_pct * 2:
        return "F"   # significantly oversized
    return "D"


# ---------------------------------------------------------------------------
# Journal operations
# ---------------------------------------------------------------------------

def log_trade_entry(
    user_id:         str,
    symbol:          str,
    entry_date:      date,
    entry_price:     Decimal,
    shares:          int,
    direction:       str        = "LONG",
    signal_id:       Optional[str] = None,
    campaign_id:     Optional[str] = None,
    tier:            Optional[str] = None,
    notes:           Optional[str] = None,
    portfolio_value: float         = 0.0,
) -> Optional[str]:
    """
    Log a new trade entry to the journal.
    Returns journal_id if successful, None if failed.
    """
    _ensure_tables()

    journal_id     = "jrn_" + uuid.uuid4().hex[:14]
    position_value = float(entry_price) * shares

    # Look up signal entry price for quality grading
    signal_entry = None
    signal_date  = None
    if signal_id:
        try:
            conn = _db()
            cur  = conn.cursor()
            cur.execute(
                "SELECT entry_price, signal_date FROM scoreboard_signals WHERE signal_id = %s",
                (signal_id,)
            )
            row = cur.fetchone()
            if row:
                signal_entry = float(row[0]) if row[0] else None
                signal_date  = row[1].date() if row[1] else None
            cur.close()
            conn.close()
        except Exception as exc:
            log.warning("Signal lookup failed: %s", exc)

    days_after = (entry_date - signal_date).days if signal_date else 0
    entry_grade = _grade_entry_quality(
        float(entry_price), signal_entry, signal_date, entry_date
    )
    fomo_score = _compute_fomo_score(
        float(entry_price), signal_entry, signal_entry, days_after
    )

    # Recommended sizing
    recommended_pct = 21.2 if tier == "TIER_1" else (19.9 if tier == "TIER_2" else 0)
    sizing_grade = _grade_sizing(position_value, portfolio_value, recommended_pct)

    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO trade_journal (
                journal_id, user_id, symbol, direction,
                entry_date, entry_price, shares, position_value,
                signal_id, campaign_id, tier,
                entry_quality_grade, fomo_score, sizing_grade,
                notes, status, created_at, updated_at
            ) VALUES (
                %s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,'OPEN',NOW(),NOW()
            )
        """, (
            journal_id, user_id, symbol, direction,
            entry_date, float(entry_price), shares, position_value,
            signal_id, campaign_id, tier,
            entry_grade, fomo_score, sizing_grade,
            notes,
        ))
        conn.commit()
        cur.close()
        conn.close()

        log.info("Trade logged: %s %s @ $%s | grade=%s fomo=%.0f",
                 symbol, direction, entry_price, entry_grade, fomo_score)
        return journal_id

    except Exception as exc:
        log.error("Trade log error for %s: %s", symbol, exc)
        return None


def log_trade_exit(
    journal_id:      str,
    exit_date:       date,
    exit_price:      Decimal,
    exit_reason:     str        = "MANUAL",
    notes:           Optional[str] = None,
) -> bool:
    """
    Record the exit for an open trade and compute final grades.
    Returns True if successful.
    """
    try:
        conn = _db()
        cur  = conn.cursor()

        # Fetch existing trade
        cur.execute("""
            SELECT entry_price, entry_date, shares, campaign_id,
                   signal_id, tier, position_value
            FROM trade_journal WHERE journal_id = %s
        """, (journal_id,))
        row = cur.fetchone()
        if not row:
            log.warning("Journal entry not found: %s", journal_id)
            cur.close()
            conn.close()
            return False

        entry_price, entry_date, shares, campaign_id, signal_id, tier, pos_val = row
        entry_price  = float(entry_price)
        exit_price_f = float(exit_price)
        hold_days    = (exit_date - entry_date).days if entry_date else 0
        pnl          = (exit_price_f - entry_price) * (shares or 0)
        pnl_pct      = (exit_price_f - entry_price) / entry_price * 100 if entry_price > 0 else 0

        # Look up target from signal
        target_price = None
        stop_price   = None
        campaign_age = hold_days
        if signal_id:
            try:
                cur.execute(
                    "SELECT target1, invalidation FROM scoreboard_signals WHERE signal_id = %s",
                    (signal_id,)
                )
                sig = cur.fetchone()
                if sig:
                    target_price = float(sig[0]) if sig[0] else None
                    stop_price   = float(sig[1]) if sig[1] else None
            except Exception:
                pass

        exit_grade     = _grade_exit_quality(exit_price_f, entry_price, target_price, stop_price, hold_days)
        patience_score = _compute_patience_score(hold_days, campaign_age, exit_reason)

        cur.execute("""
            UPDATE trade_journal SET
                exit_date          = %s,
                exit_price         = %s,
                pnl                = %s,
                pnl_pct            = %s,
                hold_days          = %s,
                exit_quality_grade = %s,
                patience_score     = %s,
                status             = 'CLOSED',
                notes              = COALESCE(notes || ' | ' || %s, notes, %s),
                updated_at         = NOW()
            WHERE journal_id = %s
        """, (
            exit_date, float(exit_price), round(pnl, 2), round(pnl_pct, 4),
            hold_days, exit_grade, patience_score,
            f"Exit: {exit_reason}", f"Exit: {exit_reason}",
            journal_id,
        ))
        conn.commit()
        cur.close()
        conn.close()

        log.info("Trade exit logged: %s | pnl=%.1f%% | exit_grade=%s | patience=%.0f",
                 journal_id, pnl_pct, exit_grade, patience_score)

        # Update trader profile
        _update_trader_profile(row[0] if row else None, journal_id)
        return True

    except Exception as exc:
        log.error("Trade exit error for %s: %s", journal_id, exc)
        return False


def get_journal_entries(
    user_id: str,
    status:  Optional[str] = None,
    limit:   int            = 100,
) -> list[dict]:
    """Fetch journal entries for a user."""
    try:
        columns = (
            "journal_id, symbol, direction, entry_date, entry_price, "
            "exit_date, exit_price, shares, position_value, pnl, pnl_pct, "
            "hold_days, tier, entry_quality_grade, exit_quality_grade, "
            "patience_score, fomo_score, sizing_grade, status, notes, "
            "signal_id, campaign_id, created_at"
        )

        query = (
            _supabase()
            .table("trade_journal")
            .select(columns)
            .eq("user_id", user_id)
        )
        if status:
            query = query.eq("status", status)

        response = query.order("created_at", desc=True).limit(limit).execute()
        rows = response.data or []

        return [
            {
                "journal_id":          r.get("journal_id"),
                "symbol":              r.get("symbol"),
                "direction":           r.get("direction"),
                "entry_date":          str(r["entry_date"]) if r.get("entry_date") else None,
                "entry_price":         float(r["entry_price"]) if r.get("entry_price") else 0,
                "exit_date":           str(r["exit_date"]) if r.get("exit_date") else None,
                "exit_price":          float(r["exit_price"]) if r.get("exit_price") else 0,
                "shares":              r.get("shares") or 0,
                "position_value":      float(r["position_value"]) if r.get("position_value") else 0,
                "pnl":                 float(r["pnl"]) if r.get("pnl") else 0,
                "pnl_pct":             float(r["pnl_pct"]) if r.get("pnl_pct") else 0,
                "hold_days":           r.get("hold_days") or 0,
                "tier":                r.get("tier"),
                "entry_quality_grade": r.get("entry_quality_grade"),
                "exit_quality_grade":  r.get("exit_quality_grade"),
                "patience_score":      float(r["patience_score"]) if r.get("patience_score") else 0,
                "fomo_score":          float(r["fomo_score"]) if r.get("fomo_score") else 0,
                "sizing_grade":        r.get("sizing_grade"),
                "status":              r.get("status"),
                "notes":               r.get("notes"),
                "signal_id":           r.get("signal_id"),
                "campaign_id":         r.get("campaign_id"),
                "created_at":          str(r["created_at"]) if r.get("created_at") else None,
            }
            for r in rows
        ]
    except Exception as exc:
        log.error("Get journal error for %s: %s", user_id, exc)
        return []


def get_trader_profile(user_id: str) -> dict:
    """Get the behavioral profile for a trader."""
    try:
        response = (
            _supabase()
            .table("trader_profile")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []

        if not rows:
            return {"user_id": user_id, "total_trades": 0, "message": "No trades logged yet."}

        return rows[0]

    except Exception as exc:
        log.error("Get profile error for %s: %s", user_id, exc)
        return {"user_id": user_id, "error": str(exc)}


def _update_trader_profile(entry_price_unused: Any, journal_id: str) -> None:
    """Recompute the trader profile from all closed trades."""
    try:
        conn = _db()
        cur  = conn.cursor()

        # Get user_id from the journal entry
        cur.execute("SELECT user_id FROM trade_journal WHERE journal_id = %s", (journal_id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return
        user_id = row[0]

        # Aggregate stats from all closed trades
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE pnl > 0) as wins,
                AVG(pnl_pct) as avg_pnl,
                AVG(hold_days) as avg_hold,
                AVG(patience_score) as avg_patience,
                AVG(fomo_score) as avg_fomo
            FROM trade_journal
            WHERE user_id = %s AND status = 'CLOSED'
        """, (user_id,))
        stats = cur.fetchone()

        cur.execute(
            "SELECT COUNT(*) FROM trade_journal WHERE user_id = %s AND status = 'OPEN'",
            (user_id,)
        )
        open_count = cur.fetchone()[0]

        if stats and stats[0] > 0:
            total, wins, avg_pnl, avg_hold, avg_patience, avg_fomo = stats
            win_rate = wins / total * 100

            # Grade distributions
            import json
            for grade_col, dist_col in [
                ("entry_quality_grade", "entry_grade_dist"),
                ("exit_quality_grade", "exit_grade_dist"),
            ]:
                cur.execute(f"""
                    SELECT {grade_col}, COUNT(*) FROM trade_journal
                    WHERE user_id = %s AND status = 'CLOSED' AND {grade_col} IS NOT NULL
                    GROUP BY {grade_col}
                """, (user_id,))
                dist = {r[0]: r[1] for r in cur.fetchall()}

            # Behavioral trend
            trend = "IMPROVING" if (avg_patience or 0) > 65 and (avg_fomo or 0) < 30 else (
                "NEEDS_WORK" if (avg_fomo or 0) > 50 else "STABLE"
            )

            cur.execute("""
                INSERT INTO trader_profile (
                    user_id, total_trades, open_trades, win_rate, avg_pnl_pct,
                    avg_hold_days, avg_patience_score, avg_fomo_score,
                    behavioral_trend, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    total_trades      = EXCLUDED.total_trades,
                    open_trades       = EXCLUDED.open_trades,
                    win_rate          = EXCLUDED.win_rate,
                    avg_pnl_pct       = EXCLUDED.avg_pnl_pct,
                    avg_hold_days     = EXCLUDED.avg_hold_days,
                    avg_patience_score = EXCLUDED.avg_patience_score,
                    avg_fomo_score    = EXCLUDED.avg_fomo_score,
                    behavioral_trend  = EXCLUDED.behavioral_trend,
                    updated_at        = EXCLUDED.updated_at
            """, (
                user_id, total, open_count, round(win_rate, 1),
                round(float(avg_pnl or 0), 2), round(float(avg_hold or 0), 1),
                round(float(avg_patience or 0), 1), round(float(avg_fomo or 0), 1),
                trend,
            ))
            conn.commit()

        cur.close()
        conn.close()

    except Exception as exc:
        log.error("Profile update error: %s", exc)
