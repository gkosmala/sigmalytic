# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/campaign_tab.py
-------------------------
Campaign Intelligence Tab for Sigmalytic V2.

Displays all active campaigns with:
  - State, days open, tier
  - ODS (Operator Dominance Score)
  - P&F progress toward target
  - Entry price, current price, return %
  - Distribution risk indicator
  - Conjunction exit signal warning

Plugs into sigmalytic_app_TODAY.py:

  1. Import at top of app file:
       from campaign_tab import build_campaign_tab

  2. Add to ALL_TABS list:
       ("campaigns", "📊 Campaigns"),

  3. Add to tab router (in the render_tab callback):
       if tab == "campaigns":
           return build_campaign_tab(session=session)

Requires backend endpoint: GET /api/campaigns/active
(see campaign_api.py for the FastAPI router)
"""

from __future__ import annotations

import os
import requests as _rq
from dash import html

# ── Brand tokens (must match sigmalytic_app_TODAY.py) ────────────────────────
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; BORDER_T = "rgba(45,143,111,.35)"
PURPLE    = "#a78bfa"; PURPLE_GLOW = "rgba(167,139,250,.15)"

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")


# ── Helpers (mirrors patterns in main app) ────────────────────────────────────

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


def _label(text):
    return html.Span(text, style={
        "flex": "1", "fontSize": "9px", "color": MUTED,
        "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em",
    })


def _mono(text, color=None):
    return html.Span(text, style={
        "fontFamily": "DM Mono, monospace",
        "fontSize":   "13px",
        "color":      color or WHITE,
        "fontWeight": "600",
    })


# ── State color mapping ───────────────────────────────────────────────────────

_STATE_COLORS = {
    "BIRTH":             BLUE_DIM,
    "CONFIRMED":         TEAL_DIM,
    "SURVIVING":         TEAL_DIM,
    "EXPANDING":         YELLOW_DIM,
    "MATURING":          YELLOW,
    "DISTRIBUTION_RISK": RED_DIM,
    "CLOSED":            MUTED,
}

_STATE_ICONS = {
    "BIRTH":             "🌱",
    "CONFIRMED":         "✅",
    "SURVIVING":         "🛡️",
    "EXPANDING":         "🚀",
    "MATURING":          "📈",
    "DISTRIBUTION_RISK": "⚠️",
    "CLOSED":            "🔒",
}

_TIER_COLORS = {
    "TIER_1": TEAL_DIM,
    "TIER_2": BLUE_DIM,
    "TIER_3": YELLOW_DIM,
    "TIER_4": MUTED,
}


# ── ODS gauge bar ─────────────────────────────────────────────────────────────

def _ods_bar(ods_score: float) -> html.Div:
    """Render a compact horizontal ODS gauge."""
    pct   = min(100.0, max(0.0, float(ods_score or 0)))
    color = TEAL_DIM if pct >= 70 else (YELLOW_DIM if pct >= 40 else RED_DIM)
    return html.Div([
        html.Div(style={
            "width":         f"{pct}%",
            "height":        "4px",
            "background":    color,
            "borderRadius":  "2px",
            "transition":    "width .3s",
        }),
    ], style={
        "width":        "60px",
        "height":       "4px",
        "background":   "rgba(255,255,255,.08)",
        "borderRadius": "2px",
        "marginTop":    "4px",
    })


# ── P&F progress bar ──────────────────────────────────────────────────────────

def _pnf_bar(pct: float) -> html.Div:
    pct   = min(100.0, max(0.0, float(pct or 0)))
    color = TEAL_DIM if pct >= 75 else (YELLOW_DIM if pct >= 40 else BLUE_DIM)
    return html.Div([
        html.Div(style={
            "width":        f"{pct}%",
            "height":       "4px",
            "background":   color,
            "borderRadius": "2px",
        }),
    ], style={
        "width":        "60px",
        "height":       "4px",
        "background":   "rgba(255,255,255,.08)",
        "borderRadius": "2px",
        "marginTop":    "4px",
    })


# ── Campaign row ──────────────────────────────────────────────────────────────

def _campaign_row(c: dict) -> html.Div:
    state    = c.get("current_state", "BIRTH")
    symbol   = c.get("symbol", "—")
    tier     = c.get("historical_confidence", "—")
    days     = int(c.get("campaign_age_days", 0))
    ods      = float(c.get("operator_dominance") or 0)
    dist_r   = float(c.get("distribution_risk") or 0)
    entry    = float(c.get("entry_price") or 0)
    current  = float(c.get("current_price") or 0)
    pnf_t    = float(c.get("pnf_target") or 0)
    mfe90    = float(c.get("mfe90_expected") or 0)

    # Return %
    ret_pct  = ((current - entry) / entry * 100) if entry > 0 else 0.0
    ret_color = TEAL_DIM if ret_pct >= 0 else RED_DIM

    # P&F progress %
    pnf_span = pnf_t - entry
    pnf_pct  = ((current - entry) / pnf_span * 100) if pnf_span > 0 else 0.0

    state_color = _STATE_COLORS.get(state, MUTED)
    state_icon  = _STATE_ICONS.get(state, "•")
    tier_color  = _TIER_COLORS.get(tier, MUTED)

    # Conjunction exit warning
    conjunction = (ods < 40 and state in {"MATURING", "DISTRIBUTION_RISK"})

    row_bg = "rgba(239,68,68,.06)" if conjunction else "transparent"

    return html.Div([

        # Symbol + tier badge
        html.Div([
            html.Span(symbol, style={
                "fontFamily": "DM Mono, monospace",
                "fontSize":   "15px",
                "fontWeight": "900",
                "color":      WHITE,
            }),
            html.Span(tier, style={
                "fontSize":      "9px",
                "fontWeight":    "700",
                "color":         tier_color,
                "background":    f"rgba(255,255,255,.05)",
                "borderRadius":  "6px",
                "padding":       "2px 6px",
                "marginLeft":    "6px",
                "border":        f"1px solid {tier_color}30",
            }),
        ], style={"flex": "1.2", "display": "flex", "alignItems": "center"}),

        # State
        html.Div([
            html.Span(f"{state_icon} {state.replace('_', ' ')}", style={
                "fontSize":   "11px",
                "fontWeight": "700",
                "color":      state_color,
            }),
        ], style={"flex": "1.5"}),

        # Days open
        html.Div([
            _mono(f"Day {days}", BLUE_DIM),
        ], style={"flex": ".7"}),

        # Entry → Current → Return
        html.Div([
            html.Div(_mono(f"${entry:,.2f}", MUTED), style={"fontSize": "11px"}),
            html.Div([
                _mono(f"${current:,.2f}", WHITE),
                html.Span(f" {ret_pct:+.1f}%", style={
                    "fontSize":   "11px",
                    "fontWeight": "700",
                    "color":      ret_color,
                    "marginLeft": "4px",
                }),
            ], style={"display": "flex", "alignItems": "baseline"}),
        ], style={"flex": "1.2"}),

        # P&F progress
        html.Div([
            html.Div(f"{pnf_pct:.0f}% of target", style={
                "fontSize": "11px", "color": TEXT,
            }),
            _pnf_bar(pnf_pct),
        ], style={"flex": "1"}),

        # ODS
        html.Div([
            html.Div(f"ODS {ods:.0f}", style={
                "fontSize":   "11px",
                "fontWeight": "700",
                "color":      TEAL_DIM if ods >= 70 else (YELLOW_DIM if ods >= 40 else RED_DIM),
            }),
            _ods_bar(ods),
        ], style={"flex": ".8"}),

        # mfe90 expectation
        html.Div([
            _mono(f"{mfe90:.1f}%", PURPLE),
        ], style={"flex": ".8"}),

        # Conjunction exit warning
        html.Div([
            html.Span("⚡ EXIT", style={
                "fontSize":     "10px",
                "fontWeight":   "800",
                "color":        RED_DIM,
                "background":   RED_GLOW,
                "borderRadius": "6px",
                "padding":      "3px 8px",
                "border":       f"1px solid {RED_DIM}40",
            }) if conjunction else html.Span("—", style={"color": MUTED, "fontSize": "11px"}),
        ], style={"flex": ".8", "textAlign": "center"}),

    ], style={
        "display":      "flex",
        "alignItems":   "center",
        "gap":          "12px",
        "padding":      "14px 0",
        "borderBottom": f"1px solid {BORDER}",
        "background":   row_bg,
        "borderRadius": "4px",
    })


# ── Summary metrics row ───────────────────────────────────────────────────────

def _summary_tile(label: str, value: str, color: str = WHITE) -> html.Div:
    return html.Div([
        html.Div(label, style={"fontSize": "10px", "color": MUTED, "fontWeight": "700",
                               "textTransform": "uppercase", "letterSpacing": ".08em"}),
        html.Div(value, style={"fontSize": "22px", "fontWeight": "900", "color": color,
                               "marginTop": "4px", "fontFamily": "DM Mono, monospace"}),
    ], style={
        "background":   NAVY_MID,
        "border":       f"1px solid {BORDER}",
        "borderRadius": "12px",
        "padding":      "16px 20px",
        "minWidth":     "120px",
    })


# ── Main tab builder ──────────────────────────────────────────────────────────

def build_campaign_tab(session=None) -> html.Div:
    """
    Build the Campaign Intelligence tab.
    Fetches active campaigns from the backend API.
    """
    try:
        fetch_error = None
        r = _rq.get(f"{BACKEND_HTTP}/api/campaigns/active", timeout=20)
        if r.ok:
            _d = r.json()
            campaigns = _d.get("campaigns", []) if isinstance(_d, dict) else (_d if isinstance(_d, list) else [])
        else:
            campaigns = []
            fetch_error = f"Backend {r.status_code}"
    except Exception as _fe:
        fetch_error = str(_fe)
        campaigns = []

    # ── Summary metrics ───────────────────────────────────────────────────
    total     = len(campaigns)
    tier1     = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier2     = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    exits     = sum(1 for c in campaigns
                    if float(c.get("operator_dominance") or 100) < 40
                    and c.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"})
    avg_ods   = (
        sum(float(c.get("operator_dominance") or 0) for c in campaigns) / total
        if total else 0
    )

    state_counts: dict[str, int] = {}
    for c in campaigns:
        s = c.get("current_state", "BIRTH")
        state_counts[s] = state_counts.get(s, 0) + 1

    summary_row = html.Div([
        _summary_tile("Active",       str(total),          WHITE),
        _summary_tile("TIER 1",       str(tier1),          TEAL_DIM),
        _summary_tile("TIER 2",       str(tier2),          BLUE_DIM),
        _summary_tile("Avg ODS",      f"{avg_ods:.0f}",    TEAL_DIM if avg_ods >= 60 else YELLOW_DIM),
        _summary_tile("Exit Signals", str(exits),          RED_DIM if exits > 0 else MUTED),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "20px", "flexWrap": "wrap"})

    # ── State breakdown ───────────────────────────────────────────────────
    state_badges = html.Div([
        html.Span([
            html.Span(f"{_STATE_ICONS.get(s, '•')} {s.replace('_', ' ')}",
                      style={"fontSize": "11px", "fontWeight": "700",
                             "color": _STATE_COLORS.get(s, MUTED)}),
            html.Span(f" ({n})", style={"fontSize": "11px", "color": MUTED}),
        ], style={
            "background":   "rgba(255,255,255,.04)",
            "borderRadius": "8px",
            "padding":      "4px 10px",
            "border":       f"1px solid {BORDER}",
        })
        for s, n in sorted(state_counts.items(), key=lambda x: x[1], reverse=True)
    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "20px"})

    # ── Table header ──────────────────────────────────────────────────────
    header = html.Div([
        _label("Symbol / Tier"),
        _label("State"),
        _label("Age"),
        _label("Entry → Price"),
        _label("P&F Progress"),
        _label("ODS"),
        _label("mfe90 Exp"),
        _label("Signal"),
    ], style={
        "display":       "flex",
        "gap":           "12px",
        "paddingBottom": "10px",
        "borderBottom":  f"1px solid {BORDER}",
        "marginBottom":  "4px",
    })

    # ── Campaign rows ─────────────────────────────────────────────────────
    if campaigns:
        # Sort: conjunction exits first, then by TIER, then by days open
        def _sort_key(c):
            ods   = float(c.get("operator_dominance") or 100)
            state = c.get("current_state", "BIRTH")
            conj  = 1 if (ods < 40 and state in {"MATURING", "DISTRIBUTION_RISK"}) else 0
            tier  = c.get("historical_confidence", "TIER_4")
            tier_n = {"TIER_1": 0, "TIER_2": 1, "TIER_3": 2, "TIER_4": 3}.get(tier, 4)
            return (-conj, tier_n, -int(c.get("campaign_age_days", 0)))

        campaigns_sorted = sorted(campaigns, key=_sort_key)
        rows = [_campaign_row(c) for c in campaigns_sorted]
    else:
        error_msg = f"API error: {fetch_error}" if fetch_error else (
            "The signal birth engine runs nightly at 20:30 UTC. "
            "Check back after the first run."
        )
        rows = [html.Div([
            html.Div("🌱", style={"fontSize": "32px", "marginBottom": "12px"}),
            html.Div("No active campaigns yet.", style={
                "color": WHITE, "fontSize": "16px", "fontWeight": "700",
            }),
            html.Div(error_msg,
                style={"color": RED_DIM if fetch_error else TEXT,
                       "fontSize": "13px", "marginTop": "8px"}),
            html.Div(f"Backend: {BACKEND_HTTP}",
                style={"color": MUTED, "fontSize": "11px", "marginTop": "4px"}),
        ], style={
            "textAlign":  "center",
            "padding":    "48px 24px",
            "color":      MUTED,
        })]

    return html.Div([
        _card([
            html.Div([
                html.H2("📊 Campaign Intelligence", style={
                    "color": WHITE, "fontSize": "18px",
                    "fontWeight": "900", "margin": "0 0 4px",
                }),
                html.P(
                    "Active institutional campaigns — lifecycle state, "
                    "operator dominance, and P&F progress.",
                    style={"color": TEXT, "fontSize": "13px", "margin": "0 0 20px"},
                ),
            ]),
            summary_row,
            state_badges,
            header,
            html.Div(rows),
        ]),
    ])
