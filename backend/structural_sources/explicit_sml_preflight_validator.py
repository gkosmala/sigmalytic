from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.structural_sources.explicit_sml_source_adapter import (
    load_explicit_sml_records_read_only,
)


VALIDATOR_NAME = "SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_VALIDATOR"
VALIDATOR_VERSION = "source_resolution_src7d_explicit_sml_source_evidence_preflight_v1"

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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


def _extract_validation_results(adapter_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in _as_list(adapter_result.get("validation_results"))
        if isinstance(item, dict)
    ]


def _extract_valid_records(adapter_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in _extract_validation_results(adapter_result)
        if item.get("record_valid") is True
    ]


def _guardrail_failures(adapter_result: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_adapter",
        "operator_control_unconfirmed_by_this_adapter",
        "src7b_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if adapter_result.get(field) is not False:
            failures.append(
                {
                    "field": field,
                    "expected": False,
                    "actual": adapter_result.get(field),
                }
            )

    if adapter_result.get("read_only") is not True:
        failures.append(
            {
                "field": "read_only",
                "expected": True,
                "actual": adapter_result.get("read_only"),
            }
        )

    if adapter_result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": adapter_result.get("not_a_trade_signal"),
            }
        )

    if adapter_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": adapter_result.get("d3d_execution_recommendation"),
            }
        )

    return failures


def run_explicit_sml_source_evidence_preflight(
    symbol: str,
    candidate_payload: dict[str, Any] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    adapter_result = load_explicit_sml_records_read_only(
        symbol=symbol,
        candidate_payload=candidate_payload,
        json_file_path=json_file_path,
        source_priority_policy=source_priority_policy,
    )

    valid_records = _extract_valid_records(adapter_result)
    failures = _guardrail_failures(adapter_result)

    valid_source_evidence_count = len(valid_records)
    has_valid_source_evidence = valid_source_evidence_count > 0

    if has_valid_source_evidence:
        source_evidence_status = "PASS_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_SOURCE_ONLY"
        next_action = "PROCEED_TO_SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW"
        reason = (
            "SRC7D found explicit SML/structural-location evidence that satisfies the source-evidence contract. "
            "This is source-evidence readiness only. It does not confirm operator control and does not authorize D3D."
        )
    else:
        source_evidence_status = "HOLD_SRC7D_NO_VALID_EXPLICIT_SML_SOURCE_EVIDENCE"
        next_action = "ADD_VALID_EXPLICIT_SML_RUNTIME_SOURCE_OR_STOP"
        reason = (
            "SRC7D did not find valid explicit SML/structural-location evidence. "
            "D3D remains blocked."
        )

    return {
        "validator": VALIDATOR_NAME,
        "validator_version": VALIDATOR_VERSION,
        "validation_timestamp_utc": _utc_now(),
        "symbol": str(symbol or "").strip().upper(),
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_validator": False,
        "operator_control_unconfirmed_by_this_validator": False,
        "not_a_trade_signal": True,
        "adapter_result": adapter_result,
        "valid_source_evidence_count": valid_source_evidence_count,
        "invalid_source_evidence_count": int(adapter_result.get("invalid_record_count") or 0),
        "source_evidence_status": source_evidence_status,
        "source_evidence_requirement_satisfied": has_valid_source_evidence,
        "d3d_preflight_source_requirement_satisfied": has_valid_source_evidence,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7d_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7d_status": source_evidence_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7d_makes_any_campaign_d3d_eligible": False,
            "reason": reason,
        },
    }


def run_many_explicit_sml_source_evidence_preflights(
    symbols: list[str],
    candidate_payload_by_symbol: dict[str, dict[str, Any]] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    candidate_payload_by_symbol = candidate_payload_by_symbol or {}

    results = []

    for symbol in symbols:
        normalized_symbol = str(symbol or "").strip().upper()

        if not normalized_symbol:
            continue

        result = run_explicit_sml_source_evidence_preflight(
            symbol=normalized_symbol,
            candidate_payload=candidate_payload_by_symbol.get(normalized_symbol, {}),
            json_file_path=json_file_path,
            source_priority_policy=source_priority_policy,
        )
        results.append(result)

    pass_count = sum(
        1 for item in results
        if item.get("source_evidence_requirement_satisfied") is True
    )

    failure_count = sum(
        int(item.get("guardrail_failure_count") or 0)
        for item in results
    )

    return {
        "validator": VALIDATOR_NAME,
        "validator_version": VALIDATOR_VERSION,
        "validation_timestamp_utc": _utc_now(),
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_validator": False,
        "operator_control_unconfirmed_by_this_validator": False,
        "not_a_trade_signal": True,
        "symbol_count_attempted": len(results),
        "symbol_count_source_evidence_requirement_satisfied": pass_count,
        "symbol_count_without_source_evidence_requirement_satisfied": len(results) - pass_count,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7d_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": failure_count,
        "results": results,
        "runtime_decision": {
            "src7d_status": (
                "PASS_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_SOURCE_ONLY"
                if pass_count > 0 and failure_count == 0
                else "HOLD_SRC7D_NO_VALID_EXPLICIT_SML_SOURCE_EVIDENCE_OR_GUARDRAIL_FAILURE"
            ),
            "next_action": (
                "PROCEED_TO_SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW"
                if pass_count > 0 and failure_count == 0
                else "ADD_VALID_EXPLICIT_SML_RUNTIME_SOURCE_OR_STOP"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7d_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7D validates explicit SML source evidence only. "
                "Even when the source-evidence requirement is satisfied, D3D remains blocked until future dry-run source binding and no-drift review are complete."
            ),
        },
    }
