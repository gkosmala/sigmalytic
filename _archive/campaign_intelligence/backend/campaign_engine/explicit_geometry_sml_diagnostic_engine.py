"""
D3E Explicit Geometry SML Diagnostic Engine.

Read-only diagnostic layer after:
- D3C.2A structural-location evidence enrichment
- D3C.3 structural-location validation
- D3C shadow explicit-geometry integration
- D3D v2 explicit-geometry-only production mutation gate

Purpose:
Diagnose why campaigns do or do not produce EXPLICIT_GEOMETRY SML.

This engine:
- Does not write to Supabase.
- Does not mutate campaigns.
- Does not confirm operator control.
- Does not change scores, ranks, states, transitions, gamma, probabilities,
  expected return, edge, targets, or historical outcomes.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3E_EXPLICIT_GEOMETRY_SML_DIAGNOSTIC"
ENGINE_VERSION = "phase_d3e_explicit_geometry_sml_diagnostic_v1"


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


def _run_d3c_shadow_review(evidence: Dict[str, Any], symbol: str | None, campaign_state: str | None) -> Dict[str, Any]:
    try:
        from backend.campaign_engine.wyckoff_weis_operator_confirmation_engine import (
            classify_wyckoff_weis_operator_confirmation,
        )
    except Exception:
        from campaign_engine.wyckoff_weis_operator_confirmation_engine import (
            classify_wyckoff_weis_operator_confirmation,
        )

    return classify_wyckoff_weis_operator_confirmation(
        evidence=evidence,
        symbol=symbol,
        campaign_state=campaign_state,
    )


def _run_d3d_candidate_review(campaign: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.campaign_engine.operator_control_production_mutation_gate import (
            evaluate_d3d_operator_control_candidate,
        )
    except Exception:
        from campaign_engine.operator_control_production_mutation_gate import (
            evaluate_d3d_operator_control_candidate,
        )

    return evaluate_d3d_operator_control_candidate(campaign)


def diagnose_explicit_geometry_sml(campaign: Dict[str, Any]) -> Dict[str, Any]:
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
    timeframe = _get(c, "timeframe") or evidence.get("timeframe") or "DAILY"

    current_price = _number(structural_location.get("current_price") or structural_location.get("bar_close"))
    range_floor = _number(structural_location.get("range_floor"))
    range_ceiling = _number(structural_location.get("range_ceiling"))
    range_midpoint = _number(structural_location.get("range_midpoint"))
    range_height = _number(structural_location.get("range_height"))
    range_position_pct = _number(structural_location.get("range_position_pct"))
    atr_14 = _number(structural_location.get("atr_14"))
    effective_atr = _number(structural_location.get("effective_atr"))

    explicit_geometry_available = bool(
        current_price is not None
        and range_floor is not None
        and range_ceiling is not None
        and range_ceiling > range_floor
        and effective_atr is not None
        and effective_atr > 0
    )

    lower_15_band = None
    upper_15_band = None
    distance_to_floor_atr = None
    distance_to_ceiling_atr = None

    if range_floor is not None and range_ceiling is not None and range_ceiling > range_floor:
        lower_15_band = range_floor + ((range_ceiling - range_floor) * 0.15)
        upper_15_band = range_ceiling - ((range_ceiling - range_floor) * 0.15)

    if current_price is not None and range_floor is not None and effective_atr is not None and effective_atr > 0:
        distance_to_floor_atr = (current_price - range_floor) / effective_atr

    if current_price is not None and range_ceiling is not None and effective_atr is not None and effective_atr > 0:
        distance_to_ceiling_atr = (range_ceiling - current_price) / effective_atr

    shadow = _run_d3c_shadow_review(evidence, symbol, campaign_state)
    d3d = _run_d3d_candidate_review(c)

    explicit_sml_flags_present = [
        name for name in [
            "near_range_floor",
            "standard_spring_zone",
            "spring_recaptured",
            "near_range_ceiling",
            "standard_upthrust_zone",
            "ut_failed_back_inside",
            "near_hvn_poc",
        ]
        if bool(flags.get(name))
    ]

    geometry_gap_reasons: List[str] = []

    if not structural_location:
        geometry_gap_reasons.append("No evidence.structural_location payload is present.")

    if not explicit_geometry_available:
        geometry_gap_reasons.append("Core explicit geometry is incomplete or invalid.")

    if explicit_geometry_available and shadow.get("sml_evidence_quality") != "EXPLICIT_GEOMETRY":
        geometry_gap_reasons.append("Explicit geometry exists, but current price/flags do not place campaign at an explicit SML zone.")

    if explicit_geometry_available and not explicit_sml_flags_present and not shadow.get("sml_locations"):
        geometry_gap_reasons.append("No explicit range-floor, spring, ceiling, upthrust, or HVN/POC SML flag is active.")

    if shadow.get("doctrine_confirmable") is not True:
        geometry_gap_reasons.append("D3C shadow doctrine is not confirmable.")

    if bool(operator_control.get("operator_control_confirmed")):
        geometry_gap_reasons.append("Operator control is already confirmed; D3D should not reconfirm.")

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "campaign_state": campaign_state,
        "timeframe": timeframe,

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

        "explicit_geometry_available": explicit_geometry_available,
        "current_price": current_price,
        "range_floor": range_floor,
        "range_ceiling": range_ceiling,
        "range_midpoint": range_midpoint,
        "range_height": range_height,
        "range_position_pct": range_position_pct,
        "atr_14": atr_14,
        "effective_atr": effective_atr,
        "lower_15_band": lower_15_band,
        "upper_15_band": upper_15_band,
        "distance_to_floor_atr": distance_to_floor_atr,
        "distance_to_ceiling_atr": distance_to_ceiling_atr,

        "explicit_sml_flags_present": explicit_sml_flags_present,
        "all_structural_location_flags": flags,

        "d3c_shadow_doctrine_confirmable": shadow.get("doctrine_confirmable"),
        "d3c_shadow_doctrine_verdict": shadow.get("doctrine_verdict"),
        "d3c_shadow_sml_present": shadow.get("sml_present"),
        "d3c_shadow_sml_evidence_quality": shadow.get("sml_evidence_quality"),
        "d3c_shadow_sml_locations": shadow.get("sml_locations") or [],
        "d3c_shadow_supply_exhaustion_validated": shadow.get("supply_exhaustion_validated"),
        "d3c_shadow_demand_support_validated": shadow.get("demand_support_validated"),
        "d3c_shadow_contrary_failure_present": shadow.get("contrary_failure_present"),
        "d3c_shadow_block_reasons": shadow.get("block_reasons") or [],

        "d3d_eligible_for_mutation": d3d.get("eligible_for_d3d_mutation"),
        "d3d_block_reasons": d3d.get("block_reasons") or [],
        "d3d_mutation_target": d3d.get("mutation_target"),

        "geometry_gap_reasons": geometry_gap_reasons,
    }
