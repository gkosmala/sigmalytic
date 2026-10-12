# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/content_chart.py
------------------------
Draws the share image (Open Graph / social card) for a Content Hub report: daily candles, 20/50/200-day averages,
volume, the nearest reference levels as price tags, and three summary panels. Every number on the image comes from
the same `facts` the blog was written from, so the picture cannot disagree with the text.

Output is 1800 x 945 (the 1.91:1 shape social sites use; it downsizes cleanly to 1200 x 630).
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

W, H, DPI = 1800, 945, 100
BG, PANEL, GRID = "#0a1530", "#0d1c3d", "#1e2f57"
UP, DOWN = "#22c55e", "#ef4444"
TXT, MUTED, GOLD, BLUE, CYAN = "#e8eefc", "#8fa3cc", "#f5b82e", "#2f6bff", "#38bdf8"
MAX_BARS = 120


def _m(v: float) -> str:
    return f"\\${v:,.2f}"


def _short(label: str) -> str:
    return (str(label).replace("swing high", "high").replace("swing low", "low").replace("largest ", "")
            .replace("open-interest strike", "OI strike").replace("estimated ", ""))


def _sma(vals: Sequence[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for i in range(len(vals)):
        out.append(sum(vals[i - n + 1:i + 1]) / n if i >= n - 1 else None)
    return out


def _date_label(d: str) -> str:
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return d


def render_share_image(facts: Dict[str, Any], bars: List[Sequence[Any]]) -> bytes:
    """bars: [[date, open, high, low, close, volume], ...] oldest first. Returns PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    if len(bars) < 30:
        raise ValueError("Not enough bars to draw the share image.")
    d = [str(b[0])[:10] for b in bars]
    o, h, l, c = ([float(b[i]) for b in bars] for i in (1, 2, 3, 4))
    v = [float(b[5] or 0) for b in bars]
    s20, s50, s200 = _sma(c, 20), _sma(c, 50), _sma(c, 200)
    n = min(MAX_BARS, len(bars))
    sl = slice(len(bars) - n, len(bars))
    x = list(range(n))
    O, Hh, L, C, V = o[sl], h[sl], l[sl], c[sl], v[sl]

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)
    sym, last = facts["symbol"], facts["last_close"]
    ch1 = facts.get("change_1d_pct")
    fig.text(0.03, 0.935, "SIGMALYTIC QUANT CORPORATION  ·  MARKET STRUCTURE REPORT", color=GOLD, fontsize=15, fontweight="bold")
    t_px = fig.text(0.03, 0.865, f"{sym}  {_m(last)}", color=TXT, fontsize=40, fontweight="bold")
    if ch1 is not None:
        right_edge = t_px.get_window_extent(fig.canvas.get_renderer()).x1 / W
        fig.text(right_edge + 0.012, 0.8665, f"{ch1:+.2f}%", color=UP if ch1 >= 0 else DOWN, fontsize=26, fontweight="bold")
    fig.text(0.97, 0.935, f"Daily chart · Market data through {_date_label(facts['as_of'])}", color=MUTED, fontsize=15, ha="right")

    ax = fig.add_axes([0.03, 0.40, 0.84, 0.43], facecolor=PANEL)
    axv = fig.add_axes([0.03, 0.335, 0.84, 0.065], facecolor=PANEL, sharex=ax)
    levels = facts.get("levels") or {}
    near = lambda p: abs(p - last) / last <= 0.14
    above = [x_ for x_ in (levels.get("above") or [])[:3] if near(x_["price"])]
    below = [x_ for x_ in (levels.get("below") or [])[:3] if near(x_["price"])]
    lo = min(L + [y["price"] for y in below] + [last]) * 0.985
    hi = max(Hh + [y["price"] for y in above] + [last]) * 1.015
    ax.set_xlim(-2, n + 13)
    ax.set_ylim(lo, hi)
    ax.grid(color=GRID, linewidth=0.8, alpha=0.8)
    for xi in x:
        col = UP if C[xi] >= O[xi] else DOWN
        ax.vlines(xi, L[xi], Hh[xi], color=col, linewidth=1.3, zorder=3)
        ax.bar(xi, abs(C[xi] - O[xi]) or (hi - lo) * 0.0008, bottom=min(O[xi], C[xi]), width=0.68, color=col, zorder=4)
    for series, col, name in ((s20, GOLD, "20-day"), (s50, CYAN, "50-day"), (s200, "#ffffff", "200-day")):
        pts = [(i, series[len(bars) - n + i]) for i in x if series[len(bars) - n + i] is not None]
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, linewidth=2.2, zorder=5, label=name)
    ax.legend(loc="lower right", frameon=False, labelcolor=TXT, fontsize=13, ncol=3)
    tags = [(y["price"], f" {_m(y['price'])}  {_short(y['label'])}", color, "white") for y, color in
            [(y, DOWN) for y in above] + [(y, BLUE) for y in below]] + [(last, f" {_m(last)}  last close", UP, "#04210f")]
    for price, _t, color, _c in tags:
        ax.axhline(price, color=color, linestyle=(0, (6, 5)) if color != UP else "-", linewidth=1.4, alpha=0.9, zorder=2)
    gap, placed = (hi - lo) * 0.058, []
    for price, text, color, fcol in sorted(tags, key=lambda t: -t[0]):
        y = price if not placed else min(price, placed[-1] - gap)
        placed.append(y)
        ax.text(n + 0.6, y, text, color=fcol, fontsize=11.5, va="center", ha="left", zorder=6, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.25", fc=color, ec="none"))
    ax.tick_params(colors=MUTED, labelsize=12, labelbottom=False)
    ax.yaxis.tick_left()
    for sp in ax.spines.values():
        sp.set_color(GRID)

    axv.bar(x, V, width=0.68, color=[UP if C[i] >= O[i] else DOWN for i in x], alpha=0.85)
    axv.grid(color=GRID, linewidth=0.8, alpha=0.8)
    axv.set_yticks([])
    ticks = [i for i in x if i % 20 == 0]
    axv.set_xticks(ticks)
    axv.set_xticklabels([datetime.strptime(d[len(bars) - n + i], "%Y-%m-%d").strftime("%b %-d") for i in ticks])
    axv.tick_params(colors=MUTED, labelsize=12)
    axv.text(0.006, 0.88, "Volume", transform=axv.transAxes, color=MUTED, fontsize=11, va="top", zorder=9,
             bbox=dict(boxstyle="round,pad=0.15", fc=PANEL, ec="none"))
    for sp in axv.spines.values():
        sp.set_color(GRID)

    def panel(x0: float, w: float, title: str, lines: List[str], edge: str, tcolor: str) -> None:
        pax = fig.add_axes([x0, 0.085, w, 0.215])
        pax.set_axis_off()
        pax.add_patch(FancyBboxPatch((0.0, 0.0), 1, 1, boxstyle="round,pad=0,rounding_size=0.04", fc=PANEL, ec=edge,
                                     linewidth=2.2, transform=pax.transAxes))
        pax.text(0.04, 0.86, title, color=tcolor, fontsize=15, fontweight="bold", va="center", transform=pax.transAxes)
        for i, ln in enumerate(lines[:5]):
            pax.text(0.04, 0.68 - i * 0.145, ln, color=TXT, fontsize=13.2, va="center", transform=pax.transAxes)

    def rel(pct: Optional[float], word: str) -> str:
        return f"{abs(pct):.2f}% {'above' if pct >= 0 else 'below'} {word}" if pct is not None else "n/a"

    tfs = facts.get("timeframes") or {}
    left = [f"Daily: {rel(facts.get('vs_sma20_pct'), '20-day avg')}"]
    for key, name in (("weekly", "Weekly"), ("4h", "4-hour"), ("2h", "2-hour")):
        t = tfs.get(key)
        left.append(f"{name}: {rel(t.get('vs_sma20_pct'), '20-bar avg')}" if t else f"{name}: not available")
    left.append(f"Daily vs 200-day avg: {rel(facts.get('vs_sma200_pct'), '200-day avg')}" if facts.get("vs_sma200_pct") is not None else "")
    centre = [f"Above  {_m(y['price'])}  {_short(y['label'])}" for y in above] or ["Above: none within range"]
    centre += [f"Below  {_m(y['price'])}  {_short(y['label'])}" for y in below]
    right = []
    if facts.get("volume_vs_20d_avg") is not None:
        right.append(f"Daily volume: {facts['volume_vs_20d_avg']:.2f}x its 20-day avg")
    wk = tfs.get("weekly") or {}
    if wk.get("volume_vs_20_bar_avg") is not None:
        right.append(f"Weekly volume: {wk['volume_vs_20_bar_avg']:.2f}x its 20-week avg")
    right += [f"5-day change: {facts['change_5d_pct']:+.2f}%" if facts.get("change_5d_pct") is not None else "",
              f"20-day change: {facts['change_20d_pct']:+.2f}%" if facts.get("change_20d_pct") is not None else "",
              f"52-week range: {_m(facts['low_52w'])} to {_m(facts['high_52w'])}" if facts.get("high_52w") else ""]
    panel(0.03, 0.27, "TIMEFRAME VIEW", [t for t in left if t], BLUE, CYAN)
    panel(0.31, 0.37, "KEY LEVELS", centre, GOLD, GOLD)
    panel(0.69, 0.28, "PARTICIPATION & RANGE", [t for t in right if t], BLUE, CYAN)

    fig.text(0.03, 0.035, "Better Opportunities. Better Decisions. Better Trading Results.", color=GOLD, fontsize=14.5, fontweight="bold")
    fig.text(0.97, 0.035, "www.sigmalyticquantcorp.com  ·  Educational research, not investment advice.", color=MUTED, fontsize=13, ha="right")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
