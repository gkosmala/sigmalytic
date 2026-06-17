# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/campaign_tab.py
-------------------------
Campaign Intelligence Tab for Sigmalytic V2.

Phase 14D UI:
  - Lifecycle state
  - ODS
  - Decay score / band / reason
  - Transition next-state prediction
  - Advance / failure / continuation probabilities
  - Expected days / return / MFE / MAE
  - Transition bias
"""

from __future__ import annotations

import os
import requests as _rq
from dash import html

NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#64748b"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"; BORDER_T = "rgba(45,143,111,.35)"
PURPLE    = "#a78bfa"; PURPLE_GLOW = "rgba(167,139,250,.15)"

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")


def _card(children, sx=None):
    base = {
        "background": NAVY_CARD,
        "border": f"1px solid {BORDER}",
        "borderRadius": "16px",
        "padding": "20px",
        "marginBottom": "16px",
    }
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _label(text, flex="1"):
    return html.Span(text, style={
        "flex": flex,
        "fontSize": "9px",
        "color": MUTED,
        "fontWeight": "700",
        "textTransform": "uppercase",
        "letterSpacing": ".1em",
    })


def _mono(text, color=None, size="13px"):
    return html.Span(text, style={
        "fontFamily": "DM Mono, monospace",
        "fontSize": size,
        "color": color or WHITE,
        "fontWeight": "600",
    })


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


_STATE_COLORS = {
    "BIRTH": BLUE_DIM,
    "CONFIRMED": TEAL_DIM,
    "SURVIVING": TEAL_DIM,
    "EXPANDING": YELLOW_DIM,
    "MATURING": YELLOW,
    "DISTRIBUTION_RISK": RED_DIM,
    "CLOSED": MUTED,
}

_STATE_ICONS = {
    "BIRTH": "🌱",
    "CONFIRMED": "✅",
    "SURVIVING": "🛡️",
    "EXPANDING": "🚀",
    "MATURING": "📈",
    "DISTRIBUTION_RISK": "⚠️",
    "CLOSED": "🔒",
}

_TIER_COLORS = {
    "TIER_1": TEAL_DIM,
    "TIER_2": BLUE_DIM,
    "TIER_3": YELLOW_DIM,
    "TIER_4": MUTED,
}

_DECAY_COLORS = {
    "HEALTHY": TEAL_DIM,
    "MONITOR": YELLOW_DIM,
    "WEAKENING": RED_DIM,
    "EXIT_CANDIDATE": RED_DIM,
    "UNKNOWN": MUTED,
}

_BIAS_COLORS = {
    "ADVANCE_LIKELY": TEAL_DIM,
    "ADVANCE_EDGE": TEAL_DIM,
    "HOLDING_PATTERN": BLUE_DIM,
    "MIXED": YELLOW_DIM,
    "FAILURE_RISK": RED_DIM,
    "UNKNOWN": MUTED,
}

_BIAS_LABELS = {
    "ADVANCE_LIKELY": "↑ ADV LIKELY",
    "ADVANCE_EDGE": "↑ ADV EDGE",
    "HOLDING_PATTERN": "→ HOLD",
    "MIXED": "◇ MIXED",
    "FAILURE_RISK": "↓ FAIL RISK",
    "UNKNOWN": "—",
}


def _bar(pct: float, color: str, width="60px") -> html.Div:
    pct = min(100.0, max(0.0, float(pct or 0)))
    return html.Div([
        html.Div(style={
            "width": f"{pct}%",
            "height": "4px",
            "background": color,
            "borderRadius": "2px",
            "transition": "width .3s",
        }),
    ], style={
        "width": width,
        "height": "4px",
        "background": "rgba(255,255,255,.08)",
        "borderRadius": "2px",
        "marginTop": "4px",
    })


def _pill(label: str, color: str) -> html.Span:
    return html.Span(label, style={
        "fontSize": "10px",
        "fontWeight": "800",
        "color": color,
        "background": f"{color}18",
        "borderRadius": "6px",
        "padding": "3px 8px",
        "border": f"1px solid {color}40",
        "whiteSpace": "nowrap",
    })


def _summary_tile(label: str, value: str, color: str = WHITE, sub: str = "") -> html.Div:
    return html.Div([
        html.Div(label, style={
            "fontSize": "10px",
            "color": MUTED,
            "fontWeight": "700",
            "textTransform": "uppercase",
            "letterSpacing": ".08em",
        }),
        html.Div(value, style={
            "fontSize": "22px",
            "fontWeight": "900",
            "color": color,
            "marginTop": "4px",
            "fontFamily": "DM Mono, monospace",
        }),
        html.Div(sub, style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"}) if sub else html.Div(),
    ], style={
        "background": NAVY_MID,
        "border": f"1px solid {BORDER}",
        "borderRadius": "12px",
        "padding": "16px 20px",
        "minWidth": "120px",
    })


def _campaign_row(c: dict) -> html.Div:
    state = c.get("current_state", "BIRTH")
    symbol = c.get("symbol", "—")
    tier = c.get("historical_confidence", "—")
    days = _safe_int(c.get("campaign_age_days"), 0)

    entry = _safe_float(c.get("entry_price"), 0)
    current = _safe_float(c.get("current_price"), 0)
    ret_pct = _safe_float(c.get("return_pct"), 0)
    pnf_pct = _safe_float(c.get("pnf_progress_pct"), 0)

    ods = _safe_float(c.get("operator_dominance"), 0)
    decay_score = _safe_float(c.get("decay_score"), 0)
    decay_band = str(c.get("decay_band") or "UNKNOWN").upper()
    decay_reason = c.get("decay_reason") or ""
    exit_signal = bool(c.get("exit_signal")) or bool(c.get("conjunction_exit"))

    next_state = str(c.get("transition_next_state") or "—").upper()
    adv = _safe_float(c.get("transition_advance_prob"), 0)
    fail = _safe_float(c.get("transition_failure_prob"), 0)
    cont = _safe_float(c.get("transition_continuation_prob"), 0)
    exp_days = _safe_int(c.get("transition_expected_days"), 0)
    exp_ret = _safe_float(c.get("transition_expected_return"), 0)
    exp_mfe = _safe_float(c.get("transition_expected_mfe"), 0)
    exp_mae = _safe_float(c.get("transition_expected_mae"), 0)
    bias = str(c.get("transition_bias") or "UNKNOWN").upper()

    state_color = _STATE_COLORS.get(state, MUTED)
    state_icon = _STATE_ICONS.get(state, "•")
    tier_color = _TIER_COLORS.get(tier, MUTED)
    ret_color = TEAL_DIM if ret_pct >= 0 else RED_DIM
    decay_color = _DECAY_COLORS.get(decay_band, MUTED)
    bias_color = _BIAS_COLORS.get(bias, MUTED)

    row_bg = "rgba(239,68,68,.08)" if exit_signal or bias == "FAILURE_RISK" else (
        "rgba(45,143,111,.05)" if bias in {"ADVANCE_LIKELY", "ADVANCE_EDGE"} else
        "rgba(245,158,11,.04)" if decay_band in {"MONITOR", "WEAKENING"} else "transparent"
    )

    return html.Div([

        html.Div([
            html.Span(symbol, style={
                "fontFamily": "DM Mono, monospace",
                "fontSize": "15px",
                "fontWeight": "900",
                "color": WHITE,
            }),
            html.Span(tier, style={
                "fontSize": "9px",
                "fontWeight": "700",
                "color": tier_color,
                "background": "rgba(255,255,255,.05)",
                "borderRadius": "6px",
                "padding": "2px 6px",
                "marginLeft": "6px",
                "border": f"1px solid {tier_color}30",
            }),
        ], style={"flex": "1.05", "display": "flex", "alignItems": "center"}),

        html.Div([
            html.Span(f"{state_icon} {state.replace('_', ' ')}", style={
                "fontSize": "11px",
                "fontWeight": "700",
                "color": state_color,
            }),
            html.Div(f"Day {days}", style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"}),
        ], style={"flex": "1.25"}),

        html.Div([
            html.Div(_mono(f"${current:,.2f}", WHITE), style={"lineHeight": "1.2"}),
            html.Div([
                html.Span(f"{ret_pct:+.1f}%", style={
                    "fontSize": "11px",
                    "fontWeight": "800",
                    "color": ret_color,
                    "fontFamily": "DM Mono, monospace",
                }),
                html.Span(f" · P&F {pnf_pct:.0f}%", style={
                    "fontSize": "10px",
                    "color": TEXT,
                    "marginLeft": "4px",
                }),
            ]),
        ], style={"flex": "1.05"}),

        html.Div([
            html.Div(f"ODS {ods:.0f}", style={
                "fontSize": "11px",
                "fontWeight": "700",
                "color": TEAL_DIM if ods >= 70 else (YELLOW_DIM if ods >= 40 else RED_DIM),
            }),
            _bar(ods, TEAL_DIM if ods >= 70 else (YELLOW_DIM if ods >= 40 else RED_DIM)),
            html.Div(f"Decay {decay_score:.0f}", style={
                "fontSize": "10px",
                "fontWeight": "700",
                "color": decay_color,
                "marginTop": "5px",
            }),
        ], style={"flex": ".75"}),

        html.Div([
            html.Div("Next", style={"fontSize": "9px", "color": MUTED, "fontWeight": "700", "letterSpacing": ".08em"}),
            html.Div(next_state.replace("_", " "), style={
                "fontSize": "11px",
                "fontWeight": "800",
                "color": _STATE_COLORS.get(next_state, BLUE_DIM),
                "marginTop": "3px",
            }),
            _pill(_BIAS_LABELS.get(bias, bias), bias_color),
        ], style={"flex": "1.15"}),

        html.Div([
            html.Div([
                html.Span("Adv ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{adv:.0f}%", style={"fontSize": "12px", "fontWeight": "900", "color": TEAL_DIM, "fontFamily": "DM Mono, monospace"}),
            ]),
            _bar(adv, TEAL_DIM, width="70px"),
            html.Div([
                html.Span("Fail ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{fail:.0f}%", style={"fontSize": "12px", "fontWeight": "900", "color": RED_DIM if fail >= 40 else YELLOW_DIM, "fontFamily": "DM Mono, monospace"}),
            ], style={"marginTop": "5px"}),
            _bar(fail, RED_DIM if fail >= 40 else YELLOW_DIM, width="70px"),
        ], style={"flex": ".85"}),

        html.Div([
            html.Div([
                html.Span("Hold ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{cont:.0f}%", style={"fontSize": "12px", "fontWeight": "900", "color": BLUE_DIM, "fontFamily": "DM Mono, monospace"}),
            ]),
            html.Div(f"{exp_days}d exp", style={"fontSize": "11px", "color": WHITE, "fontWeight": "700", "marginTop": "5px"}),
        ], style={"flex": ".75"}),

        html.Div([
            html.Div([
                html.Span("ER ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{exp_ret:+.1f}%", style={"fontSize": "12px", "fontWeight": "900", "color": TEAL_DIM if exp_ret >= 0 else RED_DIM, "fontFamily": "DM Mono, monospace"}),
            ]),
            html.Div([
                html.Span("MFE ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{exp_mfe:+.1f}%", style={"fontSize": "11px", "fontWeight": "800", "color": PURPLE, "fontFamily": "DM Mono, monospace"}),
            ], style={"marginTop": "4px"}),
            html.Div([
                html.Span("MAE ", style={"fontSize": "9px", "color": MUTED}),
                html.Span(f"{exp_mae:+.1f}%", style={"fontSize": "11px", "fontWeight": "800", "color": RED_DIM, "fontFamily": "DM Mono, monospace"}),
            ], style={"marginTop": "2px"}),
        ], style={"flex": ".85"}),

        html.Div([
            _pill("🚨 EXIT" if exit_signal else decay_band, RED_DIM if exit_signal else decay_color),
            html.Div(decay_reason[:70] + ("…" if len(decay_reason) > 70 else ""), style={
                "fontSize": "9px",
                "color": MUTED,
                "marginTop": "4px",
                "lineHeight": "1.2",
                "maxWidth": "150px",
            }) if decay_reason else html.Div(),
        ], style={"flex": "1.15"}),

    ], style={
        "display": "flex",
        "alignItems": "center",
        "gap": "12px",
        "padding": "14px 8px",
        "borderBottom": f"1px solid {BORDER}",
        "background": row_bg,
        "borderRadius": "6px",
    })


def build_campaign_tab(session=None) -> html.Div:
    try:
        fetch_error = None
        r = _rq.get(f"{BACKEND_HTTP}/api/campaigns/active", timeout=20)
        if r.ok:
            data = r.json()
            campaigns = data.get("campaigns", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        else:
            campaigns = []
            fetch_error = f"Backend {r.status_code}"
    except Exception as exc:
        fetch_error = str(exc)
        campaigns = []

    total = len(campaigns)
    tier1 = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier2 = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    avg_ods = sum(_safe_float(c.get("operator_dominance"), 0) for c in campaigns) / total if total else 0

    healthy = sum(1 for c in campaigns if str(c.get("decay_band") or "").upper() == "HEALTHY")
    monitor = sum(1 for c in campaigns if str(c.get("decay_band") or "").upper() == "MONITOR")
    weakening = sum(1 for c in campaigns if str(c.get("decay_band") or "").upper() == "WEAKENING")
    exits = sum(1 for c in campaigns if bool(c.get("exit_signal")) or bool(c.get("conjunction_exit")))

    advance_edge = sum(1 for c in campaigns if str(c.get("transition_bias") or "").upper() in {"ADVANCE_EDGE", "ADVANCE_LIKELY"})
    failure_risk = sum(1 for c in campaigns if str(c.get("transition_bias") or "").upper() == "FAILURE_RISK")
    avg_advance = sum(_safe_float(c.get("transition_advance_prob"), 0) for c in campaigns) / total if total else 0
    avg_failure = sum(_safe_float(c.get("transition_failure_prob"), 0) for c in campaigns) / total if total else 0

    state_counts: dict[str, int] = {}
    for c in campaigns:
        s = c.get("current_state", "BIRTH")
        state_counts[s] = state_counts.get(s, 0) + 1

    summary_row = html.Div([
        _summary_tile("Active", str(total), WHITE),
        _summary_tile("TIER 1", str(tier1), TEAL_DIM),
        _summary_tile("TIER 2", str(tier2), BLUE_DIM),
        _summary_tile("Avg ODS", f"{avg_ods:.0f}", TEAL_DIM if avg_ods >= 60 else YELLOW_DIM),
        _summary_tile("Avg Advance", f"{avg_advance:.0f}%", TEAL_DIM, "next-state probability"),
        _summary_tile("Avg Failure", f"{avg_failure:.0f}%", RED_DIM if avg_failure >= 35 else YELLOW_DIM, "failure/distribution"),
        _summary_tile("Advance Edge", str(advance_edge), TEAL_DIM if advance_edge else MUTED),
        _summary_tile("Failure Risk", str(failure_risk), RED_DIM if failure_risk else MUTED),
        _summary_tile("Exit Signals", str(exits), RED_DIM if exits else MUTED),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "20px", "flexWrap": "wrap"})

    state_badges = html.Div([
        html.Span([
            html.Span(f"{_STATE_ICONS.get(s, '•')} {s.replace('_', ' ')}",
                      style={"fontSize": "11px", "fontWeight": "700", "color": _STATE_COLORS.get(s, MUTED)}),
            html.Span(f" ({n})", style={"fontSize": "11px", "color": MUTED}),
        ], style={
            "background": "rgba(255,255,255,.04)",
            "borderRadius": "8px",
            "padding": "4px 10px",
            "border": f"1px solid {BORDER}",
        })
        for s, n in sorted(state_counts.items(), key=lambda x: x[1], reverse=True)
    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "20px"})

    header = html.Div([
        _label("Symbol / Tier", "1.05"),
        _label("State / Age", "1.25"),
        _label("Price / P&F", "1.05"),
        _label("ODS / Decay", ".75"),
        _label("Next State / Bias", "1.15"),
        _label("Advance / Failure", ".85"),
        _label("Hold / Days", ".75"),
        _label("Expected", ".85"),
        _label("Signal / Reason", "1.15"),
    ], style={
        "display": "flex",
        "gap": "12px",
        "paddingBottom": "10px",
        "borderBottom": f"1px solid {BORDER}",
        "marginBottom": "4px",
    })

    if campaigns:
        def _sort_key(c):
            exit_flag = 1 if (bool(c.get("exit_signal")) or bool(c.get("conjunction_exit"))) else 0
            bias = str(c.get("transition_bias") or "UNKNOWN").upper()
            bias_rank = {"FAILURE_RISK": 0, "ADVANCE_LIKELY": 1, "ADVANCE_EDGE": 2, "MIXED": 3, "HOLDING_PATTERN": 4, "UNKNOWN": 5}.get(bias, 5)
            tier = c.get("historical_confidence", "TIER_4")
            tier_rank = {"TIER_1": 0, "TIER_2": 1, "TIER_3": 2, "TIER_4": 3}.get(tier, 4)
            return (-exit_flag, bias_rank, tier_rank, -_safe_float(c.get("transition_advance_prob"), 0))

        rows = [_campaign_row(c) for c in sorted(campaigns, key=_sort_key)]
    else:
        error_msg = f"API error: {fetch_error}" if fetch_error else "No active campaigns yet."
        rows = [html.Div([
            html.Div("🌱", style={"fontSize": "32px", "marginBottom": "12px"}),
            html.Div("No active campaigns yet.", style={"color": WHITE, "fontSize": "16px", "fontWeight": "700"}),
            html.Div(error_msg, style={"color": RED_DIM if fetch_error else TEXT, "fontSize": "13px", "marginTop": "8px"}),
            html.Div(f"Backend: {BACKEND_HTTP}", style={"color": MUTED, "fontSize": "11px", "marginTop": "4px"}),
        ], style={"textAlign": "center", "padding": "48px 24px", "color": MUTED})]

    return html.Div([
        _card([
            html.Div([
                html.H2("📊 Campaign Intelligence", style={
                    "color": WHITE,
                    "fontSize": "18px",
                    "fontWeight": "900",
                    "margin": "0 0 4px",
                }),
                html.P(
                    "Active campaigns — lifecycle state, ODS, decay, and Phase 14D next-state transition probabilities.",
                    style={"color": TEXT, "fontSize": "13px", "margin": "0 0 20px"},
                ),
            ]),
            summary_row,
            state_badges,
            header,
            html.Div(rows),
        ]),
    ])
