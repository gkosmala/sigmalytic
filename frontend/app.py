"""
Sigmalytic Quant Corporation — Decision Intelligence Platform
Institutional-Grade Frontend · Dash + Plotly
Includes: Behavioral Intelligence Layer v1.0
"""

from __future__ import annotations
import json
import os
import random
from datetime import datetime, timezone, timedelta

import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go
import requests as req

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.engine import (
    sanitize_symbol, create_live_update, generate_initial_candles, get_key_levels,
)

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS   = os.getenv("BACKEND_WS_URL", "ws://localhost:8000")
TIMEFRAMES   = ["1m", "5m", "15m", "1H", "1D", "1W"]
USER_ID      = "demo_user_001"

TF_VOLATILITY = {"1m": 0.25, "5m": 0.60, "15m": 1.10, "1H": 2.00, "1D": 4.50, "1W": 9.00}
TF_INTERVAL   = {"1m": 60,   "5m": 300,  "15m": 900,  "1H": 3600, "1D": 86400, "1W": 604800}
TF_TICKFMT    = {"1m": "%H:%M", "5m": "%H:%M", "15m": "%H:%M",
                 "1H": "%b %d %H:%M", "1D": "%b %d", "1W": "%b %d '%y"}

# ── Brand tokens ───────────────────────────────────────────────────────────────
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; BORDER_T = "rgba(45,143,111,.35)"
PURPLE    = "#a78bfa"; PURPLE_GLOW = "rgba(167,139,250,.15)"

GLOBAL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap');
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{NAVY};color:{WHITE};font-family:'DM Sans',ui-sans-serif,system-ui,sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}}
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-track{{background:{NAVY};}}
::-webkit-scrollbar-thumb{{background:{TEAL};border-radius:2px;}}
button{{font-family:inherit;cursor:pointer;border:none;outline:none;}}
input,textarea,select{{font-family:inherit;outline:none;}}
.Select-control,.Select-menu-outer,.Select--single>.Select-control .Select-value,
.Select-placeholder,.Select-value-label{{background:{NAVY_MID} !important;color:{WHITE} !important;}}
.Select-menu-outer{{border:1px solid {BORDER} !important;border-radius:10px !important;overflow:hidden;z-index:9999 !important;}}
.Select-option{{background:{NAVY_MID} !important;color:{TEXT} !important;padding:10px 14px !important;font-size:13px !important;}}
.Select-option:hover,.Select-option.is-focused{{background:{TEAL_GLOW} !important;color:{WHITE} !important;}}
.Select-option.is-selected{{background:rgba(45,143,111,.3) !important;color:{TEAL_DIM} !important;font-weight:700;}}
.Select-arrow{{border-color:{MUTED} transparent transparent !important;}}
.Select-control{{border:1px solid {BORDER} !important;border-radius:10px !important;min-height:40px !important;}}
.Select-control:hover{{border-color:{BORDER_T} !important;}}
.is-open .Select-control{{border-color:{BORDER_T} !important;border-radius:10px 10px 0 0 !important;}}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────

def _track(event_type, symbol, price=None, timeframe=None, regime=None,
           decision_score=None, decision_status=None, metadata=None):
    """Fire-and-forget behavioral event to backend."""
    try:
        req.post(f"{BACKEND_HTTP}/api/behavior/event", json={
            "user_id": USER_ID, "event_type": event_type, "symbol": symbol,
            "price": price, "timeframe": timeframe, "market_regime": regime,
            "decision_score": decision_score, "decision_status": decision_status,
            "metadata": metadata or {},
        }, timeout=2)
    except Exception:
        pass

def _get(path, **params):
    try:
        r = req.get(f"{BACKEND_HTTP}{path}", params=params, timeout=4)
        return r.json() if r.ok else {}
    except Exception:
        return {}

def _post(path, body):
    try:
        r = req.post(f"{BACKEND_HTTP}{path}", json=body, timeout=4)
        return r.json() if r.ok else {}
    except Exception:
        return {}

def _scaled_candles(anchor_price: float, tf: str) -> list[dict]:
    """
    Generate historical candles with proper OHLC structure.
    - Open  : locked at candle start
    - High  : max(open, close) + realistic wick scaled to TF volatility
    - Low   : min(open, close) - realistic wick scaled to TF volatility
    - Close : end price of that period
    - Timestamp: real UTC time anchored so last candle = now
    """
    vol      = TF_VOLATILITY.get(tf, 0.60)
    interval = TF_INTERVAL.get(tf, 300)
    base     = generate_initial_candles(anchor_price)
    n        = len(base)
    now      = datetime.now(timezone.utc)
    out      = []
    for i, c in enumerate(base):
        # Scale body by TF volatility
        body  = (c.c - c.o) * vol
        mid   = (c.o + c.c) / 2
        o     = round(mid - body / 2, 2)
        cl    = round(mid + body / 2, 2)
        # Wick = 30% of body on each side, minimum 0.05% of price
        wick  = max(abs(body) * 0.3, anchor_price * 0.0005)
        h     = round(max(o, cl) + wick, 2)
        l     = round(min(o, cl) - wick, 2)
        # Timestamp: last candle = now, walk backwards
        ts    = now - timedelta(seconds=interval * (n - 1 - i))
        out.append({"o": o, "h": h, "l": l, "c": cl, "t": ts.isoformat()})
    return out

def _regime_from_live(live: dict) -> str:
    score = live.get("decision", {}).get("score", 50)
    price = live.get("price", 100)
    kl    = get_key_levels(price)
    if score >= 80 and price >= kl.expansion: return "expansion"
    if score >= 70:                            return "trend_continuation"
    if score >= 45:                            return "neutral"
    if price <= kl.fail:                       return "reversal"
    return "compression"

# ── UI primitives ──────────────────────────────────────────────────────────────

def badge(text, color="teal"):
    p = {"teal":(TEAL_DIM,TEAL_GLOW,BORDER_T),"blue":(BLUE_DIM,"rgba(59,130,246,.12)","rgba(96,165,250,.35)"),
         "yellow":(YELLOW_DIM,"rgba(245,158,11,.12)","rgba(245,158,11,.35)"),
         "red":(RED_DIM,RED_GLOW,"rgba(239,68,68,.35)"),"gray":(TEXT,"rgba(100,116,139,.12)","rgba(100,116,139,.25)"),
         "purple":(PURPLE,PURPLE_GLOW,"rgba(167,139,250,.35)")}
    fg,bg,bdr = p.get(color, p["teal"])
    return html.Span(text, style={"borderRadius":"999px","border":f"1px solid {bdr}",
        "padding":"4px 12px","fontSize":"11px","fontWeight":"800","letterSpacing":".06em",
        "color":fg,"background":bg,"whiteSpace":"nowrap","textTransform":"uppercase"})

def metric_tile(label, value, accent=WHITE, sub=None):
    return html.Div([
        html.Span(label, style={"display":"block","color":TEXT,"fontSize":"11px","fontWeight":"600",
                                "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Strong(value, style={"display":"block","color":accent,"fontSize":"15px","fontWeight":"800"}),
        *([html.Span(sub, style={"fontSize":"10px","color":MUTED,"marginTop":"2px","display":"block"})] if sub else []),
    ], style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px","minHeight":"64px"})

def card(children, sx=None):
    s = {"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px",
         "padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Section(children, style=s)

def note_box(text, variant=""):
    s = {"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"12px",
         "padding":"12px 14px","color":TEXT,"fontSize":"12px","lineHeight":"1.6"}
    if variant=="yellow": s.update({"borderColor":"rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":"#fef3c7"})
    elif variant=="blue":  s.update({"borderColor":"rgba(59,130,246,.25)","background":"rgba(59,130,246,.08)","color":"#dbeafe"})
    elif variant=="teal":  s.update({"borderColor":BORDER_T,"background":TEAL_GLOW,"color":"#d1fae5"})
    elif variant=="red":   s.update({"borderColor":"rgba(239,68,68,.25)","background":RED_GLOW,"color":"#fecaca"})
    elif variant=="purple":s.update({"borderColor":"rgba(167,139,250,.25)","background":PURPLE_GLOW,"color":"#ede9fe"})
    return html.Div(text, style=s)

def slabel(text):
    return html.Div(text, style={"color":MUTED,"fontSize":"10px","fontWeight":"800",
                                  "textTransform":"uppercase","letterSpacing":".28em","marginBottom":"8px"})

def pbar(label, value, color=None):
    pct = max(0, min(100, value))
    c = color or (TEAL_DIM if pct>=70 else (YELLOW_DIM if pct>=45 else RED_DIM))
    return html.Div([
        html.Div([html.Span(label,style={"color":TEXT,"fontSize":"12px","fontWeight":"600"}),
                  html.Span(f"{pct}%",style={"color":c,"fontWeight":"800","fontSize":"13px"})],
                 style={"display":"flex","justifyContent":"space-between","marginBottom":"6px"}),
        html.Div(html.Div(style={"width":f"{pct}%","height":"100%","borderRadius":"999px",
                                  "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})","transition":"width .5s"}),
                 style={"height":"8px","background":"rgba(255,255,255,.08)","borderRadius":"999px","overflow":"hidden"}),
    ])

def brow(label, value, tone):
    color = TEAL_DIM if tone=="up" else (RED_DIM if tone=="down" else YELLOW_DIM)
    return html.Div([
        html.Div([html.Span(label,style={"fontSize":"13px","fontWeight":"600","color":WHITE}),
                  html.Span(f"{value}%",style={"fontWeight":"800","color":color,"fontSize":"13px"})],
                 style={"display":"flex","justifyContent":"space-between","marginBottom":"6px"}),
        html.Div(html.Div(style={"width":f"{value}%","height":"100%","borderRadius":"999px",
                                  "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})"}),
                 style={"height":"7px","background":"rgba(255,255,255,.08)","borderRadius":"999px","overflow":"hidden"}),
    ], style={"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"12px",
               "padding":"12px 14px","marginBottom":"8px"})

def zcard(name, level, desc, color):
    return html.Div([
        html.P(name, style={"fontSize":"11px","color":TEXT,"margin":"0 0 6px","fontWeight":"600",
                             "textTransform":"uppercase","letterSpacing":".1em"}),
        html.Div(level, style={"fontSize":"26px","fontWeight":"900","color":color,"margin":"4px 0 8px"}),
        html.P(desc,  style={"fontSize":"11px","color":MUTED,"margin":"0"}),
    ], style={"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"14px",
               "padding":"14px","textAlign":"center"})

def _tf_btn_style(tf, active_tf):
    active = tf == active_tf
    return {"background":TEAL_GLOW if active else "transparent","color":TEAL_DIM if active else TEXT,
            "border":f"1px solid {BORDER_T}" if active else "none","borderRadius":"10px",
            "padding":"8px 12px","fontSize":"12px","fontWeight":"800" if active else "700","cursor":"pointer","fontFamily":"inherit"}

def _input_style(width="100%"):
    return {"background":"rgba(0,0,0,.3)","color":WHITE,"border":f"1px solid {BORDER}",
            "borderRadius":"10px","padding":"9px 12px","width":width,"fontSize":"13px",
            "fontWeight":"600","fontFamily":"inherit"}

def _btn(label, id_, color=TEAL_DIM, bg=TEAL_GLOW, border=BORDER_T, extra=None):
    s = {"background":bg,"border":f"1px solid {border}","color":color,"borderRadius":"12px",
         "padding":"10px 18px","fontSize":"13px","fontWeight":"800","cursor":"pointer","fontFamily":"inherit"}
    if extra: s.update(extra)
    return html.Button(label, id=id_, n_clicks=0, style=s)

# ── Chart ──────────────────────────────────────────────────────────────────────

def build_chart(candles, price, nodes, tf="5m"):
    """Clean chart — horizontal level lines only, no right-side annotations."""
    kl = get_key_levels(price)
    xs = [c["t"] for c in candles]
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=xs, open=[c["o"] for c in candles], high=[c["h"] for c in candles],
        low=[c["l"] for c in candles], close=[c["c"] for c in candles], name="Price",
        increasing=dict(line=dict(color=TEAL_DIM, width=1), fillcolor=TEAL_DIM),
        decreasing=dict(line=dict(color=RED_DIM,  width=1), fillcolor=RED_DIM),
        whiskerwidth=0.3,
    ))
    # Make candles wider — auto width based on data density
    fig.update_traces(selector=dict(type="candlestick"),
                      increasing_line_width=2, decreasing_line_width=2)
    # Level lines — no annotations (labels are in the Price Ladder panel)
    for level,color,dash,width in [
        (kl.breakout,   TEAL_DIM,   "dash",    1.0),
        (kl.prior_high, TEAL_DIM,   "dot",     1.0),
        (kl.expansion,  TEAL_DIM,   "dashdot", 1.0),
        (kl.confirm,    YELLOW_DIM, "solid",   1.0),
        (kl.trigger,    YELLOW_DIM, "dash",    1.0),
        (kl.trap,       RED_DIM,    "dot",     1.0),
        (kl.fail,       RED_DIM,    "dash",    1.0),
    ]:
        fig.add_hline(y=level, line_color=color, line_dash=dash,
                      line_width=width, opacity=0.6)
    # Live price line
    fig.add_hline(y=price, line_color=BLUE_DIM, line_dash="solid", line_width=1.5, opacity=0.9)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=NAVY,
        font=dict(family="DM Sans", color=WHITE, size=12),
        xaxis=dict(
            type="date", showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            rangeslider=dict(visible=False),
            showticklabels=True,
            tickformat=TF_TICKFMT.get(tf, "%H:%M"),
            tickfont=dict(color=WHITE, size=12, family="DM Mono, monospace"),
            title=dict(text=f"{tf} · {len(candles)} candles",
                       font=dict(color=WHITE, size=11)),
            color=WHITE,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            color=WHITE, side="right", tickformat=".2f",
            tickfont=dict(color=WHITE, size=12, family="DM Mono, monospace"),
        ),
        # Enough right margin for y-axis labels, bottom for x-axis labels
        margin=dict(l=0, r=60, t=8, b=40),
        height=460,
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor=NAVY_CARD, font_color=WHITE, bordercolor=BORDER, font_size=12),
        dragmode="pan",
    )
    return fig

def _build_clock_inline():
    EST = timezone(timedelta(hours=-4)); now = datetime.now(EST)
    minutes = now.hour*60+now.minute; in_sess = 570<=minutes<=960
    phase = ("Outside RTH" if not in_sess else "Opening Drive" if minutes<630
             else "Midday Auction" if minutes<840 else "Closing Auction")
    pc = TEAL_DIM if in_sess else MUTED
    return [metric_tile("Clock",now.strftime("%I:%M:%S %p")+" ET"),
            html.Div(style={"height":"8px"}),
            metric_tile("Session Phase",phase,pc),
            html.Div(style={"height":"10px"}),
            note_box("Future: economic releases, auction windows, proprietary cycle layers.")]

# ── Trade Plan Panel ───────────────────────────────────────────────────────────
# The INPUT components (buttons, fields) live in the permanent layout via their IDs.
# This function only builds the card SHELL — the inputs are defined once in the layout.

def _build_trade_plan_contents(live):
    """Only updates the header label — buttons/inputs are permanent in layout."""
    price  = live.get("price", 0)
    symbol = live.get("symbol", "")
    return html.Div([
        html.H2("🎯 Plan Trade", style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0"}),
        html.Span(f"{symbol} · ${price:.2f}", style={"fontSize":"12px","color":MUTED}),
    ], style={"display":"flex","justifyContent":"space-between","alignItems":"center"})



# ── Active Trade Panel ─────────────────────────────────────────────────────────

def build_active_trade_panel(trade: dict, current_price: float):
    if not trade:
        return html.Div()
    direction  = trade.get("direction","long")
    entry      = trade.get("entry_price", current_price)
    stop       = trade.get("stop_price")
    target     = trade.get("target_price")
    size       = trade.get("size", 0)
    if direction == "long":
        unreal_pnl = (current_price - entry) * size
        unreal_pct = ((current_price - entry) / entry * 100) if entry else 0
    else:
        unreal_pnl = (entry - current_price) * size
        unreal_pct = ((entry - current_price) / entry * 100) if entry else 0

    pnl_color = TEAL_DIM if unreal_pnl >= 0 else RED_DIM
    entry_time = trade.get("entry_time", "")

    return card([
        html.Div([
            html.H2("📈 Active Trade", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0"}),
            badge(direction.upper(), "teal" if direction=="long" else "red"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"14px"}),

        html.Div([
            metric_tile("Entry",   f"${entry:.2f}",        WHITE),
            metric_tile("Current", f"${current_price:.2f}", BLUE_DIM),
            metric_tile("Unreal P&L", f"${unreal_pnl:+.2f} ({unreal_pct:+.2f}%)", pnl_color),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"8px","marginBottom":"12px"}),

        html.Div([
            metric_tile("Stop",   f"${stop:.2f}"   if stop   else "—", RED_DIM),
            metric_tile("Target", f"${target:.2f}" if target else "—", TEAL_DIM),
            metric_tile("Size",   str(size),        TEXT),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"8px","marginBottom":"14px"}),

        # Exit review fields
        html.Div([
            slabel("Exit Review"),
            html.Div([
                dcc.Checklist(id="exit-flags", options=[
                    {"label": " No trade plan existed",        "value": "no_plan"},
                    {"label": " Stop was moved wider",         "value": "stop_moved_wider"},
                    {"label": " Target moved emotionally",     "value": "target_moved"},
                    {"label": " Exited before invalidation",   "value": "premature_exit"},
                    {"label": " Added size after adverse move","value": "added_size_adverse"},
                    {"label": " Changed TF to justify trade",  "value": "timeframe_changed"},
                ], value=[],
                style={"color":TEXT,"fontSize":"12px","lineHeight":"2"},
                inputStyle={"marginRight":"6px","accentColor":TEAL_DIM}),
            ], style={"marginBottom":"10px"}),
            dcc.Textarea(id="exit-notes", value="", placeholder="Exit notes…",
                style={**_input_style(),"height":"50px","resize":"vertical"}),
        ], style={"borderTop":f"1px solid {BORDER}","paddingTop":"12px","marginBottom":"12px"}),

        _btn("🏁 Exit Trade", "btn-exit-trade",
             color=RED_DIM, bg=RED_GLOW, border="rgba(239,68,68,.35)"),
        html.Div(id="exit-status", style={"marginTop":"8px","fontSize":"12px","color":TEAL_DIM}),

        dcc.Store(id="s-active-trade-id", data=trade.get("trade_id")),
    ])


# ── CSV Import Tab ─────────────────────────────────────────────────────────────

BROKER_INFO = {
    "alpaca":       {"name": "Alpaca",                  "icon": "📊", "priority": "HIGH",   "color": TEAL_DIM},
    "tdameritrade": {"name": "TD Ameritrade / Schwab",  "icon": "🏦", "priority": "HIGH",   "color": TEAL_DIM},
    "ibkr":         {"name": "Interactive Brokers",     "icon": "🌐", "priority": "HIGH",   "color": TEAL_DIM},
    "robinhood":    {"name": "Robinhood",               "icon": "🪶", "priority": "HIGH",   "color": TEAL_DIM},
    "webull":       {"name": "Webull",                  "icon": "🐂", "priority": "MEDIUM", "color": YELLOW_DIM},
    "generic":      {"name": "Generic CSV",             "icon": "📄", "priority": "ALWAYS", "color": BLUE_DIM},
}

EXPORT_INSTRUCTIONS = {
    "alpaca": [
        "Log in to Alpaca dashboard",
        "Go to Account → Activity",
        "Select date range → Export CSV",
        "Upload the downloaded file here",
    ],
    "tdameritrade": [
        "Log in to thinkorswim or TDA web",
        "Go to My Account → History & Statements",
        "Select Trade History → Export to CSV",
        "Upload the downloaded file here",
    ],
    "ibkr": [
        "Log in to Client Portal or TWS",
        "Go to Reports → Flex Query",
        "Create a Trade Confirmation Flex Query",
        "Export as CSV and upload here",
    ],
    "robinhood": [
        "Log in to Robinhood web (not mobile)",
        "Go to Account → Statements & History",
        "Download Account Statement CSV",
        "Upload the downloaded file here",
    ],
    "webull": [
        "Log in to Webull desktop app",
        "Go to Orders → Order History",
        "Click Export in top right",
        "Upload the downloaded CSV here",
    ],
    "generic": [
        "Export your trade history from any broker",
        "Ensure CSV has: Symbol, Side (buy/sell), Quantity, Price, Date",
        "Upload and map columns if needed",
    ],
}

def build_import_tab():
    # Fetch latest analysis if exists
    analysis = _get(f"/api/import/analysis/{USER_ID}")

    ROW = {"display":"flex","gap":"16px","marginBottom":"16px"}

    # ── Broker cards ──────────────────────────────────────────────────────────
    broker_cards = []
    for key, info in BROKER_INFO.items():
        priority_color = (TEAL_DIM if info["priority"]=="HIGH"
                         else YELLOW_DIM if info["priority"]=="MEDIUM"
                         else BLUE_DIM)
        broker_cards.append(html.Div([
            html.Div([
                html.Span(info["icon"], style={"fontSize":"24px"}),
                html.Div([
                    html.Div(info["name"],
                             style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                    html.Span(info["priority"],
                              style={"fontSize":"10px","fontWeight":"800","color":priority_color,
                                     "letterSpacing":".1em"}),
                ]),
            ], style={"display":"flex","alignItems":"center","gap":"10px","marginBottom":"10px"}),
            *[html.P(f"• {step}",
                     style={"fontSize":"11px","color":MUTED,"marginBottom":"4px","lineHeight":"1.5"})
              for step in EXPORT_INSTRUCTIONS[key]],
        ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
                   "borderRadius":"14px","padding":"14px","flex":"1","minWidth":"200px"}))

    # ── Upload section ────────────────────────────────────────────────────────
    upload_section = card([
        html.H2("📤 Upload Brokerage History",
                style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"6px"}),
        html.P("Upload your brokerage trade export and we'll instantly build your behavioral profile.",
               style={"fontSize":"12px","color":MUTED,"marginBottom":"16px"}),

        # Broker cards
        html.Div(broker_cards,
                 style={"display":"flex","flexWrap":"wrap","gap":"12px","marginBottom":"20px"}),

        # Upload widget
        html.Div([
            dcc.Upload(
                id="csv-upload",
                children=html.Div([
                    html.Div("📂", style={"fontSize":"32px","marginBottom":"8px"}),
                    html.Div("Drag & drop your CSV here, or click to browse",
                             style={"fontSize":"14px","fontWeight":"700","color":WHITE,"marginBottom":"4px"}),
                    html.Div("Supports: Alpaca · TD Ameritrade · Schwab · IBKR · Robinhood · Webull · Generic CSV",
                             style={"fontSize":"11px","color":MUTED}),
                ], style={"textAlign":"center","padding":"20px"}),
                style={
                    "border":f"2px dashed {BORDER_T}",
                    "borderRadius":"16px",
                    "background":TEAL_GLOW,
                    "cursor":"pointer",
                    "marginBottom":"14px",
                    "transition":"border-color .2s",
                },
                accept=".csv",
                multiple=False,
            ),
            html.Div(id="csv-upload-status",
                     style={"fontSize":"13px","color":TEAL_DIM,"minHeight":"20px"}),
        ]),
    ])

    # ── Analysis display ──────────────────────────────────────────────────────
    if not analysis:
        analysis_section = card([
            note_box("No import history yet. Upload your brokerage CSV above to generate your behavioral snapshot.", "blue")
        ])
    else:
        total   = analysis.get("total_trades", 0)
        wr      = analysis.get("win_rate", 0)
        pnl     = analysis.get("total_pnl", 0)
        avg_win = analysis.get("avg_win", 0)
        avg_loss= analysis.get("avg_loss", 0)
        rr      = analysis.get("rr_ratio", 0)
        edge    = analysis.get("edge_score", 0)
        hold    = analysis.get("avg_hold_time", "—")
        best_d  = analysis.get("best_day")
        worst_d = analysis.get("worst_day")
        best_s  = analysis.get("best_symbol")
        worst_s = analysis.get("worst_symbol")
        flags   = analysis.get("behavioral_flags", [])
        overtrade = analysis.get("overtrade_rate", 0)
        sym_perf  = analysis.get("symbol_performance", {})
        day_perf  = analysis.get("day_performance", {})

        wr_color  = TEAL_DIM if wr>=55 else (YELLOW_DIM if wr>=45 else RED_DIM)
        pnl_color = TEAL_DIM if pnl>=0 else RED_DIM
        edge_color= TEAL_DIM if edge>0 else RED_DIM
        rr_color  = TEAL_DIM if rr>=1.5 else (YELLOW_DIM if rr>=1.0 else RED_DIM)

        # Mathematical edge insight
        if edge > 0:
            edge_insight = f"Your system has a positive mathematical edge of ${edge:.2f} per trade."
        else:
            edge_insight = f"Your system has a negative edge of ${edge:.2f} per trade — the math works against you long-term."

        # Top symbols table
        top_syms = sorted(sym_perf.items(), key=lambda x: x[1]["total_pnl"], reverse=True)[:8]
        sym_rows = []
        for sym, sp in top_syms:
            c = TEAL_DIM if sp["total_pnl"]>=0 else RED_DIM
            sym_rows.append(html.Tr([
                html.Td(sym, style={"color":WHITE,"fontWeight":"700","padding":"8px 12px","fontSize":"12px"}),
                html.Td(str(sp["trades"]), style={"color":TEXT,"padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"{sp['win_rate']:.0f}%", style={"color":TEAL_DIM if sp['win_rate']>=50 else RED_DIM,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"${sp['total_pnl']:+.2f}", style={"color":c,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"right"}),
            ], style={"borderBottom":f"1px solid {BORDER}"}))

        analysis_section = html.Div([
            # Score cards
            card([
                html.H2("📊 Historical Behavioral Snapshot",
                        style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
                html.Div([
                    metric_tile("Total Trades",    str(total),          WHITE),
                    metric_tile("Win Rate",        f"{wr}%",            wr_color),
                    metric_tile("Total P&L",       f"${pnl:+,.2f}",     pnl_color),
                    metric_tile("Avg Win",         f"${avg_win:+.2f}",  TEAL_DIM),
                    metric_tile("Avg Loss",        f"${avg_loss:+.2f}", RED_DIM),
                    metric_tile("Risk/Reward",     f"{rr:.2f}x",        rr_color),
                    metric_tile("Avg Hold Time",   hold,                BLUE_DIM),
                    metric_tile("Overtrade Rate",  f"{overtrade:.0f}%", YELLOW_DIM if overtrade>20 else TEXT),
                ], style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"10px","marginBottom":"16px"}),

                # Mathematical edge
                html.Div([
                    html.Span("⚡ Mathematical Edge: ",
                              style={"fontWeight":"800","color":edge_color,"fontSize":"13px"}),
                    html.Span(edge_insight, style={"color":TEXT,"fontSize":"12px"}),
                ], style={"background":"rgba(0,0,0,.2)","borderRadius":"12px","padding":"12px 16px",
                           "border":f"1px solid {BORDER}","marginBottom":"12px"}),

                # Best/worst
                html.Div([
                    html.Div([
                        html.Span("🟢 Best Day: ",   style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px"}),
                        html.Span(best_d or "—",      style={"color":WHITE,"fontSize":"12px"}),
                        html.Span("   🔴 Worst Day: ",style={"color":RED_DIM,"fontWeight":"700","fontSize":"12px","marginLeft":"16px"}),
                        html.Span(worst_d or "—",     style={"color":WHITE,"fontSize":"12px"}),
                    ]),
                    html.Div([
                        html.Span("🟢 Best Symbol: ",  style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px"}),
                        html.Span(best_s or "—",        style={"color":WHITE,"fontSize":"12px"}),
                        html.Span("   🔴 Worst Symbol: ",style={"color":RED_DIM,"fontWeight":"700","fontSize":"12px","marginLeft":"16px"}),
                        html.Span(worst_s or "—",       style={"color":WHITE,"fontSize":"12px"}),
                    ], style={"marginTop":"6px"}),
                ], style={"background":"rgba(0,0,0,.2)","borderRadius":"12px","padding":"12px 16px",
                           "border":f"1px solid {BORDER}"}),
            ]),

            html.Div(style={"height":"16px"}),

            html.Div([
                # Behavioral flags
                card([
                    html.H2("🚩 Behavioral Flags",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
                    *([html.Div([
                        html.Span("✅ " if any(w in f for w in ["Strong","Above","positive","discipline"])
                                  else "⚠️ ",
                                  style={"fontSize":"14px"}),
                        html.Span(f, style={"fontSize":"12px","color":TEXT,"lineHeight":"1.6"}),
                    ], style={"padding":"8px 12px","borderRadius":"10px","marginBottom":"6px",
                               "background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}"})
                      for f in flags]
                     if flags else [note_box("No behavioral flags detected yet.", "blue")]),
                ], sx={"flex":"1"}),

                # Symbol performance table
                card([
                    html.H2("📈 Symbol Performance",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
                    html.Table([
                        html.Thead(html.Tr([
                            html.Th("Symbol",  style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"left"}),
                            html.Th("Trades",  style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"center"}),
                            html.Th("Win %",   style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"center"}),
                            html.Th("Total P&L",style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"right"}),
                        ])),
                        html.Tbody(sym_rows if sym_rows
                                   else [html.Tr([html.Td("No data",colSpan=4,
                                                           style={"color":MUTED,"padding":"16px","textAlign":"center"})])]),
                    ], style={"width":"100%","borderCollapse":"collapse"}),
                ], sx={"flex":"1"}),
            ], style={**ROW,"alignItems":"start"}),
        ])

    return html.Div([upload_section, html.Div(style={"height":"16px"}), analysis_section])


# ── Behavioral Dashboard Tab ───────────────────────────────────────────────────

def build_behavior_tab():
    dash_data = _get(f"/api/behavior/dashboard/{USER_ID}")
    if not dash_data:
        return card([note_box("No behavioral data yet. Start tracking trades to build your profile.", "blue")])

    total    = dash_data.get("total_trades", 0)
    comp     = dash_data.get("avg_decision_score", 0)
    exec_    = dash_data.get("execution_score", 0)
    disc     = dash_data.get("discipline_score", 0)
    timing   = dash_data.get("timing_score", 0)
    risk     = dash_data.get("risk_score", 0)
    flag     = dash_data.get("common_behavior_flag", "neutral")
    best_r   = dash_data.get("best_regime")
    worst_r  = dash_data.get("worst_regime")
    regimes  = dash_data.get("regime_performance", [])
    cards_   = dash_data.get("recent_scorecards", [])
    warnings = dash_data.get("adaptive_warnings", [])

    def score_color(v): return TEAL_DIM if v>=70 else (YELLOW_DIM if v>=45 else RED_DIM)

    flag_color = {
        "plan_followed":"teal","disciplined_execution":"teal",
        "late_chase":"yellow","premature_exit":"yellow","panic_exit":"red",
        "plan_violated":"red","over_sized":"red","ignored_high_quality_signal":"yellow",
        "revenge_trade":"red","neutral":"gray","under_sized":"gray",
    }.get(flag, "gray")

    ROW = {"display":"flex","gap":"16px","marginBottom":"16px"}

    # Section 1 — Profile scores
    section1 = card([
        html.H2("🧠 Behavioral Profile", style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
        html.Div([
            metric_tile("Total Trades",    str(total),          WHITE),
            metric_tile("Composite Score", f"{comp}%",          score_color(comp)),
            metric_tile("Execution",       f"{exec_}%",         score_color(exec_)),
            metric_tile("Discipline",      f"{disc}%",          score_color(disc)),
            metric_tile("Timing",          f"{timing}%",        score_color(timing)),
            metric_tile("Risk Mgmt",       f"{risk}%",          score_color(risk)),
        ], style={"display":"grid","gridTemplateColumns":"repeat(6,1fr)","gap":"10px","marginBottom":"16px"}),
        html.Div([
            pbar("Composite Decision Score", comp),
            html.Div(style={"height":"8px"}),
            pbar("Execution Quality",        exec_),
            html.Div(style={"height":"8px"}),
            pbar("Discipline",               disc),
            html.Div(style={"height":"8px"}),
            pbar("Timing Quality",           timing),
            html.Div(style={"height":"8px"}),
            pbar("Risk Management",          risk),
        ]),
    ])

    # Section 2 — Adaptive warnings
    def warn_box(w):
        variant = "teal" if w["type"]=="strength" else "yellow"
        icon    = "✅" if w["type"]=="strength" else "⚠️"
        return note_box(f"{icon}  {w['message']}", variant)

    section2 = card([
        html.H2("🔔 Adaptive Guidance", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        *([warn_box(w) for w in warnings] if warnings
          else [note_box("No active warnings. Keep trading to build your profile.", "blue")]),
        html.Div(style={"height":"8px"}),
        html.Div([
            html.Span("Most Common Pattern: ", style={"fontSize":"12px","color":TEXT}),
            badge(flag.replace("_"," "), flag_color),
        ], style={"marginTop":"10px"}),
        html.Div([
            *([html.Div([html.Span("Best Regime: ", style={"fontSize":"12px","color":TEXT}),
                         badge(best_r.replace("_"," "), "teal")],
                        style={"marginTop":"8px"})] if best_r else []),
            *([html.Div([html.Span("Worst Regime: ", style={"fontSize":"12px","color":TEXT}),
                         badge(worst_r.replace("_"," "), "red")],
                        style={"marginTop":"8px"})] if worst_r else []),
        ]),
    ])

    # Section 3 — Regime table
    regime_rows_html = []
    for r in regimes:
        wr_color  = TEAL_DIM if r["win_rate"]>=60 else (YELLOW_DIM if r["win_rate"]>=40 else RED_DIM)
        dec_color = TEAL_DIM if r["avg_decision_score"]>=70 else (YELLOW_DIM if r["avg_decision_score"]>=45 else RED_DIM)
        regime_rows_html.append(html.Tr([
            html.Td(r["regime"].replace("_"," ").title(),
                    style={"color":WHITE,"fontWeight":"600","padding":"10px 12px","fontSize":"12px"}),
            html.Td(str(r["total_trades"]),
                    style={"color":TEXT,"padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(f"{r['win_rate']:.0f}%",
                    style={"color":wr_color,"fontWeight":"800","padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(f"{r['avg_decision_score']:.0f}",
                    style={"color":dec_color,"fontWeight":"800","padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(r.get("common_behavior_flag","—").replace("_"," "),
                    style={"color":MUTED,"padding":"10px 12px","fontSize":"11px"}),
        ], style={"borderBottom":f"1px solid {BORDER}"}))

    section3 = card([
        html.H2("📊 Regime Performance Memory", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"14px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Regime",           style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"left"}),
                html.Th("Trades",           style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Win Rate",         style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Avg Score",        style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Common Pattern",   style={"color":MUTED,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"left"}),
            ])),
            html.Tbody(regime_rows_html if regime_rows_html
                       else [html.Tr([html.Td("No regime data yet.",
                                               colSpan=5,style={"color":MUTED,"padding":"20px","textAlign":"center"})])]),
        ], style={"width":"100%","borderCollapse":"collapse"}),
    ]) if True else html.Div()

    # Section 4 — Recent scorecards
    def scorecard_row(s):
        c = TEAL_DIM if s["composite_decision_score"]>=70 else (YELLOW_DIM if s["composite_decision_score"]>=45 else RED_DIM)
        pnl = s.get("pnl_percent")
        pnl_str = f"{pnl:+.2f}%" if pnl is not None else "—"
        pnl_c = TEAL_DIM if (pnl or 0)>0 else RED_DIM
        return html.Div([
            html.Div([
                html.Span(s.get("symbol","—"), style={"fontWeight":"800","color":WHITE,"fontSize":"13px"}),
                html.Span(s.get("direction","").upper() if s.get("direction") else "",
                          style={"fontSize":"10px","color":MUTED,"marginLeft":"8px"}),
                html.Span(s.get("primary_behavior_flag","").replace("_"," "),
                          style={"fontSize":"10px","color":MUTED,"marginLeft":"8px"}),
            ]),
            html.Div([
                html.Span(f"Score: {s['composite_decision_score']:.0f}",
                          style={"color":c,"fontWeight":"800","fontSize":"13px"}),
                html.Span(f"P&L: {pnl_str}",
                          style={"color":pnl_c,"fontWeight":"700","fontSize":"12px","marginLeft":"12px"}),
                html.Span(s.get("timestamp","")[:16] if s.get("timestamp") else "",
                          style={"color":MUTED,"fontSize":"11px","marginLeft":"12px"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"10px 14px","borderBottom":f"1px solid {BORDER}",
                   "borderRadius":"10px","background":"rgba(0,0,0,.15)","marginBottom":"6px"})

    section4 = card([
        html.H2("📋 Recent Decision Scorecards", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        *([scorecard_row(s) for s in cards_] if cards_
          else [note_box("No scorecards yet. Complete a trade to generate your first scorecard.", "blue")]),
    ])

    return html.Div([section1, html.Div(style={"height":"16px"}),
                     html.Div([section2, section3], style={**ROW,"alignItems":"start"}),
                     html.Div(style={"height":"16px"}), section4])

# ── Command tab ────────────────────────────────────────────────────────────────

def build_command_tab(live, candles, symbol, tf):
    price    = live["price"]; decision = live["decision"]
    nodes    = live["confluence"]; kl = get_key_levels(price)
    seq      = live["sequence"]; score = decision["score"]
    try:
        ts = datetime.fromisoformat(live["timestamp"].replace("Z","+00:00"))
        ts = ts.astimezone(timezone(timedelta(hours=-4))); live_age = ts.strftime("%I:%M:%S %p")
    except: live_age = "—"
    sc   = TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    size = "FULL" if score>=80 else ("HALF" if score>=65 else ("PROBE" if score>=45 else "NONE"))
    top  = nodes[0] if nodes else {"public_label":"—","score":0}
    vs   = max(18,min(96,round(abs(price-kl.trigger)*18+(seq%9)*4)))
    cp   = max(12,min(94,round(score+(8 if price>kl.confirm else -10)+(seq%5))))
    pp   = max(8,min(92,100-cp)); gp = max(20,min(95,round(55+(price-kl.confirm)*7)))
    fb   = "Call Accumulation / Supportive Flow" if price>=kl.confirm else "Neutral Rotation / Pinning"
    as_  = "Expansion Alert" if score>=80 else ("Trap-Door Alert" if price<kl.trap else "Monitoring")
    aa   = as_ != "Monitoring"
    fig  = build_chart(candles, price, nodes, tf)
    ROW  = {"display":"flex","gap":"16px","marginBottom":"16px"}
    regime = _regime_from_live(live)

    # ── Price Ladder row helper ───────────────────────────────────────────────
    def level_row(label, level, color, is_live=False, arrow=""):
        bg  = "rgba(45,143,111,.15)" if is_live else "transparent"
        bdr = f"1px solid {BORDER_T}" if is_live else f"1px solid {BORDER}"
        return html.Div([
            html.Div([
                html.Span(arrow+" " if arrow else "",
                          style={"color":color,"fontWeight":"900","fontSize":"11px","marginRight":"2px"}),
                html.Span(label,
                          style={"fontSize":"11px","fontWeight":"700","color":TEXT,
                                 "textTransform":"uppercase","letterSpacing":".08em"}),
            ], style={"flex":"1"}),
            html.Span(f"${level:.2f}",
                      style={"fontSize":"16px","fontWeight":"900","color":WHITE,
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"9px 12px","borderRadius":"10px","marginBottom":"5px",
                   "background":bg,"border":bdr})

    # ── LEFT: Price Ladder ────────────────────────────────────────────────────
    price_ladder = html.Div([
        card([
            slabel("Price Ladder"),
            level_row("Breakout",  kl.breakout,   TEAL_DIM,  arrow="▲"),
            level_row("Liquidity", kl.prior_high, TEAL_DIM,  arrow="▲"),
            level_row("Expansion", kl.expansion,  TEAL_DIM,  arrow="▲"),
            html.Div(style={"height":"3px","background":BORDER,"borderRadius":"2px","margin":"5px 0"}),
            level_row("Live Price",price,          BLUE_DIM,  is_live=True),
            html.Div(style={"height":"3px","background":BORDER,"borderRadius":"2px","margin":"5px 0"}),
            level_row("Trigger",   kl.trigger,    YELLOW_DIM,arrow="▼"),
            level_row("Trap Door", kl.trap,       RED_DIM,   arrow="▼"),
            level_row("Fail Gate", kl.fail,       RED_DIM,   arrow="▼"),
            html.Div(style={"flex":"1"}),  # pushes Distance to bottom
            html.Hr(style={"border":"none","borderTop":f"1px solid {BORDER}","margin":"0 0 12px"}),
            slabel("Distance"),
            html.Div([
                html.Div([
                    html.Span("↑ Breakout",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"+{((kl.breakout-price)/price*100):.2f}%",
                              style={"fontSize":"14px","color":TEAL_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"}),
                html.Div([
                    html.Span("↓ Fail Gate",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"-{((price-kl.fail)/price*100):.2f}%",
                              style={"fontSize":"14px","color":RED_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"}),
                html.Div([
                    html.Span("R/R Ratio",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"{((kl.breakout-price)/(price-kl.fail)):.1f}x" if price>kl.fail else "—",
                              style={"fontSize":"14px","color":YELLOW_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between"}),
            ], style={"background":"rgba(0,0,0,.2)","borderRadius":"10px","padding":"14px",
                       "border":f"1px solid {BORDER}"}),
        ], sx={"flex":"1","display":"flex","flexDirection":"column"}),
    ], style={"flex":"0 0 230px","minWidth":"0","display":"flex","flexDirection":"column"})

    # ── CENTER: Chart — fills the card tile completely ────────────────────────
    chart_panel = card([
        # Header row
        html.Div([
            html.Div([
                html.Span(f"📊 {symbol}  ·  Smart Chart",
                          style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                html.Span(f"  {live_age}  ·  {tf}  ·  {regime.replace('_',' ').title()}",
                          style={"fontSize":"10px","color":MUTED}),
            ]),
            html.Span(f"${price:.2f}",
                      style={"fontSize":"14px","fontWeight":"900","color":WHITE,
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "marginBottom":"6px"}),

        # Chart — fills remaining space
        html.Div(
            dcc.Graph(figure=fig,
                      config={"displayModeBar":False,"scrollZoom":True,"displaylogo":False},
                      style={"height":"100%"}),
            style={"flex":"1","margin":"0 -20px 0 -20px","overflow":"hidden"},
        ),

        # Footer — aligned with Distance box at bottom of price ladder
        html.Div([
            html.Span(f"{tf} · {len(candles)} candles",
                      style={"fontSize":"12px","color":WHITE,"fontWeight":"600",
                             "fontFamily":"DM Mono, monospace"}),
            html.Span(f"Vol {live['volume']:,}",
                      style={"fontSize":"12px","color":MUTED}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"10px 0 0 0","borderTop":f"1px solid {BORDER}","marginTop":"8px"}),

    ], sx={"flex":"1","minWidth":"0","padding":"16px 20px 12px 20px",
            "overflow":"hidden","display":"flex","flexDirection":"column"})

    # ── Row 1 ─────────────────────────────────────────────────────────────────
    row1 = html.Div([price_ladder, chart_panel],
                    style={"display":"flex","gap":"16px","marginBottom":"16px",
                           "alignItems":"stretch"})

    # ── Row 2: Decision Engine + Trade Card + Probability Ladder (ONE card) ──
    row2 = card([
        html.Div([

            # Column A — Decision Engine signal
            html.Div([
                slabel("Decision Engine"),
                html.Div(decision["status"],
                         style={"color":sc,"fontSize":"28px","fontWeight":"900",
                                "lineHeight":"1","letterSpacing":"-.02em","margin":"6px 0 4px"}),
                html.Div(f"LIVE STATE: {decision['behavior']}",
                         style={"fontSize":"9px","fontWeight":"800","color":TEXT,
                                "textTransform":"uppercase","letterSpacing":".1em","marginBottom":"8px"}),
                html.Div(decision["next_action"],
                         style={"color":TEXT,"fontSize":"11px","fontWeight":"600",
                                "lineHeight":"1.5","marginBottom":"6px"}),
                pbar("Signal Strength", score),
                html.Div(style={"height":"8px"}),
                html.Div([
                    metric_tile("Bias",       decision["bias"],       sc),
                    metric_tile("Grade",      decision["grade"],      sc),
                    metric_tile("Confidence", decision["confidence"], sc),
                    metric_tile("Mode",       decision["mode"],       BLUE_DIM),
                ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"6px"}),
            ], style={"flex":"1.2","minWidth":"160px",
                       "borderRight":f"1px solid {BORDER}","paddingRight":"16px"}),

            # Column B — Trade Card
            html.Div([
                slabel("Trade Card"),
                html.Div(style={"height":"6px"}),
                html.Div([
                    html.Span("Bias  ",style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                                              "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(decision["bias"],style={"fontSize":"13px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"8px"}),
                html.Div([
                    html.Span("Setup  ",style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                                               "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(decision["status"],style={"fontSize":"13px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"8px"}),
                html.Div([
                    html.Span("Size  ",style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                                              "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(size,style={"fontSize":"22px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"10px"}),
                note_box(f"Ref: ${price:.2f}  ·  A-grade requires live-volume expansion.","yellow"),
            ], style={"flex":"1","minWidth":"140px",
                       "borderRight":f"1px solid {BORDER}","padding":"0 16px"}),

            # Column C — Probability Ladder
            html.Div([
                slabel("Probability Ladder"),
                html.Div(style={"height":"6px"}),
                brow("Upside Expansion", nodes[0]["score"] if nodes else 63, "up"),
                html.P(f"Level ${nodes[0]['level']:.2f}" if nodes else "",
                       style={"fontSize":"9px","color":MUTED,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Liquidity Retest", nodes[1]["score"] if len(nodes)>1 else 60, "up"),
                html.P(f"Level ${nodes[1]['level']:.2f}" if len(nodes)>1 else "",
                       style={"fontSize":"9px","color":MUTED,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Hold / Balance", score, "neutral"),
                html.P(f"Level ${kl.confirm:.2f}",
                       style={"fontSize":"9px","color":MUTED,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Failure Gate", 100-score, "down"),
                html.P(f"Level ${kl.fail:.2f}",
                       style={"fontSize":"9px","color":MUTED,"marginTop":"-3px"}),
            ], style={"flex":"1.5","minWidth":"180px","paddingLeft":"16px"}),

        ], style={"display":"flex","gap":"0","alignItems":"flex-start","flexWrap":"wrap"}),
    ], sx={"marginBottom":"16px"})

    # ── Row 3: Options Matrix ─────────────────────────────────────────────────
    row3 = card([
        html.Div([
            html.Div([
                html.H2("🧱 Dynamic Options Matrix + Flow Map",
                        style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                html.P("Synthetic intelligence from price, volume, volatility proxy, and decision score.",
                       style={"fontSize":"12px","color":TEXT})]),
            badge(fb,"blue"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                   "flexWrap":"wrap","gap":"10px","marginBottom":"14px"}),
        html.Div([
            zcard("Call Wall",   f"${round(kl.breakout):.0f}",  f"{cp}% call-side pressure", TEAL_DIM),
            zcard("Put Wall",    f"${round(kl.fail):.0f}",     f"{pp}% put-side pressure",  RED_DIM),
            zcard("Gamma Pivot", f"${round(kl.confirm):.0f}",  f"{gp}% dealer sensitivity", YELLOW_DIM),
            zcard("Vol Trigger", "LIVE",                        f"{vs}% expansion energy",   TEAL_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"12px"}),
        note_box("Synthetic options layer — connect Tradier or CBOE for live institutional flow data.","blue"),
    ], sx={"marginBottom":"16px"})

    # ── Row 4: Time Engine + Alerts + Footer ──────────────────────────────────
    # Clock with white text
    EST = timezone(timedelta(hours=-4)); now = datetime.now(EST)
    minutes = now.hour*60+now.minute; in_sess = 570<=minutes<=960
    phase = ("Outside RTH" if not in_sess else "Opening Drive" if minutes<630
             else "Midday Auction" if minutes<840 else "Closing Auction")
    phase_color = TEAL_DIM if in_sess else MUTED

    row4 = html.Div([
        card([
            html.H2("⏱️ Time Engine",
                    style={"fontSize":"14px","fontWeight":"800","color":WHITE,"margin":"0 0 12px"}),
            html.Div(now.strftime("%I:%M:%S %p")+" ET",
                     style={"fontSize":"22px","fontWeight":"900","color":WHITE,
                            "fontFamily":"DM Mono, monospace","marginBottom":"8px"}),
            html.Div(phase,
                     style={"fontSize":"13px","fontWeight":"800","color":phase_color,"marginBottom":"8px"}),
            note_box("Future: economic releases, auction windows, proprietary cycle layers."),
        ], sx={"flex":"1"}),

        card([
            html.Div([
                html.H2("🔔 Visual + Audio Alerts",
                        style={"fontSize":"14px","fontWeight":"800","color":WHITE,"margin":"0"}),
                html.Button("🔔 ON", id="btn-alerts-toggle", n_clicks=0,
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
                           "borderRadius":"20px","padding":"4px 12px","fontSize":"11px",
                           "fontWeight":"800","cursor":"pointer"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"12px"}),
            html.Div(as_, style={
                "borderRadius":"12px","padding":"12px","textAlign":"center","fontWeight":"900",
                "fontSize":"12px","letterSpacing":".06em","textTransform":"uppercase",
                **({"border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM} if aa
                   else {"border":"1px solid rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM}),
            }),
            html.Div([
                html.Span(f"Score: {score}",
                          style={"fontSize":"11px","color":WHITE,"marginTop":"8px","display":"block","fontWeight":"700"}),
                html.Span(
                    "🔴 Trap Door" if score<35 else
                    ("🟢 A-Grade — Audio Active" if score>=80 else
                     "🟡 B-Grade — Audio Active" if score>=55 else "⚪ Monitoring"),
                    style={"fontSize":"11px","fontWeight":"700","marginTop":"3px","display":"block",
                           "color":RED_DIM if score<35 else (TEAL_DIM if score>=55 else MUTED)}),
            ]),
        ], sx={"flex":"1"}),

        card([html.Div([
            metric_tile("Symbol",       symbol,                           WHITE),
            metric_tile("Live Price",   f"${price:.2f}",                 WHITE),
            metric_tile("Engine Score", f"{score}%",                     sc),
            metric_tile("Regime",       regime.replace("_"," ").title(), YELLOW_DIM),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"10px"})], sx={"flex":"1"}),

    ], style={**ROW,"alignItems":"start","marginBottom":"16px"})

    return html.Div([row1, row2, row3, row4],
                    style={"display":"flex","flexDirection":"column"})


def build_feed_tab(live, live_mode):
    price = live["price"]
    return card([
        html.Div([
            html.Div([html.H2("🔌 Live Feed Monitor",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                      html.P(f"Backend: {BACKEND_HTTP}",style={"fontSize":"12px","color":MUTED})]),
            badge("Connected" if live_mode else "Synthetic","teal" if live_mode else "gray"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"16px"}),
        html.Div([
            metric_tile("Feed Mode","Live Alpaca" if live_mode else "Synthetic"),
            metric_tile("Symbol",live["symbol"]),
            metric_tile("Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Volume",f"{live['volume']:,}"),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"16px"}),
        html.Pre(json.dumps(live,indent=2),style={"margin":"0","maxHeight":"460px","overflow":"auto","borderRadius":"14px",
            "border":f"1px solid {BORDER}","background":"rgba(0,0,0,.35)","padding":"16px",
            "color":TEAL_DIM,"fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.6"}),
    ])

def build_performance_tab(live):
    price=live["price"]; decision=live["decision"]; score=decision["score"]
    sc=TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    return card([
        html.H2("📈 Performance Logger",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Div([
            metric_tile("Current Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Setup",decision["status"],sc),
            metric_tile("Score",f"{score}%",sc),
            metric_tile("Bias",decision["bias"],BLUE_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
        note_box("Trade logging reconnects automatically once live feed stabilizes."),
    ])

def build_setup_tab():
    return card([
        html.H2("🧩 Setup & Deployment",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Pre(
            f"Frontend  : Dash (Python)  →  Render\n"
            f"Backend   : FastAPI        →  Render\n"
            f"Data      : Alpaca IEX (free) / SIP (paid)\n"
            f"WebSocket : {BACKEND_WS}/ws/{{symbol}}\n"
            f"REST      : {BACKEND_HTTP}/api/stock/{{symbol}}\n"
            f"Behavior  : {BACKEND_HTTP}/api/behavior/*\n\n"
            f"Env vars:\n"
            f"  ALPACA_API_KEY     — Alpaca key ID\n"
            f"  ALPACA_API_SECRET  — Alpaca secret\n"
            f"  BACKEND_URL        — HTTP base URL\n"
            f"  BACKEND_WS_URL     — WebSocket base URL\n"
            f"  BEHAVIOR_DB        — SQLite path (default: behavior.db)",
            style={"margin":"0","borderRadius":"14px","border":f"1px solid {BORDER}",
                   "background":"rgba(0,0,0,.35)","padding":"16px","color":TEAL_DIM,
                   "fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.7"}),
    ])

# ── App ────────────────────────────────────────────────────────────────────────

LOGO = html.Div([
    html.Div("Σ",style={"fontSize":"28px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1",
                         "fontFamily":"Georgia, serif","marginRight":"4px","flexShrink":"0"}),
    html.Div([
        html.Span("SIGMALYTIC",style={"fontSize":"18px","fontWeight":"900","color":WHITE,"letterSpacing":".08em","lineHeight":"1"}),
        html.Span("QUANT CORPORATION",style={"fontSize":"9px","fontWeight":"700","color":TEAL_DIM,"letterSpacing":".22em","display":"block","marginTop":"2px"}),
    ]),
], style={"display":"flex","alignItems":"center","gap":"10px"})

app = dash.Dash(__name__, title="Sigmalytic Quant Corporation — Decision Intelligence",
                update_title=None, suppress_callback_exceptions=True,
                meta_tags=[{"name":"viewport","content":"width=device-width, initial-scale=1"},
                           {"name":"theme-color","content":NAVY}])
server = app.server

app.index_string = f"""<!DOCTYPE html>
<html><head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
<style>{GLOBAL_CSS}</style></head>
<body>{{%app_entry%}}<footer>{{%config%}}</footer>{{%scripts%}}{{%renderer%}}
<script>
window._sigmaAudioCtx = null;
function _getAudioCtx() {{
    if (!window._sigmaAudioCtx) {{
        window._sigmaAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }}
    return window._sigmaAudioCtx;
}}
function sigmaBeep(freq, duration, gain) {{
    try {{
        var ctx = _getAudioCtx();
        var osc = ctx.createOscillator();
        var vol = ctx.createGain();
        osc.connect(vol);
        vol.connect(ctx.destination);
        osc.frequency.value = freq;
        osc.type = 'sine';
        vol.gain.setValueAtTime(gain || 0.3, ctx.currentTime);
        vol.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + duration);
    }} catch(e) {{ console.warn('Audio error:', e); }}
}}
function sigmaAlert(level) {{
    if (level === 'A') {{
        // Three rising tones — A grade signal
        sigmaBeep(523, 0.15, 0.4);
        setTimeout(function(){{ sigmaBeep(659, 0.15, 0.4); }}, 160);
        setTimeout(function(){{ sigmaBeep(784, 0.3,  0.5); }}, 320);
    }} else if (level === 'B') {{
        // Two tones — B tactical
        sigmaBeep(440, 0.15, 0.3);
        setTimeout(function(){{ sigmaBeep(554, 0.25, 0.35); }}, 180);
    }} else if (level === 'warn') {{
        // Single low tone — warning / trap door
        sigmaBeep(220, 0.4, 0.3);
    }}
}}
// Called by Dash clientside callback
window.dash_clientside = window.dash_clientside || {{}};
window.dash_clientside.sigmalytic = {{
    fireAlert: function(score, prev_score, alerts_on) {{
        if (!alerts_on) return window.dash_clientside.no_update;
        if (score >= 80 && prev_score < 80) {{ sigmaAlert('A'); }}
        else if (score >= 55 && prev_score < 55) {{ sigmaAlert('B'); }}
        else if (score < 35 && prev_score >= 35) {{ sigmaAlert('warn'); }}
        return score;
    }}
}};
</script>
</body></html>"""

_init_live    = create_live_update("AAPL", 280.15, 750_000, 0).to_dict()
_init_candles = _scaled_candles(280.15, "5m")

ALL_TABS = [
    ("command",    "Command Center"),
    ("feed",       "Live Feed"),
    ("performance","Performance"),
    ("behavior",   "Behavioral Intelligence"),
    ("import",     "Import History"),
    ("setup",      "Setup"),
]

app.layout = html.Div([
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-candles",   data=_init_candles),
    dcc.Store(id="s-seq",       data=0),
    dcc.Store(id="s-live-mode", data=True),
    dcc.Store(id="s-symbol",    data="AAPL"),
    dcc.Store(id="s-tf",        data="5m"),
    dcc.Store(id="s-tab",       data="command"),
    dcc.Store(id="s-alert-score",    data=0),
    dcc.Store(id="s-alerts-on",      data=True),
    dcc.Store(id="s-current-plan-id",data=None),
    dcc.Store(id="s-plan-score",     data=0),
    dcc.Store(id="s-plan-regime",    data="neutral"),
    dcc.Store(id="tp-direction",     data="long"),
    html.Div(id="audio-trigger", style={"display":"none"}),
    dcc.Interval(id="i-synth",  interval=1_400, n_intervals=0),
    dcc.Interval(id="i-alpaca", interval=5_000, n_intervals=0),
    dcc.Interval(id="i-clock",  interval=1_000, n_intervals=0),

    html.Div([html.Div([
        html.Header([
            html.Div([
                LOGO,
                html.Div([
                    html.Div("SIGMALYTIC SYSTEM // DECISION LAYER",
                             style={"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".32em","color":TEAL_DIM}),
                    html.Div(id="sim-label", style={"display":"none"}),
                ], style={"textAlign":"center"}),
                html.Div(style={"width":"120px"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","width":"100%","marginBottom":"6px"}),
            html.P("Real-time decision intelligence — scores, interprets, and projects market behavior via multi-layer confluence.",
                   style={"fontSize":"12px","color":MUTED,"textAlign":"center","maxWidth":"640px","margin":"0 auto"}),
            html.P("Powered by Confluence Engine · Expansion Node Modeling · Forward Projection Layer · Behavioral Intelligence",
                   style={"fontSize":"11px","color":"#475569","textAlign":"center","letterSpacing":".06em","marginTop":"4px"}),
            html.Hr(style={"border":"none","height":"1px","background":BORDER,"width":"60%","margin":"12px auto 0"}),
            html.Div([
                html.H1("Decision Command Center",
                        style={"fontSize":"30px","fontWeight":"900","lineHeight":"1","letterSpacing":"-.02em","color":WHITE}),
                html.Span(id="b-connected"), html.Span(id="b-feed"), html.Span(id="b-tick"),
            ], style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
            html.Div([
                dcc.Input(id="ticker-input", value="AAPL", debounce=False,
                          style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}","borderRadius":"12px",
                                 "padding":"10px 14px","width":"120px","fontSize":"14px","fontWeight":"700"}),
                html.Button("Load Symbol", id="btn-load", n_clicks=0,
                            style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
                                   "borderRadius":"12px","padding":"10px 18px","fontSize":"13px","fontWeight":"800"}),
                html.Div(id="price-ctrl"),
                html.Div([
                    html.Button("1m",  id="tf-1m",  n_clicks=0, style=_tf_btn_style("1m",  "5m")),
                    html.Button("5m",  id="tf-5m",  n_clicks=0, style=_tf_btn_style("5m",  "5m")),
                    html.Button("15m", id="tf-15m", n_clicks=0, style=_tf_btn_style("15m", "5m")),
                    html.Button("1H",  id="tf-1H",  n_clicks=0, style=_tf_btn_style("1H",  "5m")),
                    html.Button("1D",  id="tf-1D",  n_clicks=0, style=_tf_btn_style("1D",  "5m")),
                    html.Button("1W",  id="tf-1W",  n_clicks=0, style=_tf_btn_style("1W",  "5m")),
                ], style={"display":"flex","gap":"2px","padding":"4px","background":NAVY_MID,
                           "border":f"1px solid {BORDER}","borderRadius":"12px"}),

            ], style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
        ], style={"display":"flex","flexDirection":"column","alignItems":"center","gap":"14px","paddingBottom":"4px"}),

        html.Nav([
            html.Button(label, id=f"tab-{key}", n_clicks=0,
                        style={"background":"transparent","color":TEXT,"border":"none","borderRadius":"10px",
                               "padding":"10px 20px","fontSize":"13px","fontWeight":"700","whiteSpace":"nowrap"})
            for key, label in ALL_TABS
        ], style={"display":"flex","gap":"4px","padding":"4px","borderRadius":"14px",
                   "background":NAVY_MID,"border":f"1px solid {BORDER}","justifyContent":"center","overflowX":"auto"}),

        html.Main(id="main-content"),

        # ── Trade plan + active trade — ALL inputs permanent, never recreated ──
        html.Div([
            # Trade plan card — header updates, inputs are static
            html.Div([
                html.Div(id="trade-plan-panel", style={"marginBottom":"16px"}),
                html.Div([
                    slabel("Direction"),
                    html.Div([
                        html.Button("Long",    id="dir-long",    n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"800",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"8px 0 0 8px",
                                   "border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM}),
                        html.Button("Short",   id="dir-short",   n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"700",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"0",
                                   "border":f"1px solid {BORDER}","borderLeft":"none","borderRight":"none",
                                   "background":"transparent","color":TEXT}),
                        html.Button("Neutral", id="dir-neutral", n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"700",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"0 8px 8px 0",
                                   "border":f"1px solid {BORDER}","background":"transparent","color":TEXT}),
                    ], style={"display":"flex","width":"100%"}),
                ], style={"marginBottom":"12px"}),
                html.Div([
                    html.Div([slabel("Entry Price"),
                              dcc.Input(id="tp-entry", value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                    html.Div([slabel("Stop"),
                              dcc.Input(id="tp-stop",  value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                ], style={"display":"flex","gap":"12px","marginBottom":"12px"}),
                html.Div([
                    html.Div([slabel("Target"),
                              dcc.Input(id="tp-target", value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                    html.Div([slabel("Size"),
                              dcc.Input(id="tp-size",   value="100",  debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                ], style={"display":"flex","gap":"12px","marginBottom":"12px"}),
                html.Div([
                    slabel("Setup Notes"),
                    dcc.Textarea(id="tp-notes", value="", placeholder="Why this setup?",
                        style={**_input_style(),"height":"60px","resize":"vertical","lineHeight":"1.5"}),
                ], style={"marginBottom":"16px"}),
                html.Div([
                    _btn("💾 Save Plan",   "btn-save-plan"),
                    _btn("🚀 Enter Trade", "btn-enter-trade",
                         color=WHITE, bg=WHITE, border=BORDER, extra={"color":NAVY}),
                ], style={"display":"flex","gap":"10px"}),
                html.Div(id="tp-status", style={"marginTop":"10px","fontSize":"12px","color":TEAL_DIM}),
            ], style={"flex":"1","minWidth":"0","background":NAVY_CARD,"border":f"1px solid {BORDER}",
                       "borderRadius":"20px","padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}),

            # Active trade panel
            html.Div(id="active-trade-panel", style={"flex":"1","minWidth":"0"}),
        ], id="trade-panels-row",
           style={"display":"none","gap":"16px","alignItems":"start"}),

    ], style={"maxWidth":"1440px","margin":"0 auto","display":"flex","flexDirection":"column","gap":"16px"})],
    style={"minHeight":"100vh","background":NAVY,"padding":"24px"}),
], style={"margin":"0","background":NAVY})

# ── Callbacks ──────────────────────────────────────────────────────────────────

@app.callback(
    Output("s-tf","data"), Output("s-candles","data",allow_duplicate=True),
    Output("s-seq","data",allow_duplicate=True),
    Output("tf-1m","style"), Output("tf-5m","style"), Output("tf-15m","style"),
    Output("tf-1H","style"), Output("tf-1D","style"), Output("tf-1W","style"),
    Input("tf-1m","n_clicks"), Input("tf-5m","n_clicks"), Input("tf-15m","n_clicks"),
    Input("tf-1H","n_clicks"), Input("tf-1D","n_clicks"), Input("tf-1W","n_clicks"),
    State("s-live","data"), prevent_initial_call=True,
)
def select_tf(_1m,_5m,_15m,_1H,_1D,_1W, live):
    ctx = callback_context
    if not ctx.triggered:
        return (no_update,)*9
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    new_tf = btn_id.replace("tf-","")
    price  = live["price"] if live else 280.15
    fresh  = _scaled_candles(price, new_tf)
    # Track event
    if live:
        _track("timeframe_changed", live.get("symbol",""), price=price, timeframe=new_tf,
               regime=_regime_from_live(live),
               decision_score=live.get("decision",{}).get("score"),
               decision_status=live.get("decision",{}).get("status"))
    s0=_tf_btn_style("1m",new_tf); s1=_tf_btn_style("5m",new_tf); s2=_tf_btn_style("15m",new_tf)
    s3=_tf_btn_style("1H",new_tf); s4=_tf_btn_style("1D",new_tf); s5=_tf_btn_style("1W",new_tf)
    return new_tf, fresh, 0, s0, s1, s2, s3, s4, s5

# Live-only mode — no toggle callback needed

@app.callback(
    Output("s-symbol","data"), Output("ticker-input","value"),
    Input("btn-load","n_clicks"), State("ticker-input","value"),
    State("s-live","data"), prevent_initial_call=True,
)
def load_symbol(_, ticker, live):
    clean = sanitize_symbol(ticker or "")
    if not clean: return no_update, no_update
    price = live["price"] if live else 280.15
    _track("symbol_loaded", clean, price=price,
           decision_score=live.get("decision",{}).get("score") if live else None)
    return clean, clean

@app.callback(
    Output("s-tab","data"),
    Input("tab-command","n_clicks"), Input("tab-feed","n_clicks"),
    Input("tab-performance","n_clicks"), Input("tab-behavior","n_clicks"),
    Input("tab-import","n_clicks"), Input("tab-setup","n_clicks"),
    prevent_initial_call=True,
)
def set_tab(*_):
    ctx = callback_context
    if not ctx.triggered: return no_update
    tab = ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")
    return tab

@app.callback(
    Output("s-live","data"),
    Output("s-seq","data",allow_duplicate=True),
    Output("s-candles","data",allow_duplicate=True),
    Input("i-synth","n_intervals"), Input("i-alpaca","n_intervals"),
    State("s-live","data"), State("s-seq","data"), State("s-candles","data"),
    State("s-live-mode","data"), State("s-symbol","data"), State("s-tf","data"),
    prevent_initial_call=True,
)
def tick(_,__,current,seq,candles,live_mode,symbol,tf):
    ctx = callback_context
    if not ctx.triggered: return no_update,no_update,no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    vol = TF_VOLATILITY.get(tf, 0.60)
    # Always attempt Alpaca first on any interval trigger.
    # If Alpaca fails, use synthetic movement to keep chart alive.
    prev = current["price"] if current else 280.15
    price = None; volume = None

    if trigger == "i-alpaca":
        try:
            r = req.get(f"{BACKEND_HTTP}/api/stock/{symbol}", timeout=4)
            r.raise_for_status()
            d = r.json()
            price  = float(d["price"])
            volume = int(d.get("volume", 0))
        except Exception:
            pass  # fall through to synthetic below

    if price is None:
        if trigger == "i-synth":
            tick_scale = {
                "1m": 0.05, "5m": 0.08, "15m": 0.12,
                "1H": 0.18, "1D": 0.30, "1W":  0.50,
            }.get(tf, 0.08)
            price  = round(max(1.0, prev + (random.random() - 0.48) * tick_scale), 2)
            volume = round(500_000 + random.random() * 5_000_000)
        else:
            return no_update, no_update, no_update
    new_seq  = (seq or 0)+1
    new_live = create_live_update(symbol,price,volume,new_seq,candles).to_dict()
    if candles:
        prior    = candles[-1]
        interval = TF_INTERVAL.get(tf, 300)
        now_utc  = datetime.now(timezone.utc)

        try:    last_ts = datetime.fromisoformat(prior["t"])
        except: last_ts = now_utc - timedelta(seconds=interval)

        # Only open a NEW candle if enough real time has passed for this TF.
        # Otherwise update the current candle in-place (high/low/close update,
        # timestamp stays fixed). This prevents weekly/daily candles from
        # printing dates far into the future.
        elapsed = (now_utc - last_ts).total_seconds()

        if elapsed >= interval:
            # Enough real time has passed — open a fresh candle.
            # New candle: open = prior close, high = low = open (price hasn't moved yet),
            # close = current price. No artificial offset on high/low at open.
            new_ts  = last_ts + timedelta(seconds=interval)
            o_price = prior["c"]          # open is prior close
            new_c   = {
                "o": o_price,
                "h": round(max(o_price, price), 2),   # true high so far
                "l": round(min(o_price, price), 2),   # true low so far
                "c": price,
                "t": new_ts.isoformat(),
            }
            new_candles = candles[-49:] + [new_c]
        else:
            # Still within the current candle period — update in-place.
            # Open is permanently locked to candle start.
            # High only moves up, low only moves down, close is latest price.
            updated_last = {
                "o": prior["o"],                         # LOCKED — never changes
                "h": round(max(prior["h"], price), 2),   # only moves up
                "l": round(min(prior["l"], price), 2),   # only moves down
                "c": price,                              # always latest
                "t": prior["t"],                         # timestamp locked to open
            }
            new_candles = candles[:-1] + [updated_last]
    else:
        new_candles = _init_candles
    return new_live, new_seq, new_candles

@app.callback(
    Output("price-ctrl","children"),
    Input("s-live-mode","data"), Input("s-live","data"),
)
def render_price_ctrl(live_mode, live):
    price=live["price"] if live else 280.15
    return html.Div([
        html.Span("LIVE PRICE",style={"fontSize":"10px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
        html.Strong(f"${price:.2f}",style={"fontSize":"17px","color":WHITE,"fontWeight":"900"}),
    ], style={"background":NAVY_MID,"border":f"1px solid {BORDER_T}","borderRadius":"12px",
               "padding":"8px 14px","width":"130px","minHeight":"50px","display":"flex","flexDirection":"column","justifyContent":"center"})

@app.callback(
    Output("b-connected","children"), Output("b-feed","children"), Output("b-tick","children"),
    Input("s-live","data"),
)
def update_badges(live):
    seq = live["sequence"] if live else 0
    return (badge("LIVE","teal"),
            badge("Alpaca IEX","blue"),
            badge(f"Tick #{seq}","yellow"))

@app.callback(
    Output("main-content",       "children"),
    Output("trade-panels-row",   "style"),
    Output("trade-plan-panel",   "children"),
    Output("active-trade-panel", "children"),
    Input("s-live","data"), Input("s-candles","data"), Input("s-tab","data"),
    Input("s-live-mode","data"), Input("i-clock","n_intervals"),
    State("s-symbol","data"), State("s-tf","data"),
)
def render_main(live,candles,tab,live_mode,_clock,symbol,tf):
    HIDDEN = {"display":"none"}
    SHOWN  = {"display":"flex","gap":"16px","alignItems":"start"}

    if not live:
        return (html.Div("Initializing…",style={"color":MUTED,"padding":"60px","textAlign":"center"}),
                HIDDEN, no_update, no_update)

    if tab == "command":
        open_trade  = _get(f"/api/behavior/open-trade/{USER_ID}")
        trade_plan  = _build_trade_plan_contents(live)
        active_pane = build_active_trade_panel(open_trade, live["price"]) if open_trade else html.Div()
        return (build_command_tab(live, candles or _init_candles, symbol, tf),
                SHOWN, trade_plan, active_pane)

    if tab=="feed":          main = build_feed_tab(live,live_mode)
    elif tab=="performance": main = build_performance_tab(live)
    elif tab=="behavior":    main = build_behavior_tab()
    elif tab=="import":      main = build_import_tab()
    elif tab=="setup":       main = build_setup_tab()
    else:                    main = html.Div("Unknown tab")
    return main, HIDDEN, no_update, no_update

# ── Trade plan / entry / exit callbacks ───────────────────────────────────────

@app.callback(
    Output("tp-status","children"),
    Output("s-current-plan-id","data"),
    Input("btn-save-plan","n_clicks"),
    State("tp-direction","data"), State("tp-entry","value"),
    State("tp-stop","value"), State("tp-target","value"),
    State("tp-size","value"), State("tp-notes","value"),
    State("s-live","data"), prevent_initial_call=True,
)
def save_plan(n,direction,entry,stop,target,size,notes,live):
    if not n: return no_update, no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-plan",{
            "user_id":USER_ID,"symbol":symbol,"direction":direction,
            "planned_entry":float(entry),"planned_stop":float(stop),
            "planned_target":float(target),"planned_size":float(size),
            "setup_reason":notes or "","signal_score_at_plan":score,"regime_at_plan":regime,
        })
        plan_id = resp.get("plan_id")
        _track("trade_planned",symbol,price=price,regime=regime,decision_score=score,
               metadata={"plan_id":plan_id,"direction":direction})
        return f"✅ Plan saved: {plan_id}", plan_id
    except Exception as e:
        return f"❌ Error: {e}", no_update

@app.callback(
    Output("tp-status","children",allow_duplicate=True),
    Input("btn-enter-trade","n_clicks"),
    State("tp-direction","data"), State("tp-entry","value"),
    State("tp-stop","value"), State("tp-target","value"),
    State("tp-size","value"),
    State("s-current-plan-id","data"),
    State("s-live","data"), prevent_initial_call=True,
)
def enter_trade(n,direction,entry,stop,target,size,plan_id,live):
    if not n: return no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-entry",{
            "user_id":USER_ID,"symbol":symbol,"direction":direction,
            "entry_price":float(entry),"stop_price":float(stop) if stop else None,
            "target_price":float(target) if target else None,"size":float(size),
            "plan_id":plan_id,"market_regime_entry":regime,"signal_score_entry":score,
        })
        trade_id = resp.get("trade_id")
        _track("trade_entered",symbol,price=float(entry),regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"direction":direction})
        return f"🚀 Trade entered: {trade_id}"
    except Exception as e:
        return f"❌ Error: {e}"

@app.callback(
    Output("exit-status","children"),
    Input("btn-exit-trade","n_clicks"),
    State("s-active-trade-id","data"),
    State("exit-flags","value"),
    State("exit-notes","value"),
    State("s-live","data"), prevent_initial_call=True,
)
def exit_trade(n,trade_id,flags,notes,live):
    if not n or not trade_id: return no_update
    try:
        price  = live["price"] if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        score  = live.get("decision",{}).get("score",0) if live else 0
        flags  = flags or []
        resp = _post("/api/behavior/trade-exit",{
            "trade_id":trade_id,"exit_price":price,
            "market_regime_exit":regime,"signal_score_exit":score,"notes":notes or "",
            "no_plan":            "no_plan"            in flags,
            "stop_moved_wider":   "stop_moved_wider"   in flags,
            "target_moved":       "target_moved"        in flags,
            "premature_exit":     "premature_exit"      in flags,
            "added_size_adverse": "added_size_adverse"  in flags,
            "timeframe_changed":  "timeframe_changed"   in flags,
        })
        scores = resp.get("scores",{})
        _track("trade_exited",live.get("symbol",""),price=price,regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"pnl":resp.get("pnl"),"flag":resp.get("behavior_flag")})
        return (f"🏁 Exited · P&L: ${resp.get('pnl',0):+.2f} ({resp.get('pnl_percent',0):+.2f}%) · "
                f"Score: {scores.get('composite',0):.0f} · Flag: {resp.get('behavior_flag','—')}")
    except Exception as e:
        return f"❌ Error: {e}"

# ── Direction toggle buttons ─────────────────────────────────────────────────
def _dir_styles(active):
    base = {"flex":"1","padding":"9px 0","fontSize":"13px","cursor":"pointer","fontFamily":"inherit"}
    styles = {
        "long":    {**base,"fontWeight":"800","borderRadius":"8px 0 0 8px",
                    "border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM},
        "short":   {**base,"fontWeight":"800","borderRadius":"0",
                    "border":f"1px solid rgba(239,68,68,.35)","borderLeft":"none","borderRight":"none",
                    "background":RED_GLOW,"color":RED_DIM},
        "neutral": {**base,"fontWeight":"800","borderRadius":"0 8px 8px 0",
                    "border":f"1px solid rgba(245,158,11,.35)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM},
    }
    idle = {
        "long":    {**base,"fontWeight":"700","borderRadius":"8px 0 0 8px",
                    "border":f"1px solid {BORDER}","background":"transparent","color":TEXT},
        "short":   {**base,"fontWeight":"700","borderRadius":"0",
                    "border":f"1px solid {BORDER}","borderLeft":"none","borderRight":"none",
                    "background":"transparent","color":TEXT},
        "neutral": {**base,"fontWeight":"700","borderRadius":"0 8px 8px 0",
                    "border":f"1px solid {BORDER}","background":"transparent","color":TEXT},
    }
    return (styles["long"]    if active=="long"    else idle["long"],
            styles["short"]   if active=="short"   else idle["short"],
            styles["neutral"] if active=="neutral" else idle["neutral"])

@app.callback(
    Output("tp-direction", "data"),
    Output("dir-long",    "style"),
    Output("dir-short",   "style"),
    Output("dir-neutral", "style"),
    Input("dir-long",    "n_clicks"),
    Input("dir-short",   "n_clicks"),
    Input("dir-neutral", "n_clicks"),
    prevent_initial_call=True,
)
def select_direction(_l, _s, _n):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update
    btn = ctx.triggered[0]["prop_id"].split(".")[0]
    direction = btn.replace("dir-", "")
    sl, ss, sn = _dir_styles(direction)
    return direction, sl, ss, sn


# ── CSV upload callback ──────────────────────────────────────────────────────
@app.callback(
    Output("csv-upload-status", "children"),
    Input("csv-upload", "contents"),
    State("csv-upload", "filename"),
    prevent_initial_call=True,
)
def handle_csv_upload(contents, filename):
    if not contents:
        return no_update
    import base64, io as _io
    try:
        # Decode base64 data URI
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        # POST to backend
        resp = req.post(
            f"{BACKEND_HTTP}/api/import/upload",
            files={"file": (filename, _io.BytesIO(decoded), "text/csv")},
            timeout=30,
        )
        if resp.ok:
            data = resp.json()
            a    = data.get("analysis", {})
            return html.Div([
                html.Span(f"✅ {data.get('broker_name','Unknown')} detected · ",
                          style={"color":TEAL_DIM,"fontWeight":"800"}),
                html.Span(f"{data.get('trades_closed',0)} trades imported · "
                          f"Win rate: {a.get('win_rate',0)}% · "
                          f"Total P&L: ${a.get('total_pnl',0):+,.2f}",
                          style={"color":TEXT}),
                html.Br(),
                html.Span("Switch to the Behavioral Intelligence tab to see your full profile.",
                          style={"color":MUTED,"fontSize":"11px"}),
            ])
        else:
            return f"❌ Upload failed: {resp.text[:200]}"
    except Exception as e:
        return f"❌ Error: {str(e)[:200]}"


# ── Audio alert clientside callback ──────────────────────────────────────────
app.clientside_callback(
    """
    function(score, prev_score, alerts_on) {
        if (window.dash_clientside && window.dash_clientside.sigmalytic) {
            return window.dash_clientside.sigmalytic.fireAlert(score, prev_score, alerts_on);
        }
        return score;
    }
    """,
    Output("s-alert-score", "data"),
    Input("s-live", "data"),
    State("s-alert-score", "data"),
    State("s-alerts-on", "data"),
)

@app.callback(
    Output("s-alerts-on", "data"),
    Output("btn-alerts-toggle", "children"),
    Output("btn-alerts-toggle", "style"),
    Input("btn-alerts-toggle", "n_clicks"),
    State("s-alerts-on", "data"),
    prevent_initial_call=True,
)
def toggle_alerts(n, currently_on):
    new_on = not currently_on
    label  = "🔔 ON"  if new_on else "🔕 OFF"
    style  = {"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
               "borderRadius":"20px","padding":"4px 12px","fontSize":"11px","fontWeight":"800","cursor":"pointer"}
    if not new_on:
        style.update({"background":"rgba(100,116,139,.12)","border":f"1px solid {BORDER}","color":MUTED})
    return new_on, label, style


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
