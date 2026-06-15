# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/portfolio_tab.py
--------------------------
Portfolio Intelligence Dashboard for Sigmalytic V2.

Shows the Phase 11 portfolio view:
  - Active position count vs 20-25 optimal range
  - Capital deployed vs available
  - Average ODS across portfolio
  - Campaign state distribution
  - Sector concentration
  - Closed campaign performance (win rate, avg return)
  - Half-Kelly deployment status

Plugs into sigmalytic_app_TODAY.py:

  1. Import:
       from portfolio_tab import build_portfolio_tab

  2. Add to ALL_TABS:
       ("portfolio", "💼 Portfolio"),

  3. Add to tab router:
       elif tab == "portfolio":
           return build_portfolio_tab(session=session)

Requires:
  GET /api/campaigns/active   — active campaigns
  GET /api/campaigns/summary  — portfolio stats
"""

from __future__ import annotations

import os
import requests as _rq
from dash import html

# ── Brand tokens ──────────────────────────────────────────────────────────────
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; BORDER_T = "rgba(45,143,111,.35)"
PURPLE    = "#a78bfa"; PURPLE_GLOW = "rgba(167,139,250,.15)"
ORANGE    = "#fb923c"

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# Phase 11 optimal portfolio parameters
OPTIMAL_MIN_POSITIONS = 20
OPTIMAL_MAX_POSITIONS = 25
MAX_POSITIONS         = 30


# ── UI helpers ────────────────────────────────────────────────────────────────

def _card(children, sx=None):
    base = {
        "background":   NAVY_CARD,
        "border":       f"1px solid {BORDER}",
        "borderRadius": "16px",
        "padding":      "20px",
        "marginBottom": "16px",
    }
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _section_title(text: str) -> html.Div:
    return html.Div(text, style={
        "fontSize":      "11px",
        "fontWeight":    "700",
        "color":         MUTED,
        "textTransform": "uppercase",
        "letterSpacing": ".08em",
        "marginBottom":  "14px",
    })


def _metric(label: str, value: str, color: str = WHITE, sub: str = "") -> html.Div:
    return html.Div([
        html.Div(label, style={
            "fontSize": "10px", "color": MUTED, "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": ".08em",
        }),
        html.Div(value, style={
            "fontSize": "26px", "fontWeight": "900", "color": color,
            "marginTop": "4px", "fontFamily": "DM Mono, monospace",
        }),
        html.Div(sub, style={"fontSize": "11px", "color": TEXT, "marginTop": "2px"}) if sub else None,
    ], style={
        "background":   NAVY_MID,
        "border":       f"1px solid {BORDER}",
        "borderRadius": "12px",
        "padding":      "16px 20px",
        "minWidth":     "130px",
        "flex":         "1",
    })


def _hbar(pct: float, color: str, height: str = "8px") -> html.Div:
    """Horizontal progress bar."""
    pct = min(100.0, max(0.0, float(pct)))
    return html.Div([
        html.Div(style={
            "width":        f"{pct}%",
            "height":       height,
            "background":   color,
            "borderRadius": "4px",
            "transition":   "width .4s",
        }),
    ], style={
        "width":        "100%",
        "height":       height,
        "background":   "rgba(255,255,255,.06)",
        "borderRadius": "4px",
        "marginTop":    "6px",
    })


# ── Position count gauge ──────────────────────────────────────────────────────

def _position_gauge(active: int) -> html.Div:
    """
    Visual gauge showing position count vs Phase 11 optimal range (20-25).
    Green zone: 20-25. Yellow: 15-19 or 26-28. Red: <15 or >28.
    """
    pct = active / MAX_POSITIONS * 100

    if OPTIMAL_MIN_POSITIONS <= active <= OPTIMAL_MAX_POSITIONS:
        color = TEAL_DIM
        status = "Optimal Range"
        status_color = TEAL_DIM
    elif active < OPTIMAL_MIN_POSITIONS:
        color = YELLOW_DIM
        status = f"Below Optimal ({OPTIMAL_MIN_POSITIONS - active} more needed)"
        status_color = YELLOW_DIM
    else:
        color = RED_DIM
        status = f"Above Optimal ({active - OPTIMAL_MAX_POSITIONS} over max)"
        status_color = RED_DIM

    # Build tick marks at 20 and 25
    return html.Div([
        html.Div([
            html.Span(f"{active}", style={
                "fontSize": "42px", "fontWeight": "900",
                "color": color, "fontFamily": "DM Mono, monospace",
            }),
            html.Span(f" / {MAX_POSITIONS}", style={
                "fontSize": "18px", "color": MUTED, "fontWeight": "600",
            }),
        ]),
        html.Div(style={"position": "relative", "marginTop": "12px"})[
            html.Div(style={
                "width": "100%", "height": "12px",
                "background": "rgba(255,255,255,.06)",
                "borderRadius": "6px", "position": "relative", "overflow": "hidden",
            })[
                html.Div(style={
                    "width":        f"{pct}%",
                    "height":       "12px",
                    "background":   color,
                    "borderRadius": "6px",
                    "transition":   "width .4s",
                })
            ],
        ] if False else html.Div([
            html.Div([
                html.Div(style={
                    "width": f"{pct}%", "height": "12px",
                    "background": color, "borderRadius": "6px",
                }),
            ], style={
                "width": "100%", "height": "12px",
                "background": "rgba(255,255,255,.06)",
                "borderRadius": "6px", "overflow": "hidden",
            }),
            # Optimal zone markers
            html.Div([
                html.Div(style={
                    "position": "absolute",
                    "left": f"{OPTIMAL_MIN_POSITIONS / MAX_POSITIONS * 100}%",
                    "top": "0", "width": "2px", "height": "12px",
                    "background": TEAL_DIM, "opacity": "0.6",
                }),
                html.Div(style={
                    "position": "absolute",
                    "left": f"{OPTIMAL_MAX_POSITIONS / MAX_POSITIONS * 100}%",
                    "top": "0", "width": "2px", "height": "12px",
                    "background": TEAL_DIM, "opacity": "0.6",
                }),
            ], style={"position": "relative"}),
            html.Div([
                html.Span("0", style={"color": MUTED, "fontSize": "10px"}),
                html.Span(f"Optimal: {OPTIMAL_MIN_POSITIONS}-{OPTIMAL_MAX_POSITIONS}",
                          style={"color": TEAL_DIM, "fontSize": "10px", "fontWeight": "700"}),
                html.Span(str(MAX_POSITIONS), style={"color": MUTED, "fontSize": "10px"}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginTop": "6px"}),
        ]),
        html.Div(status, style={
            "fontSize": "12px", "fontWeight": "700",
            "color": status_color, "marginTop": "8px",
        }),
    ])


# ── Sector distribution ───────────────────────────────────────────────────────

def _sector_bar(sector: str, count: int, total: int) -> html.Div:
    pct   = count / total * 100 if total > 0 else 0
    color = TEAL_DIM if pct <= 25 else (YELLOW_DIM if pct <= 40 else RED_DIM)
    return html.Div([
        html.Div([
            html.Span(sector, style={"fontSize": "12px", "color": WHITE, "fontWeight": "600"}),
            html.Span(f"{count} ({pct:.0f}%)", style={"fontSize": "11px", "color": MUTED}),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "4px"}),
        _hbar(pct, color, "6px"),
    ], style={"marginBottom": "12px"})


# ── Closed campaign performance ───────────────────────────────────────────────

def _perf_row(label: str, value: str, color: str = WHITE) -> html.Div:
    return html.Div([
        html.Span(label, style={"fontSize": "12px", "color": TEXT, "flex": "1"}),
        html.Span(value, style={
            "fontSize": "13px", "fontWeight": "700",
            "color": color, "fontFamily": "DM Mono, monospace",
        }),
    ], style={
        "display":       "flex",
        "justifyContent": "space-between",
        "alignItems":    "center",
        "padding":       "10px 0",
        "borderBottom":  f"1px solid {BORDER}",
    })


# ── Main tab builder ──────────────────────────────────────────────────────────

def build_portfolio_tab(session=None) -> html.Div:
    """Build the Portfolio Intelligence dashboard."""

    # ── Fetch data ────────────────────────────────────────────────────────
    try:
        r_active = _rq.get(f"{BACKEND_HTTP}/api/campaigns/active", timeout=8)
        active_data = r_active.json() if r_active.ok else {}
        campaigns   = active_data.get("campaigns", [])
    except Exception:
        campaigns = []

    try:
        r_summary = _rq.get(f"{BACKEND_HTTP}/api/campaigns/summary", timeout=8)
        summary = r_summary.json() if r_summary.ok else {}
    except Exception:
        summary = {}

    # ── Compute portfolio metrics ─────────────────────────────────────────
    active_count = len(campaigns)
    avg_ods      = float(summary.get("avg_ods", 0))
    avg_return   = float(summary.get("avg_return_pct", 0))
    exits        = int(summary.get("conjunction_exits", 0))
    tier_1       = int(summary.get("tier_1", 0))
    tier_2       = int(summary.get("tier_2", 0))

    # Average days open
    avg_days = (
        sum(int(c.get("campaign_age_days", 0)) for c in campaigns) / active_count
        if active_count else 0
    )

    # State breakdown
    state_counts: dict[str, int] = summary.get("state_breakdown", {})

    # Sector distribution (from symbol metadata if available, else N/A)
    # Placeholder — will populate once symbol_metadata is seeded
    sector_data: dict[str, int] = {}
    for c in campaigns:
        sector = c.get("sector", "Unknown")
        sector_data[sector] = sector_data.get(sector, 0) + 1

    # ODS color
    ods_color = TEAL_DIM if avg_ods >= 60 else (YELLOW_DIM if avg_ods >= 40 else RED_DIM)

    # Return color
    ret_color = TEAL_DIM if avg_return >= 0 else RED_DIM

    # Position count color
    pos_color = (
        TEAL_DIM if OPTIMAL_MIN_POSITIONS <= active_count <= OPTIMAL_MAX_POSITIONS
        else (YELLOW_DIM if active_count < OPTIMAL_MIN_POSITIONS else RED_DIM)
    )

    # ── Layout ────────────────────────────────────────────────────────────
    return html.Div([

        # ── Row 1: Key metrics ────────────────────────────────────────────
        _card([
            _section_title("Portfolio Overview"),
            html.Div([
                _metric("Active Campaigns", str(active_count), pos_color,
                        f"Optimal: {OPTIMAL_MIN_POSITIONS}-{OPTIMAL_MAX_POSITIONS}"),
                _metric("Avg ODS", f"{avg_ods:.0f}", ods_color, "Operator dominance"),
                _metric("Avg Return", f"{avg_return:+.1f}%", ret_color, "Open positions"),
                _metric("Exit Signals", str(exits), RED_DIM if exits > 0 else MUTED,
                        "Conjunction exits"),
                _metric("TIER 1", str(tier_1), TEAL_DIM, "Elite signals"),
                _metric("TIER 2", str(tier_2), BLUE_DIM, "Strong signals"),
                _metric("Avg Age", f"{avg_days:.0f}d", PURPLE, "Days open"),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
        ]),

        # ── Row 2: Position gauge + State breakdown ───────────────────────
        html.Div([

            # Position gauge
            _card([
                _section_title("Position Count"),
                _position_gauge(active_count),
                html.Div([
                    html.Div([
                        html.Span("■ ", style={"color": TEAL_DIM}),
                        html.Span("Optimal zone (20-25)", style={"fontSize": "11px", "color": TEXT}),
                    ]),
                    html.Div([
                        html.Span("■ ", style={"color": YELLOW_DIM}),
                        html.Span("Building / winding down", style={"fontSize": "11px", "color": TEXT}),
                    ]),
                    html.Div([
                        html.Span("■ ", style={"color": RED_DIM}),
                        html.Span("Overweight — no new positions", style={"fontSize": "11px", "color": TEXT}),
                    ]),
                ], style={"marginTop": "16px", "display": "flex", "flexDirection": "column", "gap": "6px"}),
            ], sx={"flex": "1"}),

            # State breakdown
            _card([
                _section_title("Campaign States"),
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span(
                                {
                                    "BIRTH":             "🌱",
                                    "CONFIRMED":         "✅",
                                    "SURVIVING":         "🛡️",
                                    "EXPANDING":         "🚀",
                                    "MATURING":          "📈",
                                    "DISTRIBUTION_RISK": "⚠️",
                                }.get(state, "•"),
                                style={"fontSize": "16px"},
                            ),
                            html.Div([
                                html.Div(state.replace("_", " "), style={
                                    "fontSize": "11px", "fontWeight": "700",
                                    "color": {
                                        "BIRTH":             BLUE_DIM,
                                        "CONFIRMED":         TEAL_DIM,
                                        "SURVIVING":         TEAL_DIM,
                                        "EXPANDING":         YELLOW_DIM,
                                        "MATURING":          YELLOW,
                                        "DISTRIBUTION_RISK": RED_DIM,
                                    }.get(state, MUTED),
                                }),
                                html.Div(f"{count} campaign{'s' if count != 1 else ''}",
                                         style={"fontSize": "10px", "color": MUTED}),
                            ], style={"marginLeft": "8px"}),
                        ], style={"display": "flex", "alignItems": "center"}),
                        html.Div(str(count), style={
                            "fontSize": "20px", "fontWeight": "900",
                            "color": WHITE, "fontFamily": "DM Mono, monospace",
                        }),
                    ], style={
                        "display":        "flex",
                        "justifyContent": "space-between",
                        "alignItems":     "center",
                        "padding":        "10px 0",
                        "borderBottom":   f"1px solid {BORDER}",
                    })
                    for state, count in sorted(
                        state_counts.items(),
                        key=lambda x: ["BIRTH","CONFIRMED","SURVIVING",
                                       "EXPANDING","MATURING","DISTRIBUTION_RISK"].index(x[0])
                        if x[0] in ["BIRTH","CONFIRMED","SURVIVING",
                                     "EXPANDING","MATURING","DISTRIBUTION_RISK"] else 99
                    )
                ] if state_counts else [
                    html.Div("No active campaigns", style={
                        "color": MUTED, "fontSize": "13px",
                        "padding": "24px 0", "textAlign": "center",
                    })
                ]),
            ], sx={"flex": "1"}),

        ], style={"display": "flex", "gap": "16px"}),

        # ── Row 3: Half-Kelly deployment status ───────────────────────────
        _card([
            _section_title("Half-Kelly Deployment Status"),
            html.Div([
                html.Div([
                    html.Div("Layer A (TIER_1)", style={
                        "fontSize": "12px", "color": TEXT, "marginBottom": "4px",
                    }),
                    html.Div([
                        html.Span(f"{tier_1} positions", style={
                            "fontSize": "14px", "fontWeight": "700", "color": TEAL_DIM,
                        }),
                        html.Span(" × 21.2% Half-Kelly", style={
                            "fontSize": "12px", "color": MUTED, "marginLeft": "6px",
                        }),
                    ]),
                    html.Div(
                        f"Max loss per position: -10% of position value",
                        style={"fontSize": "11px", "color": MUTED, "marginTop": "4px"},
                    ),
                ], style={
                    "flex": "1", "padding": "16px",
                    "background": TEAL_GLOW,
                    "borderRadius": "10px",
                    "border": f"1px solid {BORDER_T}",
                }),
                html.Div([
                    html.Div("Layer B (TIER_2)", style={
                        "fontSize": "12px", "color": TEXT, "marginBottom": "4px",
                    }),
                    html.Div([
                        html.Span(f"{tier_2} positions", style={
                            "fontSize": "14px", "fontWeight": "700", "color": BLUE_DIM,
                        }),
                        html.Span(" × 19.9% Half-Kelly", style={
                            "fontSize": "12px", "color": MUTED, "marginLeft": "6px",
                        }),
                    ]),
                    html.Div(
                        f"Max loss per position: -20% of position value",
                        style={"fontSize": "11px", "color": MUTED, "marginTop": "4px"},
                    ),
                ], style={
                    "flex": "1", "padding": "16px",
                    "background": "rgba(147,197,253,.06)",
                    "borderRadius": "10px",
                    "border": f"1px solid rgba(147,197,253,.2)",
                }),
                html.Div([
                    html.Div("Portfolio Capacity", style={
                        "fontSize": "12px", "color": TEXT, "marginBottom": "4px",
                    }),
                    html.Div([
                        html.Span(f"{active_count}", style={
                            "fontSize": "14px", "fontWeight": "700", "color": pos_color,
                        }),
                        html.Span(f" / {OPTIMAL_MAX_POSITIONS} positions", style={
                            "fontSize": "12px", "color": MUTED, "marginLeft": "6px",
                        }),
                    ]),
                    html.Div(
                        f"{max(0, OPTIMAL_MAX_POSITIONS - active_count)} slots remaining",
                        style={"fontSize": "11px", "color": MUTED, "marginTop": "4px"},
                    ),
                ], style={
                    "flex": "1", "padding": "16px",
                    "background": "rgba(255,255,255,.03)",
                    "borderRadius": "10px",
                    "border": f"1px solid {BORDER}",
                }),
            ], style={"display": "flex", "gap": "12px"}),
        ]),

        # ── Row 4: Conjunction exits warning (if any) ─────────────────────
        html.Div([
            _card([
                html.Div([
                    html.Span("⚡", style={"fontSize": "20px", "marginRight": "10px"}),
                    html.Div([
                        html.Div("Conjunction Exit Signals Active", style={
                            "fontSize": "14px", "fontWeight": "800", "color": RED_DIM,
                        }),
                        html.Div(
                            f"{exits} campaign{'s' if exits != 1 else ''} showing "
                            f"ODS < 40 in MATURING or DISTRIBUTION_RISK state. "
                            f"Review the Campaigns tab for details.",
                            style={"fontSize": "12px", "color": TEXT, "marginTop": "4px"},
                        ),
                    ]),
                ], style={"display": "flex", "alignItems": "flex-start"}),
            ], sx={
                "border":     f"1px solid {RED_DIM}40",
                "background": RED_GLOW,
            }),
        ]) if exits > 0 else html.Div(),

        # ── Empty state ───────────────────────────────────────────────────
        html.Div([
            _card([
                html.Div([
                    html.Div("💼", style={"fontSize": "32px", "marginBottom": "12px"}),
                    html.Div("Portfolio is empty.", style={
                        "color": WHITE, "fontSize": "16px", "fontWeight": "700",
                    }),
                    html.Div(
                        "The signal birth engine runs nightly at 20:30 UTC. "
                        "Campaigns will appear here after the first run.",
                        style={"color": TEXT, "fontSize": "13px", "marginTop": "8px"},
                    ),
                ], style={"textAlign": "center", "padding": "48px 24px"}),
            ]),
        ]) if active_count == 0 else html.Div(),

    ])
