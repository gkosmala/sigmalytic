"""
D3C.2D Macro-Anchor State Alignment Engine.

Read-only alignment review between:
- D3C.2C macro-anchor quality tier
- campaign state
- current macro-location relevance

Doctrine:
- Operator control is evidence, not a score.
- State / macro-anchor alignment is structural-location diagnostic evidence only.
- This engine does not confirm operator control.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
- This engine is not a trade signal.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3C2D_MACRO_ANCHOR_STATE_ALIGNMENT"
ENGINE_VERSION = "phase_d3c2d_macro_anchor_state_alignment_read_only_v1"


def _upper(value: Any) -> str:
    if value is None:
        return ""
    return str(value).upper()


def classify_macro_anchor_state_alignment(campaign: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.campaign_engine.external_macro_anchor_quality_tier_engine import classify_macro_anchor_quality
    except Exception:
        from campaign_engine.external_macro_anchor_quality_tier_engine import classify_macro_anchor_quality

    base = classify_macro_anchor_quality(campaign)

    campaign_state = _upper(base.get("campaign_state"))
    quality_tier = str(base.get("macro_anchor_quality_tier") or "")
    location_relevance = str(base.get("current_location_relevance") or "")
    caution_flags = list(base.get("caution_flags") or [])

    notes: List[str] = []
    alignment_flags: List[str] = []

    is_birth = campaign_state == "BIRTH"
    is_confirmed = campaign_state == "CONFIRMED"
    is_surviving = campaign_state == "SURVIVING"
    is_expanding = campaign_state == "EXPANDING"

    is_tier_a = quality_tier == "TIER_A_DUAL_ANCHOR_HIGH_QUALITY"
    is_tier_b = quality_tier == "TIER_B_DUAL_ANCHOR_ACCEPTABLE"
    is_tier_c = quality_tier == "TIER_C_STRONG_SUPPORT_ONLY"
    is_tier_d = quality_tier == "TIER_D_PARTIAL_OR_WEAK_MACRO_CONTEXT"
    is_tier_e = quality_tier == "TIER_E_BLOCKED_OR_INSUFFICIENT_MACRO_ANCHOR"

    immediate_resistance = location_relevance == "IMMEDIATE_RESISTANCE_TEST"
    near_support = location_relevance == "NEAR_VALIDATED_SUPPORT"
    range_context = location_relevance == "VALIDATED_RANGE_CONTEXT"
    support_context = location_relevance == "VALIDATED_SUPPORT_CONTEXT"
    no_macro_context = location_relevance == "NO_VALIDATED_MACRO_LOCATION_CONTEXT"

    if immediate_resistance:
        alignment_flags.append("AT_IMMEDIATE_VALIDATED_RESISTANCE")
        notes.append("Campaign is at or near validated overhead macro resistance; this is a decision-zone diagnostic, not confirmation.")

    if near_support:
        alignment_flags.append("NEAR_VALIDATED_SUPPORT")
        notes.append("Campaign is near validated support; this provides structural-location context only.")

    if range_context:
        alignment_flags.append("INSIDE_VALIDATED_MACRO_RANGE")
        notes.append("Campaign has validated support and resistance context without immediate resistance classification.")

    if support_context:
        alignment_flags.append("SUPPORT_CONTEXT_WITHOUT_VALIDATED_OVERHEAD_RESISTANCE")
        notes.append("Campaign has validated support context but lacks validated resistance context.")

    if no_macro_context:
        alignment_flags.append("NO_VALIDATED_MACRO_LOCATION_CONTEXT")
        notes.append("Macro-location evidence is insufficient or blocked.")

    if is_tier_a and (is_surviving or is_expanding) and immediate_resistance:
        state_macro_alignment_class = "DECISION_ZONE_HIGH_QUALITY_SURVIVING_OR_EXPANDING"
        notes.append("High-quality macro anchors align with advanced campaign state, but price is testing immediate resistance.")
    elif is_tier_a and (is_surviving or is_expanding):
        state_macro_alignment_class = "HIGH_QUALITY_ADVANCED_CAMPAIGN_CONTEXT"
        notes.append("High-quality macro anchors align with surviving or expanding campaign state.")
    elif is_tier_a and (is_birth or is_confirmed):
        state_macro_alignment_class = "HIGH_QUALITY_EARLY_CAMPAIGN_CONTEXT"
        notes.append("High-quality macro anchors exist while campaign remains early or newly confirmed.")
    elif is_tier_b and immediate_resistance:
        state_macro_alignment_class = "ACCEPTABLE_DUAL_ANCHOR_DECISION_ZONE"
        notes.append("Dual-anchor context is acceptable, but immediate resistance requires caution.")
    elif is_tier_b:
        state_macro_alignment_class = "ACCEPTABLE_DUAL_ANCHOR_STATE_CONTEXT"
        notes.append("Dual-anchor context is acceptable but not high-quality.")
    elif is_tier_c and (is_surviving or is_expanding):
        state_macro_alignment_class = "STRONG_SUPPORT_ADVANCED_CAMPAIGN_CONTEXT"
        notes.append("Strong support exists in an advanced campaign, but overhead resistance is not validated.")
    elif is_tier_c:
        state_macro_alignment_class = "STRONG_SUPPORT_EARLY_OR_PARTIAL_CONTEXT"
        notes.append("Strong support exists, but macro resistance is absent or insufficient.")
    elif is_tier_d:
        state_macro_alignment_class = "WEAK_PARTIAL_MACRO_CONTEXT"
        notes.append("Macro-anchor evidence is partial or weak.")
    elif is_tier_e:
        state_macro_alignment_class = "BLOCKED_OR_INSUFFICIENT_MACRO_CONTEXT"
        notes.append("Macro-anchor evidence is blocked or insufficient.")
    else:
        state_macro_alignment_class = "UNCLASSIFIED_MACRO_STATE_CONTEXT"
        notes.append("Macro-anchor state alignment could not be classified.")

    if is_birth and immediate_resistance:
        alignment_flags.append("EARLY_STATE_AT_RESISTANCE_DECISION_ZONE")

    if is_surviving and immediate_resistance:
        alignment_flags.append("SURVIVING_STATE_AT_RESISTANCE_DECISION_ZONE")

    if is_expanding and immediate_resistance:
        alignment_flags.append("EXPANDING_STATE_AT_RESISTANCE_DECISION_ZONE")

    if is_confirmed and no_macro_context:
        alignment_flags.append("CONFIRMED_STATE_WITHOUT_VALIDATED_MACRO_CONTEXT")

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

        "macro_anchor_quality_tier": quality_tier,
        "current_location_relevance": location_relevance,
        "d3c2b_macro_anchor_status": base.get("d3c2b_macro_anchor_status"),

        "state_macro_alignment_class": state_macro_alignment_class,
        "alignment_flags": alignment_flags,
        "alignment_notes": notes,
        "caution_flags": caution_flags,

        "support_touch_count": base.get("support_touch_count"),
        "support_rejection_count": base.get("support_rejection_count"),
        "support_distance_atr": base.get("support_distance_atr"),
        "support_distance_bucket": base.get("support_distance_bucket"),

        "resistance_touch_count": base.get("resistance_touch_count"),
        "resistance_rejection_count": base.get("resistance_rejection_count"),
        "resistance_distance_atr": base.get("resistance_distance_atr"),
        "resistance_distance_bucket": base.get("resistance_distance_bucket"),

        "source_d3c2c_row": base,
    }
