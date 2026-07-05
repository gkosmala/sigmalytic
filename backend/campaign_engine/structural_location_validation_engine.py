"""
D3C.3 Structural Location Validation Engine.
Read-only structural-location validator.
This engine does NOT confirm operator control.
This engine does NOT write to Supabase.
This engine does NOT mutate campaigns.
This engine does NOT change scores, ranks, states, transitions, or confirmations.
Purpose:
    Validate that D3C.2 structural-location evidence is internally coherent
    before any future D3D production mutation gate is allowed to rely on it.
"""
from math import isfinite
from typing import Any, Dict, List, Optional
ENGINE_NAME = "STRUCTURAL_LOCATION_VALIDATION_REVIEW"
ENGINE_VERSION = "phase_d3c_3_structural_location_validation_review_v1"
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
def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
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
def _is_finite_number(value: Any) -> bool:
    return _safe_float(value, None) is not None
def _close_enough(a: Any, b: Any, tolerance: float) -> bool:
    left = _safe_float(a, None)
    right = _safe_float(b, None)
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance
def _nested(mapping: Dict[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
def validate_structural_location(
    evidence: Dict[str, Any],
    symbol: str | None = None,
    campaign_state: str | None = None,
    d3c1_review: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    evidence = _as_dict(evidence)
    structural_location = _as_dict(evidence.get("structural_location"))
    d3c1_review = _as_dict(d3c1_review)
    passed_checks: List[str] = []
    failed_checks: List[str] = []
    warnings: List[str] = []
    if not structural_location:
        failed_checks.append("structural_location payload is missing.")
    sl_guardrail_ok = True
    if structural_location:
        expected_guardrails = {
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
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
        }
        for key, expected in expected_guardrails.items():
            actual = structural_location.get(key)
            if actual != expected:
                sl_guardrail_ok = False
                failed_checks.append(
                    f"structural_location guardrail mismatch: {key} expected {expected!r}, got {actual!r}."
                )
        if sl_guardrail_ok:
            passed_checks.append("structural_location guardrails are intact.")
    required_fields = [
        "current_price",
        "bar_high",
        "bar_low",
        "bar_close",
        "range_floor",
        "range_ceiling",
        "range_midpoint",
        "range_height",
        "range_position_pct",
        "atr_14",
        "effective_atr",
        "support_level",
        "resistance_level",
        "primary_tr",
        "current_bar",
        "volatility",
        "support_resistance",
        "flags",
        "price_series",
    ]
    missing_required_fields = [
        field for field in required_fields
        if field not in structural_location or structural_location.get(field) is None
    ]
    if missing_required_fields:
        failed_checks.append(
            "Missing required structural-location fields: "
            + ", ".join(missing_required_fields)
            + "."
        )
    elif structural_location:
        passed_checks.append("All D3C.3 required structural-location fields are present.")
    current_price = _safe_float(structural_location.get("current_price"), None)
    bar_high = _safe_float(structural_location.get("bar_high"), None)
    bar_low = _safe_float(structural_location.get("bar_low"), None)
    bar_close = _safe_float(structural_location.get("bar_close"), None)
    range_floor = _safe_float(structural_location.get("range_floor"), None)
    range_ceiling = _safe_float(structural_location.get("range_ceiling"), None)
    range_height = _safe_float(structural_location.get("range_height"), None)
    range_midpoint = _safe_float(structural_location.get("range_midpoint"), None)
    range_position_pct = _safe_float(structural_location.get("range_position_pct"), None)
    atr_14 = _safe_float(structural_location.get("atr_14"), None)
    effective_atr = _safe_float(structural_location.get("effective_atr"), None)
    numeric_core_ready = all(
        value is not None
        for value in [
            current_price,
            bar_high,
            bar_low,
            bar_close,
            range_floor,
            range_ceiling,
            range_height,
            range_midpoint,
            range_position_pct,
            atr_14,
            effective_atr,
        ]
    )
    if numeric_core_ready:
        passed_checks.append("Core structural-location numeric fields are finite.")
    else:
        failed_checks.append("One or more core structural-location numeric fields are missing or non-finite.")
    range_bounds_valid = bool(
        range_floor is not None
        and range_ceiling is not None
        and range_height is not None
        and range_floor < range_ceiling
        and range_height > 0
    )
    if range_bounds_valid:
        passed_checks.append("Range floor, ceiling, and height are structurally valid.")
    else:
        failed_checks.append("Range floor, ceiling, and height are not structurally valid.")
    range_height_matches_bounds = False
    midpoint_matches_bounds = False
    position_matches_bounds = False
    if range_bounds_valid:
        calculated_height = float(range_ceiling - range_floor)
        height_tolerance = max(0.01, abs(calculated_height) * 0.005)
        range_height_matches_bounds = _close_enough(range_height, calculated_height, height_tolerance)
        calculated_midpoint = float(range_floor + (calculated_height / 2.0))
        midpoint_tolerance = max(0.01, abs(calculated_midpoint) * 0.0025)
        midpoint_matches_bounds = _close_enough(range_midpoint, calculated_midpoint, midpoint_tolerance)
        if current_price is not None and range_position_pct is not None:
            calculated_position = ((current_price - range_floor) / calculated_height) * 100.0
            position_matches_bounds = _close_enough(range_position_pct, calculated_position, 0.50)
    if range_height_matches_bounds:
        passed_checks.append("Range height matches range ceiling minus range floor.")
    else:
        failed_checks.append("Range height does not match range ceiling minus range floor.")
    if midpoint_matches_bounds:
        passed_checks.append("Range midpoint matches floor/ceiling midpoint.")
    else:
        failed_checks.append("Range midpoint does not match floor/ceiling midpoint.")
    if position_matches_bounds:
        passed_checks.append("Range position percent matches current price and range bounds.")
    else:
        failed_checks.append("Range position percent does not match current price and range bounds.")
    current_bar = _as_dict(structural_location.get("current_bar"))
    current_bar_consistent = bool(
        current_bar
        and _close_enough(current_bar.get("close"), current_price, 0.01)
        and _close_enough(bar_close, current_price, 0.01)
        and bar_low is not None
        and bar_high is not None
        and current_price is not None
        and bar_low <= current_price <= bar_high
    )
    if current_bar_consistent:
        passed_checks.append("Current bar is internally consistent with current price.")
    else:
        failed_checks.append("Current bar is not internally consistent with current price.")
    volatility = _as_dict(structural_location.get("volatility"))
    atr_valid = bool(
        effective_atr is not None
        and effective_atr > 0
        and (
            (atr_14 is not None and atr_14 > 0)
            or structural_location.get("atr_source") == "fallback_range_height_5pct"
            or volatility.get("atr_source") == "fallback_range_height_5pct"
        )
    )
    if atr_valid:
        passed_checks.append("ATR/effective ATR is valid for structural-location testing.")
    else:
        failed_checks.append("ATR/effective ATR is not valid for structural-location testing.")
    support_resistance = _as_dict(structural_location.get("support_resistance"))
    support_level = _safe_float(structural_location.get("support_level"), None)
    resistance_level = _safe_float(structural_location.get("resistance_level"), None)
    sr_support = _safe_float(support_resistance.get("support_level"), None)
    sr_resistance = _safe_float(support_resistance.get("resistance_level"), None)
    support_resistance_consistent = bool(
        support_level is not None
        and resistance_level is not None
        and range_floor is not None
        and range_ceiling is not None
        and _close_enough(support_level, range_floor, max(0.01, abs(range_floor) * 0.0025))
        and _close_enough(resistance_level, range_ceiling, max(0.01, abs(range_ceiling) * 0.0025))
        and _close_enough(sr_support, range_floor, max(0.01, abs(range_floor) * 0.0025))
        and _close_enough(sr_resistance, range_ceiling, max(0.01, abs(range_ceiling) * 0.0025))
    )
    if support_resistance_consistent:
        passed_checks.append("Support/resistance fields are consistent with range floor/ceiling.")
    else:
        failed_checks.append("Support/resistance fields are not consistent with range floor/ceiling.")
    price_series = _as_dict(structural_location.get("price_series"))
    bars = _as_list(price_series.get("bars"))
    usable_bar_count = 0
    for bar in bars:
        row = _as_dict(bar)
        if all(
            _is_finite_number(row.get(key))
            for key in ["open", "high", "low", "close", "volume"]
        ):
            usable_bar_count += 1
    price_series_usable = bool(len(bars) >= 14 and usable_bar_count >= 14)
    if price_series_usable:
        passed_checks.append("Price series contains at least 14 usable OHLCV bars.")
    else:
        failed_checks.append("Price series does not contain at least 14 usable OHLCV bars.")
    flags = _as_dict(structural_location.get("flags"))
    spring_recaptured = bool(flags.get("spring_recaptured"))
    ut_failed_back_inside = bool(flags.get("ut_failed_back_inside"))
    spring_flag_valid = True
    if spring_recaptured:
        spring_flag_valid = bool(
            bar_low is not None
            and range_floor is not None
            and current_price is not None
            and bar_low < range_floor
            and current_price >= range_floor
        )
    ut_flag_valid = True
    if ut_failed_back_inside:
        ut_flag_valid = bool(
            bar_high is not None
            and range_ceiling is not None
            and current_price is not None
            and bar_high > range_ceiling
            and current_price <= range_ceiling
        )
    if spring_flag_valid and ut_flag_valid:
        passed_checks.append("Spring/upthrust failure flags are logically coherent when present.")
    else:
        failed_checks.append("Spring/upthrust failure flags are not logically coherent.")
    d3c1_explicit_ready = bool(d3c1_review.get("production_sml_possible_now"))
    d3c1_readiness = str(d3c1_review.get("structural_location_readiness") or "")
    if d3c1_explicit_ready and d3c1_readiness == "EXPLICIT_LOCATION_READY":
        passed_checks.append("D3C.1 confirms explicit structural-location readiness.")
    else:
        failed_checks.append("D3C.1 does not confirm explicit structural-location readiness.")
    hvn_poc_available = bool(d3c1_review.get("hvn_poc_available"))
    if not hvn_poc_available:
        warnings.append("HVN/POC is still missing; this is optional for D3C.3 primary validation but remains a later enrichment gap.")
    validation_passed = bool(
        structural_location
        and not missing_required_fields
        and sl_guardrail_ok
        and numeric_core_ready
        and range_bounds_valid
        and range_height_matches_bounds
        and midpoint_matches_bounds
        and position_matches_bounds
        and current_bar_consistent
        and atr_valid
        and support_resistance_consistent
        and price_series_usable
        and spring_flag_valid
        and ut_flag_valid
        and d3c1_explicit_ready
        and d3c1_readiness == "EXPLICIT_LOCATION_READY"
    )
    if not structural_location:
        validation_status = "MISSING_STRUCTURAL_LOCATION"
    elif validation_passed:
        validation_status = "STRUCTURAL_LOCATION_VALIDATED"
    else:
        validation_status = "STRUCTURAL_LOCATION_VALIDATION_FAILED"
    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_state": campaign_state,
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
        "state_transition_enabled": False,
        "not_a_trade_signal": True,
        "validation_status": validation_status,
        "structural_location_validation_passed": validation_passed,
        "production_sml_validation_passed": validation_passed,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "missing_required_fields": missing_required_fields,
        "range_bounds_valid": range_bounds_valid,
        "range_height_matches_bounds": range_height_matches_bounds,
        "range_midpoint_matches_bounds": midpoint_matches_bounds,
        "range_position_matches_bounds": position_matches_bounds,
        "current_bar_consistent": current_bar_consistent,
        "atr_valid": atr_valid,
        "support_resistance_consistent": support_resistance_consistent,
        "price_series_usable": price_series_usable,
        "price_series_bar_count": len(bars),
        "price_series_usable_bar_count": usable_bar_count,
        "spring_upthrust_flags_valid": bool(spring_flag_valid and ut_flag_valid),
        "d3c1_structural_location_readiness": d3c1_readiness,
        "d3c1_production_sml_possible_now": d3c1_explicit_ready,
        "hvn_poc_available": hvn_poc_available,
        "structural_location_engine": structural_location.get("engine"),
        "structural_location_version": structural_location.get("version"),
    }
