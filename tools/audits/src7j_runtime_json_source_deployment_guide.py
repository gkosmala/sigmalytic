from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_contract import validate_explicit_sml_record  # noqa: E402
from backend.structural_sources.explicit_sml_source_adapter import load_explicit_sml_records_read_only  # noqa: E402


AUDIT_NAME = "SRC7J_RUNTIME_JSON_SOURCE_DEPLOYMENT_GUIDE"
AUDIT_VERSION = "source_resolution_src7j_runtime_json_source_deployment_guide_v1"

GUIDE_PATH = ROOT / "docs" / "deployment" / "src7j_runtime_explicit_sml_json_source_deployment_guide_2026-07-06.md"
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

REQUIRED_GUIDE_PHRASES = [
    "SIGMALYTIC_EXPLICIT_SML_JSON_PATH",
    "That fixture was not runtime production evidence",
    "D3D remains blocked",
    "writes_to_supabase = false",
    "mutates_campaigns = false",
    "executes_d3d = false",
    "authorizes_d3d = false",
    "operator_control_confirmed = false",
    "production_d3d_eligibility_satisfied = false",
    "DO_NOT_EXECUTE_D3D",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _example_valid_record() -> dict[str, Any]:
    return {
        "symbol": "SPY",
        "campaign_id": "example-only-not-runtime",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "src7j_example_only_auditable_source_reference",
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


def _example_invalid_proxy_record() -> dict[str, Any]:
    record = _example_valid_record()
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    record["source_reference"] = "src7j_invalid_proxy_example_must_be_rejected"
    return record


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
            failures.append({"check": f"{label}_{field}", "expected": False, "actual": result.get(field)})

    if result.get("read_only") is not True:
        failures.append({"check": f"{label}_read_only", "expected": True, "actual": result.get("read_only")})

    if result.get("not_a_trade_signal") is not True:
        failures.append({"check": f"{label}_not_a_trade_signal", "expected": True, "actual": result.get("not_a_trade_signal")})

    if result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append({"check": f"{label}_d3d_execution_recommendation", "expected": "DO_NOT_EXECUTE_D3D", "actual": result.get("d3d_execution_recommendation")})


def main() -> int:
    failures: list[dict[str, Any]] = []

    env_path = os.environ.get("SIGMALYTIC_EXPLICIT_SML_JSON_PATH")
    env_path_present = bool(env_path)
    env_path_exists = bool(env_path and Path(env_path).exists())

    if not GUIDE_PATH.exists():
        failures.append({"check": "deployment_guide_exists", "expected": True, "actual": False, "path": str(GUIDE_PATH)})
        guide_text = ""
    else:
        guide_text = GUIDE_PATH.read_text(encoding="utf-8", errors="replace")

    missing_phrases = [phrase for phrase in REQUIRED_GUIDE_PHRASES if phrase not in guide_text]

    if missing_phrases:
        failures.append({"check": "deployment_guide_required_phrases", "expected": "all required phrases present", "actual": missing_phrases})

    if not TEMPLATE_PATH.exists():
        failures.append({"check": "src7h_template_exists", "expected": True, "actual": False, "path": str(TEMPLATE_PATH)})
        template_payload = {}
    else:
        template_payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    if template_payload.get("template_only") is not True:
        failures.append({"check": "template_only", "expected": True, "actual": template_payload.get("template_only")})

    if template_payload.get("not_runtime_evidence") is not True:
        failures.append({"check": "template_not_runtime_evidence", "expected": True, "actual": template_payload.get("not_runtime_evidence")})

    valid_contract_result = validate_explicit_sml_record(_example_valid_record())
    invalid_contract_result = validate_explicit_sml_record(_example_invalid_proxy_record())

    if valid_contract_result.get("record_valid") is not True:
        failures.append({"check": "valid_example_contract", "expected": True, "actual": valid_contract_result.get("record_valid"), "details": valid_contract_result.get("failures")})

    if invalid_contract_result.get("record_valid") is not False:
        failures.append({"check": "invalid_proxy_example_rejected", "expected": False, "actual": invalid_contract_result.get("record_valid")})

    env_probe_result = load_explicit_sml_records_read_only(
        symbol="SPY",
        candidate_payload={},
        json_file_path=env_path if env_path_present else None,
        source_priority_policy=["read_only_json_file_explicit_sml_records"],
    )

    _check_adapter_guardrails(failures, "env_runtime_json_probe", env_probe_result)

    runtime_source_status = "REAL_RUNTIME_JSON_SOURCE_PRESENT_AND_PROBED_READ_ONLY" if env_path_exists else "REAL_RUNTIME_JSON_SOURCE_NOT_CONFIGURED_OR_NOT_AVAILABLE"

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
        "deployment_guide": {
            "path": str(GUIDE_PATH.relative_to(ROOT)),
            "exists": GUIDE_PATH.exists(),
            "required_phrase_count": len(REQUIRED_GUIDE_PHRASES),
            "missing_required_phrases": missing_phrases,
        },
        "template_status": {
            "path": str(TEMPLATE_PATH.relative_to(ROOT)),
            "exists": TEMPLATE_PATH.exists(),
            "template_only": template_payload.get("template_only"),
            "not_runtime_evidence": template_payload.get("not_runtime_evidence"),
        },
        "environment_status": {
            "SIGMALYTIC_EXPLICIT_SML_JSON_PATH_present": env_path_present,
            "SIGMALYTIC_EXPLICIT_SML_JSON_PATH_exists": env_path_exists,
            "environment_path_value_redacted": True,
            "runtime_source_status": runtime_source_status,
        },
        "env_probe_result": {
            "adapter_status": env_probe_result.get("adapter_status"),
            "source_quality": env_probe_result.get("source_quality"),
            "raw_record_count": env_probe_result.get("raw_record_count"),
            "symbol_filtered_record_count": env_probe_result.get("symbol_filtered_record_count"),
            "valid_record_count": env_probe_result.get("valid_record_count"),
            "invalid_record_count": env_probe_result.get("invalid_record_count"),
            "selected_source": env_probe_result.get("selected_source"),
            "warning_count": len(env_probe_result.get("warnings") or []),
        },
        "contract_examples": {
            "valid_example_record_valid": valid_contract_result.get("record_valid"),
            "invalid_proxy_example_record_valid": invalid_contract_result.get("record_valid"),
        },
        "runtime_evidence_conclusion": {
            "src7j_created_runtime_evidence": False,
            "real_runtime_json_source_confirmed": env_path_exists and int(env_probe_result.get("valid_record_count") or 0) > 0,
            "d3d_execution_authorized": False,
            "production_mutation_authorized": False,
            "operator_control_confirmed": False,
        },
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7j_status": "PASS_SRC7J_RUNTIME_JSON_SOURCE_DEPLOYMENT_GUIDE" if len(failures) == 0 else "FAIL_SRC7J_RUNTIME_JSON_SOURCE_DEPLOYMENT_GUIDE",
            "next_action": "CONFIGURE_REAL_SIGMALYTIC_EXPLICIT_SML_JSON_PATH_THEN_PROCEED_TO_SRC7K_RUNTIME_ENVIRONMENT_READINESS_PROBE" if len(failures) == 0 else "STOP_UNTIL_SRC7J_FAILURES_RESOLVED",
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7j_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC7J creates and audits the runtime JSON source deployment guide. It does not create runtime evidence, does not mutate campaigns, does not confirm operator control, and does not authorize D3D.",
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7J runtime JSON source deployment guide failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7J runtime JSON source deployment guide created and audited; no runtime evidence was created; D3D remains blocked; configure real JSON source before SRC7K.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
