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

SCOPE NOTE (2026-10-03): this module holds two independent pivot sources.
Only the fractal source below feeds the line-drawing design. The three-bar-
reversal scan was built first but turned out to be too sparse to serve as a
general-purpose pivot feed (validated against a full year of AKAM bars: 2
pivots total, 0 swing highs) -- it is kept here as a candidate source for a
*different*, still-undecided feature (a backup reward/risk target for
Spring/Upthrust events whose opposite-side level fails the primary engine's
multi-touch validation), not for line-drawing. Do not wire it into Steps 2+
below.

LINE-DRAWING DESIGN (7 steps; this increment covers Step 1 only)
------------------------------------------------------------------
Step 1 -- Pivot detection (THIS INCREMENT):
    Symmetric N-bar fractal. Swing high: bar's high is the max of the N
    bars on each side. Swing low: bar's low is the min of the N bars on
    each side. Confirms N bars after the pivot bar (symmetric lag, unlike
    the three-bar-reversal source above).
Step 2 -- Horizontal axis lines: for each pivot price, count OTHER pivots
    (highs AND lows -- axis lines flip roles) within a tolerance band,
    separated by a minimum bar gap; rank by touch count x persistence.
    Generalizes _separated_touches() (backend/weis_imminent.py) but drops
    its support-only-tests-support restriction.
Step 3 -- Trendlines: fit a line through N>=2 ascending (or descending)
    pivots; reject any line a later close has decisively broken; among
    candidates sharing an anchor, prefer the most touches and best fit.
Step 4 -- Channels / reverse channels: given a validated trendline, find
    the intervening opposite-side pivot with the largest perpendicular
    offset and draw the parallel through it; try both orientations, keep
    the tighter/more-touched fit.
Step 5 -- Apex/triangle detection: a down-sloping line across recent highs
    and an up-sloping line across recent lows with a shrinking gap;
    flag "apex forming" and project the convergence point forward.
Step 6 -- Ice line: a labeling pass over Step 2's output -- the longest-
    standing, most-touched horizontal line sitting at the bottom of an
    established range. No new detection logic.
Step 7 -- Confluence: after all lines are generated, flag any price/time
    zone where >= 2 independently-built lines sit within a small
    tolerance of each other.
Steps 2-7 are not yet implemented; each is built on the previous step's
output and validated against real charts before moving on.

CONFIGURATION
--------------
Per-timeframe-adjustable via the existing admin-only Weis Radar settings
panel (same pattern as RADAR_CONFIG_DEFAULTS / _load_radar_config() in
backend/weis_radar_scan.py). This increment does not yet wire the config
plumbing -- PIVOT_WINDOW_DEFAULTS below are the N values the fractal scan
uses per timeframe, until an admin-configurable override is added.

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


def scan_fractal_pivots(bars: List[dict], *, n: Optional[int] = None,
                         timeframe: str = "1Day") -> List[Pivot]:
    """
    Step 1 of the line-drawing design: symmetric N-bar fractal pivots.

        Swing HIGH at bar i: bar i's high is the max of the N bars on
            each side (i.e. the max over bars[i-N : i+N+1]).
        Swing LOW  at bar i: bar i's low is the min of the N bars on
            each side.

    N defaults to PIVOT_WINDOW_DEFAULTS[timeframe] (falls back to 5 for an
    unrecognized timeframe) and can be overridden explicitly once the
    admin config plumbing is wired in.

    Unlike scan_three_bar_reversal_pivots(), a fractal pivot is not known
    until N bars AFTER it -- that confirmation lag is the trade-off for
    catching pivots with no particular bar-by-bar shape (a slow rounding
    top, or a sharp single-bar climax reversal like AKAM's 2026-09-25
    high, which the three-bar-reversal pattern missed entirely).

    A flat top/bottom (two or more bars tied for the window's extreme)
    only produces one pivot, at the first bar reaching that extreme --
    ties on later bars are not re-flagged, so a plateau isn't reported as
    several back-to-back pivots at the same price.

    Returns pivots in chronological order (oldest first).
    """
    window = n if n is not None else PIVOT_WINDOW_DEFAULTS.get(timeframe, 5)
    pivots: List[Pivot] = []
    if window < 1 or not bars or len(bars) < 2 * window + 1:
        return pivots

    highs = [_num(b, "h") for b in bars]
    lows = [_num(b, "l") for b in bars]

    for i in range(window, len(bars) - window):
        if highs[i] is None or lows[i] is None:
            continue
        lo, hi = i - window, i + window + 1
        high_window = highs[lo:hi]
        low_window = lows[lo:hi]
        if any(v is None for v in high_window) or any(v is None for v in low_window):
            continue

        if highs[i] == max(high_window) and high_window.index(highs[i]) == i - lo:
            confirmed = i + window
            pivots.append(Pivot(
                kind="swing_high", price=highs[i], bar_index=i,
                confirmed_index=confirmed, confirmed_time=str(bars[confirmed].get("t") or ""),
                source=f"fractal_{window}",
            ))

        if lows[i] == min(low_window) and low_window.index(lows[i]) == i - lo:
            confirmed = i + window
            pivots.append(Pivot(
                kind="swing_low", price=lows[i], bar_index=i,
                confirmed_index=confirmed, confirmed_time=str(bars[confirmed].get("t") or ""),
                source=f"fractal_{window}",
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


# Default tolerance/gap: same convention as _separated_touches() in
# backend/weis_imminent.py (0.15% price tolerance, 10-bar minimum
# separation between the first and last touch).
AXIS_LINE_TOLERANCE = 0.0015
AXIS_LINE_MIN_GAP = 10


@dataclass
class AxisLine:
    level: float               # mean price of the cluster's touches
    touch_count: int
    first_touch_index: int       # earliest pivot's bar_index
    last_touch_index: int        # latest pivot's bar_index
    first_touch_time: str
    last_touch_time: str
    touches: List[Pivot]         # the pivots making up this line, by bar_index


def find_axis_lines(pivots: List[Pivot], *, tolerance: float = AXIS_LINE_TOLERANCE,
                     min_gap: int = AXIS_LINE_MIN_GAP) -> List[AxisLine]:
    """
    Step 2 of the line-drawing design: horizontal axis lines.

    An axis line is a price level that keeps getting touched, regardless of
    which side touches it -- unlike _separated_touches() in
    backend/weis_imminent.py, which only counts a support level's lows
    against other lows (and a resistance level's highs against other
    highs), an axis line explicitly flips roles: a level that was
    resistance can later act as support, and both kinds of touch count
    toward the same line (this is the book's central point about axis
    lines -- they don't belong to one side).

    Clustering: pivots are sorted by price and grouped into a line whenever
    a pivot's price is within `tolerance` (relative) of the RUNNING MEAN of
    the cluster being built -- not just its first member -- so a line
    can't silently drift beyond `tolerance` of where it started through a
    chain of small steps.

    A cluster only becomes a published axis line if it has >= 2 touches
    AND its earliest and latest touches (by bar_index, regardless of which
    pivot kind) are at least `min_gap` bars apart -- the same two-touches-
    separated-in-time requirement as _separated_touches(), generalized to
    mixed swing-high/swing-low touches.

    Returns axis lines sorted by touch_count desc, then persistence
    (last_touch_index - first_touch_index) desc -- the book's "rank by how
    often and how long a level has held."
    """
    if not pivots:
        return []

    ordered = sorted(pivots, key=lambda p: p.price)
    clusters: List[List[Pivot]] = []
    current: List[Pivot] = [ordered[0]]
    current_mean = ordered[0].price

    for p in ordered[1:]:
        if current_mean > 0 and abs(p.price / current_mean - 1) <= tolerance:
            current.append(p)
            current_mean = sum(c.price for c in current) / len(current)
        else:
            clusters.append(current)
            current = [p]
            current_mean = p.price
    clusters.append(current)

    lines: List[AxisLine] = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        by_time = sorted(cluster, key=lambda p: p.bar_index)
        first, last = by_time[0], by_time[-1]
        if last.bar_index - first.bar_index < min_gap:
            continue
        level = sum(c.price for c in cluster) / len(cluster)
        lines.append(AxisLine(
            level=level, touch_count=len(cluster),
            first_touch_index=first.bar_index, last_touch_index=last.bar_index,
            first_touch_time=first.confirmed_time, last_touch_time=last.confirmed_time,
            touches=by_time,
        ))

    lines.sort(key=lambda l: (l.touch_count, l.last_touch_index - l.first_touch_index),
               reverse=True)
    return lines


def axis_line_records(lines: List[AxisLine]) -> List[Dict[str, Any]]:
    """JSON-serializable form of find_axis_lines() output."""
    return [
        {
            "level": round(l.level, 4), "touch_count": l.touch_count,
            "first_touch_index": l.first_touch_index, "last_touch_index": l.last_touch_index,
            "first_touch_time": l.first_touch_time, "last_touch_time": l.last_touch_time,
            "touches": pivot_records(l.touches),
        }
        for l in lines
    ]


# Default break tolerance for trendlines: how far a close can pierce the
# line, relative to the line's value at that bar, before the line is
# considered decisively broken rather than just tested. Looser than
# AXIS_LINE_TOLERANCE on purpose -- a horizontal level is "touched or not,"
# but a sloped trendline is probed by wicks constantly and should only be
# discarded on a real close-through, not noise.
TRENDLINE_BREAK_TOLERANCE = 0.003
TRENDLINE_MIN_BAR_GAP = 5


@dataclass
class Trendline:
    kind: str                  # "swing_low" (ascending/support) | "swing_high" (descending/resistance)
    slope: float                # price change per bar
    intercept: float             # price at bar_index == 0
    anchor_start: Pivot
    anchor_end: Pivot
    touches: List[Pivot]         # all same-kind pivots lying on the line between the anchors (incl. the anchors)
    fit: float                   # mean relative deviation of touches from the line (lower = tighter)

    def value_at(self, bar_index: int) -> float:
        return self.slope * bar_index + self.intercept


def find_trendlines(pivots: List[Pivot], bars: List[dict], *, kind: str,
                     tolerance: float = AXIS_LINE_TOLERANCE,
                     break_tolerance: float = TRENDLINE_BREAK_TOLERANCE,
                     min_bar_gap: int = TRENDLINE_MIN_BAR_GAP) -> List[Trendline]:
    """
    Step 3 of the line-drawing design: trendlines.

    kind="swing_low"  -> ascending support trendlines, built by connecting
        swing lows that rise over time.
    kind="swing_high" -> descending resistance trendlines, built by
        connecting swing highs that fall over time.

    For every ordered pair of same-kind pivots (p1 earlier, p2 later, at
    least `min_bar_gap` bars apart) whose slope matches the requested
    direction, a candidate line is fit through them and extended across
    the WHOLE bar series (not just between the anchors): if any bar's
    close pierces the line by more than `break_tolerance` (relative), the
    candidate is rejected outright -- "a later close has decisively broken
    it" invalidates the line everywhere, not just going forward.

    Among surviving candidates that share the same starting anchor (p1),
    only the single best one is kept -- ranked by touch count, then by
    tightest fit -- which is the algorithmic form of "skip the meaningless
    intervening point": if connecting p1 to a FARTHER point p3 (skipping
    an intervening pivot p2) picks up more touches or fits tighter than
    p1-to-p2, p1-to-p3 wins and p2 is treated as noise rather than an
    anchor.

    "Touches" counts every same-kind pivot between the two anchors
    (inclusive) whose price sits within `tolerance` (relative) of the
    line's value at that pivot's bar index -- not just the two anchors
    themselves.

    Returns trendlines sorted by touch_count desc, then fit (tighter
    first).
    """
    same_kind = sorted((p for p in pivots if p.kind == kind), key=lambda p: p.bar_index)
    n = len(same_kind)
    if n < 2 or not bars:
        return []

    want_ascending = kind == "swing_low"
    candidates = []

    for i in range(n):
        p1 = same_kind[i]
        for j in range(i + 1, n):
            p2 = same_kind[j]
            span = p2.bar_index - p1.bar_index
            if span < min_bar_gap:
                continue
            slope = (p2.price - p1.price) / span
            if want_ascending and slope <= 0:
                continue
            if not want_ascending and slope >= 0:
                continue
            intercept = p1.price - slope * p1.bar_index

            broken = False
            for idx in range(p1.bar_index, len(bars)):
                close = _num(bars[idx], "c")
                if close is None:
                    continue
                line_val = slope * idx + intercept
                if line_val <= 0:
                    continue
                if want_ascending and close < line_val * (1 - break_tolerance):
                    broken = True
                    break
                if not want_ascending and close > line_val * (1 + break_tolerance):
                    broken = True
                    break
            if broken:
                continue

            touches = []
            for p in same_kind:
                if p.bar_index < p1.bar_index or p.bar_index > p2.bar_index:
                    continue
                line_val = slope * p.bar_index + intercept
                if line_val > 0 and abs(p.price / line_val - 1) <= tolerance:
                    touches.append(p)
            if len(touches) < 2:
                continue
            deviations = [abs(t.price / (slope * t.bar_index + intercept) - 1) for t in touches]
            fit = sum(deviations) / len(deviations)
            candidates.append(Trendline(
                kind=kind, slope=slope, intercept=intercept,
                anchor_start=p1, anchor_end=p2, touches=touches, fit=fit,
            ))

    # "Skip the meaningless intervening point": among candidates sharing a
    # start anchor, keep only the one with the most touches / tightest fit.
    best_by_start: Dict[int, Trendline] = {}
    for c in candidates:
        key = c.anchor_start.bar_index
        incumbent = best_by_start.get(key)
        if incumbent is None or (len(c.touches), -c.fit) > (len(incumbent.touches), -incumbent.fit):
            best_by_start[key] = c

    trendlines = list(best_by_start.values())
    trendlines.sort(key=lambda t: (len(t.touches), -t.fit), reverse=True)
    return trendlines


def trendline_records(trendlines: List[Trendline]) -> List[Dict[str, Any]]:
    """JSON-serializable form of find_trendlines() output."""
    return [
        {
            "kind": t.kind, "slope": round(t.slope, 6), "intercept": round(t.intercept, 4),
            "anchor_start": pivot_records([t.anchor_start])[0],
            "anchor_end": pivot_records([t.anchor_end])[0],
            "touch_count": len(t.touches), "fit": round(t.fit, 6),
            "touches": pivot_records(t.touches),
        }
        for t in trendlines
    ]


@dataclass
class Channel:
    trendline: Trendline          # the base support/resistance line
    orientation: str                # "normal" | "reverse" -- see find_channel() note
    parallel_slope: float
    parallel_intercept: float
    anchor_pivot: Pivot             # the opposite-kind pivot the parallel line passes through
    touch_count: int                 # other opposite-kind pivots (between the anchors) lying on the parallel
    fit: float

    def value_at(self, bar_index: int) -> float:
        return self.parallel_slope * bar_index + self.parallel_intercept


def find_channel(trendline: Trendline, pivots: List[Pivot], *,
                  tolerance: float = AXIS_LINE_TOLERANCE) -> Optional[Channel]:
    """
    Step 4 of the line-drawing design: channel for a single validated
    trendline.

    IMPLEMENTATION NOTE: the book distinguishes a "channel" from a "reverse
    trend channel" but doesn't reduce either to a formula -- this is a
    pragmatic, explicit interpretation of the user's spec ("find the
    intervening pivot on the opposite side with the largest perpendicular
    offset ... try both orientations ... keep whichever gives a tighter,
    more-touched fit"), not a claim that this is Weis's own algorithm:

        normal  -> the parallel line passes through whichever opposite-
                   kind pivot (between the trendline's two anchors) has
                   the LARGEST offset from the trendline -- the widest
                   reasonable channel.
        reverse -> the parallel passes through whichever opposite-kind
                   pivot has the SMALLEST (but still correctly-signed)
                   offset -- a tighter inner line, which tends to fit
                   better on a very steep trendline where the "wide"
                   choice overshoots every other opposite-kind pivot.

    Both parallels share the trendline's slope. Whichever orientation
    picks up more touches from the OTHER opposite-kind pivots in range
    (or, tied, the tighter fit) is returned; if only one opposite-kind
    pivot exists in range, there's nothing to choose between and that one
    is used for both, returned as "normal".

    Returns None if no opposite-kind pivot exists between the trendline's
    anchors (nothing to build a channel from).
    """
    opposite_kind = "swing_high" if trendline.kind == "swing_low" else "swing_low"
    lo, hi = trendline.anchor_start.bar_index, trendline.anchor_end.bar_index
    in_range = [p for p in pivots if p.kind == opposite_kind and lo <= p.bar_index <= hi]
    if not in_range:
        return None

    # Expected offset sign: a support trendline's channel partner (highs)
    # sits ABOVE it; a resistance trendline's channel partner (lows) sits
    # BELOW it.
    expected_sign = 1 if trendline.kind == "swing_low" else -1
    offsets = [(p, p.price - trendline.value_at(p.bar_index)) for p in in_range]
    valid = [(p, o) for p, o in offsets if o * expected_sign > 0]
    if not valid:
        return None

    def evaluate(pivot: Pivot):
        intercept = trendline.intercept + (pivot.price - trendline.value_at(pivot.bar_index))
        touches = []
        for cp in in_range:
            line_val = trendline.slope * cp.bar_index + intercept
            if line_val > 0 and abs(cp.price / line_val - 1) <= tolerance:
                touches.append(cp)
        deviations = [abs(t.price / (trendline.slope * t.bar_index + intercept) - 1) for t in touches]
        fit = sum(deviations) / len(deviations) if deviations else 1.0
        return intercept, touches, fit

    widest = max(valid, key=lambda po: abs(po[1]))[0]
    tightest = min(valid, key=lambda po: abs(po[1]))[0]

    normal_intercept, normal_touches, normal_fit = evaluate(widest)
    if tightest is widest:
        return Channel(trendline=trendline, orientation="normal",
                        parallel_slope=trendline.slope, parallel_intercept=normal_intercept,
                        anchor_pivot=widest, touch_count=len(normal_touches), fit=normal_fit)

    reverse_intercept, reverse_touches, reverse_fit = evaluate(tightest)

    def score(touches, fit):
        return (len(touches), -fit)

    if score(reverse_touches, reverse_fit) > score(normal_touches, normal_fit):
        return Channel(trendline=trendline, orientation="reverse",
                        parallel_slope=trendline.slope, parallel_intercept=reverse_intercept,
                        anchor_pivot=tightest, touch_count=len(reverse_touches), fit=reverse_fit)
    return Channel(trendline=trendline, orientation="normal",
                    parallel_slope=trendline.slope, parallel_intercept=normal_intercept,
                    anchor_pivot=widest, touch_count=len(normal_touches), fit=normal_fit)


def channel_records(channels: List[Channel]) -> List[Dict[str, Any]]:
    """JSON-serializable form of find_channel() output."""
    return [
        {
            "orientation": c.orientation,
            "trendline": trendline_records([c.trendline])[0],
            "parallel_slope": round(c.parallel_slope, 6),
            "parallel_intercept": round(c.parallel_intercept, 4),
            "anchor_pivot": pivot_records([c.anchor_pivot])[0],
            "touch_count": c.touch_count, "fit": round(c.fit, 6),
        }
        for c in channels
    ]


# How close to "now" a trendline's latest touch must be to count as part of
# a currently-forming apex (not some converging-lines coincidence from
# ancient, no-longer-relevant history), and how far out a projected
# convergence can be before it's too speculative to flag.
APEX_RECENT_WINDOW = 60
APEX_MAX_BARS_AHEAD = 120


@dataclass
class Apex:
    support_trendline: Trendline       # ascending (swing_low) trendline
    resistance_trendline: Trendline     # descending (swing_high) trendline
    convergence_bar_index: float          # where the two lines meet (may be fractional)
    bars_until_convergence: float
    current_gap: float                    # resistance - support, at the last bar
    current_gap_pct: Optional[float]      # current_gap relative to the lines' midpoint price


def find_apexes(support_lines: List[Trendline], resistance_lines: List[Trendline],
                 bars: List[dict], *, recent_window: int = APEX_RECENT_WINDOW,
                 max_bars_ahead: int = APEX_MAX_BARS_AHEAD) -> List[Apex]:
    """
    Step 5 of the line-drawing design: apex / triangle detection.

    An apex is an ascending support trendline and a descending resistance
    trendline that are both still valid (unbroken) through the last bar,
    both anchored recently (at least one of the pair's last touches within
    `recent_window` bars of the end of the series -- otherwise this is
    just two old, unrelated lines that happen to converge), and whose
    projected intersection lies in the near future (0 < bars-ahead <=
    `max_bars_ahead`) rather than already behind us (already crossed) or
    implausibly far out.

    Because support rises and resistance falls, the gap between them
    (resistance value minus support value, at a given bar index) strictly
    DECREASES as the bar index increases -- "the gap is shrinking
    bar-over-bar" is a direct consequence of the slope signs, not a
    separate check -- so this function does not re-verify it bar-by-bar,
    it only confirms the two slopes actually point at each other
    (support.slope > 0 and resistance.slope < 0) and that they haven't
    already crossed as of the last bar.

    Returns apexes sorted by soonest projected convergence first.
    """
    if not bars or not support_lines or not resistance_lines:
        return []
    last_idx = len(bars) - 1
    apexes: List[Apex] = []

    for s in support_lines:
        if s.slope <= 0:
            continue
        for r in resistance_lines:
            if r.slope >= 0:
                continue
            most_recent_touch = max(s.anchor_end.bar_index, r.anchor_end.bar_index)
            if last_idx - most_recent_touch > recent_window:
                continue
            denom = s.slope - r.slope
            if denom == 0:
                continue
            convergence_bar = (r.intercept - s.intercept) / denom
            bars_ahead = convergence_bar - last_idx
            if bars_ahead <= 0 or bars_ahead > max_bars_ahead:
                continue
            support_now = s.value_at(last_idx)
            resistance_now = r.value_at(last_idx)
            gap = resistance_now - support_now
            if gap <= 0:
                continue
            mid = (support_now + resistance_now) / 2
            apexes.append(Apex(
                support_trendline=s, resistance_trendline=r,
                convergence_bar_index=convergence_bar, bars_until_convergence=bars_ahead,
                current_gap=gap, current_gap_pct=(gap / mid) if mid else None,
            ))

    apexes.sort(key=lambda a: a.bars_until_convergence)
    return apexes


def apex_records(apexes: List[Apex]) -> List[Dict[str, Any]]:
    """JSON-serializable form of find_apexes() output."""
    return [
        {
            "support_trendline": trendline_records([a.support_trendline])[0],
            "resistance_trendline": trendline_records([a.resistance_trendline])[0],
            "convergence_bar_index": round(a.convergence_bar_index, 2),
            "bars_until_convergence": round(a.bars_until_convergence, 2),
            "current_gap": round(a.current_gap, 4),
            "current_gap_pct": round(a.current_gap_pct, 6) if a.current_gap_pct is not None else None,
        }
        for a in apexes
    ]


# How much of the overall pivot price range counts as "the bottom" for ice
# line eligibility (bottom 33% of the low-to-high pivot span, by default).
ICE_LINE_BOTTOM_FRACTION = 0.33


def label_ice_line(axis_lines: List[AxisLine], pivots: List[Pivot], *,
                    bottom_fraction: float = ICE_LINE_BOTTOM_FRACTION) -> Optional[AxisLine]:
    """
    Step 6 of the line-drawing design: ice line.

    A labeling pass over Step 2's output, not new detection logic: the ice
    line is simply the best-ranked axis line (find_axis_lines() already
    sorts by touch_count desc, then persistence desc) whose level falls in
    the bottom `bottom_fraction` of the overall price range spanned by all
    pivots -- the book's "a long-standing floor at the bottom of the
    range."

    What counts as "the range" is itself an approximation here: the full
    low-to-high span of every pivot price in the series, not a specific
    detected trading range (this module has no range-detection step of its
    own). On a strongly trending series this bottom band may just mean
    "the oldest, lowest prices," not a current consolidation floor --
    treat this as a first-pass heuristic, not a claim that a trading range
    is actually in effect.

    Returns the single AxisLine to label as the ice line, or None if no
    axis line qualifies (or there are no axis lines / pivots at all).
    """
    if not axis_lines or not pivots:
        return None
    prices = [p.price for p in pivots]
    lo, hi = min(prices), max(prices)
    if hi <= lo:
        return None
    threshold = lo + bottom_fraction * (hi - lo)
    candidates = [line for line in axis_lines if line.level <= threshold]
    return candidates[0] if candidates else None


# Default tolerance for deciding two lines occupy "the same" price at a
# given bar -- same convention as the other steps (0.15% relative).
CONFLUENCE_TOLERANCE = AXIS_LINE_TOLERANCE


@dataclass
class ConfluenceZone:
    bar_index: int
    price: float                 # mean price of the converging lines at bar_index
    members: List[Dict[str, Any]]  # [{"type": "axis_line"|"trendline"|"channel", "level": ..., "ref": ...}, ...]


def find_confluence(*, axis_lines: Optional[List[AxisLine]] = None,
                     trendlines: Optional[List[Trendline]] = None,
                     channels: Optional[List[Channel]] = None,
                     bar_range: Optional[range] = None,
                     tolerance: float = CONFLUENCE_TOLERANCE) -> List[ConfluenceZone]:
    """
    Step 7 of the line-drawing design: confluence.

    Takes the output of Steps 2/3/4 (axis lines, trendlines, channels --
    any subset; pass what you have) and, across `bar_range` (defaults to
    the span covered by the sloped lines' anchors, since a horizontal axis
    line has no natural bar range of its own), flags every bar where two
    or more independently-built lines sit within `tolerance` of the same
    price -- "extra significance" per the book, from lines that were never
    constructed with reference to each other.

    Each line type contributes one price-at-bar value per bar in range:
    an axis line contributes its flat `level` at every bar; a trendline or
    channel contributes `value_at(bar_index)`. Lines are only sampled
    within bar ranges they're actually defined over -- a trendline doesn't
    contribute outside its own anchor span.

    Zones are built independently per bar (no merging of adjacent bars
    into a single wider zone in this increment), sorted by bar_index, and
    only returned where at least 2 distinct lines cluster -- clustering
    uses the same running-mean approach as find_axis_lines().

    Returns one ConfluenceZone per qualifying bar/cluster.
    """
    axis_lines = axis_lines or []
    trendlines = trendlines or []
    channels = channels or []
    if not (axis_lines or trendlines or channels):
        return []

    sloped_spans = [(t.anchor_start.bar_index, t.anchor_end.bar_index) for t in trendlines]
    sloped_spans += [(c.trendline.anchor_start.bar_index, c.trendline.anchor_end.bar_index) for c in channels]
    if bar_range is None:
        if not sloped_spans:
            return []  # nothing but flat axis lines with no bar range to sample
        lo = min(s for s, _ in sloped_spans)
        hi = max(e for _, e in sloped_spans)
        bar_range = range(lo, hi + 1)

    def anchors_of(point: Dict[str, Any]) -> frozenset:
        """Bar indices of the pivots a line's construction actually depends
        on. Two lines sharing any of these aren't independent evidence --
        e.g. two channels built from trendlines that share an anchor pivot
        would otherwise "confirm" each other just by being nested."""
        ref = point["ref"]
        if point["type"] == "axis_line":
            return frozenset(t.bar_index for t in ref.touches)
        if point["type"] == "trendline":
            return frozenset((ref.anchor_start.bar_index, ref.anchor_end.bar_index))
        return frozenset((ref.trendline.anchor_start.bar_index, ref.trendline.anchor_end.bar_index,
                           ref.anchor_pivot.bar_index))

    zones: List[ConfluenceZone] = []
    for bar_index in bar_range:
        points: List[Dict[str, Any]] = []
        for line in axis_lines:
            points.append({"type": "axis_line", "level": line.level, "ref": line})
        for t in trendlines:
            if t.anchor_start.bar_index <= bar_index <= t.anchor_end.bar_index:
                points.append({"type": "trendline", "level": t.value_at(bar_index), "ref": t})
        for c in channels:
            if c.trendline.anchor_start.bar_index <= bar_index <= c.trendline.anchor_end.bar_index:
                points.append({"type": "channel", "level": c.value_at(bar_index), "ref": c})
        if len(points) < 2:
            continue

        ordered = sorted(points, key=lambda p: p["level"])
        cluster: List[Dict[str, Any]] = [ordered[0]]
        cluster_mean = ordered[0]["level"]
        cluster_anchors = set(anchors_of(ordered[0]))
        for point in ordered[1:]:
            point_anchors = anchors_of(point)
            independent = not (point_anchors & cluster_anchors)
            if independent and cluster_mean > 0 and abs(point["level"] / cluster_mean - 1) <= tolerance:
                cluster.append(point)
                cluster_mean = sum(p["level"] for p in cluster) / len(cluster)
                cluster_anchors |= point_anchors
            else:
                if len(cluster) >= 2:
                    zones.append(ConfluenceZone(bar_index=bar_index, price=cluster_mean, members=cluster))
                cluster = [point]
                cluster_mean = point["level"]
                cluster_anchors = set(point_anchors)
        if len(cluster) >= 2:
            zones.append(ConfluenceZone(bar_index=bar_index, price=cluster_mean, members=cluster))

    return zones


def confluence_records(zones: List[ConfluenceZone]) -> List[Dict[str, Any]]:
    """JSON-serializable form of find_confluence() output."""
    out = []
    for z in zones:
        members = []
        for m in z.members:
            ref = m["ref"]
            if m["type"] == "axis_line":
                members.append({"type": "axis_line", "level": round(m["level"], 4),
                                 "touch_count": ref.touch_count})
            elif m["type"] == "trendline":
                members.append({"type": "trendline", "level": round(m["level"], 4),
                                 "kind": ref.kind, "touch_count": len(ref.touches)})
            else:
                members.append({"type": "channel", "level": round(m["level"], 4),
                                 "orientation": ref.orientation, "base_kind": ref.trendline.kind})
        out.append({"bar_index": z.bar_index, "price": round(z.price, 4), "members": members})
    return out
