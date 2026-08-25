"""
ADDED (2026-08-24): Weis Radar -- scans the full Russell 1000 for
Spring, Upthrust, Breakout, and Breakdown patterns, using the real,
already-fixed WyckoffVerdictEngine (backend/research_engine/
wyckoff_verdict_engine.py). Genuinely separate from the existing
"Radar" tab's own composite scoring (get_radar_scores in
radar_service.py) -- deliberately additive, not integrated into that
system, so this carries zero risk to the existing, already-working
Radar/Market Radio/report pipeline.

Same architecture already proven for report generation earlier this
session: runs entirely on the isolated worker process (never the web
backend), on a daily schedule, results cached in Redis for the
frontend to read. Reuses fetch_bars_batch's own established batching
(not 1,023 individual API calls) and the exact same raw-bar-to-
DataFrame conversion already used by the live, single-symbol
wyckoff-verdict endpoint (backend/main.py's radar_symbol_wyckoff_verdict).
"""
import json
from datetime import datetime, timezone

import pandas as pd

WEIS_RADAR_RESULTS_KEY = "weis_radar:results"
WEIS_RADAR_JOB_KEY = "weis_radar:job_status"
WEIS_RADAR_JOB_TTL_SECONDS = 3600


def _bars_to_dataframe(raw_bars: list) -> pd.DataFrame:
    """
    Same conversion already used by the live single-symbol
    wyckoff-verdict endpoint -- Alpaca's own o/h/l/c/v field names.

    FIX (2026-08-24): confirmed a real bug -- previously dropped
    Alpaca's own timestamp field ("t") entirely, so the resulting
    DataFrame had only a default 0,1,2... integer index. _scan_for_
    crossing()'s "date" field then read that raw row number (e.g.
    "236") instead of an actual date -- exactly the "crossed 236"
    output reported live. Now keeps the real date, sliced to just the
    calendar date portion of Alpaca's ISO timestamp.
    """
    return pd.DataFrame([
        {"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"],
         "date": str(b.get("t", ""))[:10]}
        for b in raw_bars
    ])


def scan_symbol_for_weis_patterns(engine, df: pd.DataFrame) -> list:
    """
    Runs all four pattern checks on one symbol's already-prepared
    DataFrame, returning a list of hit dicts (empty if none). Mirrors
    the exact logic already validated in the standalone Weis scan
    tool this session -- same thresholds (spring/upthrust >= 70),
    same well-defined-level requirement.
    """
    if len(df) < 60:
        return []
    df = engine._prepare(df)
    idx = len(df) - 1

    support = engine._find_well_defined_level(df, idx, is_support=True)
    resistance = engine._find_well_defined_level(df, idx, is_support=False)
    spring = engine._score_spring(df, idx, support)
    upthrust = engine._score_upthrust(df, idx, resistance, trend_context="neutral")
    breakout = engine.detect_breakout(df, idx, resistance)
    breakdown = engine.detect_breakdown(df, idx, support)

    hits = []
    price = float(df["close"].iloc[idx])
    if spring >= 70:
        hits.append({"type": "SPRING", "score": spring, "level": round(float(support), 2)})
    if upthrust >= 70:
        hits.append({"type": "UPTHRUST", "score": upthrust, "level": round(float(resistance), 2)})
    if breakout:
        hits.append({"type": "BREAKOUT", **breakout})
    if breakdown:
        hits.append({"type": "BREAKDOWN", **breakdown})

    return [{"price": round(price, 2), **h} for h in hits] if hits else []


def run_weis_radar_scan() -> dict:
    """
    The actual full-universe scan -- called from the worker's own
    scheduled job, never from the web backend. Real, meaningful
    compute cost (1,023 symbols), same lesson as the report generation
    fix earlier this session: this must never run on the web-facing
    process's memory budget.
    """
    from backend.radar_service import load_russell1000, fetch_bars_batch, _redis_client
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine

    started_at = datetime.now(timezone.utc).isoformat()
    if _redis_client:
        try:
            _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({"status": "running", "started_at": started_at}),
                               ex=WEIS_RADAR_JOB_TTL_SECONDS)
        except Exception:
            pass

    engine = WyckoffVerdictEngine()
    symbols = load_russell1000()
    bars_map = fetch_bars_batch(symbols, timeframe="1Day", limit=252)

    results = []
    errors = 0
    for symbol, raw_bars in bars_map.items():
        try:
            df = _bars_to_dataframe(raw_bars)
            hits = scan_symbol_for_weis_patterns(engine, df)
            if hits:
                results.append({"symbol": symbol, "hits": hits})
        except Exception:
            errors += 1

    results.sort(key=lambda r: len(r["hits"]), reverse=True)
    payload = {
        "ok": True,
        "scanned": len(bars_map),
        "hits": len(results),
        "errors": errors,
        "results": results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if _redis_client:
        try:
            _redis_client.set(WEIS_RADAR_RESULTS_KEY, json.dumps(payload))
            _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({
                "status": "done", "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "hits": len(results), "scanned": len(bars_map), "errors": errors,
            }), ex=WEIS_RADAR_JOB_TTL_SECONDS)
        except Exception:
            pass

    return payload


def get_weis_radar_results() -> dict:
    """Read-only -- called from the web backend's own API endpoint to
    serve whatever the worker's last scan produced. Never runs the
    scan itself."""
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured"}
    try:
        raw = _redis_client.get(WEIS_RADAR_RESULTS_KEY)
        if raw is None:
            return {"ok": True, "results": [], "generated_at": None,
                     "note": "No scan has completed yet."}
        return json.loads(raw)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
