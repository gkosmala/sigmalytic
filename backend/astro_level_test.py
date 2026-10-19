# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research level test (owner only): do the report's price zones and bands behave differently from random levels?

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
  * Baseline: for every real level, a random level at the same distance from the prior close (distances drawn from the real
    pool, random side). Repeated `draws` times; the p-value is the share of baseline runs at least as far from the baseline
    mean as the real result.
"""
from __future__ import annotations

import random
from typing import Any, Callable, Dict, List, Optional

FOLLOW_DAYS = 5
MIN_HISTORY = 130


PRICE_FAMILIES = {"Pivot", "Square of 9"}
GROUPS = (("zone_price", "Zones made only of price-history methods (pivots, Square of 9)"),
          ("zone_planet", "Zones made only of planet methods"),
          ("zone_mixed", "Zones mixing price-history and planet methods"),
          ("band", "Mean/Cycle bands"))


def _zone_group(z: Dict[str, Any]) -> str:
    fams = set(z.get("families", []))
    return "zone_price" if fams <= PRICE_FAMILIES else ("zone_mixed" if fams & PRICE_FAMILIES else "zone_planet")


def _levels(rep: Dict[str, Any], kinds=("zone", "band")) -> List[Dict[str, Any]]:
    out = []
    for z in rep.get("top_zones", []):
        if "zone" in kinds or _zone_group(z) in kinds:
            out.append({"kind": "zone", "lo": float(z["price"]), "hi": float(z["price"])})
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
               max_days: int = 400, draws: int = 300, seed: int = 11, kinds=("zone", "band"), step: int = 1) -> Dict[str, Any]:
    n = len(bars)
    first = max(MIN_HISTORY, start_index if start_index is not None else n - max_days - FOLLOW_DAYS)
    days = list(range(first, n - FOLLOW_DAYS, max(1, int(step))))
    per_day = []
    pool: List[float] = []
    skipped = 0
    for i in days:
        try:
            rep = report_fn(str(bars[i]["t"])[:10])
        except Exception:
            skipped += 1
            continue
        lvs = _levels(rep, kinds)
        ref = float(bars[i - 1]["c"])
        for lv in lvs:
            pool.append(abs((lv["lo"] + lv["hi"]) / 2 / ref - 1))
        per_day.append((i, ref, lvs))
    if not pool:
        return {"error": "No levels were produced in the test window."}
    real = []
    for i, ref, lvs in per_day:
        for lv in lvs:
            r = classify(lv, ref, bars[i], float(bars[i + FOLLOW_DAYS]["c"]))
            if r:
                real.append(r)
    rng = random.Random(seed)

    def baseline_once() -> List[Dict[str, Any]]:
        rows = []
        for i, ref, lvs in per_day:
            for lv in lvs:
                d = rng.choice(pool) * rng.choice((-1, 1))
                p = ref * (1 + d)
                half = (lv["hi"] - lv["lo"]) / 2
                r = classify({"kind": lv["kind"], "lo": p - half, "hi": p + half}, ref, bars[i], float(bars[i + FOLLOW_DAYS]["c"]))
                if r:
                    rows.append(r)
        return rows

    runs = [_stats(baseline_once()) for _ in range(draws)]
    rs = _stats(real)
    out: Dict[str, Any] = {"days_tested": len(per_day), "days_skipped": skipped, "levels_total": len(pool),
                           "first_day": str(bars[per_day[0][0]]["t"])[:10], "last_day": str(bars[per_day[-1][0]]["t"])[:10],
                           "follow_days": FOLLOW_DAYS, "step": max(1, int(step)), "kinds": list(kinds), "real": rs, "draws": draws, "metrics": []}
    for key, label in (("through_pct", "Closed through the level (% of touches)"), ("reversal_pct", "Reversed at the level (% of touches)"),
                       ("follow_mean_pct", f"Mean {FOLLOW_DAYS}-day follow-through, all touches (%)"),
                       ("through_follow_mean_pct", f"Mean {FOLLOW_DAYS}-day follow-through after a close through (%)")):
        vals = [r[key] for r in runs if r.get(key) is not None]
        if rs.get(key) is None or len(vals) < 20:
            out["metrics"].append({"label": label, "real": None, "baseline": None, "p_value": None})
            continue
        mu = sum(vals) / len(vals)
        p = (1 + sum(abs(v - mu) >= abs(rs[key] - mu) for v in vals)) / (1 + len(vals))
        out["metrics"].append({"label": label, "real": round(rs[key], 2), "baseline": round(mu, 2), "p_value": round(p, 3)})
    out["touches_real"] = rs["touches"]
    out["touches_baseline_mean"] = round(sum(r["touches"] for r in runs) / len(runs), 1)
    out["caveat"] = ("Daily bars only: a touch and its outcome are judged on one day's open, range and close, so intraday detail is not "
                     "seen. Thresholds were fixed before the run. A result near the baseline means the levels add nothing measurable; "
                     "a result that differs is a pattern in past data, not a forecast. Touches on neighbouring days overlap, so the p-value is optimistic.")
    return out


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
