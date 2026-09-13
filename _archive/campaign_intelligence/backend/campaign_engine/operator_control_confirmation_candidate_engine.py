
"""
D3A Composite Operator Confirmation Candidate Engine.

Diagnostic-only candidate classifier.

This engine does NOT confirm operator control.
This engine does NOT change scores, ranks, states, transitions, or saved campaign data.
It only identifies campaigns that appear to qualify for future confirmation review
based on early operator footprints plus hard confirmation mechanisms.
"""

from typing import Any, Dict, List


ENGINE_NAME = "OPERATOR_CONTROL_CONFIRMATION_CANDIDATE"
ENGINE_VERSION = "phase_d3a_diagnostic_only_v1"


HARD_CONFIRMATION_FLAG_NAMES = [
    "survives_adverse_tests",
    "recapture_after_breakdown",
    "demand_efficiency_dominates_supply",
    "shortening_downside_thrust",
    "high_volume_controlled_spread",
    "absorption_against_resistance",
    "supply_failure",
]

VSA_WEIS_CONFIRMATION_NAMES = [
    "effort_vs_result_divergence",
    "no_supply_test",
]

CAUTION_FLAG_NAMES = [
    "no_demand_test",
    "upthrust_supply",
    "buying_climax",
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


def _true_flags(payload: Dict[str, Any], names: List[str]) -> List[str]:
    payload = _as_dict(payload)
    return [name for name in names if bool(payload.get(name))]


def classify_operator_control_confirmation_candidate(
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
    operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))

    hard_flags_present = _true_flags(raw_flags, HARD_CONFIRMATION_FLAG_NAMES)
    vsa_weis_confirmation_flags_present = _true_flags(vsa_weis, VSA_WEIS_CONFIRMATION_NAMES)
    caution_flags_present = _true_flags(vsa_weis, CAUTION_FLAG_NAMES)

    hard_confirmation_count = len(hard_flags_present) + len(vsa_weis_confirmation_flags_present)
    caution_count = len(caution_flags_present)

    archetypes = []
    for item in footprints.get("footprint_archetypes") or []:
        d = _as_dict(item)
        name = d.get("archetype")
        if name:
            archetypes.append(name)

    confirmation_candidate = False

    if operator_control_confirmed:
        verdict = "LEGACY_OPERATOR_CONTROL_EVIDENCE_ALREADY_PRESENT"
        reason = "Legacy operator-control evidence is already present from raw tape behavior, but this is not D3D production-confirmed operator control."
    elif not footprint_present:
        verdict = "NO_OPERATOR_FOOTPRINT"
        reason = "No early operator footprint is present."
    elif footprint_count >= 4 and hard_confirmation_count >= 1 and caution_count == 0:
        confirmation_candidate = True
        verdict = "D3A_CONFIRMATION_CANDIDATE"
        reason = "Dense early operator footprint plus at least one hard confirmation mechanism and no caution block."
    elif footprint_count >= 4 and hard_confirmation_count >= 1 and caution_count > 0:
        verdict = "D3A_CANDIDATE_BLOCKED_BY_CAUTION"
        reason = "Dense footprint plus hard confirmation exists, but caution evidence blocks clean candidate status."
    elif footprint_count >= 4 and hard_confirmation_count == 0:
        verdict = "D3A_DENSE_FOOTPRINT_MISSING_HARD_CONFIRMATION"
        reason = "Dense early operator footprint exists, but no hard confirmation mechanism is visible."
    else:
        verdict = "D3A_EARLY_FOOTPRINT_ONLY"
        reason = "Early operator footprint exists, but density and/or hard confirmation is insufficient."

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_state": campaign_state,
        "diagnostic_only": True,
        "read_only": True,
        "confirmation_candidate": confirmation_candidate,
        "candidate_verdict": verdict,
        "candidate_reason": reason,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,
        "footprint_present": footprint_present,
        "footprint_count": footprint_count,
        "footprint_archetypes": archetypes,
        "operator_control_confirmed_current": operator_control_confirmed,
        "hard_confirmation_flags_present": hard_flags_present,
        "vsa_weis_confirmation_flags_present": vsa_weis_confirmation_flags_present,
        "caution_flags_present": caution_flags_present,
        "hard_confirmation_count": hard_confirmation_count,
        "caution_count": caution_count,
        "candidate_rule": "footprint_count >= 4 AND hard_confirmation_count >= 1 AND caution_count == 0 AND operator_control_confirmed_current == false",
        "risk_context": footprints.get("risk_context") or [],
        "source_sections": [
            "early_operator_footprints",
            "early_operator_footprints.raw_operator_flags",
            "early_operator_footprints.vsa_weis_inputs",
            "operator_control",
        ],
    }
