"""
D3G Explicit SML Taxonomy Audit Engine.

Read-only no-drift diagnostic layer.

Purpose:
Audit whether explicit SML evidence is being separated into the correct
doctrinal taxonomy:

1. Constructive lower-zone SML:
   - range floor
   - spring zone
   - spring recapture

2. Risk-side upper-zone SML:
   - range ceiling
   - upthrust zone
   - failed upthrust back inside range

This engine does not repair D3C.
This engine does not alter D3D.
This engine does not write to Supabase.
This engine does not mutate campaigns.
This engine does not confirm operator control.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3G_EXPLICIT_SML_TAXONOMY_AUDIT"
ENGINE_VERSION = "phase_d3g_explicit_sml_taxonomy_audit_v1"


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


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def audit_explicit_sml_taxonomy(campaign: Dict[str, Any]) -> Dict[str, Any]:
    c = _as_dict(campaign)
    evidence = _as_dict(_get(c, "evidence", {}))
    structural_location = _as_dict(evidence.get("structural_location"))
    flags = _as_dict(structural_location.get("flags"))
    operator_control = _as_dict(evidence.get("operator_control"))

    symbol = _get(c, "symbol")
    campaign_id = _get(c, "campaign_id") or _get(c, "id")
    campaign_state = (
        _get(c, "current_state")
        or _get(c, "state_enum")
        or _get(c, "campaign_state")
        or _get(c, "state")
        or _get(c, "lifecycle_state")
        or _get(c, "campaign_lifecycle_state")
    )

    current_price = _number(structural_location.get("current_price") or structural_location.get("bar_close"))
    range_floor = _number(structural_location.get("range_floor"))
    range_ceiling = _number(structural_location.get("range_ceiling"))
    range_position_pct = _number(structural_location.get("range_position_pct"))
    effective_atr = _number(structural_location.get("effective_atr"))

    distance_to_floor_atr = None
    distance_to_ceiling_atr = None

    if current_price is not None and range_floor is not None and effective_atr is not None and effective_atr > 0:
        distance_to_floor_atr = (current_price - range_floor) / effective_atr

    if current_price is not None and range_ceiling is not None and effective_atr is not None and effective_atr > 0:
        distance_to_ceiling_atr = (range_ceiling - current_price) / effective_atr

    lower_flags = []
    upper_flags = []

    for flag in ["near_range_floor", "standard_spring_zone", "spring_recaptured"]:
        if bool(flags.get(flag)):
            lower_flags.append(flag)

    for flag in ["near_range_ceiling", "standard_upthrust_zone", "ut_failed_back_inside"]:
        if bool(flags.get(flag)):
            upper_flags.append(flag)

    constructive_lower_zone = bool(lower_flags)
    risk_side_upper_zone = bool(upper_flags)

    taxonomy_classification = "NO_EXPLICIT_SML"

    if constructive_lower_zone and risk_side_upper_zone:
        taxonomy_classification = "MIXED_LOWER_CONSTRUCTIVE_AND_UPPER_RISK"
    elif constructive_lower_zone:
        taxonomy_classification = "CONSTRUCTIVE_LOWER_ZONE_SML"
    elif risk_side_upper_zone:
        taxonomy_classification = "RISK_SIDE_UPPER_ZONE_SML"

    d3d_allowed_by_taxonomy = bool(constructive_lower_zone and not risk_side_upper_zone)

    risk_side_must_not_confirm_operator_control = bool(risk_side_upper_zone)

    no_drift_status = "PASS"

    drift_findings: List[str] = []

    if risk_side_upper_zone and d3d_allowed_by_taxonomy:
        no_drift_status = "FAIL"
        drift_findings.append("Risk-side upper-zone SML was allowed as D3D-confirmable taxonomy.")

    if risk_side_upper_zone:
        drift_findings.append("Upper-zone/upthrust evidence must remain diagnostic-risk evidence only.")

    if constructive_lower_zone:
        drift_findings.append("Lower-zone/spring evidence may be constructive SML only if doctrine confirms.")

    if not constructive_lower_zone and not risk_side_upper_zone:
        drift_findings.append("No explicit SML taxonomy flags are active.")

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "campaign_state": campaign_state,

        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "operator_control_confirmed_current": bool(operator_control.get("operator_control_confirmed")),

        "current_price": current_price,
        "range_floor": range_floor,
        "range_ceiling": range_ceiling,
        "range_position_pct": range_position_pct,
        "distance_to_floor_atr": distance_to_floor_atr,
        "distance_to_ceiling_atr": distance_to_ceiling_atr,

        "lower_zone_flags": lower_flags,
        "upper_zone_flags": upper_flags,
        "constructive_lower_zone": constructive_lower_zone,
        "risk_side_upper_zone": risk_side_upper_zone,
        "taxonomy_classification": taxonomy_classification,

        "d3d_allowed_by_taxonomy": d3d_allowed_by_taxonomy,
        "risk_side_must_not_confirm_operator_control": risk_side_must_not_confirm_operator_control,
        "no_drift_status": no_drift_status,
        "drift_findings": drift_findings,
    }
