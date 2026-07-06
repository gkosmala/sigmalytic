from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_source_adapter import (  # noqa: E402
    ADAPTER_NAME,
    ADAPTER_VERSION,
    load_explicit_sml_records_read_only,
)


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


def _valid_fixture() -> dict[str, Any]:
    return {
        "symbol": "SPY",
        "campaign_id": "fixture-only-not-runtime",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "fixture_explicit_manual_markup_chart_review",
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


def _invalid_fixture() -> dict[str, Any]:
    record = _valid_fixture()
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _check_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
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


def main() -> int:
    failures: list[dict[str, Any]] = []

    no_records_result = load_explicit_sml_records_read_only(symbol="SPY", candidate_payload={})
    valid_payload_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture(),
            ]
        },
    )
    invalid_payload_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                _invalid_fixture(),
            ]
        },
    )
    forbidden_policy_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture(),
            ]
        },
        source_priority_policy=[
            "hvn_absorption_proxy",
        ],
    )

    _check_guardrails(failures, "no_records", no_records_result)
    _check_guardrails(failures, "valid_payload", valid_payload_result)
    _check_guardrails(failures, "invalid_payload", invalid_payload_result)
    _check_guardrails(failures, "forbidden_policy", forbidden_policy_result)

    if no_records_result.get("adapter_status") != "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY":
        failures.append(
            {
                "check": "no_records_status",
                "expected": "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY",
                "actual": no_records_result.get("adapter_status"),
            }
        )

    if valid_payload_result.get("adapter_status") != "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY":
        failures.append(
            {
                "check": "valid_payload_status",
                "expected": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
                "actual": valid_payload_result.get("adapter_status"),
            }
        )

    if valid_payload_result.get("valid_record_count") != 1:
        failures.append(
            {
                "check": "valid_payload_valid_count",
                "expected": 1,
                "actual": valid_payload_result.get("valid_record_count"),
            }
        )

    if invalid_payload_result.get("adapter_status") != "SRC7B_RECORDS_FOUND_BUT_CONTRACT_REJECTED_ALL_READ_ONLY":
        failures.append(
            {
                "check": "invalid_payload_status",
                "expected": "SRC7B_RECORDS_FOUND_BUT_CONTRACT_REJECTED_ALL_READ_ONLY",
                "actual": invalid_payload_result.get("adapter_status"),
            }
        )

    if invalid_payload_result.get("valid_record_count") != 0:
        failures.append(
            {
                "check": "invalid_payload_valid_count",
                "expected": 0,
                "actual": invalid_payload_result.get("valid_record_count"),
            }
        )

    if forbidden_policy_result.get("adapter_status") != "SRC7B_BLOCKED_FORBIDDEN_SOURCE_POLICY":
        failures.append(
            {
                "check": "forbidden_policy_status",
                "expected": "SRC7B_BLOCKED_FORBIDDEN_SOURCE_POLICY",
                "actual": forbidden_policy_result.get("adapter_status"),
            }
        )

    if forbidden_policy_result.get("policy_failure_count") < 1:
        failures.append(
            {
                "check": "forbidden_policy_failure_count",
                "expected": ">= 1",
                "actual": forbidden_policy_result.get("policy_failure_count"),
            }
        )

    output = {
        "engine": "SRC7B_RUNTIME_EXPLICIT_SML_SOURCE_ADAPTER_DESIGN_AUDIT",
        "adapter": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "audit_cases": {
            "no_records_status": no_records_result.get("adapter_status"),
            "valid_payload_status": valid_payload_result.get("adapter_status"),
            "valid_payload_valid_record_count": valid_payload_result.get("valid_record_count"),
            "invalid_payload_status": invalid_payload_result.get("adapter_status"),
            "invalid_payload_valid_record_count": invalid_payload_result.get("valid_record_count"),
            "forbidden_policy_status": forbidden_policy_result.get("adapter_status"),
            "forbidden_policy_failure_count": forbidden_policy_result.get("policy_failure_count"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7b_status": (
                "PASS_SRC7B_RUNTIME_EXPLICIT_SML_SOURCE_ADAPTER_DESIGN_AUDIT"
                if len(failures) == 0
                else "FAIL_SRC7B_RUNTIME_EXPLICIT_SML_SOURCE_ADAPTER_DESIGN_AUDIT"
            ),
            "next_action": (
                "PROCEED_TO_SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7B_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7b_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7B creates and audits the runtime read-only adapter design for explicit SML records. "
                "It validates supplied records against SRC7A but does not create runtime evidence, persist records, mutate campaigns, or authorize D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7B runtime explicit SML source adapter design audit failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7B runtime explicit SML source adapter design created and audited; D3D remains blocked; proceed to SRC7C runtime source probe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
