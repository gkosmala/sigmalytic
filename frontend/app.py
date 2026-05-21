"""
Sigmalytic Quant Corporation — Decision Intelligence Platform
Institutional-Grade Frontend · Dash + Plotly
"""

from __future__ import annotations
import json
import os
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from shared.engine import (
    sanitize_symbol, create_live_update, generate_initial_candles,
    get_key_levels, build_confluence_nodes, run_decision,
)
from billing_ui import build_billing_tab, register_billing_callbacks
from admin_tab import build_admin_tab, is_admin   # ← ADMIN TAB

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_WS   = os.getenv("BACKEND_WS_URL", "ws://localhost:8000")
TIMEFRAMES   = ["1m", "5m", "15m", "1H", "1D", "1W"]

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

def _auth_headers(session: dict) -> dict:
    if not session: return {}
    token = session.get("access_token", "")
    if not token: return {}
    return {"Authorization": f"Bearer {token}"}

def _user_id(session: dict) -> str:
    return (session or {}).get("user_id", "demo_user_001")

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
                                "letterSpacing":".12em","marginBottom":"8px","minHeight":"28px"}),
        html.Strong(value, style={"display":"block","color":accent,"fontSize":"15px","fontWeight":"800"}),
    ], style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px","minHeight":"64px",
               "display":"flex","flexDirection":"column","justifyContent":"space-between"})

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

def _status_color(status):
    return {"Armed":TEAL_DIM,"Building":YELLOW_DIM,"Triggered":BLUE_DIM,"Confirmed":TEAL_DIM,
            "Failed":RED_DIM,"Short Trigger":RED_DIM,"Short Confirmed":RED_DIM,
            "Short Armed":"#ff6b6b","Watching":TEXT,"Avoid":RED_DIM}.get(status, TEXT)

def _score_color(score):
    if score >= 75: return TEAL_DIM
    if score >= 60: return YELLOW_DIM
    return RED_DIM

def _change_color(pct):
    if pct > 0: return TEAL_DIM
    if pct < 0: return RED_DIM
    return TEXT

def build_radar_row(sym):
    score=sym.get("composite_score",0); status=sym.get("status","Watching")
    chg=sym.get("change_pct",0); price=sym.get("price",0)
    sc=_score_color(score); stc=_status_color(status); chgc=_change_color(chg)
    trigger=sym.get("trigger",0); invalidation=sym.get("invalidation",0)
    target1=sym.get("target1",0); target2=sym.get("target2",0); atr=sym.get("atr",1)
    bear1=round(invalidation-atr*1.0,2); bear2=round(invalidation-atr*2.0,2)
    score_bar=html.Div([html.Div(style={"width":f"{score}%","height":"100%","borderRadius":"999px",
        "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})"})],
        style={"height":"5px","background":"rgba(255,255,255,.08)","borderRadius":"999px",
               "overflow":"hidden","marginTop":"4px","width":"80px"})
    projection_block=html.Div([
        html.Div([html.Span("▲ Bull",style={"fontSize":"9px","fontWeight":"800","color":TEAL_DIM,"textTransform":"uppercase","letterSpacing":".08em","marginRight":"6px"}),
                  html.Span(f"Above ${trigger:,.2f} → ${target1:,.2f} → ${target2:,.2f}",style={"fontSize":"10px","color":TEAL_DIM,"fontFamily":"DM Mono, monospace"})],style={"marginBottom":"3px"}),
        html.Div([html.Span("◆ Neutral",style={"fontSize":"9px","fontWeight":"800","color":YELLOW_DIM,"textTransform":"uppercase","letterSpacing":".08em","marginRight":"6px"}),
                  html.Span(f"${invalidation:,.2f} – ${trigger:,.2f} chop zone",style={"fontSize":"10px","color":YELLOW_DIM,"fontFamily":"DM Mono, monospace"})],style={"marginBottom":"3px"}),
        html.Div([html.Span("▼ Bear",style={"fontSize":"9px","fontWeight":"800","color":RED_DIM,"textTransform":"uppercase","letterSpacing":".08em","marginRight":"6px"}),
                  html.Span(f"Below ${invalidation:,.2f} → ${bear1:,.2f} → ${bear2:,.2f}",style={"fontSize":"10px","color":RED_DIM,"fontFamily":"DM Mono, monospace"})]),
    ],style={"borderLeft":f"2px solid {BORDER}","paddingLeft":"10px","marginTop":"8px"})
    return html.Div([
        html.Div([
            html.Div([html.Span(sym.get("symbol",""),style={"fontWeight":"800","fontSize":"14px","color":WHITE,"fontFamily":"DM Mono, monospace"}),
                      html.Span(sym.get("setup_type",""),style={"fontSize":"10px","color":WHITE,"display":"block","marginTop":"2px"})],style={"flex":"2","minWidth":"120px"}),
            html.Div([html.Span(f"${price:,.2f}",style={"fontWeight":"700","fontSize":"13px","color":WHITE}),
                      html.Span(f"  {'+' if chg>=0 else ''}{chg:.2f}%",style={"fontSize":"12px","color":chgc,"fontWeight":"600"})],style={"flex":"1.5","minWidth":"100px"}),
            html.Div([html.Span(f"{score:.0f}",style={"fontWeight":"900","fontSize":"15px","color":sc}),score_bar],style={"flex":"1","minWidth":"70px"}),
            html.Div(html.Span(status,style={"fontSize":"10px","fontWeight":"800","color":stc,"border":f"1px solid {stc}","borderRadius":"999px","padding":"3px 10px","background":f"{stc}18","textTransform":"uppercase","letterSpacing":".06em"}),style={"flex":"1","minWidth":"80px"}),
            html.Div([html.Span("Trigger",style={"fontSize":"10px","color":WHITE,"display":"block"}),html.Span(f"${trigger:,.2f}",style={"fontSize":"12px","color":YELLOW_DIM,"fontWeight":"700"}),html.Span(f"{sym.get('trigger_proximity',0):+.1f}%" if sym.get('trigger_proximity',0)!=0 else "",style={"fontSize":"10px","color":WHITE,"display":"block"})],style={"flex":"1","minWidth":"80px"}),
            html.Div(html.Span(sym.get("regime","—"),style={"fontSize":"11px","color":sc,"fontWeight":"600"}),style={"flex":"1.5","minWidth":"100px"}),
            html.Div([html.Span(f"C:{sym.get('confluence',0):.0f} E:{sym.get('expansion_node',0):.0f} RS:{sym.get('relative_strength',0):.0f}",style={"fontSize":"10px","color":sc,"fontFamily":"DM Mono, monospace","fontWeight":"600","display":"block"}),
                      html.Span(f"VP:{sym.get('volume_pressure',0):.0f} B:{sym.get('behavioral',0):.0f}",style={"fontSize":"10px","color":sc,"fontFamily":"DM Mono, monospace","fontWeight":"600","display":"block","marginTop":"2px"})],style={"flex":"2","minWidth":"130px"}),
        ],style={"display":"flex","alignItems":"center","gap":"12px"}),
        projection_block,
    ],style={"padding":"12px 16px","borderBottom":f"1px solid {BORDER}","transition":"background .15s"})


def build_radar_tab(radar_data=None, status_filter="all"):
    import requests as _req
    if radar_data is None:
        try:
            r=_req.get(f"{BACKEND_HTTP}/api/radar/scores?limit=100",timeout=10)
            radar_data=r.json() if r.ok else {}
        except Exception:
            radar_data={}
        if not radar_data or not radar_data.get("symbols"):
            return card([html.Div([html.Div("📡",style={"fontSize":"48px","marginBottom":"16px"}),
                html.Div("Radar initializing…",style={"fontSize":"16px","fontWeight":"700","color":WHITE,"marginBottom":"8px"}),
                html.Div("The scoring engine is warming up. This takes about 60 seconds on first load.",style={"fontSize":"13px","color":TEXT,"maxWidth":"400px","lineHeight":"1.7"})],
                style={"textAlign":"center","padding":"60px 20px"})])

    all_symbols=radar_data.get("symbols",[])
    status_filter=(status_filter or "all").lower()
    if status_filter=="all": symbols=all_symbols
    elif status_filter=="triggered": symbols=[s for s in all_symbols if s.get("status","").lower() in ("triggered","confirmed")]
    elif status_filter=="long": symbols=[s for s in all_symbols if s.get("status","") in ("Armed","Triggered","Confirmed")]
    elif status_filter=="short": symbols=[s for s in all_symbols if s.get("status","") in ("Short Trigger","Short Confirmed","Short Armed")]
    else: symbols=[s for s in all_symbols if s.get("status","").lower()==status_filter]

    delay=radar_data.get("data_delay","15min"); last_scan=radar_data.get("last_scan")
    if last_scan:
        import time; ago=int(time.time()-last_scan); scan_label=f"{ago}s ago"
    else: scan_label="—"

    armed=sum(1 for s in all_symbols if s.get("status")=="Armed")
    building=sum(1 for s in all_symbols if s.get("status")=="Building")
    triggered=sum(1 for s in all_symbols if s.get("status") in ("Triggered","Confirmed"))
    long_ct=armed+triggered
    shorting=sum(1 for s in all_symbols if s.get("status") in ("Short Trigger","Short Confirmed","Short Armed"))
    avoid=sum(1 for s in all_symbols if s.get("status")=="Avoid")
    avg_score=round(sum(s.get("composite_score",0) for s in all_symbols)/len(all_symbols),1) if all_symbols else 0
    delay_color=YELLOW_DIM if delay=="15min" else TEAL_DIM
    delay_label="15-Min Delayed" if delay=="15min" else "Live"

    return html.Div([
        card([
            html.Div([
                html.Div([html.H2("📡 Radar Screen",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                          html.P("Real-time opportunity ranking — scored, interpreted, and ranked by confluence.",style={"fontSize":"12px","color":TEXT})]),
                html.Div([html.Span(delay_label,style={"fontSize":"10px","fontWeight":"800","color":delay_color,"border":f"1px solid {delay_color}","borderRadius":"999px","padding":"4px 12px","background":f"{delay_color}18","textTransform":"uppercase","letterSpacing":".06em","marginRight":"8px"}),
                          html.Span(f"Last scan: {scan_label}",style={"fontSize":"11px","color":MUTED})],style={"display":"flex","alignItems":"center"}),
            ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"16px"}),
            html.Div([
                metric_tile("Symbols Scanned",str(len(all_symbols)),BLUE_DIM),
                metric_tile("▲ Long",str(long_ct),TEAL_DIM),
                metric_tile("Armed",str(armed),TEAL_DIM),
                metric_tile("Building",str(building),YELLOW_DIM),
                metric_tile("Triggered",str(triggered),BLUE_DIM),
                metric_tile("▼ Short",str(shorting),RED_DIM),
                metric_tile("Avoid",str(avoid),RED_DIM),
                metric_tile("Avg Score",f"{avg_score}",_score_color(avg_score)),
            ],style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"12px"}),
        ],sx={"marginBottom":"16px"}),
        card([
            html.Div([
                html.Span("Filter:",style={"color":MUTED,"fontSize":"12px","fontWeight":"600","marginRight":"8px"}),
                *[html.Button(label,id=f"radar-filter-{key}",n_clicks=0,style={
                    "background":TEAL_GLOW if status_filter==key else "transparent",
                    "color":TEAL_DIM if status_filter==key else TEXT,
                    "border":f"1px solid {BORDER_T}" if status_filter==key else f"1px solid {BORDER}",
                    "borderRadius":"8px","padding":"6px 14px","fontSize":"12px","fontWeight":"700","marginRight":"6px","cursor":"pointer"})
                  for key,label in [("all","All"),("armed","Armed"),("building","Building"),("triggered","Triggered"),("long","▲ Long"),("short","▼ Short"),("watching","Watching"),("avoid","Avoid")]],
                html.Div(style={"flex":"1"}),
                html.Span(f"{len(symbols)} of {len(all_symbols)} symbols",style={"fontSize":"11px","color":MUTED}),
            ],style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
        ],sx={"marginBottom":"16px","padding":"12px 20px"}),
        card([
            html.Div([
                html.Span("Symbol / Setup",style={"flex":"2","minWidth":"120px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Price / Chg",style={"flex":"1.5","minWidth":"100px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Score",style={"flex":"1","minWidth":"70px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Status",style={"flex":"1","minWidth":"80px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Trigger",style={"flex":"1","minWidth":"80px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Regime",style={"flex":"1.5","minWidth":"100px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Breakdown",style={"flex":"2","minWidth":"130px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
            ],style={"display":"flex","alignItems":"center","gap":"12px","padding":"8px 16px","borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),
            html.Div([html.Span("C=Confluence · E=Expansion · RS=Rel.Strength · VP=Vol.Pressure · B=Behavioral",style={"fontSize":"9px","color":MUTED,"paddingLeft":"16px","fontFamily":"DM Mono, monospace"})],style={"paddingBottom":"6px"}),
            html.Div([html.Span("▲ Bull / ◆ Neutral / ▼ Bear projection paths shown below each symbol",style={"fontSize":"10px","color":WHITE,"fontStyle":"italic","paddingLeft":"16px"})],style={"paddingBottom":"8px"}),
            html.Div([build_radar_row(s) for s in symbols] if symbols else [html.Div("No radar data yet — scanner initializing…",style={"padding":"40px","textAlign":"center","color":MUTED})],id="radar-rows"),
        ]),
        html.Div(note_box(f"{'⏱ Data is 15 minutes delayed (free Alpaca IEX feed).' if delay=='15min' else '✅ Live data feed active.'}  Scores update every 60 seconds.","yellow" if delay=="15min" else "teal"),style={"marginTop":"16px"}),
    ],style={"display":"flex","flexDirection":"column"})


def build_scoreboard_tab():
    import requests as _req
    try:
        r=_req.get(f"{BACKEND_HTTP}/api/scoreboard",timeout=10)
        data=r.json() if r.ok else {}
    except Exception:
        data={}
    total=data.get("total_graded",0); pending=data.get("pending",0)
    long_wr=data.get("long_win_rate",0); short_wr=data.get("short_win_rate",0)
    grade_a=data.get("grade_a",0); grade_b=data.get("grade_b",0)
    avg_pct=data.get("avg_winner_pct",0); avg_days=data.get("avg_days",0)
    signals=data.get("recent_signals",[])

    def grade_color(g):
        if g in ("A","Short-A"): return TEAL_DIM
        if g in ("B","Short-B"): return BLUE_DIM
        if g in ("C","Short-C"): return YELLOW_DIM
        if g in ("Miss","Short-Miss"): return RED_DIM
        return MUTED

    def grade_label(g):
        return {"A":"A — Full Target","B":"B — Partial","C":"C — Neutral","Miss":"Miss",
                "Short-A":"A — Short Full","Short-B":"B — Short Partial","Short-C":"C — Short Neutral",
                "Short-Miss":"Short Miss","Pending":"Pending"}.get(g,g)

    rows=[]
    for s in signals:
        grade=s.get("grade","Pending"); gc=grade_color(grade); gl=grade_label(grade)
        pct=s.get("outcome_pct"); days=s.get("days"); sig_type=s.get("signal_type","")
        is_short="Short" in sig_type
        try:
            dt=datetime.fromisoformat(s["signal_date"].replace("Z","+00:00")); date_str=dt.strftime("%b %d %I:%M %p")
        except: date_str="—"
        rows.append(html.Div([
            html.Div([html.Span(s.get("symbol",""),style={"fontWeight":"800","fontSize":"14px","color":WHITE,"fontFamily":"DM Mono, monospace","display":"block"}),
                      html.Span(sig_type,style={"fontSize":"10px","color":RED_DIM if is_short else TEAL_DIM,"fontWeight":"700","display":"block","marginTop":"2px"})],style={"flex":"1.5","minWidth":"100px"}),
            html.Div(html.Span(date_str,style={"fontSize":"11px","color":TEXT}),style={"flex":"1.5","minWidth":"100px"}),
            html.Div(html.Span(f"${s.get('entry_price',0):,.2f}",style={"fontSize":"12px","color":WHITE,"fontWeight":"700"}),style={"flex":"1","minWidth":"80px"}),
            html.Div(html.Span(f"{s.get('score',0):.0f}",style={"fontSize":"13px","color":_score_color(s.get('score',0)),"fontWeight":"800"}),style={"flex":"0.8","minWidth":"60px"}),
            html.Div(html.Span(s.get("setup_type","—"),style={"fontSize":"10px","color":TEXT}),style={"flex":"2","minWidth":"120px"}),
            html.Div(html.Span(s.get("regime","—"),style={"fontSize":"11px","color":TEXT}),style={"flex":"1.5","minWidth":"100px"}),
            html.Div(html.Span(gl,style={"fontSize":"10px","fontWeight":"800","color":gc,"border":f"1px solid {gc}","borderRadius":"999px","padding":"3px 10px","background":f"{gc}18","textTransform":"uppercase","letterSpacing":".06em"}),style={"flex":"1","minWidth":"90px"}),
            html.Div(html.Span(f"{pct:+.1f}%" if pct is not None else "—",style={"fontSize":"12px","fontWeight":"700","color":TEAL_DIM if (pct or 0)>0 else (RED_DIM if (pct or 0)<0 else MUTED)}),style={"flex":"0.8","minWidth":"60px"}),
            html.Div(html.Span(f"{days}d" if days is not None else "—",style={"fontSize":"11px","color":MUTED}),style={"flex":"0.6","minWidth":"40px"}),
        ],style={"display":"flex","alignItems":"center","gap":"12px","padding":"12px 16px","borderBottom":f"1px solid {BORDER}"}))

    empty_state=html.Div([html.Div("📡",style={"fontSize":"48px","marginBottom":"16px"}),
        html.Div("No signals logged yet",style={"fontSize":"16px","fontWeight":"700","color":WHITE,"marginBottom":"8px"}),
        html.Div("The scoreboard begins recording when the market opens.",style={"fontSize":"13px","color":TEXT,"maxWidth":"480px","lineHeight":"1.7"})],
        style={"textAlign":"center","padding":"60px 20px"})

    return html.Div([
        card([
            html.Div([
                html.Div([html.H2("📋 Signal Scoreboard",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                          html.P("Every radar signal logged, tracked, and graded.",style={"fontSize":"12px","color":TEXT})]),
                html.Div([badge("LIVE TRACKING","teal"),html.Span("Signals logged from market open · Graded at 4:15 PM ET daily",style={"fontSize":"10px","color":MUTED,"marginLeft":"8px"})],style={"display":"flex","alignItems":"center"}),
            ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"20px"}),
            html.Div([
                metric_tile("Graded",str(total),WHITE),metric_tile("Pending",str(pending),YELLOW_DIM),
                metric_tile("Long Win %",f"{long_wr}%",TEAL_DIM if long_wr>=50 else RED_DIM),
                metric_tile("Short Win %",f"{short_wr}%",TEAL_DIM if short_wr>=50 else RED_DIM),
                metric_tile("A Grades",str(grade_a),TEAL_DIM),metric_tile("B Grades",str(grade_b),BLUE_DIM),
                metric_tile("Avg Win %",f"{avg_pct:+.1f}%",TEAL_DIM if avg_pct>0 else RED_DIM),
                metric_tile("Avg Hold",f"{avg_days:.1f}" if avg_days>=1 else f"{avg_days*24:.1f}h" if avg_days>0 else "—",TEXT),
            ],style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"12px"}),
        ],sx={"marginBottom":"16px"}),
        card([
            html.Div([
                html.Span("Grade Guide:",style={"fontSize":"11px","color":MUTED,"fontWeight":"700","marginRight":"16px"}),
                *[html.Span([html.Span(l,style={"fontWeight":"800","color":c,"fontSize":"11px","marginRight":"4px"}),
                             html.Span(d,style={"color":TEXT,"fontSize":"11px","marginRight":"16px"})])
                  for l,c,d in [("A",TEAL_DIM,"— Hit full target"),("B",BLUE_DIM,"— Hit target 1"),
                                ("C",YELLOW_DIM,"— Moved right direction"),("Miss",RED_DIM,"— Hit invalidation"),
                                ("Pending",MUTED,"— Awaiting outcome")]],
            ],style={"display":"flex","alignItems":"center","flexWrap":"wrap","gap":"4px"}),
        ],sx={"marginBottom":"16px","padding":"12px 20px"}),
        card([
            html.Div([
                html.Span("Symbol",style={"flex":"1.5","minWidth":"100px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Date",style={"flex":"1.5","minWidth":"100px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Entry",style={"flex":"1","minWidth":"80px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Score",style={"flex":"0.8","minWidth":"60px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Setup",style={"flex":"2","minWidth":"120px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Regime",style={"flex":"1.5","minWidth":"100px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Grade",style={"flex":"1","minWidth":"90px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Outcome",style={"flex":"0.8","minWidth":"60px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
                html.Span("Days",style={"flex":"0.6","minWidth":"40px","fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
            ],style={"display":"flex","alignItems":"center","gap":"12px","padding":"8px 16px","borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),
            html.Div(rows if rows else [empty_state],id="scoreboard-rows"),
        ]),
        html.Div(note_box("Signals logged in real time · Graded at 4:15 PM ET daily.","teal"),style={"marginTop":"16px"}),
    ],style={"display":"flex","flexDirection":"column"})


def build_chart(candles, price, nodes):
    kl=get_key_levels(price)
    opens=[c["o"] for c in candles]; highs=[c["h"] for c in candles]
    lows=[c["l"] for c in candles]; closes=[c["c"] for c in candles]
    xs=list(range(len(candles)))
    fig=go.Figure()
    fig.add_trace(go.Candlestick(x=xs,open=opens,high=highs,low=lows,close=closes,name="Price",
        increasing=dict(line=dict(color=TEAL_DIM,width=1),fillcolor=TEAL_DIM),
        decreasing=dict(line=dict(color=RED_DIM,width=1),fillcolor=RED_DIM)))
    for level,label,color,dash in [
        (kl.breakout,f"  {kl.breakout:.2f} Breakout",TEAL_DIM,"dash"),
        (kl.prior_high,f"  {kl.prior_high:.2f} Liquidity",TEAL_DIM,"dot"),
        (kl.expansion,f"  {kl.expansion:.2f} Expansion",TEAL_DIM,"dashdot"),
        (kl.confirm,f"  {kl.confirm:.2f} Live Anchor",YELLOW_DIM,"solid"),
        (kl.trigger,f"  {kl.trigger:.2f} Trigger",YELLOW_DIM,"dash"),
        (kl.trap,f"  {kl.trap:.2f} Trap Door",RED_DIM,"dot"),
        (kl.fail,f"  {kl.fail:.2f} Fail Gate",RED_DIM,"dash"),
    ]:
        fig.add_hline(y=level,line_color=color,line_dash=dash,line_width=1,opacity=0.75,
                      annotation_text=label,annotation_position="right",
                      annotation_font=dict(color=color,size=10,family="DM Mono, monospace"))
    fig.add_hline(y=price,line_color=BLUE_DIM,line_dash="solid",line_width=1.5,opacity=1,
                  annotation_text=f"  ${price:.2f} LIVE",annotation_position="right",
                  annotation_font=dict(color=BLUE_DIM,size=11,family="DM Sans"))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor=NAVY,
        font=dict(family="DM Sans",color=TEXT,size=11),
        xaxis=dict(showgrid=True,gridcolor="rgba(255,255,255,.04)",zeroline=False,showticklabels=False,rangeslider=dict(visible=False),color=MUTED),
        yaxis=dict(showgrid=True,gridcolor="rgba(255,255,255,.04)",zeroline=False,color=MUTED,side="right",tickformat=".2f"),
        margin=dict(l=0,r=130,t=12,b=12),height=390,showlegend=False,hovermode="x unified",
        hoverlabel=dict(bgcolor=NAVY_CARD,font_color=WHITE,bordercolor=BORDER,font_size=12),dragmode="pan")
    return fig

def build_command_tab(live, candles, symbol, tf):
    price=live["price"]; decision=live["decision"]; nodes=live["confluence"]
    kl=get_key_levels(price); seq=live["sequence"]; score=decision["score"]
    try:
        ts=datetime.fromisoformat(live["timestamp"].replace("Z","+00:00")); live_age=ts.strftime("%I:%M:%S %p")
    except: live_age="—"
    sc=TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    size="FULL" if score>=80 else ("HALF" if score>=65 else ("PROBE" if score>=45 else "NONE"))
    top=nodes[0] if nodes else {"public_label":"—","score":0}
    vs=max(18,min(96,round(abs(price-kl.trigger)*18+(seq%9)*4)))
    cp=max(12,min(94,round(score+(8 if price>kl.confirm else -10)+(seq%5))))
    pp=max(8,min(92,100-cp)); gp=max(20,min(95,round(55+(price-kl.confirm)*7)))
    fb="Call Accumulation / Supportive Flow" if price>=kl.confirm else "Neutral Rotation / Pinning"
    as_="Expansion Alert" if score>=80 else ("Trap-Door Alert" if price<kl.trap else "Monitoring")
    aa=as_!="Monitoring"; fig=build_chart(candles,price,nodes)
    ROW={"display":"flex","gap":"16px","marginBottom":"16px"}
    return html.Div([
        html.Div([
            card([
                html.Div([
                    html.Div([html.H2(f"📊 {symbol}  ·  Smart Chart + Live Levels",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                              html.P(f"Last update {live_age}  ·  Vol {live['volume']:,}  ·  {tf}",style={"fontSize":"12px","color":TEXT})]),
                    html.Div([badge(f"Last ${price:.2f}","blue"),html.Span("MODEL: CONFLUENCE ENGINE v1.0",style={"fontSize":"10px","color":MUTED,"fontWeight":"700","letterSpacing":".14em","textTransform":"uppercase"})],style={"display":"flex","alignItems":"center","gap":"10px"}),
                ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","flexWrap":"wrap","marginBottom":"14px","gap":"10px"}),
                dcc.Graph(figure=fig,config={"displayModeBar":True,"scrollZoom":True,"modeBarButtonsToRemove":["select2d","lasso2d","autoScale2d"],"displaylogo":False},style={"borderRadius":"12px","overflow":"hidden"}),
            ],sx={"flex":"1.4","minWidth":"0"}),
            card([
                slabel("Decision Engine"),
                html.Div(decision["status"],style={"color":sc,"fontSize":"40px","fontWeight":"900","lineHeight":"1","letterSpacing":"-.02em","margin":"8px 0 4px"}),
                html.Div("EXECUTION WINDOW",style={"fontSize":"10px","fontWeight":"800","color":TEXT,"letterSpacing":".22em","textTransform":"uppercase"}),
                html.Div("Confluence-driven signal derived from multi-factor expansion modeling",style={"fontSize":"11px","color":MUTED,"marginTop":"6px"}),
                html.Div(f"LIVE STATE: {decision['behavior']}",style={"textAlign":"center","borderRadius":"999px","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","padding":"10px 14px","fontSize":"11px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".16em","color":TEXT,"marginTop":"16px"}),
                html.Div([slabel("Execution Directive"),html.Div(decision["next_action"],style={"color":WHITE,"fontSize":"13px","fontWeight":"700","lineHeight":"1.5","marginBottom":"6px"}),
                          html.P(f"${price:.2f}  ·  {top.get('public_label','—')} {top.get('score',0)}%",style={"fontSize":"11px","color":TEXT})],
                         style={"borderRadius":"14px","background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}","padding":"14px","marginTop":"14px"}),
                html.Div(pbar("Signal Strength",score),style={"marginTop":"16px"}),
                html.Div([metric_tile("Bias",decision["bias"],sc),metric_tile("Grade",decision["grade"],sc),metric_tile("Confidence",decision["confidence"],sc),metric_tile("Mode",decision["mode"],BLUE_DIM)],
                         style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"8px","marginTop":"14px"}),
            ],sx={"flex":"1","minWidth":"0"}),
        ],style={**ROW,"alignItems":"start"}),
        html.Div([
            card([html.H2("🎯 Trade Card",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                  metric_tile("Bias",decision["bias"],sc),html.Div(style={"height":"8px"}),
                  metric_tile("Setup",decision["status"],sc),html.Div(style={"height":"8px"}),
                  metric_tile("Suggested Size",size,sc),html.Div(style={"height":"10px"}),
                  note_box("Entry logic: tactical only above trigger; A-grade requires live-volume expansion.","yellow"),
                  html.P(f"Reference: ${price:.2f}",style={"fontSize":"11px","color":MUTED,"marginTop":"8px"})],sx={"flex":"1"}),
            card([html.H2("🪜 Probability Ladder",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                  brow("Upside Expansion",nodes[0]["score"] if nodes else 63,"up"),
                  html.P(f"Level ${nodes[0]['level']:.2f}  ·  Current ${price:.2f}" if nodes else "",style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                  brow("Liquidity Retest",nodes[1]["score"] if len(nodes)>1 else 60,"up"),
                  html.P(f"Level ${nodes[1]['level']:.2f}  ·  Current ${price:.2f}" if len(nodes)>1 else "",style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                  brow("Hold / Balance",score,"neutral"),
                  html.P(f"Level ${kl.confirm:.2f}  ·  Current ${price:.2f}",style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","marginBottom":"8px","paddingLeft":"2px"}),
                  brow("Failure Gate",100-score,"down"),
                  html.P(f"Level ${kl.fail:.2f}  ·  Current ${price:.2f}",style={"fontSize":"10px","color":MUTED,"marginTop":"-4px","paddingLeft":"2px"})],sx={"flex":"1"}),
            card([html.H2("⏱️ Time Engine",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),html.Div(id="clock-body")],sx={"flex":"1"}),
            card([html.H2("🔔 Visual + Audio Alerts",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
                  html.Div(as_,style={"borderRadius":"14px","padding":"18px","textAlign":"center","fontWeight":"900","fontSize":"14px","letterSpacing":".06em","textTransform":"uppercase",
                      **({"border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM} if aa else {"border":"1px solid rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM})}),
                  html.P("Visual triggers active.",style={"fontSize":"11px","color":MUTED,"marginTop":"10px"})],sx={"flex":"1"}),
        ],style={**ROW,"alignItems":"start"}),
        card([
            html.Div([
                html.Div([html.H2("🧱 Dynamic Options Matrix + Flow Map",style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                          html.P("Synthetic intelligence from price, volume, volatility proxy, and decision score.",style={"fontSize":"12px","color":TEXT})]),
                badge(fb,"blue"),
            ],style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","flexWrap":"wrap","gap":"10px","marginBottom":"16px"}),
            html.Div([zcard("Call Wall","285",f"{cp}% call-side pressure",TEAL_DIM),zcard("Put Wall","275",f"{pp}% put-side pressure",RED_DIM),
                      zcard("Gamma Pivot","280",f"{gp}% dealer sensitivity",YELLOW_DIM),zcard("Vol Trigger","LIVE",f"{vs}% expansion energy",TEAL_DIM)],
                     style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
            note_box("Synthetic options layer — connect Tradier or CBOE for live institutional flow data.","blue"),
        ],sx={"marginBottom":"16px"}),
        card([html.Div([metric_tile("Symbol",symbol,BLUE_DIM),metric_tile("Live Price",f"${price:.2f}",TEAL_DIM),metric_tile("Engine Score",f"{score}%",sc),metric_tile("Regime",decision["mode"],YELLOW_DIM)],
                       style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px"})]),
    ],style={"display":"flex","flexDirection":"column"})

def build_feed_tab(live, live_mode):
    price=live["price"]
    return card([
        html.Div([html.Div([html.H2("🔌 Live Feed Monitor",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),html.P(f"Backend: {BACKEND_HTTP}",style={"fontSize":"12px","color":MUTED})]),
                  badge("Connected" if live_mode else "Synthetic","teal" if live_mode else "gray")],
                 style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"16px"}),
        html.Div([metric_tile("Feed Mode","Live Alpaca" if live_mode else "Synthetic"),metric_tile("Symbol",live["symbol"]),metric_tile("Price",f"${price:.2f}",TEAL_DIM),metric_tile("Volume",f"{live['volume']:,}")],
                 style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"16px"}),
        html.Pre(json.dumps(live,indent=2),style={"margin":"0","maxHeight":"460px","overflow":"auto","borderRadius":"14px","border":f"1px solid {BORDER}","background":"rgba(0,0,0,.35)","padding":"16px","color":TEAL_DIM,"fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.6"}),
    ])

def build_performance_tab(live):
    price=live["price"]; decision=live["decision"]; score=decision["score"]
    sc=TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    return card([
        html.H2("📈 Performance Logger",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Div([metric_tile("Current Price",f"${price:.2f}",TEAL_DIM),metric_tile("Setup",decision["status"],sc),metric_tile("Score",f"{score}%",sc),metric_tile("Bias",decision["bias"],BLUE_DIM)],
                 style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
        note_box("Trade logging reconnects automatically once live feed stabilizes."),
    ])

def build_behavior_tab(analysis=None, perms=None, session=None):
    can_upload=(perms or {}).get("behavioral_intel_csv_upload",True)
    uid=_user_id(session)
    if not analysis or not analysis.get("total_trades"):
        import requests as _req
        try:
            r=_req.get(f"{BACKEND_HTTP}/api/import/analysis/{uid}",headers=_auth_headers(session),timeout=5)
            if r.ok and r.json(): analysis=r.json()
        except Exception: pass
    if analysis is None: analysis={}

    if can_upload:
        upload_content=html.Div([
            dcc.Upload(id="csv-upload-behavior",children=html.Div([html.Div("📂",style={"fontSize":"32px","marginBottom":"8px"}),
                html.Div("Drag & drop your CSV here, or click to browse",style={"fontSize":"14px","fontWeight":"700","color":WHITE,"marginBottom":"4px"}),
                html.Div("Generic CSV · date, symbol, action, qty, price columns",style={"fontSize":"11px","color":MUTED})],style={"textAlign":"center","padding":"30px 20px"}),
                style={"border":f"2px dashed {BORDER_T}","borderRadius":"16px","background":TEAL_GLOW,"cursor":"pointer","marginBottom":"14px"},accept=".csv",multiple=False),
            html.Div(id="csv-upload-behavior-status",style={"fontSize":"13px","minHeight":"20px"}),
        ])
    else:
        upload_content=html.Div([
            html.Div([html.Div("🔒",style={"fontSize":"32px","marginBottom":"8px"}),html.Div("CSV Upload — Premium Feature",style={"fontSize":"14px","fontWeight":"700","color":WHITE,"marginBottom":"4px"}),html.Div("Upgrade to Premium Beta.",style={"fontSize":"11px","color":MUTED})],style={"textAlign":"center","padding":"30px 20px"}),
            dcc.Upload(id="csv-upload-behavior",children=html.Div(),style={"display":"none"}),
            html.Div(id="csv-upload-behavior-status",style={"display":"none"}),
        ],style={"border":f"2px dashed {BORDER}","borderRadius":"16px","background":"rgba(0,0,0,.2)","marginBottom":"14px","opacity":"0.7"})

    upload_section=card([html.H2("🧠 Behavioral Intelligence",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 6px"}),html.P("Upload your brokerage CSV to generate a full behavioral profile.",style={"fontSize":"12px","color":TEXT,"marginBottom":"20px"}),upload_content])
    if not analysis or not analysis.get("total_trades"):
        analysis_section=card([note_box("No import history yet. Upload your CSV above.","blue")])
    else:
        total=analysis.get("total_trades",0); wr=analysis.get("win_rate",0); pnl=analysis.get("total_pnl",0)
        avg_win=analysis.get("avg_win",0); avg_loss=analysis.get("avg_loss",0); rr=analysis.get("rr_ratio",0)
        edge=analysis.get("edge_score",0); hold=analysis.get("avg_hold_time","—")
        wr_color=TEAL_DIM if wr>=55 else (YELLOW_DIM if wr>=45 else RED_DIM)
        pnl_color=TEAL_DIM if pnl>=0 else RED_DIM
        edge_color=TEAL_DIM if edge>0 else RED_DIM
        rr_color=TEAL_DIM if rr>=1.5 else (YELLOW_DIM if rr>=1.0 else RED_DIM)
        edge_insight=(f"Positive mathematical edge of ${edge:.2f} per trade." if edge>0 else f"Negative edge of ${edge:.2f} per trade.")
        analysis_section=card([
            html.H2("📊 Behavioral Snapshot",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
            html.Div([metric_tile("Total Trades",str(total),WHITE),metric_tile("Win Rate",f"{wr}%",wr_color),metric_tile("Total P&L",f"${pnl:+,.2f}",pnl_color),metric_tile("Avg Win",f"${avg_win:+.2f}",TEAL_DIM),metric_tile("Avg Loss",f"${avg_loss:+.2f}",RED_DIM),metric_tile("R:R Ratio",f"{rr:.2f}",rr_color),metric_tile("Edge Score",f"${edge:.2f}",edge_color),metric_tile("Avg Hold",hold,BLUE_DIM)],
                     style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
            note_box(edge_insight,"teal" if edge>0 else "yellow"),
        ])
    return html.Div([upload_section,analysis_section])

def build_import_tab():
    return card([
        html.H2("📂 Import Trade History",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 6px"}),
        html.P("Upload a CSV file containing your trade history.",style={"fontSize":"12px","color":TEXT,"marginBottom":"20px"}),
        html.Div([
            html.Div([
                slabel("Required columns"),
                html.Div([html.Span(col,style={"background":"rgba(45,143,111,.15)","border":f"1px solid {BORDER_T}","borderRadius":"6px","padding":"4px 10px","fontSize":"11px","color":TEAL_DIM,"fontWeight":"700","fontFamily":"DM Mono, monospace"})
                          for col in ["symbol","side / action","qty / quantity","price","date / time"]],
                         style={"display":"flex","flexWrap":"wrap","gap":"8px","marginBottom":"16px"}),
                dcc.Upload(id="csv-upload",children=html.Div([html.Div("📁",style={"fontSize":"32px","marginBottom":"8px"}),html.Div("Drag & drop your CSV here, or click to browse",style={"color":WHITE,"fontWeight":"700","fontSize":"14px","marginBottom":"4px"}),html.Div("Supports generic broker exports · .csv files only",style={"color":MUTED,"fontSize":"12px"})],style={"textAlign":"center","padding":"40px 20px"}),
                    style={"border":f"2px dashed {BORDER_T}","borderRadius":"16px","background":"rgba(45,143,111,.05)","cursor":"pointer"},accept=".csv",multiple=False),
                html.Div(id="csv-upload-status",style={"marginTop":"16px","fontSize":"13px"}),
            ],style={"flex":"1.2","minWidth":"0"}),
            html.Div([slabel("Import Tips"),note_box("• Export trades as CSV from your broker.\n• Include BUY and SELL rows.\n• Date formats like 2024-01-15 or 01/15/2024 are both fine.",variant="blue")],style={"flex":"1","minWidth":"0"}),
        ],style={"display":"flex","gap":"20px","alignItems":"flex-start","flexWrap":"wrap"}),
    ])

def build_setup_tab():
    return card([
        html.H2("🧩 Setup & Deployment",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Pre(f"Frontend  : Dash (Python)  →  Render\nBackend   : FastAPI        →  Render\nData      : Alpaca IEX (free) / SIP (paid)\nWebSocket : {BACKEND_WS}/ws/{{symbol}}\nREST      : {BACKEND_HTTP}/api/stock/{{symbol}}",
                 style={"margin":"0","borderRadius":"14px","border":f"1px solid {BORDER}","background":"rgba(0,0,0,.35)","padding":"16px","color":TEAL_DIM,"fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.7"}),
        html.Hr(style={"borderColor":"#2a2f45","margin":"24px 0"}),
        html.H4("🧪 Lab Tools",style={"color":"#888","fontSize":"13px","letterSpacing":"1px","marginBottom":"8px"}),
        html.P("Reset all imported trade history.",style={"color":"#666","fontSize":"12px","marginBottom":"12px"}),
        html.Button("🗑️ Reset Import History",id="reset-trades-btn",n_clicks=0,
            style={"backgroundColor":"#8B0000","color":"white","border":"none","padding":"10px 24px","borderRadius":"6px","cursor":"pointer","fontSize":"13px","fontWeight":"600"}),
        html.Div(id="reset-trades-output",style={"marginTop":"10px","fontSize":"13px"}),
    ])

LOGO=html.Div([
    html.Div("Σ",style={"fontSize":"28px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1","flexShrink":"0"}),
    html.Div([html.Span("SIGMALYTIC",style={"fontSize":"18px","fontWeight":"900","color":WHITE,"letterSpacing":".08em","lineHeight":"1"}),
              html.Span("QUANT CORPORATION",style={"fontSize":"9px","fontWeight":"700","color":TEAL_DIM,"letterSpacing":".22em","display":"block","marginTop":"2px"})]),
],style={"display":"flex","alignItems":"center","gap":"10px"})

app=dash.Dash(__name__,title="Sigmalytic Quant Corporation — Decision Intelligence",update_title=None,
    suppress_callback_exceptions=True,
    meta_tags=[{"name":"viewport","content":"width=device-width, initial-scale=1"},{"name":"theme-color","content":NAVY}])
server=app.server

RESET_JS="""
<script>
window.addEventListener('load', function() {
    var hash = window.location.hash;
    if (hash && hash.includes('type=recovery') && hash.includes('access_token=')) {
        var params = new URLSearchParams(hash.substring(1));
        var token = params.get('access_token');
        if (token) {
            sessionStorage.setItem('supabase_recovery_token', token);
            setTimeout(function() { var el=document.getElementById('recovery-token-signal'); if(el) el.innerText=token; }, 1000);
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }
});
</script>
"""

app.index_string=f"""<!DOCTYPE html>
<html>
<head>
{{%metas%}}
<title>{{%title%}}</title>
{{%favicon%}}
{{%css%}}
<style>{GLOBAL_CSS}</style>
{RESET_JS}
</head>
<body>
{{%app_entry%}}
<footer>{{%config%}}</footer>
{{%scripts%}}
{{%renderer%}}
</body>
</html>"""

_init_live=create_live_update("AAPL",280.15,750_000,0).to_dict()
_init_candles=[{"o":c.o,"h":c.h,"l":c.l,"c":c.c,"t":str(i)} for i,c in enumerate(generate_initial_candles(280.15))]
SUPABASE_URL=os.getenv("SUPABASE_URL","")
SUPABASE_ANON_KEY=os.getenv("SUPABASE_ANON_KEY","")

def build_reset_page():
    return html.Div([html.Div([
        html.Div([html.Div("Σ",style={"fontSize":"48px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1"}),html.Div("SIGMALYTIC",style={"fontSize":"20px","fontWeight":"900","color":WHITE,"letterSpacing":".2em","marginTop":"4px"}),html.Div("QUANT CORPORATION",style={"fontSize":"10px","fontWeight":"700","color":MUTED,"letterSpacing":".3em","marginTop":"2px"})],style={"textAlign":"center","marginBottom":"40px"}),
        html.Div([
            html.H2("Set New Password",style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
            html.Div([html.Label("New Password",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="reset-password-input",type="password",placeholder="Min 6 characters",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"16px"}),
            html.Div([html.Label("Confirm Password",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="reset-password-confirm",type="password",placeholder="Repeat password",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"24px"}),
            html.Div(id="reset-error",style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
            html.Button("Set New Password",id="reset-submit-btn",n_clicks=0,style={"width":"100%","background":TEAL,"color":WHITE,"border":"none","borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700","cursor":"pointer"}),
        ],style={"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px","padding":"40px","width":"400px","boxShadow":"0 20px 60px rgba(0,0,0,.4)"}),
    ],style={"display":"flex","flexDirection":"column","alignItems":"center","justifyContent":"center","minHeight":"100vh","padding":"20px"})],style={"background":NAVY})

def build_login_page(error=""):
    def pill(icon,text):
        return html.Div([html.Span(icon,style={"marginRight":"6px"}),html.Span(text,style={"fontSize":"11px","fontWeight":"600","color":TEXT})],
                        style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}","borderRadius":"999px","padding":"6px 14px","whiteSpace":"nowrap"})
    def stat(value,label):
        return html.Div([html.Div(value,style={"fontSize":"24px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1"}),html.Div(label,style={"fontSize":"10px","color":MUTED,"fontWeight":"600","textTransform":"uppercase","letterSpacing":".12em","marginTop":"4px"})],style={"textAlign":"center","flex":"1"})
    hero=html.Div([
        html.Div([html.Span("Σ",style={"fontSize":"36px","fontWeight":"900","color":TEAL_DIM,"marginRight":"10px"}),html.Div([html.Div("SIGMALYTIC",style={"fontSize":"22px","fontWeight":"900","color":WHITE,"letterSpacing":".08em","lineHeight":"1"}),html.Div("QUANT CORPORATION",style={"fontSize":"9px","fontWeight":"700","color":TEAL_DIM,"letterSpacing":".22em"})])],style={"display":"flex","alignItems":"center","marginBottom":"40px"}),
        html.H1(["Real-Time ",html.Span("Decision Intelligence",style={"color":TEAL_DIM}),html.Br(),"for Modern Markets."],style={"fontSize":"42px","fontWeight":"900","color":WHITE,"lineHeight":"1.1","letterSpacing":"-.02em","margin":"0 0 20px"}),
        html.P("Sigmalytic continuously scores, interprets, and projects market behavior — surfacing the highest-quality setups before they trigger.",style={"fontSize":"16px","color":TEXT,"lineHeight":"1.7","margin":"0 0 32px","maxWidth":"480px"}),
        html.Div([pill("📡","Live Radar — 35+ symbols"),pill("🎯","Armed / Triggered alerts"),pill("📊","Confluence Engine™"),pill("🔮","Forward Projection Layer™"),pill("🧠","Behavioral Intelligence™"),pill("⚡","60-second scans")],style={"display":"flex","flexWrap":"wrap","gap":"8px","marginBottom":"40px"}),
        html.Div([stat("60s","Scan interval"),html.Div(style={"width":"1px","background":BORDER,"margin":"0 8px"}),stat("5","Score dimensions"),html.Div(style={"width":"1px","background":BORDER,"margin":"0 8px"}),stat("3","Projection paths"),html.Div(style={"width":"1px","background":BORDER,"margin":"0 8px"}),stat("A–F","Grade system")],
                 style={"display":"flex","alignItems":"center","background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}","borderRadius":"16px","padding":"20px 24px","marginBottom":"40px"}),
        html.Div([html.Div("POWERED BY",style={"fontSize":"9px","fontWeight":"800","color":MUTED,"letterSpacing":".3em","textTransform":"uppercase","marginBottom":"10px"}),
                  html.Div([html.Span("Confluence Engine™",style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px","marginRight":"16px"}),html.Span("·",style={"color":MUTED,"marginRight":"16px"}),html.Span("Expansion Node Modeling™",style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px","marginRight":"16px"}),html.Span("·",style={"color":MUTED,"marginRight":"16px"}),html.Span("Forward Projection Layer™",style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px"})])],
                 style={"borderTop":f"1px solid {BORDER}","paddingTop":"20px"}),
    ],style={"flex":"1","minWidth":"0","paddingRight":"60px"})
    form=html.Div([
        html.Div([html.Div("Σ",style={"fontSize":"48px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1"}),html.Div("SIGMALYTIC",style={"fontSize":"20px","fontWeight":"900","color":WHITE,"letterSpacing":".2em","marginTop":"4px"}),html.Div("QUANT CORPORATION",style={"fontSize":"10px","fontWeight":"700","color":MUTED,"letterSpacing":".3em","marginTop":"2px"})],style={"textAlign":"center","marginBottom":"40px"}),
        html.Div(id="login-section",children=[
            html.H2("Sign In",style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
            html.Div([html.Label("Email",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="login-email",type="email",placeholder="you@example.com",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"16px"}),
            html.Div([html.Label("Password",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="login-password",type="password",placeholder="••••••••",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"24px"}),
            html.Div(id="login-error",style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
            html.Button("Sign In",id="login-btn",n_clicks=0,style={"width":"100%","background":TEAL,"color":WHITE,"border":"none","borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700","cursor":"pointer","marginBottom":"8px"}),
            html.Div([html.Span("Forgot your password? ",style={"color":MUTED,"fontSize":"12px"}),html.A("Click here to reset",href=f"{BACKEND_HTTP}/api/auth/reset-form",target="_blank",style={"color":TEAL_DIM,"fontSize":"12px","fontWeight":"700","textDecoration":"underline"})],style={"textAlign":"center","marginBottom":"12px"}),
            html.Div([html.Div(style={"flex":"1","height":"1px","background":BORDER}),html.Span("or",style={"color":MUTED,"fontSize":"12px","padding":"0 12px"}),html.Div(style={"flex":"1","height":"1px","background":BORDER})],style={"display":"flex","alignItems":"center","marginBottom":"16px"}),
            html.Button("🎯 Try Demo — No Sign Up Required",id="demo-btn",n_clicks=0,style={"width":"100%","background":"rgba(45,143,111,.15)","color":TEAL_DIM,"border":f"1px solid {BORDER_T}","borderRadius":"8px","padding":"14px","fontSize":"13px","fontWeight":"700","cursor":"pointer","marginBottom":"24px"}),
            html.Div([html.Span("Don't have an account? ",style={"color":MUTED,"fontSize":"12px"}),html.Button("Sign Up",id="goto-signup-btn",n_clicks=0,style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px","fontWeight":"700","cursor":"pointer","padding":"0"})],style={"textAlign":"center"}),
        ]),
        html.Div(id="signup-section",style={"display":"none"},children=[
            html.H2("Create Account",style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
            html.Div([html.Label("Email",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="signup-email",type="email",placeholder="you@example.com",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"16px"}),
            html.Div([html.Label("Password",style={"fontSize":"11px","fontWeight":"700","color":MUTED,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),dcc.Input(id="signup-password",type="password",placeholder="Min 6 characters",style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px","outline":"none","fontFamily":"DM Sans, sans-serif"})],style={"marginBottom":"24px"}),
            html.Div(id="signup-error",style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
            html.Button("Create Account",id="signup-btn",n_clicks=0,style={"width":"100%","background":TEAL,"color":WHITE,"border":"none","borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700","cursor":"pointer","marginBottom":"24px"}),
            html.Div([html.Span("Already have an account? ",style={"color":MUTED,"fontSize":"12px"}),html.Button("Sign In",id="goto-login-btn",n_clicks=0,style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px","fontWeight":"700","cursor":"pointer","padding":"0"})],style={"textAlign":"center"}),
        ]),
    ],style={"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px","padding":"40px","width":"420px","minWidth":"420px","boxShadow":"0 20px 60px rgba(0,0,0,.4)"})
    return html.Div([html.Div([hero,form],style={"display":"flex","alignItems":"center","justifyContent":"center","minHeight":"100vh","padding":"60px 40px","maxWidth":"1200px","margin":"0 auto"})],style={"background":NAVY,"minHeight":"100vh"})

def build_main_app():
    return html.Div([html.Div([
        html.Div([html.Span("⚡ LIVE · ",style={"fontWeight":"800","color":TEAL_DIM}),html.Span("Confluence Engine v1.0 · Radar Screen · Behavioral Intelligence · Real-Time Decision Layer",style={"color":TEXT}),html.Span(" · Beta",style={"fontWeight":"700","color":YELLOW_DIM})],
                 style={"background":"rgba(45,143,111,.08)","border":f"1px solid {BORDER_T}","borderRadius":"10px","padding":"8px 20px","textAlign":"center","fontSize":"11px","letterSpacing":".04em","marginBottom":"8px"}),
        html.Header([
            html.Div([LOGO,html.Div([html.Div("SIGMALYTIC SYSTEM // DECISION LAYER",style={"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".32em","color":TEAL_DIM}),html.Div(id="sim-label",style={"display":"none"})],style={"textAlign":"center"}),html.Div(style={"width":"120px"})],style={"display":"flex","justifyContent":"space-between","alignItems":"center","width":"100%","marginBottom":"6px"}),
            html.P("Real-time decision intelligence — scores, interprets, and projects market behavior via multi-layer confluence.",style={"fontSize":"12px","color":MUTED,"textAlign":"center","maxWidth":"640px","margin":"0 auto"}),
            html.P("Powered by Confluence Engine · Expansion Node Modeling · Forward Projection Layer",style={"fontSize":"11px","color":"#475569","textAlign":"center","letterSpacing":".06em","marginTop":"4px"}),
            html.Hr(style={"border":"none","height":"1px","background":BORDER,"width":"60%","margin":"12px auto 0"}),
            html.Div([html.H1("Decision Command Center",style={"fontSize":"30px","fontWeight":"900","lineHeight":"1","letterSpacing":"-.02em","color":WHITE}),html.Span(id="b-connected"),html.Span(id="b-feed"),html.Span(id="b-tick")],style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
            html.Div([
                dcc.Input(id="ticker-input",value="AAPL",debounce=False,style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}","borderRadius":"12px","padding":"10px 14px","width":"120px","fontSize":"14px","fontWeight":"700"}),
                html.Button("Load Symbol",id="btn-load",n_clicks=0,style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,"borderRadius":"12px","padding":"10px 18px","fontSize":"13px","fontWeight":"800"}),
                html.Div(id="price-ctrl"),
                html.Div([html.Button(tf,id=f"btn-tf-{tf}",n_clicks=0,style={"background":"transparent","color":TEXT,"border":"none","borderRadius":"10px","padding":"8px 12px","fontSize":"12px","fontWeight":"700"}) for tf in TIMEFRAMES],style={"display":"flex","gap":"2px","padding":"4px","background":NAVY_MID,"border":f"1px solid {BORDER}","borderRadius":"12px"}),
                html.Button("Use Synthetic Feed",id="btn-live",n_clicks=0,style={"display":"none"}),
            ],style={"display":"flex","flexWrap":"wrap","alignItems":"center","justifyContent":"center","gap":"10px"}),
        ],style={"display":"flex","flexDirection":"column","alignItems":"center","gap":"14px","paddingBottom":"4px"}),

        # ── Nav bar ───────────────────────────────────────────────────────
        html.Nav([
            html.Button(label,id=f"tab-{key}",n_clicks=0,style={"background":"transparent","color":TEXT,"border":"none","borderRadius":"10px","padding":"10px 20px","fontSize":"13px","fontWeight":"700","whiteSpace":"nowrap"})
            for key,label in [
                ("command","Command Center"),("feed","Live Feed"),("performance","Performance"),
                ("behavior","Behavioral Intelligence"),("import","Import History"),
                ("radar","Radar Screen"),("scoreboard","Scoreboard"),("billing","Billing"),
                ("setup","Setup"),("admin","🔒 Admin"),    # ← ADMIN TAB
            ]
        ],style={"display":"flex","gap":"4px","padding":"4px","borderRadius":"14px","background":NAVY_MID,"border":f"1px solid {BORDER}","justifyContent":"center","overflowX":"auto"}),

        html.Main(id="main-content"),
    ],style={"maxWidth":"1440px","margin":"0 auto","display":"flex","flexDirection":"column","gap":"16px"})],
    style={"minHeight":"100vh","background":NAVY,"padding":"24px"})

app.layout=html.Div([
    dcc.Store(id="s-session",data=None,storage_type="session"),
    dcc.Store(id="s-live",data=_init_live),dcc.Store(id="s-candles",data=_init_candles),
    dcc.Store(id="s-seq",data=0),dcc.Store(id="s-live-mode",data=True),
    dcc.Store(id="s-symbol",data="AAPL"),dcc.Store(id="s-tf",data="5m"),
    dcc.Store(id="s-tab",data="command"),dcc.Store(id="s-price-text",data="280.15"),
    dcc.Store(id="s-analysis",data={}),dcc.Store(id="s-refresh",data=0),
    dcc.Store(id="s-page",data="login"),dcc.Store(id="s-permissions",data={}),
    dcc.Interval(id="i-synth",interval=1_400,n_intervals=0),
    dcc.Interval(id="i-alpaca",interval=5_000,n_intervals=0),
    dcc.Interval(id="i-clock",interval=1_000,n_intervals=0),
    dcc.Interval(id="i-radar",interval=60_000,n_intervals=0),
    dcc.Interval(id="i-demo-timer",interval=90_000,n_intervals=0,max_intervals=1),
    dcc.Store(id="s-modal-dismissed",data=False),dcc.Store(id="s-show-signup",data=False),
    dcc.Store(id="s-reset-token",data=""),dcc.Store(id="s-radar-filter",data="all"),
    html.Div([
        html.Button(id="login-btn-dummy",n_clicks=0,style={"display":"none"}),
        html.Div(id="login-error-dummy",style={"display":"none"}),
        html.Div(id="forgot-msg-dummy",style={"display":"none"}),
        html.Div(id="reset-error-dummy",style={"display":"none"}),
        html.Button(id="forgot-btn",n_clicks=0,style={"display":"none"}),
        html.Div(id="forgot-msg",children="",style={"display":"none"}),
    ],style={"display":"none"}),

    html.Div(id="conversion-modal",style={"display":"none"},children=html.Div([
        html.Div(style={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,"background":"rgba(0,0,0,.75)","zIndex":8000,"display":"flex","alignItems":"center","justifyContent":"center"},children=[
            html.Div([
                html.Div([html.Div("Σ",style={"fontSize":"32px","fontWeight":"900","color":TEAL_DIM,"marginBottom":"8px"}),html.H2("Enjoying Sigmalytic?",style={"fontSize":"22px","fontWeight":"900","color":WHITE,"margin":"0 0 8px"}),html.P("Create a free account to unlock full access:",style={"fontSize":"13px","color":TEXT,"margin":"0 0 20px","lineHeight":"1.6"})],style={"textAlign":"center"}),
                html.Div([*[html.Div([html.Span("✓ ",style={"color":TEAL_DIM,"fontWeight":"800"}),html.Span(feat,style={"color":WHITE,"fontSize":"13px"})],style={"marginBottom":"8px"}) for feat in ["Save your watchlists across sessions","Receive Armed & Triggered email alerts","Access the Signal Scoreboard","Track your behavioral performance history"]]],style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}","borderRadius":"12px","padding":"16px 20px","marginBottom":"20px"}),
                html.Button("Create Free Account — No Credit Card",id="modal-signup-btn",n_clicks=0,style={"width":"100%","background":TEAL,"color":WHITE,"border":"none","borderRadius":"10px","padding":"14px","fontSize":"14px","fontWeight":"800","cursor":"pointer","marginBottom":"10px"}),
                html.Button("Continue Demo",id="modal-dismiss-btn",n_clicks=0,style={"width":"100%","background":"transparent","color":MUTED,"border":f"1px solid {BORDER}","borderRadius":"10px","padding":"12px","fontSize":"13px","cursor":"pointer"}),
                html.P("Free account · No credit card · Cancel anytime",style={"textAlign":"center","fontSize":"11px","color":MUTED,"marginTop":"12px","marginBottom":"0"}),
            ],style={"background":NAVY_CARD,"border":f"1px solid {BORDER_T}","borderRadius":"20px","padding":"32px","width":"420px","boxShadow":"0 20px 60px rgba(0,0,0,.6)"}),
        ]),
    ])),

    html.Div(id="reset-overlay",children=build_reset_page(),style={"display":"none","position":"fixed","top":0,"left":0,"right":0,"bottom":0,"zIndex":10000,"background":NAVY,"overflowY":"auto"}),
    html.Div(id="auth-overlay",children=build_login_page(),style={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,"zIndex":9999,"background":NAVY,"overflowY":"auto"}),
    html.Div(id="app-container",children=build_main_app()),
])

# ── Callbacks ──────────────────────────────────────────────────────────────────

@app.callback(Output("s-permissions","data"),Input("s-session","data"),prevent_initial_call=True)
def load_permissions(session):
    if not session or not session.get("user_id"): return {}
    import requests as _req
    try:
        r=_req.get(f"{BACKEND_HTTP}/api/v1/permissions/{session['user_id']}",timeout=5)
        if r.ok: return r.json()
    except Exception: pass
    return {}

@app.callback(Output("login-section","style"),Output("signup-section","style"),Input("goto-signup-btn","n_clicks"),Input("goto-login-btn","n_clicks"),prevent_initial_call=True)
def toggle_auth_section(to_signup,to_login):
    ctx=callback_context
    if not ctx.triggered: return no_update,no_update
    trigger=ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger=="goto-signup-btn": return {"display":"none"},{"display":"block"}
    return {"display":"block"},{"display":"none"}

@app.callback(Output("s-session","data"),Output("s-page","data"),
              Input("login-btn","n_clicks"),Input("demo-btn","n_clicks"),Input("signup-btn","n_clicks"),
              State("login-email","value"),State("login-password","value"),State("signup-email","value"),State("signup-password","value"),
              prevent_initial_call=True)
def handle_auth(login_clicks,demo_clicks,signup_clicks,login_email,login_password,signup_email,signup_password):
    ctx=callback_context
    if not ctx.triggered: return no_update,no_update
    trigger=ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger=="demo-btn": return {"user_id":"demo_user_001","email":"demo@sigmalytic.com","is_demo":True},"app"
    if trigger=="login-btn":
        if not login_email or not login_password: return no_update,no_update
        import requests as _req
        try:
            r=_req.get(f"{BACKEND_HTTP}/api/auth/test-login",params={"email":login_email,"password":login_password},timeout=10)
            if r.ok:
                data=r.json()
                if data.get("status")==200:
                    resp=data.get("response",{}); user=resp.get("user",{})
                    return {"user_id":user.get("id",""),"email":user.get("email",""),"access_token":resp.get("access_token",""),"is_demo":False},"app"
                else: return {"login_error":data.get("response",{}).get("msg","Invalid credentials")},no_update
        except Exception as e: return {"login_error":str(e)[:100]},no_update
        return no_update,no_update
    if trigger=="signup-btn":
        if not signup_email or not signup_password: return no_update,no_update
        import requests as _req
        try:
            r=_req.post(f"{SUPABASE_URL}/auth/v1/signup",headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},json={"email":signup_email,"password":signup_password},timeout=10)
            if r.ok:
                data=r.json(); user=data.get("user",{})
                return {"user_id":user.get("id",""),"email":user.get("email",""),"access_token":data.get("access_token",""),"is_demo":False},"app"
        except Exception: pass
        return no_update,no_update
    return no_update,no_update

@app.callback(Output("s-live-mode","data"),Output("btn-live","children"),Output("sim-label","children"),Input("btn-live","n_clicks"),State("s-live-mode","data"),prevent_initial_call=True)
def toggle_live(_,current):
    new=not current
    return new,("Use Synthetic Feed" if new else "Use Live Alpaca Feed"),("LIVE MARKET FEED · ALPACA IEX" if new else "SIMULATION MODE · SYNTHETIC FEED")

@app.callback(Output("s-symbol","data"),Output("ticker-input","value"),Input("btn-load","n_clicks"),State("ticker-input","value"),prevent_initial_call=True)
def load_symbol(_,ticker):
    clean=sanitize_symbol(ticker or "")
    return (clean,clean) if clean else (no_update,no_update)

@app.callback(Output("s-tab","data"),
              Input("tab-command","n_clicks"),Input("tab-feed","n_clicks"),Input("tab-performance","n_clicks"),
              Input("tab-behavior","n_clicks"),Input("tab-import","n_clicks"),Input("tab-radar","n_clicks"),
              Input("tab-scoreboard","n_clicks"),Input("tab-billing","n_clicks"),Input("tab-setup","n_clicks"),
              Input("tab-admin","n_clicks"),    # ← ADMIN TAB INPUT
              prevent_initial_call=True)
def set_tab(*_):
    ctx=callback_context
    if not ctx.triggered: return no_update
    return ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")


@app.callback(Output("s-tf","data"),
              [Input(f"btn-tf-{tf}","n_clicks") for tf in ["1m","5m","15m","1H","1D","1W"]],
              prevent_initial_call=True)
def set_timeframe(*_):
    ctx=callback_context
    if not ctx.triggered: return no_update
    trigger=ctx.triggered[0]["prop_id"].split(".")[0]
    return trigger.replace("btn-tf-","")

@app.callback(Output("s-radar-filter","data"),
              Input("radar-filter-all","n_clicks"),Input("radar-filter-armed","n_clicks"),Input("radar-filter-building","n_clicks"),
              Input("radar-filter-triggered","n_clicks"),Input("radar-filter-long","n_clicks"),Input("radar-filter-short","n_clicks"),
              Input("radar-filter-watching","n_clicks"),Input("radar-filter-avoid","n_clicks"),prevent_initial_call=True)
def set_radar_filter(*_):
    ctx=callback_context
    if not ctx.triggered: return no_update
    return ctx.triggered[0]["prop_id"].split(".")[0].replace("radar-filter-","")

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
            import requests as req; r=req.get(f"{BACKEND_HTTP}/api/stock/{symbol}",timeout=4); r.raise_for_status()
            data=r.json(); price=float(data["price"]); volume=int(data.get("volume",0))
        except: return no_update,no_update,no_update
    elif not live_mode and trigger=="i-synth":
        prev=current["price"] if current else float(price_text or 280.15)
        price=round(max(1.0,prev+(random.random()-0.45)*1.25),2); volume=round(500_000+random.random()*5_000_000)
    else: return no_update,no_update,no_update
    new_seq=(seq or 0)+1; new_live=create_live_update(symbol,price,volume,new_seq).to_dict()
    if candles:
        prior=candles[-1]; new_c={"o":prior["c"],"h":round(max(prior["c"],price)+0.12,2),"l":round(min(prior["c"],price)-0.12,2),"c":price,"t":str(new_seq)}
        new_candles=candles[-49:]+[new_c]
    else: new_candles=_init_candles
    return new_live,new_seq,new_candles

@app.callback(Output("price-ctrl","children"),Input("s-live-mode","data"),Input("s-live","data"),State("s-price-text","data"))
def render_price_ctrl(live_mode,live,price_text):
    if live_mode:
        price=live["price"] if live else 0
        return html.Div([html.Span("Live Price",style={"fontSize":"10px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),html.Strong(f"${price:.2f}",style={"fontSize":"17px","color":TEAL_DIM,"fontWeight":"900"})],
                        style={"background":NAVY_MID,"border":f"1px solid {BORDER_T}","borderRadius":"12px","padding":"8px 14px","width":"130px","minHeight":"50px","display":"flex","flexDirection":"column","justifyContent":"center"})
    return dcc.Input(id={"type":"price-in","index":"0"},value=price_text or "280.15",debounce=True,style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}","borderRadius":"12px","padding":"10px 14px","width":"120px","fontSize":"14px"})

@app.callback(Output("b-connected","children"),Output("b-feed","children"),Output("b-tick","children"),Input("s-live","data"),Input("s-live-mode","data"))
def update_badges(live,live_mode):
    seq=live["sequence"] if live else 0
    return badge("LIVE" if live_mode else "SIM","teal" if live_mode else "gray"),badge("Alpaca IEX" if live_mode else "Synthetic Feed","blue"),badge(f"Tick #{seq}","yellow")

@app.callback(Output("main-content","children"),
              Input("s-live","data"),Input("s-candles","data"),Input("s-tab","data"),Input("s-live-mode","data"),
              Input("i-clock","n_intervals"),Input("i-radar","n_intervals"),
              Input("s-analysis","data"),Input("s-refresh","data"),Input("s-permissions","data"),Input("s-radar-filter","data"),
              State("s-session","data"),State("s-symbol","data"),State("s-tf","data"))
def render_main(live,candles,tab,live_mode,_clock,_radar,analysis,_refresh,perms,radar_filter,session,symbol,tf):
    if not live: return html.Div("Initializing…",style={"color":MUTED,"padding":"60px","textAlign":"center"})
    ctx=callback_context
    trigger=ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""
    if tab in ("behavior","import","billing","setup","performance","feed","radar","scoreboard","admin") and trigger=="i-clock": return no_update
    if tab!="radar" and trigger=="i-radar": return no_update
    if tab=="command":     return build_command_tab(live,candles or _init_candles,symbol,tf)
    if tab=="feed":        return build_feed_tab(live,live_mode)
    if tab=="performance": return build_performance_tab(live)
    if tab=="behavior":    return build_behavior_tab(analysis or {},perms or {},session)
    if tab=="import":      return build_import_tab()
    if tab=="radar":       return build_radar_tab(status_filter=radar_filter)
    if tab=="scoreboard":
        if session and session.get("is_demo"):
            return card([html.Div([html.Div("📋",style={"fontSize":"48px","marginBottom":"16px"}),html.H2("Signal Scoreboard",style={"fontSize":"20px","fontWeight":"900","color":WHITE,"marginBottom":"8px"}),html.P("Create a free account to access the Signal Scoreboard.",style={"fontSize":"14px","color":TEXT,"marginBottom":"24px","lineHeight":"1.7","maxWidth":"400px"}),html.A("Create Free Account",href="/",style={"background":TEAL,"color":WHITE,"border":"none","borderRadius":"10px","padding":"14px 28px","fontSize":"14px","fontWeight":"800","cursor":"pointer","textDecoration":"none","display":"inline-block"})],style={"textAlign":"center","padding":"60px 20px"})])
        return build_scoreboard_tab()
    if tab=="billing":     return build_billing_tab(session,perms or {})
    if tab=="setup":       return build_setup_tab()
    if tab=="admin":       return build_admin_tab(session or {},BACKEND_HTTP)   # ← ADMIN RENDER
    return html.Div("Unknown tab")

@app.callback(Output("clock-body","children"),Input("i-clock","n_intervals"))
def update_clock(_):
    try:
        import zoneinfo
        et = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    except Exception:
        from datetime import timezone, timedelta
        et = datetime.now(timezone(timedelta(hours=-4)))  # EDT fallback
    minutes=et.hour*60+et.minute; in_sess=570<=minutes<=960
    phase="Outside RTH" if not in_sess else ("Opening Drive" if minutes<630 else ("Midday Auction" if minutes<840 else "Closing Auction"))
    return html.Div([metric_tile("Clock",et.strftime("%I:%M:%S %p")+" ET"),html.Div(style={"height":"8px"}),metric_tile("Session Phase",phase,TEAL_DIM if in_sess else MUTED),html.Div(style={"height":"10px"}),note_box("Future: economic releases, auction windows, proprietary cycle layers.")])

@app.callback(Output("csv-upload-behavior-status","children"),Output("s-analysis","data"),Output("s-refresh","data"),
              Input("csv-upload-behavior","contents"),State("csv-upload-behavior","filename"),State("s-refresh","data"),State("s-session","data"),prevent_initial_call=True)
def handle_csv_upload_behavior(contents,filename,refresh,session):
    if not contents: return no_update,no_update,no_update
    import base64,io as _io,requests as _req
    uid=_user_id(session); headers=_auth_headers(session)
    try:
        content_type,content_string=contents.split(","); decoded=base64.b64decode(content_string)
        resp=_req.post(f"{BACKEND_HTTP}/api/import/upload-generic",files={"file":(filename,_io.BytesIO(decoded),"text/csv")},data={"symbol_col":"symbol","side_col":"action","qty_col":"qty","price_col":"price","timestamp_col":"date"},headers=headers,timeout=30)
        if not resp.ok: return html.Span(f"❌ Backend error {resp.status_code}: {resp.text[:300]}",style={"color":RED_DIM}),no_update,no_update
        data=resp.json(); trades_count=data.get("trades_closed",0)
        if trades_count==0: return html.Span(f"⚠️ 0 trades reconstructed. Rows: {data.get('raw_rows',0)}.",style={"color":YELLOW_DIM}),no_update,no_update
        try:
            r2=_req.get(f"{BACKEND_HTTP}/api/import/analysis/{uid}",headers=headers,timeout=10)
            cumulative=r2.json() if r2.ok and r2.json() else data.get("analysis",{})
        except Exception: cumulative=data.get("analysis",{})
        return html.Div([html.Span("✅ Import successful · ",style={"color":TEAL_DIM,"fontWeight":"800"}),html.Span(f"{trades_count} trades · Win rate: {cumulative.get('win_rate',0)}% · P&L: ${cumulative.get('total_pnl',0):+,.2f}",style={"color":TEXT})]),cumulative,(refresh or 0)+1
    except Exception as e: return html.Span(f"❌ Error: {str(e)[:300]}",style={"color":RED_DIM}),no_update,no_update

@app.callback(Output("csv-upload-status","children"),Input("csv-upload","contents"),State("csv-upload","filename"),State("s-session","data"),prevent_initial_call=True)
def handle_csv_upload(contents,filename,session):
    if not contents: return no_update
    import base64,io as _io,requests as _req; headers=_auth_headers(session)
    try:
        content_type,content_string=contents.split(","); decoded=base64.b64decode(content_string)
        resp=_req.post(f"{BACKEND_HTTP}/api/import/upload-generic",files={"file":(filename,_io.BytesIO(decoded),"text/csv")},data={"symbol_col":"symbol","side_col":"action","qty_col":"qty","price_col":"price","timestamp_col":"date"},headers=headers,timeout=30)
        if not resp.ok: return html.Span(f"❌ Upload failed ({resp.status_code}): {resp.text[:300]}",style={"color":RED_DIM})
        data=resp.json(); trades_count=data.get("trades_closed",0); analysis=data.get("analysis",{})
        if trades_count==0: return html.Span("⚠️ 0 trades reconstructed. Check CSV format.",style={"color":YELLOW_DIM})
        return html.Div([html.Span("✅ Import successful · ",style={"color":TEAL_DIM,"fontWeight":"800"}),html.Span(f"{trades_count} trades · Win rate: {analysis.get('win_rate',0)}% · P&L: ${analysis.get('total_pnl',0):+,.2f}",style={"color":TEXT})])
    except Exception as e: return html.Span(f"❌ Error: {str(e)[:300]}",style={"color":RED_DIM})

@app.callback(Output("reset-trades-output","children"),Input("reset-trades-btn","n_clicks"),prevent_initial_call=True)
def reset_trade_history(n_clicks):
    if not n_clicks: return ""
    import requests as _req
    try:
        r=_req.delete(f"{BACKEND_HTTP}/api/trades/reset",timeout=10)
        if r.status_code==200: return html.Span("✅ Trade history cleared.",style={"color":"#00ff88"})
        return html.Span(f"❌ Reset failed (status {r.status_code}).",style={"color":"#ff4444"})
    except Exception as e: return html.Span(f"❌ Error: {str(e)}",style={"color":"#ff4444"})

@app.callback(Output("login-error","children"),Input("s-session","data"),prevent_initial_call=True)
def show_login_error(session):
    if session and session.get("login_error"): return session["login_error"]
    return ""

app.clientside_callback(
    """function(n) {
        var token = sessionStorage.getItem('supabase_recovery_token');
        if (token) { return [{"display":"block","position":"fixed","top":"0","left":"0","right":"0","bottom":"0","zIndex":"10000","background":"#0d1b2e","overflowY":"auto"}, token]; }
        return [{"display":"none"}, ""];
    }""",
    Output("reset-overlay","style"),Output("s-reset-token","data"),Input("i-clock","n_intervals"))

@app.callback(Output("reset-error","children"),Input("reset-submit-btn","n_clicks"),State("reset-password-input","value"),State("reset-password-confirm","value"),State("s-reset-token","data"),prevent_initial_call=True)
def submit_reset(n_clicks,password,confirm,token):
    if not n_clicks: return ""
    if not password or len(password)<6: return "Password must be at least 6 characters."
    if password!=confirm: return "Passwords do not match."
    if not token: return "Reset token missing."
    import requests as _req
    try:
        r=_req.put(f"{SUPABASE_URL}/auth/v1/user",headers={"apikey":SUPABASE_ANON_KEY,"Authorization":f"Bearer {token}","Content-Type":"application/json"},json={"password":password},timeout=10)
        if r.status_code==200: return "✅ Password updated successfully. You can now sign in."
        return f"Error: {r.text[:200]}"
    except Exception as e: return f"Error: {str(e)[:200]}"

@app.callback(Output("forgot-msg","children"),Output("forgot-msg","style"),Input("forgot-btn","n_clicks"),State("login-email","value"),prevent_initial_call=True)
def forgot_password(n_clicks,email):
    if not n_clicks: return "",{}
    if not email: return "Enter your email above first.",{"fontSize":"12px","color":RED_DIM,"textAlign":"center"}
    import requests as _req
    try:
        r=_req.post(f"{BACKEND_HTTP}/api/auth/reset-password",json={"email":email},timeout=10)
        data=r.json()
        if data.get("ok"): return f"✅ Reset email sent to {email}.",{"fontSize":"12px","color":TEAL_DIM,"textAlign":"center"}
        return "Something went wrong.",{"fontSize":"12px","color":RED_DIM,"textAlign":"center"}
    except Exception as e: return f"Error: {str(e)[:100]}",{"fontSize":"12px","color":RED_DIM,"textAlign":"center"}

@app.callback(Output("s-show-signup","data"),Input("modal-signup-btn","n_clicks"),prevent_initial_call=True)
def trigger_signup(*_): return True

@app.callback(Output("auth-overlay","style"),Input("s-session","data"),Input("s-show-signup","data"))
def show_overlay(session,show_signup):
    overlay={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,"zIndex":9999,"background":NAVY,"overflowY":"auto"}
    if show_signup: return overlay
    if session and session.get("login_error"): return overlay
    if session and session.get("user_id"): return {"display":"none"}
    return overlay

@app.callback(Output("conversion-modal","style"),Output("s-modal-dismissed","data"),
              Input("i-demo-timer","n_intervals"),Input("modal-dismiss-btn","n_clicks"),Input("s-session","data"),State("s-modal-dismissed","data"),prevent_initial_call=True)
def handle_conversion_modal(timer_fired,dismiss_clicks,session,dismissed):
    ctx=callback_context
    if not ctx.triggered: return {"display":"none"},dismissed
    trigger=ctx.triggered[0]["prop_id"].split(".")[0]
    if session and not session.get("is_demo"): return {"display":"none"},True
    if trigger=="modal-dismiss-btn" and dismiss_clicks: return {"display":"none"},True
    if trigger=="i-demo-timer" and not dismissed:
        if session and session.get("is_demo"): return {"display":"block"},dismissed
    return {"display":"none"},dismissed

register_billing_callbacks(app)

if __name__=="__main__":
    app.run(debug=False,host="0.0.0.0",port=8050)
