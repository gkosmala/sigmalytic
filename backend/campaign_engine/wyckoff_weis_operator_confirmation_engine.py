
"""
D3C Wyckoff / Weis Composite Operator Confirmation Engine.

Shadow-production / diagnostic-only.

This engine does NOT confirm operator control in production.
This engine does NOT write to Supabase.
This engine does NOT mutate campaigns.
This engine does NOT change scores, ranks, states, or transitions.

Doctrine:
Composite Operator Control =
    Tested Supply Exhaustion
    AND Active Demand / Support Validation
    AND Structurally Meaningful Location
    AND NOT Contrary Failure
"""

from typing import Any, Dict, List


ENGINE_NAME = "WYCKOFF_WEIS_OPERATOR_CONFIRMATION_SHADOW"
ENGINE_VERSION = "phase_d3c_shadow_read_only_v1"


SUPPLY_EXHAUSTION_FLAGS = [
    "shortening_downside_thrust",
    "effort_vs_result_divergence",
    "no_supply_test",
    "supply_failure",
    "high_volume_controlled_spread",
]

DEMAND_SUPPORT_FLAGS = [
    "demand_efficiency_dominates_supply",
    "recapture_after_breakdown",
    "survives_adverse_tests",
    "absorption_against_resistance",
    "high_volume_controlled_spread",
]

CONTRARY_FAILURE_FLAGS = [
    "no_demand_test",
    "upthrust_supply",
    "buying_climax",
    "post_test_structural_failure",
    "failed_test",
    "test_low_broken",
]

CONTRARY_RISK_CONTEXT = [
    "VSA_NO_DEMAND_CAUTION",
    "UPTHRUST_SUPPLY_CAUTION",
    "BUYING_CLIMAX_CAUTION",
    "POST_TEST_FAILURE_CAUTION",
]

STRUCTURAL_ARCHETYPES = [
    "CLIMACTIC_STOPPING",
    "REACCUMULATION_ABSORPTION",
    "SPRING_TEST",
    "NO_SUPPLY_TEST",
]

LP_ZONE_ARCHETYPES = [
    "SPRING_TEST",
    "NO_SUPPLY_TEST",
]

TR_FLOOR_ARCHETYPES = [
    "CLIMACTIC_STOPPING",
    "REACCUMULATION_ABSORPTION",
]

HVN_PROXY_FLAGS = [
    "high_volume_controlled_spread",
]


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


def _true_flags(payload: Dict[str, Any], names: List[str]) -> List[str]:
    payload = _as_dict(payload)
    return [name for name in names if bool(payload.get(name))]


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _footprint_archetype_names(footprints: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for item in _as_list(footprints.get("footprint_archetypes")):
        item_dict = _as_dict(item)
        if item_dict:
            name = item_dict.get("archetype")
        else:
            name = item
        if name:
            names.append(str(name))
    return names


def _detect_structurally_meaningful_location(
    evidence: Dict[str, Any],
    footprints: Dict[str, Any],
    raw_flags: Dict[str, Any],
    vsa_weis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Shadow SML detection.

    Production-grade SML should later use explicit price geometry:
      - TR floor / ceiling
      - ATR
      - HVN / volume profile node
      - liquidity pool zone

    This shadow version accepts explicit geometry when present and otherwise
    marks an inferred structural location only when the footprint itself is
    tied to a classical structural event such as Spring, No-Supply Test,
    Climactic Stopping, or Re-Accumulation Absorption.
    """
    archetypes = _footprint_archetype_names(footprints)

    locations: List[str] = []
    reasons: List[str] = []
    evidence_quality = "MISSING"

    # Explicit geometry path, if available in future payloads.
    price = _number(
        evidence.get("close")
        or evidence.get("price")
        or evidence.get("last_price")
        or evidence.get("current_price")
    )

    tr_floor = _number(
        evidence.get("tr_floor")
        or evidence.get("trading_range_floor")
        or evidence.get("range_floor")
    )

    tr_ceiling = _number(
        evidence.get("tr_ceiling")
        or evidence.get("trading_range_ceiling")
        or evidence.get("range_ceiling")
    )

    atr = _number(evidence.get("atr") or evidence.get("atr_14") or evidence.get("ATR14"))

    hvn = _number(
        evidence.get("hvn")
        or evidence.get("high_volume_node")
        or evidence.get("volume_profile_poc")
        or evidence.get("poc")
    )

    if price is not None and tr_floor is not None and tr_ceiling is not None and tr_ceiling > tr_floor:
        lower_band = tr_floor + ((tr_ceiling - tr_floor) * 0.15)
        if price <= lower_band:
            locations.append("TR_FLOOR")
            reasons.append("Price is in the lower 15 percent of explicit trading-range geometry.")
            evidence_quality = "EXPLICIT_GEOMETRY"

    if price is not None and hvn is not None and hvn > 0:
        if abs(price - hvn) / hvn <= 0.015:
            locations.append("HVN")
            reasons.append("Price is within 1.5 percent of explicit high-volume node / POC.")
            evidence_quality = "EXPLICIT_GEOMETRY"

    if price is not None and tr_floor is not None and atr is not None and atr > 0:
        if tr_floor - (3 * atr) <= price <= tr_floor:
            locations.append("LP_ZONE")
            reasons.append("Price is within 3 ATR below explicit range floor / liquidity-pool zone.")
            evidence_quality = "EXPLICIT_GEOMETRY"

    # Inferred structural path, used only when explicit geometry is absent.
    if not locations:
        if any(name in archetypes for name in LP_ZONE_ARCHETYPES):
            locations.append("LP_ZONE_INFERRED")
            reasons.append("Spring / No-Supply structural event implies test near liquidity pool or range floor.")
            evidence_quality = "INFERRED_FROM_CLASSICAL_EVENT"

        if any(name in archetypes for name in TR_FLOOR_ARCHETYPES):
            locations.append("TR_FLOOR_INFERRED")
            reasons.append("Climactic stopping or re-accumulation absorption implies structural floor interaction.")
            evidence_quality = "INFERRED_FROM_CLASSICAL_EVENT"

        if any(bool(raw_flags.get(flag)) for flag in HVN_PROXY_FLAGS):
            locations.append("HVN_ABSORPTION_PROXY")
            reasons.append("High-volume controlled spread acts as a shadow proxy for volume-node absorption.")
            evidence_quality = "INFERRED_FROM_ABSORPTION_EVENT"

    # Deduplicate while preserving order.
    deduped_locations: List[str] = []
    for item in locations:
        if item not in deduped_locations:
            deduped_locations.append(item)

    return {
        "sml_present": bool(deduped_locations),
        "sml_locations": deduped_locations,
        "sml_evidence_quality": evidence_quality,
        "sml_reason": reasons,
        "explicit_geometry_available": any(
            value is not None for value in [price, tr_floor, tr_ceiling, atr, hvn]
        ),
        "geometry_inputs": {
            "price": price,
            "tr_floor": tr_floor,
            "tr_ceiling": tr_ceiling,
            "atr": atr,
            "hvn": hvn,
        },
    }


def classify_wyckoff_weis_operator_confirmation(
    evidence: Dict[str, Any],
    symbol: str | None = None,
    campaign_state: str | None = None,
) -> Dict[str, Any]:
    evidence = _as_dict(evidence)

    footprints = _as_dict(evidence.get("early_operator_footprints"))
    operator_control = _as_dict(evidence.get("operator_control"))

    raw_flags = _as_dict(footprints.get("raw_operator_flags"))
    vsa_weis = _as_dict(footprints.get("vsa_weis_inputs"))

    footprint_present = bool(footprints.get("footprint_present"))
    footprint_count = int(footprints.get("footprint_count") or 0)
    archetypes = _footprint_archetype_names(footprints)

    operator_control_confirmed_current = bool(operator_control.get("operator_control_confirmed"))

    supply_flags = _true_flags(raw_flags, SUPPLY_EXHAUSTION_FLAGS)
    supply_flags += _true_flags(vsa_weis, SUPPLY_EXHAUSTION_FLAGS)
    supply_flags = list(dict.fromkeys(supply_flags))

    demand_flags = _true_flags(raw_flags, DEMAND_SUPPORT_FLAGS)
    demand_flags += _true_flags(vsa_weis, DEMAND_SUPPORT_FLAGS)
    demand_flags = list(dict.fromkeys(demand_flags))

    contrary_flags = _true_flags(raw_flags, CONTRARY_FAILURE_FLAGS)
    contrary_flags += _true_flags(vsa_weis, CONTRARY_FAILURE_FLAGS)
    contrary_flags = list(dict.fromkeys(contrary_flags))

    risk_context = [str(x) for x in _as_list(footprints.get("risk_context"))]
    contrary_risk_hits = [x for x in risk_context if x in CONTRARY_RISK_CONTEXT]

    contrary_failure_present = bool(contrary_flags or contrary_risk_hits)

    sml = _detect_structurally_meaningful_location(
        evidence=evidence,
        footprints=footprints,
        raw_flags=raw_flags,
        vsa_weis=vsa_weis,
    )

    supply_exhaustion_validated = bool(supply_flags)
    demand_support_validated = bool(demand_flags)

    doctrine_confirmable = (
        footprint_present
        and sml.get("sml_present") is True
        and supply_exhaustion_validated
        and demand_support_validated
        and not contrary_failure_present
    )

    block_reasons: List[str] = []

    if not footprint_present:
        block_reasons.append("No early Composite Operator footprint is present.")

    if not sml.get("sml_present"):
        block_reasons.append("No structurally meaningful location is confirmed or inferable from the current evidence.")

    if not supply_exhaustion_validated:
        block_reasons.append("Supply exhaustion is not validated.")

    if not demand_support_validated:
        block_reasons.append("Active demand/support validation is not present.")

    if contrary_failure_present:
        block_reasons.append("Contrary failure evidence blocks confirmation.")

    if doctrine_confirmable:
        doctrine_verdict = "DOCTRINE_CONFIRMABLE_SHADOW"
        doctrine_reason = (
            "Composite Operator control is shadow-confirmable because supply exhaustion, "
            "active demand/support validation, structurally meaningful location, and absence "
            "of contrary failure are all present."
        )
    else:
        doctrine_verdict = "DOCTRINE_NOT_CONFIRMABLE"
        doctrine_reason = " ".join(block_reasons)

    if operator_control_confirmed_current:
        existing_control_context = "ALREADY_CONFIRMED_BY_EXISTING_OPERATOR_CONTROL_ENGINE"
    elif doctrine_confirmable:
        existing_control_context = "SHADOW_CONFIRMABLE_BUT_EXISTING_ENGINE_UNCONFIRMED"
    else:
        existing_control_context = "UNCONFIRMED_AND_NOT_SHADOW_CONFIRMABLE"

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_state": campaign_state,
        "diagnostic_only": True,
        "read_only": True,
        "shadow_production": True,
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

        "doctrine_confirmable": doctrine_confirmable,
        "doctrine_verdict": doctrine_verdict,
        "doctrine_reason": doctrine_reason,
        "existing_control_context": existing_control_context,

        "footprint_present": footprint_present,
        "footprint_count": footprint_count,
        "footprint_archetypes": archetypes,
        "operator_control_confirmed_current": operator_control_confirmed_current,

        "sml_present": bool(sml.get("sml_present")),
        "sml_locations": sml.get("sml_locations") or [],
        "sml_evidence_quality": sml.get("sml_evidence_quality"),
        "sml_reason": sml.get("sml_reason") or [],
        "explicit_geometry_available": bool(sml.get("explicit_geometry_available")),
        "geometry_inputs": sml.get("geometry_inputs") or {},

        "supply_exhaustion_validated": supply_exhaustion_validated,
        "supply_exhaustion_flags_present": supply_flags,

        "demand_support_validated": demand_support_validated,
        "demand_support_flags_present": demand_flags,

        "contrary_failure_present": contrary_failure_present,
        "contrary_failure_flags_present": contrary_flags,
        "contrary_risk_context_present": contrary_risk_hits,

        "block_reasons": block_reasons,

        "doctrine_rule": (
            "Composite Operator Control = Tested Supply Exhaustion "
            "AND Active Demand/Support Validation "
            "AND Structurally Meaningful Location "
            "AND NOT Contrary Failure"
        ),

        "source_sections": [
            "early_operator_footprints",
            "early_operator_footprints.raw_operator_flags",
            "early_operator_footprints.vsa_weis_inputs",
            "operator_control",
        ],
    }
