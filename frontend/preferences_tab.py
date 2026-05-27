"""
preferences_tab.py — Sigmalytic Quant
Minimal working version. Stores in app.py root (localStorage).
NO store inputs in callbacks - only button clicks trigger updates.
"""

from __future__ import annotations
import os
import requests
from dash import dcc, html, Input, Output, State, no_update, callback_context

BACKEND_HTTP = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")

NAVY_CARD="#111f35"; TEAL="#2d8f6f"; TEAL_DIM="#34d399"
TEAL_GLOW="rgba(45,143,111,.18)"; RED_DIM="#f87171"; YELLOW_DIM="#fde68a"
MUTED="#64748b"; TEXT="#94a3b8"; WHITE="#f1f5f9"
BORDER="rgba(255,255,255,.08)"; BORDER_T="rgba(45,143,111,.35)"

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
            "fontWeight":"700","padding":"8px 16px","cursor":"pointer","transition":"all .15s"}

def _off():
    return {"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"8px",
            "color":TEXT,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
            "fontWeight":"700","padding":"8px 16px","cursor":"pointer","transition":"all .15s"}


def build_preferences_tab(user_id="", mode="realtime", types=None, hours=True, min_score=60, watchlist=None):
    types = types or {"wyckoff":True,"gann":True,"ab_score":True,"elliott":False,"fibonacci":False}
    watchlist = watchlist or []
    return html.Div([
        html.Div([
            html.H2("Alert Preferences", style={"color":WHITE,"fontSize":"22px","fontWeight":"800","marginBottom":"4px"}),
            html.P("Control which alerts you receive and how often.", style={"color":TEXT,"fontSize":"13px"}),
            html.Span(user_id, id="prefs-user-id", style={"display":"none"}),
        ], style={"marginBottom":"24px"}),

        _card([_stitle("📬 Delivery Mode"), _label("How often do you want alerts?"),
            html.Div([
                html.Button("Real-time",     id="pref-mode-realtime", n_clicks=0, style=_on() if mode=="realtime" else _off()),
                html.Button("Hourly Digest", id="pref-mode-hourly",   n_clicks=0, style=_on() if mode=="hourly"   else _off()),
                html.Button("Daily Summary", id="pref-mode-daily",    n_clicks=0, style=_on() if mode=="daily"    else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        _card([_stitle("🎯 Minimum Confluence Score"), _label("Only alert when score is at least:"),
            dcc.Slider(id="prefs-min-score", min=0, max=100, step=5, value=min_score,
                marks={0:"0",25:"25",50:"50",75:"75",100:"100"},
                tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height":"8px"}),
            html.Div("Higher score = fewer, higher-quality alerts", style={"color":MUTED,"fontSize":"11px"})]),

        _card([_stitle("⚡ Alert Types"), _label("Select any combination — or activate all:"),
            html.Div([
                html.Button("✓ All",            id="pref-type-all",      n_clicks=0, style=_off()),
                html.Button("✗ None",           id="pref-type-none",     n_clicks=0, style=_off()),
                html.Button("Structure Alerts", id="pref-type-wyckoff",  n_clicks=0, style=_on() if types.get("wyckoff")   else _off()),
                html.Button("Vector Alerts",    id="pref-type-gann",     n_clicks=0, style=_on() if types.get("gann")      else _off()),
                html.Button("Score Alerts",     id="pref-type-ab_score", n_clicks=0, style=_on() if types.get("ab_score")  else _off()),
                html.Button("Cycle Alerts",     id="pref-type-elliott",  n_clicks=0, style=_on() if types.get("elliott")   else _off()),
                html.Button("Level Alerts",     id="pref-type-fibonacci",n_clicks=0, style=_on() if types.get("fibonacci") else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        _card([_stitle("📋 Watchlist"), _label("Only alert on these symbols (leave empty for all 1,403)"),
            html.Div([
                dcc.Input(id="prefs-symbol-input", type="text", placeholder="e.g. AAPL", maxLength=5,
                    style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}","borderRadius":"8px",
                           "color":WHITE,"fontFamily":"DM Mono, monospace","fontSize":"13px",
                           "padding":"10px 14px","width":"160px","marginRight":"10px","textTransform":"uppercase"}),
                html.Button("Add Symbol", id="prefs-add-symbol", n_clicks=0,
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","borderRadius":"8px",
                           "color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                           "fontWeight":"700","padding":"10px 18px","cursor":"pointer"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.Div(id="prefs-watchlist-display", children=_render_watchlist(watchlist))]),

        _card([_stitle("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only", style={"color":WHITE,"fontSize":"13px","fontWeight":"600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET", style={"color":MUTED,"fontSize":"11px","marginTop":"2px"}),
                ], style={"flex":"1"}),
                html.Button("ON" if hours else "OFF", id="pref-hours-btn", n_clicks=0,
                            style=_on() if hours else _off()),
            ], style={"display":"flex","alignItems":"center","gap":"16px"})]),

        # Hurst Cycle Profile
        _card([
            _stitle("🔄 Hurst Cycle Profile"),
            _label("Lookback horizon for cycle timing analysis"),
            dcc.RadioItems(
                id="prefs-hurst-profile",
                options=[
                    {"label": "Short-Term (90 days — scalping/swing)", "value": "SHORT"},
                    {"label": "Medium-Term (1 year — standard)", "value": "MEDIUM"},
                    {"label": "Long-Term (3 years — macro)", "value": "LONG"},
                ],
                value="MEDIUM",
                labelStyle={"display":"block","marginBottom":"6px","color":TEXT,"fontSize":"13px"},
            ),
        ]),

        # Weis Wave Sensitivity
        _card([
            _stitle("〰️ Weis Wave Sensitivity"),
            _label("Reversal threshold — lower = more sensitive, higher = fewer signals"),
            dcc.Slider(
                id="prefs-weis-threshold",
                min=0.1, max=3.0, step=0.1, value=0.5,
                marks={0.1:"0.1%", 0.5:"0.5%", 1.0:"1.0%", 2.0:"2.0%", 3.0:"3.0%"},
                tooltip={"placement":"bottom","always_visible":True},
            ),
            html.Div(style={"height":"8px"}),
            html.Div([
                html.Span("Timeframe defaults: ", style={"color":MUTED,"fontSize":"11px"}),
                html.Span("1m=0.2% · 5m=0.5% · 15m=0.75% · 1H=1.0% · 1D=1.5% · 1W=2.5%",
                          style={"color":MUTED,"fontSize":"11px"}),
            ]),
        ]),

        html.Button("Save Preferences", id="prefs-save-btn", n_clicks=0, style={
            "width":"100%","background":TEAL,"border":"none","borderRadius":"12px","color":WHITE,
            "fontFamily":"DM Sans, sans-serif","fontSize":"14px","fontWeight":"800",
            "padding":"16px","cursor":"pointer","letterSpacing":".05em","marginBottom":"12px"}),
        html.Div(id="prefs-status-msg", style={"textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px"}),

    ], style={"maxWidth":"600px","margin":"0 auto","padding":"24px 16px"})


def register_preferences_callbacks(app):

    @app.callback(
        Output("pref-mode-val","data"),
        Output("pref-types-val","data"),
        Output("pref-hours-val","data"),
        Output("prefs-min-score-val","data"),
        Output("prefs-watchlist","data"),
        Input("s-tab","data"),
        State("s-session","data"),
        prevent_initial_call=True,
    )
    def load_preferences(tab, session):
        """Load saved preferences from backend when preferences tab opens."""
        if tab != "preferences":
            return no_update, no_update, no_update, no_update, no_update
        uid = (session or {}).get("user_id","")
        if not uid:
            return no_update, no_update, no_update, no_update, no_update
        try:
            r = requests.get(f"{BACKEND_HTTP}/api/preferences/{uid}", timeout=5)
            if not r.ok:
                return no_update, no_update, no_update, no_update, no_update
            p = r.json()
            mode  = p.get("delivery_mode", "realtime")
            types = p.get("alert_types", {"wyckoff":True,"gann":True,"ab_score":True,"elliott":False,"fibonacci":False})
            hours = p.get("market_hours_only", True)
            score = p.get("min_score", 60)
            wl    = p.get("watchlist", [])
            if isinstance(types, list):
                all_types = ["wyckoff","gann","ab_score","elliott","fibonacci"]
                types = {k: (k in types) for k in all_types}
            return mode, types, hours, score, wl
        except Exception:
            return no_update, no_update, no_update, no_update, no_update


    @app.callback(
        Output("pref-mode-val","data"),
        Output("pref-mode-realtime","style"), Output("pref-mode-hourly","style"), Output("pref-mode-daily","style"),
        Input("pref-mode-realtime","n_clicks"), Input("pref-mode-hourly","n_clicks"), Input("pref-mode-daily","n_clicks"),
        State("pref-mode-val","data"), prevent_initial_call=True,
    )
    def set_mode(r,h,d,cur):
        ctx=callback_context
        if not ctx.triggered: return no_update,no_update,no_update,no_update
        t=ctx.triggered[0]["prop_id"].split(".")[0]
        m={"pref-mode-realtime":"realtime","pref-mode-hourly":"hourly","pref-mode-daily":"daily"}.get(t,cur)
        return m,*[_on() if x==m else _off() for x in ["realtime","hourly","daily"]]

    @app.callback(
        Output("pref-types-val","data"),
        Output("pref-type-wyckoff","style"), Output("pref-type-gann","style"),
        Output("pref-type-ab_score","style"), Output("pref-type-elliott","style"), Output("pref-type-fibonacci","style"),
        Input("pref-type-wyckoff","n_clicks"), Input("pref-type-gann","n_clicks"),
        Input("pref-type-ab_score","n_clicks"), Input("pref-type-elliott","n_clicks"),
        Input("pref-type-fibonacci","n_clicks"), Input("pref-type-all","n_clicks"), Input("pref-type-none","n_clicks"),
        State("pref-types-val","data"), prevent_initial_call=True,
    )
    def set_types(nw,ng,na,ne,nf,n_all,n_none,types):
        ctx=callback_context
        if not ctx.triggered: return (no_update,)*6
        t=ctx.triggered[0]["prop_id"].split(".")[0]
        types=dict(types)
        if t=="pref-type-all": types={k:True for k in types}
        elif t=="pref-type-none": types={k:False for k in types}
        else:
            km={"pref-type-wyckoff":"wyckoff","pref-type-gann":"gann","pref-type-ab_score":"ab_score",
                "pref-type-elliott":"elliott","pref-type-fibonacci":"fibonacci"}
            if t in km: types[km[t]]=not types.get(km[t],False)
        return types,*[_on() if types.get(k) else _off() for k in ["wyckoff","gann","ab_score","elliott","fibonacci"]]

    @app.callback(
        Output("pref-hours-val","data"), Output("pref-hours-btn","children"), Output("pref-hours-btn","style"),
        Input("pref-hours-btn","n_clicks"), State("pref-hours-val","data"), prevent_initial_call=True,
    )
    def toggle_hours(n,cur):
        new=not cur
        return new,("ON" if new else "OFF"),(_on() if new else _off())

    @app.callback(
        Output("prefs-min-score-val","data"),
        Input("prefs-min-score","value"), prevent_initial_call=True,
    )
    def save_score(v): return v

    @app.callback(
        Output("prefs-watchlist","data"), Output("prefs-watchlist-display","children"), Output("prefs-symbol-input","value"),
        Input("prefs-add-symbol","n_clicks"), State("prefs-symbol-input","value"), State("prefs-watchlist","data"),
        prevent_initial_call=True,
    )
    def add_symbol(n,sym,wl):
        if not sym: return wl,_render_watchlist(wl),""
        s=sym.strip().upper()
        if s and s not in wl: wl=wl+[s]
        return wl,_render_watchlist(wl),""

    @app.callback(
        Output("prefs-status-msg","children"), Output("prefs-status-msg","style"),
        Input("prefs-save-btn","n_clicks"),
        State("prefs-user-id","children"), State("pref-mode-val","data"), State("prefs-min-score-val","data"),
        State("pref-hours-val","data"), State("prefs-watchlist","data"), State("pref-types-val","data"),
        State("s-session","data"),
        prevent_initial_call=True,
    )
    def save_prefs(n,uid,mode,score,hours,wl,types,session):
        hurst_profile="MEDIUM"; weis_thresh=0.5
        if not uid and session: uid=session.get("user_id","")
        email=(session or {}).get("email","")
        if not uid: return "⚠️ No user ID — please log in first.",_msg("yellow")
        payload={"delivery_mode":mode or "realtime","min_score":score or 60,
                 "alert_types":{k:bool(v) for k,v in (types or {}).items()},
                 "watchlist":wl or [],"market_hours_only":bool(hours),"weis_threshold":weis_thresh or 0.5}
        try:
            url=f"{BACKEND_HTTP}/api/preferences/{uid}"
            r=requests.patch(url,json=payload,timeout=8)
            if r.status_code==404: r=requests.post(url,json={**payload,"user_id":uid,"email":email},timeout=8)
            if r.ok: return "✅ Preferences saved!",_msg("teal")
            return f"❌ {r.json().get('detail','Save failed')}",_msg("red")
        except Exception as e: return f"❌ {str(e)}",_msg("red")


def _render_watchlist(wl):
    if not wl:
        return [html.Span("All symbols — no filter applied",style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]
    return [html.Span([s,html.Span(" ×",style={"color":RED_DIM,"cursor":"pointer","marginLeft":"4px"})],
            style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"6px",
                   "color":WHITE,"fontSize":"12px","padding":"4px 10px","marginRight":"6px",
                   "marginBottom":"6px","display":"inline-block"}) for s in wl]

def _msg(c="teal"):
    return {"textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px",
            "color":{"teal":TEAL_DIM,"red":RED_DIM,"yellow":YELLOW_DIM}.get(c,WHITE)}
