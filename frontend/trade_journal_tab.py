# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/trade_journal_tab.py
------------------------------
Trade Journal Tab for Sigmalytic V2.

Shows:
  - Open positions with entry quality grades
  - Closed trades with full behavioral grades
  - Trader behavioral profile (patience, FOMO, sizing, consistency)
  - Log new trade form

Plugs into sigmalytic_app_TODAY.py:
  1. from trade_journal_tab import build_trade_journal_tab
  2. Add ("journal", "ðŸ““ Journal") to ALL_TABS
  3. Add elif tab=="journal": main = build_trade_journal_tab() to router
"""

from __future__ import annotations

import os
import requests as _rq
from dash import html, dcc

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL_DIM  = "#34d399"; RED_DIM   = "#f87171"; YELLOW_DIM = "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; PURPLE = "#a78bfa"

GRADE_COLORS = {
    "A": TEAL_DIM, "B": BLUE_DIM, "C": YELLOW_DIM, "D": "#f97316",
    "F": RED_DIM, "N/A": MUTED,
}


def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "padding": "20px", "marginBottom": "16px"}
    if sx: base.update(sx)
    return html.Div(children, style=base)


def _section(text):
    return html.Div(text, style={"fontSize": "10px", "fontWeight": "700", "color": MUTED,
                                  "textTransform": "uppercase", "letterSpacing": ".1em",
                                  "marginBottom": "12px"})


def _grade_pill(grade: str) -> html.Span:
    color = GRADE_COLORS.get(grade or "N/A", MUTED)
    return html.Span(grade or "â€”", style={
        "fontSize": "11px", "fontWeight": "900", "color": color,
        "background": f"{color}18", "borderRadius": "6px",
        "padding": "2px 8px", "border": f"1px solid {color}30",
        "fontFamily": "DM Mono, monospace",
    })


def _score_bar(score: float, color: str) -> html.Div:
    pct = min(100.0, max(0.0, float(score or 0)))
    return html.Div([
        html.Div(style={"width": f"{pct}%", "height": "4px",
                        "background": color, "borderRadius": "2px"}),
    ], style={"width": "60px", "height": "4px",
              "background": "rgba(255,255,255,.06)", "borderRadius": "2px"})


def _profile_stat(label: str, value: str, color: str = WHITE, bar_val: float = 0,
                  bar_color: str = TEAL_DIM) -> html.Div:
    return html.Div([
        html.Div([
            html.Span(label, style={"fontSize": "11px", "color": TEXT, "flex": "1"}),
            html.Span(value, style={"fontSize": "13px", "fontWeight": "800",
                                    "color": color, "fontFamily": "DM Mono, monospace"}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "4px"}),
        _score_bar(bar_val, bar_color),
    ], style={"marginBottom": "12px"})


def _trade_row(t: dict, is_open: bool = False) -> html.Div:
    symbol    = t.get("symbol", "â€”")
    direction = t.get("direction", "LONG")
    entry_p   = float(t.get("entry_price", 0))
    exit_p    = float(t.get("exit_price", 0))
    pnl_pct   = float(t.get("pnl_pct", 0))
    pnl       = float(t.get("pnl", 0))
    hold      = int(t.get("hold_days", 0))
    tier      = t.get("tier") or "â€”"
    eq        = t.get("entry_quality_grade") or "â€”"
    xq        = t.get("exit_quality_grade") or "â€”"
    patience  = float(t.get("patience_score", 0))
    fomo      = float(t.get("fomo_score", 0))
    entry_d   = t.get("entry_date", "â€”")
    exit_d    = t.get("exit_date", "â€”")

    dir_color = TEAL_DIM if direction == "LONG" else RED_DIM
    pnl_color = TEAL_DIM if pnl_pct >= 0 else RED_DIM

    return html.Div([
        # Symbol + direction
        html.Div([
            html.Div(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                    "fontSize": "14px", "color": WHITE}),
            html.Div([
                html.Span(direction, style={"fontSize": "9px", "color": dir_color,
                                            "fontWeight": "800"}),
                html.Span(f" Â· {tier}", style={"fontSize": "9px", "color": MUTED}),
            ]),
        ], style={"flex": "1"}),

        # Dates
        html.Div([
            html.Div(entry_d, style={"fontSize": "11px", "color": TEXT}),
            html.Div(exit_d if not is_open else "Open", style={"fontSize": "10px", "color": MUTED}),
        ], style={"flex": "1"}),

        # Prices
        html.Div([
            html.Div(f"${entry_p:,.2f}", style={"fontSize": "12px", "color": WHITE,
                                                  "fontFamily": "DM Mono, monospace"}),
            html.Div(f"${exit_p:,.2f}" if not is_open else "â€”",
                     style={"fontSize": "11px", "color": MUTED, "fontFamily": "DM Mono, monospace"}),
        ], style={"flex": "1"}),

        # P&L
        html.Div([
            html.Div(f"{pnl_pct:+.1f}%" if not is_open else "â€”",
                     style={"fontSize": "13px", "fontWeight": "800",
                            "color": pnl_color, "fontFamily": "DM Mono, monospace"}),
            html.Div(f"${pnl:+,.0f}" if not is_open else f"{hold}d held",
                     style={"fontSize": "10px", "color": MUTED}),
        ], style={"flex": ".8"}),

        # Entry quality
        html.Div([
            html.Div("Entry", style={"fontSize": "9px", "color": MUTED}),
            _grade_pill(eq),
        ], style={"flex": ".7", "textAlign": "center"}),

        # Exit quality
        html.Div([
            html.Div("Exit", style={"fontSize": "9px", "color": MUTED}),
            _grade_pill(xq) if not is_open else html.Span("â€”", style={"color": MUTED}),
        ], style={"flex": ".7", "textAlign": "center"}),

        # Patience
        html.Div([
            html.Div("Patience", style={"fontSize": "9px", "color": MUTED, "marginBottom": "4px"}),
            _score_bar(patience, TEAL_DIM if patience >= 60 else YELLOW_DIM),
            html.Div(f"{patience:.0f}", style={"fontSize": "10px", "color": MUTED,
                                               "marginTop": "2px"}),
        ], style={"flex": ".8"}),

        # FOMO
        html.Div([
            html.Div("FOMO", style={"fontSize": "9px", "color": MUTED, "marginBottom": "4px"}),
            _score_bar(fomo, RED_DIM if fomo >= 50 else (YELLOW_DIM if fomo >= 25 else TEAL_DIM)),
            html.Div(f"{fomo:.0f}", style={"fontSize": "10px", "color": MUTED, "marginTop": "2px"}),
        ], style={"flex": ".8"}),

    ], style={"display": "flex", "alignItems": "center", "gap": "10px",
              "padding": "12px 0", "borderBottom": f"1px solid {BORDER}"})


def _log_trade_form() -> html.Div:
    """Simple form to log a new trade entry."""
    inp = lambda id_, ph, typ="text": dcc.Input(
        id=id_, type=typ, placeholder=ph,
        style={"background": NAVY_MID, "border": f"1px solid {BORDER}", "borderRadius": "8px",
               "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
               "width": "100%", "outline": "none"},
    )
    return html.Div([
        _section("Log New Trade"),
        html.Div([
            html.Div([
                html.Div("Symbol", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                inp("jrn-symbol", "AAPL"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Entry Date", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                inp("jrn-entry-date", "2026-06-16", "date"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Entry Price", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                inp("jrn-entry-price", "182.50", "number"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Shares", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                inp("jrn-shares", "100", "number"),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Tier", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                dcc.Dropdown(
                    id="jrn-tier",
                    options=[
                        {"label": "TIER 1", "value": "TIER_1"},
                        {"label": "TIER 2", "value": "TIER_2"},
                        {"label": "TIER 3", "value": "TIER_3"},
                        {"label": "Manual", "value": None},
                    ],
                    placeholder="Select tier",
                    style={"background": NAVY_MID, "color": WHITE, "fontSize": "13px"},
                ),
            ], style={"flex": "1"}),
            html.Div([
                html.Div("Notes", style={"fontSize": "10px", "color": MUTED, "marginBottom": "4px"}),
                inp("jrn-notes", "Optional notes"),
            ], style={"flex": "2"}),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "14px"}),
        html.Div(id="jrn-submit-result"),
        html.Button("Log Trade Entry", id="jrn-submit", n_clicks=0, style={
            "background": TEAL_DIM, "color": NAVY, "border": "none",
            "borderRadius": "8px", "padding": "10px 24px", "fontWeight": "800",
            "fontSize": "13px", "cursor": "pointer",
        }),
    ])


def build_trade_journal_tab(session=None) -> html.Div:
    """Build the Trade Journal tab."""
    user_id = "demo_user_001"  # replaced with real user_id when auth is wired

    try:
        r = _rq.get(f"{BACKEND_HTTP}/api/journal/trades", timeout=8,
                    headers={"Authorization": "Bearer demo"})
        data   = r.json() if r.ok else {}
        trades = data.get("trades", []) if isinstance(data, dict) else []
    except Exception:
        trades = []

    try:
        r2     = _rq.get(f"{BACKEND_HTTP}/api/journal/profile", timeout=8,
                         headers={"Authorization": "Bearer demo"})
        profile = r2.json() if r2.ok else {}
    except Exception:
        profile = {}

    open_trades   = [t for t in trades if t.get("status") == "OPEN"]
    closed_trades = [t for t in trades if t.get("status") == "CLOSED"]

    total_trades  = len(closed_trades)
    wins          = sum(1 for t in closed_trades if float(t.get("pnl_pct", 0)) > 0)
    win_rate      = wins / total_trades * 100 if total_trades > 0 else 0
    avg_pnl       = sum(float(t.get("pnl_pct", 0)) for t in closed_trades) / total_trades if total_trades > 0 else 0
    avg_patience  = float(profile.get("avg_patience_score", 0))
    avg_fomo      = float(profile.get("avg_fomo_score", 0))
    trend         = profile.get("behavioral_trend", "â€”")
    trend_color   = TEAL_DIM if trend == "IMPROVING" else (YELLOW_DIM if trend == "STABLE" else RED_DIM)

    table_header = html.Div([
        *[html.Span(h, style={"fontSize": "9px", "color": MUTED, "fontWeight": "700",
                              "textTransform": "uppercase", "flex": f})
          for h, f in [("Symbol", "1"), ("Date", "1"), ("Price", "1"), ("P&L", ".8"),
                       ("Entry", ".7"), ("Exit", ".7"), ("Patience", ".8"), ("FOMO", ".8")]],
    ], style={"display": "flex", "gap": "10px", "paddingBottom": "8px",
              "borderBottom": f"1px solid {BORDER}", "marginBottom": "4px"})

    return html.Div([

        # â”€â”€ Behavioral Profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _card([
            _section("ðŸ“Š Trader Behavioral Profile"),
            html.Div([
                # Stats
                html.Div([
                    html.Div([
                        html.Div(str(total_trades), style={"fontSize": "32px", "fontWeight": "900",
                                                           "color": WHITE, "fontFamily": "DM Mono, monospace"}),
                        html.Div("Total Trades", style={"fontSize": "10px", "color": MUTED}),
                    ], style={"marginBottom": "16px"}),
                    _profile_stat("Win Rate", f"{win_rate:.0f}%",
                                  TEAL_DIM if win_rate >= 60 else YELLOW_DIM, win_rate, TEAL_DIM),
                    _profile_stat("Avg P&L", f"{avg_pnl:+.1f}%",
                                  TEAL_DIM if avg_pnl >= 0 else RED_DIM),
                    _profile_stat("Patience", f"{avg_patience:.0f}/100",
                                  TEAL_DIM if avg_patience >= 65 else YELLOW_DIM,
                                  avg_patience, TEAL_DIM),
                    _profile_stat("FOMO", f"{avg_fomo:.0f}/100",
                                  TEAL_DIM if avg_fomo < 30 else (YELLOW_DIM if avg_fomo < 50 else RED_DIM),
                                  avg_fomo, RED_DIM if avg_fomo >= 50 else YELLOW_DIM),
                ], style={"flex": "1"}),

                html.Div(style={"width": "1px", "background": BORDER, "margin": "0 20px"}),

                # Behavioral trend
                html.Div([
                    html.Div("Behavioral Trend", style={"fontSize": "10px", "color": MUTED,
                                                         "fontWeight": "700", "textTransform": "uppercase",
                                                         "letterSpacing": ".08em", "marginBottom": "12px"}),
                    html.Div(trend, style={"fontSize": "28px", "fontWeight": "900",
                                          "color": trend_color}),
                    html.Div(style={"height": "1px", "background": BORDER, "margin": "16px 0"}),
                    html.Div("Open Positions", style={"fontSize": "10px", "color": MUTED,
                                                       "marginBottom": "8px"}),
                    html.Div(str(len(open_trades)), style={"fontSize": "32px", "fontWeight": "900",
                                                           "color": BLUE_DIM,
                                                           "fontFamily": "DM Mono, monospace"}),
                    html.Div(style={"height": "1px", "background": BORDER, "margin": "16px 0"}),
                    html.Div("The platform learns how you trade.", style={
                        "fontSize": "12px", "color": MUTED, "fontStyle": "italic",
                        "lineHeight": "1.6",
                    }),
                ], style={"flex": "1"}),

            ], style={"display": "flex"}),
        ]),

        # â”€â”€ Log new trade â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _card([_log_trade_form()]),

        # â”€â”€ Open trades â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _card([
            _section(f"ðŸ“‚ Open Positions ({len(open_trades)})"),
            table_header,
            *[_trade_row(t, is_open=True) for t in open_trades],
            html.Div("No open positions.", style={"color": MUTED, "fontSize": "12px",
                                                   "padding": "16px 0", "textAlign": "center"})
            if not open_trades else html.Div(),
        ]),

        # â”€â”€ Closed trades â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        _card([
            _section(f"ðŸ“‹ Trade History ({len(closed_trades)})"),
            table_header,
            *[_trade_row(t, is_open=False) for t in closed_trades],
            html.Div("No closed trades yet.", style={"color": MUTED, "fontSize": "12px",
                                                      "padding": "16px 0", "textAlign": "center"})
            if not closed_trades else html.Div(),
        ]),

    ])

