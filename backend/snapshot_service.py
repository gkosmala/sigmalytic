# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/snapshot_service.py
----------------------------
Sigmalytic Snapshot Writer + Admin Report Engine

Writes radar scores to Supabase every 5 minutes during market hours,
and a daily close snapshot at 4:15 PM ET.

Exposes /api/admin/report — private endpoint for greg.kosmala@gmail.com only.

SUPABASE TABLE REQUIRED:
    Run this SQL in Supabase SQL editor:

    CREATE TABLE IF NOT EXISTS radar_snapshots (
        id              BIGSERIAL PRIMARY KEY,
        symbol          TEXT NOT NULL,
        snapshot_time   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        composite_score NUMERIC(5,1),
        confluence      NUMERIC(5,1),
        expansion_node  NUMERIC(5,1),
        relative_strength NUMERIC(5,1),
        volume_pressure NUMERIC(5,1),
        behavioral      NUMERIC(5,1),
        status          TEXT,
        setup_type      TEXT,
        price           NUMERIC(12,2),
        change_pct      NUMERIC(6,2),
        regime          TEXT,
        is_daily_close  BOOLEAN DEFAULT FALSE,
        grade           TEXT,
        notes           TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_time
        ON radar_snapshots (symbol, snapshot_time DESC);

    CREATE INDEX IF NOT EXISTS idx_snapshots_daily_close
        ON radar_snapshots (snapshot_time DESC)
        WHERE is_daily_close = TRUE;
"""

from __future__ import annotations
import os
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Header, HTTPException

log = logging.getLogger("snapshot")

DATABASE_URL   = os.getenv("DATABASE_URL", "")
ADMIN_EMAIL    = "greg.kosmala@gmail.com"

snapshot_router = APIRouter(prefix="/api/admin", tags=["admin"])

# ── Intraday snapshot writer (every 5 min) ─────────────────────────────────

def write_intraday_snapshots(radar_cache: dict):
    """
    Write current radar scores to radar_snapshots table.
    Called by APScheduler every 5 minutes during market hours.
    """
    if not DATABASE_URL:
        log.warning("No DATABASE_URL — skipping snapshot write")
        return

    now_utc = datetime.now(timezone.utc)

    # Market hours check: 9:30 AM – 4:15 PM ET = 13:30 – 20:15 UTC
    hour_utc   = now_utc.hour
    minute_utc = now_utc.minute
    total_min  = hour_utc * 60 + minute_utc
    market_open  = 13 * 60 + 30   # 9:30 AM ET
    market_close = 20 * 60 + 15   # 4:15 PM ET

    if not (market_open <= total_min <= market_close):
        log.debug("Outside market hours — skipping intraday snapshot")
        return

    symbols = list(radar_cache.values())
    if not symbols:
        log.warning("Radar cache empty — skipping snapshot")
        return

    rows = []
    for s in symbols:
        rows.append((
            s.get("symbol"),
            now_utc,
            s.get("composite_score"),
            s.get("confluence"),
            s.get("expansion_node"),
            s.get("relative_strength"),
            s.get("volume_pressure"),
            s.get("behavioral"),
            s.get("status"),
            s.get("setup_type"),
            s.get("price"),
            s.get("change_pct"),
            s.get("regime"),
            False,   # is_daily_close
            None,    # grade — assigned at close
            None,    # notes
        ))

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        psycopg2.extras.execute_values(cur, """
            INSERT INTO radar_snapshots
            (symbol, snapshot_time, composite_score, confluence,
             expansion_node, relative_strength, volume_pressure,
             behavioral, status, setup_type, price, change_pct,
             regime, is_daily_close, grade, notes)
            VALUES %s
        """, rows)
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Wrote {len(rows)} intraday snapshots to Supabase")
    except Exception as e:
        log.warning(f"Snapshot write error: {e}")


# ── Daily close snapshot (4:15 PM ET) ─────────────────────────────────────

def write_daily_close_snapshots(radar_cache: dict):
    """
    Write end-of-day snapshots with grades.
    Called by APScheduler at 4:15 PM ET (21:15 UTC).
    """
    if not DATABASE_URL:
        return

    now_utc  = datetime.now(timezone.utc)
    symbols  = list(radar_cache.values())

    if not symbols:
        log.warning("Radar cache empty at close — skipping daily snapshot")
        return

    rows = []
    for s in symbols:
        grade = _assign_eod_grade(s)
        rows.append((
            s.get("symbol"),
            now_utc,
            s.get("composite_score"),
            s.get("confluence"),
            s.get("expansion_node"),
            s.get("relative_strength"),
            s.get("volume_pressure"),
            s.get("behavioral"),
            s.get("status"),
            s.get("setup_type"),
            s.get("price"),
            s.get("change_pct"),
            s.get("regime"),
            True,    # is_daily_close
            grade,
            f"EOD · {s.get('setup_type','')} · {s.get('regime','')}",
        ))

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        psycopg2.extras.execute_values(cur, """
            INSERT INTO radar_snapshots
            (symbol, snapshot_time, composite_score, confluence,
             expansion_node, relative_strength, volume_pressure,
             behavioral, status, setup_type, price, change_pct,
             regime, is_daily_close, grade, notes)
            VALUES %s
        """, rows)
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Wrote {len(rows)} daily close snapshots")
    except Exception as e:
        log.warning(f"Daily close snapshot write error: {e}")


def _assign_eod_grade(s: dict) -> str:
    """
    Assign letter grade based on EOD score + status.
    Mirrors the A/B/C/F grading from the manual scoreboard.
    """
    score   = s.get("composite_score", 0)
    status  = s.get("status", "")
    chg_pct = s.get("change_pct", 0)

    if status in ("Triggered", "Confirmed"):
        if chg_pct >= 2:    return "A"
        if chg_pct >= 0.5:  return "B"
        if chg_pct >= 0:    return "B-"
        return "C"

    if status == "Short Confirmed":
        if chg_pct <= -2:   return "A"
        if chg_pct <= -0.5: return "B"
        return "C"

    if status == "Failed":  return "F"

    if score >= 80:         return "A-"
    if score >= 70:         return "B+"
    if score >= 60:         return "B"
    if score >= 50:         return "C"
    return "F"


# ── Admin report builder ───────────────────────────────────────────────────

def build_admin_report(radar_cache: dict) -> dict:
    """
    Build the full admin performance report from live radar cache
    + Supabase historical snapshots.
    """
    symbols  = list(radar_cache.values())
    now_utc  = datetime.now(timezone.utc)
    today    = now_utc.date()

    # ── Live stats from cache ──────────────────────────────────────────────
    total    = len(symbols)
    armed    = sum(1 for s in symbols if s.get("status") == "Armed")
    triggered= sum(1 for s in symbols if s.get("status") in ("Triggered","Confirmed"))
    building = sum(1 for s in symbols if s.get("status") == "Building")
    avoid    = sum(1 for s in symbols if s.get("status") == "Avoid")
    short_ct = sum(1 for s in symbols if "Short" in s.get("status",""))
    avg_score= round(sum(s.get("composite_score",0) for s in symbols) / total, 1) if total else 0

    # ── Anomaly detection ──────────────────────────────────────────────────
    anomalies = _detect_anomalies(symbols)

    # ── Top performers today ───────────────────────────────────────────────
    top_scores = sorted(symbols, key=lambda x: x.get("composite_score",0), reverse=True)[:10]
    top_movers = sorted(symbols, key=lambda x: abs(x.get("change_pct",0)), reverse=True)[:10]

    # ── Regime distribution ────────────────────────────────────────────────
    regimes: Dict[str,int] = {}
    for s in symbols:
        r = s.get("regime","Unknown")
        regimes[r] = regimes.get(r, 0) + 1

    # ── Historical daily grades from Supabase ──────────────────────────────
    daily_grades = []
    accuracy_stats = {"total":0,"a_grade":0,"b_grade":0,"c_grade":0,"f_grade":0,
                      "hit_rate":0,"conf_rate":0,"miss_rate":0,"neutral_rate":0}

    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Last 30 days of daily close snapshots
            cutoff = (now_utc - timedelta(days=30)).isoformat()
            cur.execute("""
                SELECT
                    DATE(snapshot_time AT TIME ZONE 'America/New_York') as trade_date,
                    symbol, composite_score, confluence, expansion_node,
                    relative_strength, volume_pressure, behavioral,
                    status, setup_type, price, change_pct, regime, grade
                FROM radar_snapshots
                WHERE is_daily_close = TRUE
                  AND snapshot_time >= %s
                ORDER BY snapshot_time DESC
            """, (cutoff,))
            rows = cur.fetchall()

            # Build date × symbol grade grid
            dates_seen = {}
            for row in rows:
                d   = str(row["trade_date"])
                sym = row["symbol"]
                if d not in dates_seen:
                    dates_seen[d] = {}
                dates_seen[d][sym] = {
                    "grade":           row["grade"],
                    "score":           float(row["composite_score"] or 0),
                    "status":          row["status"],
                    "change_pct":      float(row["change_pct"] or 0),
                    "confluence":      float(row["confluence"] or 0),
                    "expansion_node":  float(row["expansion_node"] or 0),
                    "relative_strength": float(row["relative_strength"] or 0),
                    "volume_pressure": float(row["volume_pressure"] or 0),
                    "behavioral":      float(row["behavioral"] or 0),
                }

            daily_grades = [
                {"date": d, "symbols": symbols_dict}
                for d, symbols_dict in sorted(dates_seen.items(), reverse=True)
            ]

            # Accuracy stats from graded snapshots
            all_grades = [row["grade"] for row in rows if row["grade"]]
            if all_grades:
                total_g   = len(all_grades)
                a_count   = sum(1 for g in all_grades if g and g.startswith("A"))
                b_count   = sum(1 for g in all_grades if g and g.startswith("B"))
                c_count   = sum(1 for g in all_grades if g and g == "C")
                f_count   = sum(1 for g in all_grades if g and g == "F")
                hit_count = a_count + b_count
                accuracy_stats = {
                    "total":        total_g,
                    "a_grade":      a_count,
                    "b_grade":      b_count,
                    "c_grade":      c_count,
                    "f_grade":      f_count,
                    "hit_rate":     round(hit_count / total_g * 100, 1),
                    "conf_rate":    round(a_count   / total_g * 100, 1),
                    "miss_rate":    round(f_count   / total_g * 100, 1),
                    "neutral_rate": round(c_count   / total_g * 100, 1),
                }

            # Snapshot writer health check — last write time
            cur.execute("""
                SELECT MAX(snapshot_time) as last_write,
                       COUNT(*) FILTER (WHERE snapshot_time >= NOW() - INTERVAL '10 minutes') as recent_count
                FROM radar_snapshots
            """)
            snap_health = cur.fetchone()

            cur.close()
            conn.close()

        except Exception as e:
            log.warning(f"Admin report DB error: {e}")
            snap_health = {"last_write": None, "recent_count": 0}
    else:
        snap_health = {"last_write": None, "recent_count": 0}

    # ── Regime narrative (auto-generated) ─────────────────────────────────
    narrative = _generate_regime_narrative(symbols, regimes, armed, triggered, avg_score)

    return {
        "generated_at":   now_utc.isoformat(),
        "today":          str(today),
        "live_stats": {
            "total_symbols": total,
            "armed":         armed,
            "triggered":     triggered,
            "building":      building,
            "avoid":         avoid,
            "short":         short_ct,
            "avg_score":     avg_score,
        },
        "accuracy_stats":  accuracy_stats,
        "snapshot_health": {
            "last_write":    str(snap_health.get("last_write","—")) if snap_health else "—",
            "recent_count":  snap_health.get("recent_count", 0) if snap_health else 0,
            "status":        "✅ Active" if (snap_health and snap_health.get("recent_count",0) > 0) else "⚠️ No recent writes",
        },
        "top_scores":      [_slim(s) for s in top_scores],
        "top_movers":      [_slim(s) for s in top_movers],
        "regime_distribution": regimes,
        "narrative":       narrative,
        "anomalies":       anomalies,
        "daily_grades":    daily_grades[:14],   # last 14 days
    }


def _slim(s: dict) -> dict:
    """Return a trimmed symbol dict for API response."""
    return {
        "symbol":           s.get("symbol"),
        "price":            s.get("price"),
        "change_pct":       s.get("change_pct"),
        "composite_score":  s.get("composite_score"),
        "confluence":       s.get("confluence"),
        "expansion_node":   s.get("expansion_node"),
        "relative_strength":s.get("relative_strength"),
        "volume_pressure":  s.get("volume_pressure"),
        "behavioral":       s.get("behavioral"),
        "status":           s.get("status"),
        "setup_type":       s.get("setup_type"),
        "regime":           s.get("regime"),
        "trigger":          s.get("trigger"),
        "invalidation":     s.get("invalidation"),
        "atr":              s.get("atr"),
        "rel_volume":       s.get("rel_volume"),
    }


def _detect_anomalies(symbols: list) -> List[dict]:
    """
    Detect unusual patterns in the current scan.
    Flags things worth investigating before launch.
    """
    flags = []

    for s in symbols:
        sym   = s.get("symbol","")
        score = s.get("composite_score", 0)
        status= s.get("status","")
        chg   = s.get("change_pct", 0)
        rel_v = s.get("rel_volume", 1)
        conf  = s.get("confluence", 0)
        exp   = s.get("expansion_node", 0)
        beh   = s.get("behavioral", 0)

        # Armed but low expansion — contradictory
        if status == "Armed" and exp < 50:
            flags.append({
                "type":    "CONTRADICTION",
                "symbol":  sym,
                "message": f"{sym} is Armed but Expansion Node is low ({exp:.0f}) — review trigger logic",
                "severity":"WARN",
            })

        # High score but Avoid status
        if score >= 75 and status == "Avoid":
            flags.append({
                "type":    "SCORE_STATUS_MISMATCH",
                "symbol":  sym,
                "message": f"{sym} scores {score:.0f} but status is Avoid — check change_pct filter",
                "severity":"WARN",
            })

        # Extreme mover with low confluence
        if abs(chg) > 5 and conf < 50:
            flags.append({
                "type":    "MOVER_LOW_CONF",
                "symbol":  sym,
                "message": f"{sym} moved {chg:+.1f}% but Confluence is only {conf:.0f} — possible data issue",
                "severity":"INFO",
            })

        # Extreme relative volume spike
        if rel_v > 10:
            flags.append({
                "type":    "VOLUME_SPIKE",
                "symbol":  sym,
                "message": f"{sym} has {rel_v:.1f}x relative volume — news event or data anomaly",
                "severity":"INFO",
            })

        # Behavioral strongly contradicts confluence
        if abs(conf - beh) > 35:
            flags.append({
                "type":    "DIMENSION_DIVERGENCE",
                "symbol":  sym,
                "message": f"{sym}: Confluence={conf:.0f} vs Behavioral={beh:.0f} — large divergence",
                "severity":"INFO",
            })

    # Global flags
    symbols_with_data = [s for s in symbols if s.get("composite_score",0) > 0]
    if len(symbols_with_data) < 10:
        flags.append({
            "type":    "LOW_DATA_COUNT",
            "symbol":  "SYSTEM",
            "message": f"Only {len(symbols_with_data)} symbols scored — Alpaca data may be degraded",
            "severity":"ERROR",
        })

    return flags


def _generate_regime_narrative(symbols, regimes, armed, triggered, avg_score) -> str:
    """
    Auto-generate a plain-English market path narrative
    based on current regime distribution and score profile.
    """
    if not symbols:
        return "No data available."

    dominant = max(regimes, key=regimes.get) if regimes else "Neutral"
    total    = len(symbols)
    bull_pct = round((regimes.get("Bull Expansion",0) + regimes.get("Bull Pullback",0)) / total * 100) if total else 0
    bear_pct = round((regimes.get("Bear Expansion",0) + regimes.get("Bear Rally",0))    / total * 100) if total else 0
    comp_pct = round(regimes.get("Compression",0) / total * 100) if total else 0

    # Dominant regime narrative
    if dominant == "Bull Expansion":
        tone = "Market in active bull expansion. Leadership broad, momentum sustained."
    elif dominant == "Bull Pullback":
        tone = "Bull structure intact with controlled pullback. Watch for continuation setups."
    elif dominant == "Bear Expansion":
        tone = "Bear expansion active. Downside pressure dominant — short setups elevated."
    elif dominant == "Bear Rally":
        tone = "Bear rally underway. Counter-trend bounce in bear structure — caution on longs."
    elif dominant == "Compression":
        tone = "Market in compression. Volatility contracting — expect expansion soon."
    else:
        tone = "Neutral regime. No dominant directional bias detected."

    # Score context
    if avg_score >= 72:
        score_read = f"System-wide score of {avg_score} confirms broad setup quality."
    elif avg_score >= 60:
        score_read = f"System-wide score of {avg_score} shows moderate opportunity."
    else:
        score_read = f"System-wide score of {avg_score} — low-edge environment. Selectivity required."

    # Alert summary
    alert_read = ""
    if armed + triggered >= 5:
        alert_read = f" {armed} Armed + {triggered} Triggered setups active."
    elif armed + triggered == 0:
        alert_read = " No active armed or triggered setups."

    return (
        f"{tone} "
        f"Bull: {bull_pct}% · Bear: {bear_pct}% · Compression: {comp_pct}%. "
        f"{score_read}{alert_read}"
    )


# ── Admin API endpoint ─────────────────────────────────────────────────────

@snapshot_router.get("/report")
def get_admin_report(authorization: Optional[str] = Header(None)):
    """
    Private admin performance report.
    Only accessible when logged in as greg.kosmala@gmail.com.
    Validates via Supabase JWT.
    """
    # Validate admin access
    if not _is_admin(authorization):
        raise HTTPException(403, "Admin access required")

    try:
        from backend.radar_service import RADAR_CACHE
    except Exception:
        from radar_service import RADAR_CACHE
    report = build_admin_report(RADAR_CACHE)
    return report


@snapshot_router.get("/report/public")
def get_admin_report_dev():
    """
    Dev/local access — no auth check. Disable in production by
    checking ADMIN_KEY env var.
    """
    admin_key = os.getenv("ADMIN_KEY","")
    if admin_key:
        raise HTTPException(403, "Use /api/admin/report with auth header in production")
    try:
        from backend.radar_service import RADAR_CACHE
    except Exception:
        from radar_service import RADAR_CACHE
    return build_admin_report(RADAR_CACHE)


@snapshot_router.post("/snapshot/write-now")
def force_snapshot_write(authorization: Optional[str] = Header(None)):
    """Manually trigger a snapshot write — admin only."""
    if not _is_admin(authorization):
        raise HTTPException(403, "Admin access required")
    try:
        from backend.radar_service import RADAR_CACHE
    except Exception:
        from radar_service import RADAR_CACHE
    write_intraday_snapshots(RADAR_CACHE)
    return {"ok": True, "symbols_written": len(RADAR_CACHE)}


def _is_admin(authorization: Optional[str]) -> bool:
    """Validate that the request comes from the admin email via Supabase JWT."""
    if not authorization:
        return False

    # Allow no-auth in local dev (no DATABASE_URL)
    if not DATABASE_URL:
        return True

    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            return False

        SUPABASE_URL      = os.getenv("SUPABASE_URL","")
        SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY","")

        import requests as _req
        r = _req.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if r.status_code == 200:
            email = r.json().get("email","")
            return email == ADMIN_EMAIL
    except Exception as e:
        log.warning(f"Admin auth check failed: {e}")
    return False

