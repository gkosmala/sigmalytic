# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/campaign_tab.py
-------------------------
Clean Campaign Intelligence Tab for Sigmalytic V2.
ASCII-safe: no emoji/mojibake characters.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
import requests as _rq
from dash import html

NAVY      = "#0d1b2e"
NAVY_CARD = "#111f35"
NAVY_MID  = "#0f172a"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
RED_DIM   = "#f87171"
YELLOW    = "#f59e0b"
YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"
MUTED     = "#f8fafc"
TEXT      = "#f8fafc"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
PURPLE    = "#a78bfa"

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
DASH = "-"


def _is_missing(value) -> bool:
    return value is None or value == "" or str(value).strip().lower() in {"none", "null", "nan", "unknown"}


def _safe_float(value, default=0.0) -> float:
    try:
        if _is_missing(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0) -> int:
    try:
        if _is_missing(value):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _num_or_dash(value, digits=0) -> str:
    if _is_missing(value):
        return DASH
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return DASH


def _pct_or_dash(value, digits=0, signed=False) -> str:
    if _is_missing(value):
        return DASH
    try:
        v = float(value)
        sign = "+" if signed and v >= 0 else ""
        return f"{sign}{v:.{digits}f}%"
    except Exception:
        return DASH


def _label_or_dash(value) -> str:
    if _is_missing(value):
        return DASH
    return str(value).strip().upper()


def _avg_present(campaigns, field: str, default=0.0):
    vals = []
    for c in campaigns:
        value = c.get(field)
        if not _is_missing(value):
            try:
                vals.append(float(value))
            except Exception:
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def _campaign_days(c: dict) -> str:
    raw = c.get("campaign_age_days")
    if not _is_missing(raw):
        try:
            val = int(float(raw))
            if val > 0:
                return str(val)
        except Exception:
            pass

    for key in ["state_changed_at", "created_at", "birth_date", "updated_at"]:
        dt_raw = c.get(key)
        if _is_missing(dt_raw):
            continue
        try:
            s = str(dt_raw).replace("Z", "+00:00")
            if "T" not in s and len(s) == 10:
                s = s + "T00:00:00+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return str(max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days))
        except Exception:
            continue
    return DASH


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
    "BIRTH": "BIRTH",
    "CONFIRMED": "CONFIRMED",
    "SURVIVING": "SURVIVING",
    "EXPANDING": "EXPANDING",
    "MATURING": "MATURING",
    "DISTRIBUTION_RISK": "RISK",
    "CLOSED": "CLOSED",
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
    "-": MUTED,
}

_BIAS_LABELS = {
    "ADVANCE_LIKELY": "ADV LIKELY",
    "ADVANCE_EDGE": "ADV EDGE",
    "HOLDING_PATTERN": "HOLD",
    "MIXED": "MIXED",
    "FAILURE_RISK": "FAIL RISK",
    "UNKNOWN": DASH,
    "-": DASH,
}

_QUALITY_COLORS = {
    "A": TEAL_DIM,
    "B": TEAL_DIM,
    "C": YELLOW_DIM,
    "WATCH": YELLOW,
    "AVOID": RED_DIM,
    "UNKNOWN": MUTED,
    "-": MUTED,
}


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
        "color": WHITE,
        "fontWeight": "800",
        "textTransform": "uppercase",
        "letterSpacing": ".1em",
    })


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
            "color": WHITE,
            "fontWeight": "800",
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
        html.Div(sub, style={"fontSize": "10px", "color": WHITE, "marginTop": "3px"}) if sub else html.Div(),
    ], style={
        "background": NAVY_MID,
        "border": f"1px solid {BORDER}",
        "borderRadius": "12px",
        "padding": "16px 20px",
        "minWidth": "120px",
    })


def _signal_summary(c: dict, quality: str, decay_band: str, exit_signal: bool) -> str:
    if exit_signal:
        return "EXIT WATCH"
    wg_phase = c.get("weis_gamma_phase")
    wg_bucket = c.get("weis_gamma_rank_bucket")
    if not _is_missing(wg_phase):
        if not _is_missing(wg_bucket):
            return f"{str(wg_phase).upper()} | {str(wg_bucket).upper()}"
        return str(wg_phase).upper()
    if decay_band not in {"UNKNOWN", "-", ""}:
        return decay_band
    if quality != DASH:
        return quality
    return "PENDING"


def _campaign_row(c: dict) -> html.Div:
    state = str(c.get("current_state") or "BIRTH").upper()
    symbol = c.get("symbol") or DASH
    tier = c.get("historical_confidence") or DASH
    days = _campaign_days(c)

    ret_pct = _safe_float(c.get("return_pct"), 0)
    pnf_pct = _safe_float(c.get("pnf_progress_pct"), 0)

    ods_raw = c.get("operator_dominance")
    ods = _safe_float(ods_raw, 0)
    ods_display = _num_or_dash(ods_raw, 0)

    decay_raw = c.get("decay_score")
    decay_score = _safe_float(decay_raw, 0)
    decay_display = _num_or_dash(decay_raw, 0)
    decay_band = str(c.get("decay_band") or "UNKNOWN").upper()
    exit_signal = bool(c.get("exit_signal")) or bool(c.get("conjunction_exit"))

    next_state = str(c.get("transition_next_state") or DASH).upper()
    adv_raw = c.get("transition_advance_prob")
    fail_transition_raw = c.get("transition_failure_prob")
    adv = _safe_float(adv_raw, 0)
    fail_transition = _safe_float(fail_transition_raw, 0)
    adv_display = _pct_or_dash(adv_raw, 0)
    fail_transition_display = _pct_or_dash(fail_transition_raw, 0)

    raw_bias = c.get("transition_bias")
    # transition_bias can be a long explanation; only display recognized short labels.
    bias = str(raw_bias or "UNKNOWN").upper()
    if len(bias) > 40 or "CAMPAIGN STATE" in bias or "REASON:" in bias:
        bias = "UNKNOWN"

    quality = _label_or_dash(c.get("outcome_quality"))
    quality_score_raw = c.get("outcome_quality_score")
    quality_score = _safe_float(quality_score_raw, 0)
    quality_score_display = _num_or_dash(quality_score_raw, 0)

    exp_return_raw = c.get("outcome_expected_return")
    exp_return = _safe_float(exp_return_raw, 0)
    exp_return_display = _pct_or_dash(exp_return_raw, 1, signed=True)

    exp_mfe_raw = c.get("outcome_expected_mfe")
    exp_mfe_display = _pct_or_dash(exp_mfe_raw, 1, signed=True)

    exp_mae_raw = c.get("outcome_expected_mae")
    exp_mae_display = _pct_or_dash(exp_mae_raw, 1, signed=True)

    exp_days_raw = c.get("outcome_expected_duration_days")
    exp_days_display = _num_or_dash(exp_days_raw, 0)

    t1_raw = c.get("outcome_target1_prob")
    t1 = _safe_float(t1_raw, 0)
    t1_display = _pct_or_dash(t1_raw, 0)

    t2_raw = c.get("outcome_target2_prob")
    t2 = _safe_float(t2_raw, 0)
    t2_display = _pct_or_dash(t2_raw, 0)

    fail_raw = c.get("outcome_failure_prob")
    fail = _safe_float(fail_raw, 0)
    fail_display = _pct_or_dash(fail_raw, 0)

    rr_raw = c.get("outcome_risk_reward")
    rr = _safe_float(rr_raw, 0)
    rr_display = _num_or_dash(rr_raw, 2)

    state_color = _STATE_COLORS.get(state, MUTED)
    state_label = _STATE_ICONS.get(state, state)
    tier_color = _TIER_COLORS.get(tier, MUTED)
    decay_color = _DECAY_COLORS.get(decay_band, MUTED)
    bias_color = _BIAS_COLORS.get(bias, MUTED)
    bias_label = _BIAS_LABELS.get(bias, DASH)
    quality_color = _QUALITY_COLORS.get(quality, MUTED)

    signal_summary = _signal_summary(c, quality, decay_band, exit_signal)

    row_bg = (
        "rgba(239,68,68,.08)" if exit_signal or quality == "AVOID" or bias == "FAILURE_RISK"
        else "rgba(45,143,111,.05)" if quality in {"A", "B"} or bias in {"ADVANCE_LIKELY", "ADVANCE_EDGE"}
        else "rgba(245,158,11,.04)" if quality in {"C", "WATCH"} or decay_band in {"MONITOR", "WEAKENING"}
        else "transparent"
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
        ], style={"flex": ".9", "display": "flex", "alignItems": "center"}),

        html.Div([
            html.Span(state_label, style={"fontSize": "11px", "fontWeight": "800", "color": state_color}),
            html.Div(f"Day {days}", style={"fontSize": "10px", "color": WHITE, "marginTop": "3px"}),
        ], style={"flex": "1.05"}),

        html.Div([
            html.Div(f"ODS {ods_display}", style={
                "fontSize": "11px",
                "fontWeight": "800",
                "color": TEAL_DIM if ods >= 70 else (YELLOW_DIM if ods >= 40 else RED_DIM),
            }),
            _bar(ods, TEAL_DIM if ods >= 70 else (YELLOW_DIM if ods >= 40 else RED_DIM)),
            html.Div(f"Decay {decay_display}", style={
                "fontSize": "10px",
                "fontWeight": "800",
                "color": decay_color,
                "marginTop": "5px",
            }),
        ], style={"flex": ".7"}),

        html.Div([
            html.Div(next_state.replace("_", " "), style={
                "fontSize": "11px",
                "fontWeight": "800",
                "color": _STATE_COLORS.get(next_state, BLUE_DIM),
            }),
            _pill(bias_label, bias_color),
            html.Div(f"Adv {adv_display} / Fail {fail_transition_display}", style={
                "fontSize": "9px",
                "color": WHITE,
                "marginTop": "4px",
                "fontFamily": "DM Mono, monospace",
            }),
        ], style={"flex": "1.05"}),

        html.Div([
            _pill(quality, quality_color),
            html.Div(f"Score {quality_score_display}", style={
                "fontSize": "10px",
                "color": quality_color,
                "fontWeight": "800",
                "marginTop": "5px",
                "fontFamily": "DM Mono, monospace",
            }),
            html.Div(f"{exp_days_display}d" if exp_days_display != DASH else DASH, style={
                "fontSize": "9px", "color": WHITE, "marginTop": "2px"
            }),
        ], style={"flex": ".7"}),

        html.Div([
            html.Div([
                html.Span("ER ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(exp_return_display, style={
                    "fontSize": "13px",
                    "fontWeight": "900",
                    "color": TEAL_DIM if exp_return >= 0 else RED_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ]),
            html.Div(f"Live {ret_pct:+.1f}% | P&F {pnf_pct:.0f}%", style={
                "fontSize": "9px",
                "color": WHITE,
                "marginTop": "4px",
                "fontFamily": "DM Mono, monospace",
            }),
        ], style={"flex": ".75"}),

        html.Div([
            html.Div([
                html.Span("MFE ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(exp_mfe_display, style={
                    "fontSize": "12px",
                    "fontWeight": "900",
                    "color": PURPLE,
                    "fontFamily": "DM Mono, monospace",
                }),
            ]),
            html.Div([
                html.Span("MAE ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(exp_mae_display, style={
                    "fontSize": "12px",
                    "fontWeight": "900",
                    "color": RED_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ], style={"marginTop": "4px"}),
        ], style={"flex": ".75"}),

        html.Div([
            html.Div([
                html.Span("T1 ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(t1_display, style={
                    "fontSize": "12px",
                    "fontWeight": "900",
                    "color": TEAL_DIM if t1 >= 60 else YELLOW_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ]),
            _bar(t1, TEAL_DIM if t1 >= 60 else YELLOW_DIM, width="70px"),
            html.Div([
                html.Span("T2 ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(t2_display, style={
                    "fontSize": "12px",
                    "fontWeight": "900",
                    "color": TEAL_DIM if t2 >= 40 else YELLOW_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ], style={"marginTop": "5px"}),
            _bar(t2, TEAL_DIM if t2 >= 40 else YELLOW_DIM, width="70px"),
        ], style={"flex": ".85"}),

        html.Div([
            html.Div([
                html.Span("Fail ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(fail_display, style={
                    "fontSize": "13px",
                    "fontWeight": "900",
                    "color": RED_DIM if fail >= 50 else YELLOW_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ]),
            _bar(fail, RED_DIM if fail >= 50 else YELLOW_DIM, width="70px"),
            html.Div([
                html.Span("RR ", style={"fontSize": "9px", "color": WHITE}),
                html.Span(rr_display, style={
                    "fontSize": "12px",
                    "fontWeight": "900",
                    "color": TEAL_DIM if rr >= 2.0 else YELLOW_DIM,
                    "fontFamily": "DM Mono, monospace",
                }),
            ], style={"marginTop": "5px"}),
        ], style={"flex": ".75"}),

        html.Div([
            _pill(signal_summary, RED_DIM if exit_signal else (decay_color if signal_summary != "PENDING" else MUTED)),
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

    avg_ods = _avg_present(campaigns, "operator_dominance")
    avg_outcome_return = _avg_present(campaigns, "outcome_expected_return")
    avg_t1 = _avg_present(campaigns, "outcome_target1_prob")
    avg_t2 = _avg_present(campaigns, "outcome_target2_prob")
    avg_fail = _avg_present(campaigns, "outcome_failure_prob")
    avg_rr = _avg_present(campaigns, "outcome_risk_reward")

    b_quality = sum(1 for c in campaigns if str(c.get("outcome_quality") or "").upper() == "B")
    c_quality = sum(1 for c in campaigns if str(c.get("outcome_quality") or "").upper() == "C")
    watch_quality = sum(1 for c in campaigns if str(c.get("outcome_quality") or "").upper() == "WATCH")
    avoid_quality = sum(1 for c in campaigns if str(c.get("outcome_quality") or "").upper() == "AVOID")

    state_counts: dict[str, int] = {}
    for c in campaigns:
        s = str(c.get("current_state") or "BIRTH").upper()
        state_counts[s] = state_counts.get(s, 0) + 1

    summary_row = html.Div([
        _summary_tile("Active", str(total), WHITE),
        _summary_tile("TIER 1", str(tier1), TEAL_DIM),
        _summary_tile("TIER 2", str(tier2), BLUE_DIM),
        _summary_tile("Avg ODS", _num_or_dash(avg_ods, 0), TEAL_DIM if _safe_float(avg_ods, 0) >= 60 else YELLOW_DIM),
        _summary_tile("Avg ER", _pct_or_dash(avg_outcome_return, 1, signed=True), TEAL_DIM if _safe_float(avg_outcome_return, 0) >= 0 else RED_DIM),
        _summary_tile("Avg T1", _pct_or_dash(avg_t1, 0), TEAL_DIM if _safe_float(avg_t1, 0) >= 50 else YELLOW_DIM),
        _summary_tile("Avg T2", _pct_or_dash(avg_t2, 0), TEAL_DIM if _safe_float(avg_t2, 0) >= 35 else YELLOW_DIM),
        _summary_tile("Avg Fail", _pct_or_dash(avg_fail, 0), RED_DIM if _safe_float(avg_fail, 0) >= 45 else YELLOW_DIM),
        _summary_tile("Avg RR", _num_or_dash(avg_rr, 2), TEAL_DIM if _safe_float(avg_rr, 0) >= 2.0 else YELLOW_DIM),
        _summary_tile("B / C", f"{b_quality}/{c_quality}", TEAL_DIM),
        _summary_tile("Watch", str(watch_quality), YELLOW),
        _summary_tile("Avoid", str(avoid_quality), RED_DIM if avoid_quality else MUTED),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "20px", "flexWrap": "wrap"})

    state_badges = html.Div([
        html.Span([
            html.Span(_STATE_ICONS.get(s, s), style={
                "fontSize": "11px",
                "fontWeight": "800",
                "color": _STATE_COLORS.get(s, MUTED),
            }),
            html.Span(f" ({n})", style={"fontSize": "11px", "color": WHITE}),
        ], style={
            "background": "rgba(255,255,255,.04)",
            "borderRadius": "8px",
            "padding": "4px 10px",
            "border": f"1px solid {BORDER}",
        })
        for s, n in sorted(state_counts.items(), key=lambda x: x[1], reverse=True)
    ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "20px"})

    header = html.Div([
        _label("Symbol / Tier", ".9"),
        _label("State / Age", "1.05"),
        _label("ODS / Decay", ".7"),
        _label("Next / Bias", "1.05"),
        _label("Outcome", ".7"),
        _label("Exp Return", ".75"),
        _label("MFE / MAE", ".75"),
        _label("Target 1 / 2", ".85"),
        _label("Failure / RR", ".75"),
        _label("Signal / Summary", "1.15"),
    ], style={
        "display": "flex",
        "gap": "12px",
        "paddingBottom": "10px",
        "borderBottom": f"1px solid {BORDER}",
        "marginBottom": "4px",
    })

    if campaigns:
        def _sort_key(c):
            q = str(c.get("outcome_quality") or "UNKNOWN").upper()
            quality_rank = {"A": 0, "B": 1, "C": 2, "WATCH": 3, "AVOID": 4, "UNKNOWN": 5}.get(q, 5)
            exit_flag = 1 if (bool(c.get("exit_signal")) or bool(c.get("conjunction_exit"))) else 0
            return (
                -exit_flag,
                quality_rank,
                -_safe_float(c.get("outcome_risk_reward"), 0),
                -_safe_float(c.get("outcome_expected_return"), 0),
            )

        rows = [_campaign_row(c) for c in sorted(campaigns, key=_sort_key)]
    else:
        error_msg = f"API error: {fetch_error}" if fetch_error else "No active campaigns yet."
        rows = [html.Div([
            html.Div("No active campaigns yet.", style={"color": WHITE, "fontSize": "16px", "fontWeight": "800"}),
            html.Div(error_msg, style={"color": RED_DIM if fetch_error else TEXT, "fontSize": "13px", "marginTop": "8px"}),
            html.Div(f"Backend: {BACKEND_HTTP}", style={"color": WHITE, "fontSize": "11px", "marginTop": "4px"}),
        ], style={"textAlign": "center", "padding": "48px 24px", "color": WHITE})]

    return html.Div([
        _card([
            html.Div([
                html.H2("Campaign Intelligence", style={
                    "color": WHITE,
                    "fontSize": "18px",
                    "fontWeight": "900",
                    "margin": "0 0 4px",
                }),
                html.P(
                    "Active campaigns - lifecycle state, ODS, decay, transition probability, and Phase 15 outcome economics.",
                    style={"color": WHITE, "fontSize": "13px", "margin": "0 0 20px"},
                ),
            ]),
            summary_row,
            state_badges,
            header,
            html.Div(rows),
        ]),
    ])

