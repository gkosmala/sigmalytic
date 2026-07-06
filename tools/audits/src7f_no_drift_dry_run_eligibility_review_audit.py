from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_no_drift_eligibility_review import (  # noqa: E402
    REVIEW_NAME,
    REVIEW_VERSION,
    NO_DRIFT_DOCTRINE,
    run_no_drift_dry_run_eligibility_review,
    run_many_no_drift_dry_run_eligibility_reviews,
)


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


def _check_outer_guardrails(failures: list[dict[str, Any]], label: str, result: dict[str, Any]) -> None:
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

    valid_candidate = {
        "symbol": "SPY",
        "campaign_id": "fixture-spy",
    }

    no_source_candidate = {
        "symbol": "QQQ",
        "campaign_id": "fixture-qqq",
    }

    valid_result = run_no_drift_dry_run_eligibility_review(
        candidate=valid_candidate,
        candidate_payload={
            "explicit_sml_records": [
                _valid_fixture("SPY"),
            ]
        },
    )

    no_source_result = run_no_drift_dry_run_eligibility_review(
        candidate=no_source_candidate,
        candidate_payload={},
    )

    invalid_source_result = run_no_drift_dry_run_eligibility_review(
        candidate=valid_candidate,
        candidate_payload={
            "explicit_sml_records": [
                _invalid_fixture("SPY"),
            ]
        },
    )

    many_result = run_many_no_drift_dry_run_eligibility_reviews(
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

    _check_outer_guardrails(failures, "valid_result", valid_result)
    _check_outer_guardrails(failures, "no_source_result", no_source_result)
    _check_outer_guardrails(failures, "invalid_source_result", invalid_source_result)

    if valid_result.get("source_binding_requirement_satisfied") is not True:
        failures.append(
            {
                "check": "valid_result_source_binding_requirement",
                "expected": True,
                "actual": valid_result.get("source_binding_requirement_satisfied"),
            }
        )

    if valid_result.get("no_drift_requirement_satisfied") is not True:
        failures.append(
            {
                "check": "valid_result_no_drift_requirement",
                "expected": True,
                "actual": valid_result.get("no_drift_requirement_satisfied"),
            }
        )

    if valid_result.get("source_only_dry_run_eligibility_satisfied") is not True:
        failures.append(
            {
                "check": "valid_result_source_only_dry_run_eligibility",
                "expected": True,
                "actual": valid_result.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if no_source_result.get("source_only_dry_run_eligibility_satisfied") is not False:
        failures.append(
            {
                "check": "no_source_result_source_only_dry_run_eligibility",
                "expected": False,
                "actual": no_source_result.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if invalid_source_result.get("source_only_dry_run_eligibility_satisfied") is not False:
        failures.append(
            {
                "check": "invalid_source_result_source_only_dry_run_eligibility",
                "expected": False,
                "actual": invalid_source_result.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if many_result.get("candidate_count_source_only_dry_run_eligibility_satisfied") != 1:
        failures.append(
            {
                "check": "many_result_source_only_count",
                "expected": 1,
                "actual": many_result.get("candidate_count_source_only_dry_run_eligibility_satisfied"),
            }
        )

    if many_result.get("candidate_count_production_d3d_eligible") != 0:
        failures.append(
            {
                "check": "many_result_production_d3d_eligible_count",
                "expected": 0,
                "actual": many_result.get("candidate_count_production_d3d_eligible"),
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

    if many_result.get("src7f_makes_any_campaign_d3d_eligible") is not False:
        failures.append(
            {
                "check": "many_result_src7f_makes_any_campaign_d3d_eligible",
                "expected": False,
                "actual": many_result.get("src7f_makes_any_campaign_d3d_eligible"),
            }
        )

    output = {
        "engine": "SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW_AUDIT",
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
            "valid_source_binding_satisfied": valid_result.get("source_binding_requirement_satisfied"),
            "valid_no_drift_satisfied": valid_result.get("no_drift_requirement_satisfied"),
            "valid_source_only_dry_run_eligibility_satisfied": valid_result.get("source_only_dry_run_eligibility_satisfied"),
            "valid_production_d3d_eligibility_satisfied": valid_result.get("production_d3d_eligibility_satisfied"),
            "no_source_source_only_dry_run_eligibility_satisfied": no_source_result.get("source_only_dry_run_eligibility_satisfied"),
            "invalid_source_only_dry_run_eligibility_satisfied": invalid_source_result.get("source_only_dry_run_eligibility_satisfied"),
            "many_candidate_count_attempted": many_result.get("candidate_count_attempted"),
            "many_candidate_count_source_only_dry_run_eligibility_satisfied": many_result.get("candidate_count_source_only_dry_run_eligibility_satisfied"),
            "many_candidate_count_production_d3d_eligible": many_result.get("candidate_count_production_d3d_eligible"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7f_status": (
                "PASS_SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW_AUDIT"
                if len(failures) == 0
                else "FAIL_SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW_AUDIT"
            ),
            "next_action": (
                "PROCEED_TO_SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7F_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7f_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7F confirms source-only dry-run eligibility can pass while production D3D eligibility remains false. "
                "No mutation, operator-control confirmation, or D3D authorization is permitted."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7F no-drift dry-run eligibility review audit failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7F no-drift dry-run eligibility review created and audited; source-only dry-run readiness can pass; production D3D remains blocked; proceed to SRC7G runtime dry-run preflight endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
