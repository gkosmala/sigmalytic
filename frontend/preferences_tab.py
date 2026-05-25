"""
preferences_tab.py — Sigmalytic Quant
Alert Preferences UI — stable, no dynamic re-rendering.
"""

from __future__ import annotations
import os
import requests
from dash import dcc, html, Input, Output, State, no_update, callback_context

BACKEND_HTTP = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")

NAVY      = "#0d1b2e"
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

def _card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
         "borderRadius": "20px", "padding": "20px",
         "boxShadow": "0 8px 32px rgba(0,0,0,.32)", "marginBottom": "16px"}
    if sx: s.update(sx)
    return html.Section(children, style=s)

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

def _on():
    return {"background": TEAL_GLOW, "border": f"1px solid {BORDER_T}",
            "borderRadius": "8px", "color": TEAL_DIM,
            "fontFamily": "DM Sans, sans-serif", "fontSize": "12px",
            "fontWeight": "700", "padding": "10px 16px",
            "cursor": "pointer", "marginRight": "8px", "transition": "all .15s"}

def _off():
    return {"background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
            "borderRadius": "8px", "color": TEXT,
            "fontFamily": "DM Sans, sans-serif", "fontSize": "12px",
            "fontWeight": "700", "padding": "10px 16px",
            "cursor": "pointer", "marginRight": "8px", "transition": "all .15s"}

def _hours_on():
    return {"background": TEAL_GLOW, "border": f"1px solid {BORDER_T}",
            "borderRadius": "8px", "color": TEAL_DIM,
            "fontFamily": "DM Sans, sans-serif", "fontSize": "12px",
            "fontWeight": "800", "padding": "8px 18px",
            "cursor": "pointer", "minWidth": "60px", "marginLeft": "auto"}

def _hours_off():
    return {"background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
            "borderRadius": "8px", "color": MUTED,
            "fontFamily": "DM Sans, sans-serif", "fontSize": "12px",
            "fontWeight": "800", "padding": "8px 18px",
            "cursor": "pointer", "minWidth": "60px", "marginLeft": "auto"}


def build_preferences_tab(user_id: str = "") -> html.Div:
    return html.Div([
        # Stores live in app.py layout to persist across tab switches

        html.Div([
            html.H2("Alert Preferences", style={
                "color": WHITE, "fontSize": "22px", "fontWeight": "800", "marginBottom": "4px"
            }),
            html.P("Control which alerts you receive and how often.",
                   style={"color": TEXT, "fontSize": "13px"}),
        ], style={"marginBottom": "24px"}),

        # Delivery Mode — static buttons, styles updated by callback
        _card([
            _section_title("📬 Delivery Mode"),
            _label("How often do you want alerts?"),
            html.Div([
                html.Button("Real-time",     id="mode-realtime", n_clicks=0, style=_on()),
                html.Button("Hourly Digest", id="mode-hourly",   n_clicks=0, style=_off()),
                html.Button("Daily Summary", id="mode-daily",    n_clicks=0, style=_off()),
            ], style={"display": "flex"}),
        ]),

        # Min Score
        _card([
            _section_title("🎯 Minimum Confluence Score"),
            _label("Only alert when score is at least:"),
            dcc.Slider(id="prefs-min-score", min=0, max=100, step=5, value=60,
                       marks={0:"0", 25:"25", 50:"50", 75:"75", 100:"100"},
                       tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height": "8px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color": MUTED, "fontSize": "11px"}),
        ]),

        # Alert Types — static buttons, styles updated by callback
        _card([
            _section_title("⚡ Alert Types"),
            _label("Select any combination — or activate all:"),
            html.Div([
                html.Button("✓ All",            id="type-select-all", n_clicks=0, style=_off()),
                html.Button("✗ None",           id="type-clear-all",  n_clicks=0, style=_off()),
                html.Button("Structure Alerts", id="type-wyckoff",    n_clicks=0, style=_on()),
                html.Button("Vector Alerts",    id="type-gann",       n_clicks=0, style=_on()),
                html.Button("Score Alerts",     id="type-ab_score",   n_clicks=0, style=_on()),
                html.Button("Cycle Alerts",     id="type-elliott",    n_clicks=0, style=_off()),
                html.Button("Level Alerts",     id="type-fibonacci",  n_clicks=0, style=_off()),
            ], style={"flexWrap": "wrap", "display": "flex"}),
        ]),

        # Watchlist
        _card([
            _section_title("📋 Watchlist"),
            _label("Only alert on these symbols (leave empty for all 1,403)"),
            html.Div([
                dcc.Input(id="prefs-symbol-input", type="text",
                          placeholder="e.g. AAPL", maxLength=5,
                          style={"background":"rgba(0,0,0,.3)", "border":f"1px solid {BORDER}",
                                 "borderRadius":"8px", "color":WHITE,
                                 "fontFamily":"DM Mono, monospace", "fontSize":"13px",
                                 "padding":"10px 14px", "width":"160px", "marginRight":"10px",
                                 "textTransform":"uppercase"}),
                html.Button("Add Symbol", id="prefs-add-symbol", n_clicks=0,
                            style={"background":TEAL_GLOW, "border":f"1px solid {BORDER_T}",
                                   "borderRadius":"8px", "color":TEAL_DIM,
                                   "fontFamily":"DM Sans, sans-serif", "fontSize":"12px",
                                   "fontWeight":"700", "padding":"10px 18px", "cursor":"pointer"}),
            ], style={"display":"flex", "alignItems":"center", "marginBottom":"12px"}),
            html.Div(id="prefs-watchlist-display",
                     children=[html.Span("All symbols — no filter applied",
                                         style={"color":MUTED,"fontSize":"12px","fontStyle":"italic"})]),
        ]),

        # Market Hours — single static button, style updated by callback
        _card([
            _section_title("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only",
                             style={"color":WHITE,"fontSize":"13px","fontWeight":"600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color":MUTED,"fontSize":"11px","marginTop":"2px"}),
                ]),
                html.Button("ON", id="prefs-market-hours-btn", n_clicks=0,
                            style=_hours_on()),
            ], style={"display":"flex","alignItems":"center","gap":"16px"}),
        ]),

        html.Button("Save Preferences", id="prefs-save-btn", n_clicks=0, style={
            "width":"100%", "background":TEAL, "border":"none", "borderRadius":"12px",
            "color":WHITE, "fontFamily":"DM Sans, sans-serif", "fontSize":"14px",
            "fontWeight":"800", "padding":"16px", "cursor":"pointer",
            "letterSpacing":".05em", "marginBottom":"12px",
        }),
        html.Div(id="prefs-status-msg", style={
            "textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px"
        }),

    ], style={"maxWidth":"600px","margin":"0 auto","padding":"24px 16px"})


def register_preferences_callbacks(app):

    # ── Sync user_id from session into store when tab opens ───────────────────
    @app.callback(
        Output("prefs-user-id", "data"),
        Input("s-tab", "data"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def sync_user_id(tab, session):
        if tab == "preferences" and session:
            return session.get("user_id", "")
        return no_update


    # ── Delivery mode: update store + button styles ────────────────────────────
    @app.callback(
        Output("prefs-delivery-mode", "data"),
        Output("mode-realtime", "style"),
        Output("mode-hourly",   "style"),
        Output("mode-daily",    "style"),
        Input("mode-realtime", "n_clicks"),
        Input("mode-hourly",   "n_clicks"),
        Input("mode-daily",    "n_clicks"),
        State("prefs-delivery-mode", "data"),
        prevent_initial_call=True,
    )
    def set_delivery_mode(r, h, d, current):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        mode_map = {
            "mode-realtime": "realtime",
            "mode-hourly":   "hourly",
            "mode-daily":    "daily",
        }
        new_mode = mode_map.get(trigger, current)
        styles = [_on() if m == new_mode else _off()
                  for m in ["realtime", "hourly", "daily"]]
        return new_mode, styles[0], styles[1], styles[2]

    # ── Alert types: update store + button styles ──────────────────────────────
    @app.callback(
        Output("prefs-types",      "data"),
        Output("type-wyckoff",     "style"),
        Output("type-gann",        "style"),
        Output("type-ab_score",    "style"),
        Output("type-elliott",     "style"),
        Output("type-fibonacci",   "style"),
        Input("type-wyckoff",      "n_clicks"),
        Input("type-gann",         "n_clicks"),
        Input("type-ab_score",     "n_clicks"),
        Input("type-elliott",      "n_clicks"),
        Input("type-fibonacci",    "n_clicks"),
        Input("type-select-all",   "n_clicks"),
        Input("type-clear-all",    "n_clicks"),
        State("prefs-types",       "data"),
        prevent_initial_call=True,
    )
    def update_types(nw, ng, na, ne, nf, n_all, n_none, types):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        types = dict(types)
        if trigger == "type-select-all":
            types = {k: True for k in types}
        elif trigger == "type-clear-all":
            types = {k: False for k in types}
        else:
            key_map = {"type-wyckoff":"wyckoff","type-gann":"gann","type-ab_score":"ab_score",
                       "type-elliott":"elliott","type-fibonacci":"fibonacci"}
            if trigger in key_map:
                k = key_map[trigger]
                types[k] = not types.get(k, False)
        return (types,
                _on() if types.get("wyckoff")   else _off(),
                _on() if types.get("gann")       else _off(),
                _on() if types.get("ab_score")   else _off(),
                _on() if types.get("elliott")    else _off(),
                _on() if types.get("fibonacci")  else _off())

    # ── Market hours toggle ────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-market-hours-val",  "data"),
        Output("prefs-market-hours-btn",  "children"),
        Output("prefs-market-hours-btn",  "style"),
        Input("prefs-market-hours-btn",   "n_clicks"),
        State("prefs-market-hours-val",   "data"),
        prevent_initial_call=True,
    )
    def toggle_market_hours(n, current):
        new_val = not current
        return new_val, ("ON" if new_val else "OFF"), (_hours_on() if new_val else _hours_off())

    # ── Watchlist ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-watchlist",        "data"),
        Output("prefs-watchlist-display","children"),
        Output("prefs-symbol-input",     "value"),
        Input("prefs-add-symbol",        "n_clicks"),
        State("prefs-symbol-input",      "value"),
        State("prefs-watchlist",         "data"),
        prevent_initial_call=True,
    )
    def add_symbol(n, symbol, watchlist):
        if not symbol:
            return watchlist, _render_watchlist(watchlist), ""
        sym = symbol.strip().upper()
        if sym and sym not in watchlist:
            watchlist = watchlist + [sym]
        return watchlist, _render_watchlist(watchlist), ""

    # ── Save ───────────────────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-status-msg", "children"),
        Output("prefs-status-msg", "style"),
        Input("prefs-save-btn",              "n_clicks"),
        State("prefs-user-id",               "data"),
        State("prefs-delivery-mode",         "data"),
        State("prefs-min-score",             "value"),
        State("prefs-market-hours-val",      "data"),
        State("prefs-watchlist",             "data"),
        State("prefs-types",                 "data"),
        State("s-session",                   "data"),
        prevent_initial_call=True,
    )
    def save_preferences(n, user_id, delivery_mode, min_score,
                         market_hours, watchlist, types, session):
        if not user_id and session:
            user_id = session.get("user_id", "")
        user_email = (session or {}).get("email", "")
        if not user_id:
            return "⚠️ No user ID — please log in first.", _status_style("yellow")

        alert_types = [k for k, v in (types or {}).items() if v]
        payload = {
            "delivery_mode":     delivery_mode or "realtime",
            "min_score":         min_score or 60,
            "alert_types":       alert_types,
            "watchlist":         watchlist or [],
            "market_hours_only": bool(market_hours),
        }
        try:
            url = f"{BACKEND_HTTP}/api/preferences/{user_id}"
            r = requests.patch(url, json=payload, timeout=8)
            if r.status_code == 404:
                r = requests.post(url, json={**payload, "user_id": user_id, "email": user_email}, timeout=8)
            if r.ok:
                return "✅ Preferences saved!", _status_style("teal")
            return f"❌ Error: {r.json().get('detail','Save failed')}", _status_style("red")
        except Exception as e:
            return f"❌ Error: {str(e)}", _status_style("red")


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

def _status_style(color="teal"):
    return {"textAlign":"center","fontSize":"13px","minHeight":"20px","marginBottom":"24px",
            "color": {"teal":TEAL_DIM,"red":RED_DIM,"yellow":YELLOW_DIM}.get(color, WHITE)}
