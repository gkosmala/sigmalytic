"""
Sigmalytic Frontend — Dash + Plotly (Institutional Grade)
----------------------------------------------------------
Connects to the FastAPI backend via:
  - REST  GET /api/candles/{symbol}  on load / symbol change
  - WS    /ws/{symbol}               for real-time price ticks

Run alongside the backend:
  python frontend/app.py
"""

from __future__ import annotations
import json
import os

import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.engine import (
    sanitize_symbol, create_live_update, generate_initial_candles,
    get_key_levels, build_confluence_nodes, run_decision,
)

# ── Config ──────────────────────────────────────────────────────────────────
BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS   = os.getenv("BACKEND_WS_URL", "ws://localhost:8000")
TIMEFRAMES   = ["1m", "5m", "15m", "1H", "1D", "1W"]

# ── Design tokens (matches original dark theme exactly) ────────────────────
T = {
    "bg":        "#020617",
    "surface":   "#0f172a",
    "card":      "rgba(15,23,42,.72)",
    "border":    "rgba(255,255,255,.10)",
    "green":     "#6ee7b7",
    "green_dim": "#34d399",
    "red":       "#fca5a5",
    "red_dim":   "#f87171",
    "yellow":    "#fde68a",
    "blue":      "#93c5fd",
    "muted":     "#94a3b8",
    "text":      "#cbd5e1",
    "white":     "#f8fafc",
}

CARD = {
    "background":  T["card"],
    "border":      f"1px solid {T['border']}",
    "borderRadius":"22px",
    "padding":     "20px",
    "boxShadow":   "0 24px 60px rgba(0,0,0,.28)",
}

# ── Reusable component helpers ──────────────────────────────────────────────

def badge(text: str, color: str = "green") -> html.Span:
    palette = {
        "green":  (T["green"],  "rgba(16,185,129,.18)", "rgba(52,211,153,.50)"),
        "blue":   (T["blue"],   "rgba(59,130,246,.12)", "rgba(96,165,250,.38)"),
        "yellow": (T["yellow"], "rgba(234,179,8,.12)",  "rgba(250,204,21,.38)"),
        "red":    (T["red"],    "rgba(239,68,68,.12)",  "rgba(248,113,113,.38)"),
    }
    fg, bg, border = palette.get(color, palette["green"])
    return html.Span(text, style={
        "borderRadius": "999px", "border": f"1px solid {border}",
        "padding": "5px 12px", "fontSize": "12px", "fontWeight": "900",
        "color": fg, "background": bg, "whiteSpace": "nowrap",
    })


def metric_box(label: str, value: str, accent: str = T["white"]) -> html.Div:
    return html.Div([
        html.Span(label, style={"display": "block", "color": T["muted"],
                                "fontSize": "11px", "fontWeight": "700",
                                "textTransform": "uppercase", "letterSpacing": ".12em",
                                "marginBottom": "6px"}),
        html.Strong(value, style={"display": "block", "color": accent,
                                  "fontSize": "16px", "fontWeight": "950"}),
    ], style={
        "background": "rgba(0,0,0,.30)", "border": f"1px solid {T['border']}",
        "borderRadius": "14px", "padding": "14px", "minHeight": "66px",
    })


def progress_bar(label: str, value: int) -> html.Div:
    color = T["green_dim"] if value >= 70 else (T["yellow"] if value >= 45 else T["red_dim"])
    return html.Div([
        html.Div([
            html.Span(label, style={"color": T["muted"], "fontSize": "12px"}),
            html.Span(f"{value}%", style={"color": color, "fontWeight": "900"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "marginBottom": "6px"}),
        html.Div(html.Div(style={
            "width": f"{value}%", "height": "100%", "borderRadius": "999px",
            "background": f"linear-gradient(90deg, #ef4444, #facc15, #34d399)",
        }), style={"height": "10px", "background": "#1e293b",
                   "borderRadius": "999px", "overflow": "hidden"}),
    ], style={"marginTop": "12px"})


def section_card(children, extra: dict | None = None) -> html.Section:
    style = {**CARD, **(extra or {})}
    return html.Section(children, style=style)


def note_box(text: str, color: str = "") -> html.Div:
    styles: dict = {
        "border": f"1px solid {T['border']}", "background": T["bg"],
        "borderRadius": "14px", "padding": "12px",
        "color": T["text"], "fontSize": "12px",
    }
    if color == "yellow":
        styles.update({"borderColor": "rgba(250,204,21,.22)",
                       "background": "rgba(234,179,8,.10)", "color": "#fef3c7"})
    elif color == "blue":
        styles.update({"borderColor": "rgba(96,165,250,.25)",
                       "background": "rgba(59,130,246,.10)", "color": "#dbeafe"})
    return html.Div(text, style=styles)


# ── Plotly candlestick chart ────────────────────────────────────────────────

def build_plotly_chart(candles: list, price: float, nodes: list) -> go.Figure:
    kl = get_key_levels(price)

    opens  = [c["o"] for c in candles]
    highs  = [c["h"] for c in candles]
    lows   = [c["l"] for c in candles]
    closes = [c["c"] for c in candles]
    times  = [c.get("t", str(i)) for i, c in enumerate(candles)]

    fig = go.Figure()

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=times, open=opens, high=highs, low=lows, close=closes,
        name="Price",
        increasing_line_color=T["green_dim"],
        increasing_fillcolor=T["green_dim"],
        decreasing_line_color=T["red_dim"],
        decreasing_fillcolor=T["red_dim"],
        line_width=1,
    ))

    # Key level horizontal lines
    level_config = [
        (kl.breakout,   f"{kl.breakout:.2f} Breakout",   T["green"],  "dash"),
        (kl.prior_high, f"{kl.prior_high:.2f} Liquidity", T["green"],  "dot"),
        (kl.expansion,  f"{kl.expansion:.2f} Expansion",  T["green"],  "dashdot"),
        (kl.confirm,    f"{kl.confirm:.2f} Anchor",       T["yellow"], "solid"),
        (kl.trigger,    f"{kl.trigger:.2f} Trigger",      T["yellow"], "dash"),
        (kl.trap,       f"{kl.trap:.2f} Trap",            T["red"],    "dot"),
        (kl.fail,       f"{kl.fail:.2f} Fail Gate",       T["red"],    "dash"),
    ]

    for level, label, color, dash in level_config:
        fig.add_hline(
            y=level, line_color=color, line_dash=dash,
            line_width=1, opacity=0.7,
            annotation_text=label,
            annotation_position="right",
            annotation_font_color=color,
            annotation_font_size=10,
        )

    # Current price line
    fig.add_hline(
        y=price, line_color=T["blue"], line_dash="solid",
        line_width=2, opacity=0.9,
        annotation_text=f"  Live ${price:.2f}",
        annotation_position="right",
        annotation_font_color=T["blue"],
        annotation_font_size=11,
    )

    # Confluence node annotations
    for node in nodes:
        color = T["green"] if node["tone"] == "up" else T["red"]
        fig.add_hline(
            y=node["level"], line_color=color, line_dash="dot",
            line_width=1, opacity=0.5,
        )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#020617",
        font=dict(family="Inter, sans-serif", color=T["text"]),
        xaxis=dict(
            gridcolor="rgba(255,255,255,.05)",
            showgrid=True, zeroline=False,
            rangeslider=dict(visible=False),
            color=T["muted"],
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,.05)",
            showgrid=True, zeroline=False,
            color=T["muted"], side="right",
        ),
        margin=dict(l=10, r=120, t=20, b=30),
        height=400,
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=T["surface"], font_color=T["white"],
            bordercolor=T["border"],
        ),
        dragmode="pan",
    )
    return fig


# ── Panel builders ──────────────────────────────────────────────────────────

def build_command_tab(live: dict, candles: list, symbol: str, timeframe: str, live_mode: bool) -> html.Div:
    price    = live["price"]
    decision = live["decision"]
    nodes    = live["confluence"]
    kl       = get_key_levels(price)

    from datetime import datetime, timezone
    ts       = live["timestamp"]
    try:
        dt      = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        live_age = dt.strftime("%I:%M:%S %p")
    except Exception:
        live_age = ts

    fig = build_plotly_chart(candles, price, nodes)

    score       = decision["score"]
    score_color = T["green"] if score >= 70 else (T["yellow"] if score >= 45 else T["red"])
    size        = "FULL" if score >= 80 else ("HALF" if score >= 65 else ("PROBE" if score >= 45 else "NONE"))

    top_node = nodes[0] if nodes else {"public_label": "—", "score": 0}

    # ── Options matrix calcs ──────────────────────────────────────────────
    seq              = live["sequence"]
    vol_score        = max(18, min(96, round(abs(price - kl.trigger) * 18 + (seq % 9) * 4)))
    call_pressure    = max(12, min(94, round(score + (8 if price > kl.confirm else -10) + (seq % 5))))
    put_pressure     = max(8,  min(92, 100 - call_pressure))
    gamma_pressure   = max(20, min(95, round(55 + (price - kl.confirm) * 7)))
    flow_bias        = "Call Accumulation" if price >= kl.confirm else "Neutral / Pinning"

    return html.Div([

        # ── Chart + Decision Hero ──────────────────────────────────────────
        html.Div([

            # Chart card
            section_card([
                html.Div([
                    html.Div([
                        html.H2(f"📊 {symbol}  ·  Smart Chart + Live Levels",
                                style={"margin": "0 0 4px", "fontSize": "18px",
                                       "fontWeight": "900", "color": T["white"]}),
                        html.P(f"Updated {live_age}  ·  Vol {live['volume']:,}  ·  {timeframe}",
                               style={"fontSize": "12px", "color": T["muted"]}),
                    ]),
                    html.Div([
                        badge(f"Last  ${price:.2f}", "blue"),
                        badge("MODEL: CONFLUENCE ENGINE v1.0", "green"),
                    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "alignItems": "flex-start", "flexWrap": "wrap",
                          "marginBottom": "12px"}),
                dcc.Graph(
                    figure=fig,
                    config={"displayModeBar": True, "scrollZoom": True,
                            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                            "displaylogo": False},
                    style={"borderRadius": "14px", "overflow": "hidden"},
                ),
            ]),

            # Decision Hero
            section_card([
                html.Div("Decision Engine", style={
                    "color": T["muted"], "fontSize": "11px", "fontWeight": "900",
                    "textTransform": "uppercase", "letterSpacing": ".28em",
                }),
                html.Div(decision["status"], style={
                    "color": T["green"], "fontSize": "44px",
                    "fontWeight": "950", "lineHeight": "1", "marginTop": "8px",
                }),
                html.Div(f"Live State: {decision['behavior']}", style={
                    "textAlign": "center", "borderRadius": "999px",
                    "background": "rgba(0,0,0,.30)",
                    "border": f"1px solid {T['border']}",
                    "padding": "10px 14px", "fontSize": "12px",
                    "fontWeight": "900", "textTransform": "uppercase",
                    "letterSpacing": ".16em", "marginTop": "8px",
                }),
                html.Div([
                    html.Div("Execution Directive", style={
                        "color": T["muted"], "fontSize": "11px", "fontWeight": "900",
                        "textTransform": "uppercase", "letterSpacing": ".22em",
                    }),
                    html.H3(decision["next_action"], style={
                        "color": T["white"], "fontSize": "15px",
                        "fontWeight": "800", "margin": "8px 0 4px",
                    }),
                    html.P(
                        f"Price ${price:.2f}  ·  Top node: "
                        f"{top_node.get('public_label','—')} {top_node.get('score',0)}%",
                        style={"fontSize": "12px", "color": T["text"]},
                    ),
                ], style={
                    "borderRadius": "16px", "background": "rgba(0,0,0,.30)",
                    "border": f"1px solid {T['border']}", "padding": "16px",
                    "marginTop": "8px",
                }),
                progress_bar("Signal Strength", score),
                html.Div([
                    metric_box("Bias",       decision["bias"],       T["green"]),
                    metric_box("Grade",      decision["grade"],      score_color),
                    metric_box("Confidence", decision["confidence"], score_color),
                    metric_box("Mode",       decision["mode"],       T["blue"]),
                ], style={"display": "grid",
                          "gridTemplateColumns": "repeat(2, 1fr)",
                          "gap": "10px", "marginTop": "12px"}),
            ]),

        ], style={"display": "grid", "gridTemplateColumns": "1.4fr 1fr",
                  "gap": "16px", "marginBottom": "16px",
                  "alignItems": "start"}),

        # ── 4-column cards ─────────────────────────────────────────────────
        html.Div([

            # Trade Card
            section_card([
                html.H2("🎯 Trade Card", style={"margin": "0 0 12px",
                        "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
                metric_box("Bias",           decision["bias"]),
                html.Div(style={"height": "8px"}),
                metric_box("Setup",          decision["status"]),
                html.Div(style={"height": "8px"}),
                metric_box("Suggested Size", size, score_color),
                html.Div(style={"height": "8px"}),
                note_box("Entry logic: tactical only above trigger; "
                         "A-grade continuation requires live-volume expansion.", "yellow"),
                html.P(f"Reference: ${price:.2f}",
                       style={"fontSize": "11px", "color": T["muted"], "marginTop": "8px"}),
            ]),

            # Probability Ladder
            section_card([
                html.H2("🪜 Probability Ladder", style={"margin": "0 0 12px",
                        "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
                *[html.Div([
                    html.Div([
                        html.Span(row["label"], style={"fontSize": "12px"}),
                        html.Span(f"{row['prob']}%", style={
                            "fontWeight": "900",
                            "color": T["green"] if row["tone"] == "up"
                                     else (T["red"] if row["tone"] == "down" else T["yellow"]),
                        }),
                    ], style={"display": "flex", "justifyContent": "space-between"}),
                    html.Div(html.Div(style={
                        "width": f"{row['prob']}%", "height": "100%",
                        "borderRadius": "999px",
                        "background": "linear-gradient(90deg,#ef4444,#facc15,#34d399)",
                    }), style={"height": "8px", "background": "#1e293b",
                               "borderRadius": "999px", "overflow": "hidden",
                               "marginTop": "6px"}),
                    html.P(f"Level ${row['level']:.2f}",
                           style={"fontSize": "10px", "color": T["muted"], "marginTop": "4px"}),
                ], style={"border": f"1px solid {T['border']}", "background": T["bg"],
                          "borderRadius": "12px", "padding": "10px", "marginBottom": "8px"})
                  for row in [
                    {"label": "Upside Expansion", "level": nodes[0]["level"] if nodes else kl.breakout,
                     "prob": nodes[0]["score"] if nodes else 63, "tone": "up"},
                    {"label": "Liquidity Retest", "level": nodes[1]["level"] if len(nodes) > 1 else kl.prior_high,
                     "prob": nodes[1]["score"] if len(nodes) > 1 else 60, "tone": "up"},
                    {"label": "Hold / Balance",   "level": kl.confirm, "prob": score,       "tone": "neutral"},
                    {"label": "Failure Gate",     "level": kl.fail,    "prob": 100 - score, "tone": "down"},
                ]],
            ]),

            # Time Engine
            section_card(id="time-engine-card", children=[
                html.H2("⏱️ Time Engine", style={"margin": "0 0 12px",
                        "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
                html.Div(id="time-engine-body"),
            ]),

            # Alerts
            section_card([
                html.H2("🔔 Alerts", style={"margin": "0 0 12px",
                        "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
                *_build_alert(decision, price, kl),
                html.P("Visual triggers active. Audio alerts available post-configuration.",
                       style={"fontSize": "11px", "color": T["muted"], "marginTop": "8px"}),
            ]),

        ], style={"display": "grid",
                  "gridTemplateColumns": "repeat(4, minmax(0,1fr))",
                  "gap": "16px", "marginBottom": "16px"}),

        # ── Options Matrix ─────────────────────────────────────────────────
        section_card([
            html.Div([
                html.Div([
                    html.H2("🧱 Dynamic Options Matrix + Flow Map",
                            style={"margin": "0 0 4px", "fontSize": "17px",
                                   "fontWeight": "900", "color": T["white"]}),
                    html.P("Synthetic options intelligence from price, volume, "
                           "volatility proxy, and decision score.",
                           style={"fontSize": "12px", "color": T["muted"]}),
                ]),
                badge(flow_bias, "blue"),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "flex-start", "flexWrap": "wrap",
                      "marginBottom": "16px"}),
            html.Div([
                _zone_card("Call Wall",   "285",  f"{call_pressure}% call-side",  "up"),
                _zone_card("Put Wall",    "275",  f"{put_pressure}% put-side",    "down"),
                _zone_card("Gamma Pivot", "280",  f"{gamma_pressure}% sensitivity","neutral"),
                _zone_card("Vol Trigger", "LIVE", f"{vol_score}% expansion",      "up"),
            ], style={"display": "grid",
                      "gridTemplateColumns": "repeat(4, minmax(0,1fr))",
                      "gap": "16px"}),
            html.Div(style={"height": "12px"}),
            note_box("Synthetic options layer — connect Tradier or CBOE for live flow data.", "blue"),
        ]),

        # ── Summary strip ──────────────────────────────────────────────────
        section_card([
            html.Div([
                metric_box("Symbol",       symbol,           T["blue"]),
                metric_box("Live Price",   f"${price:.2f}",  T["green"]),
                metric_box("Engine Score", f"{score}%",      score_color),
                metric_box("Regime",       decision["mode"], T["yellow"]),
            ], style={"display": "grid",
                      "gridTemplateColumns": "repeat(4, minmax(0,1fr))",
                      "gap": "16px"}),
        ]),

    ])


def _build_alert(decision: dict, price: float, kl) -> list:
    score       = decision["score"]
    alert_state = ("Expansion Alert" if score >= 80
                   else "Trap-Door Alert" if price < kl.trap
                   else "Monitoring")
    is_active   = alert_state != "Monitoring"
    style = {
        "borderRadius": "16px", "padding": "16px",
        "textAlign": "center", "fontWeight": "950", "fontSize": "14px",
        **({"border": "1px solid rgba(52,211,153,.40)",
            "background": "rgba(16,185,129,.10)", "color": "#d1fae5"}
           if is_active
           else {"border": "1px solid rgba(250,204,21,.30)",
                 "background": "rgba(234,179,8,.10)", "color": "#fef3c7"}),
    }
    return [html.Div(alert_state, style=style)]


def _zone_card(name: str, level: str, desc: str, tone: str) -> html.Div:
    color = T["green"] if tone == "up" else (T["red"] if tone == "down" else T["yellow"])
    return html.Div([
        html.P(name,  style={"fontSize": "11px", "color": T["muted"], "margin": "0 0 4px"}),
        html.Div(level, style={"fontSize": "26px", "fontWeight": "950",
                               "color": color, "margin": "6px 0"}),
        html.P(desc,  style={"fontSize": "11px", "color": T["muted"], "margin": "0"}),
    ], style={"border": f"1px solid {T['border']}", "background": T["bg"],
              "borderRadius": "14px", "padding": "14px"})


def build_feed_tab(live: dict, connected: bool, live_mode: bool) -> html.Div:
    return section_card([
        html.Div([
            html.Div([
                html.H2("🔌 Live Feed Monitor", style={"margin": "0 0 4px",
                        "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
                html.P(f"Backend: {BACKEND_HTTP}",
                       style={"fontSize": "12px", "color": T["muted"]}),
            ]),
            badge("Connected" if connected else "Disconnected",
                  "green" if connected else "yellow"),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "marginBottom": "16px"}),
        html.Div([
            metric_box("Feed Mode", "Live Alpaca" if live_mode else "Synthetic"),
            metric_box("Symbol",   live["symbol"]),
            metric_box("Price",    f"${live['price']:.2f}", T["green"]),
            metric_box("Volume",   f"{live['volume']:,}"),
        ], style={"display": "grid",
                  "gridTemplateColumns": "repeat(4, minmax(0,1fr))",
                  "gap": "16px", "marginBottom": "16px"}),
        html.Pre(json.dumps(live, indent=2), style={
            "margin": "0", "maxHeight": "420px", "overflow": "auto",
            "borderRadius": "14px", "border": f"1px solid {T['border']}",
            "background": "rgba(0,0,0,.40)", "padding": "16px",
            "color": "#a7f3d0", "fontSize": "12px",
        }),
    ])


def build_performance_tab(live: dict) -> html.Div:
    price    = live["price"]
    decision = live["decision"]
    score    = decision["score"]
    score_color = T["green"] if score >= 70 else (T["yellow"] if score >= 45 else T["red"])
    return section_card([
        html.H2("📈 Performance Logger", style={"margin": "0 0 16px",
                "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
        html.Div([
            metric_box("Current Price", f"${price:.2f}",   T["green"]),
            metric_box("Setup",         decision["status"], score_color),
            metric_box("Score",         f"{score}%",        score_color),
            metric_box("Bias",          decision["bias"],   T["blue"]),
        ], style={"display": "grid",
                  "gridTemplateColumns": "repeat(4, minmax(0,1fr))",
                  "gap": "16px"}),
        html.Div(style={"height": "12px"}),
        note_box("Trade logging reconnects automatically once live feed stabilizes."),
    ])


def build_setup_tab() -> html.Div:
    return section_card([
        html.H2("🧩 Setup & Deployment", style={"margin": "0 0 16px",
                "fontSize": "17px", "fontWeight": "900", "color": T["white"]}),
        html.Pre(
            f"Frontend : Dash (Python)  →  Render / Railway\n"
            f"Backend  : FastAPI        →  Render\n"
            f"Data     : Alpaca IEX (free) / Alpaca SIP (paid)\n"
            f"WebSocket: {BACKEND_WS}/ws/{{symbol}}\n"
            f"REST     : {BACKEND_HTTP}/api/stock/{{symbol}}\n\n"
            f"Environment variables:\n"
            f"  ALPACA_API_KEY     — your Alpaca key ID\n"
            f"  ALPACA_API_SECRET  — your Alpaca secret\n"
            f"  BACKEND_URL        — HTTP base URL of backend\n"
            f"  BACKEND_WS_URL     — WS base URL of backend",
            style={"margin": "0", "borderRadius": "14px",
                   "border": f"1px solid {T['border']}",
                   "background": "rgba(0,0,0,.40)", "padding": "16px",
                   "color": "#a7f3d0", "fontSize": "12px"},
        ),
    ])


# ── Dash app ────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="Sigmalytic — Decision Intelligence Platform",
    update_title=None,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server   # expose for gunicorn

_init_live = create_live_update("AAPL", 280.15, 750_000, 0).to_dict()
_init_candles = [{"o": c.o, "h": c.h, "l": c.l, "c": c.c, "t": str(i)}
                 for i, c in enumerate(generate_initial_candles(280.15))]

app.layout = html.Div([

    # ── Stores ──────────────────────────────────────────────────────────
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-candles",   data=_init_candles),
    dcc.Store(id="s-seq",       data=0),
    dcc.Store(id="s-live-mode", data=False),
    dcc.Store(id="s-symbol",    data="AAPL"),
    dcc.Store(id="s-tf",        data="5m"),
    dcc.Store(id="s-tab",       data="command"),
    dcc.Store(id="s-connected", data=False),
    dcc.Store(id="s-price-text",data="280.15"),

    # ── Intervals ────────────────────────────────────────────────────────
    dcc.Interval(id="i-synth",  interval=1_400, n_intervals=0),
    dcc.Interval(id="i-alpaca", interval=5_000, n_intervals=0),
    dcc.Interval(id="i-clock",  interval=1_000, n_intervals=0),

    # ── App shell ────────────────────────────────────────────────────────
    html.Div([
        html.Div([

            # HEADER
            html.Header([
                html.Div([
                    html.Div("Sigmalytic System // Decision Layer", style={
                        "fontSize": "11px", "fontWeight": "900",
                        "textTransform": "uppercase", "letterSpacing": ".32em",
                        "color": T["green"],
                    }),
                    html.Div(id="sim-label", style={
                        "marginTop": "6px", "fontSize": "10px", "fontWeight": "800",
                        "textTransform": "uppercase", "letterSpacing": ".2em",
                        "color": T["blue"],
                    }),
                    html.Div(
                        "Real-time decision intelligence — scores, interprets, and "
                        "projects market behavior via multi-layer confluence.",
                        style={"margin": "10px auto 0", "fontSize": "12px",
                               "color": T["muted"], "maxWidth": "720px"},
                    ),
                    html.Div(
                        "Powered by Confluence Engine · Expansion Node Modeling · "
                        "Forward Projection Layer",
                        style={"marginTop": "6px", "fontSize": "11px",
                               "color": "#64748b", "letterSpacing": ".08em"},
                    ),
                    html.Hr(style={"height": "1px", "background": "rgba(255,255,255,.08)",
                                   "border": "none", "margin": "16px auto 0", "width": "60%"}),
                ], style={"textAlign": "center", "width": "100%"}),

                html.Div([
                    html.H1("Decision Command Center", style={
                        "margin": "0", "fontSize": "32px",
                        "fontWeight": "950", "lineHeight": "1",
                    }),
                    html.Span(id="b-connected"),
                    html.Span(id="b-feed"),
                    html.Span(id="b-tick"),
                ], style={"display": "flex", "flexWrap": "wrap",
                          "alignItems": "center", "justifyContent": "center", "gap": "10px"}),

                html.Div([
                    dcc.Input(id="ticker-input", value="AAPL", debounce=False,
                              style={"background": T["surface"], "color": "white",
                                     "border": f"1px solid {T['border']}",
                                     "borderRadius": "12px", "padding": "10px 14px",
                                     "width": "120px", "outline": "none",
                                     "fontSize": "14px", "fontWeight": "700"}),
                    html.Button("Load Symbol", id="btn-load", n_clicks=0, style={
                        "background": "rgba(16,185,129,.12)",
                        "border": "1px solid rgba(52,211,153,.40)",
                        "color": "#a7f3d0", "borderRadius": "12px",
                        "padding": "10px 16px", "fontSize": "13px",
                        "fontWeight": "900", "cursor": "pointer",
                    }),
                    html.Div(id="price-ctrl"),
                    html.Div([
                        html.Button(tf, id={"type": "tf", "index": tf}, n_clicks=0, style={
                            "background": "transparent", "color": T["text"],
                            "border": "none", "cursor": "pointer",
                            "borderRadius": "10px", "padding": "8px 12px",
                            "fontSize": "12px", "fontWeight": "900",
                        }) for tf in TIMEFRAMES
                    ], style={"display": "flex", "gap": "4px", "padding": "4px",
                              "background": T["surface"],
                              "border": f"1px solid {T['border']}",
                              "borderRadius": "12px"}),
                    html.Button(id="btn-live", n_clicks=0, style={
                        "background": "white", "color": T["bg"],
                        "border": "none", "borderRadius": "12px",
                        "padding": "10px 16px", "fontSize": "13px",
                        "fontWeight": "900", "cursor": "pointer",
                    }),
                ], style={"display": "flex", "flexWrap": "wrap",
                          "alignItems": "center", "justifyContent": "center", "gap": "10px"}),
            ], style={"display": "flex", "flexDirection": "column",
                      "alignItems": "center", "gap": "14px"}),

            # TABS
            html.Nav([
                html.Button(label, id=f"tab-{key}", n_clicks=0, style={
                    "background": "transparent", "color": T["text"],
                    "border": "none", "cursor": "pointer",
                    "borderRadius": "10px", "padding": "10px 16px",
                    "fontSize": "13px", "fontWeight": "900", "whiteSpace": "nowrap",
                }) for key, label in [
                    ("command", "Command Center"), ("feed", "Live Feed"),
                    ("performance", "Performance"), ("setup", "Setup"),
                ]
            ], style={"display": "flex", "gap": "8px", "padding": "4px",
                      "borderRadius": "12px", "background": T["surface"],
                      "border": f"1px solid {T['border']}",
                      "justifyContent": "center", "overflowX": "auto"}),

            # MAIN
            html.Main(id="main-content", style={"marginTop": "4px"}),

        ], style={
            "maxWidth": "1400px", "margin": "0 auto",
            "display": "flex", "flexDirection": "column", "gap": "16px",
        }),
    ], style={
        "minHeight": "100vh", "background": T["bg"], "padding": "24px",
        "fontFamily": "Inter, ui-sans-serif, system-ui, sans-serif",
        "color": "white", "boxSizing": "border-box",
    }),

], style={"margin": "0", "background": T["bg"]})


# ── Callbacks ───────────────────────────────────────────────────────────────

@app.callback(
    Output("s-live-mode", "data"),
    Output("btn-live",    "children"),
    Output("sim-label",   "children"),
    Input("btn-live",     "n_clicks"),
    State("s-live-mode",  "data"),
    prevent_initial_call=True,
)
def toggle_live(n, current):
    new = not current
    return (
        new,
        "Use Synthetic Feed" if new else "Use Live Alpaca Feed",
        "Live Market Feed · Alpaca IEX · Synthetic Options Intelligence"
        if new else
        "Simulation Mode · Synthetic Feed · Controlled Environment",
    )


@app.callback(
    Output("s-symbol", "data"),
    Output("ticker-input", "value"),
    Input("btn-load", "n_clicks"),
    State("ticker-input", "value"),
    prevent_initial_call=True,
)
def load_symbol(_, ticker):
    clean = sanitize_symbol(ticker or "")
    return (clean, clean) if clean else (no_update, no_update)


@app.callback(
    Output("s-tab", "data"),
    Input("tab-command",     "n_clicks"),
    Input("tab-feed",        "n_clicks"),
    Input("tab-performance", "n_clicks"),
    Input("tab-setup",       "n_clicks"),
    prevent_initial_call=True,
)
def set_tab(*_):
    ctx = callback_context
    if not ctx.triggered:
        return no_update
    return ctx.triggered[0]["prop_id"].replace(".n_clicks", "").replace("tab-", "")


@app.callback(
    Output("s-live",    "data"),
    Output("s-seq",     "data"),
    Output("s-candles", "data"),
    Input("i-synth",    "n_intervals"),
    Input("i-alpaca",   "n_intervals"),
    State("s-live",     "data"),
    State("s-seq",      "data"),
    State("s-candles",  "data"),
    State("s-live-mode","data"),
    State("s-symbol",   "data"),
    State("s-price-text","data"),
)
def tick(n_s, n_a, current, seq, candles, live_mode, symbol, price_text):
    import random
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update

    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if live_mode and trigger == "i-alpaca":
        # Hit FastAPI backend which calls Alpaca
        try:
            import requests as req
            r = req.get(f"{BACKEND_HTTP}/api/stock/{symbol}", timeout=4)
            r.raise_for_status()
            data   = r.json()
            price  = float(data["price"])
            volume = int(data.get("volume", 0))
        except Exception:
            return no_update, no_update, no_update
    elif not live_mode and trigger == "i-synth":
        prev  = current["price"] if current else float(price_text or 280.15)
        price  = round(max(1.0, prev + (random.random() - 0.45) * 1.25), 2)
        volume = round(500_000 + random.random() * 5_000_000)
    else:
        return no_update, no_update, no_update

    new_seq  = (seq or 0) + 1
    new_live = create_live_update(symbol, price, volume, new_seq).to_dict()

    # Roll candles
    if candles:
        prior = candles[-1]
        new_c = {
            "o": prior["c"],
            "h": round(max(prior["c"], price) + 0.12, 2),
            "l": round(min(prior["c"], price) - 0.12, 2),
            "c": price,
            "t": new_live["timestamp"],
        }
        new_candles = candles[-49:] + [new_c]
    else:
        new_candles = _init_candles

    return new_live, new_seq, new_candles


@app.callback(
    Output("price-ctrl",  "children"),
    Input("s-live-mode",  "data"),
    Input("s-live",       "data"),
    State("s-price-text", "data"),
)
def render_price_ctrl(live_mode, live, price_text):
    if live_mode:
        price = live["price"] if live else 0
        return html.Div([
            html.Span("Live Price", style={"fontSize": "10px", "color": T["muted"],
                                           "fontWeight": "800", "textTransform": "uppercase",
                                           "letterSpacing": ".12em"}),
            html.Strong(f"${price:.2f}", style={"fontSize": "18px", "color": T["green"],
                                                "fontWeight": "950"}),
        ], style={"background": T["surface"], "border": "1px solid rgba(52,211,153,.40)",
                  "borderRadius": "12px", "padding": "8px 14px", "width": "130px",
                  "minHeight": "50px", "display": "flex",
                  "flexDirection": "column", "justifyContent": "center"})
    return dcc.Input(
        id={"type": "price-in", "index": "0"},
        value=price_text or "280.15", debounce=True,
        style={"background": T["surface"], "color": "white",
               "border": f"1px solid {T['border']}",
               "borderRadius": "12px", "padding": "10px 14px",
               "width": "120px", "outline": "none", "fontSize": "14px"},
    )


@app.callback(
    Output("b-connected", "children"),
    Output("b-feed",      "children"),
    Output("b-tick",      "children"),
    Input("s-live",       "data"),
    Input("s-live-mode",  "data"),
)
def update_badges(live, live_mode):
    seq = live["sequence"] if live else 0
    return (
        badge("LIVE" if live_mode else "SIM", "green" if live_mode else "yellow"),
        badge("Alpaca IEX" if live_mode else "Synthetic Feed", "blue"),
        badge(f"Tick #{seq}", "yellow"),
    )


@app.callback(
    Output("main-content", "children"),
    Input("s-live",        "data"),
    Input("s-candles",     "data"),
    Input("s-tab",         "data"),
    Input("s-live-mode",   "data"),
    Input("i-clock",       "n_intervals"),
    State("s-symbol",      "data"),
    State("s-tf",          "data"),
    State("s-connected",   "data"),
)
def render_main(live, candles, tab, live_mode, _clock, symbol, tf, connected):
    if not live:
        return html.Div("Initializing…", style={"color": T["muted"], "padding": "40px"})

    if tab == "command":
        return build_command_tab(live, candles or _init_candles, symbol, tf, live_mode)
    if tab == "feed":
        return build_feed_tab(live, connected, live_mode)
    if tab == "performance":
        return build_performance_tab(live)
    if tab == "setup":
        return build_setup_tab()
    return html.Div("Unknown tab")


@app.callback(
    Output("time-engine-body", "children"),
    Input("i-clock", "n_intervals"),
)
def update_clock(_):
    from datetime import datetime
    now     = datetime.now()
    minutes = now.hour * 60 + now.minute
    phase   = ("Outside RTH"   if not (570 <= minutes <= 960)
               else "Opening Drive"  if minutes < 630
               else "Midday Auction" if minutes < 840
               else "Closing Auction")
    session_color = T["green"] if 570 <= minutes <= 960 else T["muted"]
    return html.Div([
        metric_box("Clock",         now.strftime("%I:%M:%S %p")),
        html.Div(style={"height": "8px"}),
        metric_box("Session Phase", phase, session_color),
        html.Div(style={"height": "8px"}),
        note_box("Future: economic releases, auction windows, proprietary cycle layers."),
    ])


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
