# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
Moving Average Study (Admin only): how a symbol has behaved around one simple moving average, from Alpaca daily bars.

Answers, for any symbol and MA length (default 20):
  * how many times price crossed the MA, and how much of its history it spent above vs below;
  * once it crossed, how many days it stayed on that side (distribution, median, longest, whipsaw share);
  * whether crossings on heavy volume lasted longer or followed through better than crossings on light volume;
  * what happened 5, 10 and 20 days after each cross;
  * the MA's own trend now (slope, and its position against the 50- and 200-day averages);
  * where the current run sits against history, and what volume has done during it.

A "day above" is a close above that day's MA (computed from that day and the previous length-1 closes).
Research output only.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

HEAVY, LIGHT = 1.5, 1.0          # relative-volume thresholds for a heavy / light crossing day
FOLLOW = (5, 10, 20)
BUCKETS = ((1, 1), (2, 3), (4, 10), (11, 20), (21, 50), (51, 10_000))
_cache: Dict[tuple, tuple] = {}


def _sma(xs: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or not b else (a / b - 1) * 100


def _stats(xs: List[float]) -> Dict[str, Any]:
    if not xs:
        return {"count": 0}
    xs = sorted(xs)
    return {"count": len(xs), "median": statistics.median(xs), "mean": round(sum(xs) / len(xs), 2),
            "p75": xs[int(0.75 * (len(xs) - 1))], "max": xs[-1]}


def _follow_stats(rets: List[float]) -> Dict[str, Any]:
    if not rets:
        return {"count": 0}
    return {"count": len(rets), "median_pct": round(statistics.median(rets), 2),
            "positive_share": round(sum(1 for r in rets if r > 0) / len(rets), 3)}


def analyze(symbol: str, bars: List[dict], length: int = 20) -> Dict[str, Any]:
    bars = sorted(bars, key=lambda b: str(b["t"]))
    dates = [str(b["t"])[:10] for b in bars]
    c = [float(b["c"]) for b in bars]
    v = [float(b.get("v") or 0) for b in bars]
    n = len(c)
    if n < length + 40:
        raise ValueError(f"Not enough daily history for {symbol} ({n} bars) to study a {length}-day average.")
    ma, ma50, ma200 = _sma(c, length), _sma(c, 50), _sma(c, 200)
    vavg = [None] * n                                   # average volume of the 20 sessions before each day
    for i in range(20, n):
        w = v[i - 20:i]
        vavg[i] = sum(w) / 20 if sum(w) else None
    rel = [(v[i] / vavg[i]) if vavg[i] else None for i in range(n)]

    first = length - 1
    side = [None] * n
    for i in range(first, n):
        if c[i] > ma[i]:
            side[i] = 1
        elif c[i] < ma[i]:
            side[i] = -1
        else:
            side[i] = side[i - 1] if i > first else 1     # a close exactly on the MA keeps the previous side

    runs: List[Dict[str, Any]] = []
    start = first
    for i in range(first + 1, n + 1):
        if i == n or side[i] != side[start]:
            end = i - 1
            seg_rel = [r for r in rel[start:end + 1] if r is not None]
            runs.append({"side": "above" if side[start] == 1 else "below", "start": dates[start], "end": dates[end],
                         "s": start, "e": end, "days": end - start + 1,
                         "cross_rel_volume": rel[start], "avg_rel_volume": (sum(seg_rel) / len(seg_rel)) if seg_rel else None,
                         "return_pct": _pct(c[end], c[start - 1] if start > 0 else c[start]),
                         "ongoing": i == n})
            start = i
    crosses = runs[1:]                                   # the first run starts with the data, not with a crossing
    done = [r for r in crosses if not r["ongoing"]]

    def by_side(rs, s):
        return [r for r in rs if r["side"] == s]

    def lengths(rs):
        return [r["days"] for r in rs]

    def buckets(rs):
        return [{"range": f"{a}" if a == b else (f"{a}+" if b >= 10_000 else f"{a}-{b}"),
                 "count": sum(1 for r in rs if a <= r["days"] <= b)} for a, b in BUCKETS]

    def volume_split(rs):
        heavy = [r["days"] for r in rs if (r["cross_rel_volume"] or 0) >= HEAVY]
        light = [r["days"] for r in rs if r["cross_rel_volume"] is not None and r["cross_rel_volume"] < LIGHT]
        return {"heavy_cross": _stats(heavy), "light_cross": _stats(light)}

    def follow(rs, lead):
        out = {}
        for h in FOLLOW:
            all_r, heavy, light = [], [], []
            for r in rs:
                i = r["s"]
                if i + h < n:
                    x = _pct(c[i + h], c[i])
                    all_r.append(x)
                    cr = r["cross_rel_volume"]
                    if cr is not None and cr >= HEAVY:
                        heavy.append(x)
                    elif cr is not None and cr < LIGHT:
                        light.append(x)
            out[f"{h}d"] = {"all": _follow_stats(all_r), "heavy_cross": _follow_stats(heavy), "light_cross": _follow_stats(light)}
        return out

    sides = {}
    for s in ("above", "below"):
        rs_done, rs_all = by_side(done, s), by_side(crosses, s)
        sides[s] = {
            "crossings_into": len(rs_all),
            "days_total": sum(1 for x in side[first:] if x == (1 if s == "above" else -1)),
            "run_days": _stats(lengths(rs_done)),
            "whipsaw_share": round(sum(1 for r in rs_done if r["days"] <= 2) / len(rs_done), 3) if rs_done else None,
            "buckets": buckets(rs_done),
            "volume": volume_split(rs_done),
            "avg_rel_volume_during": round(statistics.mean([r["avg_rel_volume"] for r in rs_done if r["avg_rel_volume"]]), 2)
            if any(r["avg_rel_volume"] for r in rs_done) else None,
            "follow_through": follow(rs_all, s),
            "longest": max(rs_done, key=lambda r: r["days"], default=None),
        }
        if sides[s]["longest"]:
            L = sides[s]["longest"]
            sides[s]["longest"] = {"days": L["days"], "start": L["start"], "end": L["end"], "return_pct": L["return_pct"]}
    studied = n - first

    cur = runs[-1]
    same = lengths(by_side(done, cur["side"]))
    last = n - 1
    trend = {
        "ma": round(ma[last], 2), "ma_5d_change_pct": _pct(ma[last], ma[last - 5]),
        "ma_20d_change_pct": _pct(ma[last], ma[last - 20]) if last - 20 >= first else None,
        "ma_rising_days_last_60": sum(1 for i in range(max(first + 1, last - 59), last + 1) if ma[i] > ma[i - 1]),
        "ma50": round(ma50[last], 2) if ma50[last] else None, "ma200": round(ma200[last], 2) if ma200[last] else None,
        "close": c[last], "close_vs_ma_pct": _pct(c[last], ma[last]),
    }
    if trend["ma50"] and trend["ma200"]:
        order = sorted([("close", c[last]), (f"{length}-day", ma[last]), ("50-day", ma50[last]), ("200-day", ma200[last])],
                       key=lambda kv: -kv[1])
        trend["stack_high_to_low"] = [k for k, _ in order]
    seg = [r for r in rel[cur["s"]:last + 1] if r is not None]
    current = {
        "side": cur["side"], "since": cur["start"], "days": cur["days"],
        "cross_rel_volume": cur["cross_rel_volume"], "avg_rel_volume_during": (sum(seg) / len(seg)) if seg else None,
        "latest_rel_volume": rel[last],
        "longer_than_share_of_past_runs": round(sum(1 for d in same if d < cur["days"]) / len(same), 3) if same else None,
        "return_since_cross_pct": cur["return_pct"],
    }
    recent = [{k: r[k] for k in ("side", "start", "end", "days", "cross_rel_volume", "return_pct", "ongoing")}
              for r in runs[-12:]][::-1]
    return {"symbol": symbol, "length": length, "first_date": dates[0], "last_date": dates[-1],
            "studied_days": studied, "crossings": len(crosses), "sides": sides, "trend": trend, "current": current,
            "recent_runs": recent}


def summary_text(r: Dict[str, Any]) -> str:
    """Plain-text version for copying into a chat or a report."""
    def f(x, d=2, suf=""):
        return "n/a" if x is None else f"{x:.{d}f}{suf}"
    L, s, t, cu = r["length"], r["sides"], r["trend"], r["current"]
    lines = [f"{r['symbol']} {L}-day moving average study, daily bars {r['first_date']} to {r['last_date']} "
             f"({r['studied_days']} sessions studied). Source: Alpaca.",
             f"Crossings: {r['crossings']}. Days above: {s['above']['days_total']}, days below: {s['below']['days_total']}."]
    for k in ("above", "below"):
        x = s[k]
        rd = x["run_days"]
        lines.append(f"Runs {k}: {rd.get('count', 0)} completed; median {f(rd.get('median'), 1)} days, mean {f(rd.get('mean'), 1)}, "
                     f"75th pct {rd.get('p75', 'n/a')}, longest {rd.get('max', 'n/a')}; 1-2 day whipsaws {f((x['whipsaw_share'] or 0) * 100, 0, '%')}.")
        lines.append("  Length buckets: " + ", ".join(f"{b['range']}d: {b['count']}" for b in x["buckets"]))
        vh, vl = x["volume"]["heavy_cross"], x["volume"]["light_cross"]
        lines.append(f"  Cross on heavy volume (>= {HEAVY}x): {vh.get('count', 0)} runs, median {f(vh.get('median'), 1)} days. "
                     f"Cross on light volume (< {LIGHT}x): {vl.get('count', 0)} runs, median {f(vl.get('median'), 1)} days. "
                     f"Avg relative volume during {k} runs: {f(x['avg_rel_volume_during'])}x.")
        for h, d in x["follow_through"].items():
            a, hv, lv = d["all"], d["heavy_cross"], d["light_cross"]
            lines.append(f"  {h} after crossing {k}: median {f(a.get('median_pct'), 2, '%')}, positive {f((a.get('positive_share') or 0) * 100, 0, '%')} "
                         f"(n={a.get('count', 0)}); heavy-volume crosses {f(hv.get('median_pct'), 2, '%')} (n={hv.get('count', 0)}); "
                         f"light-volume {f(lv.get('median_pct'), 2, '%')} (n={lv.get('count', 0)}).")
        if x["longest"]:
            lg = x["longest"]
            lines.append(f"  Longest {k} run: {lg['days']} days, {lg['start']} to {lg['end']}, {f(lg['return_pct'], 1, '%')}.")
    lines.append(f"MA trend: {L}-day MA {f(t['ma'])}, 5-day change {f(t['ma_5d_change_pct'], 2, '%')}, 20-day change "
                 f"{f(t['ma_20d_change_pct'], 2, '%')}, rising on {t['ma_rising_days_last_60']} of the last 60 days. "
                 f"50-day {f(t['ma50'])}, 200-day {f(t['ma200'])}. Stack (high to low): {', '.join(t.get('stack_high_to_low') or [])}.")
    lines.append(f"Current: {cu['side']} the {L}-day since {cu['since']} ({cu['days']} days), "
                 f"{f(t['close_vs_ma_pct'], 2, '%')} from the MA; crossed on {f(cu['cross_rel_volume'])}x volume; average "
                 f"{f(cu['avg_rel_volume_during'])}x since; latest {f(cu['latest_rel_volume'])}x. Longer than "
                 f"{f((cu['longer_than_share_of_past_runs'] or 0) * 100, 0, '%')} of past {cu['side']} runs. "
                 f"Return since the cross {f(cu['return_since_cross_pct'], 2, '%')}.")
    lines.append("Recent runs (newest first): " + "; ".join(
        f"{x['side']} {x['start']}-{x['end']} {x['days']}d {f(x['return_pct'], 1, '%')} cross vol {f(x['cross_rel_volume'])}x"
        + (" (ongoing)" if x["ongoing"] else "") for x in r["recent_runs"]))
    return "\n".join(lines)


def build(symbol: str, length: int = 20, years: int = 10) -> Dict[str, Any]:
    from backend import broker_market_data as bmd
    symbol, length, years = symbol.strip().upper(), max(5, min(int(length or 20), 200)), max(1, min(int(years or 10), 20))
    key = (symbol, length, years)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 3 * 3600:
        return {**hit[1], "cached": True}
    end = datetime.now(timezone.utc)
    bars = bmd.fetch_daily_bars([symbol], end - timedelta(days=int(365.25 * years) + 10), end).get(symbol) or []
    if not bars:
        raise ValueError(f"Alpaca returned no daily bars for {symbol}.")
    out = analyze(symbol, bars, length)
    out["text"] = summary_text(out)
    _cache[key] = (time.time(), out)
    return out
