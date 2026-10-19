# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research extras taken from the Gann PDF: Square of 144, numerology, natal cycle dates, cosmogram table.

Where the PDF (or the rule the owner supplied) gives no definition, the choice is named in the output so it is never
shown as Gann's. Nothing here applies a tolerance: distances are reported and the reader judges them.
  * Square of 144: PDF pp. 42-44 (box of 144 time x 144 price units, divisions 36/48/72/96/108/144, grand center 72, price
    unit table). Anchor choice is the owner-supplied rule: highest price, lowest price, the 2nd and 3rd higher bottoms,
    minor highs and lows, and the half-price centres.
  * Numerology: PDF pp. 22-24 (digit reduction to 1-9, natal vibration from the first-trade date, resonant prices,
    numbers ending in 9, 144).
  * Natal cycle dates: PDF p. 24 (turning points every N days, weeks or months from the listing date, N = natal vibration,
    and the 49-unit Jubilee). The PDF gives no natal breakout PRICE formula (p. 2), so none is built.
  * Cosmogram: PDF pp. 2 and 108 (a circle of planet longitudes and the angles between them). No construction beyond that is
    given, so this is a table of angles and the nearest aspect with its distance, not a forecast.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

DIVISIONS = (36, 48, 72, 96, 108, 144)
SWING_WINDOW = 20      # my definition (not Gann's): a swing low is the lowest low of +/-20 bars


def reduce_digits(n: int) -> int:
    """Add the digits until one remains (1-9); 0 stays 0. PDF p. 22."""
    n = abs(int(n))
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def natal_vibration(ipo_date: str) -> Dict[str, Any]:
    """PDF p. 23 method: reduce the month, the day and the year separately, add them, reduce again."""
    y, m, d = (int(x) for x in ipo_date.split("-"))
    parts = {"month": reduce_digits(m), "day": reduce_digits(d), "year": reduce_digits(y)}
    return {"vibration": reduce_digits(sum(parts.values())), "parts": parts, "date": ipo_date}


def day_vibration(day: str) -> int:
    """All digits of the date added and reduced (the PDF's own page-109 example does this; its printed answer is inconsistent)."""
    return reduce_digits(sum(int(c) for c in day if c.isdigit()))


def numerology_levels(ref: float, unit: float, band: float, vib: int) -> List[Dict[str, Any]]:
    """Prices (in whole price units) within `band` of the reference that match the natal vibration: the digit sum of the
    number equals it, or it is a multiple of it, or it ends in 9 (PDF pp. 22-23). Includes multiples of 144 and 72."""
    lo, hi = int(ref * (1 - band) / unit), int(ref * (1 + band) / unit) + 1
    out = []
    for k in range(max(lo, 1), hi + 1):
        why = []
        if vib and reduce_digits(k) == vib:
            why.append(f"digits reduce to the natal vibration {vib}")
        if vib and k % vib == 0:
            why.append(f"multiple of {vib}")
        if k % 10 == 9:
            why.append("ends in 9")
        if k % 144 == 0:
            why.append("multiple of 144")
        if why:
            price = k * unit
            if abs(price / ref - 1) <= band:
                out.append({"price": price, "number": k, "why": why})
    return out


def _add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    year, month = d.year + y, mo + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


def natal_cycle_dates(ipo_date: str, vib: int, day: str, ahead: int = 3) -> List[Dict[str, Any]]:
    """Dates that are k x N days / weeks / months after the listing date, and the 49-unit Jubilee (PDF p. 24).
    Reports whether the report day is one, and the next few dates."""
    d0, d = date.fromisoformat(ipo_date), date.fromisoformat(day)
    out = []
    for n in sorted({vib, 49} - {0}):
        for unit, label in (("days", "day"), ("weeks", "week"), ("months", "month")):
            def nth(k, _n=n, _u=unit):
                return d0 + timedelta(days=k * _n * (7 if _u == "weeks" else 1)) if _u != "months" else _add_months(d0, k * _n)
            k = 1
            while nth(k) < d:
                k += 1
            nxt = []
            kk = k
            while len(nxt) < ahead and kk < k + 400:
                if nth(kk) >= d:
                    nxt.append({"k": kk, "date": nth(kk).isoformat()})
                kk += 1
            prev = nth(k - 1) if k > 1 else None
            out.append({"cycle": f"{n} {unit}" + (" (Jubilee 7 x 7)" if n == 49 else ""), "n": n, "unit": unit,
                        "on_report_day": nth(k) == d, "previous": prev.isoformat() if prev else None, "next": nxt[:ahead]})
    return out


# ── Square of 144 ──
def swing_lows(bars: List[Dict[str, Any]], window: int = SWING_WINDOW) -> List[int]:
    lows = [float(b["l"]) for b in bars]
    return [i for i in range(window, len(bars) - window) if lows[i] == min(lows[i - window:i + window + 1])]


def sq144_anchors(bars: List[Dict[str, Any]], pivots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Anchors by the owner-supplied rule. `bars` are daily bars before the report day (the history available, which
    is not necessarily the true all-time range)."""
    rows = [b for b in bars if b.get("h") and b.get("l")]
    if len(rows) < 60:
        return []
    first = str(rows[0]["t"])[:10]
    ih = max(range(len(rows)), key=lambda i: float(rows[i]["h"]))
    il = min(range(len(rows)), key=lambda i: float(rows[i]["l"]))
    hi, lo = float(rows[ih]["h"]), float(rows[il]["l"])
    out = [{"label": f"Highest price in available history (since {first})", "kind": "high", "price": hi, "date": str(rows[ih]["t"])[:10]},
           {"label": f"Lowest price in available history (since {first})", "kind": "low", "price": lo, "date": str(rows[il]["t"])[:10]}]
    kept: List[int] = []
    last = lo
    for i in swing_lows(rows):
        if i > il and float(rows[i]["l"]) > last:
            kept.append(i)
            last = float(rows[i]["l"])
    for n in (2, 3):
        if len(kept) >= n:
            i = kept[n - 1]
            out.append({"label": f"Higher bottom #{n} after the low", "kind": "low", "price": float(rows[i]["l"]), "date": str(rows[i]["t"])[:10]})
    for p in pivots:
        if p["name"] in ("Intermediate High", "Breakout Pivot"):
            out.append({"label": f"Minor high: {p['name']}", "kind": "high", "price": p["price"], "date": p["date"]})
        elif p["name"] == "Major Higher Low":
            out.append({"label": f"Minor low: {p['name']}", "kind": "low", "price": p["price"], "date": p["date"]})
    seen, uniq = set(), []
    for a in out:
        key = (a["kind"], a["date"])
        if key not in seen:
            seen.add(key)
            uniq.append(a)
    return uniq


def _marks(limit: int) -> List[int]:
    """Every division of every 144-unit square up to about `limit`: 36, 48, 72, 96, 108, 144, 180, 192, ..."""
    return sorted({144 * k + d for k in range(0, limit // 144 + 2) for d in DIVISIONS})


def sq144(anchors: List[Dict[str, Any]], day: str, ref: float, unit: float, band: float, high_price: Optional[float] = None,
          low_price: Optional[float] = None) -> Dict[str, Any]:
    """Price levels, time marks and the 1x1 diagonal for each anchor, and price-only boxes centred on half the highest price and
    on the middle of the price range (owner-supplied alternatives). Time unit: calendar days, weeks and months."""
    d = date.fromisoformat(day)
    boxes, levels = [], []
    for a in anchors:
        sign = 1 if a["kind"] == "low" else -1
        ad = date.fromisoformat(a["date"])
        e = (d - ad).days
        if e < 0:
            continue
        lv = []
        for m in _marks(int(abs(ref - a["price"]) / unit) + 150):
            p = a["price"] + sign * m * unit
            if p > 0 and abs(p / ref - 1) <= band:
                dv = m % 144 or 144
                lv.append({"price": p, "mark": m, "label": f"Square of 144 from {a['label']}: {m} price units"
                           + (" (grand center, 72)" if dv == 72 else f" (division {dv})")})
        diag = []
        for u, per in (("days", 1), ("weeks", 7)):
            p = a["price"] + sign * (e / per) * unit
            if p > 0 and abs(p / ref - 1) <= band:
                diag.append({"price": p, "label": f"1x1 diagonal from {a['label']} ({u} as time unit)"})
        tm = []
        for unit_name, step in (("days", 1), ("weeks", 7)):
            marks = [m * step for m in _marks(int(e / step) + 150)]
            near = min(marks, key=lambda x: abs(x - e))
            tm.append({"unit": unit_name, "elapsed": round(e / step, 1), "nearest_mark": near // step, "days_away": near - e})
        months = (d.year - ad.year) * 12 + d.month - ad.month
        mm = min(_marks(months + 150), key=lambda x: abs(x - months))
        tm.append({"unit": "months", "elapsed": months, "nearest_mark": mm, "days_away": (_add_months(ad, mm) - d).days})
        boxes.append({**a, "elapsed_days": e, "time_marks": tm, "levels": lv, "diagonals": diag})
        levels += [{"price": x["price"], "label": x["label"]} for x in lv + diag]
    centers = []
    if high_price:
        centers.append(("Half of the highest price", high_price / 2.0))
    if high_price and low_price:
        centers.append(("Middle of the price range", (high_price + low_price) / 2.0))
    for name, c in centers:
        lv = []
        for m in (0,) + DIVISIONS:
            p = c - 72 * unit + m * unit
            if p > 0 and abs(p / ref - 1) <= band:
                lv.append({"price": p, "label": f"Square of 144 centred on {name.lower()} ${c:.2f}: division {m}"
                           + (" (grand center, 72)" if m == 72 else "")})
        boxes.append({"label": name, "kind": "center", "price": c, "date": None, "elapsed_days": None, "time_marks": [], "levels": lv, "diagonals": []})
        levels += lv
    return {"boxes": boxes, "levels": levels}


# ── cosmogram ──
def cosmogram(open_pos: Dict[str, Dict[str, Any]], natal: Dict[str, Dict[str, Any]], aspects: Dict[str, float], top: int = 14) -> Dict[str, Any]:
    """Angles between the planets at the open and to the IPO chart, with the nearest aspect and its distance, tightest first."""
    def sep(a, b):
        return abs((a - b + 180) % 360 - 180)
    rows = []
    allowed = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Moon's Node"}   # the bodies in the PDF's example
    names = [n for n in open_pos if n in allowed]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rows.append(("Sky to sky", a, b, sep(open_pos[a]["lon"], open_pos[b]["lon"])))
        for b in [n for n in natal if n in allowed]:
            rows.append(("Sky to IPO chart", a, b, sep(open_pos[a]["lon"], natal[b]["lon"])))
    out = []
    for kind, a, b, ang in rows:
        asp, tgt = min(aspects.items(), key=lambda kv: abs(ang - kv[1]))
        out.append({"kind": kind, "a": a, "b": b, "angle": round(ang, 2), "aspect": asp, "orb": round(abs(ang - tgt), 2)})
    out.sort(key=lambda r: r["orb"])
    return {"pairs": out[:top],
            "wheel": {"sky": {n: round(open_pos[n]["lon"], 2) for n in names},
                      "ipo": {n: round(natal[n]["lon"], 2) for n in natal if n in allowed}}}
