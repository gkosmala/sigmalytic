"""
preferences_tab.py — Sigmalytic Quant
Instant-save approach: every button click saves to backend immediately.
No store dependencies, no style callback conflicts.
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

def _msg_style(c="teal"):
    return {"textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px",
            "color":{"teal":TEAL_DIM,"red":RED_DIM,"yellow":YELLOW_DIM}.get(c,WHITE)}

def _save(uid, email, payload):
    """Save preferences to backend. Returns (message, color)."""
    try:
        url = f"{BACKEND_HTTP}/api/preferences/{uid}"
        r = requests.patch(url, json=payload, timeout=8)
        if r.status_code == 404:
            r = requests.post(url, json={**payload, "user_id": uid, "email": email}, timeout=8)
        if r.ok:
            return "✅ Saved", "teal"
        return f"❌ {r.json().get('detail','Save failed')}", "red"
    except Exception as e:
        return f"❌ {str(e)}", "red"

def _render_watchlist(wl):
    if not wl:
        return [html.Span("All symbols — no filter applied",
                          style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]
    return [html.Span([s, html.Span(" ×", style={"color":RED_DIM,"cursor":"pointer","marginLeft":"4px"})],
            style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"6px",
                   "color":WHITE,"fontSize":"12px","padding":"4px 10px","marginRight":"6px",
                   "marginBottom":"6px","display":"inline-block"}) for s in wl]


def build_preferences_tab(user_id="", session=None):
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
            r = requests.get(f"{BACKEND_HTTP}/api/preferences/{user_id}", timeout=4)
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
