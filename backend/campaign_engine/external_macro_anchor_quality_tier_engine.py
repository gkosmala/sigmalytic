"""
D3C.2C External Macro-Anchor Quality Tier Engine.

Read-only quality-tier review over D3C.2B macro-anchor evidence.

Doctrine:
- Operator control is evidence, not a score.
- Macro-anchor quality tiers are structural-location diagnostics only.
- This engine does not confirm operator control.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
- This engine is not a trade signal.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Dict, List, Optional


ENGINE_NAME = "D3C2C_EXTERNAL_MACRO_ANCHOR_QUALITY_TIER"
ENGINE_VERSION = "phase_d3c2c_external_macro_anchor_quality_tier_read_only_v1"


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return {}
    if hasattr(value, "dict"):
        try:
            return value.dict()
        except Exception:
            return {}
    return {}


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        number = float(value)
        if not isfinite(number):
            return default
        return number
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    number = _safe_float(value, None)
    if number is None:
        return default
    return int(number)


def _distance_bucket(distance_atr: Any) -> str:
    value = _safe_float(distance_atr, None)
    if value is None:
        return "UNKNOWN_DISTANCE"
    if value <= 1.0:
        return "IMMEDIATE_WITHIN_1_ATR"
    if value <= 2.0:
        return "NEAR_WITHIN_2_ATR"
    if value <= 5.0:
        return "MODERATE_WITHIN_5_ATR"
    if value <= 10.0:
        return "DISTANT_WITHIN_10_ATR"
    return "VERY_DISTANT_OVER_10_ATR"


def classify_macro_anchor_quality(campaign: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.campaign_engine.external_macro_anchor_enrichment_engine import evaluate_external_macro_anchor
    except Exception:
        from campaign_engine.external_macro_anchor_enrichment_engine import evaluate_external_macro_anchor

    base = evaluate_external_macro_anchor(campaign)

    support = _as_dict(base.get("macro_support"))
    resistance = _as_dict(base.get("macro_resistance"))

    support_validated = bool(support.get("validated") is True)
    resistance_validated = bool(resistance.get("validated") is True)

    support_touch_count = _safe_int(support.get("touch_count"))
    support_rejection_count = _safe_int(support.get("rejection_count"))
    resistance_touch_count = _safe_int(resistance.get("touch_count"))
    resistance_rejection_count = _safe_int(resistance.get("rejection_count"))

    support_last_touch_age = _safe_float(support.get("last_touch_age_bars"), None)
    resistance_last_touch_age = _safe_float(resistance.get("last_touch_age_bars"), None)

    support_distance_atr = _safe_float(support.get("distance_atr"), None)
    resistance_distance_atr = _safe_float(resistance.get("distance_atr"), None)

    usable_bar_count = _safe_int(base.get("usable_bar_count"))

    support_acceptable = bool(
        support_validated
        and support_touch_count >= 2
        and support_rejection_count >= 1
        and support_last_touch_age is not None
        and support_last_touch_age <= 126
    )

    resistance_acceptable = bool(
        resistance_validated
        and resistance_touch_count >= 2
        and resistance_rejection_count >= 1
        and resistance_last_touch_age is not None
        and resistance_last_touch_age <= 126
    )

    support_strong = bool(
        support_validated
        and support_touch_count >= 5
        and support_rejection_count >= 2
        and support_last_touch_age is not None
        and support_last_touch_age <= 126
    )

    resistance_strong = bool(
        resistance_validated
        and resistance_touch_count >= 5
        and resistance_rejection_count >= 2
        and resistance_last_touch_age is not None
        and resistance_last_touch_age <= 126
    )

    quality_notes: List[str] = []
    caution_flags: List[str] = []

    if usable_bar_count < 120:
        caution_flags.append("LESS_THAN_120_USABLE_BARS")

    if not support_validated:
        caution_flags.append("SUPPORT_ANCHOR_NOT_VALIDATED")
    elif not support_strong:
        caution_flags.append("SUPPORT_ANCHOR_ACCEPTABLE_BUT_NOT_STRONG")

    if not resistance_validated:
        caution_flags.append("RESISTANCE_ANCHOR_NOT_VALIDATED")
    elif not resistance_strong:
        caution_flags.append("RESISTANCE_ANCHOR_ACCEPTABLE_BUT_NOT_STRONG")

    if support_distance_atr is not None and support_distance_atr > 10.0:
        caution_flags.append("SUPPORT_ANCHOR_VERY_DISTANT_CONTEXT_ONLY")

    if resistance_distance_atr is not None and resistance_distance_atr <= 1.0:
        caution_flags.append("RESISTANCE_ANCHOR_IMMEDIATE_OVERHEAD")

    if support_strong and resistance_strong and usable_bar_count >= 120:
        quality_tier = "TIER_A_DUAL_ANCHOR_HIGH_QUALITY"
        quality_notes.append("Both support and resistance anchors are validated with strong touch/rejection evidence.")
    elif support_acceptable and resistance_acceptable:
        quality_tier = "TIER_B_DUAL_ANCHOR_ACCEPTABLE"
        quality_notes.append("Both support and resistance anchors are validated but at least one side is not high quality.")
    elif support_strong and not resistance_acceptable:
        quality_tier = "TIER_C_STRONG_SUPPORT_ONLY"
        quality_notes.append("Support anchor is strong, but resistance anchor is absent or insufficient.")
    elif support_acceptable or resistance_acceptable:
        quality_tier = "TIER_D_PARTIAL_OR_WEAK_MACRO_CONTEXT"
        quality_notes.append("At least one macro anchor is acceptable, but the macro frame is incomplete or weak.")
    else:
        quality_tier = "TIER_E_BLOCKED_OR_INSUFFICIENT_MACRO_ANCHOR"
        quality_notes.append("Macro-anchor evidence is blocked or insufficient for structural-location reliance.")

    if resistance_validated and resistance_distance_atr is not None and resistance_distance_atr <= 1.0:
        current_location_relevance = "IMMEDIATE_RESISTANCE_TEST"
    elif support_validated and support_distance_atr is not None and support_distance_atr <= 2.0:
        current_location_relevance = "NEAR_VALIDATED_SUPPORT"
    elif support_validated and resistance_validated:
        current_location_relevance = "VALIDATED_RANGE_CONTEXT"
    elif support_validated:
        current_location_relevance = "VALIDATED_SUPPORT_CONTEXT"
    elif resistance_validated:
        current_location_relevance = "VALIDATED_RESISTANCE_CONTEXT"
    else:
        current_location_relevance = "NO_VALIDATED_MACRO_LOCATION_CONTEXT"

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,

        "symbol": base.get("symbol"),
        "campaign_id": base.get("campaign_id"),
        "campaign_state": base.get("campaign_state"),

        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,

        "d3c2b_macro_anchor_status": base.get("macro_anchor_status"),
        "d3c2b_macro_anchor_validated_count": base.get("macro_anchor_validated_count"),
        "macro_anchor_quality_tier": quality_tier,
        "current_location_relevance": current_location_relevance,
        "quality_notes": quality_notes,
        "caution_flags": caution_flags,

        "usable_bar_count": usable_bar_count,

        "support_validated": support_validated,
        "support_touch_count": support_touch_count,
        "support_rejection_count": support_rejection_count,
        "support_last_touch_age_bars": support_last_touch_age,
        "support_distance_atr": support_distance_atr,
        "support_distance_bucket": _distance_bucket(support_distance_atr),

        "resistance_validated": resistance_validated,
        "resistance_touch_count": resistance_touch_count,
        "resistance_rejection_count": resistance_rejection_count,
        "resistance_last_touch_age_bars": resistance_last_touch_age,
        "resistance_distance_atr": resistance_distance_atr,
        "resistance_distance_bucket": _distance_bucket(resistance_distance_atr),

        "old_pivot_gate_policy": base.get("old_pivot_gate_policy"),
        "source_d3c2b_row": base,
    }
