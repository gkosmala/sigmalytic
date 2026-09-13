# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/portfolio_tab.py
--------------------------
Portfolio Dashboard Tab for Sigmalytic V2.

REBUILT (2026-09-13): the previous version of this tab showed a
summary of Campaign Intelligence's own internally-generated
opportunities (position count vs. an optimal range, TIER/ODS
distribution, conjunction exits) -- confirmed via direct user
discussion this session to be a genuine, pre-existing naming/concept
mismatch: "Portfolio" should mean the trader's own real holdings, not
a summary of the app's own opportunity-tracking system. That system
(Campaign Intelligence) was separately archived earlier this session
for unrelated reasons, which is what originally surfaced this tab as
broken -- but the rebuild below is a genuine redesign around the
correct concept, not just a data-source swap.

This is now a real portfolio built from the trader's own open
positions (the same trade-entry data already captured by the Journal
tab's "Log New Trade" form), showing three things the Journal tab
does not already cover -- confirmed directly against
trade_journal_tab.py before building this, so nothing here duplicates
Journal's own closed-trade performance and behavioral scoring:
  - Live, unrealized P&L per open position (current price vs. the
    real entry price already on file)
  - Capital allocation: what share of total deployed capital sits in
    each open position
  - Sector exposure: open positions grouped by real Russell 1000
    sector classification, surfacing concentration risk a trader
    can't see from the Journal's trade-by-trade view alone

All three are computed server-side by /api/portfolio/summary
(backend/main.py), which reuses backend.heatmap_engine's existing,
already-trusted sector classification and the same parallelized,
rate-limit-aware fetch_bars_batch() already proven for the Weis Radar
scan.

Plugs into frontend/app.py:
  1. from portfolio_tab import build_portfolio_tab
  2. ("portfolio", "Portfolio") in ALL_TABS
  3. elif tab=="portfolio": main = build_portfolio_tab(session=session) in the tab router
"""

from __future__ import annotations

import os
import requests as _rq
from dash import html

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; BORDER_T = "rgba(45,143,111,.35)"
PURPLE    = "#a78bfa"

SECTOR_COLORS = [TEAL_DIM, BLUE_DIM, YELLOW_DIM, RED_DIM, PURPLE, "#f472b6", "#60a5fa", "#facc15"]


def _current_user_id(session=None) -> str:
    try:
        if session and isinstance(session, dict):
            return str(session.get("user_id") or session.get("id") or "anonymous")
    except Exception:
        pass
    return "anonymous"


def _auth_headers(session=None) -> dict:
    try:
        if session and isinstance(session, dict) and session.get("access_token"):
            return {"Authorization": f"Bearer {session['access_token']}"}
    except Exception:
        pass
    return {}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "padding": "20px", "marginBottom": "16px"}
    if sx: base.update(sx)
    return html.Div(children, style=base)


def _section(text):
    return html.Div(text, style={"fontSize": "11px", "fontWeight": "700", "color": MUTED,
                                  "textTransform": "uppercase", "letterSpacing": ".08em",
                                  "marginBottom": "14px"})


def _metric(label, value, color=WHITE, sub=""):
    return html.Div([
        html.Div(label, style={"fontSize": "10px", "color": MUTED, "fontWeight": "700",
                               "textTransform": "uppercase", "letterSpacing": ".08em"}),
        html.Div(value, style={"fontSize": "26px", "fontWeight": "900", "color": color,
                               "fontFamily": "DM Mono, monospace", "marginTop": "4px"}),
        html.Div(sub, style={"fontSize": "11px", "color": MUTED, "marginTop": "2px"}) if sub else html.Div(),
    ], style={"background": NAVY_MID, "border": f"1px solid {BORDER}", "borderRadius": "12px",
              "padding": "16px 20px", "flex": "1", "minWidth": "110px"})


def _hbar(label, pct, color=TEAL_DIM, sub=""):
    pct = max(0.0, min(100.0, pct))
    return html.Div([
        html.Div([
            html.Span(label, style={"fontSize": "12px", "color": TEXT, "fontWeight": "600"}),
            html.Span(f"{pct:.1f}%" + (f"  ·  {sub}" if sub else ""),
                      style={"fontSize": "12px", "color": color,
                             "fontWeight": "800", "fontFamily": "DM Mono, monospace"}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "5px"}),
        html.Div([html.Div(style={"width": f"{pct}%", "height": "6px", "background": color,
                                  "borderRadius": "3px"})],
                 style={"width": "100%", "height": "6px", "background": "rgba(255,255,255,.06)",
                        "borderRadius": "3px"}),
    ], style={"marginBottom": "12px"})


def _position_row(p: dict) -> html.Div:
    pnl = p.get("unrealized_pnl_pct")
    pnl_color = TEAL_DIM if (pnl or 0) >= 0 else RED_DIM
    pnl_text = f"{pnl:+.1f}%" if pnl is not None else "—"
    current = p.get("current_price")
    current_text = f"${current:.2f}" if current is not None else "—"

    return html.Div([
        html.Span(p.get("symbol", "—"), style={"fontSize": "13px", "fontWeight": "800",
                                                 "color": WHITE, "flex": "1"}),
        html.Span(p.get("direction", "—"), style={"fontSize": "11px", "color": MUTED, "flex": "0.7"}),
        html.Span(f"${p.get('entry_price', 0):.2f}", style={"fontSize": "12px", "color": TEXT,
                                                              "fontFamily": "DM Mono, monospace", "flex": "0.8"}),
        html.Span(current_text, style={"fontSize": "12px", "color": TEXT,
                                        "fontFamily": "DM Mono, monospace", "flex": "0.8"}),
        html.Span(pnl_text, style={"fontSize": "12px", "color": pnl_color, "fontWeight": "800",
                                    "fontFamily": "DM Mono, monospace", "flex": "0.7"}),
        html.Span(f"{p.get('allocation_pct', 0):.1f}%", style={"fontSize": "12px", "color": BLUE_DIM,
                                                                  "fontFamily": "DM Mono, monospace", "flex": "0.7"}),
        html.Span(p.get("sector", "Unknown"), style={"fontSize": "11px", "color": MUTED, "flex": "1"}),
    ], style={"display": "flex", "gap": "10px", "alignItems": "center",
              "padding": "10px 0", "borderBottom": f"1px solid {BORDER}"})


def build_portfolio_tab(session=None) -> html.Div:
    user_id = _current_user_id(session)

    def _do_fetch():
        r = _rq.get(f"{BACKEND_HTTP}/api/portfolio/summary", timeout=20,
                    headers=_auth_headers(session))
        return r.json() if r.ok else {}

    try:
        data = (
            shared_cache.get_or_fetch(f"/api/portfolio/summary:{user_id}", _do_fetch, ttl_seconds=30)
            if shared_cache is not None
            else _do_fetch()
        )
    except Exception:
        data = {}

    positions = data.get("positions", []) if isinstance(data, dict) else []
    total_capital = _safe_float(data.get("total_capital"))
    sector_exposure = data.get("sector_exposure", {}) if isinstance(data, dict) else {}

    if not positions:
        return html.Div([_card([
            html.Div([
                html.Div("Portfolio", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE}),
                html.Div(
                    "No open positions yet. Log a trade from the Journal tab, and it will appear "
                    "here with live P&L, capital allocation, and sector exposure.",
                    style={"color": TEXT, "fontSize": "13px", "marginTop": "8px", "maxWidth": "440px"}),
            ], style={"textAlign": "center", "padding": "48px"}),
        ])])

    avg_pnl = sum((p.get("unrealized_pnl_pct") or 0) for p in positions) / len(positions)
    avg_color = TEAL_DIM if avg_pnl >= 0 else RED_DIM

    return html.Div([

        # Row 1 — Overview
        _card([
            _section("Portfolio Overview"),
            html.Div([
                _metric("Open Positions", str(len(positions)), WHITE),
                _metric("Capital Deployed", f"${total_capital:,.0f}", WHITE),
                _metric("Avg Unrealized P&L", f"{avg_pnl:+.1f}%", avg_color, "across open positions"),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
        ]),

        # Row 2 — Open positions table
        _card([
            _section(f"Open Positions ({len(positions)})"),
            html.Div([
                html.Span("Symbol", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "1"}),
                html.Span("Dir", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "0.7"}),
                html.Span("Entry", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "0.8"}),
                html.Span("Current", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "0.8"}),
                html.Span("P&L", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "0.7"}),
                html.Span("Alloc.", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "0.7"}),
                html.Span("Sector", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "flex": "1"}),
            ], style={"display": "flex", "gap": "10px", "paddingBottom": "8px",
                      "borderBottom": f"1px solid {BORDER}", "marginBottom": "4px",
                      "textTransform": "uppercase", "letterSpacing": ".06em"}),
            html.Div([_position_row(p) for p in positions]),
        ]),

        # Row 3 — Sector exposure
        _card([
            _section("Sector Exposure"),
            html.Div([
                _hbar(sector, info.get("allocation_pct", 0),
                      SECTOR_COLORS[i % len(SECTOR_COLORS)],
                      sub=f"${info.get('capital', 0):,.0f}")
                for i, (sector, info) in enumerate(sector_exposure.items())
            ]) if sector_exposure else html.Div("No sector data available.",
                                                  style={"color": MUTED, "fontSize": "12px"}),
        ]),
    ])
