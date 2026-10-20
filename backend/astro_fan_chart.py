# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research (owner only): the Gann Fan drawn over the price bars of one chart.

Charts and how many bars are shown (owner's instruction): weekly and monthly = all the history fetched, daily = 5 years,
4-hour and 2-hour = 3 years. The fan is the one in astro_gann_extra: the extreme high and low of the history on that chart and
the latest two confirmed bottoms and tops, rays 8x1 to 1x8, the 1x1 moving one price-per-degree-table unit per bar. The 2-hour
and 4-hour charts use the daily chart's pivot rules (Gann's course gives no rule for hourly bars). Lines are straight, so each
is returned as a start and an end point; they run on past the last bar by FUTURE_BARS bars."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from backend import astro_gann_extra as gx

FUTURE_BARS = 20
SHOW = {"daily": 5, "weekly": None, "monthly": None, "4h": 3, "2h": 3}   # years of bars shown; None = all
TIMEFRAME = {"2h": "2Hour", "4h": "4Hour"}
FETCH_YEARS = {"daily": 12, "weekly": 12, "monthly": 12, "4h": 3, "2h": 3}


def _future_labels(chart: str, last: str, n: int) -> List[str]:
    return [f"+{k}" for k in range(1, n + 1)]


def fan_chart_from_bars(bars: List[Dict[str, Any]], chart: str) -> Dict[str, Any]:
    """Chart data from the bars fetched (daily bars for daily, weekly and monthly; hourly bars for 2h and 4h)."""
    from backend import astro_research as ar
    if chart not in SHOW:
        return {"error": f"Unknown chart: {chart}"}
    if len(bars) < 60:
        return {"error": "Not enough price history to draw the fan."}
    last_day = str(bars[-1]["t"])[:10]
    day = (date.fromisoformat(last_day) + timedelta(days=1)).isoformat()   # periods that hold this day are left out of the pivots
    rows_all = gx.chart_bars(bars, chart, "9999-12-31")                       # every bar, including a partial last week or month
    anchors = gx.fan_anchors(bars, chart, day)
    if not anchors or not rows_all:
        return {"error": "No fan could be built (too few bars or no confirmed pivots)."}
    years = SHOW[chart]
    if years is None:
        rows = rows_all
    else:
        cut = (date.fromisoformat(last_day) - timedelta(days=int(365.25 * years))).isoformat()
        rows = [r for r in rows_all if r["t"][:10] >= cut]
    last_close = rows_all[-1]["c"]
    unit = ar.price_unit(last_close)
    n_future = FUTURE_BARS
    labels = [r["t"] for r in rows] + _future_labels(chart, rows[-1]["t"], n_future)
    first_pos, last_pos = rows[0]["pos"], rows[-1]["pos"]
    end_pos = last_pos + n_future
    lines = []
    for an in anchors:
        for a, b in gx.FAN_ANGLES:
            start_pos = max(first_pos, an["pos"] + 1)
            if start_pos > end_pos:
                continue
            y0 = gx.fan_price(an, a, b, unit, start_pos - an["pos"])
            y1 = gx.fan_price(an, a, b, unit, end_pos - an["pos"])
            if y0 is None or y1 is None:
                continue
            # x positions are indexes into `labels`: weekly and monthly positions are period numbers, so map through the rows
            lines.append({"angle": f"{a}x{b}", "from": an["label"], "kind": an["kind"], "x0": _x_index(rows, start_pos, chart, first_pos),
                          "x1": len(labels) - 1, "y0": round(y0, 4), "y1": round(y1, 4)})
    pts = []
    for an in anchors:
        i = _x_index(rows, an["pos"], chart, first_pos)
        if i is not None and 0 <= i < len(rows):
            pts.append({"label": an["label"], "kind": an["kind"], "x": i, "y": an["price"], "date": an["date"], "chart": chart,
                        "confirmed": an.get("confirmed")})
    return {"chart": chart, "bars": [{"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"]} for r in rows],
            "labels": labels, "lines": lines, "anchors": pts, "unit": unit, "future_bars": n_future,
            "all_anchors": [{k: a[k] for k in ("label", "kind", "price", "date") if k in a} for a in anchors],
            "bars_shown": len(rows), "first": rows[0]["t"], "last": rows[-1]["t"]}


def _x_index(rows: List[Dict[str, Any]], pos: int, chart: str, first_pos: int) -> int:
    """Index of a time position among the shown bars. Daily and hourly positions run 1 per bar; weekly and monthly positions are
    week and month numbers, which skip empty periods, so the nearest shown bar at or after the position is used."""
    if chart in gx.BAR_CHARTS:
        return pos - first_pos
    for i, r in enumerate(rows):
        if r["pos"] >= pos:
            return i
    return len(rows) + (pos - rows[-1]["pos"]) - 1


def fan_chart(symbol: str, chart: str) -> Dict[str, Any]:
    from backend import astro_research as ar
    if chart not in SHOW:
        return {"error": f"Unknown chart: {chart}"}
    bars = ar.fetch_bars(symbol, FETCH_YEARS[chart], TIMEFRAME.get(chart, "1Day"))
    out = fan_chart_from_bars(bars, chart)
    if "error" not in out:
        out["symbol"] = symbol
    return out
