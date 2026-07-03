from __future__ import annotations

from typing import Any, Dict, List


ENGINE = "EARLY_OPERATOR_FOOTPRINTS_DIAGNOSTIC"
VERSION = "phase_d2_5_diagnostic_only_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _flag(value: Any) -> bool:
    return bool(value) is True


def _add(archetypes: List[Dict[str, Any]], name: str, reason: str, refs: List[str]) -> None:
    archetypes.append({
        "archetype": name,
        "reason": reason,
        "evidence_references": refs,
    })


def classify_early_operator_footprints(evidence: Dict[str, Any], symbol: str | None = None) -> Dict[str, Any]:
    """
    Diagnostic-only exposure of early Composite Operator footprints.

    This does not confirm operator control.
    This does not change scores, ranks, campaign state, or transition readiness.
    This exists only to expose whether early Wyckoff / Weis / VSA operator-footprint
    evidence is present by archetype.
    """
    ev = _safe_dict(evidence)

    operator_control = _safe_dict(ev.get("operator_control"))
    oc_flags = _safe_dict(operator_control.get("evidence_flags"))

    wyckoff = _safe_dict(ev.get("wyckoff_doctrine"))
    wyckoff_verdict = _safe_dict(wyckoff.get("verdict"))
    wyckoff_survival = _safe_dict(wyckoff.get("survival"))

    vsa = _safe_dict(ev.get("vsa_weis_overlay"))
    vsa_evidence = _safe_dict(vsa.get("evidence"))

    # Raw operator-control tape flags already produced by the isolated operator engine.
    supply_failure = _flag(oc_flags.get("supply_failure"))
    survives_adverse_tests = _flag(oc_flags.get("survives_adverse_tests"))
    higher_lows_after_tests = _flag(oc_flags.get("higher_lows_after_tests"))
    recapture_after_breakdown = _flag(oc_flags.get("recapture_after_breakdown"))
    shortening_downside_thrust = _flag(oc_flags.get("shortening_downside_thrust"))
    absorption_against_resistance = _flag(oc_flags.get("absorption_against_resistance"))
    high_volume_controlled_spread = _flag(oc_flags.get("high_volume_controlled_spread"))
    demand_efficiency_dominates_supply = _flag(oc_flags.get("demand_efficiency_dominates_supply"))

    # Wyckoff diagnostic fields. These remain diagnostic context only.
    phase = wyckoff.get("phase") or wyckoff_verdict.get("phase") or "UNKNOWN"
    stopping_climax_score = _num(wyckoff_verdict.get("stopping_climax_score"))
    supply_absorption_score = _num(wyckoff_verdict.get("supply_absorption_score"))
    spring_score = _num(wyckoff_verdict.get("spring_score"))
    sign_of_strength_score = _num(wyckoff_verdict.get("sign_of_strength_score"))
    behavioral_resolution_score = _num(wyckoff_verdict.get("behavioral_resolution_score"))
    progress_against_resistance = _num(wyckoff_verdict.get("progress_against_resistance"))

    lps_quality_score = _num(wyckoff_survival.get("lps_quality_score"))
    sos_persistence_score = _num(wyckoff_survival.get("sos_persistence_score"))
    absorption_continuation_score = _num(wyckoff_survival.get("absorption_continuation_score"))
    survival_state = wyckoff_survival.get("survival_state") or "UNKNOWN"

    # VSA / Weis overlay flags.
    buying_climax = _flag(vsa_evidence.get("buying_climax"))
    no_supply_test = _flag(vsa_evidence.get("no_supply_test"))
    no_demand_test = _flag(vsa_evidence.get("no_demand_test"))
    upthrust_supply = _flag(vsa_evidence.get("upthrust_supply"))
    effort_vs_result_divergence = _flag(vsa_evidence.get("effort_vs_result_divergence"))

    archetypes: List[Dict[str, Any]] = []

    if (
        stopping_climax_score >= 60
        or buying_climax
        or high_volume_controlled_spread
    ):
        _add(
            archetypes,
            "CLIMACTIC_STOPPING",
            "Stopping or climactic behavior is visible through controlled spread, climax evidence, or high-volume stopping diagnostics.",
            [
                "wyckoff_doctrine.verdict.stopping_climax_score",
                "operator_control.evidence_flags.high_volume_controlled_spread",
                "vsa_weis_overlay.evidence.buying_climax",
            ],
        )

    if (
        phase == "PHASE_B_CAUSE_BUILDING"
        and supply_absorption_score >= 70
        and (
            absorption_continuation_score >= 60
            or lps_quality_score >= 60
            or absorption_against_resistance
            or higher_lows_after_tests
        )
    ):
        _add(
            archetypes,
            "REACCUMULATION_ABSORPTION",
            "Phase-B cause building with meaningful supply absorption and continued structural support.",
            [
                "wyckoff_doctrine.phase",
                "wyckoff_doctrine.verdict.supply_absorption_score",
                "wyckoff_doctrine.survival.absorption_continuation_score",
                "wyckoff_doctrine.survival.lps_quality_score",
                "operator_control.evidence_flags.absorption_against_resistance",
                "operator_control.evidence_flags.higher_lows_after_tests",
            ],
        )

    if (
        absorption_continuation_score >= 70
        and (
            higher_lows_after_tests
            or demand_efficiency_dominates_supply
            or no_supply_test
            or supply_absorption_score >= 70
        )
        and stopping_climax_score < 60
    ):
        _add(
            archetypes,
            "STEALTH_EXHAUSTION",
            "Supply appears to be drying up without a dramatic climax; absorption continues while downside pressure loses effectiveness.",
            [
                "wyckoff_doctrine.survival.absorption_continuation_score",
                "operator_control.evidence_flags.higher_lows_after_tests",
                "operator_control.evidence_flags.demand_efficiency_dominates_supply",
                "vsa_weis_overlay.evidence.no_supply_test",
                "wyckoff_doctrine.verdict.supply_absorption_score",
            ],
        )

    if (
        behavioral_resolution_score >= 70
        or sign_of_strength_score >= 60
        or recapture_after_breakdown
    ):
        _add(
            archetypes,
            "CHANGE_OF_BEHAVIOR",
            "Behavior has shifted away from prior markdown behavior through resolution, sign of strength, or recapture after breakdown.",
            [
                "wyckoff_doctrine.verdict.behavioral_resolution_score",
                "wyckoff_doctrine.verdict.sign_of_strength_score",
                "operator_control.evidence_flags.recapture_after_breakdown",
            ],
        )

    if (
        shortening_downside_thrust
        or effort_vs_result_divergence
    ):
        _add(
            archetypes,
            "WEIS_SHORTENING_THRUST",
            "Downside result is shortening relative to effort, consistent with Weis shortening-of-thrust / effort-vs-result evidence.",
            [
                "operator_control.evidence_flags.shortening_downside_thrust",
                "vsa_weis_overlay.evidence.effort_vs_result_divergence",
            ],
        )

    if (
        spring_score >= 60
        or (
            no_supply_test
            and recapture_after_breakdown
        )
    ):
        _add(
            archetypes,
            "SPRING_TEST",
            "Spring or shakeout-test behavior is present through spring diagnostics or no-supply recovery behavior.",
            [
                "wyckoff_doctrine.verdict.spring_score",
                "vsa_weis_overlay.evidence.no_supply_test",
                "operator_control.evidence_flags.recapture_after_breakdown",
            ],
        )

    if no_supply_test:
        _add(
            archetypes,
            "NO_SUPPLY_TEST",
            "VSA no-supply evidence suggests selling pressure is absent or exhausted.",
            [
                "vsa_weis_overlay.evidence.no_supply_test",
            ],
        )

    if (
        high_volume_controlled_spread
        or effort_vs_result_divergence
        or demand_efficiency_dominates_supply
        or supply_failure
    ):
        _add(
            archetypes,
            "EFFORT_RESULT_FAILURE",
            "Effort is failing to produce proportional downside result, or demand efficiency dominates supply.",
            [
                "operator_control.evidence_flags.high_volume_controlled_spread",
                "vsa_weis_overlay.evidence.effort_vs_result_divergence",
                "operator_control.evidence_flags.demand_efficiency_dominates_supply",
                "operator_control.evidence_flags.supply_failure",
            ],
        )

    risk_context: List[str] = []
    if no_demand_test:
        risk_context.append("VSA_NO_DEMAND_CAUTION")
    if upthrust_supply:
        risk_context.append("UPTHRUST_SUPPLY_CAUTION")
    if survival_state in {"AT_RISK", "FAILURE_RISK"}:
        risk_context.append("WYCKOFF_SURVIVAL_AT_RISK")

    return {
        "engine": ENGINE,
        "version": VERSION,
        "symbol": symbol,
        "status": "OK",
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "operator_control_confirmation_impact": "NONE",
        "operator_control_confirmed_by_this_engine": False,
        "not_derived_from_gamma": True,
        "not_a_trade_signal": True,
        "method_basis": "RAW_TAPE_OPERATOR_FLAGS_PLUS_DIAGNOSTIC_WYCKOFF_VSA_WEIS_EVIDENCE",
        "footprint_present": len(archetypes) > 0,
        "footprint_count": len(archetypes),
        "footprint_archetypes": archetypes,
        "risk_context": risk_context,
        "raw_operator_flags": {
            "supply_failure": supply_failure,
            "survives_adverse_tests": survives_adverse_tests,
            "higher_lows_after_tests": higher_lows_after_tests,
            "recapture_after_breakdown": recapture_after_breakdown,
            "shortening_downside_thrust": shortening_downside_thrust,
            "absorption_against_resistance": absorption_against_resistance,
            "high_volume_controlled_spread": high_volume_controlled_spread,
            "demand_efficiency_dominates_supply": demand_efficiency_dominates_supply,
        },
        "wyckoff_inputs": {
            "phase": phase,
            "stopping_climax_score": stopping_climax_score,
            "supply_absorption_score": supply_absorption_score,
            "spring_score": spring_score,
            "sign_of_strength_score": sign_of_strength_score,
            "behavioral_resolution_score": behavioral_resolution_score,
            "progress_against_resistance": progress_against_resistance,
            "lps_quality_score": lps_quality_score,
            "sos_persistence_score": sos_persistence_score,
            "absorption_continuation_score": absorption_continuation_score,
            "survival_state": survival_state,
        },
        "vsa_weis_inputs": {
            "buying_climax": buying_climax,
            "no_supply_test": no_supply_test,
            "no_demand_test": no_demand_test,
            "upthrust_supply": upthrust_supply,
            "effort_vs_result_divergence": effort_vs_result_divergence,
        },
        "source_sections": [
            "operator_control",
            "wyckoff_doctrine",
            "vsa_weis_overlay",
        ],
    }


__all__ = ["classify_early_operator_footprints"]
