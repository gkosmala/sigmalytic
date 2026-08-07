# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
preferences_tab.py - Sigmalytic Quant
Clean ASCII-safe Preferences tab.

This file only controls the Preferences tab.

NOTE (2026-08-07): confirmed via full-frontend search this module is
genuinely never imported anywhere -- app.py has its own separate,
earlier, inline build_preferences_tab() function, which is the one
actually used by the live "preferences" tab dispatch. This file
appears to be an incomplete or abandoned rewrite attempt.

Initially suspected this rewrite existed specifically to fix a real
mojibake/encoding bug in app.py's inline version (given this file's
own "ASCII-safe" framing) -- checked directly and that was wrong: the
live version's few non-ASCII characters (an em/en dash, and a
correctly-encoded "wavy dash" emoji for "Weis Wave Sensitivity") are
all genuinely, properly encoded. No mojibake bug exists in the live
version this file needed to fix. This is simply unused, duplicate
code, not an urgent, never-shipped bugfix.
"""

from __future__ import annotations

import os
import requests
from dash import dcc, html, Input, Output, State, no_update, callback_context

BACKEND_HTTP = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")

NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"
MUTED = "#f8fafc"
TEXT = "#f8fafc"
WHITE = "#f8fafc"
BORDER = "rgba(255,255,255,.08)"
BORDER_T = "rgba(45,143,111,.35)"


def _card(children):
    return html.Section(
        children,
        style={
            "background": NAVY_CARD,
            "border": f"1px solid {BORDER}",
            "borderRadius": "20px",
            "padding": "20px",
            "boxShadow": "0 8px 32px rgba(0,0,0,.32)",
            "marginBottom": "16px",
        },
    )


def _label(text):
    return html.Div(
        text,
        style={
            "color": MUTED,
            "fontSize": "10px",
            "fontWeight": "800",
            "textTransform": "uppercase",
            "letterSpacing": ".28em",
            "marginBottom": "10px",
        },
    )


def _section_title(text):
    return html.Div(
        text,
        style={
            "color": TEAL_DIM,
            "fontSize": "11px",
            "fontWeight": "800",
            "textTransform": "uppercase",
            "letterSpacing": ".15em",
            "marginBottom": "16px",
            "paddingBottom": "10px",
            "borderBottom": f"1px solid {BORDER}",
        },
    )


# Backward-compatible alias. This prevents the exact live error:
# name '_stitle' is not defined.
_stitle = _section_title


def _on():
    return {
        "background": TEAL_GLOW,
        "border": f"1px solid {BORDER_T}",
        "borderRadius": "8px",
        "color": TEAL_DIM,
        "fontFamily": "DM Sans, sans-serif",
        "fontSize": "12px",
        "fontWeight": "700",
        "padding": "8px 16px",
        "cursor": "pointer",
        "transition": "all .15s",
    }


def _off():
    return {
        "background": "rgba(0,0,0,.2)",
        "border": f"1px solid {BORDER}",
        "borderRadius": "8px",
        "color": WHITE,
        "fontFamily": "DM Sans, sans-serif",
        "fontSize": "12px",
        "fontWeight": "700",
        "padding": "8px 16px",
        "cursor": "pointer",
        "transition": "all .15s",
    }


def _msg_style(color="teal"):
    return {
        "textAlign": "center",
        "fontSize": "13px",
        "minHeight": "20px",
        "marginBottom": "24px",
        "color": {"teal": TEAL_DIM, "red": RED_DIM, "yellow": YELLOW_DIM}.get(color, WHITE),
    }


def _save(uid, email, payload):
    try:
        url = f"{BACKEND_HTTP}/api/preferences/{uid}"
        response = requests.patch(url, json=payload, timeout=8)
        if response.status_code == 404:
            response = requests.post(
                url,
                json={**payload, "user_id": uid, "email": email},
                timeout=8,
            )
        if response.ok:
            return "Saved", "teal"
        try:
            detail = response.json().get("detail", "Save failed")
        except Exception:
            detail = "Save failed"
        return detail, "red"
    except Exception as exc:
        return str(exc), "red"


def _render_watchlist(watchlist):
    if not watchlist:
        return [
            html.Span(
                "All symbols - no filter applied",
                style={"color": WHITE, "fontSize": "12px", "fontStyle": "italic"},
            )
        ]

    return [
        html.Span(
            symbol,
            style={
                "background": "rgba(0,0,0,.2)",
                "border": f"1px solid {BORDER}",
                "borderRadius": "6px",
                "color": WHITE,
                "fontSize": "12px",
                "padding": "4px 10px",
                "marginRight": "6px",
                "marginBottom": "6px",
                "display": "inline-block",
            },
        )
        for symbol in watchlist
    ]


def _load_preferences(user_id):
    prefs = {
        "delivery_mode": "realtime",
        "min_score": 60,
        "alert_types": {
            "wyckoff": True,
            "gann": True,
            "ab_score": True,
            "elliott": False,
            "fibonacci": False,
        },
        "watchlist": [],
        "market_hours_only": True,
        "hurst_profile": "MEDIUM",
        "weis_threshold": 0.5,
    }

    if not user_id:
        return prefs

    try:
        response = requests.get(f"{BACKEND_HTTP}/api/preferences/{user_id}", timeout=4)
        if response.ok:
            saved = response.json()
            for key in prefs:
                prefs[key] = saved.get(key, prefs[key])
    except Exception:
        pass

    if isinstance(prefs.get("alert_types"), list):
        selected = set(prefs["alert_types"])
        keys = ["wyckoff", "gann", "ab_score", "elliott", "fibonacci"]
        prefs["alert_types"] = {key: key in selected for key in keys}

    if not isinstance(prefs.get("watchlist"), list):
        prefs["watchlist"] = []

    return prefs


def build_preferences_tab(user_id="", session=None):
    prefs = _load_preferences(user_id)

    mode = prefs["delivery_mode"]
    types = prefs["alert_types"]
    hours = prefs["market_hours_only"]
    score = prefs["min_score"]
    watchlist = prefs["watchlist"]
    hurst = prefs["hurst_profile"]
    weis = prefs["weis_threshold"]
    email = (session or {}).get("email", "")

    return html.Div(
        [
            dcc.Store(id="prefs-uid", data=user_id),
            dcc.Store(id="prefs-email", data=email),
            dcc.Store(id="prefs-mode-cur", data=mode),
            dcc.Store(id="prefs-types-cur", data=types),
            dcc.Store(id="prefs-hours-cur", data=hours),
            dcc.Store(id="prefs-score-cur", data=score),
            dcc.Store(id="prefs-wl-cur", data=watchlist),
            dcc.Store(id="prefs-hurst-cur", data=hurst),
            dcc.Store(id="prefs-weis-cur", data=weis),

            html.Div(
                [
                    html.H2(
                        "Alert Preferences",
                        style={
                            "color": WHITE,
                            "fontSize": "22px",
                            "fontWeight": "800",
                            "marginBottom": "4px",
                        },
                    ),
                    html.P(
                        "Changes save instantly.",
                        style={"color": WHITE, "fontSize": "13px"},
                    ),
                ],
                style={"marginBottom": "24px"},
            ),

            html.Div(
                id="prefs-status",
                style={
                    "textAlign": "center",
                    "fontSize": "13px",
                    "minHeight": "24px",
                    "marginBottom": "8px",
                    "color": TEAL_DIM,
                },
            ),

            _card(
                [
                    _section_title("Delivery Mode"),
                    _label("How often do you want alerts?"),
                    html.Div(
                        [
                            html.Button("Real-time", id="pref-btn-realtime", n_clicks=0, style=_on() if mode == "realtime" else _off()),
                            html.Button("Hourly Digest", id="pref-btn-hourly", n_clicks=0, style=_on() if mode == "hourly" else _off()),
                            html.Button("Daily Summary", id="pref-btn-daily", n_clicks=0, style=_on() if mode == "daily" else _off()),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px"},
                    ),
                ]
            ),

            _card(
                [
                    _section_title("Minimum Confluence Score"),
                    _label("Only alert when score is at least:"),
                    dcc.Slider(
                        id="prefs-score-slider",
                        min=0,
                        max=100,
                        step=5,
                        value=score,
                        marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                    html.Div(style={"height": "8px"}),
                    html.Div(
                        "Higher score = fewer, higher-quality alerts",
                        style={"color": WHITE, "fontSize": "11px"},
                    ),
                    html.Button(
                        "Save Score",
                        id="prefs-score-save",
                        n_clicks=0,
                        style={
                            "marginTop": "12px",
                            "background": TEAL_GLOW,
                            "border": f"1px solid {BORDER_T}",
                            "borderRadius": "8px",
                            "color": TEAL_DIM,
                            "fontFamily": "DM Sans, sans-serif",
                            "fontSize": "12px",
                            "fontWeight": "700",
                            "padding": "8px 16px",
                            "cursor": "pointer",
                        },
                    ),
                ]
            ),

            _card(
                [
                    _section_title("Alert Types"),
                    _label("Click to toggle - saves instantly:"),
                    html.Div(
                        [
                            html.Button("Structure Alerts", id="pref-btn-wyckoff", n_clicks=0, style=_on() if types.get("wyckoff") else _off()),
                            html.Button("Vector Alerts", id="pref-btn-gann", n_clicks=0, style=_on() if types.get("gann") else _off()),
                            html.Button("Score Alerts", id="pref-btn-ab_score", n_clicks=0, style=_on() if types.get("ab_score") else _off()),
                            html.Button("Cycle Alerts", id="pref-btn-elliott", n_clicks=0, style=_on() if types.get("elliott") else _off()),
                            html.Button("Level Alerts", id="pref-btn-fibonacci", n_clicks=0, style=_on() if types.get("fibonacci") else _off()),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px"},
                    ),
                ]
            ),

            _card(
                [
                    _section_title("Watchlist"),
                    _label("Only alert on these symbols. Leave empty for all."),
                    html.Div(
                        [
                            dcc.Input(
                                id="prefs-sym-input",
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
                                },
                            ),
                            html.Button(
                                "Add Symbol",
                                id="prefs-sym-add",
                                n_clicks=0,
                                style={
                                    "background": TEAL_GLOW,
                                    "border": f"1px solid {BORDER_T}",
                                    "borderRadius": "8px",
                                    "color": TEAL_DIM,
                                    "fontFamily": "DM Sans, sans-serif",
                                    "fontSize": "12px",
                                    "fontWeight": "700",
                                    "padding": "10px 18px",
                                    "cursor": "pointer",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "marginBottom": "12px"},
                    ),
                    html.Div(id="prefs-wl-display", children=_render_watchlist(watchlist)),
                ]
            ),

            _card(
                [
                    _section_title("Market Hours"),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Market hours only", style={"color": WHITE, "fontSize": "13px", "fontWeight": "600"}),
                                    html.Div("Suppress alerts outside 9:30-4:00 PM ET", style={"color": WHITE, "fontSize": "11px", "marginTop": "2px"}),
                                ],
                                style={"flex": "1"},
                            ),
                            html.Button("ON" if hours else "OFF", id="pref-btn-hours", n_clicks=0, style=_on() if hours else _off()),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "16px"},
                    ),
                ]
            ),

            _card(
                [
                    _section_title("Hurst Cycle Profile"),
                    _label("Lookback horizon for cycle timing analysis"),
                    html.Div(
                        [
                            html.Button("Short (90d)", id="pref-btn-hurst-short", n_clicks=0, style=_on() if hurst == "SHORT" else _off()),
                            html.Button("Medium (1yr)", id="pref-btn-hurst-medium", n_clicks=0, style=_on() if hurst == "MEDIUM" else _off()),
                            html.Button("Long (3yr)", id="pref-btn-hurst-long", n_clicks=0, style=_on() if hurst == "LONG" else _off()),
                        ],
                        style={"display": "flex", "flexWrap": "wrap", "gap": "8px"},
                    ),
                ]
            ),

            _card(
                [
                    _section_title("Weis Wave Sensitivity"),
                    _label("Reversal threshold - lower means more sensitive"),
                    dcc.Slider(
                        id="prefs-weis-slider",
                        min=0.1,
                        max=3.0,
                        step=0.1,
                        value=weis,
                        marks={0.1: "0.1%", 0.5: "0.5%", 1.0: "1.0%", 2.0: "2.0%", 3.0: "3.0%"},
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                    html.Div(style={"height": "8px"}),
                    html.Button(
                        "Save Sensitivity",
                        id="prefs-weis-save",
                        n_clicks=0,
                        style={
                            "marginTop": "12px",
                            "background": TEAL_GLOW,
                            "border": f"1px solid {BORDER_T}",
                            "borderRadius": "8px",
                            "color": TEAL_DIM,
                            "fontFamily": "DM Sans, sans-serif",
                            "fontSize": "12px",
                            "fontWeight": "700",
                            "padding": "8px 16px",
                            "cursor": "pointer",
                        },
                    ),
                ]
            ),
        ],
        style={"maxWidth": "600px", "margin": "0 auto", "padding": "24px 16px"},
    )


def register_preferences_callbacks(app):
    @app.callback(
        Output("prefs-status", "children"),
        Output("prefs-status", "style"),
        Output("pref-btn-realtime", "style"),
        Output("pref-btn-hourly", "style"),
        Output("pref-btn-daily", "style"),
        Output("prefs-mode-cur", "data"),
        Input("pref-btn-realtime", "n_clicks"),
        Input("pref-btn-hourly", "n_clicks"),
        Input("pref-btn-daily", "n_clicks"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        State("prefs-mode-cur", "data"),
        prevent_initial_call=True,
    )
    def save_mode(_r, _h, _d, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered:
            return (no_update,) * 6
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        mode_map = {
            "pref-btn-realtime": "realtime",
            "pref-btn-hourly": "hourly",
            "pref-btn-daily": "daily",
        }
        mode = mode_map.get(triggered, cur)
        styles = [_on() if value == mode else _off() for value in ["realtime", "hourly", "daily"]]
        if not uid:
            return "Not logged in", _msg_style("yellow"), *styles, mode
        message, color = _save(uid, email, {"delivery_mode": mode})
        return message, _msg_style(color), *styles, mode

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("pref-btn-wyckoff", "style"),
        Output("pref-btn-gann", "style"),
        Output("pref-btn-ab_score", "style"),
        Output("pref-btn-elliott", "style"),
        Output("pref-btn-fibonacci", "style"),
        Output("prefs-types-cur", "data"),
        Input("pref-btn-wyckoff", "n_clicks"),
        Input("pref-btn-gann", "n_clicks"),
        Input("pref-btn-ab_score", "n_clicks"),
        Input("pref-btn-elliott", "n_clicks"),
        Input("pref-btn-fibonacci", "n_clicks"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        State("prefs-types-cur", "data"),
        prevent_initial_call=True,
    )
    def save_types(_nw, _ng, _na, _ne, _nf, uid, email, types):
        ctx = callback_context
        if not ctx.triggered:
            return (no_update,) * 8
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        key_map = {
            "pref-btn-wyckoff": "wyckoff",
            "pref-btn-gann": "gann",
            "pref-btn-ab_score": "ab_score",
            "pref-btn-elliott": "elliott",
            "pref-btn-fibonacci": "fibonacci",
        }
        types = dict(types or {})
        if triggered in key_map:
            key = key_map[triggered]
            types[key] = not types.get(key, False)
        order = ["wyckoff", "gann", "ab_score", "elliott", "fibonacci"]
        styles = [_on() if types.get(key) else _off() for key in order]
        if not uid:
            return "Not logged in", _msg_style("yellow"), *styles, types
        message, color = _save(uid, email, {"alert_types": types})
        return message, _msg_style(color), *styles, types

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("pref-btn-hours", "children"),
        Output("pref-btn-hours", "style"),
        Output("prefs-hours-cur", "data"),
        Input("pref-btn-hours", "n_clicks"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        State("prefs-hours-cur", "data"),
        prevent_initial_call=True,
    )
    def save_hours(_n, uid, email, cur):
        new_value = not cur
        label = "ON" if new_value else "OFF"
        style = _on() if new_value else _off()
        if not uid:
            return "Not logged in", _msg_style("yellow"), label, style, new_value
        message, color = _save(uid, email, {"market_hours_only": new_value})
        return message, _msg_style(color), label, style, new_value

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("prefs-score-cur", "data"),
        Input("prefs-score-save", "n_clicks"),
        State("prefs-score-slider", "value"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        prevent_initial_call=True,
    )
    def save_score(_n, value, uid, email):
        if not uid:
            return "Not logged in", _msg_style("yellow"), value
        message, color = _save(uid, email, {"min_score": value})
        return message, _msg_style(color), value

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("pref-btn-hurst-short", "style"),
        Output("pref-btn-hurst-medium", "style"),
        Output("pref-btn-hurst-long", "style"),
        Output("prefs-hurst-cur", "data"),
        Input("pref-btn-hurst-short", "n_clicks"),
        Input("pref-btn-hurst-medium", "n_clicks"),
        Input("pref-btn-hurst-long", "n_clicks"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        State("prefs-hurst-cur", "data"),
        prevent_initial_call=True,
    )
    def save_hurst(_s, _m, _l, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered:
            return (no_update,) * 6
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        hurst_map = {
            "pref-btn-hurst-short": "SHORT",
            "pref-btn-hurst-medium": "MEDIUM",
            "pref-btn-hurst-long": "LONG",
        }
        hurst = hurst_map.get(triggered, cur)
        styles = [_on() if value == hurst else _off() for value in ["SHORT", "MEDIUM", "LONG"]]
        if not uid:
            return "Not logged in", _msg_style("yellow"), *styles, hurst
        message, color = _save(uid, email, {"hurst_profile": hurst})
        return message, _msg_style(color), *styles, hurst

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("prefs-weis-cur", "data"),
        Input("prefs-weis-save", "n_clicks"),
        State("prefs-weis-slider", "value"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        prevent_initial_call=True,
    )
    def save_weis(_n, value, uid, email):
        if not uid:
            return "Not logged in", _msg_style("yellow"), value
        message, color = _save(uid, email, {"weis_threshold": value})
        return message, _msg_style(color), value

    @app.callback(
        Output("prefs-status", "children", allow_duplicate=True),
        Output("prefs-status", "style", allow_duplicate=True),
        Output("prefs-wl-cur", "data"),
        Output("prefs-wl-display", "children"),
        Output("prefs-sym-input", "value"),
        Input("prefs-sym-add", "n_clicks"),
        State("prefs-sym-input", "value"),
        State("prefs-wl-cur", "data"),
        State("prefs-uid", "data"),
        State("prefs-email", "data"),
        prevent_initial_call=True,
    )
    def add_symbol(_n, symbol, watchlist, uid, email):
        if not symbol:
            return no_update, no_update, watchlist, _render_watchlist(watchlist), ""
        clean_symbol = symbol.strip().upper()
        watchlist = list(watchlist or [])
        if clean_symbol and clean_symbol not in watchlist:
            watchlist.append(clean_symbol)
        if not uid:
            return "Not logged in", _msg_style("yellow"), watchlist, _render_watchlist(watchlist), ""
        message, color = _save(uid, email, {"watchlist": watchlist})
        return message, _msg_style(color), watchlist, _render_watchlist(watchlist), ""
