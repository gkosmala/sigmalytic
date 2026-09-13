
"""
D3C.1 Structural Location Input Review Engine.
Read-only diagnostic audit.
This engine does NOT confirm operator control.
This engine does NOT write to Supabase.
This engine does NOT mutate campaigns.
This engine does NOT change scores, ranks, states, transitions, or confirmations.
Purpose:
    Determine whether active campaign evidence contains enough explicit
    structural-location inputs to locate Wyckoff / Weis events inside the
    campaign structure.
Better phrase than "Wyckoff location geometry":
    Structural Location Review.
"""
from typing import Any, Dict, List
ENGINE_NAME = "STRUCTURAL_LOCATION_INPUT_REVIEW"
ENGINE_VERSION = "phase_d3c_1_structural_location_input_review_v1"
INPUT_ALIASES: Dict[str, List[str]] = {
    "current_price": [
        "close", "last_close", "price", "last_price", "current_price",
        "latest_price", "mark", "last"
    ],
    "range_floor": [
        "tr_floor", "trading_range_floor", "range_floor", "range_low",
        "base_low", "support_floor", "floor_price", "accumulation_floor",
        "lower_bound", "lower_boundary"
    ],
    "range_ceiling": [
        "tr_ceiling", "trading_range_ceiling", "range_ceiling", "range_high",
        "base_high", "resistance_ceiling", "ceiling_price", "accumulation_ceiling",
        "upper_bound", "upper_boundary"
    ],
    "atr": [
        "atr", "atr14", "atr_14", "average_true_range", "average_true_range_14"
    ],
    "support": [
        "support", "support_level", "structural_support", "support_price",
        "test_low", "test_bar_low", "spring_low", "swing_low", "pivot_low",
        "last_support"
    ],
    "resistance": [
        "resistance", "resistance_level", "structural_resistance",
        "resistance_price", "swing_high", "pivot_high", "range_resistance",
        "last_resistance"
    ],
    "hvn_poc": [
        "hvn", "high_volume_node", "volume_profile_poc", "poc", "vpoc",
        "volume_node", "major_volume_node", "high_volume_zone",
        "volume_profile_node"
    ],
    "spring_shakeout": [
        "spring", "spring_test", "shakeout", "shakeout_test",
        "liquidity_sweep", "liquidity_pool", "lp_zone",
        "breakdown_recapture", "recapture_after_breakdown", "spring_low"
    ],
    "last_point_of_support": [
        "lps", "last_point_of_support", "backup", "backup_to_edge",
        "test_after_sos", "support_test", "successful_test"
    ],
    "upthrust_utad": [
        "upthrust", "utad", "ut_ad", "upthrust_after_distribution",
        "upthrust_supply", "buying_climax", "no_demand_test",
        "failed_breakout", "resistance_rejection"
    ],
    "price_series": [
        "bars", "daily_bars", "ohlcv", "price_history",
        "historical_bars", "candles", "series", "quotes"
    ],
}
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
def _normalize_key(value: Any) -> str:
    text = str(value).strip().lower()
    for ch in ["_", "-", " ", ".", "/", "\\"]:
        text = text.replace(ch, "")
    return text
def _value_summary(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "dict", "keys_sample": list(value.keys())[:8], "size": len(value)}
    if isinstance(value, list):
        return {"type": "list", "size": len(value)}
    if isinstance(value, tuple):
        return {"type": "tuple", "size": len(value)}
    return {"type": type(value).__name__, "preview": str(value)[:80]}
def _walk(value: Any, path: str = "evidence", depth: int = 0, max_depth: int = 8):
    if depth > max_depth:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + "." + str(key)
            yield child_path, str(key), child
            yield from _walk(child, child_path, depth + 1, max_depth)
    elif isinstance(value, list):
        for idx, child in enumerate(value[:5]):
            child_path = path + "[" + str(idx) + "]"
            yield from _walk(child, child_path, depth + 1, max_depth)
def find_structural_input_matches(evidence: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    evidence = _as_dict(evidence)
    alias_lookup: Dict[str, str] = {}
    for group, aliases in INPUT_ALIASES.items():
        for alias in aliases:
            alias_lookup[_normalize_key(alias)] = group
    matches: Dict[str, List[Dict[str, Any]]] = {
        group: [] for group in INPUT_ALIASES.keys()
    }
    for path, key, value in _walk(evidence):
        group = alias_lookup.get(_normalize_key(key))
        if not group:
            continue
        if len(matches[group]) >= 12:
            continue
        matches[group].append({
            "path": path,
            "key": key,
            "value_summary": _value_summary(value),
        })
    return matches
def _footprint_archetypes(evidence: Dict[str, Any]) -> List[str]:
    footprints = _as_dict(evidence.get("early_operator_footprints"))
    names: List[str] = []
    for item in _as_list(footprints.get("footprint_archetypes")):
        if isinstance(item, dict):
            name = item.get("archetype")
        else:
            name = item
        if name:
            names.append(str(name))
    return names
def review_structural_location_inputs(
    evidence: Dict[str, Any],
    symbol: str | None = None,
    campaign_state: str | None = None,
) -> Dict[str, Any]:
    evidence = _as_dict(evidence)
    matches = find_structural_input_matches(evidence)
    available_groups = [group for group, rows in matches.items() if rows]
    missing_groups = [group for group, rows in matches.items() if not rows]
    current_price_available = bool(matches.get("current_price"))
    range_floor_available = bool(matches.get("range_floor"))
    range_ceiling_available = bool(matches.get("range_ceiling"))
    atr_available = bool(matches.get("atr"))
    support_available = bool(matches.get("support"))
    resistance_available = bool(matches.get("resistance"))
    hvn_poc_available = bool(matches.get("hvn_poc"))
    spring_shakeout_available = bool(matches.get("spring_shakeout"))
    lps_available = bool(matches.get("last_point_of_support"))
    upthrust_available = bool(matches.get("upthrust_utad"))
    price_series_available = bool(matches.get("price_series"))
    explicit_trading_range_ready = (
        current_price_available and range_floor_available and range_ceiling_available
    )
    explicit_lp_zone_ready = (
        current_price_available and range_floor_available and atr_available
    )
    explicit_hvn_zone_ready = (
        current_price_available and hvn_poc_available
    )
    explicit_support_resistance_ready = (
        current_price_available and support_available and resistance_available
    )
    structural_event_inputs_present = any([
        spring_shakeout_available,
        lps_available,
        upthrust_available,
    ])
    explicit_location_ready = any([
        explicit_trading_range_ready,
        explicit_lp_zone_ready,
        explicit_hvn_zone_ready,
        explicit_support_resistance_ready,
    ])
    archetypes = _footprint_archetypes(evidence)
    classical_event_inference_available = any(
        item in archetypes
        for item in [
            "SPRING_TEST",
            "NO_SUPPLY_TEST",
            "CLIMACTIC_STOPPING",
            "REACCUMULATION_ABSORPTION",
        ]
    )
    if explicit_location_ready:
        readiness = "EXPLICIT_LOCATION_READY"
    elif current_price_available and structural_event_inputs_present:
        readiness = "PARTIAL_EXPLICIT_EVENT_LOCATION_READY"
    elif classical_event_inference_available:
        readiness = "INFERRED_CLASSICAL_EVENT_ONLY"
    else:
        readiness = "MISSING_CORE_LOCATION_INPUTS"
    readiness_reasons: List[str] = []
    if explicit_trading_range_ready:
        readiness_reasons.append("Current price, range floor, and range ceiling are available.")
    if explicit_lp_zone_ready:
        readiness_reasons.append("Current price, range floor, and ATR are available for liquidity-pool / spring-zone testing.")
    if explicit_hvn_zone_ready:
        readiness_reasons.append("Current price and HVN/POC are available for volume-node proximity testing.")
    if explicit_support_resistance_ready:
        readiness_reasons.append("Current price, support, and resistance are available.")
    if current_price_available and structural_event_inputs_present and not explicit_location_ready:
        readiness_reasons.append("Current price plus at least one structural event input is available, but full explicit location is incomplete.")
    if classical_event_inference_available and not explicit_location_ready:
        readiness_reasons.append("Classical footprint archetypes allow inference, but explicit price structure is missing.")
    if not readiness_reasons:
        readiness_reasons.append("Core structural-location inputs are missing from the current evidence payload.")
    production_sml_possible_now = bool(explicit_location_ready)
    recommendation = (
        "Production SML can use explicit structural inputs."
        if production_sml_possible_now
        else "Do not production-confirm location yet; add explicit structural fields before mutation."
    )
    matched_paths = {
        group: [row["path"] for row in rows]
        for group, rows in matches.items()
        if rows
    }
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
        "structural_location_readiness": readiness,
        "production_sml_possible_now": production_sml_possible_now,
        "readiness_reasons": readiness_reasons,
        "recommendation": recommendation,
        "explicit_trading_range_ready": explicit_trading_range_ready,
        "explicit_lp_zone_ready": explicit_lp_zone_ready,
        "explicit_hvn_zone_ready": explicit_hvn_zone_ready,
        "explicit_support_resistance_ready": explicit_support_resistance_ready,
        "current_price_available": current_price_available,
        "range_floor_available": range_floor_available,
        "range_ceiling_available": range_ceiling_available,
        "atr_available": atr_available,
        "support_available": support_available,
        "resistance_available": resistance_available,
        "hvn_poc_available": hvn_poc_available,
        "spring_shakeout_available": spring_shakeout_available,
        "last_point_of_support_available": lps_available,
        "upthrust_utad_available": upthrust_available,
        "price_series_available": price_series_available,
        "available_input_groups": available_groups,
        "missing_input_groups": missing_groups,
        "matched_paths": matched_paths,
        "field_match_count_by_group": {
            group: len(rows)
            for group, rows in matches.items()
        },
        "field_matches_limited": {
            group: rows
            for group, rows in matches.items()
            if rows
        },
        "footprint_archetypes": archetypes,
        "classical_event_inference_available": classical_event_inference_available,
        "input_alias_groups": INPUT_ALIASES,
    }
