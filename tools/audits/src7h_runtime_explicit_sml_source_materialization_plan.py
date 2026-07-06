from __future__ import annotations

import json
import sys
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


def _valid_runtime_like_fixture(symbol: str = "SPY") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "campaign_id": f"fixture-{symbol.lower()}-not-runtime",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "fixture_explicit_manual_markup_chart_review_not_runtime_evidence",
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


def _invalid_proxy_fixture(symbol: str = "SPY") -> dict[str, Any]:
    record = _valid_runtime_like_fixture(symbol)
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

    if not TEMPLATE_PATH.exists():
        failures.append(
            {
                "check": "template_exists",
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
                "check": "template_only_flag",
                "expected": True,
                "actual": template_payload.get("template_only"),
            }
        )

    if template_payload.get("not_runtime_evidence") is not True:
        failures.append(
            {
                "check": "not_runtime_evidence_flag",
                "expected": True,
                "actual": template_payload.get("not_runtime_evidence"),
            }
        )

    if template_payload.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "check": "template_d3d_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": template_payload.get("d3d_execution_recommendation"),
            }
        )

    valid_fixture = _valid_runtime_like_fixture("SPY")
    invalid_fixture = _invalid_proxy_fixture("SPY")

    valid_contract_result = validate_explicit_sml_record(valid_fixture)
    invalid_contract_result = validate_explicit_sml_record(invalid_fixture)

    if valid_contract_result.get("record_valid") is not True:
        failures.append(
            {
                "check": "runtime_like_valid_fixture_contract",
                "expected": True,
                "actual": valid_contract_result.get("record_valid"),
                "details": valid_contract_result.get("failures"),
            }
        )

    if invalid_contract_result.get("record_valid") is not False:
        failures.append(
            {
                "check": "proxy_fixture_contract_rejection",
                "expected": False,
                "actual": invalid_contract_result.get("record_valid"),
            }
        )

    adapter_runtime_none = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
    )

    adapter_fixture_valid = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={
            "explicit_sml_records": [
                valid_fixture,
            ]
        },
    )

    if adapter_runtime_none.get("adapter_status") != "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY":
        failures.append(
            {
                "check": "runtime_none_expected_no_records",
                "expected": "SRC7B_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY",
                "actual": adapter_runtime_none.get("adapter_status"),
            }
        )

    if adapter_fixture_valid.get("adapter_status") != "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY":
        failures.append(
            {
                "check": "fixture_valid_adapter_status",
                "expected": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
                "actual": adapter_fixture_valid.get("adapter_status"),
            }
        )

    eligibility_fixture_valid = run_no_drift_dry_run_eligibility_review(
        candidate={
            "symbol": "SPY",
            "campaign_id": "fixture-spy-not-runtime",
        },
        candidate_payload={
            "explicit_sml_records": [
                valid_fixture,
            ]
        },
    )

    _check_guardrails(failures, "eligibility_fixture_valid", eligibility_fixture_valid)

    if eligibility_fixture_valid.get("source_only_dry_run_eligibility_satisfied") is not True:
        failures.append(
            {
                "check": "fixture_source_only_readiness",
                "expected": True,
                "actual": eligibility_fixture_valid.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if eligibility_fixture_valid.get("production_d3d_eligibility_satisfied") is not False:
        failures.append(
            {
                "check": "fixture_production_d3d_eligibility",
                "expected": False,
                "actual": eligibility_fixture_valid.get("production_d3d_eligibility_satisfied"),
            }
        )

    materialization_plan = {
        "selected_materialization_path": "READ_ONLY_EXPLICIT_SML_JSON_SOURCE_FIRST",
        "why_this_path": (
            "The SRC7B adapter already supports a read-only JSON explicit SML source through SIGMALYTIC_EXPLICIT_SML_JSON_PATH. "
            "This is the lowest-risk way to materialize real explicit structural records without mutating campaigns or relaxing D3D."
        ),
        "runtime_source_requirements": [
            "Real explicit structural records must be placed in a separate runtime JSON source, not in the template file.",
            "The runtime JSON source must use the SRC7A contract fields exactly.",
            "Every record must be explicit, non-inferred, non-proxy, source-referenced, timestamped, symbol-bound, and price-bound.",
            "The runtime JSON source must be loaded read-only.",
            "The runtime JSON source must not be derived from scores, ranks, edge, probability, trade signals, gamma/options overlays, targets, or OHLCV profile approximations.",
            "Runtime source probe must pass before any future D3D dry-run discussion.",
        ],
        "environment_variable": "SIGMALYTIC_EXPLICIT_SML_JSON_PATH",
        "next_phase": "SRC7I_READ_ONLY_RUNTIME_JSON_SOURCE_PROBE",
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src7h_makes_any_campaign_d3d_eligible": False,
    }

    output = {
        "engine": "SRC7H_RUNTIME_EXPLICIT_SML_SOURCE_MATERIALIZATION_PLAN",
        "version": "source_resolution_src7h_runtime_explicit_sml_source_materialization_plan_v1",
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
        "template_path": str(TEMPLATE_PATH.relative_to(ROOT)),
        "template_status": {
            "template_only": template_payload.get("template_only"),
            "not_runtime_evidence": template_payload.get("not_runtime_evidence"),
            "record_count": len(template_payload.get("explicit_sml_records") or []),
        },
        "local_validation_status": {
            "valid_fixture_record_valid": valid_contract_result.get("record_valid"),
            "invalid_proxy_fixture_record_valid": invalid_contract_result.get("record_valid"),
            "runtime_none_adapter_status": adapter_runtime_none.get("adapter_status"),
            "fixture_valid_adapter_status": adapter_fixture_valid.get("adapter_status"),
            "fixture_source_only_dry_run_eligibility_satisfied": eligibility_fixture_valid.get("source_only_dry_run_eligibility_satisfied"),
            "fixture_production_d3d_eligibility_satisfied": eligibility_fixture_valid.get("production_d3d_eligibility_satisfied"),
        },
        "materialization_plan": materialization_plan,
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7h_status": (
                "PASS_SRC7H_RUNTIME_EXPLICIT_SML_SOURCE_MATERIALIZATION_PLAN"
                if len(failures) == 0
                else "FAIL_SRC7H_RUNTIME_EXPLICIT_SML_SOURCE_MATERIALIZATION_PLAN"
            ),
            "next_action": (
                "PROCEED_TO_SRC7I_READ_ONLY_RUNTIME_JSON_SOURCE_PROBE"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7H_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7h_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7H creates the materialization plan and template for real explicit SML runtime records. "
                "The template is not evidence. Runtime explicit records must be supplied separately and probed read-only before any future D3D dry-run path."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7H runtime explicit SML source materialization plan failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7H runtime explicit SML source materialization plan created and audited; template is not runtime evidence; D3D remains blocked; proceed to SRC7I read-only runtime JSON source probe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
