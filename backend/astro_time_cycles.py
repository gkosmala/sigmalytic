"""Time cycles from W.D. Gann Master Stock Market Course (course page numbers from the footers). Only counts Gann states are used.

Starting points are the Gann Fan's per chart (extreme high, extreme low, latest two confirmed bottoms and tops). Counts are in the units
Gann states them in (calendar days, months, years); the chart only decides which starting points are used. "Square of the range"
(p.122): the price range of a move divided by the price-per-degree table unit, counted in bars of the chart after the start of the move.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# (unit, from, to, kind it applies to or None for any, page, wording)
COUNTS: List[Tuple[str, float, float, Optional[str], str, str]] = [
    ("d", 30, 30, None, "p.50", "30 days from the last top or bottom"),
    ("d", 60, 60, None, "p.50", "60 days"), ("d", 80, 80, None, "p.119", "80 days"),
    ("d", 90, 90, None, "p.50", "90 days"), ("d", 120, 120, None, "p.50", "120 days"),
    ("d", 135, 135, None, "p.119", "135 days"), ("d", 180, 180, None, "p.50", "180 days (six months)"),
    ("d", 42, 45, None, "p.282", "42nd to 45th day (45 days is 1/8 of a year)"),
    ("d", 49, 52, None, "pp.51, 282", "49th to 52nd day (7 x 7)"),
    ("d", 90, 98, None, "p.282", "culminations at 90 to 98 days"),
    ("m", 9, 9, None, "p.50", "9th month"), ("m", 10, 11, None, "pp.47, 280", "10th to 11th month (1-year cycle)"),
    ("m", 23, 24, None, "pp.48, 280", "23rd to 24th month"), ("m", 27, 27, None, "pp.280, 281", "27th month"),
    ("m", 30, 30, None, "p.280", "30th month (1/4 of the 10-year cycle)"), ("m", 34, 35, None, "p.48", "34th to 35th month"),
    ("m", 41, 42, None, "p.48", "41st to 42nd month"), ("m", 49, 60, None, "p.48", "49th to 60th month"),
    ("m", 59, 60, None, "p.48", "59th to 60th month (end of a 5-year campaign)"),
    ("m", 67, 72, None, "p.48", "67th to 72nd month"), ("m", 84, 90, None, "p.48", "84th to 90th month"),
    ("m", 7.5, 7.5, None, "p.280", "7.5 months (1/16 of 120)"), ("m", 15, 15, None, "p.280", "15 months (1/8 of 120)"),
    ("m", 21, 21, None, "p.280", "21 months (1/4 of 84)"), ("m", 40, 40, None, "p.280", "40 months (1/3 of 120)"),
    ("m", 80, 80, None, "p.280", "80 months (2/3 of 120)"),
    ("y", 5, 5, None, "pp.49, 51", "5 years (top to the next bottom, bottom to the next top; the 5-year cycle)"),
    ("y", 10, 10, None, "pp.48, 51", "10 years (top to the next top, bottom to the next bottom)"),
    ("y", 20, 20, None, "pp.47, 51", "20 years"), ("y", 30, 30, None, "pp.47, 51", "30 years"),
    ("y", 50, 50, None, "pp.49, 51", "50 years"), ("y", 60, 60, None, "p.51", "60 years"),
    ("y", 3, 3, None, "p.48", "3 years"), ("y", 7, 7, "low", "p.48", "7 years (3 + 4) from a bottom"),
    ("y", 6, 6, "high", "p.48", "6 years (3 + 3) from a top"),
]


def _d(s: Any) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def count_window(start: date, unit: str, lo: float, hi: float) -> Tuple[date, date]:
    from backend.astro_gann_extra import _add_months

    def at(n: float) -> date:
        months = n * (12 if unit == "y" else 1)
        whole = int(months)
        base = _add_months(start, whole)
        return base + timedelta(days=round((months - whole) * 30.4375))
    if unit == "d":
        return start + timedelta(days=int(lo)), start + timedelta(days=int(hi))
    return at(lo), at(hi)


def anchor_cycles(anchor: Dict[str, Any], today: date) -> Dict[str, Any]:
    """Every Gann count from one starting point: those in effect today, the latest one that has passed and the next one coming."""
    start = _d(anchor["date"])
    rows = []
    for unit, lo, hi, kind, page, text in COUNTS:
        if kind and kind != anchor["kind"]:
            continue
        a, b = count_window(start, unit, lo, hi)
        rows.append({"from": str(a), "to": str(b), "page": page, "text": text})
    now = [r for r in rows if _d(r["from"]) <= today <= _d(r["to"])]
    past = [r for r in rows if _d(r["to"]) < today]
    nxt = [r for r in rows if _d(r["from"]) > today]
    return {"elapsed_days": (today - start).days, "now": now,
            "last": max(past, key=lambda r: r["to"]) if past else None,
            "next": min(nxt, key=lambda r: r["from"]) if nxt else None}


def square_of_range(anchors: List[Dict[str, Any]], unit: float, elapsed) -> List[Dict[str, Any]]:
    """Gann p.122: the range of a move (any low to any high) squares with time when as many bars have passed as the range has table units.
    One row per low/high pair of a chart's starting points (any low to any high, each counted from the earlier one); `elapsed(anchor)` gives bars since that anchor."""
    out = []
    pts = sorted(anchors, key=lambda a: _d(a["date"]))
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if a["kind"] == b["kind"] or not unit:
                continue
            need = abs(b["price"] - a["price"]) / unit
            e = elapsed(a)
            out.append({"chart": a["chart"], "from": f"{a['label']} {a['date']} ${a['price']:.2f}", "to": f"{b['label']} {b['date']} ${b['price']:.2f}",
                        "range": round(abs(b["price"] - a["price"]), 2), "bars_to_square": round(need, 1), "bars_elapsed": e,
                        "bars_remaining": round(need - e, 1)})
    return out


def time_cycles(fan: Dict[str, Any], today: date, unit: float, elapsed) -> Dict[str, Any]:
    anchors = fan.get("anchors", [])
    per = []
    for a in anchors:
        c = anchor_cycles(a, today)
        per.append({"chart": a["chart"], "label": a["label"], "date": str(a["date"])[:10], "price": a["price"], "kind": a["kind"], **c})
    sq = []
    for ch in ("daily", "weekly", "monthly"):
        sq += square_of_range([a for a in anchors if a["chart"] == ch], unit, elapsed)
    # Gann pp.122, 130-132: the price of a top or bottom, in table units, is that many bars counted from the date of the top or bottom
    price_sq = []
    for a in anchors:
        if unit and a["price"]:
            need, e = a["price"] / unit, elapsed(a)
            price_sq.append({"chart": a["chart"], "label": a["label"], "date": str(a["date"])[:10], "price": a["price"],
                             "bars_to_square": round(need, 1), "bars_elapsed": e, "bars_remaining": round(need - e, 1)})
    return {"anchors": per, "square": sq, "price_square": price_sq}
