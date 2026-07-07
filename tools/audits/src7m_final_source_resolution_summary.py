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


AUDIT_NAME = "SRC7M_FINAL_SOURCE_RESOLUTION_SUMMARY"
AUDIT_VERSION = "source_resolution_src7m_final_source_resolution_summary_v1"
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
            "campaign_id": record.get("campaign_id") or f"src7m-final-summary-{symbol.lower()}",
        },
        candidate_payload={},
        json_file_path=str(REPO_JSON_PATH),
        source_priority_policy=["read_only_json_file_explicit_sml_records"],
    )

    expected_adapter_status = "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY"

    if adapter_result.get("adapter_status") != expected_adapter_status:
        failures.append(
            {
                "check": "adapter_status",
                "expected": expected_adapter_status,
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

    if eligibility_result.get("source_only_dry_run_eligibility_satisfied") is not True:
        failures.append(
            {
                "check": "source_only_dry_run_eligibility_satisfied",
                "expected": True,
                "actual": eligibility_result.get("source_only_dry_run_eligibility_satisfied"),
            }
        )

    false_required = [
        "production_d3d_eligibility_satisfied",
        "d3d_execution_authorized",
        "production_mutation_authorized",
        "operator_control_confirmed",
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "src7f_makes_any_campaign_d3d_eligible",
    ]

    for field in false_required:
        if eligibility_result.get(field) is not False:
            failures.append(
                {
                    "check": field,
                    "expected": False,
                    "actual": eligibility_result.get(field),
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
        "source_resolution_status": {
            "src7a_contract_created": True,
            "src7b_adapter_created": True,
            "src7c_runtime_probe_created": True,
            "src7d_preflight_validator_created": True,
            "src7e_source_binding_review_created": True,
            "src7f_no_drift_dry_run_review_created": True,
            "src7g_runtime_dry_run_endpoint_created": True,
            "src7h_materialization_plan_created": True,
            "src7i_local_json_probe_created": True,
            "src7j_deployment_guide_created": True,
            "src7k_repo_runtime_json_source_deployed": True,
            "src7l_production_block_review_passed": True,
            "src7m_final_summary_created": True,
        },
        "current_evidence_status": {
            "explicit_structural_source_available": True,
            "source_only_dry_run_ready": eligibility_result.get("source_only_dry_run_eligibility_satisfied"),
            "production_d3d_eligible": eligibility_result.get("production_d3d_eligibility_satisfied"),
            "d3d_execution_authorized": eligibility_result.get("d3d_execution_authorized"),
            "production_mutation_authorized": eligibility_result.get("production_mutation_authorized"),
            "operator_control_confirmed": eligibility_result.get("operator_control_confirmed"),
            "d3d_execution_recommendation": eligibility_result.get("d3d_execution_recommendation"),
        },
        "adapter_status": {
            "adapter_status": adapter_result.get("adapter_status"),
            "source_quality": adapter_result.get("source_quality"),
            "valid_record_count": adapter_result.get("valid_record_count"),
            "invalid_record_count": adapter_result.get("invalid_record_count"),
            "selected_source": adapter_result.get("selected_source"),
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7m_status": (
                "PASS_SRC7M_FINAL_SOURCE_RESOLUTION_SUMMARY"
                if len(failures) == 0
                else "FAIL_SRC7M_FINAL_SOURCE_RESOLUTION_SUMMARY"
            ),
            "next_action": (
                "HOLD_BEFORE_ANY_D3D_DESIGN_CHANGE"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7M_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7m_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7M closes the source-resolution track. The repo now contains a live-readable explicit "
                "structural source, but production D3D remains blocked and operator control remains unconfirmed."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7M final source-resolution summary failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7M final source-resolution summary passed; explicit source is live-readable, source-only dry-run readiness passes, production D3D remains blocked, and operator control remains unconfirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
