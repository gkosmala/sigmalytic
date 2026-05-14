"""
Sigmalytic Quant Corporation — Decision Intelligence Platform
Institutional-Grade Frontend · Dash + Plotly
Matches original React app layout + Sigmalytic brand upgrade
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone

import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.engine import (
    sanitize_symbol, create_live_update, generate_initial_candles,
    get_key_levels, build_confluence_nodes, run_decision,
)

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS   = os.getenv("BACKEND_WS_URL", "ws://localhost:8000")
TIMEFRAMES   = ["1m", "5m", "15m", "1H", "1D", "1W"]

# Brand tokens
NAVY      = "#0d1b2e"
NAVY_CARD = "#111f35"
NAVY_MID  = "#0f172a"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"
RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"
YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"
MUTED     = "#64748b"
TEXT      = "#94a3b8"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
BORDER_T  = "rgba(45,143,111,.35)"

GLOBAL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap');
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{NAVY};color:{WHITE};font-family:'DM Sans',ui-sans-serif,system-ui,sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}}
::-webkit-scrollbar{{width:4px;height:4px;}}
::-webkit-scrollbar-track{{background:{NAVY};}}
::-webkit-scrollbar-thumb{{background:{TEAL};border-radius:2px;}}
button{{font-family:inherit;cursor:pointer;border:none;outline:none;}}
input{{font-family:inherit;outline:none;}}
"""

def badge(text, color="teal"):
    palettes = {
        "teal":   (TEAL_DIM,  TEAL_GLOW,  BORDER_T),
        "blue":   (BLUE_DIM,  "rgba(59,130,246,.12)", "rgba(96,165,250,.35)"),
        "yellow": (YELLOW_DIM,"rgba(245,158,11,.12)",  "rgba(245,158,11,.35)"),
        "red":    (RED_DIM,   RED_GLOW,   "rgba(239,68,68,.35)"),
        "gray":   (TEXT,      "rgba(100,116,139,.12)", "rgba(100,116,139,.25)"),
    }
    fg, bg, bdr = palettes.get(color, palettes["teal"])
    return html.Span(text, style={
        "borderRadius":"999px","border":f"1px solid {bdr}",
        "padding":"4px 12px","fontSize":"11px","fontWeight":"800",
        "letterSpacing":".06em","color":fg,"background":bg,
        "whiteSpace":"nowrap","textTransform":"uppercase",
    })

def metric_tile(label, value, accent=WHITE):
    return html.Div([
        html.Span(label, style={"display":"block","color":TEXT,"fontSize":"11px",
                                "fontWeight":"600","textTransform":"uppercase",
                                "letterSpacing":".12em","marginBottom":"8px"}),
        html.Strong(value, style={"display":"block","color":accent,
                                  "fontSize":"15px","fontWeight":"800"}),
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
    elif variant=="blue": s.update({"borderColor":"rgba(59,130,246,.25)","background":"rgba(59,130,246,.08)","color":"#dbeafe"})
    elif variant=="teal": s.update({"borderColor":BORDER_T,"background":TEAL_GLOW,"color":"#d1fae5"})
    return html.Div(text, style=s)

def slabel(text):
    return html.Div(text, style={"color":MUTED,"fontSize":"10px","fontWeight":"800",
                                  "textTransform":"uppercase","letterSpacing":".28em","marginBottom":"8px"})

def pbar(label, value):
    pct = max(0, min(100, value))
    color = TEAL_DIM if pct>=70 else (YELLOW_DIM if pct>=45 else RED_DIM)
    return html.Div([
        html.Div([
            html.Span(label, style={"color":TEXT,"fontSize":"12px","fontWeight":"600"}),
            html.Span(f"{pct}%", style={"color":color,"fontWeight":"800","fontSize":"13px"}),
        ], style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"}),
        html.Div(html.Div(style={"width":f"{pct}%","height":"100%","borderRadius":"999px",
                                  "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})","transition":"width .4s"}),
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

def build_chart(candles, price, nodes):
    kl = get_key_levels(price)
    opens  = [c["o"] for c in candles]
    highs  = [c["h"] for c in candles]
    lows   = [c["l"] for c in candles]
    closes = [c["c"] for c in candles]
    xs     = list(range(len(candles)))
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=xs,open=opens,high=highs,low=lows,close=closes,name="Price",
        increasing=dict(line=dict(color=TEAL_DIM,width=1),fillcolor=TEAL_DIM),
        decreasing=dict(line=dict(color=RED_DIM,width=1),fillcolor=RED_DIM),
    ))
    lvls = [
        (kl.breakout,  f"  {kl.breakout:.2f} Breakout",  TEAL_DIM, "dash"),
        (kl.prior_high,f"  {kl.prior_high:.2f} Liquidity",TEAL_DIM,"dot"),
        (kl.expansion, f"  {kl.expansion:.2f} Expansion", TEAL_DIM,"dashdot"),
        (kl.confirm,   f"  {kl.confirm:.2f} Live Anchor", YELLOW_DIM,"solid"),
        (kl.trigger,   f"  {kl.trigger:.2f} Trigger",     YELLOW_DIM,"dash"),
        (kl.trap,      f"  {kl.trap:.2f} Trap Door",      RED_DIM,"dot"),
        (kl.fail,      f"  {kl.fail:.2f} Fail Gate",      RED_DIM,"dash"),
    ]
    for level,label,color,dash in lvls:
        fig.add_hline(y=level,line_color=color,line_dash=dash,line_width=1,opacity=0.75,
                      annotation_text=label,annotation_position="right",
                      annotation_font=dict(color=color,size=10,family="DM Mono, monospace"))
    fig.add_hline(y=price,line_color=BLUE_DIM,line_dash="solid",line_width=1.5,opacity=1,
                  annotation_text=f"  ${price:.2f} LIVE",annotation_position="right",
                  annotation_font=dict(color=BLUE_DIM,size=11,family="DM Sans"))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor=NAVY,
        font=dict(family="DM Sans",color=TEXT,size=11),
        xaxis=dict(showgrid=True,gridcolor="rgba(255,255,255,.04)",zeroline=False,
                   showticklabels=False,rangeslider=dict(visible=False),color=MUTED),
        yaxis=dict(showgrid=True,gridcolor="rgba(255,255,255,.04)",zeroline=False,
                   color=MUTED,side="right",tickformat=".2f"),
        margin=dict(l=0,r=130,t=12,b=12),height=390,showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor=NAVY_CARD,font_color=WHITE,bordercolor=BORDER,font_size=12),
        dragmode="pan",
    )
    return fig

def build_command_tab(live, candles, symbol, tf):
    price    = live["price"]
    decision = live["decision"]
    nodes    = live["confluence"]
    kl       = get_key_levels(price)
    seq      = live["sequence"]
    score    = decision["score"]
    try:
        ts = datetime.fromisoformat(live["timestamp"].replace("Z","+00:00"))
        live_age = ts.strftime("%I:%M:%S %p")
    except: live_age = "—"
    sc    = TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    size  = "FULL" if score>=80 else ("HALF" if score>=65 else ("PROBE" if score>=45 else "NONE"))
    top   = nodes[0] if nodes else {"public_label":"—","score":0}
    vs    = max(18,min(96,round(abs(price-kl.trigger)*18+(seq%9)*4)))
    cp    = max(12,min(94,round(score+(8 if price>kl.confirm else -10)+(seq%5))))
    pp    = max(8,min(92,100-cp))
    gp    = max(20,min(95,round(55+(price-kl.confirm)*7)))
    fb    = "Call Accumulation / Supportive Flow" if price>=kl.confirm else "Neutral Rotation / Pinning"
    as_   = "Expansion Alert" if score>=80 else ("Trap-Door Alert" if price<kl.trap else "Monitoring")
    aa    = as_ != "Monitoring"
    fig   = build_chart(candles, price, nodes)
    ROW   = {"display":"flex","gap":"16px","marginBottom":"16px"}

    return html.Div([
        # Row 1: Chart + Decision Hero
        html.Div([
            card([
                html.Div([
                    html.Div([
                        html.H2(f"📊 {symbol}  ·  Smart Chart + Live Levels",
                                style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                        html.P(f"Last update {live_age}  ·  Vol {live['volume']:,}  ·  {tf}",
                               style={"fontSize":"12px","color":TEXT}),
                    ]),
                    html.Div([
                        badge(f"Last ${price:.2f}","blue"),
                        html.Span("MODEL: CONFLUENCE ENGINE v1.0",style={"fontSize":"10px","color":MUTED,
                                   "fontWeight":"700","letterSpacing":".14em","textTransform":"uppercase"}),
                    ],style={"display":"flex","alignItems":"center","gap":"10px"}),
                ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                          "flexWrap":"wrap","marginBottom":"14px","gap":"10px"}),
                dcc.Graph(figure=fig,
                          config={"displayModeBar":True,"scrollZoom":True,
                                  "modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"],
                                  "displaylogo":False},
                          style={"borderRadius":"12px","overflow":"hidden"}),
            ],sx={"flex":"1.4","minWidth":"0"}),

            card([
                slabel("Decision Engine"),
                html.Div(decision["status"],style={"color":sc,"fontSize":"40px","fontWeight":"900",
                                                    "lineHeight":"1","letterSpacing":"-.02em","margin":"8px 0 4px"}),
                html.Div("EXECUTION WINDOW",style={"fontSize":"10px","fontWeight":"800","color":TEXT,
                                                    "letterSpacing":".22em","textTransform":"uppercase"}),
                html.Div("Confluence-driven signal derived from multi-factor expansion modeling",
                         style={"fontSize":"11px","color":MUTED,"marginTop":"6px"}),
                html.Div(f"LIVE STATE: {decision['behavior']}",style={
                    "textAlign":"center","borderRadius":"999px","background":"rgba(0,0,0,.3)",
                    "border":f"1px solid {BORDER}","padding":"10px 14px","fontSize":"11px",
                    "fontWeight":"800","textTransform":"uppercase","letterSpacing":".16em",
                    "color":TEXT,"marginTop":"16px"}),
                html.Div([
                    slabel("Execution Directive"),
                    html.Div(decision["next_action"],style={"color":WHITE,"fontSize":"13px",
                                                             "fontWeight":"700","lineHeight":"1.5","marginBottom":"6px"}),
                    html.P(f"${price:.2f}  ·  {top.get('public_label','—')} {top.get('score',0)}%",
                           style={"fontSize":"11px","color":TEXT}),
                ],style={"borderRadius":"14px","background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
                          "padding":"14px","marginTop":"14px"}),
                html.Div(pbar("Signal Strength",score),style={"marginTop":"16px"}),
                html.Div([
                    metric_tile("Bias",decision["bias"],sc),
                    metric_tile("Grade",decision["grade"],sc),
                    metric_tile("Confidence",decision["confidence"],sc),
                    metric_tile("Mode",decision["mode"],BLUE_DIM),
                ],style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"8px","marginTop":"14px"}),
            ],sx={"flex":"1","minWidth":"0"}),
        ],style={**ROW,"alignItems":"start"}),

        # Row 2: 4 cards
        html.Div([
            card([
                html.H2("🎯 Trade Card",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                metric_tile("Bias",decision["bias"],sc),
                html.Div(style={"height":"8px"}),
                metric_tile("Setup",decision["status"],sc),
                html.Div(style={"height":"8px"}),
                metric_tile("Suggested Size",size,sc),
                html.Div(style={"height":"10px"}),
                note_box("Entry logic: tactical only above trigger; A-grade requires live-volume expansion.","yellow"),
                html.P(f"Reference: ${price:.2f}",style={"fontSize":"11px","color":MUTED,"marginTop":"8px"}),
            ],sx={"flex":"1"}),

            card([
                html.H2("🪜 Probability Ladder",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                brow("Upside Expansion", nodes[0]["score"] if nodes else 63, "up"),
                html.P(f"Level ${nodes[0]['level']:.2f}  ·  Current ${price:.2f}" if nodes else "",
                       style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                brow("Liquidity Retest", nodes[1]["score"] if len(nodes)>1 else 60, "up"),
                html.P(f"Level ${nodes[1]['level']:.2f}  ·  Current ${price:.2f}" if len(nodes)>1 else "",
                       style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                brow("Hold / Balance", score, "neutral"),
                html.P(f"Level ${kl.confirm:.2f}  ·  Current ${price:.2f}",
                       style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                brow("Failure Gate", 100-score, "down"),
                html.P(f"Level ${kl.fail:.2f}  ·  Current ${price:.2f}",
                       style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","paddingLeft":"2px"}),
            ],sx={"flex":"1"}),

            card([
                html.H2("⏱️ Time Engine",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                html.Div(id="clock-body"),
            ],sx={"flex":"1"}),

            card([
                html.H2("🔔 Visual + Audio Alerts",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                html.Div(as_,style={
                    "borderRadius":"14px","padding":"18px","textAlign":"center","fontWeight":"900",
                    "fontSize":"14px","letterSpacing":".06em","textTransform":"uppercase",
                    **({"border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM} if aa
                       else {"border":"1px solid rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM}),
                }),
                html.P("Visual triggers active. Audio alerts after severity rules are finalized.",
                       style={"fontSize":"11px","color":MUTED,"marginTop":"10px"}),
            ],sx={"flex":"1"}),
        ],style={**ROW,"alignItems":"start"}),

        # Options Matrix
        card([
            html.Div([
                html.Div([
                    html.H2("🧱 Dynamic Options Matrix + Flow Map",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                    html.P("Synthetic intelligence from price, volume, volatility proxy, and decision score.",
                           style={"fontSize":"12px","color":TEXT}),
                ]),
                badge(fb,"blue"),
            ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                      "flexWrap":"wrap","gap":"10px","marginBottom":"16px"}),
            html.Div([
                zcard("Call Wall",   "285",  f"{cp}% call-side pressure",   TEAL_DIM),
                zcard("Put Wall",    "275",  f"{pp}% put-side pressure",     RED_DIM),
                zcard("Gamma Pivot", "280",  f"{gp}% dealer sensitivity",    YELLOW_DIM),
                zcard("Vol Trigger", "LIVE", f"{vs}% expansion energy",      TEAL_DIM),
            ],style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
            note_box("Synthetic options layer — connect Tradier or CBOE for live institutional flow data.","blue"),
        ],sx={"marginBottom":"16px"}),

        # Summary strip
        card([
            html.Div([
                metric_tile("Symbol",      symbol,         BLUE_DIM),
                metric_tile("Live Price",  f"${price:.2f}",TEAL_DIM),
                metric_tile("Engine Score",f"{score}%",    sc),
                metric_tile("Regime",      decision["mode"],YELLOW_DIM),
            ],style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px"}),
        ]),
    ],style={"display":"flex","flexDirection":"column"})

def build_feed_tab(live, live_mode):
    price = live["price"]
    return card([
        html.Div([
            html.Div([
                html.H2("🔌 Live Feed Monitor",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                html.P(f"Backend: {BACKEND_HTTP}",style={"fontSize":"12px","color":MUTED}),
            ]),
            badge("Connected" if live_mode else "Synthetic","teal" if live_mode else "gray"),
        ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"16px"}),
        html.Div([
            metric_tile("Feed Mode","Live Alpaca" if live_mode else "Synthetic"),
            metric_tile("Symbol",live["symbol"]),
            metric_tile("Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Volume",f"{live['volume']:,}"),
        ],style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"16px"}),
        html.Pre(json.dumps(live,indent=2),style={
            "margin":"0","maxHeight":"460px","overflow":"auto","borderRadius":"14px",
            "border":f"1px solid {BORDER}","background":"rgba(0,0,0,.35)","padding":"16px",
            "color":TEAL_DIM,"fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.6",
        }),
    ])

def build_performance_tab(live):
    price    = live["price"]
    decision = live["decision"]
    score    = decision["score"]
    sc       = TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    return card([
        html.H2("📈 Performance Logger",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Div([
            metric_tile("Current Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Setup",decision["status"],sc),
            metric_tile("Score",f"{score}%",sc),
            metric_tile("Bias",decision["bias"],BLUE_DIM),
        ],style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
        note_box("Trade logging reconnects automatically once live feed stabilizes."),
    ])

def build_behavior_tab(analysis=None):
    if not analysis or not analysis.get("total_trades"):
        # Try fetching cumulative from backend
        import requests as _req
        try:
            r = _req.get(f"{BACKEND_HTTP}/api/import/analysis/demo_user_001", timeout=5)
            if r.ok and r.json():
                analysis = r.json()
        except Exception:
            pass
    if analysis is None:
        analysis = {}

    # ── Upload section (always visible) ───────────────────────────────────────
    upload_section = card([
        html.H2("🧠 Behavioral Intelligence",
                style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 6px"}),
        html.P("Upload your brokerage CSV to generate a full behavioral profile — win rate, edge score, symbol breakdown, and pattern flags.",
               style={"fontSize":"12px","color":TEXT,"marginBottom":"20px"}),
        html.Div([
            dcc.Upload(
                id="csv-upload-behavior",
                children=html.Div([
                    html.Div("📂", style={"fontSize":"32px","marginBottom":"8px"}),
                    html.Div("Drag & drop your CSV here, or click to browse",
                             style={"fontSize":"14px","fontWeight":"700","color":WHITE,"marginBottom":"4px"}),
                    html.Div("Generic CSV · date, symbol, action, qty, price columns",
                             style={"fontSize":"11px","color":MUTED}),
                ], style={"textAlign":"center","padding":"30px 20px"}),
                style={
                    "border":f"2px dashed {BORDER_T}","borderRadius":"16px",
                    "background":TEAL_GLOW,"cursor":"pointer","marginBottom":"14px",
                },
                accept=".csv", multiple=False,
            ),
            html.Div(id="csv-upload-behavior-status",
                     style={"fontSize":"13px","minHeight":"20px"}),
        ]),
    ])

    # ── Analysis section ───────────────────────────────────────────────────────
    if not analysis or not analysis.get("total_trades"):
        analysis_section = card([
            note_box("No import history yet. Upload your CSV above or use the Import History tab to generate your behavioral snapshot.", "blue")
        ])
    else:
        total    = analysis.get("total_trades", 0)
        wr       = analysis.get("win_rate", 0)
        pnl      = analysis.get("total_pnl", 0)
        avg_win  = analysis.get("avg_win", 0)
        avg_loss = analysis.get("avg_loss", 0)
        rr       = analysis.get("rr_ratio", 0)
        edge     = analysis.get("edge_score", 0)
        hold     = analysis.get("avg_hold_time", "—")
        best_s   = analysis.get("best_symbol", "—")
        worst_s  = analysis.get("worst_symbol", "—")
        best_d   = analysis.get("best_day", "—")
        worst_d  = analysis.get("worst_day", "—")
        flags    = analysis.get("behavioral_flags", [])
        overtrade= analysis.get("overtrade_rate", 0)
        sym_perf = analysis.get("symbol_performance", {})

        wr_color   = TEAL_DIM if wr>=55 else (YELLOW_DIM if wr>=45 else RED_DIM)
        pnl_color  = TEAL_DIM if pnl>=0 else RED_DIM
        edge_color = TEAL_DIM if edge>0 else RED_DIM
        rr_color   = TEAL_DIM if rr>=1.5 else (YELLOW_DIM if rr>=1.0 else RED_DIM)

        edge_insight = (f"Positive mathematical edge of ${edge:.2f} per trade." if edge>0
                        else f"Negative edge of ${edge:.2f} per trade — math works against you long-term.")

        # Symbol performance table
        top_syms = sorted(sym_perf.items(), key=lambda x: x[1].get("total_pnl",0), reverse=True)[:8]
        sym_rows = []
        for sym, sp in top_syms:
            c = TEAL_DIM if sp.get("total_pnl",0)>=0 else RED_DIM
            sym_rows.append(html.Tr([
                html.Td(sym,                                    style={"color":WHITE,"fontWeight":"700","padding":"8px 12px","fontSize":"12px"}),
                html.Td(str(sp.get("trades",0)),               style={"color":TEXT,"padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"{sp.get('win_rate',0):.0f}%",        style={"color":TEAL_DIM if sp.get("win_rate",0)>=50 else RED_DIM,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"${sp.get('total_pnl',0):+.2f}",     style={"color":c,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"right"}),
            ], style={"borderBottom":f"1px solid {BORDER}"}))

        analysis_section = html.Div([
            # Row 1: Key metrics
            card([
                html.H2("📊 Behavioral Snapshot",
                        style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
                html.Div([
                    metric_tile("Total Trades",   str(total),           WHITE),
                    metric_tile("Win Rate",       f"{wr}%",             wr_color),
                    metric_tile("Total P&L",      f"${pnl:+,.2f}",      pnl_color),
                    metric_tile("Avg Win",        f"${avg_win:+.2f}",   TEAL_DIM),
                    metric_tile("Avg Loss",       f"${avg_loss:+.2f}",  RED_DIM),
                    metric_tile("R:R Ratio",      f"{rr:.2f}",          rr_color),
                    metric_tile("Edge Score",     f"${edge:.2f}",       edge_color),
                    metric_tile("Avg Hold",       hold,                 BLUE_DIM),
                ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
                note_box(edge_insight, "teal" if edge>0 else "yellow"),
            ], sx={"marginBottom":"16px"}),

            # Row 2: Flags + best/worst
            html.Div([
                card([
                    html.H2("🚩 Behavioral Flags",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                    html.Div([
                        html.Div([
                            html.Span("⚠️ " if "negative" in f.lower() or "overtrading" in f.lower() or "streak" in f.lower()
                                      else "✅ ",
                                      style={"marginRight":"6px"}),
                            html.Span(f, style={"fontSize":"12px","color":TEXT}),
                        ], style={"padding":"8px 0","borderBottom":f"1px solid {BORDER}"})
                        for f in flags
                    ]) if flags else note_box("No behavioral flags generated yet.", "blue"),
                ], sx={"flex":"1"}),

                card([
                    html.H2("🏆 Best & Worst",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                    metric_tile("Best Symbol",  best_s,  TEAL_DIM),
                    html.Div(style={"height":"8px"}),
                    metric_tile("Worst Symbol", worst_s, RED_DIM),
                    html.Div(style={"height":"8px"}),
                    metric_tile("Best Day",     best_d,  TEAL_DIM),
                    html.Div(style={"height":"8px"}),
                    metric_tile("Worst Day",    worst_d, RED_DIM),
                    html.Div(style={"height":"8px"}),
                    metric_tile("Overtrade Rate", f"{overtrade}%", YELLOW_DIM if overtrade>30 else TEXT),
                ], sx={"flex":"1"}),
            ], style={"display":"flex","gap":"16px","marginBottom":"16px"}),

            # Row 3: Symbol table
            card([
                html.H2("📋 Symbol Performance",
                        style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Symbol", style={"color":MUTED,"fontSize":"11px","fontWeight":"700","textTransform":"uppercase","padding":"8px 12px","textAlign":"left"}),
                        html.Th("Trades", style={"color":MUTED,"fontSize":"11px","fontWeight":"700","textTransform":"uppercase","padding":"8px 12px","textAlign":"center"}),
                        html.Th("Win %",  style={"color":MUTED,"fontSize":"11px","fontWeight":"700","textTransform":"uppercase","padding":"8px 12px","textAlign":"center"}),
                        html.Th("P&L",    style={"color":MUTED,"fontSize":"11px","fontWeight":"700","textTransform":"uppercase","padding":"8px 12px","textAlign":"right"}),
                    ], style={"borderBottom":f"1px solid {BORDER}"})),
                    html.Tbody(sym_rows),
                ], style={"width":"100%","borderCollapse":"collapse"})
                if sym_rows else note_box("No symbol data available.", "blue"),
            ]),
        ])

    return html.Div([upload_section, analysis_section])


def build_import_tab():
    return card([
        html.H2("📂 Import Trade History",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 6px"}),
        html.P("Upload a CSV file containing your trade history. The file should include columns for symbol, side (buy/sell), quantity, price, and date/time.",
               style={"fontSize":"12px","color":TEXT,"marginBottom":"20px"}),
        html.Div([
            html.Div([
                slabel("Required columns (any order, flexible naming)"),
                html.Div([
                    html.Span(col, style={"background":"rgba(45,143,111,.15)","border":f"1px solid {BORDER_T}",
                                          "borderRadius":"6px","padding":"4px 10px","fontSize":"11px",
                                          "color":TEAL_DIM,"fontWeight":"700","fontFamily":"DM Mono, monospace"})
                    for col in ["symbol","side / action","qty / quantity","price","date / time"]
                ], style={"display":"flex","flexWrap":"wrap","gap":"8px","marginBottom":"16px"}),
                dcc.Upload(
                    id="csv-upload",
                    children=html.Div([
                        html.Div("📁", style={"fontSize":"32px","marginBottom":"8px"}),
                        html.Div("Drag & drop your CSV here, or click to browse",
                                 style={"color":WHITE,"fontWeight":"700","fontSize":"14px","marginBottom":"4px"}),
                        html.Div("Supports generic broker exports · .csv files only",
                                 style={"color":MUTED,"fontSize":"12px"}),
                    ], style={"textAlign":"center","padding":"40px 20px"}),
                    style={
                        "border":f"2px dashed {BORDER_T}","borderRadius":"16px",
                        "background":"rgba(45,143,111,.05)","cursor":"pointer",
                        "transition":"border-color .2s",
                    },
                    accept=".csv",
                    multiple=False,
                ),
                html.Div(id="csv-upload-status", style={"marginTop":"16px","fontSize":"13px"}),
            ], style={"flex":"1.2","minWidth":"0"}),

            html.Div([
                slabel("Import Tips"),
                note_box("• Export your trades as CSV from your broker platform.\n"
                         "• Include both BUY and SELL rows — trades are reconstructed as pairs.\n"
                         "• Date formats like 2024-01-15 or 01/15/2024 are both fine.\n"
                         "• Column names are matched flexibly (e.g. 'Action', 'Side', 'B/S' all work).",
                         variant="blue"),
                html.Div(style={"height":"12px"}),
                note_box("After uploading, use the Reset button in the Setup tab to clear all history and start fresh.",
                         variant="yellow"),
            ], style={"flex":"1","minWidth":"0"}),
        ], style={"display":"flex","gap":"20px","alignItems":"flex-start","flexWrap":"wrap"}),
    ])

def build_setup_tab():
    return card([
        html.H2("🧩 Setup & Deployment",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Pre(
            f"Frontend  : Dash (Python)  →  Render\n"
            f"Backend   : FastAPI        →  Render\n"
            f"Data      : Alpaca IEX (free) / SIP (paid)\n"
            f"WebSocket : {BACKEND_WS}/ws/{{symbol}}\n"
            f"REST      : {BACKEND_HTTP}/api/stock/{{symbol}}\n\n"
            f"Env vars:\n"
            f"  ALPACA_API_KEY     — Alpaca key ID\n"
            f"  ALPACA_API_SECRET  — Alpaca secret\n"
            f"  BACKEND_URL        — HTTP base URL\n"
            f"  BACKEND_WS_URL     — WebSocket base URL",
            style={"margin":"0","borderRadius":"14px","border":f"1px solid {BORDER}",
                   "background":"rgba(0,0,0,.35)","padding":"16px","color":TEAL_DIM,
                   "fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.7"},
        ),
        html.Hr(style={"borderColor":"#2a2f45","margin":"24px 0"}),
        html.H4("🧪 Lab Tools",style={"color":"#888","fontSize":"13px",
                "letterSpacing":"1px","marginBottom":"8px"}),
        html.P("Reset all imported trade history. Use this in the lab to start fresh.",
               style={"color":"#666","fontSize":"12px","marginBottom":"12px"}),
        html.Button("🗑️ Reset Import History",id="reset-trades-btn",
            n_clicks=0,
            style={"backgroundColor":"#8B0000","color":"white",
                   "border":"none","padding":"10px 24px",
                   "borderRadius":"6px","cursor":"pointer",
                   "fontSize":"13px","fontWeight":"600"}),
        html.Div(id="reset-trades-output",style={"marginTop":"10px","fontSize":"13px"}),
    ])

# Logo
LOGO = html.Div([
    html.Div("Σ", style={"fontSize":"28px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1","flexShrink":"0"}),
    html.Div([
        html.Span("SIGMALYTIC",style={"fontSize":"18px","fontWeight":"900","color":WHITE,
                                       "letterSpacing":".08em","lineHeight":"1"}),
        html.Span("QUANT CORPORATION",style={"fontSize":"9px","fontWeight":"700","color":TEAL_DIM,
                                              "letterSpacing":".22em","display":"block","marginTop":"2px"}),
    ]),
],style={"display":"flex","alignItems":"center","gap":"10px"})

app = dash.Dash(
    __name__,
    title="Sigmalytic Quant Corporation — Decision Intelligence",
    update_title=None,
    meta_tags=[{"name":"viewport","content":"width=device-width, initial-scale=1"},
               {"name":"theme-color","content":NAVY}],
)
server = app.server

app.index_string = f"""<!DOCTYPE html>
<html>
<head>
{{%metas%}}
<title>{{%title%}}</title>
{{%favicon%}}
{{%css%}}
<style>{GLOBAL_CSS}</style>
</head>
<body>
{{%app_entry%}}
<footer>{{%config%}}</footer>
{{%scripts%}}
{{%renderer%}}
</body>
</html>"""

_init_live = create_live_update("AAPL",280.15,750_000,0).to_dict()
_init_candles = [{"o":c.o,"h":c.h,"l":c.l,"c":c.c,"t":str(i)}
                 for i,c in enumerate(generate_initial_candles(280.15))]

app.layout = html.Div([
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-candles",   data=_init_candles),
    dcc.Store(id="s-seq",       data=0),
    dcc.Store(id="s-live-mode", data=False),
    dcc.Store(id="s-symbol",    data="AAPL"),
    dcc.Store(id="s-tf",        data="5m"),
    dcc.Store(id="s-tab",       data="command"),
    dcc.Store(id="s-price-text",data="280.15"),
    dcc.Store(id="s-analysis",  data={}),
    dcc.Store(id="s-refresh",   data=0),
    dcc.Interval(id="i-synth",  interval=1_400,n_intervals=0),
    dcc.Interval(id="i-alpaca", interval=5_000,n_intervals=0),
    dcc.Interval(id="i-clock",  interval=1_000,n_intervals=0),

    html.Div([html.Div([
        html.Header([
            html.Div([
                LOGO,
                html.Div([
                    html.Div("SIGMALYTIC SYSTEM // DECISION LAYER",style={"fontSize":"10px","fontWeight":"800",
                              "textTransform":"uppercase","letterSpacing":".32em","color":TEAL_DIM}),
                    html.Div(id="sim-label",style={"fontSize":"10px","fontWeight":"700","textTransform":"uppercase",
                              "letterSpacing":".18em","color":BLUE_DIM,"marginTop":"3px"}),
                ],style={"textAlign":"center"}),
                html.Div(style={"width":"120px"}),
            ],style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                      "width":"100%","marginBottom":"6px"}),
            html.P("Real-time decision intelligence — scores, interprets, and projects market behavior via multi-layer confluence.",
                   style={"fontSize":"12px","color":MUTED,"textAlign":"center","maxWidth":"640px","margin":"0 auto"}),
            html.P("Powered by Confluence Engine · Expansion Node Modeling · Forward Projection Layer",
                   style={"fontSize":"11px","color":"#475569","textAlign":"center","letterSpacing":".06em","marginTop":"4px"}),
            html.Hr(style={"border":"none","height":"1px","background":BORDER,"width":"60%","margin":"12px auto 0"}),
            html.Div([
                html.H1("Decision Command Center",style={"fontSize":"30px","fontWeight":"900",
                          "lineHeight":"1","letterSpacing":"-.02em","color":WHITE}),
                html.Span(id="b-connected"),
                html.Span(id="b-feed"),
                html.Span(id="b-tick"),
            ],style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
            html.Div([
                dcc.Input(id="ticker-input",value="AAPL",debounce=False,
                          style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}",
                                 "borderRadius":"12px","padding":"10px 14px","width":"120px",
                                 "fontSize":"14px","fontWeight":"700"}),
                html.Button("Load Symbol",id="btn-load",n_clicks=0,style={
                    "background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
                    "borderRadius":"12px","padding":"10px 18px","fontSize":"13px","fontWeight":"800"}),
                html.Div(id="price-ctrl"),
                html.Div([
                    html.Button(tf,id={"type":"tf","index":tf},n_clicks=0,style={
                        "background":"transparent","color":TEXT,"border":"none","borderRadius":"10px",
                        "padding":"8px 12px","fontSize":"12px","fontWeight":"700"}) for tf in TIMEFRAMES
                ],style={"display":"flex","gap":"2px","padding":"4px","background":NAVY_MID,
                          "border":f"1px solid {BORDER}","borderRadius":"12px"}),
                html.Button(id="btn-live",n_clicks=0,style={
                    "background":WHITE,"color":NAVY,"border":"none","borderRadius":"12px",
                    "padding":"10px 18px","fontSize":"13px","fontWeight":"800"}),
            ],style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
        ],style={"display":"flex","flexDirection":"column","alignItems":"center","gap":"14px","paddingBottom":"4px"}),

        html.Nav([
            html.Button(label,id=f"tab-{key}",n_clicks=0,style={
                "background":"transparent","color":TEXT,"border":"none","borderRadius":"10px",
                "padding":"10px 20px","fontSize":"13px","fontWeight":"700","whiteSpace":"nowrap"})
            for key,label in [("command","Command Center"),("feed","Live Feed"),
                               ("performance","Performance"),("behavior","Behavioral Intelligence"),
                               ("import","Import History"),("setup","Setup")]
        ],style={"display":"flex","gap":"4px","padding":"4px","borderRadius":"14px",
                  "background":NAVY_MID,"border":f"1px solid {BORDER}",
                  "justifyContent":"center","overflowX":"auto"}),

        html.Main(id="main-content"),

    ],style={"maxWidth":"1440px","margin":"0 auto","display":"flex","flexDirection":"column","gap":"16px"})],
    style={"minHeight":"100vh","background":NAVY,"padding":"24px"}),
],style={"margin":"0","background":NAVY})

@app.callback(Output("s-live-mode","data"),Output("btn-live","children"),Output("sim-label","children"),
              Input("btn-live","n_clicks"),State("s-live-mode","data"),prevent_initial_call=True)
def toggle_live(_,current):
    new=not current
    return new,("Use Synthetic Feed" if new else "Use Live Alpaca Feed"),\
           ("LIVE MARKET FEED · ALPACA IEX · SYNTHETIC OPTIONS INTELLIGENCE" if new
            else "SIMULATION MODE · SYNTHETIC FEED · CONTROLLED ENVIRONMENT")

@app.callback(Output("s-symbol","data"),Output("ticker-input","value"),
              Input("btn-load","n_clicks"),State("ticker-input","value"),prevent_initial_call=True)
def load_symbol(_,ticker):
    clean=sanitize_symbol(ticker or "")
    return (clean,clean) if clean else (no_update,no_update)

@app.callback(Output("s-tab","data"),
              Input("tab-command","n_clicks"),Input("tab-feed","n_clicks"),
              Input("tab-performance","n_clicks"),Input("tab-behavior","n_clicks"),
              Input("tab-import","n_clicks"),
              Input("tab-setup","n_clicks"),prevent_initial_call=True)
def set_tab(*_):
    ctx=callback_context
    if not ctx.triggered: return no_update
    return ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")

@app.callback(Output("s-live","data"),Output("s-seq","data"),Output("s-candles","data"),
              Input("i-synth","n_intervals"),Input("i-alpaca","n_intervals"),
              State("s-live","data"),State("s-seq","data"),State("s-candles","data"),
              State("s-live-mode","data"),State("s-symbol","data"),State("s-price-text","data"))
def tick(_,__,current,seq,candles,live_mode,symbol,price_text):
    import random
    ctx=callback_context
    if not ctx.triggered: return no_update,no_update,no_update
    trigger=ctx.triggered[0]["prop_id"].split(".")[0]
    if live_mode and trigger=="i-alpaca":
        try:
            import requests as req
            r=req.get(f"{BACKEND_HTTP}/api/stock/{symbol}",timeout=4)
            r.raise_for_status()
            data=r.json(); price=float(data["price"]); volume=int(data.get("volume",0))
        except: return no_update,no_update,no_update
    elif not live_mode and trigger=="i-synth":
        prev=current["price"] if current else float(price_text or 280.15)
        price=round(max(1.0,prev+(random.random()-0.45)*1.25),2)
        volume=round(500_000+random.random()*5_000_000)
    else: return no_update,no_update,no_update
    new_seq=(seq or 0)+1
    new_live=create_live_update(symbol,price,volume,new_seq).to_dict()
    if candles:
        prior=candles[-1]
        new_c={"o":prior["c"],"h":round(max(prior["c"],price)+0.12,2),
               "l":round(min(prior["c"],price)-0.12,2),"c":price,"t":str(new_seq)}
        new_candles=candles[-49:]+[new_c]
    else: new_candles=_init_candles
    return new_live,new_seq,new_candles

@app.callback(Output("price-ctrl","children"),Input("s-live-mode","data"),
              Input("s-live","data"),State("s-price-text","data"))
def render_price_ctrl(live_mode,live,price_text):
    if live_mode:
        price=live["price"] if live else 0
        return html.Div([
            html.Span("Live Price",style={"fontSize":"10px","color":MUTED,"fontWeight":"700",
                                          "textTransform":"uppercase","letterSpacing":".12em"}),
            html.Strong(f"${price:.2f}",style={"fontSize":"17px","color":TEAL_DIM,"fontWeight":"900"}),
        ],style={"background":NAVY_MID,"border":f"1px solid {BORDER_T}","borderRadius":"12px",
                  "padding":"8px 14px","width":"130px","minHeight":"50px",
                  "display":"flex","flexDirection":"column","justifyContent":"center"})
    return dcc.Input(id={"type":"price-in","index":"0"},value=price_text or "280.15",debounce=True,
                     style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}",
                            "borderRadius":"12px","padding":"10px 14px","width":"120px","fontSize":"14px"})

@app.callback(Output("b-connected","children"),Output("b-feed","children"),Output("b-tick","children"),
              Input("s-live","data"),Input("s-live-mode","data"))
def update_badges(live,live_mode):
    seq=live["sequence"] if live else 0
    return (badge("LIVE" if live_mode else "SIM","teal" if live_mode else "gray"),
            badge("Alpaca IEX" if live_mode else "Synthetic Feed","blue"),
            badge(f"Tick #{seq}","yellow"))

@app.callback(Output("main-content","children"),
              Input("s-live","data"),Input("s-candles","data"),Input("s-tab","data"),
              Input("s-live-mode","data"),Input("i-clock","n_intervals"),
              Input("s-analysis","data"),Input("s-refresh","data"),
              State("s-symbol","data"),State("s-tf","data"))
def render_main(live,candles,tab,live_mode,_clock,analysis,_refresh,symbol,tf):
    if not live: return html.Div("Initializing…",style={"color":MUTED,"padding":"60px","textAlign":"center"})
    ctx = callback_context
    trigger = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""
    if tab in ("behavior","import","setup","performance","feed") and trigger == "i-clock":
        return no_update
    if tab=="command":     return build_command_tab(live,candles or _init_candles,symbol,tf)
    if tab=="feed":        return build_feed_tab(live,live_mode)
    if tab=="performance": return build_performance_tab(live)
    if tab=="behavior":    return build_behavior_tab(analysis or {})
    if tab=="import":      return build_import_tab()
    if tab=="setup":       return build_setup_tab()
    return html.Div("Unknown tab")

@app.callback(Output("clock-body","children"),Input("i-clock","n_intervals"))
def update_clock(_):
    now=datetime.now(); minutes=now.hour*60+now.minute
    in_sess=570<=minutes<=960
    phase=("Outside RTH" if not in_sess else "Opening Drive" if minutes<630
           else "Midday Auction" if minutes<840 else "Closing Auction")
    pc=TEAL_DIM if in_sess else MUTED
    return html.Div([
        metric_tile("Clock",now.strftime("%I:%M:%S %p")),
        html.Div(style={"height":"8px"}),
        metric_tile("Session Phase",phase,pc),
        html.Div(style={"height":"10px"}),
        note_box("Future: economic releases, auction windows, proprietary cycle layers."),
    ])

@app.callback(Output("csv-upload-behavior-status","children"),Output("s-analysis","data"),Output("s-refresh","data"),
              Input("csv-upload-behavior","contents"),
              State("csv-upload-behavior","filename"),State("s-refresh","data"),
              prevent_initial_call=True)
def handle_csv_upload_behavior(contents, filename, refresh):
    if not contents:
        return no_update, no_update, no_update
    import base64, io as _io, requests as _req
    try:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        url = f"{BACKEND_HTTP}/api/import/upload-generic"
        resp = _req.post(
            url,
            files={"file": (filename, _io.BytesIO(decoded), "text/csv")},
            data={"symbol_col":"symbol","side_col":"action","qty_col":"qty",
                  "price_col":"price","timestamp_col":"date"},
            timeout=30,
        )
        if not resp.ok:
            return html.Span(f"❌ Backend error {resp.status_code}: {resp.text[:300]}",
                             style={"color":RED_DIM}), no_update, no_update
        data = resp.json()
        trades_count = data.get("trades_closed", 0)
        if trades_count == 0:
            return html.Span(f"⚠️ 0 trades reconstructed. Raw rows: {data.get('raw_rows',0)}. Check CSV format.",
                             style={"color":YELLOW_DIM}), no_update, no_update

        # Fetch cumulative analysis from Supabase instead of using this batch only
        try:
            r2 = _req.get(f"{BACKEND_HTTP}/api/import/analysis/demo_user_001", timeout=10)
            cumulative = r2.json() if r2.ok and r2.json() else data.get("analysis", {})
        except Exception:
            cumulative = data.get("analysis", {})

        return html.Div([
            html.Span("✅ Import successful · ", style={"color":TEAL_DIM,"fontWeight":"800"}),
            html.Span(f"{trades_count} trades added · Cumulative: {cumulative.get('total_trades',0)} trades · Win rate: {cumulative.get('win_rate',0)}% · P&L: ${cumulative.get('total_pnl',0):+,.2f}",
                      style={"color":TEXT}),
        ]), cumulative, (refresh or 0) + 1
    except Exception as e:
        return html.Span(f"❌ Error: {str(e)[:300]}", style={"color":RED_DIM}), no_update, no_update

@app.callback(Output("csv-upload-status","children"),
              Input("csv-upload","contents"),
              State("csv-upload","filename"),
              prevent_initial_call=True)
def handle_csv_upload(contents, filename):
    if not contents:
        return no_update
    import base64, io as _io, requests as _req
    try:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        resp = _req.post(
            f"{BACKEND_HTTP}/api/import/upload-generic",
            files={"file": (filename, _io.BytesIO(decoded), "text/csv")},
            data={"symbol_col":"symbol","side_col":"action","qty_col":"qty",
                  "price_col":"price","timestamp_col":"date"},
            timeout=30,
        )
        if not resp.ok:
            return html.Span(f"❌ Upload failed ({resp.status_code}): {resp.text[:300]}",
                             style={"color":RED_DIM})
        data = resp.json()
        trades_count = data.get("trades_closed", 0)
        analysis = data.get("analysis", {})
        if trades_count == 0:
            return html.Span(f"⚠️ 0 trades reconstructed. Raw rows: {data.get('raw_rows',0)}. Check CSV format.",
                             style={"color":YELLOW_DIM})
        return html.Div([
            html.Span("✅ Import successful · ", style={"color":TEAL_DIM,"fontWeight":"800"}),
            html.Span(f"{trades_count} trades · Win rate: {analysis.get('win_rate',0)}% · P&L: ${analysis.get('total_pnl',0):+,.2f} · Go to Behavioral Intelligence tab to see full dashboard.",
                      style={"color":TEXT}),
        ])
    except Exception as e:
        return html.Span(f"❌ Error: {str(e)[:300]}", style={"color":RED_DIM})

@app.callback(Output("reset-trades-output","children"),
              Input("reset-trades-btn","n_clicks"),
              prevent_initial_call=True)
def reset_trade_history(n_clicks):
    if not n_clicks:
        return ""
    import requests as _req
    try:
        r = _req.delete(f"{BACKEND_HTTP}/api/trades/reset", timeout=10)
        if r.status_code == 200:
            return html.Span("✅ Trade history cleared. Refresh the page to see updated counts.",
                             style={"color":"#00ff88"})
        else:
            return html.Span(f"❌ Reset failed (status {r.status_code}). Try again.",
                             style={"color":"#ff4444"})
    except Exception as e:
        return html.Span(f"❌ Error: {str(e)}", style={"color":"#ff4444"})

if __name__=="__main__":
    app.run(debug=False,host="0.0.0.0",port=8050)