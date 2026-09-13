"""
D3C.2F Macro-Anchor / Behavioral-Resolution Confluence Engine.

Read-only confluence review between:
- D3C.2E macro-anchor decision-zone evidence
- D3J operator-control plausibility evidence

Doctrine:
- Operator control is evidence, not a score.
- Behavioral-resolution confluence is diagnostic evidence only.
- This engine does not confirm operator control.
- This engine does not unconfirm operator control.
- This engine does not execute D3D.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
- This engine is not a trade signal.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3C2F_MACRO_ANCHOR_BEHAVIORAL_RESOLUTION_CONFLUENCE"
ENGINE_VERSION = "phase_d3c2f_macro_anchor_behavioral_resolution_confluence_read_only_v1"


def _bool(value: Any) -> bool:
    return bool(value is True)


def classify_macro_anchor_behavioral_resolution_confluence(
    decision_zone_row: Dict[str, Any],
    d3j_plausibility_row: Dict[str, Any] | None,
) -> Dict[str, Any]:
    d3j = d3j_plausibility_row or {}

    decision_zone_status = str(decision_zone_row.get("decision_zone_status") or "")
    decision_zone_class = str(decision_zone_row.get("decision_zone_class") or "")
    campaign_state = str(decision_zone_row.get("campaign_state") or "")
    macro_anchor_quality_tier = str(decision_zone_row.get("macro_anchor_quality_tier") or "")
    current_location_relevance = str(decision_zone_row.get("current_location_relevance") or "")

    plausibility_status = str(d3j.get("plausibility_status") or "MISSING_D3J_PLAUSIBILITY_ROW")
    no_drift_status = str(d3j.get("no_drift_status") or "UNKNOWN_D3J_NO_DRIFT_STATUS")

    shadow_confirmable = _bool(d3j.get("shadow_confirmable"))
    legacy_operator_control_confirmed = _bool(d3j.get("legacy_operator_control_confirmed"))
    d3d_production_confirmed = _bool(d3j.get("d3d_production_confirmed"))
    d3d_eligible_dry_run_only = _bool(d3j.get("d3d_eligible_dry_run_only"))

    in_decision_zone = decision_zone_status == "IN_IMMEDIATE_RESISTANCE_DECISION_ZONE"
    advanced_decision_zone = decision_zone_class in {
        "HIGH_QUALITY_ADVANCED_DECISION_ZONE",
        "ACCEPTABLE_ADVANCED_DECISION_ZONE",
    }
    high_quality_advanced_decision_zone = decision_zone_class == "HIGH_QUALITY_ADVANCED_DECISION_ZONE"
    early_decision_zone = decision_zone_class in {
        "HIGH_QUALITY_EARLY_DECISION_ZONE",
        "ACCEPTABLE_EARLY_DECISION_ZONE",
    }

    confluence_flags: List[str] = []
    confluence_notes: List[str] = []
    caution_flags: List[str] = list(decision_zone_row.get("caution_flags") or [])

    if in_decision_zone:
        confluence_flags.append("D3C2E_IMMEDIATE_RESISTANCE_DECISION_ZONE")
        confluence_notes.append("Macro-anchor evidence places the campaign at immediate validated resistance.")
        caution_flags.append("DECISION_ZONE_REQUIRES_SEPARATE_BEHAVIORAL_RESOLUTION")

    if advanced_decision_zone:
        confluence_flags.append("ADVANCED_CAMPAIGN_STATE_DECISION_ZONE")

    if high_quality_advanced_decision_zone:
        confluence_flags.append("HIGH_QUALITY_ADVANCED_DECISION_ZONE")

    if early_decision_zone:
        confluence_flags.append("EARLY_CAMPAIGN_STATE_DECISION_ZONE")
        caution_flags.append("EARLY_STATE_ALREADY_AT_RESISTANCE_CAUTION")

    if shadow_confirmable:
        confluence_flags.append("D3J_SHADOW_CONFIRMABLE")
        confluence_notes.append("D3J identifies shadow-confirmable operator-control plausibility; this remains unconfirmed diagnostic evidence.")

    if plausibility_status == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED":
        confluence_flags.append("D3J_STEALTH_UNCONFIRMED_PLAUSIBILITY")
    elif plausibility_status == "LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE":
        confluence_flags.append("D3J_LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE")
    elif plausibility_status == "LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE":
        confluence_flags.append("D3J_LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE")
    elif plausibility_status == "NOT_SHADOW_CONFIRMABLE":
        confluence_flags.append("D3J_NOT_SHADOW_CONFIRMABLE")
    elif plausibility_status == "MISSING_D3J_PLAUSIBILITY_ROW":
        confluence_flags.append("MISSING_D3J_PLAUSIBILITY_ROW")
        caution_flags.append("MISSING_D3J_PLAUSIBILITY_ROW")

    if d3d_production_confirmed:
        confluence_flags.append("UNEXPECTED_D3D_PRODUCTION_CONFIRMATION_PRESENT")
        caution_flags.append("NO_DRIFT_GUARDRAIL_REVIEW_REQUIRED")

    if in_decision_zone and plausibility_status == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED":
        behavioral_resolution_confluence_status = "DECISION_ZONE_WITH_D3J_STEALTH_PLAUSIBILITY_UNCONFIRMED"
    elif in_decision_zone and plausibility_status == "LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE":
        behavioral_resolution_confluence_status = "DECISION_ZONE_WITH_LEGACY_SHADOW_CONFIRMABLE_OPERATOR_EVIDENCE"
    elif in_decision_zone and plausibility_status == "LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE":
        behavioral_resolution_confluence_status = "DECISION_ZONE_WITH_LEGACY_NOT_CURRENTLY_SHADOW_CONFIRMABLE_OPERATOR_EVIDENCE"
    elif in_decision_zone and plausibility_status == "NOT_SHADOW_CONFIRMABLE":
        behavioral_resolution_confluence_status = "DECISION_ZONE_WITH_NO_CURRENT_SHADOW_CONFIRMABILITY"
    elif not in_decision_zone and plausibility_status == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED":
        behavioral_resolution_confluence_status = "NON_DECISION_ZONE_WITH_D3J_STEALTH_PLAUSIBILITY_UNCONFIRMED"
    elif not in_decision_zone and plausibility_status.startswith("LEGACY_OPERATOR_CONTROL"):
        behavioral_resolution_confluence_status = "NON_DECISION_ZONE_WITH_LEGACY_OPERATOR_CONTROL_EVIDENCE"
    elif not in_decision_zone and plausibility_status == "NOT_SHADOW_CONFIRMABLE":
        behavioral_resolution_confluence_status = "NON_DECISION_ZONE_WITH_NO_CURRENT_SHADOW_CONFIRMABILITY"
    else:
        behavioral_resolution_confluence_status = "UNCLASSIFIED_D3C2F_CONFLUENCE_CONTEXT"

    if high_quality_advanced_decision_zone and shadow_confirmable and not d3d_production_confirmed:
        confluence_priority = "HIGH_PRIORITY_UNCONFIRMED_BEHAVIORAL_RESOLUTION_REVIEW"
        confluence_notes.append("High-quality advanced decision-zone context overlaps D3J shadow-confirmable plausibility.")
    elif advanced_decision_zone and shadow_confirmable and not d3d_production_confirmed:
        confluence_priority = "ADVANCED_DECISION_ZONE_WITH_D3J_PLAUSIBILITY_REVIEW"
        confluence_notes.append("Advanced decision-zone context overlaps D3J shadow-confirmable plausibility.")
    elif advanced_decision_zone and not shadow_confirmable:
        confluence_priority = "ADVANCED_DECISION_ZONE_REQUIRES_BEHAVIORAL_RESOLUTION_EVIDENCE"
        confluence_notes.append("Advanced decision-zone context lacks current D3J shadow-confirmable evidence.")
    elif early_decision_zone:
        confluence_priority = "EARLY_DECISION_ZONE_RUNWAY_CAUTION_REVIEW"
        confluence_notes.append("Early campaign state is already at resistance; runway requires caution.")
    elif shadow_confirmable:
        confluence_priority = "NON_DECISION_ZONE_D3J_PLAUSIBILITY_MONITOR"
        confluence_notes.append("D3J plausibility exists outside the immediate macro resistance decision zone.")
    else:
        confluence_priority = "BACKGROUND_CONTEXT_ONLY"

    if in_decision_zone:
        behavioral_resolution_requirement = "SEPARATE_BEHAVIORAL_RESOLUTION_REQUIRED_BEFORE_ANY_OPERATOR_CONTROL_CONFIRMATION"
    else:
        behavioral_resolution_requirement = "NO_DECISION_ZONE_RESOLUTION_REQUIREMENT_FROM_D3C2F"

    d3c2f_no_drift_status = "PASS"
    if d3d_production_confirmed:
        d3c2f_no_drift_status = "REVIEW_REQUIRED_D3D_PRODUCTION_CONFIRMATION_PRESENT"
    if no_drift_status != "PASS":
        d3c2f_no_drift_status = "REVIEW_REQUIRED_D3J_NO_DRIFT_NOT_PASS"

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": decision_zone_row.get("symbol"),
        "campaign_id": decision_zone_row.get("campaign_id"),
        "campaign_state": campaign_state,

        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_unconfirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "d3d_execution_allowed": False,
        "d3d_source_used_by_this_engine": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,

        "decision_zone_status": decision_zone_status,
        "decision_zone_class": decision_zone_class,
        "macro_anchor_quality_tier": macro_anchor_quality_tier,
        "current_location_relevance": current_location_relevance,

        "d3j_plausibility_status": plausibility_status,
        "d3j_no_drift_status": no_drift_status,
        "d3j_shadow_confirmable": shadow_confirmable,
        "d3j_legacy_operator_control_confirmed": legacy_operator_control_confirmed,
        "d3j_d3d_production_confirmed": d3d_production_confirmed,
        "d3j_d3d_eligible_dry_run_only": d3d_eligible_dry_run_only,

        "behavioral_resolution_confluence_status": behavioral_resolution_confluence_status,
        "confluence_priority": confluence_priority,
        "behavioral_resolution_requirement": behavioral_resolution_requirement,
        "confluence_flags": confluence_flags,
        "confluence_notes": confluence_notes,
        "caution_flags": caution_flags,
        "d3c2f_no_drift_status": d3c2f_no_drift_status,

        "source_d3c2e_row": decision_zone_row,
        "source_d3j_row": d3j,
    }
