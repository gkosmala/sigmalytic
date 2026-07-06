"""
D3C.2G High-Priority Behavioral-Resolution Evidence Engine.

Read-only evidence review above D3C.2F.

Purpose:
- Inspect high-priority D3C.2F confluence rows.
- Expose the exact D3J behavioral-resolution evidence fields.
- Classify completeness of behavioral-resolution evidence without confirming operator control.

Doctrine:
- Operator control is evidence, not a score.
- Behavioral-resolution evidence is diagnostic evidence only.
- This engine does not confirm operator control.
- This engine does not unconfirm operator control.
- This engine does not execute D3D.
- This engine does not use D3D as a production source.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
- This engine is not a trade signal.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3C2G_HIGH_PRIORITY_BEHAVIORAL_RESOLUTION_EVIDENCE"
ENGINE_VERSION = "phase_d3c2g_high_priority_behavioral_resolution_evidence_read_only_v1"


def _bool(value: Any) -> bool:
    return bool(value is True)


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def classify_high_priority_resolution_evidence(confluence_row: Dict[str, Any]) -> Dict[str, Any]:
    d3j = confluence_row.get("source_d3j_row") or {}
    d3c2e = confluence_row.get("source_d3c2e_row") or {}

    confluence_priority = str(confluence_row.get("confluence_priority") or "")
    decision_zone_class = str(confluence_row.get("decision_zone_class") or "")
    d3j_plausibility_status = str(confluence_row.get("d3j_plausibility_status") or "")

    is_high_priority = confluence_priority == "HIGH_PRIORITY_UNCONFIRMED_BEHAVIORAL_RESOLUTION_REVIEW"

    demand_support = _bool(d3j.get("d3c_shadow_demand_support_validated"))
    supply_exhaustion = _bool(d3j.get("d3c_shadow_supply_exhaustion_validated"))
    contrary_failure = _bool(d3j.get("d3c_shadow_contrary_failure_present"))
    explicit_geometry_sml = d3j.get("d3c_shadow_explicit_geometry_sml")
    sml_evidence_quality = d3j.get("d3c_shadow_sml_evidence_quality")

    # explicit_geometry_sml is a Boolean doctrine gate.
    # False means explicit structural-location geometry is NOT present.
    # Do not treat Boolean false as a present value merely because it serializes to "False".
    explicit_sml_present = _bool(explicit_geometry_sml)
    sml_quality_present = _present(sml_evidence_quality)

    d3j_no_drift_status = str(d3j.get("no_drift_status") or "UNKNOWN_D3J_NO_DRIFT_STATUS")
    d3j_shadow_confirmable = _bool(d3j.get("shadow_confirmable"))
    d3j_d3d_production_confirmed = _bool(d3j.get("d3d_production_confirmed"))

    evidence_flags: List[str] = []
    evidence_notes: List[str] = []
    caution_flags: List[str] = list(confluence_row.get("caution_flags") or [])

    if is_high_priority:
        evidence_flags.append("D3C2F_HIGH_PRIORITY_CONFLUENCE_ROW")
        evidence_notes.append("Row is high-priority because high-quality advanced decision-zone context overlaps D3J shadow-confirmable plausibility.")
    else:
        evidence_flags.append("NOT_D3C2F_HIGH_PRIORITY_CONFLUENCE_ROW")

    if demand_support:
        evidence_flags.append("D3J_DEMAND_SUPPORT_VALIDATED")

    if supply_exhaustion:
        evidence_flags.append("D3J_SUPPLY_EXHAUSTION_VALIDATED")

    if contrary_failure:
        evidence_flags.append("D3J_CONTRARY_FAILURE_PRESENT")

    if explicit_sml_present:
        evidence_flags.append("D3J_EXPLICIT_GEOMETRY_SML_PRESENT")
    else:
        caution_flags.append("D3J_EXPLICIT_GEOMETRY_SML_MISSING")

    if sml_quality_present:
        evidence_flags.append("D3J_SML_EVIDENCE_QUALITY_PRESENT")
    else:
        caution_flags.append("D3J_SML_EVIDENCE_QUALITY_MISSING")

    if d3j_shadow_confirmable:
        evidence_flags.append("D3J_SHADOW_CONFIRMABLE")
        evidence_notes.append("D3J shadow-confirmable status remains diagnostic and unconfirmed.")

    if d3j_d3d_production_confirmed:
        evidence_flags.append("UNEXPECTED_D3D_PRODUCTION_CONFIRMATION_PRESENT")
        caution_flags.append("NO_DRIFT_REVIEW_REQUIRED_D3D_PRODUCTION_CONFIRMATION_PRESENT")

    if demand_support and supply_exhaustion and contrary_failure and explicit_sml_present and sml_quality_present:
        behavioral_resolution_evidence_class = "FULL_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
    elif demand_support and supply_exhaustion and explicit_sml_present:
        behavioral_resolution_evidence_class = "PARTIAL_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
    elif demand_support or supply_exhaustion or contrary_failure or explicit_sml_present or sml_quality_present:
        behavioral_resolution_evidence_class = "INCOMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
    else:
        behavioral_resolution_evidence_class = "NO_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"

    if is_high_priority and behavioral_resolution_evidence_class == "FULL_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY":
        d3c2g_review_priority = "HIGHEST_REVIEW_PRIORITY_FULL_EVIDENCE_UNCONFIRMED"
        evidence_notes.append("Full behavioral-resolution evidence is present, but this remains read-only and unconfirmed.")
    elif is_high_priority and behavioral_resolution_evidence_class == "PARTIAL_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY":
        d3c2g_review_priority = "HIGH_REVIEW_PRIORITY_PARTIAL_EVIDENCE_UNCONFIRMED"
    elif is_high_priority and behavioral_resolution_evidence_class == "INCOMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY":
        d3c2g_review_priority = "HIGH_REVIEW_PRIORITY_INCOMPLETE_EVIDENCE_UNCONFIRMED"
    elif is_high_priority:
        d3c2g_review_priority = "HIGH_REVIEW_PRIORITY_NO_EVIDENCE_DETAIL_PRESENT"
    elif d3j_shadow_confirmable:
        d3c2g_review_priority = "BACKGROUND_D3J_SHADOW_CONFIRMABLE_MONITOR"
    else:
        d3c2g_review_priority = "BACKGROUND_CONTEXT_ONLY"

    if is_high_priority:
        behavioral_resolution_requirement = "FULL_BEHAVIORAL_RESOLUTION_REVIEW_REQUIRED_BEFORE_ANY_OPERATOR_CONTROL_CONFIRMATION"
    else:
        behavioral_resolution_requirement = "NO_HIGH_PRIORITY_RESOLUTION_REQUIREMENT_FROM_D3C2G"

    d3c2g_no_drift_status = "PASS"
    if d3j_no_drift_status != "PASS":
        d3c2g_no_drift_status = "REVIEW_REQUIRED_D3J_NO_DRIFT_NOT_PASS"
    if d3j_d3d_production_confirmed:
        d3c2g_no_drift_status = "REVIEW_REQUIRED_D3D_PRODUCTION_CONFIRMATION_PRESENT"

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,

        "symbol": confluence_row.get("symbol"),
        "campaign_id": confluence_row.get("campaign_id"),
        "campaign_state": confluence_row.get("campaign_state"),

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

        "source_confluence_priority": confluence_priority,
        "is_high_priority_confluence_row": is_high_priority,
        "decision_zone_class": decision_zone_class,
        "d3j_plausibility_status": d3j_plausibility_status,

        "behavioral_resolution_evidence_class": behavioral_resolution_evidence_class,
        "d3c2g_review_priority": d3c2g_review_priority,
        "behavioral_resolution_requirement": behavioral_resolution_requirement,

        "d3j_shadow_confirmable": d3j_shadow_confirmable,
        "d3j_no_drift_status": d3j_no_drift_status,
        "d3j_d3d_production_confirmed": d3j_d3d_production_confirmed,

        "d3c_shadow_doctrine_verdict": d3j.get("d3c_shadow_doctrine_verdict"),
        "d3c_shadow_explicit_geometry_sml": explicit_geometry_sml,
        "d3c_shadow_sml_evidence_quality": sml_evidence_quality,
        "d3c_shadow_demand_support_validated": demand_support,
        "d3c_shadow_supply_exhaustion_validated": supply_exhaustion,
        "d3c_shadow_contrary_failure_present": contrary_failure,

        "operator_control_method_basis": d3j.get("operator_control_method_basis"),
        "operator_control_evidence_count": d3j.get("operator_control_evidence_count"),
        "operator_control_status": d3j.get("operator_control_status"),
        "operator_control_verdict": d3j.get("operator_control_verdict"),

        "macro_anchor_quality_tier": confluence_row.get("macro_anchor_quality_tier"),
        "current_location_relevance": confluence_row.get("current_location_relevance"),
        "support_touch_count": d3c2e.get("support_touch_count"),
        "support_rejection_count": d3c2e.get("support_rejection_count"),
        "support_distance_atr": d3c2e.get("support_distance_atr"),
        "resistance_touch_count": d3c2e.get("resistance_touch_count"),
        "resistance_rejection_count": d3c2e.get("resistance_rejection_count"),
        "resistance_distance_atr": d3c2e.get("resistance_distance_atr"),
        "resistance_distance_bucket": d3c2e.get("resistance_distance_bucket"),

        "evidence_flags": evidence_flags,
        "evidence_notes": evidence_notes,
        "caution_flags": caution_flags,
        "d3c2g_no_drift_status": d3c2g_no_drift_status,

        "source_d3c2f_row": confluence_row,
        "source_d3j_row": d3j,
        "source_d3c2e_row": d3c2e,
    }

