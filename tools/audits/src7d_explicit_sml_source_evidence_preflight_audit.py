from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_preflight_validator import (  # noqa: E402
    VALIDATOR_NAME,
    VALIDATOR_VERSION,
    run_explicit_sml_source_evidence_preflight,
    run_many_explicit_sml_source_evidence_preflights,
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


def _valid_fixture(symbol: str = "SPY") -> dict[str, Any]:
    return {
        "symbol": symbol,
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


def _invalid_fixture(symbol: str = "SPY") -> dict[str, Any]:
    record = _valid_fixture(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _check_common_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
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

    if int(result.get("guardrail_failure_count") or 0) != 0:
        failures.append(
            {
                "check": f"{label}_guardrail_failure_count",
                "expected": 0,
                "actual": result.get("guardrail_failure_count"),
            }
        )


def main() -> int:
    failures: list[dict[str, Any]] = []

    no_records_result = run_explicit_sml_source_evidence_preflight(
        symbol="SPY",
        candidate_payload={},
    )

    valid_result = run_explicit_sml_source_evidence_preflight(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture("SPY"),
            ]
        },
    )

    invalid_result = run_explicit_sml_source_evidence_preflight(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                _invalid_fixture("SPY"),
            ]
        },
    )

    many_result = run_many_explicit_sml_source_evidence_preflights(
        symbols=["SPY", "QQQ"],
        candidate_payload_by_symbol={
            "SPY": {
                "explicit_sml_records": [
                    _valid_fixture("SPY"),
                ]
            },
            "QQQ": {
                "explicit_sml_records": [
                    _invalid_fixture("QQQ"),
                ]
            },
        },
    )

    _check_common_guardrails(failures, "no_records", no_records_result)
    _check_common_guardrails(failures, "valid_result", valid_result)
    _check_common_guardrails(failures, "invalid_result", invalid_result)

    if no_records_result.get("source_evidence_requirement_satisfied") is not False:
        failures.append(
            {
                "check": "no_records_source_requirement",
                "expected": False,
                "actual": no_records_result.get("source_evidence_requirement_satisfied"),
            }
        )

    if valid_result.get("source_evidence_requirement_satisfied") is not True:
        failures.append(
            {
                "check": "valid_result_source_requirement",
                "expected": True,
                "actual": valid_result.get("source_evidence_requirement_satisfied"),
            }
        )

    if valid_result.get("source_evidence_status") != "PASS_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_SOURCE_ONLY":
        failures.append(
            {
                "check": "valid_result_status",
                "expected": "PASS_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_SOURCE_ONLY",
                "actual": valid_result.get("source_evidence_status"),
            }
        )

    if invalid_result.get("source_evidence_requirement_satisfied") is not False:
        failures.append(
            {
                "check": "invalid_result_source_requirement",
                "expected": False,
                "actual": invalid_result.get("source_evidence_requirement_satisfied"),
            }
        )

    if many_result.get("symbol_count_source_evidence_requirement_satisfied") != 1:
        failures.append(
            {
                "check": "many_result_source_requirement_count",
                "expected": 1,
                "actual": many_result.get("symbol_count_source_evidence_requirement_satisfied"),
            }
        )

    if many_result.get("d3d_execution_authorized") is not False:
        failures.append(
            {
                "check": "many_result_d3d_execution_authorized",
                "expected": False,
                "actual": many_result.get("d3d_execution_authorized"),
            }
        )

    if many_result.get("src7d_makes_any_campaign_d3d_eligible") is not False:
        failures.append(
            {
                "check": "many_result_src7d_makes_any_campaign_d3d_eligible",
                "expected": False,
                "actual": many_result.get("src7d_makes_any_campaign_d3d_eligible"),
            }
        )

    output = {
        "engine": "SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_AUDIT",
        "validator": VALIDATOR_NAME,
        "validator_version": VALIDATOR_VERSION,
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
            "no_records_status": no_records_result.get("source_evidence_status"),
            "no_records_requirement_satisfied": no_records_result.get("source_evidence_requirement_satisfied"),
            "valid_status": valid_result.get("source_evidence_status"),
            "valid_requirement_satisfied": valid_result.get("source_evidence_requirement_satisfied"),
            "invalid_status": invalid_result.get("source_evidence_status"),
            "invalid_requirement_satisfied": invalid_result.get("source_evidence_requirement_satisfied"),
            "many_symbol_count_attempted": many_result.get("symbol_count_attempted"),
            "many_symbol_count_source_evidence_requirement_satisfied": many_result.get("symbol_count_source_evidence_requirement_satisfied"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7d_status": (
                "PASS_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_AUDIT"
                if len(failures) == 0
                else "FAIL_SRC7D_EXPLICIT_SML_SOURCE_EVIDENCE_PREFLIGHT_AUDIT"
            ),
            "next_action": (
                "PROCEED_TO_SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7D_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7d_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7D validates the explicit SML source-evidence preflight only. "
                "Even when source evidence passes, D3D remains blocked until future dry-run source binding and no-drift review are completed."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7D explicit SML source-evidence preflight audit failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7D explicit SML source-evidence preflight validator created and audited; D3D remains blocked; proceed to SRC7E dry-run source binding review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
