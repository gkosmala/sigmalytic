# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/watchlist_radar.py
---------------------------
Subscriber Watchlist Radar for the Live Opportunity Center.

Purpose
-------
Give each subscriber a persistent, browser-local watchlist that is evaluated
against the latest completed Weis Radar universe snapshot.

Important boundary
------------------
This panel does NOT create synthetic signals and does NOT run a second radar
engine. It reuses the latest real universe scan already loaded by the Live
Opportunity Center. A watchlist symbol with no current Radar event is shown as
WATCHING / No active event.

The watchlist is stored in Dash dcc.Store(storage_type="local"), so it persists
in that browser/device without requiring a new backend account-storage schema.
"""

from __future__ import annotations

from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update

NAVY_CARD = "#0d1b2e"
NAVY_MID = "#0f172a"
TEAL = "#2dd4bf"
GREEN = "#34d399"
RED = "#f87171"
AMBER = "#f59e0b"
BLUE = "#60a5fa"
WHITE = "#f8fafc"
MUTED = "#cbd5e1"
SUBTLE = "#94a3b8"
BORDER = "rgba(148,163,184,.20)"
BORDER_T = "rgba(45,212,191,.42)"

TIMEFRAME_LABELS = {
    "1Hour": "1H",
    "2Hour": "2H",
    "4Hour": "4H",
    "1Day": "Daily",
    "1Week": "Weekly",
}

_WATCHLIST_CALLBACKS_REGISTERED = False


def _clean_symbol(value):
    s = str(value or "").strip().upper()
    return "".join(ch for ch in s if ch.isalnum() or ch in ".-")[:16]


def _context_triplet(primary_tf):
    tf = str(primary_tf or "2Hour")
    if tf in ("1Hour", "2Hour"):
        return "1Hour", "2Hour", "4Hour"
    if tf == "4Hour":
        return "2Hour", "4Hour", "1Day"
    return "4Hour", "1Day", "1Week"


def _stage_color(stage):
    return {
        "CONFIRMED": GREEN,
        "TRIGGERED": BLUE,
        "ARMED": AMBER,
        "BUILDING": MUTED,
        "INVALIDATED": RED,
        "WATCHING": SUBTLE,
    }.get(str(stage or "").upper(), MUTED)


def _direction_color(direction):
    d = str(direction or "").lower()
    if d.startswith("bull"):
        return GREEN
    if d.startswith("bear"):
        return RED
    return MUTED


def _row_map(snapshot):
    rows = (snapshot or {}).get("rows") or []
    return {
        _clean_symbol(row.get("symbol")): row
        for row in rows
        if _clean_symbol(row.get("symbol"))
    }


def _watchlist_rows(symbols, snapshot):
    rows_by_symbol = _row_map(snapshot)
    out = []
    for raw in symbols or []:
        symbol = _clean_symbol(raw)
        if not symbol:
            continue
        real = rows_by_symbol.get(symbol)
        if real:
            row = dict(real)
            row["watchlist_status"] = "ACTIVE"
        else:
            row = {
                "symbol": symbol,
                "direction": "Neutral",
                "stage": "WATCHING",
                "primary_tf": str(((snapshot or {}).get("config") or {}).get("timeframe") or "2Hour"),
                "event": "No active Radar event",
                "detected": None,
                "signal_count": 0,
                "watchlist_status": "QUIET",
            }
        out.append(row)
    return out


def _summary(symbols, snapshot):
    rows = _watchlist_rows(symbols, snapshot)
    active = sum(1 for r in rows if r.get("stage") not in ("WATCHING", None, ""))
    triggered = sum(1 for r in rows if str(r.get("stage")).upper() == "TRIGGERED")
    confirmed = sum(1 for r in rows if str(r.get("stage")).upper() == "CONFIRMED")

    def card(label, value, color):
        return html.Div(
            [
                html.Div(label, style={"fontSize": "9px", "fontWeight": "800", "color": MUTED, "letterSpacing": ".08em"}),
                html.Div(str(value), style={"fontSize": "22px", "fontWeight": "900", "color": color, "marginTop": "2px"}),
            ],
            style={
                "minWidth": "110px",
                "padding": "10px 12px",
                "background": NAVY_MID,
                "border": f"1px solid {BORDER}",
                "borderRadius": "10px",
            },
        )

    return html.Div(
        [
            card("WATCHLIST", len(rows), WHITE),
            card("ACTIVE EVENTS", active, TEAL if active else MUTED),
            card("TRIGGERED", triggered, BLUE if triggered else MUTED),
            card("CONFIRMED", confirmed, GREEN if confirmed else MUTED),
        ],
        style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
    )


def _table(symbols, snapshot):
    rows = _watchlist_rows(symbols, snapshot)
    if not rows:
        return html.Div(
            "Your Watchlist Radar is empty. Add a symbol to begin monitoring it against the latest completed universe scan.",
            style={"fontSize": "11px", "color": MUTED, "padding": "16px"},
        )

    header_style = {
        "fontSize": "9px",
        "fontWeight": "800",
        "color": SUBTLE,
        "letterSpacing": ".07em",
        "textTransform": "uppercase",
    }
    grid = "110px 90px 105px 90px minmax(180px,1fr) 72px"

    header = html.Div(
        [
            html.Div("Symbol", style=header_style),
            html.Div("Direction", style=header_style),
            html.Div("Stage", style=header_style),
            html.Div("Primary TF", style=header_style),
            html.Div("Current Event", style=header_style),
            html.Div("", style=header_style),
        ],
        style={
            "display": "grid",
            "gridTemplateColumns": grid,
            "gap": "10px",
            "padding": "8px 12px",
            "borderBottom": f"1px solid {BORDER}",
        },
    )

    body = []
    for row in rows:
        symbol = row["symbol"]
        stage = str(row.get("stage") or "WATCHING").upper()
        direction = row.get("direction") or "Neutral"
        body.append(
            html.Div(
                [
                    html.Button(
                        symbol,
                        id={"type": "loc-watchlist-open", "symbol": symbol},
                        n_clicks=0,
                        title=f"Load {symbol} into the linked three-chart workspace",
                        style={
                            "background": "rgba(45,212,191,.08)",
                            "border": f"1px solid {BORDER_T}",
                            "borderRadius": "8px",
                            "color": TEAL,
                            "fontSize": "11px",
                            "fontWeight": "900",
                            "padding": "6px 8px",
                            "cursor": "pointer",
                            "textAlign": "left",
                        },
                    ),
                    html.Div(direction, style={"fontSize": "10px", "fontWeight": "800", "color": _direction_color(direction)}),
                    html.Div(stage, style={"fontSize": "10px", "fontWeight": "900", "color": _stage_color(stage)}),
                    html.Div(TIMEFRAME_LABELS.get(row.get("primary_tf"), row.get("primary_tf") or "—"),
                             style={"fontSize": "10px", "color": WHITE}),
                    html.Div(row.get("event") or "—",
                             style={"fontSize": "10px", "color": MUTED, "overflow": "hidden", "textOverflow": "ellipsis"}),
                    html.Button(
                        "Remove",
                        id={"type": "loc-watchlist-remove", "symbol": symbol},
                        n_clicks=0,
                        style={
                            "background": "rgba(248,113,113,.08)",
                            "border": "1px solid rgba(248,113,113,.30)",
                            "borderRadius": "8px",
                            "color": RED,
                            "fontSize": "9px",
                            "fontWeight": "800",
                            "padding": "6px 7px",
                            "cursor": "pointer",
                        },
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": grid,
                    "gap": "10px",
                    "alignItems": "center",
                    "padding": "9px 12px",
                    "borderBottom": f"1px solid {BORDER}",
                    "background": "rgba(15,23,42,.24)",
                },
            )
        )

    return html.Div([header, *body], style={"maxHeight": "330px", "overflowY": "auto", "overflowX": "auto"})


def build_watchlist_radar(snapshot=None, current_symbol="AAPL"):
    button = {
        "height": "34px",
        "borderRadius": "9px",
        "border": f"1px solid {BORDER}",
        "background": NAVY_MID,
        "color": WHITE,
        "fontSize": "10px",
        "fontWeight": "800",
        "padding": "0 11px",
        "cursor": "pointer",
    }
    input_style = {
        "height": "34px",
        "width": "130px",
        "borderRadius": "9px",
        "border": f"1px solid {BORDER}",
        "background": NAVY_MID,
        "color": WHITE,
        "fontSize": "11px",
        "fontWeight": "800",
        "padding": "0 10px",
        "textTransform": "uppercase",
    }

    return html.Div(
        [
            dcc.Store(id="loc-watchlist-store", storage_type="local", data=[]),

            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Subscriber Watchlist Radar", style={"fontSize": "15px", "fontWeight": "900", "color": WHITE}),
                            html.Div(
                                "Monitor symbols you choose against the same real Radar lifecycle used by the universe scan.",
                                style={"fontSize": "10px", "color": MUTED, "marginTop": "2px"},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            dcc.Input(
                                id="loc-watchlist-input",
                                value="",
                                placeholder="Symbol",
                                debounce=True,
                                style=input_style,
                            ),
                            html.Button("Add Symbol", id="loc-watchlist-add", n_clicks=0,
                                        style={**button, "borderColor": BORDER_T, "color": TEAL}),
                            html.Button(
                                f"Add {current_symbol}",
                                id="loc-watchlist-add-chart",
                                n_clicks=0,
                                title="Add the symbol currently loaded in Chart 1",
                                style=button,
                            ),
                            html.Button("Clear", id="loc-watchlist-clear", n_clicks=0,
                                        style={**button, "color": RED, "borderColor": "rgba(248,113,113,.30)"}),
                        ],
                        style={"display": "flex", "gap": "7px", "flexWrap": "wrap", "alignItems": "center"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "12px",
                       "alignItems": "center", "flexWrap": "wrap", "padding": "14px"},
            ),

            html.Div(id="loc-watchlist-summary", children=_summary([], snapshot), style={"padding": "0 14px 10px"}),
            html.Div(id="loc-watchlist-table", children=_table([], snapshot)),
            html.Div(
                "WATCHING means the symbol is on your list but has no active event in the latest completed universe scan. "
                "Watchlist Radar does not invent a signal when none exists.",
                style={"fontSize": "9px", "color": SUBTLE, "padding": "9px 14px 12px"},
            ),
        ],
        style={
            "background": NAVY_CARD,
            "border": f"1px solid {BORDER_T}",
            "borderRadius": "14px",
            "overflow": "hidden",
            "marginBottom": "14px",
        },
    )


def register_watchlist_radar_callbacks(app):
    global _WATCHLIST_CALLBACKS_REGISTERED
    if _WATCHLIST_CALLBACKS_REGISTERED:
        return
    _WATCHLIST_CALLBACKS_REGISTERED = True

    @app.callback(
        Output("loc-watchlist-store", "data"),
        Input("loc-watchlist-add", "n_clicks"),
        Input("loc-watchlist-add-chart", "n_clicks"),
        Input("loc-watchlist-clear", "n_clicks"),
        Input({"type": "loc-watchlist-remove", "symbol": ALL}, "n_clicks"),
        State("loc-watchlist-input", "value"),
        State("loc-symbol-1", "value"),
        State("loc-watchlist-store", "data"),
        prevent_initial_call=True,
    )
    def _manage_watchlist(_add, _add_chart, _clear, _remove_clicks, typed_symbol, chart_symbol, current):
        trigger = callback_context.triggered_id
        symbols = []
        for value in current or []:
            s = _clean_symbol(value)
            if s and s not in symbols:
                symbols.append(s)

        if trigger == "loc-watchlist-clear":
            return []

        if trigger == "loc-watchlist-add":
            symbol = _clean_symbol(typed_symbol)
            if not symbol or symbol in symbols:
                return no_update
            return (symbols + [symbol])[:50]

        if trigger == "loc-watchlist-add-chart":
            symbol = _clean_symbol(chart_symbol)
            if not symbol or symbol in symbols:
                return no_update
            return (symbols + [symbol])[:50]

        if isinstance(trigger, dict) and trigger.get("type") == "loc-watchlist-remove":
            symbol = _clean_symbol(trigger.get("symbol"))
            return [s for s in symbols if s != symbol]

        return no_update

    @app.callback(
        Output("loc-watchlist-summary", "children"),
        Output("loc-watchlist-table", "children"),
        Input("loc-watchlist-store", "data"),
        Input("loc-opportunity-store", "data"),
    )
    def _render_watchlist(symbols, snapshot):
        return _summary(symbols or [], snapshot or {}), _table(symbols or [], snapshot or {})

    @app.callback(
        Output("loc-link-mode", "data", allow_duplicate=True),
        Output("loc-symbol-1", "value", allow_duplicate=True),
        Output("loc-symbol-2", "value", allow_duplicate=True),
        Output("loc-symbol-3", "value", allow_duplicate=True),
        Output("loc-tf-1", "value", allow_duplicate=True),
        Output("loc-tf-2", "value", allow_duplicate=True),
        Output("loc-tf-3", "value", allow_duplicate=True),
        Output("loc-primary-tf", "data", allow_duplicate=True),
        Output("loc-selected-opportunity", "data", allow_duplicate=True),
        Input({"type": "loc-watchlist-open", "symbol": ALL}, "n_clicks"),
        State("loc-opportunity-store", "data"),
        prevent_initial_call=True,
    )
    def _open_watchlist_symbol(_clicks, snapshot):
        trigger = callback_context.triggered_id
        if not isinstance(trigger, dict) or trigger.get("type") != "loc-watchlist-open":
            return (no_update,) * 9

        symbol = _clean_symbol(trigger.get("symbol"))
        if not symbol:
            return (no_update,) * 9

        rows = (snapshot or {}).get("rows") or []
        real = next((r for r in rows if _clean_symbol(r.get("symbol")) == symbol), None)
        primary_tf = str((real or {}).get("primary_tf") or ((snapshot or {}).get("config") or {}).get("timeframe") or "2Hour")
        tf1, tf2, tf3 = _context_triplet(primary_tf)

        selected = real or {
            "symbol": symbol,
            "direction": "Neutral",
            "stage": "WATCHING",
            "primary_tf": primary_tf,
            "event": "No active Radar event",
            "detected": None,
            "signal_count": 0,
        }

        return True, symbol, symbol, symbol, tf1, tf2, tf3, primary_tf, selected
