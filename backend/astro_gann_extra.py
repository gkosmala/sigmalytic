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
  * Cosmogram: PDF pp. 2 and 108 (a circle of planet longitudes and the angles between them), built both ways per the owner's rule:
    the raw wheel (sky against the IPO chart: when) and the price wheel (the price converted to a degree against the sky: where).
    A table of angles with the nearest aspect and its distance, not a forecast.
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
PRICE_ASPECTS = (60.0, 90.0, 120.0, 180.0)


PRICE_ORB = 3.0          # owner-supplied: +/-3 degrees of longitude
TIME_TOLERANCE_DAYS = 1  # owner-supplied: +/-1 trading day


def trading_days_between(a: date, b: date) -> int:
    """Signed weekdays from a to b (holidays are not removed)."""
    step = 1 if b >= a else -1
    n, d = 0, a
    while d != b:
        d += timedelta(days=step)
        if d.weekday() < 5:
            n += step
    return n


AspectOffset = {"conjunction": 0.0, "sextile": 60.0, "square": 90.0, "trine": 120.0, "opposition": 180.0}


def price_wheel(open_pos: Dict[str, Dict[str, Any]], aspects: Dict[str, float], ref: float, unit: float, band: float,
                exact_fn=None, day: Optional[str] = None) -> Dict[str, Any]:
    """Owner-supplied method: the price is converted to a degree (price / unit, minus whole turns of 360; $410 at 1 per degree is 50)
    and placed against the planets. Rows give each planet's angle to the price degree, the nearest aspect and its distance.
    Levels are the prices where a planet at the open would sit in a 60, 90, 120 or 180 degree aspect to the price degree
    (the conjunction levels are the planet lines already in the report)."""
    allowed = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "Moon's Node")
    deg = (ref / unit) % 360.0

    def sep(a, b):
        return abs((a - b + 180) % 360 - 180)
    rows = []
    for n in allowed:
        if n not in open_pos:
            continue
        ang = sep(open_pos[n]["lon"], deg)
        asp, tgt = min(aspects.items(), key=lambda kv: abs(ang - kv[1]))
        row = {"body": n, "lon": round(open_pos[n]["lon"], 2), "angle": round(ang, 2), "aspect": asp, "orb": round(abs(ang - tgt), 2)}
        row["pass_price"] = row["orb"] <= PRICE_ORB
        if exact_fn is not None and day:
            lon = open_pos[n]["lon"]
            # which side of the price degree the planet is on decides whether the exact aspect is at +tgt or -tgt
            off = tgt if ((lon - deg + 180) % 360 - 180) >= 0 else -tgt
            ex = exact_fn(n, deg + off)
            if ex is not None:
                td = trading_days_between(date.fromisoformat(day), ex.date())
                row.update({"exact_et": ex.strftime("%Y-%m-%d %H:%M"), "trading_days": td})
                row["pass_time"] = abs(td) <= TIME_TOLERANCE_DAYS
            else:
                row.update({"exact_et": None, "trading_days": None, "pass_time": False})
            row["square_out"] = bool(row["pass_price"] and row["pass_time"])
        rows.append(row)
    rows.sort(key=lambda r: r["orb"])
    levels = []
    for n in allowed:
        if n not in open_pos:
            continue
        lon = open_pos[n]["lon"]
        for a in PRICE_ASPECTS:
            for off in ({a, -a}):
                k0 = round((ref / unit - lon - off) / 360.0)
                for k in (k0 - 1, k0, k0 + 1):
                    price = (lon + off + 360.0 * k) * unit
                    if price > 0 and abs(price / ref - 1) <= band:
                        levels.append({"price": price, "label": f"{n} {lon:.2f} deg {'+' if off > 0 else '-'} {a:g} deg"})
    levels = sorted({round(x["price"], 4): x for x in levels}.values(), key=lambda x: x["price"])
    return {"price": round(ref, 2), "unit": unit, "degree": round(deg, 2), "pairs": rows, "levels": levels}


def cosmogram(open_pos: Dict[str, Dict[str, Any]], natal: Dict[str, Dict[str, Any]], aspects: Dict[str, float], top: int = 14,
              ref: Optional[float] = None, unit: float = 1.0, band: float = 0.12, exact_fn=None, day: Optional[str] = None) -> Dict[str, Any]:
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
    pw = price_wheel(open_pos, aspects, ref, unit, band, exact_fn, day) if ref else None
    return {"pairs": out[:top], "price_wheel": pw,
            "wheel": {"sky": {n: round(open_pos[n]["lon"], 2) for n in names},
                      "ipo": {n: round(natal[n]["lon"], 2) for n in natal if n in allowed}}}


# ── master confluence (owner-supplied scoring) ──
GEOMETRIC = ("pivot", "sq9", "sq144")                       # price-structure methods
ASTRO = ("transit", "natal", "mean", "price_aspect")        # converted planet-to-price levels
GEOMETRIC_WEIGHT, ASTRO_WEIGHT, MASTER_TOL_PCT = 0.6, 0.4, 0.5


def master_confluence(levels: List[Dict[str, Any]], tol_pct: float = MASTER_TOL_PCT) -> List[Dict[str, Any]]:
    """A cluster counts only if a geometric level and an astrological level are within tol_pct of each other. A cluster is built
    around each geometric level (every level within tol_pct of it). Score = 100 x (0.6 x share of geometric methods present +
    0.4 x share of astrological methods present)."""
    geo = [x for x in levels if x["family"] in GEOMETRIC]
    out, seen = [], set()
    for g in geo:
        mem = [x for x in levels if abs(x["price"] / g["price"] - 1) * 100 <= tol_pct]
        if not any(x["family"] in ASTRO for x in mem):
            continue
        key = tuple(sorted((round(x["price"], 4), x["family"]) for x in mem))
        if key in seen:
            continue
        seen.add(key)
        gf = sorted({x["family"] for x in mem if x["family"] in GEOMETRIC})
        af = sorted({x["family"] for x in mem if x["family"] in ASTRO})
        score = round(100 * (GEOMETRIC_WEIGHT * len(gf) / len(GEOMETRIC) + ASTRO_WEIGHT * len(af) / len(ASTRO)), 1)
        prices = [x["price"] for x in mem]
        out.append({"price": round(sum(prices) / len(prices), 2), "low": round(min(prices), 2), "high": round(max(prices), 2), "score": score,
                    "geometric": gf, "astrological": af, "members": [f"{x['label']} ${x['price']:.2f}" for x in sorted(mem, key=lambda m: m["price"])]})
    return out


# ── natal breakout (owner-supplied method) ──
# Phase 1, the date matrix, counted from the listing date.
CYCLE_DAYS = (("7 days", 7, 7), ("14 days", 14, 14), ("21 days", 21, 21), ("28 days", 28, 28), ("42 days", 42, 42), ("45 days", 45, 45),
              ("49 to 52 days", 49, 52), ("90 to 98 days", 90, 98), ("135 days", 135, 135), ("180 days", 180, 180))
CYCLE_MONTHS = (3, 6, 9, 12)
BREAKOUT_FACTORS = (0.125, 0.25, 0.5, 1.0, 2.0)   # 2.0 = 360 degrees, 1.0 = 180, 0.5 = 90, 0.25 = 45, 0.125 = 22.5


def natal_matrix(ipo_date: str, day: str) -> List[Dict[str, Any]]:
    """Which listing-date cycles the report day falls on. 'once' counts the cycle from the listing date a single time (the literal
    reading); 'repeating' lets the cycle recur (every 7 days, every 3 months...). The text does not say which is meant, so both are shown."""
    d0, d = date.fromisoformat(ipo_date), date.fromisoformat(day)
    n = (d - d0).days
    out = []
    for label, lo, hi in CYCLE_DAYS:
        once = lo <= n <= hi
        rep = n >= lo and (n % lo) <= (hi - lo)      # recurs every `lo` days; a range such as 49 to 52 is a window of (hi - lo + 1) days
        out.append({"cycle": label, "once": once, "repeating": rep})
    months = (d.year - d0.year) * 12 + d.month - d0.month
    for m in CYCLE_MONTHS:
        once = d == _add_months(d0, m)
        rep = any(_add_months(d0, m * k) == d for k in range(1, months // m + 2))
        out.append({"cycle": f"{m}-month anniversary", "once": once, "repeating": rep})
    return [{**r, "days_since_listing": n} for r in out]


def swing_extremes(bars: List[Dict[str, Any]], window: int = SWING_WINDOW) -> Dict[str, Optional[Dict[str, Any]]]:
    """Most recent confirmed swing high and swing low (extreme of +/-window bars) in the bars given. My definition, not Gann's."""
    rows = [b for b in bars if b.get("h") and b.get("l")]
    out: Dict[str, Optional[Dict[str, Any]]] = {"high": None, "low": None}
    for i in range(len(rows) - window - 1, window - 1, -1):
        if out["high"] is None and float(rows[i]["h"]) == max(float(b["h"]) for b in rows[i - window:i + window + 1]):
            out["high"] = {"price": float(rows[i]["h"]), "date": str(rows[i]["t"])[:10]}
        if out["low"] is None and float(rows[i]["l"]) == min(float(b["l"]) for b in rows[i - window:i + window + 1]):
            out["low"] = {"price": float(rows[i]["l"]), "date": str(rows[i]["t"])[:10]}
        if out["high"] and out["low"]:
            break
    return out


def breakout_levels(refs: List[Dict[str, Any]], ref_price: float, band: float) -> List[Dict[str, Any]]:
    """Natal breakout level = (sqrt(reference price) +/- factor)^2, for the factors 0.125 to 2.0."""
    import math
    out = []
    for r in refs:
        root = math.sqrt(r["price"])
        for f in BREAKOUT_FACTORS:
            for sign in (1, -1):
                v = root + sign * f
                if v > 0:
                    p = v * v
                    if abs(p / ref_price - 1) <= band:
                        out.append({"price": p, "label": f"Natal breakout from {r['label']} ${r['price']:.2f}: sqrt {'+' if sign > 0 else '-'} {f:g}"})
    return sorted(out, key=lambda x: x["price"])


def natal_breakout(ipo_date: str, day: str, bars_before: List[Dict[str, Any]], ref_price: float, band: float) -> Dict[str, Any]:
    matrix = natal_matrix(ipo_date, day)
    flag_once = any(m["once"] for m in matrix)
    flag_rep = any(m["repeating"] for m in matrix)
    refs: List[Dict[str, Any]] = []
    lb = next((b for b in bars_before if str(b["t"])[:10] == ipo_date), None)
    if lb:
        refs += [{"label": "Listing-day high", "price": float(lb["h"]), "date": ipo_date}, {"label": "Listing-day low", "price": float(lb["l"]), "date": ipo_date},
                 {"label": "Listing-day close", "price": float(lb["c"]), "date": ipo_date}]
    sw = swing_extremes(bars_before)
    if sw["high"]:
        refs.append({"label": "Latest swing high", **sw["high"]})
    if sw["low"]:
        refs.append({"label": "Latest swing low", **sw["low"]})
    flagged = flag_once or flag_rep
    return {"matrix": matrix, "flag_once": flag_once, "flag_repeating": flag_rep, "references": refs, "listing_bar_found": bool(lb),
            "levels": breakout_levels(refs, ref_price, band) if flagged else []}


def natal_base(ipo_date: str, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Owner-supplied idea: the highs and lows made inside the exact natal windows of the FIRST year after listing become permanent
    support and resistance. For each window (the day counts and month anniversaries) take the highest high and lowest low of the bars
    inside it. A window that falls on a non-trading day uses the next trading bar (my rule). Needs the first-year bars in the
    Alpaca history fetched; windows that cannot be covered are reported as missing."""
    d0 = date.fromisoformat(ipo_date)
    rows = [(date.fromisoformat(str(b["t"])[:10]), b) for b in bars if b.get("h") and b.get("l")]
    have_start = bool(rows) and rows[0][0] <= d0 + timedelta(days=1)

    def window(lo_d: date, hi_d: date):
        inside = [b for d, b in rows if lo_d <= d <= hi_d]
        if not inside:
            nxt = next(((d, b) for d, b in rows if d >= lo_d and (d - lo_d).days <= 5), None)
            inside = [nxt[1]] if nxt else []
        return inside
    out, missing = [], []
    spans = [(label, d0 + timedelta(days=lo), d0 + timedelta(days=hi)) for label, lo, hi in CYCLE_DAYS]
    spans += [(f"{m}-month anniversary", _add_months(d0, m), _add_months(d0, m)) for m in CYCLE_MONTHS]
    for label, a, b in spans:
        w = window(a, b) if have_start else []
        if not w:
            missing.append(label)
            continue
        hi = max(w, key=lambda x: float(x["h"]))
        lo = min(w, key=lambda x: float(x["l"]))
        out.append({"window": label, "from": a.isoformat(), "to": b.isoformat(), "high": float(hi["h"]), "high_date": str(hi["t"])[:10],
                    "low": float(lo["l"]), "low_date": str(lo["t"])[:10]})
    return {"windows": out, "missing": missing, "history_starts_at_listing": have_start}


def natal_base_levels(base: Dict[str, Any], ref_price: float, band: float) -> List[Dict[str, Any]]:
    lv = []
    for w in base.get("windows", []):
        for kind in ("high", "low"):
            p = w[kind]
            if abs(p / ref_price - 1) <= band:
                lv.append({"price": p, "label": f"Natal base {kind} of the {w['window']} window ({w[kind + '_date']})"})
    return sorted(lv, key=lambda x: x["price"])


# ── Gann Fan (owner text) ──
# Angles are price units per time unit: a x b means a price units per b time units. Time unit: one calendar day.
FAN_ANGLES = ((8, 1), (4, 1), (3, 1), (2, 1), (1, 1), (1, 2), (1, 3), (1, 4), (1, 8))
WEEK52_BARS = 252


def rule3_pivots(bars: List[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Latest confirmed trough and peak by the owner's Rule of 3, using only the bars given (no look-ahead).
    Three consecutive bars each making a higher high and a higher low confirm a trough; three each making a lower high
    and a lower low confirm a peak (peak side mirrored by the owner). The pivot is the lowest low (highest high) since the
    previous opposite pivot, up to the bar before the three. A same-side pivot replaces the earlier one only when it is a
    new extreme; otherwise it is ignored. Pivots alternate."""
    rows = [b for b in bars if b.get("h") and b.get("l")]
    h = [float(b["h"]) for b in rows]
    lo = [float(b["l"]) for b in rows]
    last: Optional[Dict[str, Any]] = None
    trough: Optional[Dict[str, Any]] = None
    peak: Optional[Dict[str, Any]] = None
    for i in range(3, len(rows)):
        up = all(h[k] > h[k - 1] and lo[k] > lo[k - 1] for k in (i - 2, i - 1, i))
        dn = all(h[k] < h[k - 1] and lo[k] < lo[k - 1] for k in (i - 2, i - 1, i))
        if not (up or dn):
            continue
        start = last["idx"] + 1 if last else 0
        if i - 3 < start:
            continue
        if up:
            j = min(range(start, i - 2), key=lambda x: lo[x])
            if last is None or last["kind"] == "peak" or lo[j] < last["price"]:
                last = trough = {"kind": "trough", "idx": j, "price": lo[j], "date": str(rows[j]["t"])[:10], "confirmed": str(rows[i]["t"])[:10]}
        else:
            j = max(range(start, i - 2), key=lambda x: h[x])
            if last is None or last["kind"] == "trough" or h[j] > last["price"]:
                last = peak = {"kind": "peak", "idx": j, "price": h[j], "date": str(rows[j]["t"])[:10], "confirmed": str(rows[i]["t"])[:10]}
    return {"trough": trough, "peak": peak}


def fan_anchors(bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Master anchors (highest high and lowest low of the history, and of the last 52 weeks) plus the most recent confirmed
    Rule-of-3 trough and peak. `bars` are the daily bars before the report day."""
    rows = [b for b in bars if b.get("h") and b.get("l")]
    if len(rows) < 60:
        return []
    out = []
    for key, sub, tag in (("hist", rows, "history"), ("w52", rows[-WEEK52_BARS:], "52 weeks")):
        ih = max(range(len(sub)), key=lambda i: float(sub[i]["h"]))
        il = min(range(len(sub)), key=lambda i: float(sub[i]["l"]))
        out.append({"key": f"{key}_high", "label": f"Highest high of the {tag}", "kind": "high", "price": float(sub[ih]["h"]), "date": str(sub[ih]["t"])[:10]})
        out.append({"key": f"{key}_low", "label": f"Lowest low of the {tag}", "kind": "low", "price": float(sub[il]["l"]), "date": str(sub[il]["t"])[:10]})
    piv = rule3_pivots(rows)
    if piv["trough"]:
        out.append({"key": "recent_trough", "label": "Latest confirmed trough (Rule of 3)", "kind": "low", **{k: piv["trough"][k] for k in ("price", "date", "confirmed")}})
    if piv["peak"]:
        out.append({"key": "recent_peak", "label": "Latest confirmed peak (Rule of 3)", "kind": "high", **{k: piv["peak"][k] for k in ("price", "date", "confirmed")}})
    return out


def fan_price(anchor: Dict[str, Any], a: int, b: int, day: str, unit: float) -> Optional[float]:
    """Value on `day` of the a x b ray from the anchor: up from a trough or low, down from a peak or high."""
    e = (date.fromisoformat(day) - date.fromisoformat(anchor["date"])).days
    if e <= 0:
        return None
    return anchor["price"] + (1 if anchor["kind"] == "low" else -1) * (a / b) * e * unit


def gann_fan(bars: List[Dict[str, Any]], day: str, unit: float) -> Dict[str, Any]:
    """Every ray of every anchor on `day`; no distance filter (a ray only drops out if its price is not above zero)."""
    anchors = fan_anchors(bars)
    lines, seen = [], set()
    for an in anchors:
        k = (an["kind"], an["date"])
        if k in seen:
            continue
        seen.add(k)
        for a, b in FAN_ANGLES:
            p = fan_price(an, a, b, day, unit)
            if p is not None and p > 0:
                lines.append({"price": p, "angle": f"{a}x{b}", "label": f"{a}x{b} from {an['label']} ({an['date']}, ${an['price']:.2f})"})
    return {"anchors": anchors, "lines": lines}
