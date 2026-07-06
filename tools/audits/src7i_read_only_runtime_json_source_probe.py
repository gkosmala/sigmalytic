from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_contract import validate_explicit_sml_record  # noqa: E402
from backend.structural_sources.explicit_sml_source_adapter import load_explicit_sml_records_read_only  # noqa: E402
from backend.structural_sources.explicit_sml_no_drift_eligibility_review import (  # noqa: E402
    run_no_drift_dry_run_eligibility_review,
)


AUDIT_NAME = "SRC7I_READ_ONLY_RUNTIME_JSON_SOURCE_PROBE"
AUDIT_VERSION = "source_resolution_src7i_read_only_runtime_json_source_probe_v1"

TEMPLATE_PATH = ROOT / "docs" / "templates" / "src7h_explicit_sml_runtime_source_template_2026-07-06.json"

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


def _runtime_like_valid_record(symbol: str = "SPY") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "campaign_id": f"runtime-json-fixture-{symbol.lower()}-not-production",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "src7i_temp_json_fixture_not_runtime_production_evidence",
        "source_timestamp_utc": "2026-07-06T22:00:00Z",
        "observed_window_start_utc": "2023-04-24T08:00:00Z",
        "observed_window_end_utc": "2023-04-24T16:06:00Z",
        "is_explicit": True,
        "is_inferred": False,
        "is_proxy": False,
        "is_hvn_absorption_proxy": False,
        "derived_from_score": False,
        "derived_from_rank": False,
        "derived_from_probability": False,
        "derived_from_edge": False,
        "derived_from_expected_return": False,
        "derived_from_target_projection": False,
        "derived_from_trade_signal": False,
        "derived_from_gamma_options_overlay": False,
        "derived_from_ohlcv_profile_approximation": False,
        "confirms_operator_control": False,
        "authorizes_d3d": False,
        "mutates_campaigns": False,
        "writes_to_supabase": False,
        "eligible_for_immediate_d3d_mutation": False,
    }


def _runtime_like_invalid_proxy_record(symbol: str = "SPY") -> dict[str, Any]:
    record = _runtime_like_valid_record(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    record["source_reference"] = "src7i_invalid_proxy_fixture_must_be_rejected"
    return record


def _write_temp_json(payload: dict[str, Any]) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="sigmalytic_src7i_"))
    path = temp_dir / "explicit_sml_runtime_source_fixture_not_production.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _check_adapter_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
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
        if result.get(field) is not False:
            failures.append(
                {
                    "check": f"{label}_{field}",
                    "expected": False,
                    "actual": result.get(field),
                }
            )

    if result.get("read_only") is not True:
        failures.append(
            {
                "check": f"{label}_read_only",
                "expected": True,
                "actual": result.get("read_only"),
            }
        )

    if result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "check": f"{label}_not_a_trade_signal",
                "expected": True,
                "actual": result.get("not_a_trade_signal"),
            }
        )

    if result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "check": f"{label}_d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": result.get("d3d_execution_recommendation"),
            }
        )


def _check_eligibility_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_review",
        "operator_control_unconfirmed_by_this_review",
        "production_d3d_eligibility_satisfied",
        "d3d_execution_authorized",
        "production_mutation_authorized",
        "operator_control_confirmed",
        "src7f_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if result.get(field) is not False:
            failures.append(
                {
                    "check": f"{label}_{field}",
                    "expected": False,
                    "actual": result.get(field),
                }
            )

    if result.get("read_only") is not True:
        failures.append(
            {
                "check": f"{label}_read_only",
                "expected": True,
                "actual": result.get("read_only"),
            }
        )

    if result.get("dry_run") is not True:
        failures.append(
            {
                "check": f"{label}_dry_run",
                "expected": True,
                "actual": result.get("dry_run"),
            }
        )

    if result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "check": f"{label}_not_a_trade_signal",
                "expected": True,
                "actual": result.get("not_a_trade_signal"),
            }
        )

    if result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "check": f"{label}_d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": result.get("d3d_execution_recommendation"),
            }
        )


def main() -> int:
    failures: list[dict[str, Any]] = []

    env_path = os.environ.get("SIGMALYTIC_EXPLICIT_SML_JSON_PATH")
    env_path_present = bool(env_path)
    env_path_exists = bool(env_path and Path(env_path).exists())

    if not TEMPLATE_PATH.exists():
        failures.append(
            {
                "check": "src7h_template_exists",
                "expected": True,
                "actual": False,
                "path": str(TEMPLATE_PATH),
            }
        )
        template_payload = {}
    else:
        template_payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    if template_payload.get("template_only") is not True:
        failures.append(
            {
                "check": "template_only",
                "expected": True,
                "actual": template_payload.get("template_only"),
            }
        )

    if template_payload.get("not_runtime_evidence") is not True:
        failures.append(
            {
                "check": "template_not_runtime_evidence",
                "expected": True,
                "actual": template_payload.get("not_runtime_evidence"),
            }
        )

    valid_record = _runtime_like_valid_record("SPY")
    invalid_record = _runtime_like_invalid_proxy_record("SPY")

    valid_contract_result = validate_explicit_sml_record(valid_record)
    invalid_contract_result = validate_explicit_sml_record(invalid_record)

    if valid_contract_result.get("record_valid") is not True:
        failures.append(
            {
                "check": "valid_temp_json_record_contract",
                "expected": True,
                "actual": valid_contract_result.get("record_valid"),
                "details": valid_contract_result.get("failures"),
            }
        )

    if invalid_contract_result.get("record_valid") is not False:
        failures.append(
            {
                "check": "invalid_proxy_record_contract_rejection",
                "expected": False,
                "actual": invalid_contract_result.get("record_valid"),
            }
        )

    valid_json_path = _write_temp_json(
        {
            "source_name": "SRC7I_TEMP_READ_ONLY_JSON_FIXTURE_NOT_PRODUCTION",
            "fixture_only": True,
            "not_runtime_production_evidence": True,
            "explicit_sml_records": [
                valid_record,
            ],
        }
    )

    invalid_json_path = _write_temp_json(
        {
            "source_name": "SRC7I_TEMP_INVALID_PROXY_JSON_FIXTURE_NOT_PRODUCTION",
            "fixture_only": True,
            "not_runtime_production_evidence": True,
            "explicit_sml_records": [
                invalid_record,
            ],
        }
    )

    mixed_json_path = _write_temp_json(
        {
            "source_name": "SRC7I_TEMP_MIXED_JSON_FIXTURE_NOT_PRODUCTION",
            "fixture_only": True,
            "not_runtime_production_evidence": True,
            "explicit_sml_records": [
                valid_record,
                invalid_record,
            ],
        }
    )

    missing_json_path = valid_json_path.parent / "missing_explicit_sml_source.json"

    no_path_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=None,
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    valid_json_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=str(valid_json_path),
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    invalid_json_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=str(invalid_json_path),
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    mixed_json_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=str(mixed_json_path),
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    missing_json_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=str(missing_json_path),
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    _check_adapter_guardrails(failures, "no_path_json_adapter", no_path_result)
    _check_adapter_guardrails(failures, "valid_json_adapter", valid_json_result)
    _check_adapter_guardrails(failures, "invalid_json_adapter", invalid_json_result)
    _check_adapter_guardrails(failures, "mixed_json_adapter", mixed_json_result)
    _check_adapter_guardrails(failures, "missing_json_adapter", missing_json_result)

    if valid_json_result.get("adapter_status") != "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY":
        failures.append(
            {
                "check": "valid_json_adapter_status",
                "expected": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
                "actual": valid_json_result.get("adapter_status"),
            }
        )

    if int(valid_json_result.get("valid_record_count") or 0) != 1:
        failures.append(
            {
                "check": "valid_json_valid_record_count",
                "expected": 1,
                "actual": valid_json_result.get("valid_record_count"),
            }
        )

    if invalid_json_result.get("adapter_status") != "SRC7B_RECORDS_FOUND_BUT_CONTRACT_REJECTED_ALL_READ_ONLY":
        failures.append(
            {
                "check": "invalid_json_adapter_status",
                "expected": "SRC7B_RECORDS_FOUND_BUT_CONTRACT_REJECTED_ALL_READ_ONLY",
                "actual": invalid_json_result.get("adapter_status"),
            }
        )

    if int(invalid_json_result.get("valid_record_count") or 0) != 0:
        failures.append(
            {
                "check": "invalid_json_valid_record_count",
                "expected": 0,
                "actual": invalid_json_result.get("valid_record_count"),
            }
        )

    if mixed_json_result.get("adapter_status") != "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY":
        failures.append(
            {
                "check": "mixed_json_adapter_status",
                "expected": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
                "actual": mixed_json_result.get("adapter_status"),
            }
        )

    if int(mixed_json_result.get("valid_record_count") or 0) != 1:
        failures.append(
            {
                "check": "mixed_json_valid_record_count",
                "expected": 1,
                "actual": mixed_json_result.get("valid_record_count"),
            }
        )

    if int(mixed_json_result.get("invalid_record_count") or 0) != 1:
        failures.append(
            {
                "check": "mixed_json_invalid_record_count",
                "expected": 1,
                "actual": mixed_json_result.get("invalid_record_count"),
            }
        )

    if missing_json_result.get("adapter_status") != "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY":
        failures.append(
            {
                "check": "missing_json_adapter_status",
                "expected": "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY",
                "actual": missing_json_result.get("adapter_status"),
            }
        )

    eligibility_from_json = run_no_drift_dry_run_eligibility_review(
        candidate={
            "symbol": "SPY",
            "campaign_id": "runtime-json-fixture-spy-not-production",
        },
        candidate_payload={},
        json_file_path=str(valid_json_path),
        source_priority_policy=[
            "read_only_json_file_explicit_sml_records",
        ],
    )

    _check_eligibility_guardrails(failures, "eligibility_from_json", eligibility_from_json)

    if eligibility_from_json.get("source_only_dry_run_eligibility_satisfied") is not True:
        failures.append(
            {
                "check": "eligibility_from_json_source_only_ready",
                "expected": True,
                "actual": eligibility_from_json.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if eligibility_from_json.get("production_d3d_eligibility_satisfied") is not False:
        failures.append(
            {
                "check": "eligibility_from_json_production_d3d",
                "expected": False,
                "actual": eligibility_from_json.get("production_d3d_eligibility_satisfied"),
            }
        )

    runtime_json_probe_status = (
        "PASS_SRC7I_READ_ONLY_RUNTIME_JSON_SOURCE_PROBE_FIXTURE_ONLY"
        if len(failures) == 0
        else "FAIL_SRC7I_READ_ONLY_RUNTIME_JSON_SOURCE_PROBE"
    )

    output = {
        "engine": AUDIT_NAME,
        "version": AUDIT_VERSION,
        "audit_timestamp_utc": _utc_now(),
        "diagnostic_only": True,
        "dry_run": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "environment_status": {
            "SIGMALYTIC_EXPLICIT_SML_JSON_PATH_present": env_path_present,
            "SIGMALYTIC_EXPLICIT_SML_JSON_PATH_exists": env_path_exists,
            "environment_path_value_redacted": True,
        },
        "template_status": {
            "template_path": str(TEMPLATE_PATH.relative_to(ROOT)),
            "template_only": template_payload.get("template_only"),
            "not_runtime_evidence": template_payload.get("not_runtime_evidence"),
        },
        "temp_json_probe_paths": {
            "paths_are_temporary": True,
            "paths_are_not_committed": True,
            "valid_json_path_name": valid_json_path.name,
            "invalid_json_path_name": invalid_json_path.name,
            "mixed_json_path_name": mixed_json_path.name,
        },
        "probe_results": {
            "no_path_status": no_path_result.get("adapter_status"),
            "valid_json_status": valid_json_result.get("adapter_status"),
            "valid_json_valid_record_count": valid_json_result.get("valid_record_count"),
            "invalid_json_status": invalid_json_result.get("adapter_status"),
            "invalid_json_valid_record_count": invalid_json_result.get("valid_record_count"),
            "mixed_json_status": mixed_json_result.get("adapter_status"),
            "mixed_json_valid_record_count": mixed_json_result.get("valid_record_count"),
            "mixed_json_invalid_record_count": mixed_json_result.get("invalid_record_count"),
            "missing_json_status": missing_json_result.get("adapter_status"),
            "eligibility_from_json_source_only_ready": eligibility_from_json.get("source_only_dry_run_eligibility_satisfied"),
            "eligibility_from_json_production_d3d_eligible": eligibility_from_json.get("production_d3d_eligibility_satisfied"),
        },
        "runtime_evidence_conclusion": {
            "real_runtime_json_source_confirmed": env_path_exists,
            "temp_fixture_json_probe_passed": len(failures) == 0,
            "fixture_json_is_runtime_production_evidence": False,
            "d3d_execution_authorized": False,
            "production_mutation_authorized": False,
        },
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7i_status": runtime_json_probe_status,
            "next_action": (
                "PROCEED_TO_SRC7J_RUNTIME_JSON_SOURCE_DEPLOYMENT_GUIDE"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7I_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7i_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7I proves the read-only JSON source path works using temporary fixture JSON. "
                "Temporary fixture JSON is not runtime production evidence. A real explicit SML JSON source still must be supplied and configured separately."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7I read-only runtime JSON source probe failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7I read-only runtime JSON source probe passed with temporary fixture JSON; no production runtime evidence was created; D3D remains blocked; proceed to SRC7J runtime JSON source deployment guide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
