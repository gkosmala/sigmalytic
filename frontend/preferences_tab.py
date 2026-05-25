"""
preferences_tab.py — Sigmalytic Quant
Alert Preferences UI — matches Sigmalytic Dash frontend style.

Usage in sigmalytic_app_LATEST.py:
    from preferences_tab import build_preferences_tab, register_preferences_callbacks
    # Add to layout where needed
    # Call register_preferences_callbacks(app) after app is defined
"""

from __future__ import annotations
import os
import json
import requests
from dash import dcc, html, Input, Output, State, no_update, callback_context
import dash

BACKEND_HTTP = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")

# ── Brand tokens (match main app) ─────────────────────────────────────────────
NAVY      = "#0d1b2e"
NAVY_CARD = "#111f35"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"
YELLOW    = "#f59e0b"
YELLOW_DIM= "#fde68a"
MUTED     = "#64748b"
TEXT      = "#94a3b8"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
BORDER_T  = "rgba(45,143,111,.35)"


# ── Helpers ────────────────────────────────────────────────────────────────────

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

def _toggle_btn(label, value, btn_id, active=False):
    return html.Button(
        label,
        id={"type": "pref-toggle", "index": btn_id},
        n_clicks=0,
        style={
            "background": TEAL_GLOW if active else "rgba(0,0,0,.2)",
            "border": f"1px solid {BORDER_T if active else BORDER}",
            "borderRadius": "8px",
            "color": TEAL_DIM if active else TEXT,
            "fontFamily": "DM Sans, sans-serif",
            "fontSize": "12px",
            "fontWeight": "700",
            "padding": "8px 14px",
            "cursor": "pointer",
            "transition": "all .15s",
            "marginRight": "8px",
            "marginBottom": "8px",
        },
        **{"data-value": value, "data-active": "true" if active else "false"}
    )


# ── Layout ─────────────────────────────────────────────────────────────────────

def build_preferences_tab(user_id: str = "") -> html.Div:
    return html.Div([
        dcc.Store(id="prefs-user-id", data=user_id),
        dcc.Store(id="prefs-watchlist", data=[]),
        dcc.Store(id="prefs-data", data={}),

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
                html.Button("Real-time", id="mode-realtime", n_clicks=0,
                           style=_mode_btn_style(True)),
                html.Button("Hourly Digest", id="mode-hourly", n_clicks=0,
                           style=_mode_btn_style(False)),
                html.Button("Daily Summary", id="mode-daily", n_clicks=0,
                           style=_mode_btn_style(False)),
            ], id="delivery-mode-group"),
            dcc.Store(id="prefs-delivery-mode", data="realtime"),
        ]),

        # Min Score
        _card([
            _section_title("🎯 Minimum Confluence Score"),
            _label("Only alert when score is at least:"),
            html.Div([
                dcc.Slider(
                    id="prefs-min-score",
                    min=0, max=100, step=5, value=60,
                    marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ], style={"padding": "8px 0 16px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color": MUTED, "fontSize": "11px"}),
        ]),

        # Alert Types
        _card([
            _section_title("⚡ Alert Types"),
            _label("Select any combination — or activate all:"),
            html.Div([
                html.Button("✓ All", id="type-select-all", n_clicks=0, style=_type_btn_style(False)),
                html.Button("✗ None", id="type-clear-all", n_clicks=0, style=_type_btn_style(False)),
                html.Button("Structure Alerts", id="type-wyckoff", n_clicks=0, style=_type_btn_style(True)),
                html.Button("Vector Alerts", id="type-gann", n_clicks=0, style=_type_btn_style(True)),
                html.Button("Score Alerts", id="type-ab_score", n_clicks=0, style=_type_btn_style(True)),
                html.Button("Cycle Alerts", id="type-elliott", n_clicks=0, style=_type_btn_style(False)),
                html.Button("Level Alerts", id="type-fibonacci", n_clicks=0, style=_type_btn_style(False)),
            ], id="alert-types-group"),
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

        # Market Hours
        _card([
            _section_title("🕐 Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only", style={"color": WHITE, "fontSize": "13px", "fontWeight": "600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color": MUTED, "fontSize": "11px", "marginTop": "2px"}),
                ]),
                dcc.Checklist(
                    id="prefs-market-hours",
                    options=[{"label": "", "value": "on"}],
                    value=["on"],
                    style={"marginLeft": "auto"},
                    inputStyle={"width": "18px", "height": "18px", "accentColor": TEAL, "cursor": "pointer"},
                ),
            ], style={"display": "flex", "alignItems": "center", "gap": "16px"}),
        ]),

        # Save Button
        html.Button("Save Preferences", id="prefs-save-btn", n_clicks=0, style={
            "width": "100%",
            "background": TEAL,
            "border": "none",
            "borderRadius": "12px",
            "color": WHITE,
            "fontFamily": "DM Sans, sans-serif",
            "fontSize": "14px",
            "fontWeight": "800",
            "padding": "16px",
            "cursor": "pointer",
            "letterSpacing": ".05em",
            "marginBottom": "12px",
        }),

        html.Div(id="prefs-status-msg", style={
            "textAlign": "center", "fontSize": "13px", "minHeight": "20px", "marginBottom": "24px"
        }),

    ], style={"maxWidth": "600px", "margin": "0 auto", "padding": "24px 16px"})


def _mode_btn_style(active=False):
    return {
        "flex": "1",
        "background": TEAL_GLOW if active else "rgba(0,0,0,.2)",
        "border": f"1px solid {BORDER_T if active else BORDER}",
        "borderRadius": "8px",
        "color": TEAL_DIM if active else TEXT,
        "fontFamily": "DM Sans, sans-serif",
        "fontSize": "12px",
        "fontWeight": "700",
        "padding": "10px 8px",
        "cursor": "pointer",
        "marginRight": "8px",
        "transition": "all .15s",
        "textAlign": "center",
    }

def _type_btn_style(active=False):
    return {
        "background": TEAL_GLOW if active else "rgba(0,0,0,.2)",
        "border": f"1px solid {BORDER_T if active else BORDER}",
        "borderRadius": "8px",
        "color": TEAL_DIM if active else TEXT,
        "fontFamily": "DM Sans, sans-serif",
        "fontSize": "12px",
        "fontWeight": "700",
        "padding": "8px 14px",
        "cursor": "pointer",
        "marginRight": "8px",
        "marginBottom": "8px",
        "transition": "all .15s",
    }


# ── Callbacks ──────────────────────────────────────────────────────────────────

def register_preferences_callbacks(app):

    # Add symbol to watchlist
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

    # Save preferences
    @app.callback(
        Output("prefs-status-msg", "children"),
        Output("prefs-status-msg", "style"),
        Input("prefs-save-btn", "n_clicks"),
        State("prefs-user-id", "data"),
        State("prefs-delivery-mode", "data"),
        State("prefs-min-score", "value"),
        State("prefs-market-hours", "value"),
        State("prefs-watchlist", "data"),
        State("type-wyckoff", "style"),
        State("type-gann", "style"),
        State("type-ab_score", "style"),
        State("type-elliott", "style"),
        State("type-fibonacci", "style"),
        prevent_initial_call=True,
    )
    def save_preferences(n, user_id, delivery_mode, min_score,
                         market_hours, watchlist,
                         s_wyckoff, s_gann, s_ab, s_elliott, s_fib):
        if not user_id:
            return "⚠️ No user ID — please log in first.", _status_style("yellow")

        # Determine active alert types by checking button color
        type_map = {
            "wyckoff": s_wyckoff, "gann": s_gann, "ab_score": s_ab,
            "elliott": s_elliott, "fibonacci": s_fib,
        }
        alert_types = [t for t, s in type_map.items() if s.get("color") == TEAL_DIM]

        payload = {
            "delivery_mode":    delivery_mode or "realtime",
            "min_score":        min_score or 60,
            "alert_types":      alert_types,
            "watchlist":        watchlist or [],
            "market_hours_only": bool(market_hours),
        }

        try:
            url = f"{BACKEND_HTTP}/api/preferences/{user_id}"
            r = requests.patch(url, json=payload, timeout=8)
            if r.status_code == 404:
                # New user — need email too, try POST with just what we have
                payload["user_id"] = user_id
                payload["email"] = user_id  # fallback
                r = requests.post(url, json=payload, timeout=8)
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
        html.Span([
            sym,
            html.Span(" ×", style={"color": RED_DIM, "cursor": "pointer", "marginLeft": "4px"}),
        ], style={
            "background": "rgba(0,0,0,.2)",
            "border": f"1px solid {BORDER}",
            "borderRadius": "6px",
            "color": WHITE,
            "fontSize": "12px",
            "padding": "4px 10px",
            "marginRight": "6px",
            "marginBottom": "6px",
            "display": "inline-block",
        })
        for sym in watchlist
    ]


def _status_style(color="teal"):
    colors = {
        "teal":   TEAL_DIM,
        "red":    RED_DIM,
        "yellow": YELLOW_DIM,
    }
    return {
        "textAlign": "center", "fontSize": "13px",
        "minHeight": "20px", "marginBottom": "24px",
        "color": colors.get(color, WHITE),
    }
