# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/scoreboard_service.py
------------------------------
Sigmalytic Radar — Confidence-Based Signal Scoreboard

HOW IT WORKS
────────────
1. When a symbol hits Armed, Triggered, Short Trigger, or Short Armed —
   a signal row is written to scoreboard_signals.
   Grade is assigned IMMEDIATELY based on confluence confidence score.
   No waiting for price targets — signal quality is judged at signal time.

2. The outcome tracker runs periodically and evaluates signals older than
   SCOREBOARD_OUTCOME_HOURS:
   - Records actual price movement for transparency and learning
   - Does NOT change the grade — grade is permanent at signal time

3. The scoreboard shows confidence distribution, not win/loss rates.

CONFIDENCE GRADE DEFINITIONS
─────────────────────────────
  A  — Score ≥ 80 · High confluence · Multiple engines aligned
  B  — Score 70–79 · Good confluence · Signal confirmed
  C  — Score 60–69 · Moderate confluence · Watch closely
  W  — Score 55–59 · Marginal · Educational only
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

SCOREBOARD_SIGNAL_TYPES = {
    "Armed", "Triggered",
    "Short Armed", "Short Trigger",
}

DEDUP_WINDOW_HOURS = 2

# Launch / Production outcome tracking window
# Default is 4 hours for launch responsiveness.
# Set SCOREBOARD_OUTCOME_HOURS=20 or 24 in Render for a longer production window.
SCOREBOARD_OUTCOME_HOURS = int(
    os.getenv("SCOREBOARD_OUTCOME_HOURS", "4")
)


def _db():
    return psycopg2.connect(DATABASE_URL)


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def _is_market_hours() -> bool:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo
    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
    market_open  = et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= et < market_close


def _already_logged_recently(symbol: str, signal_type: str) -> bool:
    if not DATABASE_URL:
        return False
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM scoreboard_signals
            WHERE symbol = %s AND signal_type = %s AND signal_date >= %s
        """, (symbol, signal_type, cutoff))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0
    except Exception as e:
        log.warning(f"Dedup check error: {e}")
        return False


def _confidence_grade(score: float, sym: dict) -> str:
    """
    Assign confidence grade immediately at signal time.
    Based on composite score + engine alignment bonuses.
    """
    if score <= 0:
        return "W"

    # Engine alignment bonuses
    bonus = 0
    weis = sym.get("weis_signal", "NONE") or "NONE"
    gex  = sym.get("gex_regime", "") or ""
    bme  = float(sym.get("bme_score", 50) or 50)

    # Weis Wave confirmation
    if weis in ("SPRING", "CLIMAX_SELL", "3BAR_BULLISH"):
        bonus += 3
    elif weis in ("UPTHRUST", "CLIMAX_BUY", "3BAR_BEARISH"):
        bonus += 3

    # GEX regime alignment
    signal_type = sym.get("status", "")
    if "Short" in signal_type and gex == "NEGATIVE":
        bonus += 2
    elif "Short" not in signal_type and gex == "POSITIVE":
        bonus += 2

    # BME behavioral confirmation
    if bme >= 65:
        bonus += 2
    elif bme <= 35:
        bonus += 2  # strong bearish also confirms short signals

    adjusted = score + bonus

    if adjusted >= 80:
        return "A"
    elif adjusted >= 70:
        return "B"
    elif adjusted >= 60:
        return "C"
    return "W"


def log_signal(sym: dict, signal_type: str):
    """
    Log a signal with immediate confidence grade.
    Grade is based on confluence score + engine alignment at signal time.
    """
    symbol = sym.get("symbol", "")
    if not symbol or not DATABASE_URL:
        return

    if not _is_market_hours():
        return

    if signal_type not in SCOREBOARD_SIGNAL_TYPES:
        return

    score = float(sym.get("composite_score", 0) or 0)
    if score < 55:
        return

    if _already_logged_recently(symbol, signal_type):
        return

    signal_id = "sig_" + uuid.uuid4().hex[:14]
    price     = sym.get("price", 0)
    grade     = _confidence_grade(score, sym)

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
                %s,%s,%s
            )
            ON CONFLICT (signal_id) DO NOTHING
        """, (
            signal_id, symbol, signal_type, datetime.now(timezone.utc),
            price,
            sym.get("trigger", 0),
            sym.get("invalidation", 0),
            sym.get("target1", 0),
            sym.get("target2", 0),
            score,
            sym.get("setup_type", ""),
            sym.get("regime", ""),
            sym.get("confluence", 0),
            sym.get("expansion_node", 0),
            sym.get("relative_strength", 0),
            sym.get("volume_pressure", 0),
            sym.get("behavioral", 0),
            grade,
        ))
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Scoreboard: {symbol} → {signal_type} | Score:{score} | Grade:{grade}")
    except Exception as e:
        log.warning(f"Signal log error: {e}")


def _fetch_close_price(symbol: str) -> Optional[float]:
    """Fetch the most recent closing price for outcome tracking."""
    try:
        from radar_service import RADAR_CACHE
        cached = RADAR_CACHE.get(symbol.upper())
        if cached:
            price = cached.get("price")
            if price and float(price) > 0:
                return float(price)
    except Exception:
        pass

    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
            headers=_alpaca_headers(),
            params={"timeframe": "1Day", "limit": 3, "feed": ALPACA_FEED, "sort": "desc"},
            timeout=10,
        )
        if r.status_code == 200:
            bars = r.json().get("bars") or []
            for bar in bars:
                close = float(bar.get("c", 0))
                if close > 0:
                    return close
    except Exception as e:
        log.warning(f"Price fetch error {symbol}: {e}")
    return None


def grade_pending_signals():
    """
    Outcome tracker — records actual price movement for transparency.
    Grade is NOT changed — it was assigned at signal time.
    Runs periodically and evaluates signals older than
    SCOREBOARD_OUTCOME_HOURS.
    """
    if not DATABASE_URL:
        return

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=SCOREBOARD_OUTCOME_HOURS
    )

    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT signal_id, symbol, signal_type, signal_date,
                   entry_price, target1, target2, invalidation
            FROM scoreboard_signals
            WHERE outcome_price IS NULL
              AND signal_date < %s
            ORDER BY signal_date ASC
            LIMIT 200
        """, (cutoff,))
        pending = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning(f"Outcome fetch error: {e}")
        return

    if not pending:
        log.info("No signals need outcome tracking")
        return

    log.info(f"Tracking outcomes for {len(pending)} signals")
    tracked = 0

    for row in pending:
        sig_id, symbol, sig_type, sig_date, entry, t1, t2, inval = row
        outcome = _fetch_close_price(symbol)
        if not outcome or not entry:
            continue
        time.sleep(0.1)

        days        = (datetime.now(timezone.utc) - sig_date).days
        outcome_pct = round((outcome - entry) / entry * 100, 2)
        is_short    = "Short" in sig_type

        # Outcome direction
        if is_short:
            hit_t1    = outcome <= t1    if t1 > 0 else False
            hit_t2    = outcome <= t2    if t2 > 0 else False
            hit_inval = outcome >= inval if inval > 0 else False
        else:
            hit_t1    = outcome >= t1    if t1 > 0 else False
            hit_t2    = outcome >= t2    if t2 > 0 else False
            hit_inval = outcome <= inval if inval > 0 else False

        try:
            conn = _db()
            cur  = conn.cursor()
            cur.execute("""
                UPDATE scoreboard_signals
                SET outcome_price    = %s,
                    outcome_date     = %s,
                    outcome_pct      = %s,
                    graded_at        = %s,
                    days_to_outcome  = %s,
                    hit_target1      = %s,
                    hit_target2      = %s,
                    hit_invalidation = %s
                WHERE signal_id = %s
                  AND outcome_price IS NULL
            """, (
                outcome, datetime.now(timezone.utc), outcome_pct,
                datetime.now(timezone.utc), days,
                hit_t1, hit_t2, hit_inval,
                sig_id,
            ))
            conn.commit()
            cur.close()
            conn.close()
            tracked += 1
        except Exception as e:
            log.warning(f"Outcome update error {sig_id}: {e}")

    log.info(f"Outcome tracking complete — {tracked}/{len(pending)} signals updated")


def clear_duplicate_signals():
    """Remove duplicate signals — keep only the most recent per symbol+signal_type per day."""
    if not DATABASE_URL:
        return 0
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
                ) ranked
                WHERE rn > 1
            )
        """)
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Cleared {deleted} duplicate signals")
        return deleted
    except Exception as e:
        log.warning(f"Duplicate clear error: {e}")
        return 0


def get_scoreboard_stats() -> dict:
    """Returns confidence-based scoreboard statistics."""
    if not DATABASE_URL:
        return {}
    try:
        conn = _db()
        cur  = conn.cursor()

        cur.execute("""
            SELECT
                COUNT(*)                                           AS total_signals,
                COUNT(*) FILTER (WHERE outcome_price IS NOT NULL) AS with_outcomes,
                COUNT(*) FILTER (WHERE outcome_price IS NULL)     AS pending_outcomes,
                COUNT(*) FILTER (WHERE grade = 'A')               AS grade_a,
                COUNT(*) FILTER (WHERE grade = 'B')               AS grade_b,
                COUNT(*) FILTER (WHERE grade = 'C')               AS grade_c,
                COUNT(*) FILTER (WHERE grade = 'W')               AS grade_w,
                ROUND(AVG(outcome_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                    AND signal_type NOT LIKE 'Short%%'
                )::numeric, 2)                                     AS avg_long_pct,
                ROUND(AVG(outcome_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                    AND signal_type LIKE 'Short%%'
                )::numeric, 2)                                     AS avg_short_pct,
                ROUND(AVG(days_to_outcome) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 1)                                     AS avg_days,
                COUNT(*) FILTER (WHERE hit_target1 = true)        AS hit_t1_count,
                COUNT(*) FILTER (WHERE hit_target2 = true)        AS hit_t2_count
            FROM scoreboard_signals
        """)
        row = cur.fetchone()

        cur.execute("""
            SELECT symbol, signal_type, signal_date, entry_price,
                   composite_score, setup_type, regime, grade,
                   outcome_pct, days_to_outcome, hit_target1, hit_target2
            FROM scoreboard_signals
            ORDER BY signal_date DESC
            LIMIT 50
        """)
        signals = cur.fetchall()
        cur.close()
        conn.close()

        total    = row[0] or 0
        grade_a  = row[3] or 0
        grade_b  = row[4] or 0
        grade_ab = grade_a + grade_b

        return {
            "total_signals":    total,
            "with_outcomes":    row[1] or 0,
            "pending_outcomes": row[2] or 0,
            "grade_a":          grade_a,
            "grade_b":          grade_b,
            "grade_c":          row[5] or 0,
            "grade_w":          row[6] or 0,
            "high_confidence":  round(grade_ab / total * 100, 1) if total > 0 else 0,
            "avg_long_pct":     float(row[7] or 0),
            "avg_short_pct":    float(row[8] or 0),
            "avg_days":         float(row[9] or 0),
            "hit_target1_rate": round((row[10] or 0) / max(row[1] or 1, 1) * 100, 1),
            "hit_target2_rate": round((row[11] or 0) / max(row[1] or 1, 1) * 100, 1),
            "recent_signals": [
                {
                    "symbol":      s[0],
                    "signal_type": s[1],
                    "signal_date": s[2].isoformat() if s[2] else None,
                    "entry_price": float(s[3]) if s[3] else None,
                    "score":       float(s[4]) if s[4] else None,
                    "setup_type":  s[5],
                    "regime":      s[6],
                    "grade":       s[7],
                    "outcome_pct": float(s[8]) if s[8] else None,
                    "days":        float(s[9]) if s[9] else None,
                    "hit_t1":      s[10],
                    "hit_t2":      s[11],
                }
                for s in signals
            ],
        }
    except Exception as e:
        log.warning(f"Scoreboard stats error: {e}")
        return {}