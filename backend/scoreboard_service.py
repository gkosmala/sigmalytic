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

3. The scoreboard shows confidence distribution plus outcome path metrics
   such as direction correctness, MFE, and MAE.

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


def _to_float(value, default: float = 0.0) -> float:
    """Safe float conversion used by intelligence agreement scoring."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _agreement_bucket(agreement: float) -> str:
    """
    Bucket agreement score for validation reporting.

    Agreement 90-100 = Strong Confirmation
    Agreement 80-89  = Good Confirmation
    Agreement 70-79  = Mixed
    Agreement <70    = Warning / Filter Out
    """
    if agreement >= 90:
        return "90-100 Strong Confirmation"
    if agreement >= 80:
        return "80-89 Good Confirmation"
    if agreement >= 70:
        return "70-79 Mixed"
    return "<70 Warning"


def _derive_intelligence_metrics(sym: dict) -> tuple[float, float, float, str]:
    """
    Derive deep_score, intelligence_delta, agreement_score, and agreement_bucket.

    The radar payload may use different field names depending on which engine
    produced the symbol. This function accepts all known aliases.

    Preferred:
      composite_score = surface radar score
      deep_score      = deeper intelligence/BME score
      delta           = deep_score - composite_score

    Agreement:
      100 - abs(delta)
    """
    composite = _to_float(
        sym.get("composite_score", sym.get("score", 0)),
        0.0,
    )

    deep = _to_float(
        sym.get(
            "deep_score",
            sym.get(
                "intelligence_score",
                sym.get(
                    "behavioral",
                    sym.get(
                        "bme_score",
                        sym.get("behavioral_score", composite),
                    ),
                ),
            ),
        ),
        composite,
    )

    # Prefer backend-provided delta if present; otherwise compute it.
    if sym.get("intelligence_delta") is not None:
        delta = _to_float(sym.get("intelligence_delta"), deep - composite)
    elif sym.get("delta") is not None:
        delta = _to_float(sym.get("delta"), deep - composite)
    else:
        delta = deep - composite

    agreement = max(0.0, min(100.0, 100.0 - abs(delta)))
    bucket = _agreement_bucket(agreement)

    return round(deep, 2), round(delta, 2), round(agreement, 2), bucket


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
    deep_score, intelligence_delta, agreement_score, agreement_bucket = _derive_intelligence_metrics(sym)

    _ensure_outcome_metric_columns()

    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO scoreboard_signals (
                signal_id, symbol, signal_type, signal_date,
                entry_price, trigger_level, invalidation, target1, target2,
                composite_score, setup_type, regime,
                confluence, expansion_node, relative_strength,
                volume_pressure, behavioral, grade,
                deep_score, intelligence_delta, agreement_score, agreement_bucket
            ) VALUES (
                %s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s
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
            deep_score,
            intelligence_delta,
            agreement_score,
            agreement_bucket,
        ))
        conn.commit()
        cur.close()
        conn.close()
        log.info(
            f"Scoreboard: {symbol} → {signal_type} | Score:{score} | "
            f"Grade:{grade} | Agreement:{agreement_score} | Delta:{intelligence_delta}"
        )
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



def _ensure_outcome_metric_columns():
    """Create launch analytics columns if they do not already exist."""
    if not DATABASE_URL:
        return
    try:
        conn = _db()
        cur  = conn.cursor()
        cur.execute("""
            ALTER TABLE scoreboard_signals
            ADD COLUMN IF NOT EXISTS direction_correct BOOLEAN,
            ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC,
            ADD COLUMN IF NOT EXISTS mae_pct NUMERIC,
            ADD COLUMN IF NOT EXISTS outcome_window_hours INTEGER,
            ADD COLUMN IF NOT EXISTS deep_score NUMERIC,
            ADD COLUMN IF NOT EXISTS intelligence_delta NUMERIC,
            ADD COLUMN IF NOT EXISTS agreement_score NUMERIC,
            ADD COLUMN IF NOT EXISTS agreement_bucket TEXT;
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.warning(f"Outcome metric column check failed: {e}")


def _fetch_outcome_bars(symbol: str, signal_date: datetime, limit: int = 1000) -> list[dict]:
    """Fetch intraday bars from signal time through now for MFE/MAE calculations."""
    try:
        start = signal_date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end   = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
            headers=_alpaca_headers(),
            params={
                "timeframe": "5Min",
                "start": start,
                "end": end,
                "limit": limit,
                "feed": ALPACA_FEED,
                "adjustment": "raw",
                "sort": "asc",
            },
            timeout=12,
        )
        if r.status_code == 200:
            return r.json().get("bars") or []
        log.warning(f"Outcome bars fetch failed {symbol}: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log.warning(f"Outcome bars fetch error {symbol}: {e}")
    return []


def _compute_path_metrics(
    symbol: str,
    sig_type: str,
    sig_date: datetime,
    entry: float,
    outcome: float,
) -> tuple[bool, float, float]:
    """
    Returns direction_correct, MFE%, and MAE%.

    MFE = maximum favorable excursion after the signal.
    MAE = maximum adverse excursion after the signal.
    Both are positive percentages so they are easy to compare.
    """
    is_short = "Short" in (sig_type or "")
    direction_correct = outcome < entry if is_short else outcome > entry

    bars = _fetch_outcome_bars(symbol, sig_date)
    highs = []
    lows  = []

    for b in bars:
        try:
            highs.append(float(b.get("h", 0) or 0))
            lows.append(float(b.get("l", 0) or 0))
        except Exception:
            continue

    if not highs or not lows:
        # Fallback: use final outcome only when intraday path is unavailable.
        if is_short:
            favorable = max(0.0, (entry - outcome) / entry * 100)
            adverse   = max(0.0, (outcome - entry) / entry * 100)
        else:
            favorable = max(0.0, (outcome - entry) / entry * 100)
            adverse   = max(0.0, (entry - outcome) / entry * 100)
        return direction_correct, round(favorable, 2), round(adverse, 2)

    max_high = max(highs)
    min_low  = min(lows)

    if is_short:
        mfe = max(0.0, (entry - min_low) / entry * 100)
        mae = max(0.0, (max_high - entry) / entry * 100)
    else:
        mfe = max(0.0, (max_high - entry) / entry * 100)
        mae = max(0.0, (entry - min_low) / entry * 100)

    return direction_correct, round(mfe, 2), round(mae, 2)


def grade_pending_signals():
    """
    Outcome tracker — records actual price movement for transparency.
    Grade is NOT changed — it was assigned at signal time.
    Runs periodically and evaluates signals older than
    SCOREBOARD_OUTCOME_HOURS.
    """
    if not DATABASE_URL:
        return

    _ensure_outcome_metric_columns()

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

        direction_correct, mfe_pct, mae_pct = _compute_path_metrics(
            symbol, sig_type, sig_date, float(entry), float(outcome)
        )

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
                    hit_invalidation = %s,
                    direction_correct= %s,
                    mfe_pct          = %s,
                    mae_pct          = %s,
                    outcome_window_hours = %s
                WHERE signal_id = %s
                  AND outcome_price IS NULL
            """, (
                outcome, datetime.now(timezone.utc), outcome_pct,
                datetime.now(timezone.utc), days,
                hit_t1, hit_t2, hit_inval,
                direction_correct, mfe_pct, mae_pct, SCOREBOARD_OUTCOME_HOURS,
                sig_id,
            ))
            conn.commit()
            cur.close()
            conn.close()
            tracked += 1
        except Exception as e:
            log.warning(f"Outcome update error {sig_id}: {e}")

    log.info(f"Outcome tracking complete — {tracked}/{len(pending)} signals updated")



def repair_scoreboard_history(limit: int = 500) -> dict:
    """
    Backfill/repair older scoreboard rows that were created before the
    path-metric engine existed.

    Repairs:
    1. Missing confidence grades that still say Pending/null/blank.
    2. Missing direction_correct, mfe_pct, mae_pct for rows that already
       have outcome_price populated.

    This is safe to run repeatedly. It only updates missing/legacy fields.
    """
    result = {"grades_repaired": 0, "path_metrics_repaired": 0, "agreement_repaired": 0, "errors": []}
    if not DATABASE_URL:
        result["errors"].append("DATABASE_URL is not configured")
        return result

    _ensure_outcome_metric_columns()

    # 1) Repair legacy Pending/null grades using the same confidence logic.
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, composite_score, signal_type,
                   confluence, expansion_node, relative_strength,
                   volume_pressure, behavioral, setup_type, regime
            FROM scoreboard_signals
            WHERE grade IS NULL
               OR grade = ''
               OR LOWER(grade) = 'pending'
            ORDER BY signal_date ASC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        for row in rows:
            sig_id, score, sig_type, confluence, expansion_node, rs, vol, behavioral, setup_type, regime = row
            sym = {
                "status": sig_type or "",
                "composite_score": float(score or 0),
                "confluence": float(confluence or 0),
                "expansion_node": float(expansion_node or 0),
                "relative_strength": float(rs or 0),
                "volume_pressure": float(vol or 0),
                "behavioral": float(behavioral or 0),
                "bme_score": float(behavioral or 50),
                "setup_type": setup_type or "",
                "regime": regime or "",
            }
            grade = _confidence_grade(float(score or 0), sym)
            try:
                conn = _db()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scoreboard_signals
                    SET grade = %s
                    WHERE signal_id = %s
                      AND (grade IS NULL OR grade = '' OR LOWER(grade) = 'pending')
                """, (grade, sig_id))
                result["grades_repaired"] += cur.rowcount
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                result["errors"].append(f"grade repair {sig_id}: {e}")
    except Exception as e:
        result["errors"].append(f"grade repair fetch: {e}")

    # 2) Repair missing path metrics for already-graded outcome rows.
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, symbol, signal_type, signal_date,
                   entry_price, outcome_price
            FROM scoreboard_signals
            WHERE outcome_price IS NOT NULL
              AND entry_price IS NOT NULL
              AND (
                    direction_correct IS NULL
                 OR mfe_pct IS NULL
                 OR mae_pct IS NULL
                 OR outcome_window_hours IS NULL
              )
            ORDER BY signal_date ASC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        for row in rows:
            sig_id, symbol, sig_type, sig_date, entry, outcome = row
            try:
                direction_correct, mfe_pct, mae_pct = _compute_path_metrics(
                    symbol, sig_type, sig_date, float(entry), float(outcome)
                )
                conn = _db()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scoreboard_signals
                    SET direction_correct = %s,
                        mfe_pct = %s,
                        mae_pct = %s,
                        outcome_window_hours = %s
                    WHERE signal_id = %s
                      AND (
                            direction_correct IS NULL
                         OR mfe_pct IS NULL
                         OR mae_pct IS NULL
                         OR outcome_window_hours IS NULL
                      )
                """, (
                    direction_correct, mfe_pct, mae_pct,
                    SCOREBOARD_OUTCOME_HOURS, sig_id,
                ))
                result["path_metrics_repaired"] += cur.rowcount
                conn.commit()
                cur.close()
                conn.close()
                time.sleep(0.05)
            except Exception as e:
                result["errors"].append(f"path repair {sig_id}: {e}")
    except Exception as e:
        result["errors"].append(f"path repair fetch: {e}")


    # 3) Backfill agreement metrics for existing rows using stored
    # composite_score and behavioral score as the deep intelligence proxy.
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("""
            SELECT signal_id, composite_score, behavioral
            FROM scoreboard_signals
            WHERE agreement_score IS NULL
               OR intelligence_delta IS NULL
               OR deep_score IS NULL
               OR agreement_bucket IS NULL
            ORDER BY signal_date ASC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        for row in rows:
            sig_id, composite_score, behavioral = row
            sym = {
                "composite_score": float(composite_score or 0),
                "behavioral": float(behavioral or composite_score or 0),
            }
            deep_score, intelligence_delta, agreement_score, agreement_bucket = _derive_intelligence_metrics(sym)
            try:
                conn = _db()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scoreboard_signals
                    SET deep_score = %s,
                        intelligence_delta = %s,
                        agreement_score = %s,
                        agreement_bucket = %s
                    WHERE signal_id = %s
                      AND (
                            agreement_score IS NULL
                         OR intelligence_delta IS NULL
                         OR deep_score IS NULL
                         OR agreement_bucket IS NULL
                      )
                """, (
                    deep_score, intelligence_delta,
                    agreement_score, agreement_bucket,
                    sig_id,
                ))
                result["agreement_repaired"] += cur.rowcount
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                result["errors"].append(f"agreement repair {sig_id}: {e}")
    except Exception as e:
        result["errors"].append(f"agreement repair fetch: {e}")

    log.info(
        "Scoreboard repair complete — grades:%s path_metrics:%s agreement:%s errors:%s",
        result["grades_repaired"],
        result["path_metrics_repaired"],
        result["agreement_repaired"],
        len(result["errors"]),
    )
    return result

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


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Avoid divide-by-zero while keeping scoreboard values readable."""
    try:
        return round(float(numerator or 0) / max(float(denominator or 0), 0.01), 2)
    except Exception:
        return 0.0


def get_scoreboard_stats() -> dict:
    """
    Returns confidence-based scoreboard statistics plus intelligence
    agreement validation.

    Agreement validates whether the deeper intelligence layer agrees with
    the surface radar score:
        agreement_score = 100 - abs(deep_score - composite_score)

    Buckets:
        90-100 Strong Confirmation
        80-89 Good Confirmation
        70-79 Mixed
        <70 Warning
    """
    if not DATABASE_URL:
        return {}

    try:
        _ensure_outcome_metric_columns()
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
                COUNT(*) FILTER (WHERE hit_target2 = true)        AS hit_t2_count,
                COUNT(*) FILTER (WHERE direction_correct = true)  AS direction_correct_count,
                COUNT(*) FILTER (WHERE direction_correct IS NOT NULL) AS direction_evaluated_count,
                ROUND(AVG(mfe_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 2)                                     AS avg_mfe_pct,
                ROUND(AVG(mae_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 2)                                     AS avg_mae_pct,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mae_pct IS NOT NULL
                      AND mfe_pct > mae_pct
                )                                                   AS edge_win_count,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mae_pct IS NOT NULL
                )                                                   AS edge_evaluated_count,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mfe_pct >= 1.5
                )                                                   AS tradeable_mfe_count
            FROM scoreboard_signals
        """)
        row = cur.fetchone()

        # Agreement bucket validation.
        cur.execute("""
            SELECT
                COALESCE(agreement_bucket, '<70 Warning') AS bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE outcome_price IS NOT NULL) AS evaluated,
                COUNT(*) FILTER (WHERE direction_correct = true) AS direction_correct,
                COUNT(*) FILTER (WHERE direction_correct IS NOT NULL) AS direction_evaluated,
                ROUND(AVG(mfe_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 2) AS avg_mfe_pct,
                ROUND(AVG(mae_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 2) AS avg_mae_pct,
                ROUND(AVG(outcome_pct) FILTER (
                    WHERE outcome_price IS NOT NULL
                )::numeric, 2) AS avg_outcome_pct,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mae_pct IS NOT NULL
                      AND mfe_pct > mae_pct
                ) AS edge_win_count,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mae_pct IS NOT NULL
                ) AS edge_evaluated_count,
                COUNT(*) FILTER (
                    WHERE outcome_price IS NOT NULL
                      AND mfe_pct IS NOT NULL
                      AND mfe_pct >= 1.5
                ) AS tradeable_mfe_count
            FROM scoreboard_signals
            GROUP BY COALESCE(agreement_bucket, '<70 Warning')
            ORDER BY
                CASE COALESCE(agreement_bucket, '<70 Warning')
                    WHEN '90-100 Strong Confirmation' THEN 1
                    WHEN '80-89 Good Confirmation' THEN 2
                    WHEN '70-79 Mixed' THEN 3
                    ELSE 4
                END
        """)
        bucket_rows = cur.fetchall()

        agreement_buckets = []
        for b in bucket_rows:
            (
                bucket, total_b, evaluated_b, correct_b, direction_eval_b,
                mfe_b, mae_b, avg_outcome_b,
                edge_win_b, edge_eval_b, tradeable_mfe_b
            ) = b
            mfe = float(mfe_b or 0)
            mae = float(mae_b or 0)
            direction_eval = direction_eval_b or 0
            correct = correct_b or 0
            edge_eval = edge_eval_b or 0
            edge_win = edge_win_b or 0
            tradeable_mfe = tradeable_mfe_b or 0
            agreement_buckets.append({
                "bucket": bucket,
                "total_signals": total_b or 0,
                "with_outcomes": evaluated_b or 0,
                "direction_evaluated": direction_eval,
                "direction_correct_rate": round(correct / max(direction_eval, 1) * 100, 1),
                "avg_mfe_pct": mfe,
                "avg_mae_pct": mae,
                "edge_ratio": _safe_ratio(mfe, mae),
                "avg_outcome_pct": float(avg_outcome_b or 0),
                "edge_evaluated": edge_eval,
                "edge_win_count": edge_win,
                "edge_accuracy_rate": round(edge_win / max(edge_eval, 1) * 100, 1),
                "tradeable_mfe_count": tradeable_mfe,
                "tradeable_mfe_rate": round(tradeable_mfe / max(edge_eval, 1) * 100, 1),
            })

        # Threshold validation. This lets the frontend answer:
        # "What happens if we only take agreement >= 70/80/90?"
        agreement_thresholds = []
        for threshold in (60, 70, 80, 90):
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE outcome_price IS NOT NULL) AS evaluated,
                    COUNT(*) FILTER (WHERE direction_correct = true) AS direction_correct,
                    COUNT(*) FILTER (WHERE direction_correct IS NOT NULL) AS direction_evaluated,
                    ROUND(AVG(mfe_pct) FILTER (
                        WHERE outcome_price IS NOT NULL
                    )::numeric, 2) AS avg_mfe_pct,
                    ROUND(AVG(mae_pct) FILTER (
                        WHERE outcome_price IS NOT NULL
                    )::numeric, 2) AS avg_mae_pct,
                    ROUND(AVG(outcome_pct) FILTER (
                        WHERE outcome_price IS NOT NULL
                    )::numeric, 2) AS avg_outcome_pct,
                    COUNT(*) FILTER (
                        WHERE outcome_price IS NOT NULL
                          AND mfe_pct IS NOT NULL
                          AND mae_pct IS NOT NULL
                          AND mfe_pct > mae_pct
                    ) AS edge_win_count,
                    COUNT(*) FILTER (
                        WHERE outcome_price IS NOT NULL
                          AND mfe_pct IS NOT NULL
                          AND mae_pct IS NOT NULL
                    ) AS edge_evaluated_count,
                    COUNT(*) FILTER (
                        WHERE outcome_price IS NOT NULL
                          AND mfe_pct IS NOT NULL
                          AND mfe_pct >= 1.5
                    ) AS tradeable_mfe_count
                FROM scoreboard_signals
                WHERE agreement_score >= %s
            """, (threshold,))
            tr = cur.fetchone()
            (
                total_t, evaluated_t, correct_t, direction_eval_t,
                mfe_t, mae_t, avg_outcome_t,
                edge_win_t, edge_eval_t, tradeable_mfe_t
            ) = tr
            mfe = float(mfe_t or 0)
            mae = float(mae_t or 0)
            direction_eval = direction_eval_t or 0
            correct = correct_t or 0
            edge_eval = edge_eval_t or 0
            edge_win = edge_win_t or 0
            tradeable_mfe = tradeable_mfe_t or 0
            agreement_thresholds.append({
                "threshold": threshold,
                "total_signals": total_t or 0,
                "with_outcomes": evaluated_t or 0,
                "direction_evaluated": direction_eval,
                "direction_correct_rate": round(correct / max(direction_eval, 1) * 100, 1),
                "avg_mfe_pct": mfe,
                "avg_mae_pct": mae,
                "edge_ratio": _safe_ratio(mfe, mae),
                "avg_outcome_pct": float(avg_outcome_t or 0),
                "edge_evaluated": edge_eval,
                "edge_win_count": edge_win,
                "edge_accuracy_rate": round(edge_win / max(edge_eval, 1) * 100, 1),
                "tradeable_mfe_count": tradeable_mfe,
                "tradeable_mfe_rate": round(tradeable_mfe / max(edge_eval, 1) * 100, 1),
            })

        cur.execute("""
            SELECT symbol, signal_type, signal_date, entry_price,
                   composite_score, setup_type, regime, grade,
                   outcome_pct, days_to_outcome, hit_target1, hit_target2,
                   direction_correct, mfe_pct, mae_pct,
                   deep_score, intelligence_delta, agreement_score, agreement_bucket
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
            "direction_evaluated": row[13] or 0,
            "direction_correct_rate": round((row[12] or 0) / max(row[13] or 1, 1) * 100, 1),
            "avg_mfe_pct": float(row[14] or 0),
            "avg_mae_pct": float(row[15] or 0),
            "edge_ratio": _safe_ratio(float(row[14] or 0), float(row[15] or 0)),
            "edge_evaluated": row[17] or 0,
            "edge_win_count": row[16] or 0,
            "edge_accuracy_rate": round((row[16] or 0) / max(row[17] or 1, 1) * 100, 1),
            "tradeable_mfe_count": row[18] or 0,
            "tradeable_mfe_rate": round((row[18] or 0) / max(row[17] or 1, 1) * 100, 1),
            "outcome_window_hours": SCOREBOARD_OUTCOME_HOURS,
            "agreement_buckets": agreement_buckets,
            "agreement_thresholds": agreement_thresholds,
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
                    "direction_correct": s[12],
                    "mfe_pct":     float(s[13]) if s[13] is not None else None,
                    "mae_pct":     float(s[14]) if s[14] is not None else None,
                    "deep_score":  float(s[15]) if s[15] is not None else None,
                    "intelligence_delta": float(s[16]) if s[16] is not None else None,
                    "agreement_score": float(s[17]) if s[17] is not None else None,
                    "agreement_bucket": s[18],
                }
                for s in signals
            ],
        }

    except Exception as e:
        log.warning(f"Scoreboard stats error: {e}")
        return {}
