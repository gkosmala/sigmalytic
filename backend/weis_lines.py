# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Weis Lines Engine
================================================================================
File    : weis_lines.py
Version : 0.1.0 (pivot detection only -- first increment)
Date    : 2026-10-03

PURPOSE
-------
Automated chart line-drawing, inspired by the line-construction techniques
described in Chapter 3 ("The Story of the Lines") of David Weis's "Trades
About to Happen" -- horizontal support/resistance (axis lines), trendlines,
channels, reverse channels, apexes, and confluence. The techniques themselves
(connecting swing points, drawing parallels, triangulating converging lines)
are generic, decades-old technical-analysis constructions -- not reproduced
from the book's text.

THIS INCREMENT: pivot detection only (Step 1 of the full design). Horizontal
axis lines, trendlines, channels, and apex detection are later increments,
built on top of the pivot list this module produces.

PIVOT SOURCES (in priority order)
----------------------------------
1. Three-bar reversal (fast path, no confirmation lag beyond the pattern
   itself). Reuses the exact match rule from
   backend/weis_wave.py::detect_three_bar_reversal() -- same bar-1/bar-2/
   bar-3 shape-and-volume conditions -- but scans the ENTIRE bar series
   instead of only the last 5 bars, since line-drawing needs every
   historical pivot, not just "did one just happen." weis_wave.py itself is
   NOT modified; this is a deliberate, separate implementation of the same
   rule so nothing already in production changes.
2. N-bar fractal (fallback, catches real pivots the 3-bar pattern's strict
   shape/volume conditions miss -- e.g. slower rounding tops, or a reversal
   bar with lighter volume). NOT YET IMPLEMENTED in this increment -- added
   once 3-bar-reversal pivots are validated against real charts.

CONFIGURATION
--------------
Per-timeframe-adjustable via the existing admin-only Weis Radar settings
panel (same pattern as RADAR_CONFIG_DEFAULTS / _load_radar_config() in
backend/weis_radar_scan.py). This increment does not yet wire the config
plumbing -- PIVOT_WINDOW_DEFAULTS below are placeholders for the fractal
fallback once it's added; the 3-bar-reversal path has no window parameter
to configure (its "strong bar" threshold self-scales off recent average
range, same as detect_three_bar_reversal()).

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Placeholder for the N-bar fractal fallback (not yet implemented). Kept here
# so the config shape is visible and stable once that increment lands.
PIVOT_WINDOW_DEFAULTS: Dict[str, int] = {
    "1Min": 3, "5Min": 3, "15Min": 4, "30Min": 4,
    "1Hour": 4, "2Hour": 4, "4Hour": 5,
    "1Day": 5, "1Week": 3,
}


@dataclass
class Pivot:
    kind: str           # "swing_high" | "swing_low"
    price: float        # the extreme price of the pivot (bar 1's high/low)
    bar_index: int       # index into the bars list of bar 1 (the extreme bar)
    confirmed_index: int  # index of bar 3 (the bar whose close confirms it)
    confirmed_time: str   # bar 3's own timestamp ("t" field), confirmation time
    source: str          # "three_bar_reversal" (only source in this increment)


def _num(bar: dict, key: str) -> Optional[float]:
    try:
        value = float(bar.get(key, 0))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def scan_three_bar_reversal_pivots(bars: List[dict]) -> List[Pivot]:
    """
    Walk the full bar series and return every historical three-bar-reversal
    pivot, using the identical shape-and-volume rule as
    backend/weis_wave.py::detect_three_bar_reversal():

        Bar 1: strong directional bar (range >= 80% of the trailing
               5-bar average range)
        Bar 2: inside/narrow bar (range <= 60% of bar 1's range)
        Bar 3: strong opposite bar, closing through bar 1's open, with
               volume >= 80% of bar 1's volume

    Unlike detect_three_bar_reversal() (which only scans the last 5 bars
    and returns the single most recent match, for a "did one just happen"
    check), this scans every 3-bar window in the series and returns ALL
    matches, each confirmed at its own bar 3 -- no symmetric look-ahead
    lag, unlike an N-bar fractal.

    The trailing average-range window (5 bars, ending at bar 3) is
    recomputed at each candidate window so results are reproducible
    anywhere in history, not just against the tail of the series.

    A swing HIGH pivot (price = bar 1's high) comes from a BEARISH match
    (topping: strong up, indecision, strong down through bar 1's open).
    A swing LOW pivot (price = bar 1's low) comes from a BULLISH match
    (bottoming: strong down, indecision, strong up through bar 1's open).
    These map directly onto the "invalidation" levels
    detect_three_bar_reversal() already reports (h1 for bearish, l1 for
    bullish) -- the extreme of bar 1 IS the swing point.

    Returns pivots in chronological order (oldest first).
    """
    pivots: List[Pivot] = []
    if not bars or len(bars) < 7:  # need 5 bars of range history + the 3-bar window
        return pivots

    for i in range(1, len(bars) - 1):
        b1, b2, b3 = bars[i - 1], bars[i], bars[i + 1]

        o1, c1, h1, l1, v1 = (_num(b1, k) for k in ("o", "c", "h", "l", "v"))
        o2, c2, h2, l2 = (_num(b2, k) for k in ("o", "c", "h", "l"))
        o3, c3, h3, l3, v3 = (_num(b3, k) for k in ("o", "c", "h", "l", "v"))
        if any(v is None for v in (o1, c1, h1, l1, v1, o2, c2, h2, l2, o3, c3, h3, l3, v3)):
            continue

        # Trailing 5-bar average range ending at bar 3, same window shape as
        # detect_three_bar_reversal()'s own avg_range (there: last 5 bars of
        # whatever slice was passed in; here: the 5 bars ending at bar 3, so
        # the rule is evaluated identically at every point in history).
        range_window = bars[max(0, i + 1 - 5): i + 2]
        if len(range_window) < 5:
            continue
        ranges = []
        valid_window = True
        for rb in range_window:
            rh, rl = _num(rb, "h"), _num(rb, "l")
            if rh is None or rl is None:
                valid_window = False
                break
            ranges.append(rh - rl)
        if not valid_window:
            continue
        avg_range = sum(ranges) / len(ranges)
        if avg_range <= 0:
            continue

        range1, range2 = h1 - l1, h2 - l2

        # ── BEARISH 3-Bar Reversal -> swing HIGH at bar 1's high ──────────
        bar1_strong_up = c1 > o1 and range1 >= avg_range * 0.8
        bar2_indecision = range2 <= range1 * 0.6
        bar3_strong_down = c3 < o3 and c3 < o1
        bar3_volume_ok = v3 >= v1 * 0.8
        if bar1_strong_up and bar2_indecision and bar3_strong_down and bar3_volume_ok:
            pivots.append(Pivot(
                kind="swing_high", price=h1, bar_index=i - 1,
                confirmed_index=i + 1, confirmed_time=str(b3.get("t") or ""),
                source="three_bar_reversal",
            ))
            continue  # a window is either a bearish or bullish match, not both

        # ── BULLISH 3-Bar Reversal -> swing LOW at bar 1's low ─────────────
        bar1_strong_down = c1 < o1 and range1 >= avg_range * 0.8
        bar3_strong_up = c3 > o3 and c3 > o1
        bar3_volume_ok2 = v3 >= v1 * 0.8
        if bar1_strong_down and bar2_indecision and bar3_strong_up and bar3_volume_ok2:
            pivots.append(Pivot(
                kind="swing_low", price=l1, bar_index=i - 1,
                confirmed_index=i + 1, confirmed_time=str(b3.get("t") or ""),
                source="three_bar_reversal",
            ))

    return pivots


def pivot_records(pivots: List[Pivot]) -> List[Dict[str, Any]]:
    """JSON-serializable form, same convention as weis_radar_scan.py's own
    candidate_records() helper."""
    return [
        {
            "kind": p.kind, "price": round(p.price, 4),
            "bar_index": p.bar_index, "confirmed_index": p.confirmed_index,
            "confirmed_time": p.confirmed_time, "source": p.source,
        }
        for p in pivots
    ]
