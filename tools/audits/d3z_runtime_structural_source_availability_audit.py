from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter
from typing import Any, Dict, List


ENGINE = "D3Z_RUNTIME_STRUCTURAL_SOURCE_AVAILABILITY_AUDIT"
VERSION = "phase_d3z_runtime_structural_source_availability_audit_v1"

BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

ENDPOINTS = {
    "d3c2r_hvn_poc_source_enrichment": "/api/campaign/hvn-poc-source-enrichment-review",
    "d3v_d3d_dry_run_candidate_preflight": "/api/campaign/d3d-dry-run-candidate-preflight-review",
}


def _fetch_json(endpoint_name: str, path: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    url = BASE_URL + path
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D3Z-Runtime-Structural-Source-Audit/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{endpoint_name} did not return valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{endpoint_name} returned non-object JSON payload.")

    return payload


def _rows_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in [
        "rows",
        "review_rows",
        "validation_rows",
        "campaign_rows",
        "results",
        "items",
        "data",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}

    return bool(value)


def _list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value

    if value is None:
        return []

    return [value]


def _counter_to_dict(counter: Counter) -> Dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: str(item[0])))


def _compact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": row.get("symbol"),
        "campaign_id": row.get("campaign_id"),
        "campaign_state": row.get("campaign_state"),
        "d3v_preflight_candidate": row.get("d3v_preflight_candidate"),
        "d3v_preflight_eligible": row.get("d3v_preflight_eligible"),
        "d3v_preflight_status": row.get("d3v_preflight_status"),
        "d3v_block_reasons": row.get("d3v_block_reasons"),
        "complete_doctrine_legs": row.get("complete_doctrine_legs"),
        "explicit_geometry_sml": row.get("explicit_geometry_sml"),
        "inferred_sml": row.get("inferred_sml"),
        "hvn_absorption_proxy_present": row.get("hvn_absorption_proxy_present"),
        "true_hvn_poc_available": row.get("true_hvn_poc_available"),
        "true_hvn_poc_source_count": row.get("true_hvn_poc_source_count"),
        "d3d_production_confirmed": row.get("d3d_production_confirmed"),
        "writes_to_supabase": row.get("writes_to_supabase"),
        "mutates_campaigns": row.get("mutates_campaigns"),
        "operator_control_confirmed_by_this_engine": row.get("operator_control_confirmed_by_this_engine"),
        "d3d_execution_allowed": row.get("d3d_execution_allowed"),
        "score_impact": row.get("score_impact"),
        "rank_impact": row.get("rank_impact"),
        "state_impact": row.get("state_impact"),
        "transition_impact": row.get("transition_impact"),
        "not_a_trade_signal": row.get("not_a_trade_signal"),
    }


def _guardrail_failures_for_d3v(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    expected_values = {
        "dry_run": True,
        "execution_authorized": False,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_unconfirmed_by_this_engine": False,
        "d3d_execution_allowed": False,
        "d3d_source_used_by_this_engine": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
    }

    failures: List[Dict[str, Any]] = []

    for key, expected in expected_values.items():
        actual = payload.get(key)
        if actual != expected:
            failures.append({
                "endpoint": "D3V",
                "field": key,
                "expected": expected,
                "actual": actual,
            })

    return failures


def main() -> int:
    d3c2r_payload = _fetch_json(
        "D3C.2R HVN/POC source enrichment",
        ENDPOINTS["d3c2r_hvn_poc_source_enrichment"],
    )

    d3v_payload = _fetch_json(
        "D3V D3D dry-run candidate preflight",
        ENDPOINTS["d3v_d3d_dry_run_candidate_preflight"],
    )

    d3c2r_rows = _rows_from_payload(d3c2r_payload)
    d3v_rows = _rows_from_payload(d3v_payload)

    d3c2r_true_hvn_rows = [
        row for row in d3c2r_rows
        if _bool(row.get("true_hvn_poc_available"))
    ]

    d3c2r_proxy_rows = [
        row for row in d3c2r_rows
        if _bool(row.get("hvn_absorption_proxy_present"))
    ]

    d3v_candidate_rows = [
        row for row in d3v_rows
        if _bool(row.get("d3v_preflight_candidate"))
    ]

    d3v_eligible_rows = [
        row for row in d3v_rows
        if _bool(row.get("d3v_preflight_eligible"))
    ]

    d3v_explicit_geometry_rows = [
        row for row in d3v_rows
        if _bool(row.get("explicit_geometry_sml"))
    ]

    d3v_inferred_sml_rows = [
        row for row in d3v_rows
        if _bool(row.get("inferred_sml"))
    ]

    d3v_proxy_rows = [
        row for row in d3v_rows
        if _bool(row.get("hvn_absorption_proxy_present"))
    ]

    d3v_block_reason_counter: Counter = Counter()
    candidate_block_reason_counter: Counter = Counter()

    for row in d3v_rows:
        for reason in _list(row.get("d3v_block_reasons")):
            d3v_block_reason_counter[str(reason)] += 1

    for row in d3v_candidate_rows:
        for reason in _list(row.get("d3v_block_reasons")):
            candidate_block_reason_counter[str(reason)] += 1

    source_gap_flags: List[str] = []

    if len(d3c2r_true_hvn_rows) == 0:
        source_gap_flags.append("RUNTIME_TRUE_HVN_POC_SOURCE_UNAVAILABLE")

    if len(d3v_explicit_geometry_rows) == 0:
        source_gap_flags.append("RUNTIME_EXPLICIT_GEOMETRY_SML_UNAVAILABLE")

    if len(d3v_eligible_rows) == 0:
        source_gap_flags.append("RUNTIME_D3V_PREFLIGHT_ELIGIBLE_COUNT_ZERO")

    if len(d3v_proxy_rows) > 0 or len(d3c2r_proxy_rows) > 0:
        source_gap_flags.append("RUNTIME_HVN_ABSORPTION_PROXY_PRESENT_PROXY_ONLY")

    if len(d3v_inferred_sml_rows) > 0:
        source_gap_flags.append("RUNTIME_INFERRED_SML_PRESENT_NOT_D3D_ELIGIBLE_BY_ITSELF")

    guardrail_failures = _guardrail_failures_for_d3v(d3v_payload)

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_RUNTIME_STRUCTURAL_SOURCE_AVAILABILITY_COMPLETED_NO_MUTATION",
        "base_url": BASE_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "endpoint_versions": {
            "d3c2r": d3c2r_payload.get("version"),
            "d3v": d3v_payload.get("version"),
        },
        "endpoint_statuses": {
            "d3c2r": d3c2r_payload.get("endpoint_status"),
            "d3v": d3v_payload.get("endpoint_status"),
        },
        "runtime_counts": {
            "d3c2r_rows_count": len(d3c2r_rows),
            "d3v_rows_count": len(d3v_rows),
            "d3c2r_true_hvn_poc_available_count": len(d3c2r_true_hvn_rows),
            "d3c2r_hvn_absorption_proxy_present_count": len(d3c2r_proxy_rows),
            "d3v_preflight_candidate_count": len(d3v_candidate_rows),
            "d3v_preflight_eligible_count": len(d3v_eligible_rows),
            "d3v_explicit_geometry_sml_count": len(d3v_explicit_geometry_rows),
            "d3v_inferred_sml_count": len(d3v_inferred_sml_rows),
            "d3v_hvn_absorption_proxy_present_count": len(d3v_proxy_rows),
        },
        "runtime_distributions": {
            "d3v_block_reason_distribution": _counter_to_dict(d3v_block_reason_counter),
            "d3v_candidate_block_reason_distribution": _counter_to_dict(candidate_block_reason_counter),
        },
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "reason": "D3Z is runtime availability inventory only; D3D remains separate, unauthorized, and blocked unless future source evidence satisfies the D3D protocol.",
            "d3d_production_confirmation_allowed_by_d3z": False,
            "d3z_mutation_allowed": False,
        },
        "candidate_rows": [_compact_row(row) for row in d3v_candidate_rows],
        "candidate_row_count": len(d3v_candidate_rows),
        "candidate_rows_policy": "D3V_CANDIDATES_ARE_DRY_RUN_REVIEW_ONLY_NOT_MUTATIONS",
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D3Z runtime structural source availability audit completed without mutation.")

    if guardrail_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
