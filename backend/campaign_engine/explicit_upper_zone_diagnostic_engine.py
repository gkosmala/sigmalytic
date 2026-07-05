"""
D3F Explicit Upper-Zone / Upthrust Diagnostic Engine.

Read-only diagnostic layer.

Purpose:
Separate explicit constructive lower-zone SML from explicit upper-zone / upthrust
risk-side SML so that D3D does not drift by treating all explicit geometry as
operator-control confirmation.

This engine:
- Does not write to Supabase.
- Does not mutate campaigns.
- Does not confirm operator control.
- Does not change scores, ranks, states, transitions, gamma, probabilities,
  expected return, edge, targets, or historical outcomes.
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3F_EXPLICIT_UPPER_ZONE_DIAGNOSTIC"
ENGINE_VERSION = "phase_d3f_explicit_upper_zone_diagnostic_v1"


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


def diagnose_explicit_upper_zone(campaign: Dict[str, Any]) -> Dict[str, Any]:
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
    range_position_pct = _number(structural_location.get("range_position_pct"))
    effective_atr = _number(structural_location.get("effective_atr"))

    distance_to_ceiling_atr = None
    distance_to_floor_atr = None

    if current_price is not None and range_ceiling is not None and effective_atr is not None and effective_atr > 0:
        distance_to_ceiling_atr = (range_ceiling - current_price) / effective_atr

    if current_price is not None and range_floor is not None and effective_atr is not None and effective_atr > 0:
        distance_to_floor_atr = (current_price - range_floor) / effective_atr

    near_range_floor = bool(flags.get("near_range_floor"))
    standard_spring_zone = bool(flags.get("standard_spring_zone"))
    spring_recaptured = bool(flags.get("spring_recaptured"))

    near_range_ceiling = bool(flags.get("near_range_ceiling"))
    standard_upthrust_zone = bool(flags.get("standard_upthrust_zone"))
    ut_failed_back_inside = bool(flags.get("ut_failed_back_inside"))

    constructive_lower_zone = bool(
        near_range_floor
        or standard_spring_zone
        or spring_recaptured
    )

    explicit_upper_zone = bool(
        near_range_ceiling
        or standard_upthrust_zone
        or ut_failed_back_inside
    )

    upper_zone_classification = "NO_EXPLICIT_UPPER_ZONE"

    if explicit_upper_zone and ut_failed_back_inside:
        upper_zone_classification = "EXPLICIT_UPTHRUST_FAILURE_BACK_INSIDE_RANGE"

    elif explicit_upper_zone and standard_upthrust_zone:
        upper_zone_classification = "EXPLICIT_UPTHRUST_ZONE_RISK"

    elif explicit_upper_zone and near_range_ceiling:
        upper_zone_classification = "EXPLICIT_RANGE_CEILING_TEST"

    doctrine_handling = "NO_D3D_CONFIRMATION_IMPACT"

    if constructive_lower_zone and not explicit_upper_zone:
        doctrine_handling = "CONSTRUCTIVE_SML_CANDIDATE_FOR_D3D_IF_DOCTRINE_CONFIRMS"

    elif explicit_upper_zone:
        doctrine_handling = "RISK_SIDE_SML_DIAGNOSTIC_ONLY_NOT_OPERATOR_CONTROL_CONFIRMATION"

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

        "operator_control_confirmed_current": bool(operator_control.get("operator_control_confirmed")),

        "current_price": current_price,
        "range_floor": range_floor,
        "range_ceiling": range_ceiling,
        "range_position_pct": range_position_pct,
        "distance_to_floor_atr": distance_to_floor_atr,
        "distance_to_ceiling_atr": distance_to_ceiling_atr,

        "near_range_floor": near_range_floor,
        "standard_spring_zone": standard_spring_zone,
        "spring_recaptured": spring_recaptured,

        "near_range_ceiling": near_range_ceiling,
        "standard_upthrust_zone": standard_upthrust_zone,
        "ut_failed_back_inside": ut_failed_back_inside,

        "constructive_lower_zone": constructive_lower_zone,
        "explicit_upper_zone": explicit_upper_zone,
        "upper_zone_classification": upper_zone_classification,
        "doctrine_handling": doctrine_handling,
    }
