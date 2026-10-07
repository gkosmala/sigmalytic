# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/radar_bars_check.py
---------------------------
READ-ONLY admin diagnostic: for a few symbols, compares the daily bars the
radar is holding in memory with freshly fetched bars, and the Weis state each
set produces. Nothing is written, cached, scored or alerted.

    GET /api/admin/radar-bars-check?symbols=HUM,NIQ,TRV

Why: the swing preview (fresh bars) and the radar Status (cached bars) use the
same code, so when they disagree the difference must be in the bars.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Header

try:
    from backend import weis_setup_state as wss
except Exception:  # run from inside backend/
    import weis_setup_state as wss

LOOKBACK_DAYS = 420          # same as the swing preview
MAX_SYMBOLS = 20
CLOSE_TOL = 5e-4             # relative difference that counts as "different close"


def _day(b: dict) -> str:
    return str(b.get("t", b.get("date", b.get("timestamp", ""))))[:10]


def _close(b: dict) -> Optional[float]:
    for k in ("c", "close"):
        if b.get(k) is not None:
            try:
                return float(b[k])
            except (TypeError, ValueError):
                return None
    return None


def _describe(bars: List[dict]) -> Dict[str, Any]:
    done = wss.drop_incomplete(wss._normalize(bars or []), "1Day")
    return {
        "bars": len(bars or []),
        "first": _day(bars[0]) if bars else None,
        "last": _day(bars[-1]) if bars else None,
        "last_close": _close(bars[-1]) if bars else None,
        "last_completed": _day(done[-1]) if done else None,
        "completed_bars": len(done),
    }


def _state(bars: List[dict]) -> Optional[str]:
    try:
        r = wss.evaluate_setup_state(bars)
        return f"{r.get('direction') or '-'}/{r.get('state')}"
    except Exception as exc:  # diagnostic only
        return f"error: {str(exc)[:60]}"


def compare_symbol(sym: str, radar_bars: List[dict], fresh_bars: List[dict], radar_row: Optional[dict]) -> Dict[str, Any]:
    r_by_day = {_day(b): _close(b) for b in radar_bars or []}
    f_by_day = {_day(b): _close(b) for b in fresh_bars or []}
    common = [d for d in r_by_day if d in f_by_day]
    diffs = []
    for d in common:
        a, b = r_by_day[d], f_by_day[d]
        if a and b and abs(a - b) / max(abs(b), 1e-9) > CLOSE_TOL:
            diffs.append((d, a, b))
    n_radar = len(radar_bars or [])
    return {
        "symbol": sym,
        "radar_status_now": (radar_row or {}).get("status"),
        "radar_status_direction": (radar_row or {}).get("status_direction"),
        "radar_bars": _describe(radar_bars),
        "fresh_bars": _describe(fresh_bars),
        "days_only_in_radar": sorted(set(r_by_day) - set(f_by_day))[-5:],
        "days_only_in_fresh": sorted(set(f_by_day) - set(r_by_day))[-5:],
        "common_days": len(common),
        "different_closes": len(diffs),
        "first_different_close": ({"day": diffs[0][0], "radar": diffs[0][1], "fresh": diffs[0][2]} if diffs else None),
        "state_on_radar_bars": _state(radar_bars),
        "state_on_fresh_bars": _state(fresh_bars),
        "state_on_fresh_last_same_count": _state((fresh_bars or [])[-n_radar:]) if n_radar else None,
    }


def run_check(symbols: List[str], radar_bars: Dict[str, list], cache: Dict[str, dict],
              fetch_bars: Callable) -> Dict[str, Any]:
    syms = [s.strip().upper() for s in symbols if s.strip()][:MAX_SYMBOLS]
    fresh = fetch_bars(syms, timeframe="1Day", lookback_days=LOOKBACK_DAYS) or {}
    rows = [compare_symbol(s, radar_bars.get(s) or [], fresh.get(s) or [], cache.get(s)) for s in syms]
    return {
        "rows": rows,
        "radar_cache_symbols": len(radar_bars),
        "note": ("Read-only. 'radar' = the daily bars the radar holds in memory; 'fresh' = bars fetched now "
                 "(split-adjusted, same as the swing preview). Last-5 day lists show where the two sets differ."),
    }


def _admin_dependency():
    try:
        from backend.main import require_admin
    except Exception:  # pragma: no cover
        from main import require_admin
    return require_admin


def _admin(authorization: str = Header(default="")) -> str:
    return _admin_dependency()(authorization)


radar_bars_check_router = APIRouter(prefix="/api/admin", tags=["admin"])


@radar_bars_check_router.get("/radar-bars-check")
def radar_bars_check(symbols: str = "", _admin_email: str = Depends(_admin)):
    try:
        from backend import radar_service as rsvc
    except Exception:  # pragma: no cover
        import radar_service as rsvc
    syms = [s for s in symbols.split(",") if s.strip()]
    if not syms:
        return {"rows": [], "note": "Pass ?symbols=AAA,BBB"}
    return run_check(syms, rsvc._historical_bars, rsvc.RADAR_CACHE, rsvc.fetch_bars_multi)
