# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/content_chart.py
------------------------
Draws the report's hero / share image in the house layout: logo block, report title and dates, daily candles with the
200-day average, volume, numbered resistance (R1-R4 + Major) and support (S1-S4 + Major) tags, and three panels
(Sigmalytic View, Key Levels, Volume Insights). Every number on the image comes from the same `facts` the blog was
written from, and the Sigmalytic View text is the blog's own "current condition" sentence.

Output is 1800 x 945 (1.91:1, the shape social sites use; it downsizes cleanly to 1200 x 630).
If a logo file exists (CONTENT_HUB_LOGO_FILE, or backend/assets/sigmalytic_logo.png) it is drawn in place of the built-in mark.
"""

from __future__ import annotations

import io
import os
import textwrap
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

W, H, DPI = 1800, 945, 100
BG, PANEL, GRID, FRAME = "#111c32", "#152448", "#223460", "#2a5bd7"
UP, DOWN = "#22c55e", "#ef4444"
TXT, MUTED, GOLD, BLUE, CYAN = "#eef3ff", "#93a7d1", "#f5b82e", "#2f6bff", "#38bdf8"
MAX_BARS = 130


def _m(v: float) -> str:
    return f"\\${v:,.2f}"          # matplotlib reads paired $ as math text, so it is escaped


def _p(v: float) -> str:
    return f"{v:,.2f}"


def _sma(vals: Sequence[float], n: int) -> List[Optional[float]]:
    return [sum(vals[i - n + 1:i + 1]) / n if i >= n - 1 else None for i in range(len(vals))]


def _long_date(d: str) -> str:
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return d


def _logo_path() -> Optional[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.getenv("CONTENT_HUB_LOGO_FILE", ""), os.path.join(here, "assets", "sigmalytic_logo.png")):
        if cand and os.path.isfile(cand):
            return cand
    return None


def _fit_lines(text: str, width: int = 46, max_lines: int = 5) -> List[str]:
    """Wraps text for a panel; if it is too long, whole trailing sentences are dropped rather than cutting mid-sentence."""
    import re
    sents = re.split(r"(?<=[.!?])\s+", _money_text(text).strip())
    while sents:
        lines = textwrap.wrap(" ".join(sents), width)
        if len(lines) <= max_lines:
            return lines
        if len(sents) == 1:
            return lines[:max_lines - 1] + [lines[max_lines - 1].rstrip(" ,;:") + "…"]
        sents.pop()
    return []


def _money_text(s: str) -> str:
    return s.replace("$", "\\$")


def render_share_image(facts: Dict[str, Any], bars: List[Sequence[Any]], title: str = "",
                       view_text: str = "", volume_text: str = "") -> bytes:
    """bars: [[date, open, high, low, close, volume], ...] oldest first. Returns PNG bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch

    if len(bars) < 30:
        raise ValueError("Not enough bars to draw the share image.")
    d = [str(b[0])[:10] for b in bars]
    o, h, l, c = ([float(b[i]) for b in bars] for i in (1, 2, 3, 4))
    v = [float(b[5] or 0) for b in bars]
    s200 = _sma(c, 200)
    n = min(MAX_BARS, len(bars))
    off = len(bars) - n
    x = list(range(n))
    O, Hh, L, C, V = o[off:], h[off:], l[off:], c[off:], v[off:]
    sym, last = facts["symbol"], facts["last_close"]
    lv = facts.get("levels") or {}
    far = lambda y: abs(y["price"] - last) / last > 0.25          # levels very far from price add nothing to the picture
    above = [y for y in (lv.get("above") or []) if not far(y)][:5]
    below = [y for y in (lv.get("below") or []) if not far(y)][:5]

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=BG)
    fig.add_artist(FancyBboxPatch((0.004, 0.006), 0.992, 0.988, boxstyle="round,pad=0,rounding_size=0.01", fc="none",
                                  ec=FRAME, linewidth=2.2, transform=fig.transFigure))

    # ── header: logo, title, dates, tagline
    logo = _logo_path()
    if logo:
        lax = fig.add_axes([0.014, 0.832, 0.235, 0.15]); lax.set_axis_off(); lax.imshow(mpimg.imread(logo), interpolation="lanczos")
    else:
        lax = fig.add_axes([0.016, 0.835, 0.2, 0.15]); lax.set_xlim(0, 2.1); lax.set_ylim(0, 1); lax.set_axis_off()
        lax.set_aspect("auto")
        lax.add_patch(Circle((0.3, 0.52), 0.28, fc="#10265a", ec=GOLD, linewidth=2.6))
        lax.text(0.3, 0.50, "Σ", color=GOLD, fontsize=44, fontweight="bold", ha="center", va="center")
        lax.text(0.68, 0.70, "Sigmalytic Quant", color=TXT, fontsize=19, fontweight="bold", va="center")
        lax.text(0.68, 0.45, "CORPORATION", color=GOLD, fontsize=17, fontweight="bold", va="center")
        lax.text(0.68, 0.20, "DATA · DISCIPLINE · ALPHA", color=MUTED, fontsize=9.5, va="center")
    ttl = title or f"{sym} at ${last:,.2f}"
    tt = fig.text(0.54, 0.925, _money_text(ttl), color=TXT, fontsize=27, fontweight="bold", ha="center", va="center")
    rend = fig.canvas.get_renderer()
    while tt.get_window_extent(rend).width > 0.56 * W and tt.get_fontsize() > 15:
        tt.set_fontsize(tt.get_fontsize() - 0.5)
    fig.text(0.54, 0.862, f"Market Data Through: {_long_date(facts['as_of'])}", color=TXT, fontsize=19, fontweight="bold",
             ha="center", va="center")
    fig.text(0.985, 0.955, f"Report Date: {_long_date(facts.get('generated_at') or facts['as_of'])}", color=TXT, fontsize=13,
             ha="right", va="center", bbox=dict(boxstyle="round,pad=0.3", fc=PANEL, ec=FRAME))
    for i, ln in enumerate(("Better Opportunities.", "Better Decisions.", "Better Trading Results.")):
        fig.text(0.985, 0.905 - i * 0.026, ln, color=MUTED, fontsize=11.5, ha="right", va="center")

    # ── price chart
    ax = fig.add_axes([0.05, 0.39, 0.77, 0.42], facecolor=PANEL)
    axv = fig.add_axes([0.05, 0.31, 0.77, 0.07], facecolor=PANEL, sharex=ax)
    near = lambda p: abs(p - last) / last <= 0.16
    lo = min(L + [y["price"] for y in below if near(y["price"])] + [last]) * 0.985
    hi = max(Hh + [y["price"] for y in above if near(y["price"])] + [last]) * 1.012
    ax.set_xlim(-1.5, n + 1.5)
    ax.set_ylim(lo, hi)
    ax.grid(color=GRID, linewidth=0.8, alpha=0.8)
    for xi in x:
        col = UP if C[xi] >= O[xi] else DOWN
        ax.vlines(xi, L[xi], Hh[xi], color=col, linewidth=1.3, zorder=3)
        ax.bar(xi, abs(C[xi] - O[xi]) or (hi - lo) * 0.0008, bottom=min(O[xi], C[xi]), width=0.68, color=col, zorder=4)
    pts = [(i, s200[off + i]) for i in x if s200[off + i] is not None]
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=GOLD, linewidth=2.0, zorder=5)
        ax.text(0.5, 0.965, f"200-Day Average ({_p(pts[-1][1])})", transform=ax.transAxes, color=GOLD, fontsize=12.5,
                ha="center", va="top", zorder=8, bbox=dict(boxstyle="round,pad=0.2", fc=PANEL, ec="none"))
    ax.text(0.008, 0.965, f"{sym}  ·  Daily", transform=ax.transAxes, color=TXT, fontsize=14, fontweight="bold", va="top",
            zorder=8)
    hi_i, lo_i = max(x, key=lambda i: Hh[i]), min(x, key=lambda i: L[i])
    ax.annotate(f"High {_p(Hh[hi_i])}", (hi_i, Hh[hi_i]), xytext=(0, 12), textcoords="offset points", color=TXT, fontsize=11,
                ha="center", zorder=8)
    ax.annotate(f"Low {_p(L[lo_i])}", (lo_i, L[lo_i]), xytext=(0, -20), textcoords="offset points", color=TXT, fontsize=11,
                ha="center", zorder=8)
    for y in above + below:
        if lo < y["price"] < hi:
            ax.axhline(y["price"], color=DOWN if y["price"] > last else BLUE, linewidth=0.9, linestyle=(0, (2, 4)), alpha=0.6,
                       zorder=2)
    ax.axhline(last, color=UP, linewidth=1.1, alpha=0.9, zorder=2)
    ax.tick_params(colors=MUTED, labelsize=12, labelbottom=False)
    for sp in ax.spines.values():
        sp.set_color(GRID)

    axv.bar(x, [vv / 1e6 for vv in V], width=0.68, color=[UP if C[i] >= O[i] else DOWN for i in x], alpha=0.85)
    axv.grid(color=GRID, linewidth=0.8, alpha=0.8)
    ticks = [i for i in x if i % 22 == 0]
    axv.set_xticks(ticks)
    axv.set_xticklabels([datetime.strptime(d[off + i], "%Y-%m-%d").strftime("%b %-d") for i in ticks])
    axv.tick_params(colors=MUTED, labelsize=11.5)
    axv.yaxis.set_major_formatter(lambda val, pos: f"{val:,.0f}M")
    axv.locator_params(axis="y", nbins=3)
    axv.text(0.006, 0.9, "Volume (Daily)", transform=axv.transAxes, color=MUTED, fontsize=11, va="top", zorder=9,
             bbox=dict(boxstyle="round,pad=0.15", fc=PANEL, ec="none"))
    for sp in axv.spines.values():
        sp.set_color(GRID)

    # ── level tags in a column right of the chart (R1..R4 + Major, last price, S1..S4 + Major)
    def tag_rows():
        rows = []
        for i, y in enumerate(above):
            rows.append((y["price"], "Major Resistance" if i == len(above) - 1 and len(above) == 5 else f"R{i + 1}", DOWN, "white"))
        rows.append((last, "Latest Price", UP, "#04210f"))
        for i, y in enumerate(below):
            rows.append((y["price"], "Major Support" if i == len(below) - 1 and len(below) == 5 else f"S{i + 1}", BLUE, "white"))
        return rows

    rows = sorted(tag_rows(), key=lambda r: -r[0])
    top, bot = 0.79, 0.43
    ys = [top - i * (top - bot) / max(1, len(rows) - 1) for i in range(len(rows))] if len(rows) > 1 else [0.6]
    for (price, lab, color, fcol), y in zip(rows, ys):
        wide = lab.startswith("Major") or lab == "Latest Price"
        fig.text(0.835, y, f"{lab}  {_p(price)}" if wide else f"{lab}   {_p(price)}", color=fcol, fontsize=12.5,
                 fontweight="bold", va="center", ha="left",
                 bbox=dict(boxstyle="round,pad=0.28", fc=color, ec="white" if wide else "none", linewidth=1.0))

    # ── three panels
    def panel(x0: float, w: float, head: str, edge: str, hcolor: str, lines: List[Any]) -> None:
        pax = fig.add_axes([x0, 0.075, w, 0.185])
        pax.set_axis_off()
        pax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.05", fc=PANEL, ec=edge,
                                     linewidth=2.4, transform=pax.transAxes))
        pax.text(0.04, 0.87, head, color=hcolor, fontsize=16, fontweight="bold", va="center", transform=pax.transAxes)
        yy = 0.68
        for ln in lines:
            text, color, bold = (ln if isinstance(ln, tuple) else (ln, TXT, False))
            pax.text(0.04, yy, text, color=color, fontsize=13.4, fontweight="bold" if bold else "normal", va="center",
                     transform=pax.transAxes)
            yy -= 0.145

    cond = view_text or ""
    view = _fit_lines(cond) if cond else ["No summary was available for this run."]
    panel(0.02, 0.31, "SIGMALYTIC VIEW", BLUE, CYAN, view)

    def join(items: List[Dict[str, Any]]) -> List[str]:
        s = "  |  ".join(_p(y["price"]) for y in items)
        return textwrap.wrap(s, 50) or ["none within range"]
    kl: List[Any] = [("Resistance:", GOLD, True)] + join(above)[:2] + [("Support:", GOLD, True)] + join(below)[:2]
    panel(0.345, 0.325, "KEY LEVELS", GOLD, GOLD, kl)

    if volume_text:
        vol: List[Any] = _fit_lines(volume_text)      # the written read stands alone, never cut mid-sentence
    else:
        vol = []
        if facts.get("volume_vs_20d_avg") is not None:
            vol.append(f"Daily volume ran {facts['volume_vs_20d_avg']:.2f}x its 20-day average")
        vol += [f"5-day change: {facts['change_5d_pct']:+.2f}%" if facts.get("change_5d_pct") is not None else "",
                f"20-day change: {facts['change_20d_pct']:+.2f}%" if facts.get("change_20d_pct") is not None else ""]
    panel(0.68, 0.30, "VOLUME INSIGHTS", BLUE, CYAN, [x_ for x_ in vol if x_][:5])

    fig.text(0.02, 0.035, "www.sigmalyticquantcorp.com", color=MUTED, fontsize=13, va="center")
    year = (facts.get("as_of") or "")[:4] or "2026"
    fig.text(0.985, 0.035, f"© {year} Sigmalytic Quant Corporation. All rights reserved.", color=MUTED, fontsize=13,
             ha="right", va="center")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
