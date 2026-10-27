# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
tools/build_breakout_report.py
------------------------------
Builds the Daily Breakout & Breakdown Report as a publishable PDF, with one chart per symbol.

Data comes from the platform's own public endpoints:
  * GET /api/weis-radar/results        -> the latest radar scan (the breakout / breakdown list)
  * GET /api/weis-radar/chart/{symbol} -> daily bars (and call/put walls) for each listed symbol

Every chart and number is cut at the --as-of date, so a report for October 26 shows the market as of that
close even when it is generated the next morning.

Requirements (once):   pip install requests matplotlib reportlab
Typical run:           python tools/build_breakout_report.py --as-of 2026-10-26
Layout check offline:  python tools/build_breakout_report.py --as-of 2026-10-26 --demo

The radar only lists breakouts and breakdowns when both signals are enabled in the Radar settings
(display signals). If the report says the scan contains none, enable them, run a scan, and try again.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import re
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BACKEND = os.getenv("SIGMALYTIC_BACKEND_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "..", "backend", "assets", "sigmalytic_logo.png")

# Brand colours, sampled from the logo.
NAVY = "#17223B"
NAVY_SOFT = "#2B3A5C"
SAGE = "#5E8C61"
GOLD = "#B8913F"
INK = "#1F2430"
MUTED = "#6B7280"
RULE = "#D9DDE3"
UP = "#2E7D5B"
DOWN = "#B23A3A"

REPORT_TITLE = "Daily Breakout & Breakdown Report"
CHART_BARS = 126  # about six months of sessions

ATTRIBUTION = [
    ("h", "Market Data and Attribution"),
    ("p", "Underlying market data used in this report were obtained through Alpaca Markets. Alpaca Markets "
          "distributes market data from multiple securities exchanges and market-data providers."),
    ("p", "Sigmalytic Quant Corporation's proprietary analytical framework was used to interpret the supplied market "
          "information. Proprietary formulas, calibration procedures, internal thresholds, scoring methodology, "
          "computational logic, and analytical calculations are intentionally excluded from this public report."),
    ("h", "Reference Sources"),
    ("b", "Alpaca Markets: market data used for this report."),
    ("p", "© 2026 Sigmalytic Quant Corporation. All rights reserved."),
    ("p", "This material is provided solely for research and educational purposes. It does not constitute "
          "personalized investment advice, a recommendation, or an offer or solicitation to buy or sell any security. "
          "Market conditions can change rapidly, and historical or modeled observations do not guarantee future "
          "results."),
]

# Same guard the Content Hub applies: phrases that turn analysis into advice or a promise, and method words
# that must never reach a public report. The ATTRIBUTION block is fixed text and is not checked.
BANNED = re.compile(
    r"guarantee[ds]?|risk[- ]free|can'?t lose|sure thing|no[- ]brainer|"
    r"(?:will|going to) (?:rise|fall|go up|go down|soar|crash|rally|drop|surge|explode)|"
    r"you (?:should|must|need to) (?:buy|sell|short)|\bbuy now\b|\bsell now\b|\bprice target\b|"
    r"\bwe recommend\b|\bI recommend\b|\bwyckoff\b|\bweis\b|\btouch(?:es| count)\b|\balgorithm\b|\bthreshold\b",
    re.IGNORECASE,
)


# ─────────────────────────────── data ───────────────────────────────

def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def get_json(session, url: str, params: Optional[dict] = None, tries: int = 3, timeout: int = 120) -> dict:
    """GET with retries. The first call can be slow while a sleeping Render service wakes up."""
    last = None
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # network errors, HTTP errors, bad JSON
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Could not read {url}: {last}")


def select_signals(results_payload: dict, as_of: str) -> Tuple[List[dict], Dict[str, Any]]:
    """Picks every BREAKOUT / BREAKDOWN hit from the scan whose last completed bar is the as-of date."""
    rows = results_payload.get("results") or []
    bar_dates = sorted({str(r.get("last_bar_time") or "")[:10] for r in rows if r.get("last_bar_time")})
    picked: List[dict] = []
    for r in rows:
        if str(r.get("last_bar_time") or "")[:10] != as_of:
            continue
        for h in r.get("hits") or []:
            kind = str(h.get("type") or "").upper()
            if kind not in ("BREAKOUT", "BREAKDOWN"):
                continue
            level = _f(h.get("level"))
            if level is None:
                continue
            picked.append({
                "symbol": str(r.get("symbol") or "").upper(),
                "kind": kind,
                "level": level,
                "cross_date": str(h.get("date") or "")[:10],
                "days_back": int(h.get("days_back") or 0),
                "pct_beyond": _f(h.get("pct_beyond")),
                "scan_close": _f(h.get("price")),
            })
    meta = {
        "generated_at": results_payload.get("generated_at"),
        "scanned": results_payload.get("scanned"),
        "bar_dates_in_scan": bar_dates,
        "display_signals": (results_payload.get("config") or {}).get("display_signals") or [],
    }
    # Freshest crosses first, then the furthest beyond the level.
    picked.sort(key=lambda s: (s["days_back"], -(s["pct_beyond"] or 0), s["symbol"]))
    return picked, meta


def trim_bars(chart: dict, as_of: str) -> List[dict]:
    """Daily bars up to and including the as-of session, oldest first."""
    bars = []
    for b in chart.get("bars") or []:
        d = str(b.get("date") or "")[:10]
        if d and d <= as_of and _f(b.get("close")) is not None:
            bars.append({"date": d, "open": _f(b.get("open")), "high": _f(b.get("high")),
                         "low": _f(b.get("low")), "close": _f(b.get("close")), "volume": _f(b.get("volume")) or 0.0})
    return bars


def sma(vals: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    run = 0.0
    for i, v in enumerate(vals):
        run += v
        if i >= n:
            run -= vals[i - n]
        out.append(run / n if i >= n - 1 else None)
    return out


def symbol_facts(sig: dict, bars: List[dict], chart: dict) -> dict:
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    vols = [b["volume"] for b in bars]
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else None
    v20 = vols[-21:-1]
    avg_v20 = sum(v20) / len(v20) if v20 and sum(v20) else None
    s20, s50, s200 = sma(closes, 20)[-1], sma(closes, 50)[-1], sma(closes, 200)[-1]
    lvl = sig["level"]
    pct = ((last / lvl - 1) * 100) if sig["kind"] == "BREAKOUT" else ((1 - last / lvl) * 100)
    return {
        **sig,
        "as_of_bar": bars[-1]["date"],
        "close": last,
        "chg_1d": ((last / prev - 1) * 100) if prev else None,
        "pct_beyond": round(pct, 2),
        "vol_ratio": (vols[-1] / avg_v20) if avg_v20 else None,
        "sma20": s20, "sma50": s50, "sma200": s200,
        "high_20": max(highs[-20:]), "low_20": min(lows[-20:]),
        "high_52w": max(highs[-252:]), "low_52w": min(lows[-252:]),
        "call_wall": _f(chart.get("call_wall")), "put_wall": _f(chart.get("put_wall")),
    }


# ─────────────────────────────── demo data (layout check only) ───────────────────────────────

def demo_inputs(as_of: str) -> Tuple[dict, Dict[str, dict]]:
    """Random-walk prices shaped like the real endpoints. Every page is watermarked SAMPLE."""
    rng = random.Random(7)
    end = datetime.strptime(as_of, "%Y-%m-%d").date()
    days: List[str] = []
    d = end
    while len(days) < 300:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    days.reverse()
    specs = [("DEMOA", "BREAKOUT", 0), ("DEMOB", "BREAKOUT", 3), ("DEMOC", "BREAKOUT", 9),
             ("DEMOD", "BREAKDOWN", 0), ("DEMOE", "BREAKDOWN", 5)]
    results, charts = [], {}
    for sym, kind, days_back in specs:
        px = rng.uniform(40, 400)
        bars = []
        for i, day in enumerate(days):
            drift = 0.0
            if i > len(days) - 40:  # build a range, then break it
                drift = 0.004 if kind == "BREAKOUT" else -0.004
            o = px
            px = max(5.0, px * (1 + rng.gauss(drift, 0.017)))
            hi, lo = max(o, px) * (1 + abs(rng.gauss(0, 0.006))), min(o, px) * (1 - abs(rng.gauss(0, 0.006)))
            bars.append({"date": day, "open": round(o, 2), "high": round(hi, 2), "low": round(lo, 2),
                         "close": round(px, 2), "volume": int(rng.uniform(0.6, 1.6) * 2_000_000)})
        cross_i = len(bars) - 1 - days_back
        pre = bars[cross_i - 1]["close"]
        level = round(pre * (1.0 if kind == "BREAKOUT" else 1.0), 2)
        # Make sure every bar since the cross closes beyond the level, as the detector requires.
        for b in bars[cross_i:]:
            if kind == "BREAKOUT" and b["close"] <= level * 1.002:
                b["close"] = round(level * 1.01, 2); b["high"] = max(b["high"], b["close"])
            if kind == "BREAKDOWN" and b["close"] >= level * 0.998:
                b["close"] = round(level * 0.99, 2); b["low"] = min(b["low"], b["close"])
        last = bars[-1]["close"]
        pct = (last / level - 1) * 100 if kind == "BREAKOUT" else (1 - last / level) * 100
        results.append({"symbol": sym, "last_bar_time": f"{as_of}T04:00:00Z",
                        "hits": [{"type": kind, "price": last, "level": level, "date": bars[cross_i]["date"],
                                  "days_back": days_back, "held": True, "pct_beyond": round(pct, 2)}]})
        charts[sym] = {"ok": True, "bars": bars, "call_wall": round(last * 1.12), "put_wall": round(last * 0.9)}
    payload = {"ok": True, "generated_at": f"{as_of}T21:10:00Z", "scanned": 1023, "results": results,
               "config": {"display_signals": ["breakout", "breakdown"]}}
    return payload, charts


# ─────────────────────────────── chart ───────────────────────────────

def render_chart(f: dict, bars: List[dict]) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    closes_all = [b["close"] for b in bars]
    s20_all, s50_all = sma(closes_all, 20), sma(closes_all, 50)
    n = min(CHART_BARS, len(bars))
    off = len(bars) - n
    view = bars[off:]
    s20, s50 = s20_all[off:], s50_all[off:]
    xs = list(range(n))

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
    fig = plt.figure(figsize=(7.4, 3.9), dpi=200)
    gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 1], hspace=0.04)
    ax = fig.add_subplot(gs[0])
    axv = fig.add_subplot(gs[1], sharex=ax)

    w = 0.62
    for x, b in zip(xs, view):
        up = b["close"] >= b["open"]
        col = UP if up else DOWN
        ax.vlines(x, b["low"], b["high"], color=col, linewidth=0.7, zorder=2)
        body_lo, body_hi = sorted((b["open"], b["close"]))
        ax.add_patch(Rectangle((x - w / 2, body_lo), w, max(body_hi - body_lo, b["close"] * 0.0008),
                               facecolor=col, edgecolor=col, linewidth=0.4, zorder=3))
        axv.bar(x, b["volume"], width=w, color=col, alpha=0.55, linewidth=0)

    ax.plot(xs, [v if v is not None else float("nan") for v in s20], color=SAGE, linewidth=1.1, label="20-day average")
    ax.plot(xs, [v if v is not None else float("nan") for v in s50], color=NAVY_SOFT, linewidth=1.1,
            linestyle=(0, (4, 2)), label="50-day average")

    lvl = f["level"]
    is_bo = f["kind"] == "BREAKOUT"
    ax.axhline(lvl, color=GOLD, linewidth=1.3, linestyle=(0, (6, 3)), zorder=4)
    ax.text(1, lvl, f"  {'Breakout' if is_bo else 'Breakdown'} level  ${lvl:,.2f}", color=GOLD, fontsize=7.5,
            fontweight="bold", va="bottom" if is_bo else "top", ha="left", zorder=5,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1))

    dates = [b["date"] for b in view]
    if f.get("cross_date") in dates:
        ci = dates.index(f["cross_date"])
        cb = view[ci]
        span = max(b["high"] for b in view) - min(b["low"] for b in view)
        y = cb["low"] - span * 0.045 if is_bo else cb["high"] + span * 0.045
        ax.scatter([ci], [y], marker="^" if is_bo else "v", s=46, color=UP if is_bo else DOWN, zorder=6,
                   edgecolors="white", linewidths=0.6)

    last = view[-1]["close"]
    ax.annotate(f"${last:,.2f}", xy=(n - 1, last), xytext=(6, 0), textcoords="offset points", va="center",
                fontsize=7.5, color="white", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor=NAVY, edgecolor="none"))

    lo = min(min(b["low"] for b in view), lvl)
    hi = max(max(b["high"] for b in view), lvl)
    pad = (hi - lo) * 0.08
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-1, n + 6)
    for a in (ax, axv):
        a.grid(True, color=RULE, linewidth=0.5)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color("#B8BEC8")
        a.tick_params(colors=MUTED, length=2)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:,.0f}" if v >= 100 else f"${v:,.2f}"))
    axv.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"{v / 1e6:.0f}M" if v >= 1e6 else f"{v / 1e3:.0f}K" if v >= 1e3 else f"{v:.0f}"))
    axv.set_ylabel("Volume", color=MUTED, fontsize=7)
    plt.setp(ax.get_xticklabels(), visible=False)

    ticks, labels, seen = [], [], set()
    for i, d in enumerate(dates):
        m = d[:7]
        if m not in seen:
            seen.add(m)
            if i > 2:
                ticks.append(i)
                labels.append(datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y"))
    axv.set_xticks(ticks)
    axv.set_xticklabels(labels)
    # Legend sits above the plot, clear of the level label and the price action.
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=7, ncol=2,
              borderaxespad=0.2, handlelength=2.2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


# ─────────────────────────────── PDF ───────────────────────────────

def usd(v: Optional[float]) -> str:
    return f"${v:,.2f}" if v is not None else "—"


def pct(v: Optional[float], signed: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def long_date(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def held_text(f: dict) -> str:
    if f["days_back"] == 0:
        return "New"
    return f"{f['days_back']} session{'s' if f['days_back'] != 1 else ''}"


def symbol_paragraph(f: dict) -> str:
    is_bo = f["kind"] == "BREAKOUT"
    side, word = ("above", "Breakout") if is_bo else ("below", "Breakdown")
    when = (f"first closing {side} it in the {long_date(f['as_of_bar'])} session"
            if f["days_back"] == 0 else
            f"after first closing {side} it on {long_date(f['cross_date'])}, {f['days_back']} "
            f"session{'s' if f['days_back'] != 1 else ''} earlier")
    text = (f"{f['symbol']} closed at {usd(f['close'])} on {long_date(f['as_of_bar'])}, "
            f"{abs(f['pct_beyond']):.2f}% {side} the {usd(f['level'])} level, {when}. "
            f"Sigmalytic's scan flagged the move as a {word}.")
    if f.get("vol_ratio") is not None:
        text += f" Volume in the latest session was {f['vol_ratio']:.2f} times its 20-day average."
    if f.get("sma20") is not None:
        rel = "above" if f["close"] >= f["sma20"] else "below"
        text += f" Price sits {rel} its 20-day average of {usd(f['sma20'])}."
    return text


def build_pdf(out_path: str, as_of: str, report_date: str, sigs: List[dict], meta: dict,
              charts_png: Dict[Tuple[str, str], bytes], demo: bool) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from reportlab.lib.utils import ImageReader

    C = colors.HexColor
    W, H = letter
    margin = 0.6 * inch
    header_h = 0.78 * inch

    st = {
        "title": ParagraphStyle("title", fontName="Times-Bold", fontSize=24, leading=28, textColor=C(NAVY)),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10.5, leading=14, textColor=C(MUTED)),
        "h1": ParagraphStyle("h1", fontName="Times-Bold", fontSize=15, leading=19, textColor=C(NAVY),
                             spaceBefore=6, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=C(GOLD),
                             spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=C(INK),
                               alignment=TA_LEFT, spaceAfter=6),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, leading=11, textColor=C(MUTED)),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=C(INK)),
        "kpi_v": ParagraphStyle("kpi_v", fontName="Times-Bold", fontSize=20, leading=22, textColor=C(NAVY)),
        "kpi_l": ParagraphStyle("kpi_l", fontName="Helvetica", fontSize=7.5, leading=9, textColor=C(MUTED)),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.2, leading=13.2, textColor=C(INK),
                                 leftIndent=12, bulletIndent=2, spaceAfter=6),
    }
    checked_text: List[str] = []

    def P(text: str, style: str = "body", check: bool = True):
        if check:
            checked_text.append(text)
        return Paragraph(text, st[style])

    logo = ImageReader(LOGO) if os.path.isfile(LOGO) else None

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C(NAVY))
        canvas.rect(0, H - header_h, W, header_h, stroke=0, fill=1)
        if logo:
            lw = 2.55 * inch
            canvas.drawImage(logo, margin - 0.12 * inch, H - header_h + 0.1 * inch, width=lw,
                             height=lw * 255 / 950, mask="auto")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawRightString(W - margin, H - 0.36 * inch, REPORT_TITLE.upper())
        canvas.setFillColor(C(GOLD))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(W - margin, H - 0.55 * inch, f"Market data through {long_date(as_of)}")
        canvas.setStrokeColor(C(GOLD))
        canvas.setLineWidth(1.4)
        canvas.line(0, H - header_h, W, H - header_h)
        canvas.setStrokeColor(C(RULE))
        canvas.setLineWidth(0.6)
        canvas.line(margin, 0.55 * inch, W - margin, 0.55 * inch)
        canvas.setFillColor(C(MUTED))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(margin, 0.38 * inch, "Sigmalytic Quant Corporation")
        canvas.drawRightString(W - margin, 0.38 * inch, f"Page {doc.page}")
        if demo:
            canvas.setFillColor(C(DOWN))
            canvas.setFillAlpha(0.10)
            canvas.setFont("Helvetica-Bold", 54)
            canvas.translate(W / 2, H / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "SAMPLE · SYNTHETIC DATA")
        canvas.restoreState()

    doc = SimpleDocTemplate(out_path, pagesize=letter, leftMargin=margin, rightMargin=margin,
                            topMargin=header_h + 0.35 * inch, bottomMargin=0.8 * inch,
                            title=f"Sigmalytic {REPORT_TITLE} — {long_date(as_of)}",
                            author="Sigmalytic Quant Corporation")
    frame_w = W - 2 * margin
    story: List[Any] = []

    bos = [s for s in sigs if s["kind"] == "BREAKOUT"]
    bds = [s for s in sigs if s["kind"] == "BREAKDOWN"]
    new_bo = sum(1 for s in bos if s["days_back"] == 0)
    new_bd = sum(1 for s in bds if s["days_back"] == 0)

    # ── cover / summary ──
    story += [P(REPORT_TITLE, "title"),
              Spacer(1, 4),
              P(f"Sigmalytic Quant Corporation Market Structure Report &nbsp;·&nbsp; Report date {long_date(report_date)}"
                f" &nbsp;·&nbsp; Market data through {long_date(as_of)}", "sub"),
              Spacer(1, 14)]

    def kpi(value: str, label: str):
        return [P(value, "kpi_v", check=False), P(label, "kpi_l", check=False)]

    scanned = meta.get("scanned")
    kpis = Table([[kpi(str(len(bos)), "BREAKOUTS"), kpi(str(new_bo), "NEW BREAKOUTS TODAY"),
                   kpi(str(len(bds)), "BREAKDOWNS"), kpi(str(new_bd), "NEW BREAKDOWNS TODAY"),
                   kpi(f"{scanned:,}" if isinstance(scanned, int) else "—", "SYMBOLS SCANNED")]],
                 colWidths=[frame_w / 5] * 5)
    kpis.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C("#F4F5F7")),
        ("LINEABOVE", (0, 0), (-1, 0), 1.6, C(GOLD)),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [kpis, Spacer(1, 14)]

    story += [P("How to read this report", "h2"),
              P("Sigmalytic's scan reviews the Russell 1000 after each close. A <b>Breakout</b> is flagged when a stock "
                "closes above a resistance level identified by Sigmalytic's framework and holds there; a "
                "<b>Breakdown</b> is the same move below support. <b>New</b> marks a level first crossed in the "
                f"{long_date(as_of)} session; otherwise the column shows how many sessions the stock has held beyond "
                "the level. The tables list the freshest crosses first. Each symbol then has its own page with a "
                "six-month daily chart, the level marked in gold, and the day of the cross marked with an arrow."),
              P("These flags describe how price and volume behaved around a prior level. They are observations of "
                "past behavior, not forecasts.", "small")]

    def signal_table(rows: List[dict], kind: str):
        is_bo = kind == "BREAKOUT"
        head = ["Symbol", "Close", "1-Day", "Level", "Beyond Level", "First Crossed", "Held", "Vol / 20-Day"]
        data = [head]
        for f in rows:
            data.append([f["symbol"], usd(f["close"]), pct(f["chg_1d"]), usd(f["level"]),
                         pct(f["pct_beyond"], signed=False), f["cross_date"], held_text(f),
                         f"{f['vol_ratio']:.2f}×" if f.get("vol_ratio") is not None else "—"])
        widths = [0.8, 0.85, 0.75, 0.85, 0.95, 1.0, 0.8, 0.9]
        scale = frame_w / sum(widths)
        t = Table(data, colWidths=[w * scale for w in widths], repeatRows=1)
        style = [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.6),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), C(NAVY)),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 8.2),
            ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 8.2),
            ("TEXTCOLOR", (0, 1), (-1, -1), C(INK)),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C("#F6F7F9")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(RULE)),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, f in enumerate(rows, start=1):
            if f["days_back"] == 0:
                style.append(("TEXTCOLOR", (6, i), (6, i), C(UP if is_bo else DOWN)))
                style.append(("FONT", (6, i), (6, i), "Helvetica-Bold", 8.2))
            if f["chg_1d"] is not None:
                style.append(("TEXTCOLOR", (2, i), (2, i), C(UP if f["chg_1d"] >= 0 else DOWN)))
        t.setStyle(TableStyle(style))
        return t

    for kind, rows, label in (("BREAKOUT", bos, "Breakouts"), ("BREAKDOWN", bds, "Breakdowns")):
        story.append(P(f"{label} ({len(rows)})", "h1"))
        if rows:
            story.append(signal_table(rows, kind))
        else:
            story.append(P(f"Sigmalytic's scan flagged no {label.lower()} for the {long_date(as_of)} session."))
        story.append(Spacer(1, 6))

    # ── one page per symbol ──
    for f in sigs:
        is_bo = f["kind"] == "BREAKOUT"
        story.append(PageBreak())
        tag_col = UP if is_bo else DOWN
        title = Table([[P(f"<font color='{NAVY}'>{f['symbol']}</font>", "h1", check=False),
                        P(f"<font color='{tag_col}'><b>{'BREAKOUT' if is_bo else 'BREAKDOWN'}</b></font>"
                          f"<font color='{MUTED}'> &nbsp;{'above' if is_bo else 'below'} {usd(f['level'])}"
                          f" &nbsp;·&nbsp; {held_text(f) if f['days_back'] else 'New this session'}</font>",
                          "body", check=False)]],
                      colWidths=[1.2 * inch, frame_w - 1.2 * inch])
        title.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(title)

        strip = Table([[kpi(usd(f["close"]), "CLOSE"), kpi(pct(f["chg_1d"]), "1-DAY CHANGE"),
                        kpi(pct(f["pct_beyond"], signed=False), f"{'ABOVE' if is_bo else 'BELOW'} LEVEL"),
                        kpi(f"{f['vol_ratio']:.2f}×" if f.get("vol_ratio") is not None else "—", "VOLUME / 20-DAY"),
                        kpi(usd(f["sma20"]), "20-DAY AVERAGE")]], colWidths=[frame_w / 5] * 5)
        strip.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C("#F4F5F7")), ("LINEABOVE", (0, 0), (-1, 0), 1.4, C(GOLD)),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
        story += [strip, Spacer(1, 8)]

        png = charts_png[(f["symbol"], f["kind"])]
        img = Image(io.BytesIO(png))
        ratio = img.imageHeight / img.imageWidth
        img.drawWidth, img.drawHeight = frame_w, frame_w * ratio
        story += [img, Spacer(1, 6), P(symbol_paragraph(f))]

        levels = [("20-day high", f["high_20"]), ("20-day low", f["low_20"]), ("50-day average", f["sma50"]),
                  ("200-day average", f["sma200"]), ("52-week high", f["high_52w"]), ("52-week low", f["low_52w"]),
                  ("Call wall (largest call open interest)", f["call_wall"]),
                  ("Put wall (largest put open interest)", f["put_wall"])]
        levels = [(k, v) for k, v in levels if v is not None]
        half = (len(levels) + 1) // 2
        rows = []
        for i in range(half):
            l1 = levels[i]
            l2 = levels[i + half] if i + half < len(levels) else ("", None)
            rows.append([l1[0], usd(l1[1]), l2[0], usd(l2[1]) if l2[0] else ""])
        lt = Table(rows, colWidths=[frame_w * 0.33, frame_w * 0.17, frame_w * 0.33, frame_w * 0.17])
        lt.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8.2), ("TEXTCOLOR", (0, 0), (-1, -1), C(INK)),
            ("TEXTCOLOR", (0, 0), (0, -1), C(MUTED)), ("TEXTCOLOR", (2, 0), (2, -1), C(MUTED)),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(RULE)),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (1, 0), (1, -1), 18)]))
        story.append(KeepTogether([P("Reference levels", "h2", check=False), lt]))

    # ── attribution, once, at the end ──
    story.append(PageBreak())
    for kind, text in ATTRIBUTION:
        if kind == "h":
            story.append(P(text, "h1", check=False))
        elif kind == "b":
            story.append(Paragraph(text, st["bullet"], bulletText="•"))
        else:
            story.append(P(text, "body", check=False))

    bad = sorted({m.group(0) for t in checked_text for m in BANNED.finditer(t)})
    if bad:
        raise RuntimeError(f"Report text contains blocked wording: {bad}. Nothing was written.")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


# ─────────────────────────────── main ───────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Sigmalytic Daily Breakout & Breakdown Report (PDF).")
    ap.add_argument("--as-of", required=True, help="Session date the report covers, YYYY-MM-DD (e.g. 2026-10-26).")
    ap.add_argument("--report-date", help="Date printed as the report date. Defaults to today.")
    ap.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend base URL.")
    ap.add_argument("--results-file", help="Use a saved /api/weis-radar/results JSON instead of fetching it.")
    ap.add_argument("--out", default="reports", help="Output folder.")
    ap.add_argument("--no-options", action="store_true", help="Skip call/put walls (faster).")
    ap.add_argument("--demo", action="store_true", help="Synthetic data, watermarked SAMPLE, to check the layout.")
    a = ap.parse_args()

    as_of = a.as_of
    datetime.strptime(as_of, "%Y-%m-%d")
    report_date = a.report_date or date.today().isoformat()

    if a.demo:
        payload, demo_charts = demo_inputs(as_of)
        session = None
    else:
        import requests
        session = requests.Session()
        session.headers["User-Agent"] = "Sigmalytic-Report-Builder/1.0"
        if a.results_file:
            with open(a.results_file, encoding="utf-8") as fh:
                payload = json.load(fh)
        else:
            print(f"Reading the latest scan from {a.backend} ...")
            payload = get_json(session, f"{a.backend}/api/weis-radar/results")

    sigs, meta = select_signals(payload, as_of)
    print(f"Scan generated {meta['generated_at']}; completed bar dates in scan: {meta['bar_dates_in_scan'] or 'none'}")
    if not sigs:
        enabled = {s.lower() for s in meta["display_signals"]}
        if not {"breakout", "breakdown"} <= enabled:
            print("The radar scan does not include breakouts and breakdowns. Enable both signals in the Radar "
                  "settings (display signals), run a scan, then run this again.")
        elif as_of not in meta["bar_dates_in_scan"]:
            print(f"The latest scan's completed bars are not from {as_of}. Run this after a scan that used that close.")
        else:
            print(f"Sigmalytic's scan flagged no breakouts or breakdowns for {as_of}.")
        return 1

    print(f"Found {len(sigs)} signals. Fetching daily bars and drawing charts ...")
    facts: List[dict] = []
    charts_png: Dict[Tuple[str, str], bytes] = {}
    skipped: List[str] = []
    for i, s in enumerate(sigs, start=1):
        sym = s["symbol"]
        try:
            if a.demo:
                chart = demo_charts[sym]
            else:
                chart = get_json(session, f"{a.backend}/api/weis-radar/chart/{sym}",
                                 params={"timeframe": "1Day", "limit": 300,
                                         "include_options": "false" if a.no_options else "true"})
                time.sleep(0.4)  # be gentle with the single-worker backend
            if not chart.get("ok"):
                raise RuntimeError(chart.get("error") or "no data")
            bars = trim_bars(chart, as_of)
            if len(bars) < 60 or bars[-1]["date"] != as_of:
                raise RuntimeError(f"bars end {bars[-1]['date'] if bars else 'n/a'}, need {as_of}")
            f = symbol_facts(s, bars, chart)
            charts_png[(sym, s["kind"])] = render_chart(f, bars)
            facts.append(f)
            print(f"  [{i}/{len(sigs)}] {sym} {s['kind'].lower()} ok")
        except Exception as exc:
            skipped.append(f"{sym} ({exc})")
            print(f"  [{i}/{len(sigs)}] {sym} skipped: {exc}")

    if not facts:
        print("No symbol could be charted; no report was written.")
        return 1

    os.makedirs(a.out, exist_ok=True)
    name = f"Sigmalytic_Breakout_Breakdown_Report_{as_of}{'_SAMPLE' if a.demo else ''}.pdf"
    out_path = os.path.join(a.out, name)
    build_pdf(out_path, as_of, report_date, facts, meta, charts_png, a.demo)
    print(f"\nWrote {out_path}  ({len(facts)} symbols)")
    if skipped:
        print("Skipped: " + "; ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
