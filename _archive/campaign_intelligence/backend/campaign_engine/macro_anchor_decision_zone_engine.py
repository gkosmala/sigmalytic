"""
D3C.2E Macro-Anchor Decision-Zone Engine.

Read-only decision-zone review over D3C.2D state / macro-anchor alignment.

Purpose:
- Isolate campaigns at immediate validated macro resistance.
- Separate early-state decision-zone context from advanced-state decision-zone context.
- Preserve all no-drift doctrine boundaries.

Doctrine:
- Operator control is evidence, not a score.
- Decision-zone status is structural-location diagnostic evidence only.
- This engine does not confirm operator control.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
- This engine is not a trade signal.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3C2E_MACRO_ANCHOR_DECISION_ZONE"
ENGINE_VERSION = "phase_d3c2e_macro_anchor_decision_zone_read_only_v1"


def _upper(value: Any) -> str:
    if value is None:
        return ""
    return str(value).upper()


def _safe_float(value: Any):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def classify_macro_anchor_decision_zone(campaign: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.campaign_engine.external_macro_anchor_state_alignment_engine import (
            classify_macro_anchor_state_alignment,
        )
    except Exception:
        from campaign_engine.external_macro_anchor_state_alignment_engine import (
            classify_macro_anchor_state_alignment,
        )

    base = classify_macro_anchor_state_alignment(campaign)

    campaign_state = _upper(base.get("campaign_state"))
    quality_tier = str(base.get("macro_anchor_quality_tier") or "")
    location_relevance = str(base.get("current_location_relevance") or "")
    state_alignment = str(base.get("state_macro_alignment_class") or "")
    resistance_distance_atr = _safe_float(base.get("resistance_distance_atr"))

    base_alignment_flags = list(base.get("alignment_flags") or [])
    base_caution_flags = list(base.get("caution_flags") or [])

    decision_zone_flags: List[str] = []
    decision_zone_notes: List[str] = []
    caution_flags: List[str] = list(base_caution_flags)

    is_birth = campaign_state == "BIRTH"
    is_confirmed = campaign_state == "CONFIRMED"
    is_surviving = campaign_state == "SURVIVING"
    is_expanding = campaign_state == "EXPANDING"
    is_advanced = is_surviving or is_expanding
    is_early = is_birth or is_confirmed

    is_tier_a = quality_tier == "TIER_A_DUAL_ANCHOR_HIGH_QUALITY"
    is_tier_b = quality_tier == "TIER_B_DUAL_ANCHOR_ACCEPTABLE"

    in_immediate_resistance_zone = location_relevance == "IMMEDIATE_RESISTANCE_TEST"

    if not in_immediate_resistance_zone:
        decision_zone_status = "NOT_IN_IMMEDIATE_RESISTANCE_DECISION_ZONE"
        decision_zone_class = "NON_DECISION_ZONE_MACRO_CONTEXT"
        decision_zone_notes.append("Campaign is not classified as testing immediate validated macro resistance.")
    else:
        decision_zone_status = "IN_IMMEDIATE_RESISTANCE_DECISION_ZONE"
        decision_zone_flags.append("IMMEDIATE_VALIDATED_RESISTANCE_TEST")
        decision_zone_notes.append("Campaign is at or near validated macro resistance; this is a diagnostic decision zone only.")

        if resistance_distance_atr is not None and resistance_distance_atr <= 0.50:
            decision_zone_flags.append("RESISTANCE_TEST_CORE_WITHIN_HALF_ATR")
        elif resistance_distance_atr is not None and resistance_distance_atr <= 1.00:
            decision_zone_flags.append("RESISTANCE_TEST_WITHIN_ONE_ATR")

        if is_advanced:
            decision_zone_flags.append("ADVANCED_CAMPAIGN_STATE_AT_DECISION_ZONE")
            decision_zone_notes.append("Advanced campaign state is testing immediate resistance; continuation requires separate behavioral confirmation.")

        if is_early:
            decision_zone_flags.append("EARLY_CAMPAIGN_STATE_AT_DECISION_ZONE")
            decision_zone_notes.append("Early campaign state is already near resistance; this may limit clean structural runway.")

        if is_tier_a and is_advanced:
            decision_zone_class = "HIGH_QUALITY_ADVANCED_DECISION_ZONE"
            decision_zone_notes.append("High-quality dual macro anchors and advanced state converge at resistance.")
        elif is_tier_a and is_early:
            decision_zone_class = "HIGH_QUALITY_EARLY_DECISION_ZONE"
            decision_zone_notes.append("High-quality dual macro anchors exist, but the campaign is early while already testing resistance.")
        elif is_tier_b and is_advanced:
            decision_zone_class = "ACCEPTABLE_ADVANCED_DECISION_ZONE"
            decision_zone_notes.append("Acceptable dual macro anchors and advanced state converge at resistance.")
        elif is_tier_b and is_early:
            decision_zone_class = "ACCEPTABLE_EARLY_DECISION_ZONE"
            decision_zone_notes.append("Acceptable dual macro anchors exist, but the campaign is early while already testing resistance.")
        else:
            decision_zone_class = "OTHER_IMMEDIATE_RESISTANCE_DECISION_ZONE"
            decision_zone_notes.append("Immediate resistance is present, but quality/state pairing is not a primary D3C.2E class.")

    if in_immediate_resistance_zone:
        caution_flags.append("DECISION_ZONE_IS_NOT_BREAKOUT_CONFIRMATION")
        caution_flags.append("REQUIRES_SEPARATE_BEHAVIORAL_RESOLUTION_EVIDENCE")

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

        "decision_zone_status": decision_zone_status,
        "decision_zone_class": decision_zone_class,
        "decision_zone_flags": decision_zone_flags,
        "decision_zone_notes": decision_zone_notes,

        "macro_anchor_quality_tier": quality_tier,
        "current_location_relevance": location_relevance,
        "state_macro_alignment_class": state_alignment,
        "source_alignment_flags": base_alignment_flags,
        "caution_flags": caution_flags,

        "support_touch_count": base.get("support_touch_count"),
        "support_rejection_count": base.get("support_rejection_count"),
        "support_distance_atr": base.get("support_distance_atr"),
        "support_distance_bucket": base.get("support_distance_bucket"),

        "resistance_touch_count": base.get("resistance_touch_count"),
        "resistance_rejection_count": base.get("resistance_rejection_count"),
        "resistance_distance_atr": base.get("resistance_distance_atr"),
        "resistance_distance_bucket": base.get("resistance_distance_bucket"),

        "source_d3c2d_row": base,
    }
