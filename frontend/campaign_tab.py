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

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None

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
    "BIRTH": "SPARK",
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

    # FIX (2026-07-29): "return_pct" and "pnf_progress_pct" are never
    # actually set anywhere in the backend's enrichment output (confirmed
    # by direct search) -- unlike historical_confidence/outcome_quality
    # above, there's no clean existing field to derive a genuine live
    # return % or Point-and-Figure progress % from without risking an
    # incorrect fabricated financial figure. Every campaign showing an
    # identical "+0.0% | 0%" was this default masquerading as real data.
    # Tracking presence explicitly so the display can show an honest dash
    # instead of a look-alike zero.
    _has_ret_pct = c.get("return_pct") is not None
    _has_pnf_pct = c.get("pnf_progress_pct") is not None
    ret_pct = _safe_float(c.get("return_pct"), 0)
    pnf_pct = _safe_float(c.get("pnf_progress_pct"), 0)

    ods_raw = c.get("operator_dominance")
    ods = _safe_float(ods_raw, 0)
    ods_display = _num_or_dash(ods_raw, 0)
    if _is_missing(ods_raw):
        ods_display = str(c.get("ods_label") or "PENDING").replace("_", " ")[:18]

    decay_raw = c.get("decay_score")
    decay_score = _safe_float(decay_raw, 0)
    decay_display = _num_or_dash(decay_raw, 0)
    decay_band = str(c.get("decay_band") or c.get("decay_label") or "PENDING").upper()
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
    if _is_missing(exp_return_raw):
        exp_return_display = str(c.get("expected_return_status") or "PENDING").replace("_", " ")[:18]

    exp_mfe_raw = c.get("outcome_expected_mfe")
    exp_mfe_display = _pct_or_dash(exp_mfe_raw, 1, signed=True)
    if _is_missing(exp_mfe_raw):
        exp_mfe_display = str(c.get("mfe_status") or c.get("market_data_status") or "PENDING").replace("_", " ")[:18]

    exp_mae_raw = c.get("outcome_expected_mae")
    exp_mae_display = _pct_or_dash(exp_mae_raw, 1, signed=True)
    if _is_missing(exp_mae_raw):
        exp_mae_display = str(c.get("mae_status") or c.get("market_data_status") or "PENDING").replace("_", " ")[:18]

    exp_days_raw = c.get("outcome_expected_duration_days")
    exp_days_display = _num_or_dash(exp_days_raw, 0)

    t1_raw = c.get("outcome_target1_prob")
    t1 = _safe_float(t1_raw, 0)
    t1_display = _pct_or_dash(t1_raw, 0)
    if _is_missing(t1_raw):
        t1_display = str(c.get("target_status") or "PENDING").replace("_", " ")[:18]

    t2_raw = c.get("outcome_target2_prob")
    t2 = _safe_float(t2_raw, 0)
    t2_display = _pct_or_dash(t2_raw, 0)
    if _is_missing(t2_raw):
        t2_display = str(c.get("target_status") or "PENDING").replace("_", " ")[:18]

    fail_raw = c.get("outcome_failure_prob")
    fail = _safe_float(fail_raw, 0)
    fail_display = _pct_or_dash(fail_raw, 0)
    if _is_missing(fail_raw):
        fail_display = str(c.get("failure_status") or "PENDING").replace("_", " ")[:18]

    rr_raw = c.get("outcome_risk_reward")
    rr = _safe_float(rr_raw, 0)
    rr_display = _num_or_dash(rr_raw, 2)
    if _is_missing(rr_raw):
        rr_display = str(c.get("failure_status") or "PENDING").replace("_", " ")[:18]

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
            html.Div(
                f"Live {ret_pct:+.1f}% | P&F {pnf_pct:.0f}%"
                if (_has_ret_pct or _has_pnf_pct)
                else "Live — | P&F —",
                style={
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



# SIGMALYTIC_STEP87E_FRONTEND_ENRICHED_CAMPAIGN_TABLE_LIMIT_5
# Uses the live-verified safe row limit from Step87D-R2.
# UI display only: no writes, no campaign mutation, no D3D, no operator-control confirmation, no trade signal, no Stripe billing
# SIGMALYTIC_STEP87C_B_ENRICHED_CAMPAIGN_TABLE_FRONTEND
# Maps the read-only enriched backend route into the legacy visible Campaigns table field names.
# UI display only: no writes, no campaign mutation, no D3D authorization,
# no operator-control confirmation, no trade-signal creation, no Stripe billing
def _step87c_b_pick(row: dict, *keys, default=None):
    for key in keys:
        try:
            value = row.get(key)
        except Exception:
            value = None
        if value is not None and value != "":
            return value
    return default


def _step87c_b_enriched_campaign_alias(row: dict) -> dict:
    c = dict(row)

    c["current_state"] = _step87c_b_pick(
        c,
        "current_state",
        "state",
        "status",
        "campaign_state",
        default="SPARK",
    )

    c["historical_confidence"] = _step87c_b_pick(
        c,
        "historical_confidence",
        "grade",
        default=DASH,
    )

    c["operator_dominance"] = _step87c_b_pick(
        c,
        "operator_dominance",
        "ods_score",
        default=None,
    )

    c["decay_score"] = _step87c_b_pick(
        c,
        "decay_score",
        default=None,
    )

    c["decay_band"] = _step87c_b_pick(
        c,
        "decay_band",
        "decay_label",
        default="PENDING",
    )

    c["decay_reason"] = _step87c_b_pick(
        c,
        "decay_reason",
        default="read-only enrichment route",
    )

    c["transition_next_state"] = _step87c_b_pick(
        c,
        "transition_next_state",
        "next_state",
        "state",
        "status",
        default="REVIEW",
    )

    c["transition_bias"] = _step87c_b_pick(
        c,
        "transition_bias",
        "bias",
        default="UNKNOWN",
    )

    c["outcome_quality_score"] = _step87c_b_pick(
        c,
        "outcome_quality_score",
        "outcome_score",
        default=None,
    )

    # FIX (2026-07-29): neither "historical_confidence" (checked against
    # literal "TIER_1"/"TIER_2") nor "outcome_quality" (checked against
    # literal "B"/"C"/"WATCH"/"AVOID") is ever actually set anywhere in
    # the backend's enrichment output (campaign_full_enrichment_api.py) --
    # confirmed by direct search. These were frontend classification
    # concepts that summary counters (Tier 1, Tier 2, B/C, Watch, Avoid)
    # were built to display, but the backend side of them was never
    # implemented, so they've always read as their defaults (DASH/
    # "PENDING") and every summary count showed 0. Deriving both from
    # real fields that do exist, rather than leaving them permanently
    # unpopulated:
    #   - historical_confidence: derived from cohort_status, the real
    #     analog-match confidence classification already computed by
    #     _cohort_readiness() on the backend (COHORT_READY = enough
    #     historical analogs for a reliable expectation = Tier 1;
    #     COHORT_LIMITED = some analogs found but a small sample = Tier
    #     2; anything else -- insufficient matches/history -- stays
    #     unclassified rather than being forced into a tier).
    #   - outcome_quality: derived from the real 0-100 composite score
    #     already present (outcome_quality_score, just picked above),
    #     using the same A+/A/B/C/W grading scale used elsewhere in this
    #     codebase (e.g. intelligence_api.py's _grade()) for consistency,
    #     mapping the "W" grade to "WATCH" to match what this tab's
    #     summary counters check for.
    _cohort_status = str(c.get("cohort_status") or "").upper()
    if _cohort_status == "COHORT_READY":
        c["historical_confidence"] = "TIER_1"
    elif _cohort_status == "COHORT_LIMITED":
        c["historical_confidence"] = "TIER_2"
    else:
        c["historical_confidence"] = _step87c_b_pick(
            c, "historical_confidence", "grade", default=DASH,
        )

    _oq_score = c.get("outcome_quality_score")
    if _oq_score is not None:
        try:
            _oq_val = float(_oq_score)
            if _oq_val >= 85:
                c["outcome_quality"] = "A+"
            elif _oq_val >= 75:
                c["outcome_quality"] = "A"
            elif _oq_val >= 65:
                c["outcome_quality"] = "B"
            elif _oq_val >= 50:
                c["outcome_quality"] = "C"
            elif _oq_val >= 35:
                c["outcome_quality"] = "WATCH"
            else:
                c["outcome_quality"] = "AVOID"
        except (TypeError, ValueError):
            c["outcome_quality"] = _step87c_b_pick(
                c, "outcome_quality", "outcome_status", default="PENDING",
            )
    else:
        c["outcome_quality"] = _step87c_b_pick(
            c, "outcome_quality", "outcome_status", default="PENDING",
        )

    c["outcome_expected_return"] = _step87c_b_pick(
        c,
        "outcome_expected_return",
        "expected_return_pct",
        default=None,
    )

    c["outcome_expected_mfe"] = _step87c_b_pick(
        c,
        "outcome_expected_mfe",
        "mfe_pct",
        default=None,
    )

    c["outcome_expected_mae"] = _step87c_b_pick(
        c,
        "outcome_expected_mae",
        "mae_pct",
        default=None,
    )

    c["outcome_expected_duration_days"] = _step87c_b_pick(
        c,
        "outcome_expected_duration_days",
        "outcome_window_days",
        default=None,
    )

    c["outcome_target1_prob"] = _step87c_b_pick(
        c,
        "outcome_target1_prob",
        "target_1_pct",
        default=None,
    )

    c["outcome_target2_prob"] = _step87c_b_pick(
        c,
        "outcome_target2_prob",
        "target_2_pct",
        default=None,
    )

    c["outcome_failure_prob"] = _step87c_b_pick(
        c,
        "outcome_failure_prob",
        "failure_pct",
        default=None,
    )

    c["outcome_risk_reward"] = _step87c_b_pick(
        c,
        "outcome_risk_reward",
        "risk_reward_1",
        default=None,
    )

    c["outcome_summary"] = _step87c_b_pick(
        c,
        "outcome_summary",
        "summary",
        "expected_return_status",
        "enrichment_status",
        default="read-only enriched campaign table",
    )

    c["current_price"] = _step87c_b_pick(
        c,
        "current_price",
        "latest_close",
        "price",
        default=None,
    )

    c["pnf_target"] = _step87c_b_pick(
        c,
        "pnf_target",
        "target_1_price",
        default=None,
    )

    c["stop_price"] = _step87c_b_pick(
        c,
        "stop_price",
        "failure_price",
        default=None,
    )

    return c


# END_SIGMALYTIC_STEP87C_B_ENRICHED_CAMPAIGN_TABLE_FRONTEND


# SIGMALYTIC_STEP88A_R3_SHOW_ALL_CAMPAIGNS_ENRICH_SAFE_BATCH
# Display all ranked/active campaigns while enriching only the first live-safe batch.
# Rows outside the enrichment batch remain visible with honest PENDING / NOT ENRICHED status.
# UI display only: no database write, no campaign mutation, no D3D authorization,
# no operator-control confirmation, no trade-signal creation, no Stripe billing
_STEP88A_BASE_LIMIT = 100
# FIX (2026-07-29): was 100 -- each symbol in this batch triggers 7 years
# of daily-bar cohort analysis (a deliberate design choice for analytical
# quality, not something to shrink -- see CAMPAIGN_HISTORY_YEARS in
# campaign_full_enrichment_api.py) plus several other heavy per-symbol
# computations (gamma overlay, divergence overlay, PnF, lifecycle status).
# Processing 100 symbols' worth of that simultaneously in one request
# caused the shared backend web service to repeatedly run out of memory
# (>2GB, confirmed via production crash logs). Reducing the batch size is
# the safe lever here -- it doesn't touch analytical quality per symbol,
# just how many symbols get processed in one request. Combined with the
# much longer cache window below (10 min vs the previous 20s), this cuts
# both how much memory a single request needs and how often that request
# happens at all.
_STEP88A_SAFE_ENRICH_LIMIT = 40


def _step88a_rows_from_payload(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    for key in ("rankings", "campaigns", "rows", "opportunities", "items", "data"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [x for x in rows if isinstance(x, dict)]

    return []


def _step88a_fetch_json(path: str, timeout: int = 45, ttl_seconds: int = 20):
    def _do_fetch_raising():
        # Raises on any failure (bad status or exception) so a transient
        # error never gets cached -- only genuine successes are cached.
        # A cached failure would otherwise "lock in" a 502 or similar for
        # the full TTL window instead of allowing the next call to retry.
        r = _rq.get(f"{BACKEND_HTTP}{path}", timeout=timeout)
        if not r.ok:
            raise RuntimeError(f"{path} backend {r.status_code}")
        return r.json()

    if shared_cache is None:
        try:
            return (_do_fetch_raising(), "")
        except Exception as exc:
            return (None, str(exc))

    try:
        data = shared_cache.get_or_fetch(path, _do_fetch_raising, ttl_seconds=ttl_seconds)
        return (data, "")
    except Exception as exc:
        return (None, str(exc))


def _step88a_campaign_keys(row: dict):
    keys = []

    campaign_id = row.get("campaign_id") or row.get("id")
    if campaign_id not in (None, ""):
        keys.append(("id", str(campaign_id)))

    symbol = str(row.get("symbol") or "").upper().strip()
    timeframe = str(row.get("timeframe") or "DAILY").upper().strip()
    if symbol:
        keys.append(("symbol_timeframe", symbol, timeframe))
        keys.append(("symbol", symbol))

    return keys


def _step88a_fetch_base_campaigns():
    errors = []
    endpoints = [
        f"/api/intelligence/rankings?limit={_STEP88A_BASE_LIMIT}",
        "/api/intelligence/rankings",
        f"/api/campaigns/active?limit={_STEP88A_BASE_LIMIT}",
        "/api/campaigns/active",
    ]

    for endpoint in endpoints:
        data, err = _step88a_fetch_json(endpoint, timeout=45)
        if err:
            errors.append(err)
            continue

        rows = _step88a_rows_from_payload(data)
        if rows:
            return rows, "", endpoint

        errors.append(f"{endpoint} returned no rows")

    return [], " | ".join(errors), ""


def _step88a_fetch_enriched_batch():
    endpoint = f"/api/campaigns/read-only/full-universe-enriched-campaign-table?limit={_STEP88A_SAFE_ENRICH_LIMIT}"
    # FIX (2026-07-29): was using the default 20s TTL, which meant this
    # heavy endpoint got re-fetched almost every time the tab re-rendered
    # (render_main reacts to live price ticks roughly every 20s). The
    # underlying campaign data only actually changes once per night (the
    # nightly cron pipeline) -- there was never a real need to refresh
    # this more than a few times an hour, let alone every 20 seconds.
    # 10 minutes is still far more responsive than the data itself
    # changes, while cutting call frequency by ~30x.
    data, err = _step88a_fetch_json(endpoint, timeout=75, ttl_seconds=600)
    if err:
        return [], err

    rows = _step88a_rows_from_payload(data)
    return rows, ""


def _step88a_pending_not_enriched(row: dict) -> dict:
    c = dict(row)

    c.setdefault("ods_label", "NOT_ENRICHED")
    c.setdefault("ods_score", None)

    c.setdefault("decay_label", "PENDING_NOT_ENRICHED")
    c.setdefault("decay_score", None)
    c.setdefault("decay_reason", "outside live-safe enriched batch")

    c.setdefault("outcome_status", "PENDING_NOT_ENRICHED")
    c.setdefault("outcome_score", None)
    c.setdefault("outcome_window_days", None)

    c.setdefault("expected_return_status", "PENDING_NOT_ENRICHED")
    c.setdefault("expected_return_pct", None)

    c.setdefault("mfe_status", "NOT_ENRICHED")
    c.setdefault("mae_status", "NOT_ENRICHED")
    c.setdefault("mfe_pct", None)
    c.setdefault("mae_pct", None)

    c.setdefault("target_status", "NOT_ENRICHED")
    c.setdefault("target_1_price", None)
    c.setdefault("target_1_pct", None)
    c.setdefault("target_2_price", None)
    c.setdefault("target_2_pct", None)

    c.setdefault("failure_status", "NOT_ENRICHED")
    c.setdefault("failure_price", None)
    c.setdefault("failure_pct", None)
    c.setdefault("risk_reward_1", None)
    c.setdefault("risk_reward_2", None)

    c.setdefault("market_data_status", "NOT_ENRICHED_BATCH_LIMIT")
    c.setdefault("enrichment_status", "PENDING_NOT_ENRICHED_BATCH_LIMIT")
    c.setdefault("summary", f"{c.get('symbol') or 'Campaign'} visible; pending enriched batch")

    return c


def _step88a_merge_base_with_enriched(base_rows, enriched_rows):
    enriched_index = {}

    for enriched in enriched_rows:
        for key in _step88a_campaign_keys(enriched):
            enriched_index[key] = enriched

    merged_rows = []

    for base in base_rows:
        matched = None
        for key in _step88a_campaign_keys(base):
            matched = enriched_index.get(key)
            if matched:
                break

        if matched:
            combined = dict(base)
            combined.update(matched)
            combined.setdefault("enrichment_status", "ENRICHED_LIVE_SAFE_BATCH")
            combined.setdefault("market_data_status", "OK")
        else:
            combined = _step88a_pending_not_enriched(base)

        merged_rows.append(_step87c_b_enriched_campaign_alias(combined))

    return merged_rows


# SIGMALYTIC_STEP90B_FRONTEND_FULL_UNIVERSE_ENRICHMENT
# Campaign table now requests full-universe enriched rows up to 100 instead of enriching only the first 5.
# SIGMALYTIC_STEP88B_R2_RESILIENT_ENRICHED_FALLBACK
# Fetch enriched safe batch first so the Campaigns page never goes empty when base list endpoints 502.
def _step88a_build_campaign_rows_all_with_safe_enrichment():
    enriched_rows, enriched_error = _step88a_fetch_enriched_batch()
    base_rows, base_error, base_endpoint = _step88a_fetch_base_campaigns()

    if base_rows:
        rows = _step88a_merge_base_with_enriched(base_rows, enriched_rows)
        return rows, None

    if enriched_rows:
        rows = [_step87c_b_enriched_campaign_alias(x) for x in enriched_rows]
        return rows, None

    errors = []
    if enriched_error:
        errors.append(enriched_error)
    if base_error:
        errors.append(base_error)

    return [], " | ".join(errors) if errors else "No campaign rows returned"

# END_SIGMALYTIC_STEP88A_R3_SHOW_ALL_CAMPAIGNS_ENRICH_SAFE_BATCH



# SIGMALYTIC_STEP100R_S6_CAP_CAMPAIGN_INITIAL_PAYLOAD
# UI payload cap only. Backend campaign universe remains unchanged.
_STEP100R_S6_INITIAL_CAMPAIGN_ROWS = 40
# SIGMALYTIC_STEP100R_T_FAST_INITIAL_CAMPAIGN_LOAD
# Initial UI render must not call the full-universe enriched campaign endpoint.
# Backend campaign universe remains unchanged. This only changes the first Campaign tab payload path.
_STEP100R_T_FAST_INITIAL_CAMPAIGN_LIMIT = 40

def _step100r_t_build_campaign_rows_fast_initial():
    try:
        base_rows, base_error, base_endpoint = _step88a_fetch_base_campaigns()

        if base_rows:
            fast_rows = []
            for row in list(base_rows)[:_STEP100R_T_FAST_INITIAL_CAMPAIGN_LIMIT]:
                try:
                    fast_rows.append(_step87c_b_enriched_campaign_alias(row))
                except Exception:
                    fast_rows.append(dict(row) if isinstance(row, dict) else {"symbol": str(row)})
            return fast_rows, None

        if base_error:
            return [], base_error

        return [], "No base campaigns returned."
    except Exception as exc:
        return [], f"Fast initial Campaign load failed: {exc}"
def build_campaign_tab(session=None) -> html.Div:
    try:
        fetch_error = None
        # RE-ENABLED (2026-07-29): reverted earlier today after this call
        # caused the shared backend to repeatedly run out of memory
        # (>2GB) -- root cause was calling a heavy 100-symbol batch
        # (each involving 7 years of daily-bar cohort analysis) on
        # effectively every ~20s live-tick re-render, since the previous
        # cache TTL (20s) was barely longer than the render interval
        # itself. Now safe to re-enable: batch size reduced to 40
        # symbols, and the cache TTL raised to 600s (10 min) -- verified
        # this cache is genuinely shared across all backend workers via
        # Redis (see shared_cache.py), not per-session, so this means one
        # real fetch roughly every 10 minutes for the whole backend, not
        # one per user per tick. 10 minutes is still far more responsive
        # than the underlying data changes (once per night, via the
        # nightly campaign pipeline).
        campaigns, fetch_error = _step88a_build_campaign_rows_all_with_safe_enrichment()
    except Exception as exc:
        campaigns = []
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

        _step100r_s6_all_campaigns = list(sorted(campaigns, key=_sort_key))
        _step100r_s6_total_campaigns = len(_step100r_s6_all_campaigns)
        _step100r_s6_visible_campaigns = _step100r_s6_all_campaigns[:_STEP100R_S6_INITIAL_CAMPAIGN_ROWS]
        rows = [_campaign_row(c) for c in _step100r_s6_visible_campaigns]
        if _step100r_s6_total_campaigns > _STEP100R_S6_INITIAL_CAMPAIGN_ROWS:
            rows.append(html.Div(
                "Showing top " + str(_STEP100R_S6_INITIAL_CAMPAIGN_ROWS) + " of " + str(_step100r_s6_total_campaigns) + " campaigns. Initial UI payload is capped for fast rendering; backend universe is unchanged.",
                style={
                    "color": "#94a3b8",
                    "fontSize": "12px",
                    "fontWeight": "700",
                    "padding": "14px 16px",
                    "border": "1px solid rgba(148,163,184,.22)",
                    "borderRadius": "12px",
                    "background": "rgba(15,23,42,.55)",
                },
            ))
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
