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

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_SERVICE_KEY", "")
    or os.getenv("SUPABASE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
_SUPABASE_CLIENT = None


def _supabase():
    """
    Return a cached Supabase client for active journal persistence.
    """
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE key are required for journal persistence")

    try:
        from supabase import create_client
    except Exception as exc:
        raise RuntimeError(f"Supabase client import failed: {exc}") from exc

    _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _SUPABASE_CLIENT


def _sb_rows(result: Any) -> list[dict]:
    data = getattr(result, "data", None)
    if data is None:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _date_or_none(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(raw[:10])
        except Exception:
            return None


def _iso_date(value: Any) -> Optional[str]:
    parsed = _date_or_none(value)
    return parsed.isoformat() if parsed else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



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
    Log a new trade entry through Supabase.
    Returns journal_id if successful, None if failed.
    """
    journal_id     = "jrn_" + uuid.uuid4().hex[:14]
    entry_price_f  = float(entry_price)
    shares_i       = int(shares or 0)
    position_value = entry_price_f * shares_i

    try:
        sb = _supabase()

        signal_entry = None
        signal_date  = None

        if signal_id:
            try:
                sig_res = (
                    sb.table("scoreboard_signals")
                    .select("entry_price, signal_date")
                    .eq("signal_id", signal_id)
                    .limit(1)
                    .execute()
                )
                sig_rows = _sb_rows(sig_res)
                if sig_rows:
                    sig = sig_rows[0]
                    signal_entry = _safe_float(sig.get("entry_price"), 0.0) or None
                    signal_date = _date_or_none(sig.get("signal_date"))
            except Exception as exc:
                log.warning("Signal lookup failed: %s", exc)

        days_after = (entry_date - signal_date).days if signal_date else 0
        entry_grade = _grade_entry_quality(entry_price_f, signal_entry, signal_date, entry_date)
        fomo_score = _compute_fomo_score(entry_price_f, signal_entry, signal_entry, days_after)

        recommended_pct = 21.2 if tier == "TIER_1" else (19.9 if tier == "TIER_2" else 0)
        sizing_grade = _grade_sizing(position_value, portfolio_value, recommended_pct)

        payload = {
            "journal_id": journal_id,
            "user_id": user_id,
            "symbol": str(symbol or "").upper().strip(),
            "direction": str(direction or "LONG").upper().strip(),
            "entry_date": _iso_date(entry_date),
            "entry_price": entry_price_f,
            "shares": shares_i,
            "position_value": round(position_value, 2),
            "signal_id": signal_id,
            "campaign_id": campaign_id,
            "tier": tier,
            "entry_quality_grade": entry_grade,
            "fomo_score": round(float(fomo_score or 0), 2),
            "sizing_grade": sizing_grade,
            "notes": notes,
            "status": "OPEN",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }

        sb.table("trade_journal").insert(payload).execute()

        log.info(
            "Trade logged: %s %s @ $%s | grade=%s fomo=%.0f",
            payload["symbol"],
            payload["direction"],
            entry_price,
            entry_grade,
            fomo_score,
        )
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
    Record the exit for an open trade through Supabase.
    Returns True if successful.
    """
    try:
        sb = _supabase()

        trade_res = (
            sb.table("trade_journal")
            .select(
                "journal_id, user_id, entry_price, entry_date, shares, campaign_id, "
                "signal_id, tier, position_value, notes"
            )
            .eq("journal_id", journal_id)
            .limit(1)
            .execute()
        )
        trade_rows = _sb_rows(trade_res)
        if not trade_rows:
            log.warning("Journal entry not found: %s", journal_id)
            return False

        row = trade_rows[0]

        entry_price = _safe_float(row.get("entry_price"), 0.0)
        entry_dt    = _date_or_none(row.get("entry_date"))
        shares_i    = _safe_int(row.get("shares"), 0)
        signal_id   = row.get("signal_id")
        old_notes   = row.get("notes")

        exit_price_f = float(exit_price)
        hold_days    = (exit_date - entry_dt).days if entry_dt else 0
        pnl          = (exit_price_f - entry_price) * shares_i
        pnl_pct      = (exit_price_f - entry_price) / entry_price * 100 if entry_price > 0 else 0

        target_price = None
        stop_price   = None
        campaign_age = hold_days

        if signal_id:
            try:
                sig_res = (
                    sb.table("scoreboard_signals")
                    .select("target1, invalidation")
                    .eq("signal_id", signal_id)
                    .limit(1)
                    .execute()
                )
                sig_rows = _sb_rows(sig_res)
                if sig_rows:
                    sig = sig_rows[0]
                    target_price = _safe_float(sig.get("target1"), 0.0) or None
                    stop_price = _safe_float(sig.get("invalidation"), 0.0) or None
            except Exception as exc:
                log.warning("Signal target lookup failed for %s: %s", journal_id, exc)

        exit_grade     = _grade_exit_quality(exit_price_f, entry_price, target_price, stop_price, hold_days)
        patience_score = _compute_patience_score(hold_days, campaign_age, exit_reason)

        exit_note = f"Exit: {exit_reason}"
        if notes:
            exit_note = f"{exit_note} | {notes}"
        combined_notes = exit_note if not old_notes else f"{old_notes} | {exit_note}"

        update_payload = {
            "exit_date": _iso_date(exit_date),
            "exit_price": exit_price_f,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "hold_days": hold_days,
            "exit_quality_grade": exit_grade,
            "patience_score": round(float(patience_score or 0), 2),
            "status": "CLOSED",
            "notes": combined_notes,
            "updated_at": _now_iso(),
        }

        sb.table("trade_journal").update(update_payload).eq("journal_id", journal_id).execute()

        log.info(
            "Trade exit logged: %s | pnl=%.1f%% | exit_grade=%s | patience=%.0f",
            journal_id,
            pnl_pct,
            exit_grade,
            patience_score,
        )

        _update_trader_profile(None, journal_id)
        return True

    except Exception as exc:
        log.error("Trade exit error for %s: %s", journal_id, exc)
        return False


def get_journal_entries(
    user_id: str,
    status:  Optional[str] = None,
    limit:   int            = 100,
) -> list[dict]:
    """Fetch journal entries for a user through Supabase."""
    try:
        sb = _supabase()
        query = (
            sb.table("trade_journal")
            .select(
                "journal_id, symbol, direction, entry_date, entry_price, exit_date, exit_price, "
                "shares, position_value, pnl, pnl_pct, hold_days, tier, entry_quality_grade, "
                "exit_quality_grade, patience_score, fomo_score, sizing_grade, status, notes, "
                "signal_id, campaign_id, created_at"
            )
            .eq("user_id", user_id)
        )

        if status:
            query = query.eq("status", status)

        result = query.order("created_at", desc=True).limit(int(limit or 100)).execute()
        rows = _sb_rows(result)

        return [
            {
                "journal_id":          r.get("journal_id"),
                "symbol":              r.get("symbol"),
                "direction":           r.get("direction"),
                "entry_date":          str(r.get("entry_date")) if r.get("entry_date") else None,
                "entry_price":         _safe_float(r.get("entry_price"), 0.0),
                "exit_date":           str(r.get("exit_date")) if r.get("exit_date") else None,
                "exit_price":          _safe_float(r.get("exit_price"), 0.0),
                "shares":              _safe_int(r.get("shares"), 0),
                "position_value":      _safe_float(r.get("position_value"), 0.0),
                "pnl":                 _safe_float(r.get("pnl"), 0.0),
                "pnl_pct":             _safe_float(r.get("pnl_pct"), 0.0),
                "hold_days":           _safe_int(r.get("hold_days"), 0),
                "tier":                r.get("tier"),
                "entry_quality_grade": r.get("entry_quality_grade"),
                "exit_quality_grade":  r.get("exit_quality_grade"),
                "patience_score":      _safe_float(r.get("patience_score"), 0.0),
                "fomo_score":          _safe_float(r.get("fomo_score"), 0.0),
                "sizing_grade":        r.get("sizing_grade"),
                "status":              r.get("status"),
                "notes":               r.get("notes"),
                "signal_id":           r.get("signal_id"),
                "campaign_id":         r.get("campaign_id"),
                "created_at":          str(r.get("created_at")) if r.get("created_at") else None,
            }
            for r in rows
        ]

    except Exception as exc:
        log.error("Get journal error for %s: %s", user_id, exc)
        return []


def get_trader_profile(user_id: str) -> dict:
    """Get the behavioral profile for a trader through Supabase."""
    try:
        sb = _supabase()
        result = (
            sb.table("trader_profile")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = _sb_rows(result)

        if not rows:
            return {"user_id": user_id, "total_trades": 0, "message": "No trades logged yet."}

        return rows[0]

    except Exception as exc:
        log.error("Get profile error for %s: %s", user_id, exc)
        return {"user_id": user_id, "error": str(exc)}


def _update_trader_profile(entry_price_unused: Any, journal_id: str) -> None:
    """Recompute the trader profile from all closed trades through Supabase."""
    try:
        sb = _supabase()

        entry_res = (
            sb.table("trade_journal")
            .select("user_id")
            .eq("journal_id", journal_id)
            .limit(1)
            .execute()
        )
        entry_rows = _sb_rows(entry_res)
        if not entry_rows:
            return

        user_id = entry_rows[0].get("user_id")
        if not user_id:
            return

        all_res = (
            sb.table("trade_journal")
            .select(
                "status, pnl, pnl_pct, hold_days, patience_score, fomo_score, "
                "entry_quality_grade, exit_quality_grade"
            )
            .eq("user_id", user_id)
            .execute()
        )
        all_rows = _sb_rows(all_res)

        closed = [r for r in all_rows if str(r.get("status") or "").upper() == "CLOSED"]
        open_count = len([r for r in all_rows if str(r.get("status") or "").upper() == "OPEN"])

        total = len(closed)
        wins = len([r for r in closed if _safe_float(r.get("pnl"), 0.0) > 0])
        win_rate = wins / total * 100 if total else 0.0

        def avg(key: str) -> float:
            vals = [_safe_float(r.get(key), 0.0) for r in closed if r.get(key) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        def dist(key: str) -> dict:
            out: dict[str, int] = {}
            for r in closed:
                grade = r.get(key)
                if grade:
                    out[str(grade)] = out.get(str(grade), 0) + 1
            return out

        avg_pnl = avg("pnl_pct")
        avg_hold = avg("hold_days")
        avg_patience = avg("patience_score")
        avg_fomo = avg("fomo_score")

        def grade_avg(key: str) -> float:
            grade_points = {"A": 95.0, "B": 85.0, "C": 75.0, "D": 65.0, "F": 40.0}
            vals = [
                grade_points[str(r.get(key)).upper()]
                for r in closed
                if str(r.get(key)).upper() in grade_points
            ]
            return sum(vals) / len(vals) if vals else 0.0

        avg_entry_quality = grade_avg("entry_quality_grade")
        avg_exit_quality = grade_avg("exit_quality_grade")

        trend = "IMPROVING" if avg_patience > 65 and avg_fomo < 30 else (
            "NEEDS_WORK" if avg_fomo > 50 else "STABLE"
        )

        strongest_pattern = "PATIENCE" if avg_patience >= 70 else (
            "ENTRY_DISCIPLINE" if avg_entry_quality >= 85 else (
                "EXIT_DISCIPLINE" if avg_exit_quality >= 85 else "CONSISTENCY"
            )
        )

        weakest_pattern = "FOMO_CONTROL" if avg_fomo > 50 else (
            "PATIENCE" if avg_patience < 40 else (
                "ENTRY_DISCIPLINE" if avg_entry_quality < 70 else (
                    "EXIT_DISCIPLINE" if avg_exit_quality < 70 else "NONE"
                )
            )
        )

        profile_payload = {
            "user_id": user_id,
            "total_trades": total,
            "open_trades": open_count,
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "avg_hold_days": round(avg_hold, 1),
            "avg_entry_quality": round(avg_entry_quality, 1),
            "avg_exit_quality": round(avg_exit_quality, 1),
            "avg_patience_score": round(avg_patience, 1),
            "avg_fomo_score": round(avg_fomo, 1),
            "entry_grade_dist": dist("entry_quality_grade"),
            "exit_grade_dist": dist("exit_quality_grade"),
            "behavioral_trend": trend,
            "strongest_pattern": strongest_pattern,
            "weakest_pattern": weakest_pattern,
            "updated_at": _now_iso(),
        }

        sb.table("trader_profile").upsert(profile_payload, on_conflict="user_id").execute()

    except Exception as exc:
        log.error("Profile update error: %s", exc)
