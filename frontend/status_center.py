# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/status_center.py
--------------------------
Status Center — the first screen after login in Sigmalytic V2.

Per the blueprint (Part X):
  "The first screen is NOT a chart.
   The first screen is NOT a scanner.
   The first screen is NOT AI predictions.
   The first screen is: STATUS CENTER"

Contains four intelligence sections:
  1. Portfolio Intelligence  — active campaigns, P&L, ODS health
  2. Radar Intelligence      — today's top signals, Pre-Spark opportunities
  3. Opportunity Intelligence — new TIER_1 births, state changes, exits
  4. System Alerts           — decay monitor status, conjunction exits

Plugs into sigmalytic_app_TODAY.py:
  1. from status_center import build_status_center
  2. Add ("status", "⚡ Status") as FIRST entry in ALL_TABS
  3. Change dcc.Store(id="s-tab", data="status") to make it the default
  4. Add elif tab=="status": main = build_status_center() to tab router
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
import requests as _rq
from dash import html

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Brand tokens ──────────────────────────────────────────────────────────────
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"
PURPLE    = "#a78bfa"

OPTIMAL_MIN = 20
OPTIMAL_MAX = 25

STATE_COLORS = {
    "BIRTH": BLUE_DIM, "CONFIRMED": TEAL_DIM, "SURVIVING": TEAL_DIM,
    "EXPANDING": YELLOW_DIM, "MATURING": YELLOW, "DISTRIBUTION_RISK": RED_DIM,
}
STATE_ICONS = {
    "BIRTH": "🌱", "CONFIRMED": "✅", "SURVIVING": "🛡️",
    "EXPANDING": "🚀", "MATURING": "📈", "DISTRIBUTION_RISK": "⚠️",
}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "padding": "20px", "marginBottom": "16px"}
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _section(text, color=MUTED):
    return html.Div(text, style={
        "fontSize": "10px", "fontWeight": "700", "color": color,
        "textTransform": "uppercase", "letterSpacing": ".1em", "marginBottom": "12px",
    })


def _badge(text, color=TEAL_DIM):
    return html.Span(text, style={
        "fontSize": "10px", "fontWeight": "800", "color": color,
        "background": f"{color}18", "borderRadius": "6px",
        "padding": "2px 8px", "border": f"1px solid {color}35",
    })


def _kpi(label, value, color=WHITE, sub="", icon=""):
    return html.Div([
        html.Div([
            html.Span(icon + " " if icon else "", style={"fontSize": "14px"}),
            html.Span(label, style={"fontSize": "10px", "color": MUTED, "fontWeight": "700",
                                    "textTransform": "uppercase", "letterSpacing": ".08em"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),
        html.Div(value, style={"fontSize": "24px", "fontWeight": "900", "color": color,
                               "fontFamily": "DM Mono, monospace"}),
        html.Div(sub, style={"fontSize": "11px", "color": MUTED, "marginTop": "3px"}) if sub else html.Div(),
    ], style={
        "background": NAVY_MID, "border": f"1px solid {BORDER}",
        "borderRadius": "12px", "padding": "14px 16px", "flex": "1", "minWidth": "100px",
    })


def _alert_banner(text, level="YELLOW"):
    colors = {"YELLOW": YELLOW_DIM, "ORANGE": "#f97316", "RED": RED_DIM}
    color  = colors.get(level, YELLOW_DIM)
    icons  = {"YELLOW": "⚠️", "ORANGE": "🔶", "RED": "🚨"}
    icon   = icons.get(level, "⚠️")
    return html.Div([
        html.Span(f"{icon} {level} ALERT", style={
            "fontSize": "11px", "fontWeight": "800", "color": color,
            "marginRight": "12px",
        }),
        html.Span(text, style={"fontSize": "12px", "color": WHITE}),
    ], style={
        "background": f"{color}12", "border": f"1px solid {color}40",
        "borderRadius": "10px", "padding": "12px 16px",
        "display": "flex", "alignItems": "center", "marginBottom": "8px",
    })


def _campaign_mini(c: dict) -> html.Div:
    """Compact campaign row for Status Center."""
    symbol  = c.get("symbol", "—")
    state   = c.get("current_state", "BIRTH")
    tier    = c.get("historical_confidence", "—")
    ret_pct = float(c.get("return_pct", 0))
    ods     = float(c.get("operator_dominance") or 0)
    days    = int(c.get("campaign_age_days", 0))
    s_color = STATE_COLORS.get(state, MUTED)
    r_color = TEAL_DIM if ret_pct >= 0 else RED_DIM
    conj    = ods < 40 and state in {"MATURING", "DISTRIBUTION_RISK"}

    return html.Div([
        html.Span(STATE_ICONS.get(state, "•"), style={"fontSize": "13px", "marginRight": "6px"}),
        html.Span(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                 "fontSize": "13px", "color": WHITE, "flex": "1"}),
        html.Span(tier, style={"fontSize": "9px", "color": MUTED, "flex": ".8"}),
        html.Span(f"D{days}", style={"fontSize": "10px", "color": MUTED, "flex": ".5"}),
        html.Span(f"{ret_pct:+.1f}%", style={"fontSize": "12px", "fontWeight": "800",
                                              "color": r_color, "fontFamily": "DM Mono, monospace",
                                              "flex": ".7", "textAlign": "right"}),
        html.Span("⚡", style={"color": RED_DIM, "fontSize": "12px",
                               "marginLeft": "6px"}) if conj else html.Span(),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "6px",
        "padding": "7px 0", "borderBottom": f"1px solid {BORDER}",
    })


def _radar_mini(item: dict) -> html.Div:
    """Compact radar signal row."""
    symbol = item.get("symbol", "—")
    score  = float(item.get("score", 0))
    signal = item.get("signal_type", item.get("setup", "—"))
    s_color = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 45 else MUTED)
    return html.Div([
        html.Span(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                 "fontSize": "13px", "color": WHITE, "flex": "1"}),
        html.Span(str(signal)[:24], style={"fontSize": "11px", "color": TEXT, "flex": "2"}),
        html.Span(f"{score:.0f}", style={"fontSize": "13px", "fontWeight": "800",
                                         "color": s_color, "fontFamily": "DM Mono, monospace"}),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "10px",
        "padding": "7px 0", "borderBottom": f"1px solid {BORDER}",
    })


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch(path: str, timeout: int = 6) -> dict | list:
    try:
        r = _rq.get(f"{BACKEND_HTTP}{path}", timeout=timeout)
        return r.json() if r.ok else {}
    except Exception:
        return {}


# ── Main builder ──────────────────────────────────────────────────────────────

def build_status_center(session=None) -> html.Div:
    """Build the Status Center — first screen after login."""

    # ── Fetch all data ────────────────────────────────────────────────────
    campaign_data = _fetch("/api/campaigns/active")
    campaigns     = campaign_data.get("campaigns", []) if isinstance(campaign_data, dict) else []
    summary       = _fetch("/api/campaigns/summary")
    radar_data    = _fetch("/api/radar/top?limit=8")
    radar_items   = radar_data if isinstance(radar_data, list) else radar_data.get("signals", [])

    # ── Derived metrics ───────────────────────────────────────────────────
    total      = len(campaigns)
    tier1      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier2      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    avg_ods    = float(summary.get("avg_ods", 0))
    exits      = int(summary.get("conjunction_exits", 0))
    avg_return = float(summary.get("avg_return_pct", 0))
    state_counts: dict[str, int] = summary.get("state_breakdown", {})

    cap_color = (TEAL_DIM if OPTIMAL_MIN <= total <= OPTIMAL_MAX
                 else YELLOW_DIM if total < OPTIMAL_MIN else RED_DIM)
    cap_label = ("OPTIMAL" if OPTIMAL_MIN <= total <= OPTIMAL_MAX
                 else "BUILDING" if total < OPTIMAL_MIN else "OVER CAPACITY")
    ret_color = TEAL_DIM if avg_return >= 0 else RED_DIM

    # Most urgent campaigns — conjunction exits first, then distribution risk
    urgent = [c for c in campaigns
              if float(c.get("operator_dominance") or 100) < 40
              and c.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}]

    # Most active — expanding campaigns
    expanding = [c for c in campaigns if c.get("current_state") == "EXPANDING"]

    # New births — less than 3 days old
    new_births = [c for c in campaigns if int(c.get("campaign_age_days", 99)) <= 3]

    now_utc = datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")

    return html.Div([

        # ── Header ────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.H1("⚡ Status Center", style={
                    "fontSize": "22px", "fontWeight": "900", "color": WHITE, "margin": "0",
                }),
                html.Div(now_utc, style={"fontSize": "12px", "color": MUTED, "marginTop": "4px"}),
            ]),
            html.Div([
                _badge(f"● LIVE", TEAL_DIM),
                html.Span(f" {total} campaigns", style={"fontSize": "12px", "color": TEXT,
                                                         "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "20px"}),

        # ── System Alerts ─────────────────────────────────────────────────
        html.Div([
            *([_alert_banner(
                f"{exits} conjunction exit signal{'s' if exits > 1 else ''} — "
                f"operator exiting detected. Review campaign tab immediately.",
                "RED" if exits >= 3 else "ORANGE"
            )] if exits > 0 else []),
            *([_alert_banner(
                f"{len(new_births)} new campaign{'s' if len(new_births) > 1 else ''} "
                f"born in the last 3 days: "
                f"{', '.join(c.get('symbol','') for c in new_births[:5])}",
                "YELLOW"
            )] if new_births else []),
        ]) if exits > 0 or new_births else html.Div(),

        # ── Row 1: Portfolio KPIs ─────────────────────────────────────────
        _card([
            _section("📊 Portfolio Intelligence"),
            html.Div([
                _kpi("Campaigns", str(total), cap_color, cap_label),
                _kpi("TIER 1", str(tier1), TEAL_DIM, "highest conviction"),
                _kpi("TIER 2", str(tier2), BLUE_DIM, "strong conviction"),
                _kpi("Avg Return", f"{avg_return:+.1f}%", ret_color, "open positions"),
                _kpi("Avg ODS", f"{avg_ods:.0f}",
                     TEAL_DIM if avg_ods >= 60 else YELLOW_DIM, "operator dominance"),
                _kpi("Exit Signals", str(exits),
                     RED_DIM if exits > 0 else MUTED,
                     "conjunction exits" if exits > 0 else "all clear"),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
        ]),

        # ── Row 2: Three columns ──────────────────────────────────────────
        html.Div([

            # Column 1 — Active campaigns snapshot
            _card([
                _section("🛡️ Active Campaigns"),
                html.Div([
                    _campaign_mini(c)
                    for c in sorted(campaigns,
                        key=lambda x: (
                            -int(float(x.get("operator_dominance") or 100) < 40
                                 and x.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}),
                            -float(x.get("return_pct", 0))
                        ))[:8]
                ]) if campaigns else html.Div(
                    "No active campaigns yet. Signal birth runs at 20:30 UTC.",
                    style={"color": MUTED, "fontSize": "12px", "padding": "20px 0",
                           "textAlign": "center"}
                ),
                html.Div([
                    html.Div(style={"height": "1px", "background": BORDER, "margin": "12px 0"}),
                    html.Div([
                        *[html.Span([
                            html.Span(STATE_ICONS.get(s, "•") + " ", style={"fontSize": "11px"}),
                            html.Span(f"{state_counts.get(s, 0)}", style={
                                "fontWeight": "800", "color": STATE_COLORS.get(s, MUTED),
                                "fontFamily": "DM Mono, monospace", "fontSize": "12px",
                            }),
                            html.Span(f" {s.replace('_',' ')}", style={
                                "fontSize": "10px", "color": MUTED, "marginRight": "10px",
                            }),
                        ]) for s in ["BIRTH","CONFIRMED","SURVIVING","EXPANDING","MATURING","DISTRIBUTION_RISK"]
                           if state_counts.get(s, 0) > 0]
                    ], style={"display": "flex", "flexWrap": "wrap", "gap": "4px"}),
                ]) if campaigns else html.Div(),
            ], sx={"flex": "1.2"}),

            # Column 2 — Radar Intelligence
            _card([
                _section("📡 Radar Intelligence"),
                html.Div([
                    html.Div([
                        html.Span("Symbol", style={"fontSize": "9px", "color": MUTED,
                                                   "fontWeight": "700", "flex": "1",
                                                   "textTransform": "uppercase"}),
                        html.Span("Signal", style={"fontSize": "9px", "color": MUTED,
                                                   "fontWeight": "700", "flex": "2",
                                                   "textTransform": "uppercase"}),
                        html.Span("Score", style={"fontSize": "9px", "color": MUTED,
                                                  "fontWeight": "700",
                                                  "textTransform": "uppercase"}),
                    ], style={"display": "flex", "gap": "10px", "paddingBottom": "6px",
                              "borderBottom": f"1px solid {BORDER}", "marginBottom": "2px"}),
                    *[_radar_mini(item) for item in radar_items[:8]],
                ]) if radar_items else html.Div(
                    "Radar data loading...",
                    style={"color": MUTED, "fontSize": "12px", "padding": "20px 0",
                           "textAlign": "center"}
                ),
            ], sx={"flex": "1"}),

            # Column 3 — Opportunity Intelligence
            _card([
                _section("🎯 Opportunity Intelligence"),

                # New births
                html.Div([
                    html.Div("🌱 New Campaigns (last 3 days)", style={
                        "fontSize": "11px", "fontWeight": "800", "color": TEAL_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in new_births[:4]],
                    html.Div("No new campaigns", style={"color": MUTED, "fontSize": "11px"})
                    if not new_births else html.Div(),
                ]),

                html.Div(style={"height": "1px", "background": BORDER, "margin": "14px 0"}),

                # Expanding
                html.Div([
                    html.Div("🚀 Expanding (energy live)", style={
                        "fontSize": "11px", "fontWeight": "800", "color": YELLOW_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in expanding[:4]],
                    html.Div("None in expansion", style={"color": MUTED, "fontSize": "11px"})
                    if not expanding else html.Div(),
                ]),

                html.Div(style={"height": "1px", "background": BORDER, "margin": "14px 0"}),

                # Exit watch
                html.Div([
                    html.Div("⚡ Exit Watch", style={
                        "fontSize": "11px", "fontWeight": "800", "color": RED_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in urgent[:4]],
                    html.Div("✓ No exit signals", style={"color": TEAL_DIM, "fontSize": "11px"})
                    if not urgent else html.Div(),
                ]),

            ], sx={"flex": "1"}),

        ], style={"display": "flex", "gap": "16px"}),

        # ── Row 3: Nightly schedule status ────────────────────────────────
        _card([
            _section("⏱ Nightly Engine Schedule"),
            html.Div([
                *[html.Div([
                    html.Span(time, style={"fontFamily": "DM Mono, monospace", "fontSize": "12px",
                                          "color": BLUE_DIM, "fontWeight": "700",
                                          "minWidth": "55px"}),
                    html.Span(engine, style={"fontSize": "12px", "color": TEXT}),
                ], style={"display": "flex", "gap": "16px", "padding": "6px 0",
                          "borderBottom": f"1px solid {BORDER}"})
                for time, engine in [
                    ("20:00", "Geometry recalculation"),
                    ("20:30", "Signal birth engine — TIER scoring → new campaigns"),
                    ("21:00", "Campaign pipeline — FSM state updates"),
                    ("21:30", "ODS engine — operator dominance scores"),
                    ("21:45", "Analog engine — historical campaign matching"),
                    ("22:00", "Decay monitor — performance vs Phase 12B benchmarks"),
                    ("00:30", "EOD audit"),
                ]],
            ]),
        ]),

    ])
