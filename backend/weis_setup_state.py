# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/weis_setup_state.py
---------------------------
Weis-only setup state for one symbol: No setup / Watching / Setting Up /
Armed / Avoid, for springs (long) and upthrusts (short).

Every rule below is taken from David Weis, "Trades About to Happen" (2013).
Page numbers are given next to each rule. Where the book gives NO rule, the
choice is named in CONFIG at the top and marked "NOT FROM WEIS".

THE SEQUENCE (springs; upthrusts are the exact mirror)
------------------------------------------------------
A "line" is any line the book draws: horizontal support/resistance, axis
lines (Ch.2-3), trend lines, the parallel line of a channel (including reverse
channels), and the converging lines of a wedge (pp. 11-26). Built by
backend/weis_lines.py.

  Watching    price has traded below a support line (a "potential spring
              position") and has not yet closed back above it. (p.74)
  Setting Up  the bar that broke the line closed back above it. (p.74, p.76)
  Armed       after the close back above the line, later bars show no
              follow-through to the downside. (p.74, p.78, p.88)
  Avoid       the setup is against the LONGER-TERM trend (p.87, p.96). Trend =
              higher highs and higher lows (up) / lower highs and lower lows
              (down), universal definition given by the user; daily bars are
              read against the weekly trend. Avoid ends when that trend turns.
  Flip        follow-through (a close beyond the low/high of the break) means
              the setup failed at a point of control. It is not "avoid": the
              line is now on the other side of price and the same sequence is
              read on it mirrored (failed spring -> possible short on the same
              line; failed upthrust -> possible long). Weis: failed springs
              are "useful trading information" for shorts (p.74); repeated
              failed springs are sellers absorbing the buying (pp.112-113).
  No setup    no line has been broken.

Upthrust: price trades above a resistance line; same sequence, mirrored
(p.95-99). Confirmation by a close below the prior bars' lows (p.97-99) is the
same "no follow-through" evidence seen from the other side.

LIVENESS (replaces a bar count; the book gives none)
----------------------------------------------------
Weis buys "at the danger point where the risk is smallest", with the stop
below the low of the break (p.74, p.94). A setup is live while the trade is
open: it ends when the stop fails (that is "Avoid") or when price has reached
the target. Here the target is the nearest line on the other side of the
range. Point-and-figure count targets (Ch.11, pp.180-182) are the planned
replacement and are NOT used here yet.

ANGLE (NOT FROM WEIS): angle_profile() measures each swing leg against a price
unit (45 degrees = one unit per bar, W.D. Gann's 1x1, adopted by the user) and
flags a change of character when legs at/above 45 degrees are followed by a leg
below it. Weis supports only the idea that angle shows ease of movement
(pp.163-167). Price unit: app P&F box rule ("box") or ATR x multiplier ("atr",
web-summary method attributed to Raschke by the user, unverified).

NOT FROM WEIS (see CONFIG): line-drawing tolerances live in weis_lines.py;
the 15 percent penetration ceiling is Weis's own upper limit for upthrusts
(p.99), applied to springs as well by agreement with the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from backend import weis_lines as wl

CONFIG: Dict[str, Any] = {
    # Weis p.99: "A new high by 10 to 15 percent seems a reasonable
    # limitation for an upthrust." Upper end used. Applied to springs too.
    "penetration_ceiling": 0.15,
    # Disables weis_lines' own "line broken by a later close" rejection, which
    # would delete the very line a spring closes below. NOT FROM WEIS.
    "line_break_tolerance_off": 1e6,
    # Follow-through window: a break only counts as followed through (failed)
    # if price closes beyond the break bar's low/high within the next 2 bars of
    # the frame being read. NOT FROM WEIS as a bar count (Weis: the next day,
    # a secondary test, pp.74, 78, 88). The 2-bar number is the user's, from
    # Raschke's 2-period rule ("Raschke, per user").
    "follow_through_bars": 2,
    # Expiry of a flipped setup that has NOT been retested ("failed at the line,
    # no retest"). NOT FROM WEIS; "Raschke, per user" (source: pasted web text,
    # unverified). If ANY one applies, the setup is dead.
    #   20-bar limit: more than this many bars since the failure bar.
    "flip_max_bars": 20,
    #   new base: the last 4 bars together span less than this x ATR(14).
    "flip_base_atr_fraction": 0.75,
    # Not built (user has not given the number): 3-4 overlapping bar bodies
    # "against the line" needs a distance fraction of a bar range.
}

STATE_RANK = {"Armed": 3, "Setting Up": 2, "Watching": 1, "Avoid": 0}


def _normalize(bars: List[dict]) -> List[dict]:
    """Accept either the radar's open/high/low/close/volume/date keys or the
    weis_lines o/h/l/c/v/t keys."""
    out = []
    for b in bars or []:
        def g(*keys):
            for k in keys:
                if k in b and b[k] is not None:
                    try:
                        return float(b[k])
                    except (TypeError, ValueError):
                        return None
            return None
        t = b.get("t", b.get("date", b.get("timestamp", "")))
        out.append({"t": str(t), "o": g("o", "open"), "h": g("h", "high"),
                    "l": g("l", "low"), "c": g("c", "close"), "v": g("v", "volume") or 0.0})
    return [b for b in out if None not in (b["h"], b["l"], b["c"])]


@dataclass
class _Line:
    source: str                    # "axis" | "trendline" | "channel"
    side: str                      # "support" | "resistance" | "both"
    value_at: Callable[[int], float]
    touches: int
    last_anchor: int               # latest bar index used to draw the line


def _build_lines(bars: List[dict], timeframe: str, before: int) -> List[_Line]:
    """Lines drawn only from pivots that exist before bar index `before`."""
    pivots = [p for p in wl.scan_fractal_pivots(bars, timeframe=timeframe)
              if p.bar_index < before]
    if not pivots:
        return []
    off = CONFIG["line_break_tolerance_off"]
    lines: List[_Line] = []

    for al in wl.find_axis_lines(pivots):
        level = al.level
        lines.append(_Line("axis", "both", (lambda i, lv=level: lv), al.touch_count,
                           al.last_touch_index))

    support = wl.find_trendlines(pivots, bars, kind="swing_low", break_tolerance=off)
    resist = wl.find_trendlines(pivots, bars, kind="swing_high", break_tolerance=off)
    for t in support:
        lines.append(_Line("trendline", "support", t.value_at, len(t.touches),
                           t.anchor_end.bar_index))
    for t in resist:
        lines.append(_Line("trendline", "resistance", t.value_at, len(t.touches),
                           t.anchor_end.bar_index))
    for t in support + resist:
        ch = wl.find_channel(t, pivots)
        if ch is None:
            continue
        side = "resistance" if t.kind == "swing_low" else "support"
        lines.append(_Line("channel", side, ch.value_at, ch.touch_count + 1,
                           max(t.anchor_end.bar_index, ch.anchor_pivot.bar_index)))
    return lines


def _swing_trend(bars: List[dict], timeframe: str) -> str:
    """Universal trend definition (given by the user, not Weis-specific):
    higher highs AND higher lows = 'up'; lower highs AND lower lows = 'down';
    anything else (mixed, or too few swings) = 'none'. Swings are the fractal
    pivots from weis_lines (confirmed pivots only, no look-ahead)."""
    pivs = wl.scan_fractal_pivots(bars, timeframe=timeframe)
    highs = [p.price for p in pivs if p.kind == "swing_high"]
    lows = [p.price for p in pivs if p.kind == "swing_low"]
    if len(highs) < 2 or len(lows) < 2:
        return "none"
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "up"
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "down"
    return "none"


def _to_weekly(bars: List[dict]) -> List[dict]:
    """Group daily bars into ISO weeks. If the timestamps cannot be parsed,
    group every 5 bars instead."""
    from datetime import date
    keys = []
    for b in bars:
        try:
            keys.append(date.fromisoformat(str(b["t"])[:10]).isocalendar()[:2])
        except (ValueError, TypeError):
            keys = None
            break
    if keys is None:
        keys = [(0, i // 5) for i in range(len(bars))]
    out, cur, cur_key = [], [], None
    for b, k in zip(bars, keys):
        if k != cur_key and cur:
            out.append(cur)
            cur = []
        cur_key = k
        cur.append(b)
    if cur:
        out.append(cur)
    return [{"t": g[0]["t"], "o": g[0]["o"], "h": max(x["h"] for x in g),
             "l": min(x["l"] for x in g), "c": g[-1]["c"],
             "v": sum(x["v"] or 0 for x in g)} for g in out]


# Timeframe ladders. NOT FROM WEIS. Weis says the method is the same on every
# timeframe (pp.73, 96) and gives no frame pairs. These pairings were chosen by
# the user ("Raschke, per user"): day trading = 15-minute bars read against the
# 1-hour trend and the daily trend; swing = daily bars read against the weekly
# trend. Scalping (30/60-minute structure, 2/5-minute entry) is a different,
# faster style and is not set up here.
LADDERS: Dict[str, Dict[str, Any]] = {
    "swing": {"exec": "1Day", "structure": ["1Week"]},
    "day": {"exec": "15Min", "structure": ["1Hour", "1Day"]},
}


def _completed_before(frame_bars: List[dict], t_break: str) -> List[dict]:
    """Higher-frame bars that were COMPLETE before the break bar: start time
    earlier than the break bar's time, minus the last one (it may still have
    been forming). Timestamps must sort as strings (ISO)."""
    out = [x for x in frame_bars if str(x["t"]) < str(t_break)]
    return out[:-1]


def _trends_by_frame(bars: List[dict], b: int, timeframe: str,
                     htf_bars: Optional[Dict[str, List[dict]]] = None) -> Dict[str, str]:
    """Trend (higher highs/lows = up, lower = down) on each frame, shortest
    first, using only information available before break bar `b`. Daily bars
    with no htf_bars get a weekly frame built from the daily bars."""
    pre = bars[:b]
    out: Dict[str, str] = {timeframe: _swing_trend(pre, timeframe)}
    if htf_bars:
        for frame, fb in htf_bars.items():
            done = _completed_before(_normalize(fb), bars[b]["t"])
            out[frame] = _swing_trend(done, frame) if len(done) >= 8 else "none"
    elif timeframe == "1Day":
        weeks = _to_weekly(pre)[:-1]       # drop the still-forming week
        out["1Week"] = _swing_trend(weeks, "1Week") if len(weeks) >= 8 else "none"
    return out


def _trend_before(bars: List[dict], b: int, timeframe: str,
                  htf_bars: Optional[Dict[str, List[dict]]] = None) -> str:
    """Longer-term trend just before break bar `b`: the trend of the HIGHEST
    frame that has a trend ('up' or 'down'); if none does, 'none'. The
    longer-term trend is the significant one; shorter frames are fractals that
    build it (user, 2026-10-07), so a shorter frame against it does not make a
    setup 'Avoid'. Weis p.96: trend is the most important consideration; the
    definition of trend is the universal one, not Weis's."""
    frames = _trends_by_frame(bars, b, timeframe, htf_bars)
    for t in reversed(list(frames.values())):
        if t != "none":
            return t
    return "none"


def _episode(bars: List[dict], line: _Line, side: str, before_limit: Optional[int] = None):
    """Latest break of `line` on the given side ('support' = spring,
    'resistance' = upthrust). Returns a dict or None."""
    n = len(bars)
    h = [b["h"] for b in bars]
    lo = [b["l"] for b in bars]
    c = [b["c"] for b in bars]
    L = line.value_at

    if side == "support":
        pen = lambda i: lo[i] < L(i)
        back = lambda i: c[i] >= L(i)
    else:
        pen = lambda i: h[i] > L(i)
        back = lambda i: c[i] <= L(i)

    b = None
    for i in range(n - 1, 0, -1):
        if pen(i) and not pen(i - 1):
            b = i
            break
    if b is None:
        return None
    if before_limit is not None and b != before_limit:
        return None

    # contiguous run of penetrating bars starting at b
    m = b
    while m + 1 < n and pen(m + 1):
        m += 1

    W = CONFIG["follow_through_bars"]
    win = range(b + 1, min(b + 1 + W, n))
    if side == "support":
        depth = max((L(i) - lo[i]) / L(i) for i in range(b, m + 1) if L(i) > 0)
        stop0 = min(lo[b:m + 1])
        follow = any(c[j] < lo[b] for j in win)
        stopped = any(lo[j] < stop0 for j in range(m + 1, n))
    else:
        depth = max((h[i] - L(i)) / L(i) for i in range(b, m + 1) if L(i) > 0)
        stop0 = max(h[b:m + 1])
        follow = any(c[j] > h[b] for j in win)
        stopped = any(h[j] > stop0 for j in range(m + 1, n))
    if depth > CONFIG["penetration_ceiling"]:
        return None
    if stopped and not follow:
        return None        # the stop failed after the window: the trade is over

    close_back = next((i for i in range(b, n) if back(i)), None)

    if follow:
        state, reason = "Avoid", "follow-through after the break (p.74); flips below"
    elif close_back is None or not back(n - 1):
        state, reason = "Watching", "broke the line; not closed back inside (p.74)"
    elif close_back == n - 1:
        state, reason = "Setting Up", "closed back inside the line (p.74, p.76)"
    else:
        state, reason = "Armed", "no follow-through after the close back inside (p.78, p.88)"

    return {
        "side": side, "state": state, "reason": reason,
        "break_index": b, "break_time": bars[b]["t"],
        "line_source": line.source, "line_touches": line.touches,
        "line_value_at_break": round(L(b), 4), "penetration": round(depth, 5),
        "stop": round(stop0, 4),
        "bars_since_break": n - 1 - b,
        "close_back_index": close_back,
        "followed_through": bool(follow),
    }


def _atr(bars: List[dict], upto: int, period: int = 14) -> float:
    """Average true range of the `period` bars ending at index upto-1."""
    trs = []
    for i in range(max(1, upto - period), upto):
        pc = bars[i - 1]["c"]
        trs.append(max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - pc), abs(bars[i]["l"] - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _flip_expired(bars: List[dict], f: int, side: str) -> Optional[str]:
    """Why a never-retested flipped setup is dead, or None. `f` is the bar where
    the original setup failed; `side` is the ORIGINAL side ('support' = failed
    spring -> short setup). Any one reason kills it. NOT FROM WEIS."""
    n = len(bars)
    h = [x["h"] for x in bars]
    lo = [x["l"] for x in bars]
    c = [x["c"] for x in bars]
    if n - 1 - f > CONFIG["flip_max_bars"]:
        return "more than %d bars since the failure" % CONFIG["flip_max_bars"]
    for j in range(f + 1, n):
        if h[j] < h[j - 1] and lo[j] > lo[j - 1]:
            return "inside bar: range swallowed by the bar before"
        if j - 3 >= f:
            block = max(h[j - 3:j + 1]) - min(lo[j - 3:j + 1])
            atr = _atr(bars, j + 1)
            if atr > 0 and block < CONFIG["flip_base_atr_fraction"] * atr:
                return "new base: last 4 bars span less than %.2f x ATR(14)" % CONFIG["flip_base_atr_fraction"]
            if side == "support":          # short setup: a swept low closed back above = opposing trap
                ll = min(lo[j - 3:j])
                if lo[j] < ll and c[j] > ll:
                    return "opposing pattern: 3-bar low swept and closed back above"
            else:                          # long setup: a swept high closed back below
                hh = max(h[j - 3:j])
                if h[j] > hh and c[j] < hh:
                    return "opposing pattern: 3-bar high swept and closed back below"
    return None


def _flip(bars: List[dict], line: _Line, side: str, b: int) -> Optional[Dict[str, Any]]:
    """A spring that follows through (price kept going) has failed at a point
    of control. The line is now on the other side of price, so the same
    sequence is read on it, mirrored: a failed spring becomes a possible SHORT
    on the same line, a failed upthrust a possible LONG.

    FROM WEIS: failed springs are "useful trading information" for shorts
    (p.74); repeated failed springs mean sellers are absorbing the buying and
    a short is warranted once price moves lower (pp.112-113, Ch.7). The
    mirror for upthrusts is the same logic (user: if demand/supply is
    exhausted at a point of previous control, the other side takes over).
    NOT FROM WEIS: using the retest of the broken line as the break bar of
    the flipped setup (the book gives no timer); the 15 percent ceiling is
    applied to the retest as in CONFIG.
    Returns None when the failure has not happened or the flip has itself
    failed (price closed back through the retest)."""
    n = len(bars)
    h = [x["h"] for x in bars]
    lo = [x["l"] for x in bars]
    c = [x["c"] for x in bars]
    L = line.value_at
    if side == "support":                       # failed spring -> short
        f = next((j for j in range(b + 1, n) if c[j] < lo[b]), None)
        touch = lambda j: h[j] >= L(j)
        back = lambda j: c[j] <= L(j)
        depth_of = lambda j: (h[j] - L(j)) / L(j)
        flip_side, direction = "resistance", "short"
    else:                                       # failed upthrust -> long
        f = next((j for j in range(b + 1, n) if c[j] > h[b]), None)
        touch = lambda j: lo[j] <= L(j)
        back = lambda j: c[j] >= L(j)
        depth_of = lambda j: (L(j) - lo[j]) / L(j)
        flip_side, direction = "support", "long"
    if f is None:
        return None
    r = next((j for j in range(f + 1, n) if touch(j)), None)
    if r is None:
        if _flip_expired(bars, f, side) is not None:
            return None
        state, reason, anchor = "Watching", "failed at the line; no retest of it yet (p.74, pp.112-113)", f
        stop_ref = max(h[f:]) if side == "support" else min(lo[f:])
        stop = max(stop_ref, L(n - 1)) if side == "support" else min(stop_ref, L(n - 1))
        depth = 0.0
        close_back = None
    else:
        m = r
        while m + 1 < n and touch(m + 1):
            m += 1
        stop0 = max(h[r:m + 1]) if side == "support" else min(lo[r:m + 1])
        if any((h[j] > stop0) if side == "support" else (lo[j] < stop0) for j in range(m + 1, n)):
            return None                         # the flipped setup's own stop failed
        depth = max(depth_of(j) for j in range(r, m + 1) if L(j) > 0)
        if depth > CONFIG["penetration_ceiling"]:
            return None
        close_back = next((j for j in range(r, n) if back(j)), None)
        anchor = r
        stop = stop0
        if close_back is None or not back(n - 1):
            state, reason = "Watching", "retesting the broken line; not yet closed back (p.74, pp.112-113)"
        elif close_back == n - 1:
            state, reason = "Setting Up", "retest of the broken line closed back away from it (p.76, pp.112-113)"
        else:
            state, reason = "Armed", "no follow-through after the retest (p.78, p.88)"
    return {
        "side": flip_side, "state": state, "reason": reason,
        "break_index": anchor, "break_time": bars[anchor]["t"],
        "line_source": line.source, "line_touches": line.touches,
        "line_value_at_break": round(L(anchor), 4), "penetration": round(depth, 5),
        "stop": round(stop, 4), "bars_since_break": n - 1 - anchor,
        "close_back_index": close_back, "followed_through": False,
        "flipped_from": "spring" if side == "support" else "upthrust",
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# Angle of price (Gann 1x1 = 45 degrees). NOT FROM WEIS: the 45 degree cutoff
# is W.D. Gann's, adopted by the user from experience. Weis only says the
# angle shows ease of movement: a low angle of advance "shows how much
# difficulty" a rally had (p.167); time and volume with a flat angle is "the
# personification of weakness" (p.164); a flat decline on heavy volume is
# sellers absorbing the buying (p.163). The price UNIT (what counts as one
# price step per bar) is NOT from Weis either:
#   "box"  = the app's point-and-figure box rule: max(1% of price,
#            0.5 x average absolute close-to-close move), unrounded.
#   "atr"  = 14-bar ATR x atr_mult (a web-summary method attributed to
#            Linda Raschke by the user, unverified; multiplier is a guess).
# ---------------------------------------------------------------------------
ANGLE_CUTOFF_DEGREES = 45.0


def _unit(bars: List[dict], mode: str = "box", atr_mult: float = 1.5) -> float:
    if mode == "atr":
        trs = []
        for i in range(1, len(bars)):
            pc = bars[i - 1]["c"]
            trs.append(max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - pc),
                           abs(bars[i]["l"] - pc)))
        w = trs[-14:]
        return (sum(w) / len(w)) * atr_mult if w else 0.0
    moves = [abs(bars[i]["c"] - bars[i - 1]["c"]) for i in range(1, len(bars))]
    avg = sum(moves) / len(moves) if moves else 0.0
    return max(0.01 * bars[-1]["c"], 0.5 * avg)


def angle_profile(bars: List[dict], timeframe: str = "1Day",
                  unit_mode: str = "box", atr_mult: float = 1.5) -> Dict[str, Any]:
    """Angle of each swing leg (pivot to the next opposite pivot), where one
    price unit per bar is 45 degrees. Flags a change of character when an
    earlier leg in a direction was at or above 45 degrees and the latest leg
    in that direction is below it (the move can still continue; ease of
    movement is what changed)."""
    import math
    bars = _normalize(bars)
    unit = _unit(bars, unit_mode, atr_mult) if len(bars) > 2 else 0.0
    out: Dict[str, Any] = {"unit_mode": unit_mode, "unit": round(unit, 6),
                           "cutoff_degrees": ANGLE_CUTOFF_DEGREES,
                           "basis": "45 degree cutoff: Gann / user, not Weis",
                           "legs": [], "character_change": []}
    if unit <= 0:
        return out
    pivs = sorted(wl.scan_fractal_pivots(bars, timeframe=timeframe),
                  key=lambda p: p.bar_index)
    legs = []
    for a, b in zip(pivs, pivs[1:]):
        if a.kind == b.kind or b.bar_index <= a.bar_index:
            continue
        rise = b.price - a.price
        deg = math.degrees(math.atan((abs(rise) / unit) / (b.bar_index - a.bar_index)))
        legs.append({"direction": "up" if rise > 0 else "down",
                     "from_index": a.bar_index, "to_index": b.bar_index,
                     "degrees": round(deg, 1)})
    out["legs"] = legs[-6:]
    for d, label in (("up", "bullish: later up-legs below 45 degrees after steeper ones"),
                     ("down", "bearish: later down-legs below 45 degrees after steeper ones")):
        ds = [l["degrees"] for l in legs if l["direction"] == d]
        if len(ds) >= 2 and max(ds[:-1]) >= ANGLE_CUTOFF_DEGREES and ds[-1] < ANGLE_CUTOFF_DEGREES:
            out["character_change"].append(label)
    return out


def _target(lines: List[_Line], side: str, b: int, break_level: float) -> Optional[float]:
    """Nearest line on the other side of the range at the break bar."""
    vals = []
    for ln in lines:
        v = ln.value_at(b)
        if side == "support" and v > break_level and ln.side in ("resistance", "both"):
            vals.append(v)
        if side == "resistance" and v < break_level and ln.side in ("support", "both"):
            vals.append(v)
    if not vals:
        return None
    return min(vals) if side == "support" else max(vals)


def evaluate_setup_state(bars: List[dict], timeframe: str = "1Day",
                         unit_mode: str = "box", atr_mult: float = 1.5,
                         htf_bars: Optional[Dict[str, List[dict]]] = None) -> Dict[str, Any]:
    """Weis-only state for the latest bar. Returns a dict with at least
    state ('No setup' when nothing is broken), direction and evidence."""
    bars = _normalize(bars)
    n = len(bars)
    none = {"state": "No setup", "direction": None, "reason": "no line has been broken"}
    if n < 12:
        return none

    first_pass = _build_lines(bars, timeframe, before=n)
    if not first_pass:
        return none

    # Discover break bars with lines from all pivots, then re-check each break
    # against lines drawn only from pivots that existed BEFORE it, so a spring
    # cannot create the line it broke.
    break_bars = set()
    for ln in first_pass:
        sides = ["support", "resistance"] if ln.side == "both" else [ln.side]
        for s in sides:
            ep = _episode(bars, ln, s)
            if ep is not None:
                break_bars.add(ep["break_index"])

    candidates: List[Dict[str, Any]] = []
    for b in sorted(break_bars):
        lines_b = _build_lines(bars, timeframe, before=b)
        for ln in lines_b:
            sides = ["support", "resistance"] if ln.side == "both" else [ln.side]
            for s in sides:
                ep = _episode(bars, ln, s, before_limit=b)
                if ep is None:
                    continue
                if ep["followed_through"]:
                    ep = _flip(bars, ln, s, ep["break_index"])
                    if ep is None:
                        continue
                    s_eff = "support" if ep["direction"] == "long" else "resistance"
                else:
                    s_eff = s
                tgt = _target(lines_b, s_eff, ep["break_index"], ep["line_value_at_break"])
                bi = ep["break_index"]
                if tgt is not None:
                    reached = (max(x["h"] for x in bars[bi:]) >= tgt) if s_eff == "support" \
                        else (min(x["l"] for x in bars[bi:]) <= tgt)
                    if reached:
                        continue  # the move already happened
                cbi = ep.get("close_back_index")
                ep["close_back_time"] = bars[cbi]["t"] if cbi is not None else None
                ep["target"] = None if tgt is None else round(tgt, 4)
                ep.setdefault("direction", "long" if s == "support" else "short")
                trend = _trend_before(bars, b, timeframe, htf_bars)
                ep["trend"] = trend
                ep["trends_by_frame"] = _trends_by_frame(bars, b, timeframe, htf_bars)
                against = (ep["direction"] == "long" and trend == "down") or \
                          (ep["direction"] == "short" and trend == "up")
                if against and ep["state"] != "Avoid":
                    ep["state"], ep["reason"] = "Avoid", "against the longer-term trend (p.87, p.96)"
                candidates.append(ep)

    if not candidates:
        return none
    candidates.sort(key=lambda e: (STATE_RANK[e["state"]], e["break_index"],
                                   e["line_touches"]), reverse=True)
    best = dict(candidates[0])
    best["other_candidates"] = len(candidates) - 1
    best["angle"] = angle_profile(bars, timeframe, unit_mode, atr_mult)
    return best
