# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/portfolio_tab.py
--------------------------
Portfolio Dashboard Tab for Sigmalytic V2.

Shows the complete portfolio picture across all active campaigns:
  - Position count vs 20-25 optimal range (Phase 11)
  - Capital deployed vs available
  - State breakdown across lifecycle stages
  - TIER distribution
  - ODS distribution (operator dominance health)
  - Top performers and watch list
  - Conjunction exit signals

Plugs into sigmalytic_app_TODAY.py:
  1. from portfolio_tab import build_portfolio_tab
  2. Add ("portfolio", "Portfolio") to ALL_TABS
  3. Add elif tab=="portfolio": main = build_portfolio_tab() to tab router
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

OPTIMAL_MIN = 20
OPTIMAL_MAX = 25

STATE_ORDER = ["BIRTH","CONFIRMED","SURVIVING","EXPANDING","MATURING","DISTRIBUTION_RISK"]
STATE_COLORS = {
    "BIRTH": BLUE_DIM, "CONFIRMED": TEAL_DIM, "SURVIVING": TEAL_DIM,
    "EXPANDING": YELLOW_DIM, "MATURING": YELLOW, "DISTRIBUTION_RISK": RED_DIM,
}


def _safe_float(value, default=0.0):
    """
    Like float(value or default), but also handles the case dict.get(key, 0)
    does NOT protect against: an explicit `null` in the backend JSON, where
    the key exists but its value is None. .get(key, default) only supplies
    default when the key is missing entirely.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    return int(_safe_float(value, default))


STATE_ICONS = {
    "BIRTH": "", "CONFIRMED": "", "SURVIVING": "",
    "EXPANDING": "", "MATURING": "", "DISTRIBUTION_RISK": "",
}


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


def _hbar(label, value, max_val, color=TEAL_DIM):
    pct = min(100.0, value / max_val * 100) if max_val > 0 else 0
    return html.Div([
        html.Div([
            html.Span(label, style={"fontSize": "12px", "color": TEXT, "fontWeight": "600"}),
            html.Span(str(int(value)), style={"fontSize": "12px", "color": color,
                                              "fontWeight": "800", "fontFamily": "DM Mono, monospace"}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "5px"}),
        html.Div([html.Div(style={"width": f"{pct}%", "height": "5px", "background": color,
                                  "borderRadius": "3px"})],
                 style={"width": "100%", "height": "5px", "background": "rgba(255,255,255,.06)",
                        "borderRadius": "3px"}),
    ], style={"marginBottom": "10px"})


def _state_pill(state, count):
    color = STATE_COLORS.get(state, MUTED)
    icon  = STATE_ICONS.get(state, "•")
    return html.Div([
        html.Div(f"{icon} {count}", style={"fontSize": "20px", "fontWeight": "900",
                                           "color": color, "fontFamily": "DM Mono, monospace"}),
        html.Div(state.replace("_", " "), style={"fontSize": "9px", "color": MUTED,
                                                  "fontWeight": "700", "marginTop": "4px",
                                                  "textTransform": "uppercase", "letterSpacing": ".06em"}),
    ], style={"background": f"{color}11", "border": f"1px solid {color}30",
              "borderRadius": "10px", "padding": "10px 14px", "textAlign": "center", "minWidth": "80px"})


def _perf_row(c):
    symbol  = c.get("symbol", "—")
    tier    = c.get("historical_confidence", "—")
    ret_pct = _safe_float(c.get("return_pct"))
    days    = _safe_int(c.get("campaign_age_days"))
    state   = c.get("current_state", "BIRTH")
    color   = TEAL_DIM if ret_pct >= 0 else RED_DIM
    return html.Div([
        html.Span(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                 "fontSize": "13px", "color": WHITE, "flex": "1"}),
        html.Span(tier, style={"fontSize": "10px", "color": MUTED, "flex": ".8"}),
        html.Span(f"D{days}", style={"fontSize": "11px", "color": MUTED, "flex": ".5"}),
        html.Span(state.replace("_", " "), style={"fontSize": "10px", "color": STATE_COLORS.get(state, MUTED), "flex": "1.2"}),
        html.Span(f"{ret_pct:+.1f}%", style={"fontSize": "13px", "fontWeight": "800",
                                              "color": color, "fontFamily": "DM Mono, monospace",
                                              "flex": ".7", "textAlign": "right"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "8px",
              "padding": "8px 0", "borderBottom": f"1px solid {BORDER}"})


def build_portfolio_tab(session=None) -> html.Div:
    def _fetch_active():
        try:
            r = _rq.get(f"{BACKEND_HTTP}/api/campaigns/active", timeout=20)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    def _fetch_summary():
        try:
            r = _rq.get(f"{BACKEND_HTTP}/api/campaigns/summary", timeout=20)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    if shared_cache is not None:
        data = shared_cache.get_or_fetch("/api/campaigns/active", _fetch_active, ttl_seconds=120)
        summary = shared_cache.get_or_fetch("/api/campaigns/summary", _fetch_summary, ttl_seconds=120)
    else:
        data = _fetch_active()
        summary = _fetch_summary()

    campaigns = data.get("campaigns", []) if isinstance(data, dict) else []

    total      = len(campaigns)
    tier1      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier2      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    tier3      = total - tier1 - tier2
    avg_ods    = _safe_float(summary.get("avg_ods"))
    exits      = _safe_int(summary.get("conjunction_exits"))
    avg_return = _safe_float(summary.get("avg_return_pct"))
    ages       = [_safe_int(c.get("campaign_age_days")) for c in campaigns]
    avg_age    = sum(ages) / len(ages) if ages else 0

    state_counts: dict[str, int] = summary.get("state_breakdown", {})
    if not state_counts:
        for c in campaigns:
            s = c.get("current_state", "BIRTH")
            state_counts[s] = state_counts.get(s, 0) + 1

    ods_high = sum(1 for c in campaigns if float(c.get("operator_dominance") or 0) >= 70)
    ods_mid  = sum(1 for c in campaigns if 40 <= float(c.get("operator_dominance") or 0) < 70)
    ods_low  = sum(1 for c in campaigns if float(c.get("operator_dominance") or 0) < 40)

    cap_color  = TEAL_DIM if OPTIMAL_MIN <= total <= OPTIMAL_MAX else (YELLOW_DIM if total < OPTIMAL_MIN else RED_DIM)
    cap_label  = "OPTIMAL" if OPTIMAL_MIN <= total <= OPTIMAL_MAX else ("BUILDING" if total < OPTIMAL_MIN else "OVER")
    ret_color  = TEAL_DIM if avg_return >= 0 else RED_DIM

    if not campaigns:
        return html.Div([_card([
            html.Div([
                html.Div("", style={"fontSize": "40px", "marginBottom": "12px"}),
                html.Div("Portfolio Building", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE}),
                html.Div("Signal spark engine runs tonight at 20:30 UTC. Campaigns will appear here after the first scoring run.",
                         style={"color": TEXT, "fontSize": "13px", "marginTop": "8px", "maxWidth": "400px"}),
            ], style={"textAlign": "center", "padding": "48px"}),
        ])])

    return html.Div([

        # Row 1 — Key metrics
        _card([
            _section("Portfolio Overview"),
            html.Div([
                _metric("Campaigns", str(total), cap_color, f"{cap_label} · optimal {OPTIMAL_MIN}–{OPTIMAL_MAX}"),
                _metric("TIER 1", str(tier1), TEAL_DIM),
                _metric("TIER 2", str(tier2), BLUE_DIM),
                _metric("Avg Age", f"{avg_age:.0f}d", WHITE, "days open"),
                _metric("Avg Return", f"{avg_return:+.1f}%", ret_color, "open positions"),
                _metric("Avg ODS", f"{avg_ods:.0f}", TEAL_DIM if avg_ods >= 60 else YELLOW_DIM, "operator dominance"),
                _metric("Exit Signals", str(exits), RED_DIM if exits > 0 else MUTED, "conjunction exits"),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
        ]),

        # Row 2 — State breakdown + distributions
        html.Div([
            _card([
                _section("Campaign Lifecycle"),
                html.Div([
                    _state_pill(s, state_counts.get(s, 0))
                    for s in STATE_ORDER if state_counts.get(s, 0) > 0
                ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "20px"}),

                _section("TIER Distribution"),
                _hbar("TIER 1", tier1, max(total, 1), TEAL_DIM),
                _hbar("TIER 2", tier2, max(total, 1), BLUE_DIM),
                _hbar("TIER 3", tier3, max(total, 1), MUTED),
            ], sx={"flex": "1"}),

            _card([
                _section("Operator Dominance Distribution"),
                _hbar("High ODS ≥70 — Operator in control",  ods_high, max(total, 1), TEAL_DIM),
                _hbar("Mid ODS 40–70 — Mixed signals",        ods_mid,  max(total, 1), YELLOW_DIM),
                _hbar("Low ODS <40 — Operator exiting",       ods_low,  max(total, 1), RED_DIM),

                html.Div(style={"height": "1px", "background": BORDER, "margin": "16px 0"}),

                _section("Capacity"),
                html.Div([
                    html.Span(str(total), style={"fontSize": "40px", "fontWeight": "900",
                                                 "color": cap_color, "fontFamily": "DM Mono, monospace"}),
                    html.Span(f" / {OPTIMAL_MAX}", style={"fontSize": "20px", "color": MUTED}),
                ]),
                html.Div([html.Div(style={
                    "width": f"{min(100, total / OPTIMAL_MAX * 100):.0f}%",
                    "height": "8px", "background": cap_color, "borderRadius": "4px",
                })], style={"width": "100%", "height": "8px",
                            "background": "rgba(255,255,255,.06)", "borderRadius": "4px",
                            "marginTop": "10px"}),
                html.Div(f"Optimal range: {OPTIMAL_MIN}–{OPTIMAL_MAX} simultaneous positions (Phase 11)",
                         style={"fontSize": "11px", "color": MUTED, "marginTop": "8px"}),
            ], sx={"flex": "1"}),
        ], style={"display": "flex", "gap": "16px"}),

        # Row 3 — Top and watch
        _card([
            _section("Position Performance"),
            html.Div([
                html.Div([
                    html.Div("Top Performers", style={"fontSize": "12px", "color": TEAL_DIM,
                                                         "fontWeight": "800", "marginBottom": "10px"}),
                    *[_perf_row(c) for c in sorted(campaigns,
                       key=lambda x: _safe_float(x.get("return_pct")), reverse=True)[:6]],
                ], style={"flex": "1"}),
                html.Div(style={"width": "1px", "background": BORDER, "margin": "0 20px"}),
                html.Div([
                    html.Div("Watch List", style={"fontSize": "12px", "color": YELLOW_DIM,
                                                      "fontWeight": "800", "marginBottom": "10px"}),
                    *[_perf_row(c) for c in sorted(campaigns,
                       key=lambda x: _safe_float(x.get("return_pct")))[:6]],
                ], style={"flex": "1"}),
            ], style={"display": "flex"}),
        ]),

    ])
