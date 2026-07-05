"""
D3J Operator-Control Plausibility Status Engine.

Read-only no-drift diagnostic layer.

Purpose:
Identify operator-control plausibility tiers without mutating production
operator-control confirmation.

This engine separates:
- D3D production-confirmed control
- legacy operator-control evidence
- shadow-confirmable plausible stealth control
- non-confirmable campaigns

This engine does NOT:
- write to Supabase
- mutate campaigns
- confirm operator control
- unconfirm operator control
- change score/rank/state/transition
- execute D3D
"""

from __future__ import annotations

from typing import Any, Dict, List


ENGINE_NAME = "D3J_OPERATOR_CONTROL_PLAUSIBILITY_STATUS"
ENGINE_VERSION = "phase_d3j_operator_control_plausibility_status_v1"


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


def classify_operator_control_plausibility(
    campaign: Dict[str, Any],
    d3d_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    c = _as_dict(campaign)
    evidence = _as_dict(_get(c, "evidence", {}))
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

    legacy_confirmed = bool(operator_control.get("operator_control_confirmed"))
    d3d_eligible = bool(d3d_candidate.get("eligible_for_d3d_mutation"))
    doctrine_verdict = d3d_candidate.get("d3c_shadow_doctrine_verdict")
    shadow_confirmable = bool(doctrine_verdict == "DOCTRINE_CONFIRMABLE_SHADOW")

    sml_quality = d3d_candidate.get("d3c_shadow_sml_evidence_quality")
    explicit_geometry_sml = bool(d3d_candidate.get("d3c_shadow_explicit_geometry_sml"))

    production_engine = operator_control.get("production_confirmation_engine")
    production_engine_version = operator_control.get("production_confirmation_engine_version")

    d3d_production_confirmed = bool(
        legacy_confirmed
        and production_engine == "D3D_OPERATOR_CONTROL_PRODUCTION_MUTATION_GATE"
        and production_engine_version
    )

    if d3d_production_confirmed:
        plausibility_status = "D3D_PRODUCTION_CONFIRMED_OPERATOR_CONTROL"
    elif legacy_confirmed and shadow_confirmable:
        plausibility_status = "LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE"
    elif legacy_confirmed and not shadow_confirmable:
        plausibility_status = "LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE"
    elif shadow_confirmable and not legacy_confirmed:
        plausibility_status = "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED"
    else:
        plausibility_status = "NOT_SHADOW_CONFIRMABLE"

    no_drift_status = "PASS"

    drift_findings: List[str] = []

    if plausibility_status == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED":
        drift_findings.append(
            "Plausible stealth/operator-control evidence exists, but production confirmation is not authorized."
        )

    if plausibility_status.startswith("LEGACY_OPERATOR_CONTROL"):
        drift_findings.append(
            "Legacy operator-control evidence is preserved as evidence, not treated as D3D production confirmation."
        )

    if d3d_eligible:
        drift_findings.append(
            "D3D candidate eligibility exists only as dry-run review unless explicit execution is separately authorized."
        )

    if not shadow_confirmable and not legacy_confirmed:
        drift_findings.append("No current shadow-confirmable operator-control plausibility.")

    if legacy_confirmed and not production_engine:
        drift_findings.append("Legacy confirmation lacks D3D production confirmation provenance.")

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
        "operator_control_unconfirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "d3d_execution_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "plausibility_status": plausibility_status,
        "no_drift_status": no_drift_status,
        "drift_findings": drift_findings,

        "legacy_operator_control_confirmed": legacy_confirmed,
        "d3d_production_confirmed": d3d_production_confirmed,
        "shadow_confirmable": shadow_confirmable,
        "d3d_eligible_dry_run_only": d3d_eligible,

        "d3c_shadow_doctrine_verdict": doctrine_verdict,
        "d3c_shadow_sml_evidence_quality": sml_quality,
        "d3c_shadow_explicit_geometry_sml": explicit_geometry_sml,
        "d3c_shadow_supply_exhaustion_validated": d3d_candidate.get("d3c_shadow_supply_exhaustion_validated"),
        "d3c_shadow_demand_support_validated": d3d_candidate.get("d3c_shadow_demand_support_validated"),
        "d3c_shadow_contrary_failure_present": d3d_candidate.get("d3c_shadow_contrary_failure_present"),
        "d3d_block_reasons": d3d_candidate.get("block_reasons") or [],

        "operator_control_verdict": operator_control.get("verdict"),
        "operator_control_status": operator_control.get("status"),
        "operator_control_method_basis": operator_control.get("method_basis"),
        "operator_control_evidence_count": operator_control.get("evidence_count"),
        "operator_control_engine": operator_control.get("engine"),
        "operator_control_engine_version": operator_control.get("engine_version"),
        "production_confirmation_engine": production_engine,
        "production_confirmation_engine_version": production_engine_version,
        "not_derived_from_scores": operator_control.get("not_derived_from_scores"),
        "not_derived_from_gamma": operator_control.get("not_derived_from_gamma"),
    }
