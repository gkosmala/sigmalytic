from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_source_binding_review import (  # noqa: E402
    REVIEW_NAME,
    REVIEW_VERSION,
    run_d3d_dry_run_source_binding_review,
    run_many_d3d_dry_run_source_binding_reviews,
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
        "campaign_id": f"fixture-{symbol.lower()}",
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


def _check_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
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

    valid_candidate = {
        "symbol": "SPY",
        "campaign_id": "fixture-spy",
    }

    no_source_candidate = {
        "symbol": "QQQ",
        "campaign_id": "fixture-qqq",
    }

    valid_result = run_d3d_dry_run_source_binding_review(
        candidate=valid_candidate,
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture("SPY"),
            ]
        },
    )

    no_source_result = run_d3d_dry_run_source_binding_review(
        candidate=no_source_candidate,
        candidate_payload={},
    )

    invalid_source_result = run_d3d_dry_run_source_binding_review(
        candidate=valid_candidate,
        candidate_payload={
            "explicit_sml_records": [
                _invalid_fixture("SPY"),
            ]
        },
    )

    mismatch_result = run_d3d_dry_run_source_binding_review(
        candidate=valid_candidate,
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture("QQQ"),
            ]
        },
    )

    many_result = run_many_d3d_dry_run_source_binding_reviews(
        candidates=[
            valid_candidate,
            no_source_candidate,
        ],
        candidate_payload_by_symbol={
            "SPY": {
                "explicit_sml_records": [
                    _valid_fixture("SPY"),
                ]
            },
            "QQQ": {},
        },
    )

    _check_guardrails(failures, "valid_result", valid_result)
    _check_guardrails(failures, "no_source_result", no_source_result)
    _check_guardrails(failures, "invalid_source_result", invalid_source_result)
    _check_guardrails(failures, "mismatch_result", mismatch_result)
    _check_guardrails(failures, "many_result", many_result)

    if valid_result.get("source_binding_requirement_satisfied") is not True:
        failures.append(
            {
                "check": "valid_result_source_binding_requirement",
                "expected": True,
                "actual": valid_result.get("source_binding_requirement_satisfied"),
            }
        )

    if valid_result.get("source_binding_status") != "PASS_SRC7E_DRY_RUN_SOURCE_BINDING_SOURCE_ONLY":
        failures.append(
            {
                "check": "valid_result_status",
                "expected": "PASS_SRC7E_DRY_RUN_SOURCE_BINDING_SOURCE_ONLY",
                "actual": valid_result.get("source_binding_status"),
            }
        )

    if no_source_result.get("source_binding_requirement_satisfied") is not False:
        failures.append(
            {
                "check": "no_source_result_source_binding_requirement",
                "expected": False,
                "actual": no_source_result.get("source_binding_requirement_satisfied"),
            }
        )

    if invalid_source_result.get("source_binding_requirement_satisfied") is not False:
        failures.append(
            {
                "check": "invalid_source_result_source_binding_requirement",
                "expected": False,
                "actual": invalid_source_result.get("source_binding_requirement_satisfied"),
            }
        )

    if mismatch_result.get("source_binding_requirement_satisfied") is not False:
        failures.append(
            {
                "check": "mismatch_result_source_binding_requirement",
                "expected": False,
                "actual": mismatch_result.get("source_binding_requirement_satisfied"),
            }
        )

    if many_result.get("candidate_count_source_binding_satisfied") != 1:
        failures.append(
            {
                "check": "many_result_source_binding_count",
                "expected": 1,
                "actual": many_result.get("candidate_count_source_binding_satisfied"),
            }
        )

    if many_result.get("guardrail_failure_count") < 1:
        failures.append(
            {
                "check": "many_result_expected_hold_guardrail_count",
                "expected": ">= 1 because QQQ has no source evidence",
                "actual": many_result.get("guardrail_failure_count"),
            }
        )

    output = {
        "engine": "SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW_AUDIT",
        "review": REVIEW_NAME,
        "review_version": REVIEW_VERSION,
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
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
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "audit_cases": {
            "valid_status": valid_result.get("source_binding_status"),
            "valid_source_binding_satisfied": valid_result.get("source_binding_requirement_satisfied"),
            "no_source_status": no_source_result.get("source_binding_status"),
            "no_source_binding_satisfied": no_source_result.get("source_binding_requirement_satisfied"),
            "invalid_source_status": invalid_source_result.get("source_binding_status"),
            "invalid_source_binding_satisfied": invalid_source_result.get("source_binding_requirement_satisfied"),
            "mismatch_status": mismatch_result.get("source_binding_status"),
            "mismatch_binding_satisfied": mismatch_result.get("source_binding_requirement_satisfied"),
            "many_candidate_count_attempted": many_result.get("candidate_count_attempted"),
            "many_candidate_count_source_binding_satisfied": many_result.get("candidate_count_source_binding_satisfied"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7e_status": (
                "PASS_SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW_AUDIT"
                if len(failures) == 0
                else "FAIL_SRC7E_D3D_DRY_RUN_SOURCE_BINDING_REVIEW_AUDIT"
            ),
            "next_action": (
                "PROCEED_TO_SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7E_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7e_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7E validates dry-run source binding only. A passing source binding does not confirm operator control, does not mutate campaigns, and does not authorize D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7E D3D dry-run source binding review audit failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7E D3D dry-run source binding review created and audited; D3D remains blocked; proceed to SRC7F no-drift dry-run eligibility review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
