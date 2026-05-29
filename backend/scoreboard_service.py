# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/scoreboard_service.py
------------------------------
Sigmalytic Radar — Historical Signal Scoreboard

HOW IT WORKS
────────────
1. When a symbol hits Armed, Triggered, Short Trigger, or Short Armed —
   a signal row is written to scoreboard_signals with entry price + levels.
   Deduplication is database-backed — same symbol+type within 2 hours = skip.

2. Every day at 4:15 PM ET (after close), the outcome checker runs:
   - Finds all Pending signals older than 1 trading day
   - Fetches current/closing price from Alpaca
   - Grades the signal: A / B / C / Miss / Short-A / Short-B / Short-C / Short-Miss
   - Updates the row with outcome price, pct, and grade

3. The scoreboard API exposes this data publicly — transparency by design.

GRADE DEFINITIONS
─────────────────
Long signals:
  A     — Hit target2 (full projection)
  B     — Hit target1 (partial projection)
  C     — Moved in right direction but didn't reach target1
  Miss  — Hit invalidation (stop loss triggered)

Short signals:
  Short-A    — Dropped to bear target2
  Short-B    — Dropped to bear target1
  Short-C    — Moved lower but didn't reach bear target1
  Short-Miss — Recovered above entry (short failed)

Pending — Not yet graded (< 1 trading day old)
"""

from __future__ import annotations
import os
import uuid
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import requests as _req

log = logging.getLogger("scoreboard")

DATABASE_URL      = os.getenv("DATABASE_URL", "")
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED       = os.getenv("ALPACA_FEED", "iex")

# Signal types that get logged to scoreboard
SCOREBOARD_SIGNAL_TYPES = {
    "Armed", "Triggered",
    "Short Armed", "Short Trigger",
}

# Minimum time between logging the same symbol+signal_type (2 hours)
DEDUP_WINDOW_HOURS = 2


def _db():
    return psycopg2.connect(DATABASE_URL)


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


# ── Signal logging ─────────────────────────────────────────────────────────────

def _already_logged_recently(symbol: str, signal_type: str) -> bool:
    """
    Check database to see if this symbol+signal_type was logged
    within the dedup window. Survives restarts.
    """
    if not DATABASE_URL:
        return False
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM scoreboard_signals
            WHERE symbol = %s
              AND signal_type = %s
              AND signal_date >= %s
        """, (symbol, signal_type, cutoff))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0
    except Exception as e:
        log.warning(f"Dedup check error: {e}")
        return False


def log_signal(sym: dict, signal_type: str):
    """
    Log a new signal to scoreboard_signals.
    Uses database dedup — skips if same symbol+type logged within 2 hours.
    Survives backend restarts unlike in-memory tracking.
    """
    symbol = sym.get("symbol", "")
    if not symbol or not DATABASE_URL:
        return

    # Only log important signal types
    if signal_type not in SCOREBOARD_SIGNAL_TYPES:
        return

    # Database-backed deduplication — restart-safe
    if _already_logged_recently(symbol, signal_type):
        return

    signal_id = "sig_" + uuid.uuid4().hex[:14]
    price     = sym.get("price", 0)
    atr       = sym.get("atr", 1)

    # Bear targets for short signals
    inval  = sym.get("invalidation", 0)
    bear1  = round(inval - atr, 2) if inval > 0 else 0
    bear2  = round(inval - atr * 2, 2) if inval > 0 else 0

    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO scoreboard_signals (
                signal_id, symbol, signal_type, signal_date,
                entry_price, trigger_level, invalidation, target1, target2,
                composite_score, setup_type, regime,
                confluence, expansion_node, relative_strength,
                volume_pressure, behavioral, grade
            ) VALUES (
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,'Pending'
            )
            ON CONFLICT (signal_id) DO NOTHING
        """, (
            signal_id, symbol, signal_type, datetime.now(timezone.utc),
            price,
            sym.get("trigger", 0),
            sym.get("invalidation", 0),
            sym.get("target1", 0) if "Short" not in signal_type else bear1,
            sym.get("target2", 0) if "Short" not in signal_type else bear2,
            sym.get("composite_score", 0),
            sym.get("setup_type", ""),
            sym.get("regime", ""),
            sym.get("confluence", 0),
            sym.get("expansion_node", 0),
            sym.get("relative_strength", 0),
            sym.get("volume_pressure", 0),
            sym.get("behavioral", 0),
        ))
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Scoreboard signal logged: {symbol} → {signal_type} @ ${price}")
    except Exception as e:
        log.warning(f"Signal log error: {e}")


# ── Outcome grading ────────────────────────────────────────────────────────────

def _fetch_close_price(symbol: str) -> Optional[float]:
    """Fetch the most recent completed closing price from Alpaca.
    Requests 2 bars so we always get yesterday's close even pre-market."""
    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
            headers=_alpaca_headers(),
            params={
                "timeframe": "1Day",
                "limit":     2,
                "feed":      ALPACA_FEED,
                "sort":      "desc",
            },
            timeout=10,
        )
        if r.status_code == 200:
            bars = r.json().get("bars") or []
            for bar in bars:
                close = float(bar.get("c", 0))
                if close > 0:
                    return close
        else:
            log.warning(f"Price fetch {symbol}: status {r.status_code}")
    except Exception as e:
        log.warning(f"Price fetch error {symbol}: {e}")
    return None


def _grade_long(entry, target1, target2, invalidation, outcome) -> tuple[str, bool, bool, bool]:
    """Grade a long signal. Returns (grade, hit_t1, hit_t2, hit_inval)."""
    if outcome <= 0 or entry <= 0:
        return "Pending", False, False, False

    hit_t2    = outcome >= target2      if target2 > 0 else False
    hit_t1    = outcome >= target1      if target1 > 0 else False
    hit_inval = outcome <= invalidation if invalidation > 0 else False

    if hit_t2:    return "A",    True,  True,  False
    if hit_t1:    return "B",    True,  False, False
    if hit_inval: return "Miss", False, False, True

    pct = (outcome - entry) / entry * 100
    if pct > 0:   return "C",    False, False, False
    return "Miss", False, False, True


def _grade_short(entry, target1, target2, invalidation, outcome) -> tuple[str, bool, bool, bool]:
    """Grade a short signal. Returns (grade, hit_t1, hit_t2, hit_inval)."""
    if outcome <= 0 or entry <= 0:
        return "Pending", False, False, False

    hit_t2    = outcome <= target2      if target2 > 0 else False
    hit_t1    = outcome <= target1      if target1 > 0 else False
    hit_inval = outcome >= invalidation if invalidation > 0 else False

    if hit_t2:    return "Short-A",    True,  True,  False
    if hit_t1:    return "Short-B",    True,  False, False
    if hit_inval: return "Short-Miss", False, False, True

    pct = (entry - outcome) / entry * 100
    if pct > 0:   return "Short-C", False, False, False
    return "Short-Miss", False, False, True


def grade_pending_signals():
    """
    Grade all Pending signals that are at least 1 trading day old.
    Called daily at 4:15 PM ET by the scheduler.
    """
    if not DATABASE_URL:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)

    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT signal_id, symbol, signal_type, signal_date,
                   entry_price, target1, target2, invalidation
            FROM scoreboard_signals
            WHERE grade = 'Pending'
              AND signal_date < %s
            ORDER BY signal_date ASC
            LIMIT 100
        """, (cutoff,))
        pending = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning(f"Pending fetch error: {e}")
        return

    if not pending:
        log.info("No pending signals to grade")
        return

    log.info(f"Grading {len(pending)} pending signals")
    graded = 0

    for row in pending:
        sig_id, symbol, sig_type, sig_date, entry, t1, t2, inval = row
        outcome = _fetch_close_price(symbol)
        if not outcome:
            continue
        time.sleep(0.1)

        days = (datetime.now(timezone.utc) - sig_date).days

        is_short = "Short" in sig_type
        if is_short:
            grade, hit_t1, hit_t2, hit_inval = _grade_short(entry, t1, t2, inval, outcome)
        else:
            grade, hit_t1, hit_t2, hit_inval = _grade_long(entry, t1, t2, inval, outcome)

        if grade == "Pending":
            continue

        outcome_pct = round((outcome - entry) / entry * 100, 2) if entry > 0 else 0

        try:
            conn = _db()
            cur  = conn.cursor()
            cur.execute("""
                UPDATE scoreboard_signals
                SET outcome_price    = %s,
                    outcome_date     = %s,
                    outcome_pct      = %s,
                    grade            = %s,
                    graded_at        = %s,
                    days_to_outcome  = %s,
                    hit_target1      = %s,
                    hit_target2      = %s,
                    hit_invalidation = %s
                WHERE signal_id = %s
            """, (
                outcome, datetime.now(timezone.utc), outcome_pct,
                grade, datetime.now(timezone.utc), days,
                hit_t1, hit_t2, hit_inval,
                sig_id,
            ))
            conn.commit()
            cur.close()
            conn.close()
            graded += 1
            log.info(f"Graded {symbol} {sig_type}: {grade} @ ${outcome} ({outcome_pct:+.1f}%)")
        except Exception as e:
            log.warning(f"Grade update error {sig_id}: {e}")

    log.info(f"Grading complete — {graded}/{len(pending)} signals graded")


# ── Clear duplicate signals ────────────────────────────────────────────────────

def clear_duplicate_signals():
    """
    Remove duplicate Pending signals — keep only the most recent
    per symbol+signal_type within the same day.
    Run once to clean up the existing 259 duplicates.
    """
    if not DATABASE_URL:
        return
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            DELETE FROM scoreboard_signals
            WHERE signal_id IN (
                SELECT signal_id FROM (
                    SELECT signal_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol, signal_type,
                                            DATE(signal_date AT TIME ZONE 'America/New_York')
                               ORDER BY signal_date DESC
                           ) AS rn
                    FROM scoreboard_signals
                    WHERE grade = 'Pending'
                ) ranked
                WHERE rn > 1
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Cleared {deleted} duplicate pending signals")
        return deleted
    except Exception as e:
        log.warning(f"Duplicate clear error: {e}")
        return 0


# ── Scoreboard stats ───────────────────────────────────────────────────────────

def get_scoreboard_stats() -> dict:
    """Returns summary statistics for the public scoreboard."""
    if not DATABASE_URL:
        return {}
    try:
        conn = _db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE grade != 'Pending')                    AS total_graded,
                COUNT(*) FILTER (WHERE grade = 'Pending')                     AS pending,
                COUNT(*) FILTER (WHERE grade IN ('A','B'))                    AS long_winners,
                COUNT(*) FILTER (WHERE grade = 'Miss')                        AS long_misses,
                COUNT(*) FILTER (WHERE grade IN ('Short-A','Short-B'))        AS short_winners,
                COUNT(*) FILTER (WHERE grade = 'Short-Miss')                  AS short_misses,
                COUNT(*) FILTER (WHERE grade = 'A')                           AS grade_a,
                COUNT(*) FILTER (WHERE grade = 'B')                           AS grade_b,
                COUNT(*) FILTER (WHERE grade = 'C')                           AS grade_c,
                ROUND(AVG(outcome_pct) FILTER (WHERE grade NOT IN ('Pending','Miss','Short-Miss'))::numeric, 2) AS avg_winner_pct,
                ROUND(AVG(days_to_outcome) FILTER (WHERE grade != 'Pending')::numeric, 1) AS avg_days
            FROM scoreboard_signals
        """)
        row = cur.fetchone()

        cur.execute("""
            SELECT symbol, signal_type, signal_date, entry_price,
                   composite_score, setup_type, regime, grade, outcome_pct, days_to_outcome
            FROM scoreboard_signals
            ORDER BY signal_date DESC
            LIMIT 50
        """)
        signals = cur.fetchall()
        cur.close()
        conn.close()

        total_graded  = row[0] or 0
        long_winners  = row[2] or 0
        long_misses   = row[3] or 0
        short_winners = row[4] or 0
        short_misses  = row[5] or 0

        long_total  = long_winners + long_misses
        short_total = short_winners + short_misses
        long_wr  = round(long_winners  / long_total  * 100, 1) if long_total  > 0 else 0
        short_wr = round(short_winners / short_total * 100, 1) if short_total > 0 else 0

        return {
            "total_graded":   total_graded,
            "pending":        row[1] or 0,
            "long_win_rate":  long_wr,
            "short_win_rate": short_wr,
            "grade_a":        row[6] or 0,
            "grade_b":        row[7] or 0,
            "grade_c":        row[8] or 0,
            "avg_winner_pct": float(row[9] or 0),
            "avg_days":       float(row[10] or 0),
            "recent_signals": [
                {
                    "symbol":      s[0],
                    "signal_type": s[1],
                    "signal_date": s[2].isoformat() if s[2] else None,
                    "entry_price": s[3],
                    "score":       s[4],
                    "setup_type":  s[5],
                    "regime":      s[6],
                    "grade":       s[7],
                    "outcome_pct": s[8],
                    "days":        s[9],
                }
                for s in signals
            ],
        }
    except Exception as e:
        log.warning(f"Scoreboard stats error: {e}")
        return {}
