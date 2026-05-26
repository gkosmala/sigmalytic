"""
preferences_tab.py — Sigmalytic Quant
Uses native Dash RadioItems/Checklist with inline styles only.
No html.Style, no external CSS dependencies.
"""

from __future__ import annotations
import os
import requests
from dash import dcc, html, Input, Output, State, no_update

BACKEND_HTTP = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")

NAVY_CARD = "#111f35"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"
YELLOW_DIM= "#fde68a"
MUTED     = "#64748b"
TEXT      = "#94a3b8"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
BORDER_T  = "rgba(45,143,111,.35)"

def _card(children):
    return html.Section(children, style={
        "background": NAVY_CARD, "border": f"1px solid {BORDER}",
        "borderRadius": "20px", "padding": "20px",
        "boxShadow": "0 8px 32px rgba(0,0,0,.32)", "marginBottom": "16px"
    })

def _label(text):
    return html.Div(text, style={
        "color": MUTED, "fontSize": "10px", "fontWeight": "800",
        "textTransform": "uppercase", "letterSpacing": ".28em", "marginBottom": "10px"
    })

def _section_title(text):
    return html.Div(text, style={
        "color": TEAL_DIM, "fontSize": "11px", "fontWeight": "800",
        "textTransform": "uppercase", "letterSpacing": ".15em",
        "marginBottom": "16px", "paddingBottom": "10px",
        "borderBottom": f"1px solid {BORDER}"
    })

def build_preferences_tab(user_id: str = "") -> html.Div:
    return html.Div([
        dcc.Store(id="prefs-user-id",   data=user_id, storage_type="local"),
        dcc.Store(id="prefs-watchlist", data=[], storage_type="local"),

        # Header
        html.Div([
            html.H2("Alert Preferences", style={
                "color": WHITE, "fontSize": "22px", "fontWeight": "800", "marginBottom": "4px"
            }),
            html.P("Control which alerts you receive and how often.",
                   style={"color": TEXT, "fontSize": "13px"}),
        ], style={"marginBottom": "24px"}),

        # Delivery Mode
        _card([
            _section_title("📬 Delivery Mode"),
            _label("How often do you want alerts?"),
            html.Div([
                html.Button("Real-time",     id="pref-mode-realtime", n_clicks=0,
                            style=_active_btn()),
                html.Button("Hourly Digest", id="pref-mode-hourly",   n_clicks=0,
                            style=_inactive_btn()),
                html.Button("Daily Summary", id="pref-mode-daily",    n_clicks=0,
                            style=_inactive_btn()),
                dcc.Store(id="pref-mode-val", data="realtime", storage_type="local"),
            ], style={"display": "flex", "flexWrap": "wrap", "gap": "8px"}),
        ]),

        # Min Score
        _card([
            _section_title("🎯 Minimum Confluence Score"),
            _label("Only alert when score is at least:"),
            dcc.Slider(
                id="prefs-min-score", min=0, max=100, step=5, value=60,
                marks={0:"0", 25:"25", 50:"50", 75:"75", 100:"100"},
                tooltip={"placement":"bottom","always_visible":True},
            ),
            html.Div(style={"height":"8px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color": MUTED, "fontSize": "11px"}),
        ]),

        # Alert Types
        _card([
            _section_title("⚡ Alert Types"),
            _label("Select any combination — or activate all:"),
            html.Div([
                html.Button("✓ All",            id="pref-type-all",      n_clicks=0, style=_inactive_btn()),
                html.Button("✗ None",           id="pref-type-none",     n_clicks=0, style=_inactive_btn()),
                html.Button("Structure Alerts", id="pref-type-wyckoff",  n_clicks=0, style=_active_btn()),
                html.Button("Vector Alerts",    id="pref-type-gann",     n_clicks=0, style=_active_btn()),
                html.Button("Score Alerts",     id="pref-type-ab_score", n_clicks=0, style=_active_btn()),
                html.Button("Cycle Alerts",     id="pref-type-elliott",  n_clicks=0, style=_inactive_btn()),
                html.Button("Level Alerts",     id="pref-type-fibonacci",n_clicks=0, style=_inactive_btn()),
                dcc.Store(id="pref-types-val", data={
                    "wyckoff":True,"gann":True,"ab_score":True,
                    "elliott":False,"fibonacci":False
                }, storage_type="local"),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"}),
        ]),

        # Watchlist
        _card([
            _section_title("📋 Watchlist"),
            _label("Only alert on these symbols (leave empty for all 1,403)"),
            html.Div([
                dcc.Input(id="prefs-symbol-input", type="text",
                          placeholder="e.g. AAPL", maxLength=5,
                          style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                 "borderRadius":"8px","color":WHITE,
                                 "fontFamily":"DM Mono, monospace","fontSize":"13px",
                                 "padding":"10px 14px","width":"160px","marginRight":"10px",
                                 "textTransform":"uppercase"}),
                html.Button("Add Symbol", id="prefs-add-symbol", n_clicks=0,
                            style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                                   "borderRadius":"8px","color":TEAL_DIM,
                                   "fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                                   "fontWeight":"700","padding":"10px 18px","cursor":"pointer"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.Div(id="prefs-watchlist-display",
                     children=[html.Span("All symbols — no filter applied",
                                         style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]),
        ]),

        # Market Hours
        _card([
            _section_title("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only",
                             style={"color":WHITE,"fontSize":"13px","fontWeight":"600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color":MUTED,"fontSize":"11px","marginTop":"2px"}),
                ], style={"flex":"1"}),
                html.Button("ON", id="pref-hours-btn", n_clicks=0, style=_active_btn()),
                dcc.Store(id="pref-hours-val", data=True, storage_type="local"),
            ], style={"display":"flex","alignItems":"center","gap":"16px"}),
        ]),

        # Save
        html.Button("Save Preferences", id="prefs-save-btn", n_clicks=0, style={
            "width":"100%","background":TEAL,"border":"none","borderRadius":"12px",
            "color":WHITE,"fontFamily":"DM Sans, sans-serif","fontSize":"14px",
            "fontWeight":"800","padding":"16px","cursor":"pointer",
            "letterSpacing":".05em","marginBottom":"12px",
        }),
        html.Div(id="prefs-status-msg", style={
            "textAlign":"center","fontSize":"13px",
            "minHeight":"20px","marginBottom":"24px",
        }),

    ], style={"maxWidth":"600px","margin":"0 auto","padding":"24px 16px"})


def _active_btn():
    return {"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
            "borderRadius":"8px","color":TEAL_DIM,
            "fontFamily":"DM Sans, sans-serif","fontSize":"12px","fontWeight":"700",
            "padding":"8px 16px","cursor":"pointer","transition":"all .15s"}

def _inactive_btn():
    return {"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
            "borderRadius":"8px","color":TEXT,
            "fontFamily":"DM Sans, sans-serif","fontSize":"12px","fontWeight":"700",
            "padding":"8px 16px","cursor":"pointer","transition":"all .15s"}


def register_preferences_callbacks(app):

    # ── Delivery mode ──────────────────────────────────────────────────────────
    @app.callback(
        Output("pref-mode-val",       "data"),
        Output("pref-mode-realtime",  "style"),
        Output("pref-mode-hourly",    "style"),
        Output("pref-mode-daily",     "style"),
        Input("pref-mode-realtime",   "n_clicks"),
        Input("pref-mode-hourly",     "n_clicks"),
        Input("pref-mode-daily",      "n_clicks"),
        State("pref-mode-val",        "data"),
        prevent_initial_call=True,
    )
    def set_mode(r, h, d, current):
        from dash import callback_context
        ctx = callback_context
        if not ctx.triggered: return no_update, no_update, no_update, no_update
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        m = {"pref-mode-realtime":"realtime","pref-mode-hourly":"hourly","pref-mode-daily":"daily"}.get(t, current)
        styles = [_active_btn() if x==m else _inactive_btn() for x in ["realtime","hourly","daily"]]
        return m, styles[0], styles[1], styles[2]

    # ── Alert types ────────────────────────────────────────────────────────────
    @app.callback(
        Output("pref-types-val",        "data"),
        Output("pref-type-wyckoff",     "style"),
        Output("pref-type-gann",        "style"),
        Output("pref-type-ab_score",    "style"),
        Output("pref-type-elliott",     "style"),
        Output("pref-type-fibonacci",   "style"),
        Input("pref-type-wyckoff",      "n_clicks"),
        Input("pref-type-gann",         "n_clicks"),
        Input("pref-type-ab_score",     "n_clicks"),
        Input("pref-type-elliott",      "n_clicks"),
        Input("pref-type-fibonacci",    "n_clicks"),
        Input("pref-type-all",          "n_clicks"),
        Input("pref-type-none",         "n_clicks"),
        State("pref-types-val",         "data"),
        prevent_initial_call=True,
    )
    def set_types(nw,ng,na,ne,nf,n_all,n_none,types):
        from dash import callback_context
        ctx = callback_context
        if not ctx.triggered: return no_update,no_update,no_update,no_update,no_update,no_update
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        types = dict(types)
        if t == "pref-type-all":
            types = {k:True for k in types}
        elif t == "pref-type-none":
            types = {k:False for k in types}
        else:
            km = {"pref-type-wyckoff":"wyckoff","pref-type-gann":"gann",
                  "pref-type-ab_score":"ab_score","pref-type-elliott":"elliott",
                  "pref-type-fibonacci":"fibonacci"}
            if t in km: types[km[t]] = not types.get(km[t], False)
        return (types,
                _active_btn() if types.get("wyckoff")   else _inactive_btn(),
                _active_btn() if types.get("gann")      else _inactive_btn(),
                _active_btn() if types.get("ab_score")  else _inactive_btn(),
                _active_btn() if types.get("elliott")   else _inactive_btn(),
                _active_btn() if types.get("fibonacci") else _inactive_btn())

    # ── Market hours ───────────────────────────────────────────────────────────
    @app.callback(
        Output("pref-hours-val", "data"),
        Output("pref-hours-btn", "children"),
        Output("pref-hours-btn", "style"),
        Input("pref-hours-btn",  "n_clicks"),
        State("pref-hours-val",  "data"),
        prevent_initial_call=True,
    )
    def toggle_hours(n, current):
        new = not current
        return new, ("ON" if new else "OFF"), (_active_btn() if new else _inactive_btn())

    # ── Watchlist ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-watchlist",         "data"),
        Output("prefs-watchlist-display", "children"),
        Output("prefs-symbol-input",      "value"),
        Input("prefs-add-symbol",         "n_clicks"),
        State("prefs-symbol-input",       "value"),
        State("prefs-watchlist",          "data"),
        prevent_initial_call=True,
    )
    def add_symbol(n, symbol, watchlist):
        if not symbol: return watchlist, _render_watchlist(watchlist), ""
        sym = symbol.strip().upper()
        if sym and sym not in watchlist:
            watchlist = watchlist + [sym]
        return watchlist, _render_watchlist(watchlist), ""

    # ── Save ───────────────────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-status-msg", "children"),
        Output("prefs-status-msg", "style"),
        Input("prefs-save-btn",    "n_clicks"),
        State("prefs-user-id",     "data"),
        State("pref-mode-val",     "data"),
        State("prefs-min-score",   "value"),
        State("pref-hours-val",    "data"),
        State("prefs-watchlist",   "data"),
        State("pref-types-val",    "data"),
        State("s-session",         "data"),
        prevent_initial_call=True,
    )
    def save_prefs(n, user_id, mode, min_score, hours, watchlist, types, session):
        if not user_id and session:
            user_id = session.get("user_id","")
        email = (session or {}).get("email","")
        if not user_id:
            return "⚠️ No user ID — please log in first.", _msg_style("yellow")
        payload = {
            "delivery_mode":     mode or "realtime",
            "min_score":         min_score or 60,
            "alert_types":       [k for k,v in (types or {}).items() if v],
            "watchlist":         watchlist or [],
            "market_hours_only": bool(hours),
        }
        try:
            url = f"{BACKEND_HTTP}/api/preferences/{user_id}"
            r = requests.patch(url, json=payload, timeout=8)
            if r.status_code == 404:
                r = requests.post(url, json={**payload,"user_id":user_id,"email":email}, timeout=8)
            if r.ok:
                return "✅ Preferences saved!", _msg_style("teal")
            return f"❌ {r.json().get('detail','Save failed')}", _msg_style("red")
        except Exception as e:
            return f"❌ {str(e)}", _msg_style("red")


def _render_watchlist(watchlist):
    if not watchlist:
        return [html.Span("All symbols — no filter applied",
                          style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]
    return [
        html.Span([sym, html.Span(" ×", style={"color":RED_DIM,"cursor":"pointer","marginLeft":"4px"})],
                  style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
                         "borderRadius":"6px","color":WHITE,"fontSize":"12px",
                         "padding":"4px 10px","marginRight":"6px","marginBottom":"6px",
                         "display":"inline-block"})
        for sym in watchlist
    ]

def _msg_style(color="teal"):
    return {"textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px",
            "color":{"teal":TEAL_DIM,"red":RED_DIM,"yellow":YELLOW_DIM}.get(color,WHITE)}
