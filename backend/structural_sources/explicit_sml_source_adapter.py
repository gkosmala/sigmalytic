from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.structural_sources.explicit_sml_contract import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    validate_explicit_sml_record,
)


ADAPTER_NAME = "SRC7B_RUNTIME_EXPLICIT_SML_SOURCE_ADAPTER_DESIGN"
ADAPTER_VERSION = "source_resolution_src7b_runtime_explicit_sml_source_adapter_design_v1"

DEFAULT_SOURCE_PRIORITY_POLICY = [
    "existing_non_mutating_runtime_payload_explicit_sml_records",
    "read_only_json_file_explicit_sml_records",
]

FORBIDDEN_SOURCE_POLICY_ITEMS = {
    "inferred_sml",
    "inferred_structural_location",
    "hvn_absorption_proxy",
    "ohlcv_derived_profile_approximation",
    "score_derived",
    "rank_derived",
    "edge_derived",
    "probability_derived",
    "trade_signal_derived",
    "gamma_options_overlay_derived",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


def _symbol_matches(record: dict[str, Any], symbol: str | None) -> bool:
    if not symbol:
        return True

    return str(record.get("symbol") or "").strip().upper() == str(symbol).strip().upper()


def _normalize_source_policy(source_priority_policy: list[str] | None) -> list[str]:
    if source_priority_policy is None:
        return list(DEFAULT_SOURCE_PRIORITY_POLICY)

    normalized = []

    for item in source_priority_policy:
        cleaned = str(item or "").strip()

        if cleaned:
            normalized.append(cleaned)

    return normalized or list(DEFAULT_SOURCE_PRIORITY_POLICY)


def _policy_rejections(source_priority_policy: list[str]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    for item in source_priority_policy:
        key = str(item or "").strip().lower()

        if key in FORBIDDEN_SOURCE_POLICY_ITEMS:
            failures.append(
                {
                    "policy_item": item,
                    "expected": "explicit non-inferred structural-location source only",
                    "actual": item,
                }
            )

    return failures


def _load_runtime_payload_records(candidate_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(candidate_payload, dict):
        return []

    candidate_keys = [
        "explicit_sml_records",
        "explicit_structural_location_records",
        "structural_location_records",
        "sml_records",
    ]

    for key in candidate_keys:
        value = candidate_payload.get(key)

        records = _as_list(value)

        if records:
            return [item for item in records if isinstance(item, dict)]

    return []


def _load_json_file_records(json_file_path: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []

    if not json_file_path:
        return [], warnings

    path = Path(json_file_path)

    if not path.exists():
        warnings.append(f"read-only JSON source path does not exist: {json_file_path}")
        return [], warnings

    if not path.is_file():
        warnings.append(f"read-only JSON source path is not a file: {json_file_path}")
        return [], warnings

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        payload = json.loads(text)
    except Exception as exc:
        warnings.append(f"read-only JSON source could not be parsed: {type(exc).__name__}: {exc}")
        return [], warnings

    if isinstance(payload, dict):
        for key in [
            "explicit_sml_records",
            "explicit_structural_location_records",
            "records",
            "data",
        ]:
            records = _as_list(payload.get(key))

            if records:
                return [item for item in records if isinstance(item, dict)], warnings

        return [payload], warnings

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], warnings

    warnings.append("read-only JSON source payload was neither a dict nor a list.")
    return [], warnings


def load_explicit_sml_records_read_only(
    symbol: str | None = None,
    candidate_payload: dict[str, Any] | None = None,
    json_file_path: str | None = None,
    source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    source_policy = _normalize_source_policy(source_priority_policy)
    policy_failures = _policy_rejections(source_policy)

    warnings: list[str] = []
    attempted_sources: list[str] = []
    selected_source = None
    raw_records: list[dict[str, Any]] = []

    json_file_path = json_file_path or os.environ.get("SIGMALYTIC_EXPLICIT_SML_JSON_PATH")

    if not policy_failures:
        for source_name in source_policy:
            attempted_sources.append(source_name)

            if source_name == "existing_non_mutating_runtime_payload_explicit_sml_records":
                raw_records = _load_runtime_payload_records(candidate_payload)

                if raw_records:
                    selected_source = source_name
                    break

            elif source_name == "read_only_json_file_explicit_sml_records":
                raw_records, json_warnings = _load_json_file_records(json_file_path)
                warnings.extend(json_warnings)

                if raw_records:
                    selected_source = source_name
                    break

            else:
                warnings.append(f"unsupported read-only source policy item skipped: {source_name}")

    symbol_filtered_records = [
        record for record in raw_records
        if _symbol_matches(record, symbol)
    ]

    validation_results = [
        validate_explicit_sml_record(record)
        for record in symbol_filtered_records
    ]

    valid_results = [
        result for result in validation_results
        if result.get("record_valid") is True
    ]

    invalid_results = [
        result for result in validation_results
        if result.get("record_valid") is not True
    ]

    if policy_failures:
        adapter_status = "SRC7B_BLOCKED_FORBIDDEN_SOURCE_POLICY"
        source_quality = "INVALID_SOURCE_POLICY"
    elif not raw_records:
        adapter_status = "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        source_quality = "NO_EXPLICIT_STRUCTURAL_SOURCE_RECORDS"
    elif not symbol_filtered_records:
        adapter_status = "SRC7B_NO_SYMBOL_MATCHING_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        source_quality = "NO_SYMBOL_MATCHING_EXPLICIT_STRUCTURAL_SOURCE_RECORDS"
    elif valid_results:
        adapter_status = "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY"
        source_quality = "VALID_EXPLICIT_STRUCTURAL_LOCATION_RECORDS"
    else:
        adapter_status = "SRC7B_RECORDS_FOUND_BUT_CONTRACT_REJECTED_ALL_READ_ONLY"
        source_quality = "STRUCTURAL_RECORDS_PRESENT_BUT_INVALID"

    return {
        "adapter": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "adapter_timestamp_utc": _utc_now(),
        "symbol": str(symbol).strip().upper() if symbol else None,
        "adapter_status": adapter_status,
        "source_quality": source_quality,
        "source_policy": source_policy,
        "attempted_sources": attempted_sources,
        "selected_source": selected_source,
        "raw_record_count": len(raw_records),
        "symbol_filtered_record_count": len(symbol_filtered_records),
        "valid_record_count": len(valid_results),
        "invalid_record_count": len(invalid_results),
        "warnings": warnings,
        "policy_failure_count": len(policy_failures),
        "policy_failures": policy_failures,
        "validation_results": validation_results,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_adapter": False,
        "operator_control_unconfirmed_by_this_adapter": False,
        "not_a_trade_signal": True,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7b_makes_any_campaign_d3d_eligible": False,
        "runtime_decision": {
            "runtime_explicit_source_status": adapter_status,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "next_action": (
                "PROCEED_TO_SRC7C_READ_ONLY_RUNTIME_SOURCE_PROBE"
                if valid_results
                else "PROCEED_TO_SRC7C_WITH_EXPECTED_NO_RECORDS_OR_ADD_READ_ONLY_SOURCE"
            ),
            "reason": (
                "SRC7B defines the read-only adapter for explicit SML/structural-location records. "
                "The adapter can validate explicit records when provided, but it does not persist, mutate, confirm operator control, or authorize D3D."
            ),
        },
    }
