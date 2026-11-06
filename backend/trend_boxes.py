"""Stair-step trend boxes for breakouts and breakdowns (Darvas-style).

One implementation shared by the daily report, the Weis Radar results and the
click-to-chart view, so all three describe a stock the same way.

Bullish rules (breakdowns are the mirror image, run on negated prices):
- Sideways: from the crossing until the trend gate is first crossed.
- Trend gate: close above its 10-day average, the average rising, and the
  10-day change above +2%.
- Trending, step 1. When the trend goes 3 sessions without a new high a box
  opens: top = the trend's highest high; bottom = the lowest low since, fixed
  after 3 sessions without a new low. The box extends while closes stay inside.
- A close above the top is the next step; a close below the fixed bottom breaks
  the trend until the gate is crossed again (trend 2).
"""
from typing import Any, Callable, Dict, List, Optional


def _f(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt2(value: Any, digits: int = 2) -> str:
    v = _f(value)
    return "n/a" if v is None else f"{v:,.{digits}f}"


def _default_date(bar: Dict[str, Any]) -> Optional[str]:
    t = bar.get("t") or bar.get("date")
    return str(t)[:10] if t else None


TREND_AVERAGE_BARS = 10
TREND_MIN_CHANGE_PCT = 2.0


def trend_gate(closes: List[float], i: int, bullish: bool) -> bool:
    """Trend gate on bar i: close beyond its 10-day average, the average moving
    the break's way, and the 10-day change beyond +2% (or -2% for breakdowns)."""
    n = TREND_AVERAGE_BARS
    if i < n or i >= len(closes):
        return False
    avg = sum(closes[i - n + 1:i + 1]) / n
    prev_avg = sum(closes[i - n:i]) / n
    change = (closes[i] / closes[i - n] - 1) * 100 if closes[i - n] else 0.0
    if bullish:
        return closes[i] > avg and avg > prev_avg and change > TREND_MIN_CHANGE_PCT
    return closes[i] < avg and avg < prev_avg and change < -TREND_MIN_CHANGE_PCT


BOX_CONFIRM_SESSIONS = 3


def trend_boxes(bars: List[Dict[str, Any]], i0: int, bullish: bool,
                date_of: Callable[[Dict[str, Any]], Optional[str]] = _default_date) -> Dict[str, Any]:
    """Trend phases from the crossing bar i0 to the latest bar, as stair steps.

    Bullish (breakdowns are the mirror image, run on negated prices):
    - Sideways: before the trend gate is first crossed.
    - Trending: gate crossed; step 1. Each close above a box top is the next step.
    - Box: once 3 sessions pass with no new high, a box opens. Top = the trend's
      highest high; bottom = the lowest low since, fixed after 3 sessions with no
      new low. It extends right while closes stay inside.
    - Close above the top: trend resumes (next step). Close below a fixed bottom:
      trend broken, until the gate is crossed again (trend 2, step 1).
    Box edges use highs/lows; a close beyond an edge ends the box."""
    sign = 1 if bullish else -1
    hi = [sign * (_f(b.get("h")) if bullish else _f(b.get("l"))) for b in bars]
    lo = [sign * (_f(b.get("l")) if bullish else _f(b.get("h"))) for b in bars]
    cl = [_f(b.get("c")) for b in bars]
    if any(v is None for v in cl):
        return {}
    cl_t = [sign * c for c in cl]
    real = (lambda v: sign * v)
    st: Dict[str, Any] = {"phase": "sideways", "trend": 0, "step": 0, "boxes": []}
    high_i = None
    box = None
    for k in range(i0, len(bars)):
        phase = st["phase"]
        if phase in ("sideways", "broken"):
            if trend_gate(cl, k, bullish):
                st.update(phase="trending", trend=st["trend"] + 1, step=1,
                          trend_start=k, phase_start=k)
                high_i = max(range(st.get("broken_at", i0) if phase == "broken" else i0, k + 1), key=lambda j: hi[j])
            continue
        if phase == "trending":
            if hi[k] >= hi[high_i]:
                high_i = k
            elif k - high_i >= BOX_CONFIRM_SESSIONS:
                lows = range(high_i + 1, k + 1)
                b_i = min(lows, key=lambda j: lo[j])
                box = {"top": hi[high_i], "bottom": lo[b_i], "bottom_i": b_i, "fixed": k - b_i >= BOX_CONFIRM_SESSIONS,
                       "opened": k, "top_date": date_of(bars[high_i])}
                st.update(phase="box", phase_start=high_i + 1)   # the pause began after the high
            continue
        if phase == "box":
            if cl_t[k] > box["top"]:
                box.update(end_date=date_of(bars[k]), exit="trend resumed")
                st["boxes"].append(box)
                st.update(phase="trending", step=st["step"] + 1, phase_start=k)
                high_i, box = k, None
            elif box["fixed"] and cl_t[k] < box["bottom"]:
                box.update(end_date=date_of(bars[k]), exit="trend broken")
                st["boxes"].append(box)
                st.update(phase="broken", phase_start=k, broken_at=k, broken_date=date_of(bars[k]))
                box = None
            elif not box["fixed"]:
                if lo[k] < box["bottom"]:
                    box["bottom"], box["bottom_i"] = lo[k], k
                if k - box["bottom_i"] >= BOX_CONFIRM_SESSIONS:
                    box["fixed"] = True
    last = len(bars) - 1
    st["phase_day"] = last - st.get("phase_start", i0) + 1
    st["trend_start_date"] = date_of(bars[st["trend_start"]]) if "trend_start" in st else None

    def edges(b):
        a, c = real(b["bottom"]), real(b["top"])
        return {"low": min(a, c), "high": max(a, c), "fixed": b["fixed"], "top_date": b["top_date"],
                "end_date": b.get("end_date") or date_of(bars[last]), "exit": b.get("exit")}
    if box:
        box["number"] = st["step"]
    st["box"] = edges(box) if box else None
    st["prior_boxes"] = [edges(b) for b in st.pop("boxes")]
    # Every box in order, for drawing: number, edges, start (the trend high's
    # bar), end (the bar that closed out of it, or the latest bar if open).
    st["all_boxes"] = [dict(b, number=n + 1) for n, b in enumerate(st["prior_boxes"])] + (
        [dict(st["box"], number=len(st["prior_boxes"]) + 1)] if st["box"] else [])
    return st


def trend_label(st: Dict[str, Any], day: int, bullish: bool) -> str:
    word = "bullish" if bullish else "bearish"
    prefix = f"Trend {st['trend']}: " if st.get("trend", 0) > 1 else ""
    phase = st.get("phase")
    if phase == "trending":
        return f"{prefix}Trending {word}, step {st['step']} (trend began {st['trend_start_date']})"
    if phase == "box":
        b = st["box"]
        bottom = "" if b["fixed"] else ", bottom still forming"
        return (f"{prefix}In box {st['step']}, day {st['phase_day']}: "
                f"{_fmt2(b['low'], 2)}–{_fmt2(b['high'], 2)}{bottom}")
    if phase == "broken":
        side = "bottom" if bullish else "top"
        return f"Trend broken {st['broken_date']} (closed beyond box {st['step']} {side}), day {st['phase_day']}"
    return f"Sideways, day {day}"


def pivot_label(st: Dict[str, Any], bullish: bool) -> str:
    """Box edges as resistance (R) and support (S): the current box, then the prior one."""
    parts = []
    for name, b in (("Box", st.get("box")), ("Prior box", (st.get("prior_boxes") or [None])[-1])):
        if b:
            parts.append(f"{name}: R {_fmt2(b['high'], 2)} / S {_fmt2(b['low'], 2)}")
    return "; ".join(parts)




def true_crossing_index(closes: List[Optional[float]], j: int, level: float, bullish: bool) -> int:
    """The detector looks back only 20 bars; walk back through earlier closes
    still beyond the level (its 0.1% rule) to the real crossing bar."""
    def beyond(c):
        return c is not None and (c > level * 1.001 if bullish else c < level * 0.999)
    while j > 0 and beyond(closes[j - 1]):
        j -= 1
    return j


def boxes_for_crossing(bars: List[Dict[str, Any]], hit: Dict[str, Any],
                       date_of: Callable[[Dict[str, Any]], Optional[str]] = _default_date) -> Optional[Dict[str, Any]]:
    """Trend/box state for one detected BREAKOUT or BREAKDOWN hit, using bars
    with t/o/h/l/c keys (or date/open/high/low/close)."""
    kind = str(hit.get("type") or "").upper()
    level = _f(hit.get("level"))
    if kind not in ("BREAKOUT", "BREAKDOWN") or not level or not bars:
        return None
    norm = [{"t": b.get("t") or b.get("date"), "h": b.get("h", b.get("high")), "l": b.get("l", b.get("low")),
             "c": b.get("c", b.get("close"))} for b in bars]
    bullish = kind == "BREAKOUT"
    date = str(hit.get("date") or "")
    def same(t):
        t = str(t or "")
        return t == date or (len(date) == 10 and t[:10] == date)
    j = next((i for i in range(len(norm) - 1, -1, -1) if same(norm[i]["t"])), None)
    if j is None:
        return None
    i0 = true_crossing_index([_f(b["c"]) for b in norm], j, level, bullish)
    st = trend_boxes(norm, i0, bullish, date_of=date_of)
    if not st:
        return None
    day = len(norm) - i0
    return {
        "direction": "Bullish" if bullish else "Bearish",
        "crossing_date": date_of(norm[i0]),
        "level": level,
        "day": day,
        "phase": st.get("phase"),
        "step": st.get("step"),
        "trend_label": trend_label(st, day, bullish),
        "pivots_label": pivot_label(st, bullish),
        "boxes": st.get("all_boxes") or [],
    }
