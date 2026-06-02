# Sigmalytic v2.2 — integer x-axis for proper candle rendering
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

BACKEND_HTTP      = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
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
    """Clean chart — integer index x-axis for proper candle rendering."""
    kl = get_key_levels(price)
    xs = list(range(len(candles)))
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=xs,
        open=[c["o"] for c in candles],
        high=[c["h"] for c in candles],
        low=[c["l"] for c in candles],
        close=[c["c"] for c in candles],
        name="Price",
        increasing=dict(line=dict(color=TEAL_DIM, width=2), fillcolor=TEAL_DIM),
        decreasing=dict(line=dict(color=RED_DIM,  width=2), fillcolor=RED_DIM),
        whiskerwidth=1.0,
    ))
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
            showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            rangeslider=dict(visible=False),
            showticklabels=False,
            title=None,
            color=WHITE,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            color=WHITE, side="right", tickformat=".2f",
            tickfont=dict(color=WHITE, size=12, family="DM Mono, monospace"),
        ),
        # Enough right margin for y-axis labels, bottom for x-axis labels
        margin=dict(l=0, r=60, t=8, b=24),
        height=480,
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

        # Upload widget + reset button
        html.Div([
            html.Div([
                html.Div("Upload Brokerage Statement",
                         style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                html.Button("🗑️ Clear All Trades", id="btn-reset-imports", n_clicks=0,
                    style={"background":"rgba(239,68,68,.1)","border":"1px solid rgba(239,68,68,.3)",
                           "borderRadius":"10px","color":"#f87171","cursor":"pointer",
                           "fontSize":"12px","fontWeight":"700","padding":"6px 14px",
                           "fontFamily":"DM Sans, sans-serif"}),
            ], style={"display":"flex","justifyContent":"space-between",
                       "alignItems":"center","marginBottom":"12px"}),
            html.Div(id="reset-status"),
        ]),
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

def _behavior_empty_state():
    return card([
        html.H2("🧠 Behavioral Intelligence", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
        note_box("Behavioral tracking activates after your first trade upload. Go to Import History to upload a brokerage statement.", "blue"),
        html.Div(style={"height":"12px"}),
        note_box("Once trades are imported, your decision scores, regime memory, and behavioral patterns will appear here.", "yellow"),
    ])


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

def build_login_page(error=""):
    return html.Div([
        html.Div([
            html.Div([
                html.Div("Σ", style={"fontSize":"48px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1"}),
                html.Div("SIGMALYTIC", style={"fontSize":"20px","fontWeight":"900","color":WHITE,"letterSpacing":".2em","marginTop":"4px"}),
                html.Div("QUANT CORPORATION", style={"fontSize":"10px","fontWeight":"700","color":MUTED,"letterSpacing":".3em","marginTop":"2px"}),
            ], style={"textAlign":"center","marginBottom":"40px"}),

            html.Div([
                # Login section
                html.Div(id="login-section", children=[
                    html.H2("Sign In", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="login-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"16px"}),
                    html.Div([
                        html.Label("Password", style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="login-password", type="password", placeholder="••••••••",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"24px"}),
                    html.Div(id="login-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
                    html.Button("Sign In", id="login-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer","marginBottom":"16px"}),
                    html.Div([
                        html.Div(style={"flex":"1","height":"1px","background":BORDER}),
                        html.Span("or", style={"color":MUTED,"fontSize":"12px","padding":"0 12px"}),
                        html.Div(style={"flex":"1","height":"1px","background":BORDER}),
                    ], style={"display":"flex","alignItems":"center","marginBottom":"16px"}),
                    html.Button("🎯 Try Demo — No Sign Up Required", id="demo-btn", n_clicks=0,
                        style={"width":"100%","background":"rgba(45,143,111,.15)","color":TEAL_DIM,
                               "border":f"1px solid {BORDER_T}","borderRadius":"8px","padding":"14px",
                               "fontSize":"13px","fontWeight":"700","cursor":"pointer","marginBottom":"24px"}),
                    html.Div([
                        html.Span("Don't have an account? ", style={"color":MUTED,"fontSize":"12px"}),
                        html.Button("Sign Up", id="goto-signup-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                                   "fontWeight":"700","cursor":"pointer","padding":"0"}),
                    ], style={"textAlign":"center"}),
                ]),

                # Signup section (hidden initially)
                html.Div(id="signup-section", style={"display":"none"}, children=[
                    html.H2("Create Account", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"16px"}),
                    html.Div([
                        html.Label("Password", style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-password", type="password", placeholder="Min 6 characters",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"24px"}),
                    html.Div(id="signup-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
                    html.Button("Create Account", id="signup-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer","marginBottom":"24px"}),
                    html.Div([
                        html.Span("Already have an account? ", style={"color":MUTED,"fontSize":"12px"}),
                        html.Button("Sign In", id="goto-login-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                                   "fontWeight":"700","cursor":"pointer","padding":"0"}),
                    ], style={"textAlign":"center"}),
                ]),

            ], style={"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px",
                      "padding":"40px","width":"400px","boxShadow":"0 20px 60px rgba(0,0,0,.4)"}),
        ], style={"display":"flex","flexDirection":"column","alignItems":"center",
                  "justifyContent":"center","minHeight":"100vh","padding":"20px"}),
    ], style={"background":NAVY})


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
            style={"flex":"1","margin":"0 -20px -8px -20px","overflow":"hidden"},
        ),

        # Footer — aligned with Distance box at bottom of price ladder
        html.Div([
            html.Span(f"{tf}  ·  {len(candles)} candles",
                      style={"fontSize":"13px","color":WHITE,"fontWeight":"700",
                             "fontFamily":"DM Mono, monospace"}),
            html.Span(f"Vol {live['volume']:,}",
                      style={"fontSize":"13px","color":WHITE,"fontWeight":"700",
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"8px 0 0 0","borderTop":f"1px solid {BORDER}","marginTop":"4px"}),

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

def build_stub_tab(title, description):
    """Placeholder for tabs under development."""
    return card([
        html.H2(title, style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        note_box(description, "blue"),
        html.Div(style={"height":"12px"}),
        note_box("This feature is under active development and will be available in an upcoming release.", "yellow"),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# REAL TAB FUNCTIONS — injected from source files
# ═══════════════════════════════════════════════════════════════════════════════

def build_radar_tab(session=None):
    """Radar Screen — multi-symbol signal scanner."""
    import requests as _rq
    session    = session or {}
    user_id    = session.get("user_id", "demo_user_001")
    features   = session.get("features", {})
    is_free    = session.get("plan", "free") == "free" or session.get("is_demo", False)
    radar_limit= features.get("radar_limit", 10) if is_free else 9999
    score_only = features.get("composite_score_only", False)
    delayed    = features.get("delayed_data", False)
    delay_min  = features.get("delay_minutes", 15)

    try:
        r = _rq.get(f"{BACKEND_HTTP}/api/radar/scores", timeout=6)
        data = r.json() if r.ok else {}
        # Backend returns {count: N, symbols: [...]}
        if isinstance(data, list):
            signals = data
        else:
            signals = data.get("symbols", data.get("signals", data.get("scores", [])))
    except Exception:
        signals = []

    # Free plan limits only enforced when real auth is active
    # Developer access - full signals always
    pass

    def _sig_row(s):
        score = s.get("composite_score", s.get("score", 0))
        sc = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 45 else RED_DIM)
        chg = s.get("change_pct", 0)
        return html.Div([
            html.Span(s.get("symbol",""), style={"flex":"1","fontWeight":"900","fontSize":"14px",
                       "color":WHITE,"fontFamily":"DM Mono, monospace"}),
            html.Span(f"${s.get('price',0):,.2f}", style={"flex":"1","fontSize":"13px","color":WHITE}),
            html.Span(f"{chg:+.2f}%", style={"flex":"1","fontSize":"12px","fontWeight":"700",
                       "color":TEAL_DIM if chg>=0 else RED_DIM}),
            html.Span(f"{score:.0f}%", style={"flex":"1","fontSize":"14px","fontWeight":"900","color":sc}),
            html.Span(s.get("status","—"), style={"flex":"1.5","fontSize":"11px","color":sc,"fontWeight":"700"}),
            html.Span(s.get("regime","—"), style={"flex":"1","fontSize":"11px","color":MUTED}),
            html.Span(s.get("bias","—"), style={"flex":"1","fontSize":"11px","color":BLUE_DIM}),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"12px 0","borderBottom":f"1px solid {BORDER}"})

    header_row = html.Div([
        html.Span("Symbol",  style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Price",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Chg%",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Score",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Status",  style={"flex":"1.5","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Regime",  style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Bias",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
    ], style={"display":"flex","gap":"12px","paddingBottom":"8px","borderBottom":f"1px solid {BORDER}","marginBottom":"4px"})

    free_banner = html.Div()  # No free plan banner until real auth is active

    return html.Div([
        card([
            html.Div([
                html.H2("📡 Radar Screen", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","margin":"0 0 4px"}),
                html.P("Live multi-symbol signal scanner — A-grade setups across your universe.",
                       style={"color":TEXT,"fontSize":"13px","margin":"0"}),
            ], style={"marginBottom":"12px"}),
            free_banner,
            header_row,
            html.Div([_sig_row(s) for s in signals] if signals else [
                html.Div("No signals available. Backend may be initializing or market is closed.",
                         style={"color":MUTED,"fontSize":"13px","padding":"24px 0","textAlign":"center"})
            ]),
        ], sx={"marginBottom":"16px"}),
    ])


def build_scoreboard_tab(session=None):
    """Scoreboard — decision score leaderboard."""
    import requests as _rq

    try:
        r = _rq.get(f"{BACKEND_HTTP}/api/scoreboard", timeout=6)
        board = r.json() if r.ok else {}
    except Exception:
        board = {}

    # Backend /api/scoreboard returns {signals, stats, generated_at}
    # Backend /api/scoreboard returns {count, symbols, stats, generated_at}
    raw = board.get("symbols", board.get("entries", board.get("signals", [])))
    entries   = raw if isinstance(raw, list) else []
    generated = board.get("generated_at", board.get("last_updated", ""))
    summary   = board.get("stats", board.get("summary", {}))

    def _entry_row(e, rank):
        score = e.get("composite_score", e.get("score", 0))
        sc = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 45 else RED_DIM)
        grade = e.get("grade","—")
        gc = TEAL_DIM if grade.startswith("A") else (BLUE_DIM if grade.startswith("B") else (YELLOW_DIM if grade=="C" else RED_DIM))
        return html.Div([
            html.Span(f"#{rank}", style={"flex":"0 0 32px","fontSize":"11px","color":MUTED,"fontWeight":"700"}),
            html.Span(e.get("symbol",""), style={"flex":"1","fontWeight":"900","fontSize":"14px",
                       "color":WHITE,"fontFamily":"DM Mono, monospace"}),
            html.Span(f"{score:.0f}", style={"flex":"1","fontSize":"20px","fontWeight":"900","color":sc}),
            html.Span(grade, style={"flex":"0 0 40px","fontSize":"16px","fontWeight":"900","color":gc}),
            html.Span(e.get("status","—"), style={"flex":"2","fontSize":"11px","color":sc,"fontWeight":"700"}),
            html.Span(e.get("regime","—"), style={"flex":"1","fontSize":"11px","color":MUTED}),
            html.Span(f"${e.get('price',0):,.2f}", style={"flex":"1","fontSize":"12px","color":TEXT}),
            html.Span(f"{e.get('change_pct',0):+.2f}%", style={"flex":"1","fontSize":"12px","fontWeight":"700",
                       "color":TEAL_DIM if e.get('change_pct',0)>=0 else RED_DIM}),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"12px 0","borderBottom":f"1px solid {BORDER}"})

    top3_colors = [YELLOW_DIM, TEXT, "#CD7F32"]  # gold, silver, bronze

    return html.Div([
        card([
            html.Div([
                html.H2("🏆 Scoreboard", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","margin":"0 0 4px"}),
                html.P("Live leaderboard — highest composite decision scores across the universe.",
                       style={"color":TEXT,"fontSize":"13px","margin":"0"}),
            ], style={"marginBottom":"16px"}),

            # Summary strip
            html.Div([
                html.Div([
                    html.Div("Total Symbols", style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                              "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"4px"}),
                    html.Div(str(summary.get("total_symbols","—")), style={"fontSize":"20px","fontWeight":"900","color":WHITE}),
                ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"12px","padding":"12px 16px"}),
                html.Div([
                    html.Div("Armed", style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                              "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"4px"}),
                    html.Div(str(summary.get("armed","—")), style={"fontSize":"20px","fontWeight":"900","color":TEAL_DIM}),
                ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"12px","padding":"12px 16px"}),
                html.Div([
                    html.Div("Avg Score", style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                              "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"4px"}),
                    html.Div(f"{summary.get('avg_score',0):.0f}%", style={"fontSize":"20px","fontWeight":"900","color":YELLOW_DIM}),
                ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"12px","padding":"12px 16px"}),
                html.Div([
                    html.Div("A-Grade", style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                              "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"4px"}),
                    html.Div(str(summary.get("a_grade","—")), style={"fontSize":"20px","fontWeight":"900","color":TEAL_DIM}),
                ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"12px","padding":"12px 16px"}),
            ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"20px"}),

            # Table header
            html.Div([
                html.Span("#",       style={"flex":"0 0 32px","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Symbol",  style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Score",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Grade",   style={"flex":"0 0 40px","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Status",  style={"flex":"2","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Regime",  style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Price",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Chg%",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            ], style={"display":"flex","gap":"12px","paddingBottom":"8px","borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),

            html.Div([_entry_row(e, i+1) for i, e in enumerate(entries)] if entries else [
                html.Div("Scoreboard data not yet available. Populates after first market snapshot.",
                         style={"color":MUTED,"fontSize":"13px","padding":"24px 0","textAlign":"center"})
            ]),

            html.Div(f"Last updated: {generated}", style={"fontSize":"10px","color":MUTED,"marginTop":"12px"}) if generated else html.Div(),
        ]),
    ])


def build_divergence_tab(session=None):
    """Divergence watchlist — symbols where price and score diverge."""
    import requests as _rq

    try:
        r = _rq.get(f"{BACKEND_HTTP}/api/radar/divergence", timeout=6)
        data = r.json() if r.ok else {}
    except Exception:
        data = {}

    raw_symbols = data.get("symbols", [])
    audit_label = data.get("last_audit", "Pending — runs nightly at 8:30 PM ET") or "Pending — runs nightly at 8:30 PM ET"

    # Build items list from symbols data
    items = []
    for s in (raw_symbols if isinstance(raw_symbols, list) else []):
        if isinstance(s, dict):
            chg   = s.get("change_pct", 0) or 0
            score = s.get("composite_score", s.get("score", 0)) or 0
            if chg > 0 and score < 50:
                direction = "BEARISH"
            elif chg < 0 and score > 50:
                direction = "BULLISH"
            else:
                direction = "NEUTRAL"
            items.append({
                "symbol":           s.get("symbol", s if isinstance(s, str) else ""),
                "price":            s.get("price", 0),
                "score":            score,
                "behavioral_score": s.get("bme_score", 0),
                "delta":            abs(score - 50),
                "direction":        direction,
                "regime":           s.get("regime", "—"),
                "change_pct":       chg,
            })
        elif isinstance(s, str):
            items.append({"symbol": s, "price": 0, "score": 0,
                          "behavioral_score": 0, "delta": 0,
                          "direction": "—", "regime": "—", "change_pct": 0})

    def _div_row(d):
        direction = d.get("direction","—")
        dir_color = TEAL_DIM if direction=="BULLISH" else (RED_DIM if direction=="BEARISH" else MUTED)
        return html.Div([
            html.Span(d.get("symbol",""), style={"flex":"1","fontWeight":"900","fontSize":"14px",
                       "color":WHITE,"fontFamily":"DM Mono, monospace"}),
            html.Span(f"${d.get('price',0):,.2f}", style={"flex":"1","fontSize":"13px","color":TEXT}),
            html.Span(f"{d.get('score',0):.0f}%", style={"flex":"1","fontSize":"13px","fontWeight":"700","color":YELLOW_DIM}),
            html.Span(f"{d.get('behavioral_score',0):.0f}%", style={"flex":"1","fontSize":"13px","color":BLUE_DIM}),
            html.Span(f"{d.get('delta',0):+.0f}", style={"flex":"1","fontSize":"13px","fontWeight":"700",
                       "color":TEAL_DIM if d.get('delta',0)>0 else RED_DIM}),
            html.Span(direction, style={"flex":"1","fontSize":"12px","fontWeight":"800","color":dir_color}),
            html.Span(d.get("regime","—"), style={"flex":"1","fontSize":"11px","color":MUTED}),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"12px 0","borderBottom":f"1px solid {BORDER}"})

    return html.Div([
        card([
            html.Div([
                html.H2("🔍 Divergence Watchlist", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","margin":"0 0 4px"}),
                html.P("Symbols where price action and behavioral score are moving in opposite directions.",
                       style={"color":TEXT,"fontSize":"13px","margin":"0"}),
            ], style={"marginBottom":"8px"}),
            html.Div(f"Last audit: {audit_label}",
                     style={"fontSize":"11px","color":MUTED,"marginBottom":"16px"}),

            html.Div([
                html.Span("Symbol",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Price",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Score",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Beh Score",style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Delta",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Direction",style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
                html.Span("Regime",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            ], style={"display":"flex","gap":"12px","paddingBottom":"8px","borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),

            html.Div([_div_row(d) for d in items] if items else [
                html.Div("No divergence signals yet. The watchlist populates nightly after the EOD audit.",
                         style={"color":MUTED,"fontSize":"13px","padding":"24px 0","textAlign":"center"})
            ]),
        ]),
    ])


def build_billing_tab(session=None, perms=None):
    """Delegate to billing_ui module."""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from billing_ui import build_billing_tab as _build
        return _build(session=session, perms=perms)
    except Exception as e:
        return card([
            html.H2("💳 Billing & Plans", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
            note_box(f"Billing error: {str(e)[:120]}", "yellow"),
        ])


def register_billing_callbacks_from_module(app):
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from billing_ui import register_billing_callbacks
        register_billing_callbacks_from_module(app)
    except Exception as e:
        print(f"Warning: billing callbacks: {e}")




def build_preferences_tab(user_id="", session=None):
    import requests as _preqs

    def _card(c):
        return html.Section(c, style={"background":NAVY_CARD,"border":f"1px solid {BORDER}",
            "borderRadius":"20px","padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)","marginBottom":"16px"})

    def _label(t):
        return html.Div(t, style={"color":MUTED,"fontSize":"10px","fontWeight":"800",
            "textTransform":"uppercase","letterSpacing":".28em","marginBottom":"10px"})

    def _stitle(t):
        return html.Div(t, style={"color":TEAL_DIM,"fontSize":"11px","fontWeight":"800",
            "textTransform":"uppercase","letterSpacing":".15em","marginBottom":"16px",
            "paddingBottom":"10px","borderBottom":f"1px solid {BORDER}"})

    def _on():
        return {"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","borderRadius":"8px",
                "color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                "fontWeight":"700","padding":"8px 16px","cursor":"pointer"}

    def _off():
        return {"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"8px",
                "color":TEXT,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                "fontWeight":"700","padding":"8px 16px","cursor":"pointer"}

    def _render_watchlist(wl):
        if not wl:
            return [html.Span("All symbols — no filter applied",
                              style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]
        return [html.Span(s, style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
                "borderRadius":"6px","color":WHITE,"fontSize":"12px","padding":"4px 10px",
                "marginRight":"6px","marginBottom":"6px","display":"inline-block"}) for s in wl]

    def _save(uid, email, payload):
        try:
            url = f"{BACKEND_HTTP}/api/preferences/{uid}"
            r = _preqs.patch(url, json=payload, timeout=8)
            if r.status_code == 404:
                r = _preqs.post(url, json={**payload, "user_id": uid, "email": email}, timeout=8)
            return ("✅ Saved", "teal") if r.ok else (f"❌ Error", "red")
        except Exception as e:
            return (f"❌ {str(e)[:60]}", "red")


    """
    Fetches saved preferences from backend and renders with correct state.
    All buttons save instantly on click.
    """
    # Load saved preferences
    prefs = {
        "delivery_mode":     "realtime",
        "min_score":         60,
        "alert_types":       {"wyckoff":True,"gann":True,"ab_score":True,"elliott":False,"fibonacci":False},
        "watchlist":         [],
        "market_hours_only": True,
        "hurst_profile":     "MEDIUM",
        "weis_threshold":    0.5,
    }

    if user_id:
        try:
            r = _preqs.get(f"{BACKEND_HTTP}/api/preferences/{user_id}", timeout=4)
            if r.ok:
                p = r.json()
                prefs["delivery_mode"]     = p.get("delivery_mode", prefs["delivery_mode"])
                prefs["min_score"]         = p.get("min_score", prefs["min_score"])
                prefs["alert_types"]       = p.get("alert_types", prefs["alert_types"])
                prefs["watchlist"]         = p.get("watchlist", prefs["watchlist"])
                prefs["market_hours_only"] = p.get("market_hours_only", prefs["market_hours_only"])
                prefs["hurst_profile"]     = p.get("hurst_profile", prefs["hurst_profile"])
                prefs["weis_threshold"]    = p.get("weis_threshold", prefs["weis_threshold"])
        except Exception:
            pass

    mode     = prefs["delivery_mode"]
    types    = prefs["alert_types"]
    hours    = prefs["market_hours_only"]
    score    = prefs["min_score"]
    watchlist= prefs["watchlist"]
    hurst    = prefs["hurst_profile"]
    weis     = prefs["weis_threshold"]

    if isinstance(types, list):
        all_keys = ["wyckoff","gann","ab_score","elliott","fibonacci"]
        types = {k: (k in types) for k in all_keys}

    return html.Div([
        # Hidden stores for current state (set on load, updated on each save)
        dcc.Store(id="prefs-uid",        data=user_id),
        dcc.Store(id="prefs-email",      data=(session or {}).get("email","")),
        dcc.Store(id="prefs-mode-cur",   data=mode),
        dcc.Store(id="prefs-types-cur",  data=types),
        dcc.Store(id="prefs-hours-cur",  data=hours),
        dcc.Store(id="prefs-score-cur",  data=score),
        dcc.Store(id="prefs-wl-cur",     data=watchlist),
        dcc.Store(id="prefs-hurst-cur",  data=hurst),
        dcc.Store(id="prefs-weis-cur",   data=weis),

        html.Div([
            html.H2("Alert Preferences", style={"color":WHITE,"fontSize":"22px","fontWeight":"800","marginBottom":"4px"}),
            html.P("Changes save instantly.", style={"color":TEXT,"fontSize":"13px"}),
        ], style={"marginBottom":"24px"}),

        # Status message
        html.Div(id="prefs-status", style={"textAlign":"center","fontSize":"13px",
                 "minHeight":"24px","marginBottom":"8px","color":TEAL_DIM}),

        # Delivery Mode
        _card([_stitle("📬 Delivery Mode"), _label("How often do you want alerts?"),
            html.Div([
                html.Button("Real-time",     id="pref-btn-realtime", n_clicks=0,
                            style=_on() if mode=="realtime" else _off()),
                html.Button("Hourly Digest", id="pref-btn-hourly",   n_clicks=0,
                            style=_on() if mode=="hourly"   else _off()),
                html.Button("Daily Summary", id="pref-btn-daily",    n_clicks=0,
                            style=_on() if mode=="daily"    else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Minimum Score
        _card([_stitle("🎯 Minimum Confluence Score"), _label("Only alert when score is at least:"),
            dcc.Slider(id="prefs-score-slider", min=0, max=100, step=5, value=score,
                marks={0:"0",25:"25",50:"50",75:"75",100:"100"},
                tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height":"8px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color":MUTED,"fontSize":"11px"}),
            html.Button("Save Score", id="prefs-score-save", n_clicks=0, style={
                "marginTop":"12px","background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                "fontSize":"12px","fontWeight":"700","padding":"8px 16px","cursor":"pointer"})]),

        # Alert Types
        _card([_stitle("⚡ Alert Types"), _label("Click to toggle — saves instantly:"),
            html.Div([
                html.Button("Structure Alerts", id="pref-btn-wyckoff",   n_clicks=0,
                            style=_on() if types.get("wyckoff")   else _off()),
                html.Button("Vector Alerts",    id="pref-btn-gann",      n_clicks=0,
                            style=_on() if types.get("gann")      else _off()),
                html.Button("Score Alerts",     id="pref-btn-ab_score",  n_clicks=0,
                            style=_on() if types.get("ab_score")  else _off()),
                html.Button("Cycle Alerts",     id="pref-btn-elliott",   n_clicks=0,
                            style=_on() if types.get("elliott")   else _off()),
                html.Button("Level Alerts",     id="pref-btn-fibonacci", n_clicks=0,
                            style=_on() if types.get("fibonacci") else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Watchlist
        _card([_stitle("📋 Watchlist"), _label("Only alert on these symbols (leave empty for all)"),
            html.Div([
                dcc.Input(id="prefs-sym-input", type="text", placeholder="e.g. AAPL", maxLength=5,
                    style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                           "borderRadius":"8px","color":WHITE,"fontFamily":"DM Mono, monospace",
                           "fontSize":"13px","padding":"10px 14px","width":"160px",
                           "marginRight":"10px","textTransform":"uppercase"}),
                html.Button("Add Symbol", id="prefs-sym-add", n_clicks=0,
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                           "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                           "fontSize":"12px","fontWeight":"700","padding":"10px 18px","cursor":"pointer"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.Div(id="prefs-wl-display", children=_render_watchlist(watchlist))]),

        # Market Hours
        _card([_stitle("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only", style={"color":WHITE,"fontSize":"13px","fontWeight":"600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color":MUTED,"fontSize":"11px","marginTop":"2px"}),
                ], style={"flex":"1"}),
                html.Button("ON" if hours else "OFF", id="pref-btn-hours", n_clicks=0,
                            style=_on() if hours else _off()),
            ], style={"display":"flex","alignItems":"center","gap":"16px"})]),

        # Hurst Cycle Profile
        _card([_stitle("🔄 Hurst Cycle Profile"),
            _label("Lookback horizon for cycle timing analysis"),
            html.Div([
                html.Button("Short (90d)",   id="pref-btn-hurst-short",  n_clicks=0,
                            style=_on() if hurst=="SHORT"  else _off()),
                html.Button("Medium (1yr)",  id="pref-btn-hurst-medium", n_clicks=0,
                            style=_on() if hurst=="MEDIUM" else _off()),
                html.Button("Long (3yr)",    id="pref-btn-hurst-long",   n_clicks=0,
                            style=_on() if hurst=="LONG"   else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Weis Wave Sensitivity
        _card([_stitle("〰️ Weis Wave Sensitivity"),
            _label("Reversal threshold — lower = more sensitive"),
            dcc.Slider(id="prefs-weis-slider", min=0.1, max=3.0, step=0.1, value=weis,
                marks={0.1:"0.1%", 0.5:"0.5%", 1.0:"1.0%", 2.0:"2.0%", 3.0:"3.0%"},
                tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height":"8px"}),
            html.Button("Save Sensitivity", id="prefs-weis-save", n_clicks=0, style={
                "marginTop":"12px","background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                "fontSize":"12px","fontWeight":"700","padding":"8px 16px","cursor":"pointer"})]),

    ], style={"maxWidth":"600px","margin":"0 auto","padding":"24px 16px"})

def register_preferences_callbacks(app):

    # ── Delivery mode — instant save ───────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children"),
        Output("prefs-status","style"),
        Output("pref-btn-realtime","style"),
        Output("pref-btn-hourly","style"),
        Output("pref-btn-daily","style"),
        Output("prefs-mode-cur","data"),
        Input("pref-btn-realtime","n_clicks"),
        Input("pref-btn-hourly","n_clicks"),
        Input("pref-btn-daily","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-mode-cur","data"),
        prevent_initial_call=True,
    )
    def save_mode(r, h, d, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*6
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        mode_map = {"pref-btn-realtime":"realtime","pref-btn-hourly":"hourly","pref-btn-daily":"daily"}
        mode = mode_map.get(t, cur)
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),*[_on() if x==mode else _off() for x in ["realtime","hourly","daily"]],mode
        msg, color = _save(uid, email, {"delivery_mode": mode})
        return msg,_msg_style(color),*[_on() if x==mode else _off() for x in ["realtime","hourly","daily"]],mode

    # ── Alert types — instant save ─────────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-wyckoff","style"),
        Output("pref-btn-gann","style"),
        Output("pref-btn-ab_score","style"),
        Output("pref-btn-elliott","style"),
        Output("pref-btn-fibonacci","style"),
        Output("prefs-types-cur","data"),
        Input("pref-btn-wyckoff","n_clicks"),
        Input("pref-btn-gann","n_clicks"),
        Input("pref-btn-ab_score","n_clicks"),
        Input("pref-btn-elliott","n_clicks"),
        Input("pref-btn-fibonacci","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-types-cur","data"),
        prevent_initial_call=True,
    )
    def save_types(nw,ng,na,ne,nf, uid, email, types):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*8
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        types = dict(types or {})
        km = {"pref-btn-wyckoff":"wyckoff","pref-btn-gann":"gann","pref-btn-ab_score":"ab_score",
              "pref-btn-elliott":"elliott","pref-btn-fibonacci":"fibonacci"}
        if t in km: types[km[t]] = not types.get(km[t], False)
        styles = [_on() if types.get(k) else _off() for k in ["wyckoff","gann","ab_score","elliott","fibonacci"]]
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),*styles,types
        msg, color = _save(uid, email, {"alert_types": types})
        return msg,_msg_style(color),*styles,types

    # ── Market hours — instant save ────────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-hours","children"),
        Output("pref-btn-hours","style"),
        Output("prefs-hours-cur","data"),
        Input("pref-btn-hours","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-hours-cur","data"),
        prevent_initial_call=True,
    )
    def save_hours(n, uid, email, cur):
        new = not cur
        label = "ON" if new else "OFF"
        style = _on() if new else _off()
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),label,style,new
        msg, color = _save(uid, email, {"market_hours_only": new})
        return msg,_msg_style(color),label,style,new

    # ── Min score — save on button click ───────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-score-cur","data"),
        Input("prefs-score-save","n_clicks"),
        State("prefs-score-slider","value"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def save_score(n, val, uid, email):
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),val
        msg, color = _save(uid, email, {"min_score": val})
        return msg,_msg_style(color),val

    # ── Hurst profile — instant save ───────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-hurst-short","style"),
        Output("pref-btn-hurst-medium","style"),
        Output("pref-btn-hurst-long","style"),
        Output("prefs-hurst-cur","data"),
        Input("pref-btn-hurst-short","n_clicks"),
        Input("pref-btn-hurst-medium","n_clicks"),
        Input("pref-btn-hurst-long","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-hurst-cur","data"),
        prevent_initial_call=True,
    )
    def save_hurst(s, m, l, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*6
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        hmap = {"pref-btn-hurst-short":"SHORT","pref-btn-hurst-medium":"MEDIUM","pref-btn-hurst-long":"LONG"}
        hurst = hmap.get(t, cur)
        styles = [_on() if h==hurst else _off() for h in ["SHORT","MEDIUM","LONG"]]
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),*styles,hurst
        msg, color = _save(uid, email, {"hurst_profile": hurst})
        return msg,_msg_style(color),*styles,hurst

    # ── Weis threshold — save on button click ──────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-weis-cur","data"),
        Input("prefs-weis-save","n_clicks"),
        State("prefs-weis-slider","value"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def save_weis(n, val, uid, email):
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),val
        msg, color = _save(uid, email, {"weis_threshold": val})
        return msg,_msg_style(color),val

    # ── Watchlist — add symbol and save ───────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-wl-cur","data"),
        Output("prefs-wl-display","children"),
        Output("prefs-sym-input","value"),
        Input("prefs-sym-add","n_clicks"),
        State("prefs-sym-input","value"),
        State("prefs-wl-cur","data"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def add_symbol(n, sym, wl, uid, email):
        if not sym: return no_update,no_update,wl,_render_watchlist(wl),""
        s = sym.strip().upper()
        wl = list(wl or [])
        if s and s not in wl: wl.append(s)
        if not uid: return "⚠️ Not logged in",_msg_style("yellow"),wl,_render_watchlist(wl),""
        msg, color = _save(uid, email, {"watchlist": wl})
        return msg,_msg_style(color),wl,_render_watchlist(wl),""

# ── Admin helpers ──────────────────────────────────────────────────────────────
def _admin_tile(label, value, color=None, sub=None):
    color = color or WHITE
    return html.Div([
        html.Div(label, style={"fontSize":"10px","color":TEXT,"fontWeight":"700",
                               "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Div(value, style={"fontSize":"22px","fontWeight":"900","color":color,"lineHeight":"1"}),
        html.Div(sub,   style={"fontSize":"10px","color":MUTED,"marginTop":"4px"}) if sub else html.Div(),
    ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px"})


def _admin_card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
         "borderRadius": "16px", "padding": "20px",
         "boxShadow": "0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Div(children, style=s)


def is_admin(session: dict) -> bool:
    return (session or {}).get("email","") == ADMIN_EMAIL

def build_admin_tab(session: dict, backend_url: str) -> html.Div:
    """
    Build the full admin monitoring page.
    Returns a 403 message if not admin.
    """
    if not is_admin(session):
        return html.Div([
            html.Div("🔒", style={"fontSize":"48px","marginBottom":"16px"}),
            html.Div("Admin Access Only", style={"fontSize":"18px","fontWeight":"800","color":WHITE}),
            html.Div("This page is only accessible to the system administrator.",
                     style={"fontSize":"13px","color":TEXT,"marginTop":"8px"}),
        ], style={"textAlign":"center","padding":"80px 20px"})

    # ── Fetch report from backend ─────────────────────────────────────────
    try:
        token = session.get("access_token","")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = _req.get(f"{backend_url}/api/admin/report", headers=headers, timeout=15)
        data = r.json() if r.ok else {}
    except Exception as e:
        data = {}

    if not data:
        return _card([
            html.Div("⚠️ Could not load admin report.", style={"color":YELLOW_DIM,"fontSize":"14px"}),
            html.Div("Backend may be initializing. Refresh in 30 seconds.",
                     style={"color":TEXT,"fontSize":"12px","marginTop":"8px"}),
        ])

    live          = data.get("live_stats", {})
    accuracy      = data.get("accuracy_stats", {})
    snap_health   = data.get("snapshot_health", {})
    top_scores    = data.get("top_scores", [])
    top_movers    = data.get("top_movers", [])
    anomalies     = data.get("anomalies", [])
    narrative     = data.get("narrative","—")
    daily_grades  = data.get("daily_grades", [])
    regimes       = data.get("regime_distribution", {})
    generated_at  = data.get("generated_at","")

    # Format timestamp
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(generated_at.replace("Z","+00:00"))
        gen_label = dt.strftime("%b %d, %Y  %I:%M %p UTC")
    except:
        gen_label = generated_at

    # ── Header ────────────────────────────────────────────────────────────
    header = _card([
        html.Div([
            html.Div([
                html.Div([
                    html.Span("🔒 ", style={"fontSize":"18px"}),
                    html.Span("ADMIN PERFORMANCE MONITOR",
                              style={"fontSize":"16px","fontWeight":"900","color":GOLD,
                                     "letterSpacing":".08em"}),
                ], style={"display":"flex","alignItems":"center","gap":"8px","marginBottom":"4px"}),
                html.Div("Private · Internal Use Only · Sigmalytic Quant Corporation",
                         style={"fontSize":"11px","color":MUTED,"letterSpacing":".06em"}),
            ]),
            html.Div([
                html.Span(snap_health.get("status","—"), style={
                    "fontSize":"10px","fontWeight":"800",
                    "color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                    "border": f"1px solid {BORDER_T}","borderRadius":"999px",
                    "padding":"4px 12px","background":TEAL_GLOW,
                }),
                html.Div(f"Generated: {gen_label}",
                         style={"fontSize":"10px","color":MUTED,"marginTop":"4px","textAlign":"right"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start"}),
    ], sx={"borderColor": "rgba(245,200,66,.3)", "marginBottom":"16px"})

    # ── Accuracy stats block (mirrors your PDF scoreboard) ───────────────
    hit  = accuracy.get("hit_rate", 0)
    conf = accuracy.get("conf_rate", 0)
    neut = accuracy.get("neutral_rate", 0)
    miss = accuracy.get("miss_rate", 0)
    perf_num = accuracy.get("a_grade",0)
    perf_den = accuracy.get("total",0)

    accuracy_block = _card([
        html.Div("CLOSED-LOOP PERFORMANCE AUDIT",
                 style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                        "letterSpacing":".2em","textTransform":"uppercase","marginBottom":"16px"}),
        html.Div([
            _tile("CONF",  f"{conf:.0f}%", TEAL_DIM,  "A-grade rate"),
            _tile("HIT",   f"{hit:.0f}%",  TEAL_DIM,  "A + B rate"),
            _tile("NEUTRAL",f"{neut:.0f}%",YELLOW_DIM,"C rate"),
            _tile("MISS",  f"{miss:.0f}%", RED_DIM,   "F rate"),
            _tile("PERF",  f"{perf_num}/{perf_den}" if perf_den else "—",
                  GOLD,   "A grades / total"),
            _tile("SYMBOLS",str(live.get("total_symbols",0)), BLUE_DIM, "in universe"),
            _tile("ARMED",  str(live.get("armed",0)),   TEAL_DIM, "live now"),
            _tile("TRIGGERED",str(live.get("triggered",0)),BLUE_DIM,"live now"),
        ], style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"10px"}),
    ], sx={"marginBottom":"16px","borderColor":"rgba(245,200,66,.2)"})

    # ── Snapshot writer health ────────────────────────────────────────────
    snap_block = _card([
        html.Div([
            html.Div("📸 SNAPSHOT WRITER", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"4px"}),
            html.Div([
                html.Span("Status: ", style={"color":MUTED,"fontSize":"11px"}),
                html.Span(snap_health.get("status","—"),
                          style={"color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                                 "fontWeight":"700","fontSize":"11px"}),
                html.Span("  ·  Last write: ", style={"color":MUTED,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(snap_health.get("last_write","—")[:19] if snap_health.get("last_write") else "—",
                          style={"color":TEXT,"fontSize":"11px"}),
                html.Span("  ·  Writes in last 10 min: ", style={"color":MUTED,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(str(snap_health.get("recent_count",0)),
                          style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"11px"}),
            ]),
        ]),
    ], sx={"marginBottom":"16px","padding":"14px 20px"})

    # ── Narrative block ───────────────────────────────────────────────────
    narrative_block = _card([
        html.Div("REGIME NARRATIVE", style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                  "letterSpacing":".2em","marginBottom":"12px"}),
        html.Div(narrative, style={"fontSize":"14px","color":WHITE,"lineHeight":"1.7",
                                   "fontStyle":"italic"}),

        html.Div(style={"height":"16px"}),

        # Regime distribution pills
        html.Div("REGIME DISTRIBUTION", style={"fontSize":"10px","fontWeight":"700","color":MUTED,
                  "letterSpacing":".16em","marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Span(regime, style={"fontSize":"11px","fontWeight":"700","color":WHITE,
                                         "marginRight":"6px"}),
                html.Span(f"{count}", style={"fontSize":"11px","color":TEAL_DIM,"fontWeight":"900"}),
            ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                       "borderRadius":"999px","padding":"4px 12px","display":"inline-flex",
                       "alignItems":"center","marginRight":"6px","marginBottom":"4px"})
            for regime, count in sorted(regimes.items(), key=lambda x: x[1], reverse=True)
        ], style={"display":"flex","flexWrap":"wrap"}),
    ], sx={"marginBottom":"16px"})

    # ── Anomaly flags ─────────────────────────────────────────────────────
    anomaly_rows = []
    for a in anomalies:
        sev_color = _severity_color(a.get("severity","INFO"))
        anomaly_rows.append(html.Div([
            html.Span(a.get("severity",""), style={
                "fontSize":"9px","fontWeight":"900","color":sev_color,
                "border":f"1px solid {sev_color}","borderRadius":"4px",
                "padding":"2px 6px","marginRight":"10px","minWidth":"40px",
                "textAlign":"center","display":"inline-block",
            }),
            html.Span(a.get("symbol",""), style={
                "fontSize":"11px","fontWeight":"800","color":WHITE,
                "fontFamily":"monospace","marginRight":"10px","minWidth":"60px",
                "display":"inline-block",
            }),
            html.Span(a.get("message",""), style={"fontSize":"12px","color":TEXT}),
        ], style={"padding":"8px 0","borderBottom":f"1px solid {BORDER}",
                  "display":"flex","alignItems":"center"}))

    anomaly_block = _card([
        html.Div([
            html.Div("🚨 ANOMALY FLAGS", style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
            html.Div(f"{len(anomalies)} issues detected",
                     style={"fontSize":"11px","color": RED_DIM if anomalies else TEAL_DIM}),
        ], style={"display":"flex","justifyContent":"space-between","marginBottom":"12px"}),
        html.Div(anomaly_rows if anomaly_rows else [
            html.Div("✅ No anomalies detected — system running clean.",
                     style={"color":TEAL_DIM,"fontSize":"13px","padding":"12px 0"})
        ]),
    ], sx={"marginBottom":"16px"})

    # ── Top 10 scores table ───────────────────────────────────────────────
    def _sym_row(s):
        score = s.get("composite_score", 0)
        sc    = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 50 else RED_DIM)
        chg   = s.get("change_pct", 0)
        return html.Div([
            html.Span(s.get("symbol",""), style={
                "flex":"1","fontWeight":"800","fontSize":"13px","color":WHITE,
                "fontFamily":"monospace",
            }),
            html.Span(f"${s.get('price',0):,.2f}", style={
                "flex":"1","fontSize":"12px","color":TEXT,
            }),
            html.Span(f"{chg:+.2f}%", style={
                "flex":"1","fontSize":"12px","fontWeight":"700",
                "color": TEAL_DIM if chg >= 0 else RED_DIM,
            }),
            html.Div([
                html.Span(f"{score:.0f}", style={"fontSize":"13px","fontWeight":"900","color":sc}),
                _score_bar(score, width="80px"),
            ], style={"flex":"1"}),
            html.Span(f"C:{s.get('confluence',0):.0f} E:{s.get('expansion_node',0):.0f} "
                      f"RS:{s.get('relative_strength',0):.0f} VP:{s.get('volume_pressure',0):.0f} "
                      f"B:{s.get('behavioral',0):.0f}",
                      style={"flex":"2","fontSize":"10px","color":sc,"fontFamily":"monospace"}),
            html.Span(s.get("status",""), style={
                "flex":"1","fontSize":"10px","fontWeight":"700","color":sc,
            }),
            html.Span(s.get("regime",""), style={
                "flex":"1","fontSize":"10px","color":MUTED,
            }),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"10px 0","borderBottom":f"1px solid {BORDER}"})

    score_table = _card([
        html.Div("🏆 TOP 10 — COMPOSITE SCORE", style={"fontSize":"12px","fontWeight":"800",
                  "color":WHITE,"marginBottom":"12px"}),
        # Header
        html.Div([
            html.Span("Symbol",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Price",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Chg%",     style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Score",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Dimensions (C E RS VP B)", style={"flex":"2","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Status",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Regime",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        ], style={"display":"flex","gap":"12px","paddingBottom":"8px",
                  "borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),
        html.Div([_sym_row(s) for s in top_scores]),
    ], sx={"marginBottom":"16px"})

    # ── Historical daily grade grid ────────────────────────────────────────
    # Get all unique symbols across all dates
    all_syms_set = set()
    for day in daily_grades:
        all_syms_set.update(day.get("symbols",{}).keys())
    all_syms = sorted(all_syms_set)

    if daily_grades and all_syms:
        # Table header row — dates
        date_headers = [
            html.Th("Symbol", style={"padding":"6px 10px","textAlign":"left",
                                      "fontSize":"9px","color":MUTED,"fontWeight":"700",
                                      "textTransform":"uppercase","letterSpacing":".1em",
                                      "background":NAVY_MID,"position":"sticky","left":0}),
        ] + [
            html.Th(day["date"][5:],  # MM-DD
                    style={"padding":"6px 10px","textAlign":"center","minWidth":"56px",
                           "fontSize":"9px","color":MUTED,"fontWeight":"700",
                           "textTransform":"uppercase","letterSpacing":".06em",
                           "background":NAVY_MID})
            for day in daily_grades
        ]

        # Symbol rows
        table_rows = []
        for sym in all_syms:
            cells = [
                html.Td(sym, style={"padding":"6px 10px","fontWeight":"800","fontSize":"12px",
                                     "color":WHITE,"fontFamily":"monospace",
                                     "background":NAVY_MID,"position":"sticky","left":0,
                                     "borderRight":f"1px solid {BORDER}"}),
            ]
            for day in daily_grades:
                sym_data = day.get("symbols",{}).get(sym)
                if sym_data:
                    grade = sym_data.get("grade","—")
                    gc    = _grade_color(grade)
                    cells.append(html.Td(
                        html.Div([
                            html.Div(grade or "—", style={"fontSize":"12px","fontWeight":"900",
                                                           "color":gc,"lineHeight":"1"}),
                            html.Div(f"{sym_data.get('score',0):.0f}",
                                     style={"fontSize":"9px","color":MUTED,"marginTop":"2px"}),
                        ], style={"textAlign":"center"}),
                        style={"padding":"5px 8px","background":f"{gc}12",
                               "borderLeft":f"1px solid rgba(255,255,255,.04)"},
                    ))
                else:
                    cells.append(html.Td("—", style={"padding":"5px 8px","textAlign":"center",
                                                       "color":MUTED,"fontSize":"11px"}))
            table_rows.append(html.Tr(cells, style={"borderBottom":f"1px solid {BORDER}"}))

        grade_grid = _card([
            html.Div([
                html.Div("📋 CUMULATIVE SCOREBOARD — DAILY GRADE GRID",
                         style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
                html.Div("Grade / Score · A=Full target · B=Partial · C=Neutral · F=Miss",
                         style={"fontSize":"10px","color":MUTED,"marginTop":"4px"}),
            ], style={"marginBottom":"16px"}),
            html.Div([
                html.Table([
                    html.Thead(html.Tr(date_headers,
                               style={"borderBottom":f"1px solid {BORDER}"})),
                    html.Tbody(table_rows),
                ], style={"width":"100%","borderCollapse":"collapse",
                          "fontSize":"12px","color":WHITE}),
            ], style={"overflowX":"auto","maxHeight":"480px","overflowY":"auto",
                      "border":f"1px solid {BORDER}","borderRadius":"10px"}),

            html.Div([
                html.Span("* Starred dates = Pinning Report validation days",
                          style={"fontSize":"10px","color":MUTED,"fontStyle":"italic"}),
            ], style={"marginTop":"12px"}),
        ], sx={"marginBottom":"16px"})
    else:
        grade_grid = _card([
            html.Div("📋 CUMULATIVE SCOREBOARD", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"8px"}),
            html.Div("No daily close snapshots yet. The grade grid will populate automatically "
                     "after 4:15 PM ET on the first trading day with the snapshot writer active.",
                     style={"fontSize":"13px","color":TEXT,"lineHeight":"1.7"}),
        ], sx={"marginBottom":"16px"})

    # ── Assemble full page ────────────────────────────────────────────────
    return html.Div([
        header,
        accuracy_block,
        snap_block,
        narrative_block,

        # Two-column row: anomalies + top scores
        html.Div([
            html.Div(anomaly_block, style={"flex":"1","minWidth":"0"}),
        ], style={"marginBottom":"0"}),

        score_table,
        grade_grid,

        # Footer
        html.Div("SIGMALYTIC QUANT CORPORATION  ·  PROPRIETARY & CONFIDENTIAL  ·  INTERNAL USE ONLY",
                 style={"textAlign":"center","fontSize":"9px","color":MUTED,
                        "letterSpacing":".2em","paddingTop":"16px","paddingBottom":"8px"}),
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

# Allow Stripe scripts and iframes via CSP
@server.after_request
def add_csp_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://cdn.jsdelivr.net; "
        "frame-src 'self' https://js.stripe.com https://hooks.stripe.com; "
        "connect-src 'self' https://api.stripe.com; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:;"
    )
    return response

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
    ("command",     "Command Center"),
    ("feed",        "Live Feed"),
    ("performance", "Performance"),
    ("behavior",    "Behavioral Intelligence"),
    ("import",      "Import History"),
    ("radar",       "Radar Screen"),
    ("scoreboard",  "Scoreboard"),
    ("divergence",  "🔍 Divergence"),
    ("billing",     "Billing"),
    ("preferences", "Preferences"),
    ("admin",       "Admin"),
    ("setup",       "Setup"),
]

app.layout = html.Div([
    dcc.Location(id="url", refresh=True),
    html.Div(id="auth-overlay", children=build_login_page(),
             style={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":"#0a1628","overflowY":"auto"}),
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-session",    data=None, storage_type="session"),
    dcc.Store(id="s-page",       data="login"), 
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
            # ── Compact single-row header ──────────────────────────────────
            html.Div([
                LOGO,
                html.Div([
                    html.H1("Decision Command Center",
                            style={"fontSize":"22px","fontWeight":"900","color":WHITE,
                                   "letterSpacing":"-.02em","margin":"0"}),
                    html.Div([
                        html.Span(id="b-connected"),
                        html.Span(id="b-feed"),
                        html.Span(id="b-tick"),
                    ], style={"display":"flex","gap":"6px","marginTop":"4px"}),
                ], style={"textAlign":"center"}),
                html.Div([
                    html.Div(id="sim-label", style={"display":"none"}),
                    html.Button("⏻ Log Out", id="btn-logout", n_clicks=0,
                        style={"background":"rgba(239,68,68,.1)","border":"1px solid rgba(239,68,68,.3)",
                               "borderRadius":"10px","color":"#f87171","cursor":"pointer",
                               "fontSize":"11px","fontWeight":"700","padding":"6px 12px",
                               "fontFamily":"DM Sans, sans-serif"}),
                ], style={"display":"flex","alignItems":"center","gap":"8px"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                       "width":"100%","marginBottom":"8px"}),

            # ── Controls row ───────────────────────────────────────────────
            html.Div([
                dcc.Input(id="ticker-input", value="AAPL", debounce=False,
                          style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}",
                                 "borderRadius":"12px","padding":"10px 14px","width":"110px",
                                 "fontSize":"14px","fontWeight":"700"}),
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
            ], style={"display":"flex","flexWrap":"wrap","alignItems":"center",
                       "justifyContent":"center","gap":"10px"}),
        ], style={"display":"flex","flexDirection":"column","alignItems":"center",
                   "gap":"8px","paddingBottom":"0"}),

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
    Input("tab-command","n_clicks"),      Input("tab-feed","n_clicks"),
    Input("tab-performance","n_clicks"),  Input("tab-behavior","n_clicks"),
    Input("tab-import","n_clicks"),       Input("tab-radar","n_clicks"),
    Input("tab-scoreboard","n_clicks"),   Input("tab-divergence","n_clicks"),
    Input("tab-billing","n_clicks"),      Input("tab-preferences","n_clicks"),
    Input("tab-admin","n_clicks"),        Input("tab-setup","n_clicks"),
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
    State("s-session","data"),
)
def render_main(live,candles,tab,live_mode,_clock,symbol,tf,session=None):
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
    elif tab=="radar":       main = build_radar_tab(session=session)
    elif tab=="scoreboard":  main = build_scoreboard_tab(session=None)
    elif tab=="divergence":  main = build_divergence_tab(session=None)
    elif tab=="billing":
        try:
            main = build_billing_tab(session=None, perms=None)
        except Exception as e:
            main = card([
                html.H2("💳 Billing", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box(f"Billing module loading. Please refresh in a moment.", "blue"),
            ])
    elif tab=="preferences":
        try:
            main = build_preferences_tab(user_id="", session=None)
        except Exception as e:
            main = card([
                html.H2("⚙️ Preferences", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Preferences loading. Please refresh in a moment.", "blue"),
            ])
    elif tab=="admin":       main = build_admin_tab(session={}, backend_url=BACKEND_HTTP)
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


@app.callback(Output("auth-overlay","style"),
              Input("s-session","data"))
def route_page(session):
    overlay_base = {"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":NAVY,"overflowY":"auto"}
    hidden = {"display":"none"}
    if session and session.get("user_id"):
        return hidden
    return overlay_base

@app.callback(Output("login-section","style"), Output("signup-section","style"),
              Input("goto-signup-btn","n_clicks"), Input("goto-login-btn","n_clicks"),
              prevent_initial_call=True)
def toggle_auth_section(to_signup, to_login):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "goto-signup-btn":
        return {"display":"none"}, {"display":"block"}
    return {"display":"block"}, {"display":"none"}

@app.callback(Output("s-session","data"),Output("s-page","data"),
              Input("login-btn","n_clicks"),Input("demo-btn","n_clicks"),
              Input("signup-btn","n_clicks"),
              State("login-email","value"),State("login-password","value"),
              State("signup-email","value"),State("signup-password","value"),
              prevent_initial_call=True)
def handle_auth(login_clicks, demo_clicks, signup_clicks,
                login_email, login_password, signup_email, signup_password):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger == "demo-btn":
        return {
            "user_id": "demo_user_001",
            "email": "demo@sigmalytic.com",
            "is_demo": True,
            "plan": "elite",
            "plan_name": "Elite Trader",
            "features": {
                "radar_limit": 9999,
                "delayed_data": False,
                "delay_minutes": 0,
                "alerts": True,
                "sms_limit": -1,
                "live_data": True,
                "intelligence": True,
                "composite_score_only": False,
            }
        }, "app"

    if trigger == "login-btn":
        if not login_email or not login_password: return no_update, no_update
        import requests as _req
        try:
            r = _req.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},
                json={"email":login_email,"password":login_password}, timeout=10,
            )
            if r.ok:
                data = r.json()
                user = data.get("user",{})
                return {"user_id":user.get("id",""),"email":user.get("email",""),
                        "access_token":data.get("access_token",""),"is_demo":False}, "app"
        except Exception:
            pass
        return no_update, no_update

    if trigger == "signup-btn":
        if not signup_email or not signup_password: return no_update, no_update
        import requests as _req
        try:
            r = _req.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},
                json={"email":signup_email,"password":signup_password}, timeout=10,
            )
            if r.ok:
                data = r.json()
                user = data.get("user",{})
                return {"user_id":user.get("id",""),"email":user.get("email",""),
                        "access_token":data.get("access_token",""),"is_demo":False}, "app"
        except Exception:
            pass
        return no_update, no_update

    return no_update, no_update

# ── Main app callbacks ────────────────────────────────────────────────────────



@app.callback(
    Output("s-session", "data", allow_duplicate=True),
    Output("url", "href"),
    Input("btn-logout", "n_clicks"),
    prevent_initial_call=True,
)
def logout(n):
    if n:
        return None, "/"
    return no_update, no_update


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
