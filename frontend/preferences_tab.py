"""
preferences_tab.py — Sigmalytic Quant
Uses native Dash components for reliable state — no custom toggle callbacks.
"""

from __future__ import annotations
import os
import requests
from dash import dcc, html, Input, Output, State, no_update, callback_context

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

RADIO_STYLE = {
    "display": "flex", "gap": "8px", "flexWrap": "wrap"
}

RADIO_INPUT_STYLE = {"display": "none"}

RADIO_LABEL_STYLE = {
    "background": "rgba(0,0,0,.2)",
    "border": f"1px solid {BORDER}",
    "borderRadius": "8px",
    "color": TEXT,
    "fontFamily": "DM Sans, sans-serif",
    "fontSize": "12px",
    "fontWeight": "700",
    "padding": "10px 16px",
    "cursor": "pointer",
}

TYPE_LABEL_STYLE = {
    "background": "rgba(0,0,0,.2)",
    "border": f"1px solid {BORDER}",
    "borderRadius": "8px",
    "color": TEXT,
    "fontFamily": "DM Sans, sans-serif",
    "fontSize": "12px",
    "fontWeight": "700",
    "padding": "8px 14px",
    "cursor": "pointer",
    "marginRight": "6px",
    "marginBottom": "6px",
    "display": "inline-block",
}

PREF_CSS = """
/* Delivery mode radio */
#prefs-delivery-mode .form-check { display: inline-block; margin: 0; }
#prefs-delivery-mode input[type=radio] { display: none; }
#prefs-delivery-mode input[type=radio] + label {
    background: rgba(0,0,0,.2);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 8px;
    color: #94a3b8;
    font-family: DM Sans, sans-serif;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 16px;
    cursor: pointer;
    margin-right: 8px;
    transition: all .15s;
    display: inline-block;
}
#prefs-delivery-mode input[type=radio]:checked + label {
    background: rgba(45,143,111,.18);
    border-color: rgba(45,143,111,.35);
    color: #34d399;
}

/* Alert types checklist */
#prefs-alert-types .form-check { display: inline-block; margin: 0; }
#prefs-alert-types input[type=checkbox] { display: none; }
#prefs-alert-types input[type=checkbox] + label {
    background: rgba(0,0,0,.2);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 8px;
    color: #94a3b8;
    font-family: DM Sans, sans-serif;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 14px;
    cursor: pointer;
    margin-right: 6px;
    margin-bottom: 6px;
    transition: all .15s;
    display: inline-block;
}
#prefs-alert-types input[type=checkbox]:checked + label {
    background: rgba(45,143,111,.18);
    border-color: rgba(45,143,111,.35);
    color: #34d399;
}

/* Market hours checklist */
#prefs-market-hours .form-check { display: inline-block; margin: 0; }
#prefs-market-hours input[type=checkbox] { display: none; }
#prefs-market-hours input[type=checkbox] + label {
    background: rgba(0,0,0,.2);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 8px;
    color: #94a3b8;
    font-family: DM Sans, sans-serif;
    font-size: 12px;
    font-weight: 800;
    padding: 8px 18px;
    cursor: pointer;
    min-width: 60px;
    text-align: center;
    transition: all .15s;
    display: inline-block;
}
#prefs-market-hours input[type=checkbox]:checked + label {
    background: rgba(45,143,111,.18);
    border-color: rgba(45,143,111,.35);
    color: #34d399;
}
"""

def build_preferences_tab(user_id: str = "") -> html.Div:
    return html.Div([
        # Inject CSS
        html.Style(PREF_CSS),

        # Persistent user id store (not reset on tab switch)
        dcc.Store(id="prefs-user-id", data=user_id),
        dcc.Store(id="prefs-watchlist", data=[]),

        # Header
        html.Div([
            html.H2("Alert Preferences", style={
                "color": WHITE, "fontSize": "22px", "fontWeight": "800", "marginBottom": "4px"
            }),
            html.P("Control which alerts you receive and how often.",
                   style={"color": TEXT, "fontSize": "13px"}),
        ], style={"marginBottom": "24px"}),

        # Delivery Mode — native RadioItems, CSS handles styling
        _card([
            _section_title("📬 Delivery Mode"),
            _label("How often do you want alerts?"),
            dcc.RadioItems(
                id="prefs-delivery-mode",
                options=[
                    {"label": "Real-time",     "value": "realtime"},
                    {"label": "Hourly Digest", "value": "hourly"},
                    {"label": "Daily Summary", "value": "daily"},
                ],
                value="realtime",
                inline=True,
                style={"display": "flex", "flexWrap": "wrap", "gap": "4px"},
            ),
        ]),

        # Min Score
        _card([
            _section_title("🎯 Minimum Confluence Score"),
            _label("Only alert when score is at least:"),
            dcc.Slider(
                id="prefs-min-score",
                min=0, max=100, step=5, value=60,
                marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                tooltip={"placement": "bottom", "always_visible": True},
            ),
            html.Div(style={"height": "8px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color": MUTED, "fontSize": "11px"}),
        ]),

        # Alert Types — native Checklist, CSS handles styling
        _card([
            _section_title("⚡ Alert Types"),
            _label("Select any combination — or activate all:"),
            dcc.Checklist(
                id="prefs-alert-types",
                options=[
                    {"label": "Structure Alerts", "value": "wyckoff"},
                    {"label": "Vector Alerts",    "value": "gann"},
                    {"label": "Score Alerts",     "value": "ab_score"},
                    {"label": "Cycle Alerts",     "value": "elliott"},
                    {"label": "Level Alerts",     "value": "fibonacci"},
                ],
                value=["wyckoff", "gann", "ab_score"],
                inline=True,
                style={"display": "flex", "flexWrap": "wrap", "gap": "4px"},
            ),
        ]),

        # Watchlist
        _card([
            _section_title("📋 Watchlist"),
            _label("Only alert on these symbols (leave empty for all 1,403)"),
            html.Div([
                dcc.Input(
                    id="prefs-symbol-input",
                    type="text",
                    placeholder="e.g. AAPL",
                    maxLength=5,
                    style={
                        "background": "rgba(0,0,0,.3)",
                        "border": f"1px solid {BORDER}",
                        "borderRadius": "8px",
                        "color": WHITE,
                        "fontFamily": "DM Mono, monospace",
                        "fontSize": "13px",
                        "padding": "10px 14px",
                        "width": "160px",
                        "marginRight": "10px",
                        "textTransform": "uppercase",
                    }
                ),
                html.Button("Add Symbol", id="prefs-add-symbol", n_clicks=0, style={
                    "background": TEAL_GLOW,
                    "border": f"1px solid {BORDER_T}",
                    "borderRadius": "8px",
                    "color": TEAL_DIM,
                    "fontFamily": "DM Sans, sans-serif",
                    "fontSize": "12px",
                    "fontWeight": "700",
                    "padding": "10px 18px",
                    "cursor": "pointer",
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
            html.Div(id="prefs-watchlist-display",
                     children=[html.Span("All symbols — no filter applied",
                                         style={"color": MUTED, "fontSize": "12px", "fontStyle": "italic"})]),
        ]),

        # Market Hours — native Checklist single option, CSS handles styling
        _card([
            _section_title("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only",
                             style={"color": WHITE, "fontSize": "13px", "fontWeight": "600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color": MUTED, "fontSize": "11px", "marginTop": "2px"}),
                ], style={"flex": "1"}),
                dcc.Checklist(
                    id="prefs-market-hours",
                    options=[{"label": "ON", "value": "on"}],
                    value=["on"],
                    inline=True,
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "16px"}),
        ]),

        # Save
        html.Button("Save Preferences", id="prefs-save-btn", n_clicks=0, style={
            "width": "100%", "background": TEAL, "border": "none",
            "borderRadius": "12px", "color": WHITE,
            "fontFamily": "DM Sans, sans-serif", "fontSize": "14px",
            "fontWeight": "800", "padding": "16px", "cursor": "pointer",
            "letterSpacing": ".05em", "marginBottom": "12px",
        }),
        html.Div(id="prefs-status-msg", style={
            "textAlign": "center", "fontSize": "13px",
            "minHeight": "20px", "marginBottom": "24px",
        }),

    ], style={"maxWidth": "600px", "margin": "0 auto", "padding": "24px 16px"})


def register_preferences_callbacks(app):

    # ── Watchlist ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("prefs-watchlist", "data"),
        Output("prefs-watchlist-display", "children"),
        Output("prefs-symbol-input", "value"),
        Input("prefs-add-symbol", "n_clicks"),
        State("prefs-symbol-input", "value"),
        State("prefs-watchlist", "data"),
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
        Input("prefs-save-btn", "n_clicks"),
        State("prefs-user-id",         "data"),
        State("prefs-delivery-mode",   "value"),
        State("prefs-min-score",       "value"),
        State("prefs-market-hours",    "value"),
        State("prefs-watchlist",       "data"),
        State("prefs-alert-types",     "value"),
        State("s-session",             "data"),
        prevent_initial_call=True,
    )
    def save_preferences(n, user_id, delivery_mode, min_score,
                         market_hours, watchlist, alert_types, session):
        if not user_id and session:
            user_id = session.get("user_id", "")
        user_email = (session or {}).get("email", "")
        if not user_id:
            return "⚠️ No user ID — please log in first.", _status_style("yellow")

        payload = {
            "delivery_mode":     delivery_mode or "realtime",
            "min_score":         min_score or 60,
            "alert_types":       alert_types or [],
            "watchlist":         watchlist or [],
            "market_hours_only": "on" in (market_hours or []),
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
                          style={"color": MUTED, "fontSize": "12px", "fontStyle": "italic"})]
    return [
        html.Span([sym, html.Span(" ×", style={"color": RED_DIM, "cursor": "pointer", "marginLeft": "4px"})],
                  style={"background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
                         "borderRadius": "6px", "color": WHITE, "fontSize": "12px",
                         "padding": "4px 10px", "marginRight": "6px", "marginBottom": "6px",
                         "display": "inline-block"})
        for sym in watchlist
    ]

def _status_style(color="teal"):
    return {"textAlign": "center", "fontSize": "13px", "minHeight": "20px", "marginBottom": "24px",
            "color": {"teal": TEAL_DIM, "red": RED_DIM, "yellow": YELLOW_DIM}.get(color, WHITE)}
