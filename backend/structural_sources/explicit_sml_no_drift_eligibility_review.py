from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.structural_sources.explicit_sml_source_binding_review import (
    run_d3d_dry_run_source_binding_review,
)


REVIEW_NAME = "SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW"
REVIEW_VERSION = "source_resolution_src7f_no_drift_dry_run_eligibility_review_v1"

NO_DRIFT_DOCTRINE = [
    "Operator control is evidence, not a score.",
    "Operator control SHALL NOT be derived from composite score, campaign score, survival score, rank, tier, gamma/options overlay, probability, edge, expected return, historical outcomes, target projections, future returns, or trade signals.",
    "D3D is the only production mutation gate.",
    "D3A = candidate only.",
    "D3C = shadow/read-only.",
    "D3D = production mutation only.",
    "D3C.2 layers are read-only diagnostic/enrichment and cannot confirm operator control.",
    "HVN_ABSORPTION_PROXY is not true HVN/POC.",
    "Explicit SML/structural location is required for future D3D eligibility.",
    "Inferred SML must be rejected by D3U/D3V/D3Z for D3D preflight eligibility.",
    "Read-only endpoints must never mutate, score, rank, transition, confirm/unconfirm operator control, or produce trade signals.",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _upper(value: Any) -> str:
    return _string(value).upper()


def _candidate_symbol(candidate: dict[str, Any]) -> str:
    return _upper(
        candidate.get("symbol")
        or candidate.get("ticker")
        or candidate.get("asset")
    )


def _candidate_id(candidate: dict[str, Any]) -> str:
    return _string(
        candidate.get("campaign_id")
        or candidate.get("id")
        or candidate.get("candidate_id")
    )


def _doctrine_guardrail_failures(binding_result: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_review",
        "operator_control_unconfirmed_by_this_review",
        "d3d_execution_authorized",
        "production_mutation_authorized",
        "operator_control_confirmed",
        "src7e_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if binding_result.get(field) is not False:
            failures.append(
                {
                    "field": field,
                    "expected": False,
                    "actual": binding_result.get(field),
                }
            )

    if binding_result.get("dry_run") is not True:
        failures.append(
            {
                "field": "dry_run",
                "expected": True,
                "actual": binding_result.get("dry_run"),
            }
        )

    if binding_result.get("read_only") is not True:
        failures.append(
            {
                "field": "read_only",
                "expected": True,
                "actual": binding_result.get("read_only"),
            }
        )

    if binding_result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": binding_result.get("not_a_trade_signal"),
            }
        )

    if binding_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": binding_result.get("d3d_execution_recommendation"),
            }
        )

    return failures


def run_no_drift_dry_run_eligibility_review(
    candidate: dict[str, Any],
    candidate_payload: dict[str, Any] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {
            "review": REVIEW_NAME,
            "review_version": REVIEW_VERSION,
            "review_timestamp_utc": _utc_now(),
            "diagnostic_only": True,
            "dry_run": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed_by_this_review": False,
            "operator_control_unconfirmed_by_this_review": False,
            "not_a_trade_signal": True,
            "source_binding_requirement_satisfied": False,
            "no_drift_requirement_satisfied": False,
            "source_only_dry_run_eligibility_satisfied": False,
            "production_d3d_eligibility_satisfied": False,
            "d3d_execution_authorized": False,
            "production_mutation_authorized": False,
            "operator_control_confirmed": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7f_makes_any_campaign_d3d_eligible": False,
            "guardrail_failure_count": 1,
            "guardrail_failures": [
                {
                    "field": "candidate",
                    "expected": "dict",
                    "actual": type(candidate).__name__,
                }
            ],
        }

    symbol = _candidate_symbol(candidate)
    campaign_id = _candidate_id(candidate)

    binding_result = run_d3d_dry_run_source_binding_review(
        candidate=candidate,
        candidate_payload=candidate_payload,
        json_file_path=json_file_path,
        source_priority_policy=source_priority_policy,
    )

    doctrine_failures = _doctrine_guardrail_failures(binding_result)
    source_binding_satisfied = binding_result.get("source_binding_requirement_satisfied") is True
    no_drift_satisfied = len(doctrine_failures) == 0

    source_only_dry_run_eligibility_satisfied = source_binding_satisfied and no_drift_satisfied

    if source_only_dry_run_eligibility_satisfied:
        eligibility_status = "PASS_SRC7F_NO_DRIFT_DRY_RUN_SOURCE_ELIGIBILITY_SOURCE_ONLY"
        next_action = "PROCEED_TO_SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT"
        reason = (
            "SRC7F confirmed source binding plus no-drift requirements in dry-run mode. "
            "This is source-only dry-run readiness. It does not confirm operator control, does not mutate campaigns, and does not authorize D3D."
        )
    else:
        eligibility_status = "HOLD_SRC7F_NO_DRIFT_DRY_RUN_SOURCE_ELIGIBILITY_NOT_SATISFIED"
        next_action = "REPAIR_SOURCE_BINDING_OR_NO_DRIFT_FAILURES"
        reason = (
            "SRC7F did not confirm both source binding and no-drift dry-run requirements. D3D remains blocked."
        )

    return {
        "review": REVIEW_NAME,
        "review_version": REVIEW_VERSION,
        "review_timestamp_utc": _utc_now(),
        "diagnostic_only": True,
        "dry_run": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_review": False,
        "operator_control_unconfirmed_by_this_review": False,
        "not_a_trade_signal": True,
        "candidate": {
            "symbol": symbol,
            "campaign_id": campaign_id,
        },
        "binding_result": binding_result,
        "source_binding_requirement_satisfied": source_binding_satisfied,
        "no_drift_requirement_satisfied": no_drift_satisfied,
        "source_only_dry_run_eligibility_satisfied": source_only_dry_run_eligibility_satisfied,
        "production_d3d_eligibility_satisfied": False,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7f_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": len(doctrine_failures),
        "guardrail_failures": doctrine_failures,
        "runtime_decision": {
            "src7f_status": eligibility_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7f_makes_any_campaign_d3d_eligible": False,
            "reason": reason,
        },
    }


def run_many_no_drift_dry_run_eligibility_reviews(
    candidates: list[dict[str, Any]],
    candidate_payload_by_symbol: dict[str, dict[str, Any]] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    candidate_payload_by_symbol = candidate_payload_by_symbol or {}
    results = []

    for candidate in candidates:
        if isinstance(candidate, dict):
            symbol = _candidate_symbol(candidate)
        else:
            symbol = ""

        result = run_no_drift_dry_run_eligibility_review(
            candidate=candidate,
            candidate_payload=candidate_payload_by_symbol.get(symbol, {}),
            json_file_path=json_file_path,
            source_priority_policy=source_priority_policy,
        )
        results.append(result)

    source_only_pass_count = sum(
        1 for item in results
        if item.get("source_only_dry_run_eligibility_satisfied") is True
    )

    production_eligible_count = sum(
        1 for item in results
        if item.get("production_d3d_eligibility_satisfied") is True
    )

    doctrine_failure_count = sum(
        int(item.get("guardrail_failure_count") or 0)
        for item in results
    )

    return {
        "review": REVIEW_NAME,
        "review_version": REVIEW_VERSION,
        "review_timestamp_utc": _utc_now(),
        "diagnostic_only": True,
        "dry_run": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_review": False,
        "operator_control_unconfirmed_by_this_review": False,
        "not_a_trade_signal": True,
        "candidate_count_attempted": len(results),
        "candidate_count_source_only_dry_run_eligibility_satisfied": source_only_pass_count,
        "candidate_count_source_only_dry_run_eligibility_not_satisfied": len(results) - source_only_pass_count,
        "candidate_count_production_d3d_eligible": production_eligible_count,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7f_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": doctrine_failure_count,
        "results": results,
        "runtime_decision": {
            "src7f_status": (
                "PASS_SRC7F_NO_DRIFT_DRY_RUN_SOURCE_ELIGIBILITY_SOURCE_ONLY"
                if source_only_pass_count > 0 and doctrine_failure_count == 0
                else "HOLD_SRC7F_NO_DRIFT_DRY_RUN_SOURCE_ELIGIBILITY_NOT_SATISFIED"
            ),
            "next_action": (
                "PROCEED_TO_SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT"
                if source_only_pass_count > 0 and doctrine_failure_count == 0
                else "REPAIR_SOURCE_BINDING_OR_NO_DRIFT_FAILURES"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7f_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7F reviews source-only dry-run readiness under no-drift doctrine. "
                "It does not mutate, confirm operator control, or authorize D3D."
            ),
        },
    }
