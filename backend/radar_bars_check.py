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

LOOKBACK_DAYS = 420          # minimum; raised with the bar count
MAX_SYMBOLS = 20
RADAR_BARS = 289             # fallback only: the real window is the user's radar bar count setting
CLOSE_TOL = 5e-4             # relative difference that counts as "different close"


def current_bars() -> int:
    try:
        try:
            from backend.radar_settings import get_bar_count
        except Exception:
            from radar_settings import get_bar_count
        return get_bar_count(force=True)
    except Exception:
        return RADAR_BARS


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


def _used_comparison(radar_used: Optional[dict], fresh_bars: List[dict]) -> Dict[str, Any]:
    """Compare what the worker used (count, first/last date, last 10 closes) with
    the fresh completed bars cut to the radar's window."""
    done = wss.drop_incomplete(wss._normalize(fresh_bars or []), "1Day")[-current_bars():]
    f = {"count": len(done), "first": _day(done[0]) if done else None, "last": _day(done[-1]) if done else None}
    if not radar_used:
        return {"radar_used": None, "fresh_window": f, "tail_differences": None, "same_window": None}
    f_close = {_day(b): _close(b) for b in done}
    r_tail = {e[0]: (e[4] if len(e) >= 5 else e[-1]) for e in (radar_used.get("tail") or [])}
    diffs = []
    for d, c in r_tail.items():
        fc = f_close.get(d)
        if fc is None:
            diffs.append({"day": d, "radar": c, "fresh": None})
        elif c is None or abs(c - fc) / max(abs(fc), 1e-9) > CLOSE_TOL:
            diffs.append({"day": d, "radar": c, "fresh": fc})
    f_tail_days = [_day(b) for b in done[-10:]]
    for d in f_tail_days:
        if d not in r_tail:
            diffs.append({"day": d, "radar": None, "fresh": f_close.get(d)})
    same = (radar_used.get("count") == f["count"] and radar_used.get("first") == f["first"]
            and radar_used.get("last") == f["last"] and not diffs)
    return {"radar_used": {k: radar_used.get(k) for k in ("count", "first", "last")},
            "fresh_window": f, "tail_differences": diffs, "same_window": same}


def _with_radar_tail(fresh_bars: List[dict], radar_used: Optional[dict]) -> Optional[List[dict]]:
    """Fresh completed bars (radar window) with the bars the worker recorded swapped in
    for the same dates. None when the worker recorded no full bars."""
    tail = (radar_used or {}).get("tail") or []
    if not tail or len(tail[0]) < 6:
        return None
    done = wss.drop_incomplete(wss._normalize(fresh_bars or []), "1Day")[-current_bars():]
    swap = {e[0]: {"t": e[0], "o": e[1], "h": e[2], "l": e[3], "c": e[4], "v": e[5]} for e in tail}
    return [swap.get(_day(b), b) for b in done]


def supabase_rows(symbols: List[str], since: str = "2026-10-05") -> Dict[str, List[dict]]:
    """What the Supabase daily_bars copy holds for these symbols from `since` on
    (date, close, updated_at). Empty dict when Supabase is not configured."""
    try:
        import requests
        try:
            from backend.supabase_bars import _get_client, _headers
        except Exception:  # pragma: no cover
            from supabase_bars import _get_client, _headers
        url, key = _get_client()
        if not url:
            return {}
        r = requests.get(
            f"{url}/rest/v1/daily_bars", headers=_headers(key), timeout=30,
            params={"select": "symbol,date,close,updated_at", "symbol": f"in.({','.join(symbols)})",
                    "date": f"gte.{since}", "order": "symbol.asc,date.asc"})
        out: Dict[str, List[dict]] = {}
        for row in (r.json() if r.ok else []):
            out.setdefault(row["symbol"], []).append(
                {"date": row.get("date"), "close": row.get("close"), "updated_at": row.get("updated_at")})
        return out
    except Exception:
        return {}


def redis_copy_info(redis_client) -> Dict[str, Any]:
    """Age and size of the restart-safe Redis copy of the bars, without loading it.
    The key is written with a 24 hour life, so age = 24h minus time left."""
    try:
        if redis_client is None:
            return {"present": False, "reason": "no redis client"}
        ttl = redis_client.ttl("historical_bars:v1")
        if ttl is None or ttl < 0:
            return {"present": False, "ttl": ttl}
        return {"present": True, "ttl_seconds": ttl, "age_hours": round((86400 - ttl) / 3600, 2),
                "bytes": redis_client.strlen("historical_bars:v1")}
    except Exception as exc:
        return {"present": None, "error": str(exc)[:80]}


def compare_symbol(sym: str, radar_bars: List[dict], fresh_bars: List[dict], radar_row: Optional[dict],
                   sb_rows: Optional[List[dict]] = None) -> Dict[str, Any]:
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
        "state_on_fresh_last_setting": _state((fresh_bars or [])[-current_bars():]),
        **_used_comparison((radar_row or {}).get("status_bars"), fresh_bars),
        "state_on_fresh_with_radar_tail": (_state(sub) if (sub := _with_radar_tail(
            fresh_bars, (radar_row or {}).get("status_bars"))) is not None else None),
        "radar_bars_source": (radar_row or {}).get("status_bars_source"),
        "supabase_rows": sb_rows,
    }


def run_check(symbols: List[str], radar_bars: Dict[str, list], cache: Dict[str, dict],
              fetch_bars: Callable, redis_client=None, sb_fetch: Callable = None) -> Dict[str, Any]:
    syms = [s.strip().upper() for s in symbols if s.strip()][:MAX_SYMBOLS]
    n_set = current_bars()
    fresh = fetch_bars(syms, timeframe="1Day", lookback_days=max(LOOKBACK_DAYS, int(n_set * 1.7))) or {}
    sb = (sb_fetch or supabase_rows)(syms)
    rows = [compare_symbol(s, radar_bars.get(s) or [], fresh.get(s) or [], cache.get(s), sb.get(s)) for s in syms]
    return {
        "rows": rows,
        "redis_copy": redis_copy_info(redis_client),
        "radar_cache_symbols": len(radar_bars),
        "radar_bar_count_setting": n_set,
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
    try:
        from backend.snapshot_service import _load_radar_cache_for_admin_report
    except Exception:  # pragma: no cover
        from snapshot_service import _load_radar_cache_for_admin_report
    # The scan runs in a separate worker, so the web process holds no radar bars;
    # radar status comes from the shared Redis cache (as in the swing preview).
    return run_check(syms, rsvc._historical_bars, _load_radar_cache_for_admin_report(), rsvc.fetch_bars_multi,
                     redis_client=getattr(rsvc, "_redis_client", None))
