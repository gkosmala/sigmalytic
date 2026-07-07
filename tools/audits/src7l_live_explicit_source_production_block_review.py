from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_source_adapter import load_explicit_sml_records_read_only  # noqa: E402
from backend.structural_sources.explicit_sml_no_drift_eligibility_review import (  # noqa: E402
    run_no_drift_dry_run_eligibility_review,
)


AUDIT_NAME = "SRC7L_LIVE_EXPLICIT_SOURCE_PRODUCTION_BLOCK_REVIEW"
AUDIT_VERSION = "source_resolution_src7l_live_explicit_source_production_block_review_v1"
REPO_JSON_PATH = ROOT / "runtime_sources" / "explicit_sml_runtime_source.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    failures: list[dict[str, Any]] = []

    if not REPO_JSON_PATH.exists():
        failures.append(
            {
                "check": "repo_json_exists",
                "expected": True,
                "actual": False,
                "path": str(REPO_JSON_PATH),
            }
        )
        payload: dict[str, Any] = {}
        records: list[dict[str, Any]] = []
    else:
        payload = json.loads(REPO_JSON_PATH.read_text(encoding="utf-8-sig"))
        records = payload.get("explicit_sml_records") or []

    if len(records) != 1:
        failures.append(
            {
                "check": "explicit_sml_record_count",
                "expected": 1,
                "actual": len(records),
            }
        )

    record = records[0] if records else {}
    symbol = record.get("symbol") or ""

    adapter_result = load_explicit_sml_records_read_only(
        symbol=symbol,
        candidate_payload={},
        json_file_path=str(REPO_JSON_PATH),
        source_priority_policy=["read_only_json_file_explicit_sml_records"],
    )

    eligibility_result = run_no_drift_dry_run_eligibility_review(
        candidate={
            "symbol": symbol,
            "campaign_id": record.get("campaign_id") or f"src7l-production-block-{symbol.lower()}",
        },
        candidate_payload={},
        json_file_path=str(REPO_JSON_PATH),
        source_priority_policy=["read_only_json_file_explicit_sml_records"],
    )

    if adapter_result.get("adapter_status") != "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY":
        failures.append(
            {
                "check": "adapter_status",
                "expected": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
                "actual": adapter_result.get("adapter_status"),
            }
        )

    if int(adapter_result.get("valid_record_count") or 0) != 1:
        failures.append(
            {
                "check": "valid_record_count",
                "expected": 1,
                "actual": adapter_result.get("valid_record_count"),
            }
        )

    if int(adapter_result.get("invalid_record_count") or 0) != 0:
        failures.append(
            {
                "check": "invalid_record_count",
                "expected": 0,
                "actual": adapter_result.get("invalid_record_count"),
            }
        )

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
        if eligibility_result.get(field) is not False:
            failures.append(
                {
                    "check": f"eligibility_{field}",
                    "expected": False,
                    "actual": eligibility_result.get(field),
                }
            )

    if eligibility_result.get("source_only_dry_run_eligibility_satisfied") is not True:
        failures.append(
            {
                "check": "source_only_dry_run_eligibility_satisfied",
                "expected": True,
                "actual": eligibility_result.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    if eligibility_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "check": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": eligibility_result.get("d3d_execution_recommendation"),
            }
        )

    if int(eligibility_result.get("guardrail_failure_count") or 0) != 0:
        failures.append(
            {
                "check": "guardrail_failure_count",
                "expected": 0,
                "actual": eligibility_result.get("guardrail_failure_count"),
            }
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
        "repo_json_path": str(REPO_JSON_PATH.relative_to(ROOT)),
        "symbol": symbol,
        "adapter_status": {
            "adapter_status": adapter_result.get("adapter_status"),
            "source_quality": adapter_result.get("source_quality"),
            "raw_record_count": adapter_result.get("raw_record_count"),
            "symbol_filtered_record_count": adapter_result.get("symbol_filtered_record_count"),
            "valid_record_count": adapter_result.get("valid_record_count"),
            "invalid_record_count": adapter_result.get("invalid_record_count"),
            "selected_source": adapter_result.get("selected_source"),
        },
        "production_block_status": {
            "source_only_dry_run_eligibility_satisfied": eligibility_result.get("source_only_dry_run_eligibility_satisfied"),
            "production_d3d_eligibility_satisfied": eligibility_result.get("production_d3d_eligibility_satisfied"),
            "d3d_execution_authorized": eligibility_result.get("d3d_execution_authorized"),
            "production_mutation_authorized": eligibility_result.get("production_mutation_authorized"),
            "operator_control_confirmed": eligibility_result.get("operator_control_confirmed"),
            "d3d_execution_recommendation": eligibility_result.get("d3d_execution_recommendation"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7l_status": (
                "PASS_SRC7L_LIVE_EXPLICIT_SOURCE_PRODUCTION_BLOCK_REVIEW"
                if len(failures) == 0
                else "FAIL_SRC7L_LIVE_EXPLICIT_SOURCE_PRODUCTION_BLOCK_REVIEW"
            ),
            "next_action": (
                "PROCEED_TO_SRC7M_FINAL_SOURCE_RESOLUTION_SUMMARY_OR_FUTURE_D3D_DESIGN_REVIEW"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7L_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7l_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7L proves that explicit structural evidence can be present while production D3D remains blocked. "
                "Source-only dry-run readiness is not production mutation authority."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7L production-block review failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7L production-block review passed; explicit source is available, source-only dry-run readiness passes, production D3D remains blocked, and operator control remains unconfirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
