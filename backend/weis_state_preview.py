# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/weis_state_preview.py
-----------------------------
READ-ONLY admin preview of the Weis-only setup state (backend/weis_setup_state.py)
on live data. Nothing is written, cached, scored or alerted; the radar's score
and Status are untouched.

For a sample of radar symbols it fetches fresh bars, runs evaluate_setup_state,
and shows the result next to the Status the radar shows today.

    GET /api/admin/weis-state-preview?mode=swing&limit=60
    GET /api/admin/weis-state-preview?mode=day&symbols=AAPL,MSFT

    mode=swing  daily bars, trend read against the weekly trend
    mode=day    15-minute bars, trend read against the 1-hour and daily trends
                (ladders are the user's choice, see weis_setup_state.LADDERS)

Rows labeled NOT FROM WEIS in weis_setup_state (45 degree angle cutoff, price
unit, ladders) stay labeled in the output.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Header

try:
    from backend import weis_setup_state as wss
    from backend.readiness_impact import pick_sample
except Exception:  # run from inside backend/
    import weis_setup_state as wss
    from readiness_impact import pick_sample

# Calendar-day lookbacks per frame (enough completed higher-frame bars, and
# for 15-minute bars a couple of weeks of sessions).
LOOKBACK_DAYS = {"1Day": 420, "1Hour": 45, "15Min": 14}
MAX_SYMBOLS = 80


def _row(sym: str, res: Dict[str, Any], radar: Optional[dict]) -> Dict[str, Any]:
    ang = res.get("angle") or {}
    return {
        "symbol": sym,
        "state": res.get("state"),
        "direction": res.get("direction"),
        "reason": res.get("reason"),
        "flipped_from": res.get("flipped_from"),
        "line_source": res.get("line_source"),
        "line_touches": res.get("line_touches"),
        "break_time": res.get("break_time"),
        "bars_since_break": res.get("bars_since_break"),
        "close_back_time": res.get("close_back_time"),
        "stop": res.get("stop"),
        "target": res.get("target"),
        "trend": res.get("trend"),
        "trends_by_frame": res.get("trends_by_frame"),
        "angle_change_of_character": ang.get("character_change") or [],
        "last_leg_degrees": [l["degrees"] for l in (ang.get("legs") or [])[-3:]],
        "radar_status_today": (radar or {}).get("status"),
        "radar_composite_today": (radar or {}).get("composite_score"),
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"symbols": len(rows)}
    out["states"] = dict(Counter(f"{r['direction'] or '-'}/{r['state']}" for r in rows))
    out["flipped"] = sum(1 for r in rows if r.get("flipped_from"))
    out["angle_change_of_character"] = sum(1 for r in rows if r["angle_change_of_character"])
    out["vs_radar_today"] = dict(Counter(f"{r['radar_status_today']} -> {r['state']}" for r in rows))
    return out


CHUNK = 10  # fetch_bars_multi caps one request at 10,000 bars with no paging; small chunks avoid silent truncation


def _fetch_chunked(fetch_bars: Callable, symbols: List[str], timeframe: str, lookback_days: int) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for i in range(0, len(symbols), CHUNK):
        part = symbols[i:i + CHUNK]
        out.update(fetch_bars(part, timeframe=timeframe, lookback_days=lookback_days) or {})
    return out


def run_preview(cache: Dict[str, dict], symbols: Optional[List[str]], limit: int, mode: str,
                fetch_bars: Callable) -> Dict[str, Any]:
    sample = [s.strip().upper() for s in symbols] if symbols else pick_sample(list(cache.keys()), limit)
    sample = sample[:MAX_SYMBOLS]
    day = mode == "day"
    exec_tf = "15Min" if day else "1Day"
    needed = ["15Min", "1Hour", "1Day"] if day else ["1Day"]
    bars = {tf: _fetch_chunked(fetch_bars, sample, tf, LOOKBACK_DAYS[tf]) for tf in needed}
    rows, skipped = [], []
    for sym in sample:
        eb = bars[exec_tf].get(sym) or []
        if len(eb) < 30:
            skipped.append({"symbol": sym, "reason": f"{len(eb)} {exec_tf} bars"})
            continue
        htf = None
        if day:
            htf = {"1Hour": bars["1Hour"].get(sym) or [], "1Day": bars["1Day"].get(sym) or []}
        try:
            res = wss.evaluate_setup_state(eb, timeframe=exec_tf, htf_bars=htf)
        except Exception as exc:
            skipped.append({"symbol": sym, "reason": f"error: {str(exc)[:80]}"})
            continue
        rows.append(_row(sym, res, cache.get(sym)))
    rows.sort(key=lambda r: (-wss.STATE_RANK.get(r["state"], -1), r["symbol"]))
    return {
        "mode": mode,
        "ladder": wss.LADDERS["day" if day else "swing"],
        "summary": summarize(rows),
        "rows": rows,
        "skipped": skipped,
        "note": ("Read-only preview. Rows are Weis-only setup states; the 45 degree angle "
                 "cutoff, the price unit and the timeframe ladder are NOT from Weis (user/Gann/Raschke per user). "
                 "Bars are fetched fresh, split-adjusted; intraday bars are whatever the data feed returns."),
    }


def _admin_dependency():
    try:
        from backend.main import require_admin
    except Exception:  # pragma: no cover
        from main import require_admin
    return require_admin


def _admin(authorization: str = Header(default="")) -> str:
    return _admin_dependency()(authorization)


weis_state_router = APIRouter(prefix="/api/admin", tags=["admin"])


@weis_state_router.get("/weis-state-preview")
def weis_state_preview(mode: str = "swing", limit: int = 60, symbols: str = "",
                       _admin_email: str = Depends(_admin)):
    try:
        from backend import radar_service as rsvc
        from backend.snapshot_service import _load_radar_cache_for_admin_report
    except Exception:  # pragma: no cover
        import radar_service as rsvc
        from snapshot_service import _load_radar_cache_for_admin_report
    mode = "day" if mode == "day" else "swing"
    cache = _load_radar_cache_for_admin_report()
    syms = [s for s in symbols.split(",") if s.strip()] or None
    return run_preview(cache, syms, max(1, min(int(limit), MAX_SYMBOLS)), mode, rsvc.fetch_bars_multi)
