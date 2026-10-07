"""
Weis setup state for the Weis Radar scan (read-only, no new data request).

The Weis Radar page used to be driven only by the older Spring/Upthrust engine
(backend/weis_imminent.py, WyckoffVerdictEngine), which is a different rule set
from the Radar Status. This module runs the SAME Weis setup-state engine the Radar
Status uses (backend/weis_setup_state.evaluate_setup_state) on the SAME window
(the last N completed daily bars, N = the user's radar bar count setting), so a
symbol cannot read "Armed" on the Weis Radar page and "Avoid" on the Radar.

The setup state is a daily-bar rule: it is only computed when the scan timeframe
is 1Day. Any other timeframe returns no rows and says so.
"""
from collections import Counter
from typing import Any, Dict, List, Optional

try:
    from backend import weis_setup_state as wss
except Exception:  # run from inside backend/
    import weis_setup_state as wss

# Armed first, then Setting Up, Watching, Avoid. "No setup" is not listed.
STATE_ORDER = {"Armed": 0, "Setting Up": 1, "Watching": 2, "Avoid": 3}


def state_row(symbol: str, bars: List[dict], bar_count: int) -> Optional[Dict[str, Any]]:
    """Setup state for one symbol on its last `bar_count` completed daily bars.
    None when there is no setup (or not enough bars, or an error)."""
    try:
        done = wss.drop_incomplete(bars or [], "1Day")[-int(bar_count):]
        if len(done) < 30:
            return None
        res = wss.evaluate_setup_state(done, timeframe="1Day")
    except Exception:
        return None
    if not res or res.get("state") not in STATE_ORDER:
        return None
    return {
        "symbol": symbol,
        "state": res["state"],
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
    }


def build_block(rows: List[Dict[str, Any]], bar_count: int, scanned: int,
                timeframe: str) -> Dict[str, Any]:
    """The payload block the page reads. Sorted Armed, Setting Up, Watching, Avoid,
    then by symbol."""
    rows = sorted(rows, key=lambda r: (STATE_ORDER.get(r["state"], 9), r["symbol"]))
    counts = Counter(r["state"] for r in rows)
    return {
        "available": timeframe == "1Day",
        "timeframe": timeframe,
        "bar_count": int(bar_count),
        "scanned": int(scanned),
        "counts": {k: counts.get(k, 0) for k in STATE_ORDER},
        "rows": rows,
    }


def unavailable_block(timeframe: str) -> Dict[str, Any]:
    return {"available": False, "timeframe": timeframe, "bar_count": None,
            "scanned": 0, "counts": {k: 0 for k in STATE_ORDER}, "rows": []}


def by_symbol(block: Optional[dict]) -> Dict[str, Dict[str, Any]]:
    """{symbol: row} for tagging the older tables. Empty if the block is missing."""
    if not isinstance(block, dict):
        return {}
    return {r["symbol"]: r for r in (block.get("rows") or []) if r.get("symbol")}
