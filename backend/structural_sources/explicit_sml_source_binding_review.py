from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.structural_sources.explicit_sml_preflight_validator import (
    run_explicit_sml_source_evidence_preflight,
)


REVIEW_NAME = "SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW"
REVIEW_VERSION = "source_resolution_src7e_d3d_dry_run_source_binding_review_v1"

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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


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


def _valid_source_records(preflight_result: dict[str, Any]) -> list[dict[str, Any]]:
    adapter_result = preflight_result.get("adapter_result") or {}
    validation_results = _as_list(adapter_result.get("validation_results"))

    return [
        item for item in validation_results
        if isinstance(item, dict) and item.get("record_valid") is True
    ]


def _record_symbol(validation_result: dict[str, Any]) -> str:
    normalized = validation_result.get("normalized_record") or {}
    return _upper(normalized.get("symbol"))


def _record_price_summary(validation_result: dict[str, Any]) -> dict[str, Any]:
    normalized = validation_result.get("normalized_record") or {}

    return {
        "level_type": normalized.get("level_type"),
        "price_low": normalized.get("price_low"),
        "price_mid": normalized.get("price_mid"),
        "price_high": normalized.get("price_high"),
        "source_method": normalized.get("source_method"),
        "source_reference": normalized.get("source_reference"),
        "source_timestamp_utc": normalized.get("source_timestamp_utc"),
        "observed_window_start_utc": normalized.get("observed_window_start_utc"),
        "observed_window_end_utc": normalized.get("observed_window_end_utc"),
    }


def _preflight_guardrail_failures(preflight_result: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_validator",
        "operator_control_unconfirmed_by_this_validator",
        "d3d_execution_authorized",
        "production_mutation_authorized",
        "operator_control_confirmed",
        "src7d_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if preflight_result.get(field) is not False:
            failures.append(
                {
                    "field": field,
                    "expected": False,
                    "actual": preflight_result.get(field),
                }
            )

    if preflight_result.get("read_only") is not True:
        failures.append(
            {
                "field": "read_only",
                "expected": True,
                "actual": preflight_result.get("read_only"),
            }
        )

    if preflight_result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": preflight_result.get("not_a_trade_signal"),
            }
        )

    if preflight_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": preflight_result.get("d3d_execution_recommendation"),
            }
        )

    if int(preflight_result.get("guardrail_failure_count") or 0) != 0:
        failures.append(
            {
                "field": "preflight_guardrail_failure_count",
                "expected": 0,
                "actual": preflight_result.get("guardrail_failure_count"),
            }
        )

    return failures


def run_d3d_dry_run_source_binding_review(
    candidate: dict[str, Any],
    candidate_payload: dict[str, Any] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    binding_warnings: list[str] = []

    if not isinstance(candidate, dict):
        return {
            "review": REVIEW_NAME,
            "review_version": REVIEW_VERSION,
            "review_timestamp_utc": _utc_now(),
            "candidate_valid": False,
            "source_binding_requirement_satisfied": False,
            "d3d_dry_run_source_binding_passed": False,
            "d3d_execution_authorized": False,
            "production_mutation_authorized": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
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

    if not symbol:
        failures.append(
            {
                "field": "candidate.symbol",
                "expected": "non-empty symbol",
                "actual": candidate.get("symbol"),
            }
        )

    if not campaign_id:
        binding_warnings.append(
            "candidate campaign_id is absent. Source binding can be reviewed by symbol, but production binding requires campaign identity."
        )

    preflight_result = run_explicit_sml_source_evidence_preflight(
        symbol=symbol,
        candidate_payload=candidate_payload,
        json_file_path=json_file_path,
        source_priority_policy=source_priority_policy,
    )

    failures.extend(_preflight_guardrail_failures(preflight_result))

    valid_records = _valid_source_records(preflight_result)
    matching_records = []

    for record in valid_records:
        if _record_symbol(record) == symbol:
            matching_records.append(record)

    if not valid_records:
        failures.append(
            {
                "field": "explicit_sml_source_evidence",
                "expected": "at least one valid explicit SML source record",
                "actual": 0,
            }
        )

    if valid_records and not matching_records:
        failures.append(
            {
                "field": "explicit_sml_symbol_binding",
                "expected": symbol,
                "actual": sorted({_record_symbol(item) for item in valid_records}),
            }
        )

    source_binding_requirement_satisfied = len(failures) == 0 and len(matching_records) > 0

    if source_binding_requirement_satisfied:
        binding_status = "PASS_SRC7E_DRY_RUN_SOURCE_BINDING_SOURCE_ONLY"
        next_action = "PROCEED_TO_SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW"
        reason = (
            "SRC7E confirmed that explicit SML source evidence can be bound to the candidate symbol in dry-run mode. "
            "This is source-binding readiness only. It does not authorize D3D and does not confirm operator control."
        )
    else:
        binding_status = "HOLD_SRC7E_SOURCE_BINDING_NOT_SATISFIED"
        next_action = "ADD_OR_REPAIR_EXPLICIT_SML_SOURCE_BINDING"
        reason = (
            "SRC7E did not confirm valid explicit SML source binding. D3D remains blocked."
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
        "candidate_valid": bool(symbol),
        "preflight_result": preflight_result,
        "valid_source_record_count": len(valid_records),
        "matching_source_record_count": len(matching_records),
        "matching_source_records": [
            _record_price_summary(item)
            for item in matching_records
        ],
        "binding_warnings": binding_warnings,
        "source_binding_status": binding_status,
        "source_binding_requirement_satisfied": source_binding_requirement_satisfied,
        "d3d_dry_run_source_binding_passed": source_binding_requirement_satisfied,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7e_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7e_status": binding_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7e_makes_any_campaign_d3d_eligible": False,
            "reason": reason,
        },
    }


def run_many_d3d_dry_run_source_binding_reviews(
    candidates: list[dict[str, Any]],
    candidate_payload_by_symbol: dict[str, dict[str, Any]] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    candidate_payload_by_symbol = candidate_payload_by_symbol or {}

    results = []

    for candidate in candidates:
        symbol = _candidate_symbol(candidate) if isinstance(candidate, dict) else ""

        result = run_d3d_dry_run_source_binding_review(
            candidate=candidate,
            candidate_payload=candidate_payload_by_symbol.get(symbol, {}),
            json_file_path=json_file_path,
            source_priority_policy=source_priority_policy,
        )
        results.append(result)

    source_binding_pass_count = sum(
        1 for item in results
        if item.get("source_binding_requirement_satisfied") is True
    )

    guardrail_failure_count = sum(
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
        "candidate_count_source_binding_satisfied": source_binding_pass_count,
        "candidate_count_source_binding_not_satisfied": len(results) - source_binding_pass_count,
        "d3d_execution_authorized": False,
        "production_mutation_authorized": False,
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7e_makes_any_campaign_d3d_eligible": False,
        "guardrail_failure_count": guardrail_failure_count,
        "results": results,
        "runtime_decision": {
            "src7e_status": (
                "PASS_SRC7E_DRY_RUN_SOURCE_BINDING_SOURCE_ONLY"
                if source_binding_pass_count > 0 and guardrail_failure_count == 0
                else "HOLD_SRC7E_SOURCE_BINDING_NOT_SATISFIED_OR_GUARDRAIL_FAILURE"
            ),
            "next_action": (
                "PROCEED_TO_SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW"
                if source_binding_pass_count > 0 and guardrail_failure_count == 0
                else "ADD_OR_REPAIR_EXPLICIT_SML_SOURCE_BINDING"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7e_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7E reviews dry-run source binding only. It does not mutate, confirm operator control, or authorize D3D."
            ),
        },
    }
