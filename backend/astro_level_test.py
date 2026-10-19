# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research level test (owner only): what happened on real past days at the report's levels? Historical bars only.

Definitions are fixed before any run and are not tuned to results:
  * Each trading day D, the report is built from data before D only (no look-ahead).
  * Levels: confluence zones (a point) and Mean of Five / Cycle of Eight bands (a range).
  * Touch: the day's range reaches the level (near edge of a band) and the open was on the near side. Approach is up if the
    level is above the prior close, down if below.
  * Outcome from D's close: THROUGH (closed beyond the level / far edge), REVERSAL (closed back on the near side),
    STALLED (closed inside a band).
  * Follow-through: percent move from D's close to the close FOLLOW_DAYS later, in the approach direction.
  * `kinds` limits the test to confluence zones, bands, or both. Zones include price-history levels (pivots, Square of 9), so
    they are not random with respect to past prices; bands come from the planets alone and isolate the astro part.
  * No simulated or random levels are used. Every number comes from the actual daily bars.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

FOLLOW_DAYS = 5
MIN_HISTORY = 130


PRICE_FAMILIES = {"Pivot", "Square of 9"}
GROUPS = (("zone_price", "Zones made only of price-history methods (pivots, Square of 9)"),
          ("zone_planet", "Zones made only of planet methods"),
          ("zone_mixed", "Zones mixing price-history and planet methods"),
          ("master", "Master confluence (geometric + astrological within 0.5%)"),
          ("band", "Mean/Cycle bands"))


def _zone_group(z: Dict[str, Any]) -> str:
    fams = set(z.get("families", []))
    return "zone_price" if fams <= PRICE_FAMILIES else ("zone_mixed" if fams & PRICE_FAMILIES else "zone_planet")


def _levels(rep: Dict[str, Any], kinds=("zone", "band")) -> List[Dict[str, Any]]:
    out = []
    for z in rep.get("top_zones", []):
        if "zone" in kinds or _zone_group(z) in kinds:
            out.append({"kind": "zone", "lo": float(z["price"]), "hi": float(z["price"])})
    if "master" in kinds:
        out += [{"kind": "zone", "lo": float(z["price"]), "hi": float(z["price"])} for z in rep.get("master_zones", [])]
    if "band" in kinds:
        out += [{"kind": "band", "lo": float(b["low"]), "hi": float(b["high"])} for b in rep.get("top_bands", [])]
    return out


def classify(lv: Dict[str, Any], ref: float, bar: Dict[str, Any], close_after: Optional[float]) -> Optional[Dict[str, Any]]:
    """Outcome of one level on one day, or None when the level was not touched."""
    o, h, l, c = float(bar["o"]), float(bar["h"]), float(bar["l"]), float(bar["c"])
    up = lv["lo"] > ref
    near, far = (lv["lo"], lv["hi"]) if up else (lv["hi"], lv["lo"])
    if up:
        if not (o < near <= h):
            return None
        res = "through" if c > far else ("stalled" if c >= near else "reversal")
    else:
        if not (l <= near < o):
            return None
        res = "through" if c < far else ("stalled" if c <= near else "reversal")
    ft = None
    if close_after is not None and c > 0:
        ft = (close_after / c - 1) * 100 * (1 if up else -1)
    return {"result": res, "follow": ft}


def _stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if not n:
        return {"touches": 0}
    fo = [r["follow"] for r in rows if r["follow"] is not None]
    th = [r["follow"] for r in rows if r["result"] == "through" and r["follow"] is not None]
    return {"touches": n,
            "through_pct": 100 * sum(r["result"] == "through" for r in rows) / n,
            "reversal_pct": 100 * sum(r["result"] == "reversal" for r in rows) / n,
            "follow_mean_pct": sum(fo) / len(fo) if fo else None,
            "through_follow_mean_pct": sum(th) / len(th) if th else None,
            "through_follow_n": len(th)}


def level_test(bars: List[Dict[str, Any]], report_fn: Callable[[str], Dict[str, Any]], start_index: Optional[int] = None,
               max_days: int = 400, kinds=("zone", "band"), step: int = 1) -> Dict[str, Any]:
    n = len(bars)
    first = max(MIN_HISTORY, start_index if start_index is not None else n - max_days - FOLLOW_DAYS)
    days = list(range(first, n - FOLLOW_DAYS, max(1, int(step))))
    per_day = []
    total = 0
    skipped = 0
    for i in days:
        try:
            rep = report_fn(str(bars[i]["t"])[:10])
        except Exception:
            skipped += 1
            continue
        lvs = _levels(rep, kinds)
        total += len(lvs)
        per_day.append((i, float(bars[i - 1]["c"]), lvs))
    if not total:
        return {"error": "No levels were produced in the test window."}
    real = []
    for i, ref, lvs in per_day:
        for lv in lvs:
            r = classify(lv, ref, bars[i], float(bars[i + FOLLOW_DAYS]["c"]))
            if r:
                real.append(r)
    rs = _stats(real)
    out: Dict[str, Any] = {"days_tested": len(per_day), "days_skipped": skipped, "levels_total": total,
                           "first_day": str(bars[per_day[0][0]]["t"])[:10], "last_day": str(bars[per_day[-1][0]]["t"])[:10],
                           "follow_days": FOLLOW_DAYS, "step": max(1, int(step)), "kinds": list(kinds), "real": rs, "metrics": _metrics(rs)}
    out["touches_real"] = rs["touches"]
    out["caveat"] = ("Daily bars only: a touch and its outcome are judged on one day's open, range and close, so intraday detail is not "
                     "seen. Thresholds were fixed before the run. Results are a record of past days, not a forecast.")
    return out


def _metrics(rs: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for key, label in (("through_pct", "Closed through the level (% of touches)"), ("reversal_pct", "Reversed at the level (% of touches)"),
                       ("follow_mean_pct", f"Mean {FOLLOW_DAYS}-day follow-through, all touches (%)"),
                       ("through_follow_mean_pct", f"Mean {FOLLOW_DAYS}-day follow-through after a close through (%)")):
        rows.append({"label": label, "real": None if rs.get(key) is None else round(rs[key], 2)})
    return rows


def level_test_groups(bars: List[Dict[str, Any]], report_fn: Callable[[str], Dict[str, Any]], **kw) -> Dict[str, Any]:
    """The same test run separately for each source group, building each day's report once."""
    cache: Dict[str, Dict[str, Any]] = {}

    def cached(d: str) -> Dict[str, Any]:
        if d not in cache:
            cache[d] = report_fn(d)
        return cache[d]

    out = []
    for key, label in GROUPS:
        res = level_test(bars, cached, kinds=(key,), **kw)
        out.append({"group": key, "label": label, **res})
    return {"groups": out}


FAMILIES = (("pivot", "Pivots (daily and weekly highs and lows)"), ("sq9", "Square of 9 levels from the pivots"),
            ("natal", "Natal planet lines"), ("transit", "Transit planet lines at the open"),
            ("mean", "Mean of Five / Cycle of Eight lines"),
            ("sq144", "Square of 144 levels and diagonals"), ("numerology", "Numerology levels (digit sum, multiples, ends in 9, 144)"),
            ("price_aspect", "Price-wheel levels (a planet aspecting the price degree)"),
            ("natal_breakout", "Natal breakout levels (only on natal-window days)"),
            ("natal_base", "Natal base levels (highs and lows of the first-year natal windows)"))


def family_test(bars: List[Dict[str, Any]], report_fn: Callable[[str], Dict[str, Any]], max_days: int = 400,
                step: int = 1) -> Dict[str, Any]:
    """Each level family on its own (every level in range, no confluence step), on actual daily bars only.
    Planet-line families use the positions at the 9:30 open, which are known before the session."""
    import numpy as np
    n = len(bars)
    first = max(MIN_HISTORY, n - max_days - FOLLOW_DAYS)
    day_idx = list(range(first, n - FOLLOW_DAYS, max(1, int(step))))
    rows = {f: [] for f, _ in FAMILIES}   # (day position, price)
    refs, ob, hb, lb, cb, ca, used = [], [], [], [], [], [], []
    for i in day_idx:
        try:
            rep = report_fn(str(bars[i]["t"])[:10])
        except Exception:
            continue
        k = len(used)
        used.append(i)
        refs.append(float(bars[i - 1]["c"])); ob.append(float(bars[i]["o"])); hb.append(float(bars[i]["h"]))
        lb.append(float(bars[i]["l"])); cb.append(float(bars[i]["c"])); ca.append(float(bars[i + FOLLOW_DAYS]["c"]))
        for f, _ in FAMILIES:
            for pr in rep.get("raw_levels", {}).get(f, []):
                rows[f].append((k, pr))
    if not used:
        return {"error": "No days could be tested."}
    refs, ob, hb, lb, cb, ca = (np.array(a) for a in (refs, ob, hb, lb, cb, ca))

    def outcome(day, price):
        r, o, h, l, c, a = refs[day], ob[day], hb[day], lb[day], cb[day], ca[day]
        up = price > r
        touch = np.where(up, (o < price) & (price <= h), (l <= price) & (price < o))
        thru = np.where(up, c > price, c < price)
        rev = np.where(up, c < price, c > price)
        fol = (a / c - 1) * 100 * np.where(up, 1, -1)
        return touch, thru, rev, fol

    def summarize(touch, thru, rev, fol):
        t = int(touch.sum())
        if not t:
            return {"touches": 0}
        tt = touch & thru
        return {"touches": t, "through_pct": 100 * tt.sum() / t, "reversal_pct": 100 * (touch & rev).sum() / t,
                "follow_mean_pct": float(fol[touch].mean()),
                "through_follow_mean_pct": float(fol[tt].mean()) if tt.any() else None}

    out = []
    for f, label in FAMILIES:
        lv = rows[f]
        if not lv:
            out.append({"label": label, "error": "no levels in range"})
            continue
        day = np.array([d for d, _ in lv]); price = np.array([p for _, p in lv])
        real = summarize(*outcome(day, price))
        out.append({"label": label, "kinds": [f], "days_tested": len(used), "step": max(1, int(step)),
                    "first_day": str(bars[used[0]]["t"])[:10], "last_day": str(bars[used[-1]]["t"])[:10],
                    "touches_real": real["touches"], "levels_total": len(lv), "metrics": _metrics(real),
                    "caveat": "Daily bars only. Every level of this family in range is tested on its own, with no confluence step. "
                              "A record of past days, not a forecast."})
    return {"groups": out}
