"""
D3D Operator Control Production Mutation Gate.
This is the first controlled production mutation layer after:
- D3C.2A structural-location evidence enrichment
- D3C.3 structural-location validation
- D3C shadow Wyckoff / Weis operator-confirmation review
Doctrine:
Operator control is evidence, not a score.
This engine may confirm operator control only when validated evidence exists.
It must not derive confirmation from composite score, survival score, campaign rank,
gamma, options overlay, probability score, edge score, expected return, historical
outcome, price target, or future return.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
ENGINE_NAME = "D3D_OPERATOR_CONTROL_PRODUCTION_MUTATION_GATE"
ENGINE_VERSION = "phase_d3d_operator_control_production_mutation_gate_v1"
CONFIRM_PHRASE = "D3D_OPERATOR_CONTROL_PRODUCTION_MUTATION_APPROVED"
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
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
def _d3c1_proxy_from_structural_location(structural_location: Dict[str, Any]) -> Dict[str, Any]:
    required = [
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
    ]
    production_ready = bool(
        structural_location
        and all(structural_location.get(name) is not None for name in required)
    )
    return {
        "structural_location_readiness": (
            "EXPLICIT_LOCATION_READY" if production_ready else "MISSING_CORE_LOCATION_INPUTS"
        ),
        "production_sml_possible_now": production_ready,
        "explicit_trading_range_ready": production_ready,
        "explicit_lp_zone_ready": production_ready,
        "explicit_support_resistance_ready": production_ready,
    }
def _run_d3c3_validation(evidence: Dict[str, Any], symbol: str | None, campaign_state: str | None) -> Dict[str, Any]:
    structural_location = _as_dict(evidence.get("structural_location"))
    d3c1_proxy = _d3c1_proxy_from_structural_location(structural_location)
    try:
        from backend.campaign_engine.structural_location_validation_engine import validate_structural_location
    except Exception:
        from campaign_engine.structural_location_validation_engine import validate_structural_location
    try:
        return validate_structural_location(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
            d3c1_review=d3c1_proxy,
        )
    except TypeError:
        return validate_structural_location(evidence, symbol, campaign_state, d3c1_proxy)
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
def evaluate_d3d_operator_control_candidate(campaign: Dict[str, Any]) -> Dict[str, Any]:
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
    timeframe = _get(c, "timeframe") or evidence.get("timeframe") or "DAILY"
    already_confirmed = bool(operator_control.get("operator_control_confirmed"))
    d3c3 = _run_d3c3_validation(evidence, symbol, campaign_state)
    shadow = _run_d3c_shadow_review(evidence, symbol, campaign_state)
    d3c3_passed = bool(
        d3c3.get("structural_location_validation_passed") is True
        and d3c3.get("production_sml_validation_passed") is True
        and d3c3.get("validation_status") == "STRUCTURAL_LOCATION_VALIDATED"
    )
    shadow_guardrail_ok = bool(
        shadow.get("diagnostic_only") is True
        and shadow.get("read_only") is True
        and shadow.get("shadow_production") is True
        and shadow.get("writes_to_supabase") is False
        and shadow.get("mutates_campaigns") is False
        and shadow.get("production_confirmation_allowed") is False
        and shadow.get("operator_control_confirmed_by_this_engine") is False
        and shadow.get("operator_control_confirmation_impact") == "NONE"
        and shadow.get("score_impact") == "NONE"
        and shadow.get("rank_impact") == "NONE"
        and shadow.get("state_impact") == "NONE"
        and shadow.get("transition_impact") == "NONE"
        and shadow.get("state_transition_enabled") is False
        and shadow.get("not_a_trade_signal") is True
    )
    shadow_confirmable = bool(shadow.get("doctrine_confirmable") is True)
    explicit_geometry_sml = bool(shadow.get("sml_evidence_quality") == "EXPLICIT_GEOMETRY")
    block_reasons: List[str] = []
    if already_confirmed:
        block_reasons.append("Operator control is already confirmed in evidence.operator_control.")
    if not d3c3_passed:
        block_reasons.append("D3C.3 structural-location validation has not passed.")
    if not shadow_guardrail_ok:
        block_reasons.append("D3C shadow-confirmation guardrails are not intact.")
    if not shadow_confirmable:
        block_reasons.append("D3C shadow doctrine is not confirmable.")

    if not explicit_geometry_sml:
        block_reasons.append("D3D requires explicit structural-location geometry; inferred SML is not eligible for production mutation.")
    eligible = bool(
        not already_confirmed
        and d3c3_passed
        and shadow_guardrail_ok
        and shadow_confirmable
        and explicit_geometry_sml
    )
    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "campaign_state": campaign_state,
        "timeframe": timeframe,
        "eligible_for_d3d_mutation": eligible,
        "block_reasons": block_reasons,
        "already_confirmed": already_confirmed,
        "d3c3_validation_status": d3c3.get("validation_status"),
        "d3c3_structural_location_validation_passed": d3c3.get("structural_location_validation_passed"),
        "d3c3_production_sml_validation_passed": d3c3.get("production_sml_validation_passed"),
        "d3c_shadow_doctrine_confirmable": shadow.get("doctrine_confirmable"),
        "d3c_shadow_doctrine_verdict": shadow.get("doctrine_verdict"),
        "d3c_shadow_existing_control_context": shadow.get("existing_control_context"),
        "d3c_shadow_sml_present": shadow.get("sml_present"),
        "d3c_shadow_sml_locations": shadow.get("sml_locations") or [],
        "d3c_shadow_sml_evidence_quality": shadow.get("sml_evidence_quality"),
        "d3c_shadow_explicit_geometry_sml": explicit_geometry_sml,
        "d3c_shadow_guardrail_ok": shadow_guardrail_ok,
        "mutation_target": "evidence.operator_control.operator_control_confirmed",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_derived_from_scores": True,
        "not_a_trade_signal": True,
    }
def build_d3d_operator_control_mutation(campaign: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    updated = deepcopy(_as_dict(campaign))
    evidence = deepcopy(_as_dict(updated.get("evidence")))
    operator_control = deepcopy(_as_dict(evidence.get("operator_control")))
    confirmation = {
        "confirmed_at": _utc_now(),
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "basis": (
            "D3C.3 structural-location validation passed and D3C shadow "
            "Wyckoff / Weis doctrine is confirmable."
        ),
        "doctrine_rule": (
            "Composite Operator Control = Tested Supply Exhaustion AND Active "
            "Demand/Support Validation AND Structurally Meaningful Location "
            "AND NOT Contrary Failure."
        ),
        "source_validation": {
            "d3c3_validation_status": candidate.get("d3c3_validation_status"),
            "d3c_shadow_doctrine_verdict": candidate.get("d3c_shadow_doctrine_verdict"),
            "d3c_shadow_sml_evidence_quality": candidate.get("d3c_shadow_sml_evidence_quality"),
            "d3c_shadow_sml_locations": candidate.get("d3c_shadow_sml_locations") or [],
        },
        "negative_controls": {
            "not_derived_from_scores": True,
            "composite_score_used": False,
            "survival_score_used": False,
            "campaign_rank_used": False,
            "gamma_used_as_confirmation": False,
            "options_overlay_used_as_confirmation": False,
            "probability_score_used": False,
            "edge_score_used": False,
            "expected_return_used": False,
            "historical_outcome_used": False,
            "price_target_used": False,
            "future_return_used": False,
        },
    }
    operator_control["operator_control_confirmed"] = True
    operator_control["verdict"] = "OPERATOR_CONTROL_CONFIRMED"
    operator_control["production_confirmation"] = confirmation
    operator_control["production_confirmation_engine"] = ENGINE_NAME
    operator_control["production_confirmation_engine_version"] = ENGINE_VERSION
    operator_control["production_confirmation_at"] = confirmation["confirmed_at"]
    operator_control["production_confirmation_basis"] = confirmation["basis"]
    operator_control["not_derived_from_scores"] = True
    operator_control["score_impact"] = "NONE"
    operator_control["rank_impact"] = "NONE"
    operator_control["state_impact"] = "NONE"
    evidence["operator_control"] = operator_control
    updated["evidence"] = evidence
    mutation_summary = {
        "symbol": candidate.get("symbol"),
        "campaign_id": candidate.get("campaign_id"),
        "timeframe": candidate.get("timeframe"),
        "mutation_target": "evidence.operator_control.operator_control_confirmed",
        "old_value": False,
        "new_value": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
    }
    return updated, mutation_summary
