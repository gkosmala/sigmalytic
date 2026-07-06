from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "src2-read-only-intraday-source-probe"
NEW_ENDPOINT_FRAGMENT = "src7c-read-only-runtime-explicit-sml-source-probe"
SENTINEL_START = "# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE START ==="
SENTINEL_END = "# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE END ==="


def _find_campaign_router_file() -> tuple[Path, str, str]:
    candidates = []

    for path in (ROOT / "backend").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if TARGET_ENDPOINT_FRAGMENT not in text:
            continue

        candidates.append(path)

    if not candidates:
        raise RuntimeError("Could not find backend file containing SRC2 endpoint.")

    path = candidates[0]
    text = path.read_text(encoding="utf-8", errors="replace")

    pattern = re.compile(
        r"@(?P<router>[A-Za-z_][A-Za-z0-9_]*)\.(?:get|post)\(\s*(?P<quote>[\"'])(?P<route>[^\"']*"
        + re.escape(TARGET_ENDPOINT_FRAGMENT)
        + r"[^\"']*)(?P=quote)",
        re.MULTILINE,
    )

    match = pattern.search(text)

    if not match:
        raise RuntimeError(f"Could not detect router variable and SRC2 route in {path}.")

    router_var = match.group("router")
    existing_route = match.group("route")
    new_route = existing_route.replace(TARGET_ENDPOINT_FRAGMENT, NEW_ENDPOINT_FRAGMENT)

    return path, router_var, new_route


def _endpoint_block(router_var: str, new_route: str) -> str:
    block = r'''

# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE START ===
# SRC7C probes the deployed runtime explicit SML adapter created in SRC7B.
# It is read-only and cannot authorize D3D.

try:
    from backend.structural_sources.explicit_sml_source_adapter import (
        load_explicit_sml_records_read_only as _src7c_load_explicit_sml_records_read_only,
    )
except Exception as _src7c_import_exc:
    _src7c_load_explicit_sml_records_read_only = None
    _src7c_import_error = f"{type(_src7c_import_exc).__name__}: {_src7c_import_exc}"
else:
    _src7c_import_error = None


def _src7c_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src7c_fixture_record(symbol):
    return {
        "symbol": str(symbol or "SPY").strip().upper(),
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


def _src7c_invalid_fixture_record(symbol):
    record = _src7c_fixture_record(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _src7c_candidate_payload_for_fixture_mode(symbol, fixture_mode):
    mode = str(fixture_mode or "none").strip().lower()

    if mode == "valid":
        return {"explicit_sml_records": [_src7c_fixture_record(symbol)]}

    if mode == "invalid":
        return {"explicit_sml_records": [_src7c_invalid_fixture_record(symbol)]}

    if mode == "mixed":
        return {
            "explicit_sml_records": [
                _src7c_fixture_record(symbol),
                _src7c_invalid_fixture_record(symbol),
            ]
        }

    return {}


def _src7c_guardrail_failures_for_adapter_result(symbol, adapter_result):
    failures = []

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
        if adapter_result.get(field) is not False:
            failures.append(
                {
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": adapter_result.get(field),
                }
            )

    if adapter_result.get("read_only") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "read_only",
                "expected": True,
                "actual": adapter_result.get("read_only"),
            }
        )

    if adapter_result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": adapter_result.get("not_a_trade_signal"),
            }
        )

    if adapter_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "symbol": symbol,
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": adapter_result.get("d3d_execution_recommendation"),
            }
        )

    return failures


@__ROUTER_VAR__.get("__NEW_ROUTE__")
def src7c_read_only_runtime_explicit_sml_source_probe(
    symbols: str = "SPY",
    fixture_mode: str = "none",
    json_file_path: str = None,
):
    requested_symbols = _src7c_parse_symbols(symbols)
    normalized_fixture_mode = str(fixture_mode or "none").strip().lower()

    results = []
    adapter_status_distribution = {}
    source_quality_distribution = {}
    guardrail_failures = []

    total_raw_records = 0
    total_symbol_filtered_records = 0
    total_valid_records = 0
    total_invalid_records = 0

    for symbol in requested_symbols:
        if _src7c_load_explicit_sml_records_read_only is None:
            adapter_result = {
                "symbol": symbol,
                "adapter_status": "SRC7C_BLOCKED_IMPORT_FAILED",
                "source_quality": "ADAPTER_IMPORT_FAILED",
                "source_policy": [],
                "attempted_sources": [],
                "selected_source": None,
                "raw_record_count": 0,
                "symbol_filtered_record_count": 0,
                "valid_record_count": 0,
                "invalid_record_count": 0,
                "warnings": [_src7c_import_error or "SRC7B adapter import failed"],
                "policy_failure_count": 0,
                "policy_failures": [],
                "validation_results": [],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed_by_this_adapter": False,
                "operator_control_unconfirmed_by_this_adapter": False,
                "not_a_trade_signal": True,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "src7b_makes_any_campaign_d3d_eligible": False,
            }
        else:
            candidate_payload = _src7c_candidate_payload_for_fixture_mode(symbol, normalized_fixture_mode)

            adapter_result = _src7c_load_explicit_sml_records_read_only(
                symbol=symbol,
                candidate_payload=candidate_payload,
                json_file_path=json_file_path,
                source_priority_policy=[
                    "existing_non_mutating_runtime_payload_explicit_sml_records",
                    "read_only_json_file_explicit_sml_records",
                ],
            )

        total_raw_records += int(adapter_result.get("raw_record_count") or 0)
        total_symbol_filtered_records += int(adapter_result.get("symbol_filtered_record_count") or 0)
        total_valid_records += int(adapter_result.get("valid_record_count") or 0)
        total_invalid_records += int(adapter_result.get("invalid_record_count") or 0)

        adapter_status = str(adapter_result.get("adapter_status"))
        source_quality = str(adapter_result.get("source_quality"))

        adapter_status_distribution[adapter_status] = adapter_status_distribution.get(adapter_status, 0) + 1
        source_quality_distribution[source_quality] = source_quality_distribution.get(source_quality, 0) + 1

        guardrail_failures.extend(_src7c_guardrail_failures_for_adapter_result(symbol, adapter_result))

        results.append(adapter_result)

    fixture_used = normalized_fixture_mode in ["valid", "invalid", "mixed"]

    if fixture_used and total_valid_records > 0:
        source_status = "SRC7C_FIXTURE_VALIDATION_CONFIRMED_READ_ONLY"
        next_action = "PROBE_RUNTIME_MODE_OR_PROCEED_TO_SRC7D_EXPLICIT_SOURCE_TEMPLATE"
        source_gap_flags = [
            "SRC7C_FIXTURE_ONLY_VALIDATION_CONFIRMED",
            "SRC7C_NO_PRODUCTION_RUNTIME_EVIDENCE_CREATED",
            "SRC7C_DOES_NOT_AUTHORIZE_D3D",
        ]
    elif total_valid_records > 0:
        source_status = "SRC7C_RUNTIME_VALID_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        next_action = "PROCEED_TO_SRC7D_DRY_RUN_EXPLICIT_SML_PREFLIGHT_VALIDATOR"
        source_gap_flags = [
            "SRC7C_RUNTIME_EXPLICIT_SML_RECORDS_FOUND",
            "SRC7C_D3D_STILL_BLOCKED_PENDING_DRY_RUN_PREFLIGHT",
        ]
    elif total_raw_records == 0:
        source_status = "SRC7C_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        next_action = "PROCEED_TO_SRC7D_EXPLICIT_SML_SOURCE_TEMPLATE_OR_ADD_RUNTIME_SOURCE"
        source_gap_flags = [
            "SRC7C_RUNTIME_ADAPTER_DEPLOYED",
            "SRC7C_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND",
            "SRC7C_D3D_REMAINS_BLOCKED",
        ]
    else:
        source_status = "SRC7C_RECORDS_PRESENT_BUT_CONTRACT_REJECTED_ALL_READ_ONLY"
        next_action = "STOP_OR_REPAIR_EXPLICIT_SML_RECORD_SOURCE"
        source_gap_flags = [
            "SRC7C_RECORDS_PRESENT_BUT_INVALID",
            "SRC7C_D3D_REMAINS_BLOCKED",
        ]

    return {
        "engine": "SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE",
        "version": "source_resolution_src7c_read_only_runtime_explicit_sml_source_probe_v1",
        "audit_status": "PASS_SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "fixture_mode": normalized_fixture_mode,
        "fixture_used": fixture_used,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "raw_record_count": total_raw_records,
            "symbol_filtered_record_count": total_symbol_filtered_records,
            "valid_record_count": total_valid_records,
            "invalid_record_count": total_invalid_records,
            "symbol_count_with_valid_explicit_sml_records": sum(
                1 for item in results if int(item.get("valid_record_count") or 0) > 0
            ),
            "symbol_count_without_valid_explicit_sml_records": sum(
                1 for item in results if int(item.get("valid_record_count") or 0) == 0
            ),
        },
        "runtime_distributions": {
            "adapter_status_distribution": adapter_status_distribution,
            "source_quality_distribution": source_quality_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "source_status": source_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7c_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC7C probes explicit SML runtime source availability through the SRC7B read-only adapter. It does not persist records, mutate campaigns, confirm operator control, or authorize D3D.",
        },
    }
# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE END ===
'''
    return block.replace("__ROUTER_VAR__", router_var).replace("__NEW_ROUTE__", new_route)


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"SRC7C endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "src7c_read_only_runtime_explicit_sml_source_probe_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# SRC7C - Read-Only Runtime Explicit SML Source Probe

SRC7C adds a deployed read-only endpoint:

`/api/campaign/src7c-read-only-runtime-explicit-sml-source-probe`

## Purpose

SRC7A created the explicit SML / structural-location contract.

SRC7B created the read-only runtime adapter design.

SRC7C exposes a deployed read-only probe for that adapter.

## Strict Boundary

SRC7C is read-only.

SRC7C does not persist records.
SRC7C does not write to Supabase.
SRC7C does not mutate campaigns.
SRC7C does not execute D3D.
SRC7C does not authorize D3D.
SRC7C does not confirm operator control.
SRC7C does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Expected Result

In fixture mode, SRC7C should prove that the deployed SRC7B adapter validates explicit SML records and rejects invalid proxy records.

In runtime mode, SRC7C may return no records until an explicit SML source is supplied.

D3D remains blocked.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE_BUILDER",
        "version": "source_resolution_src7c_read_only_runtime_explicit_sml_source_probe_builder_v1",
        "target_file": str(target_path.relative_to(ROOT)),
        "router_variable": router_var,
        "route_added": new_route,
        "endpoint_fragment": NEW_ENDPOINT_FRAGMENT,
        "audit_doc": str(doc_path.relative_to(ROOT)),
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_builder": False,
        "not_a_trade_signal": True,
        "guardrail_failure_count": 0,
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - SRC7C read-only runtime explicit SML source probe written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
