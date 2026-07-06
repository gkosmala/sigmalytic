from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "src7c-read-only-runtime-explicit-sml-source-probe"
NEW_ENDPOINT_FRAGMENT = "src7g-runtime-dry-run-preflight-endpoint"
SENTINEL_START = "# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT START ==="
SENTINEL_END = "# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT END ==="


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
        raise RuntimeError("Could not find backend file containing SRC7C endpoint.")

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
        raise RuntimeError(f"Could not detect router variable and SRC7C route in {path}.")

    router_var = match.group("router")
    existing_route = match.group("route")
    new_route = existing_route.replace(TARGET_ENDPOINT_FRAGMENT, NEW_ENDPOINT_FRAGMENT)

    return path, router_var, new_route


def _endpoint_block(router_var: str, new_route: str) -> str:
    block = r'''

# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT START ===
# SRC7G exposes the deployed dry-run, read-only, no-drift eligibility review.
# It can show source-only dry-run readiness, but it cannot authorize D3D.

try:
    from backend.structural_sources.explicit_sml_no_drift_eligibility_review import (
        run_no_drift_dry_run_eligibility_review as _src7g_run_no_drift_dry_run_eligibility_review,
    )
except Exception as _src7g_import_exc:
    _src7g_run_no_drift_dry_run_eligibility_review = None
    _src7g_import_error = f"{type(_src7g_import_exc).__name__}: {_src7g_import_exc}"
else:
    _src7g_import_error = None


def _src7g_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src7g_fixture_record(symbol):
    normalized_symbol = str(symbol or "SPY").strip().upper()

    return {
        "symbol": normalized_symbol,
        "campaign_id": f"fixture-{normalized_symbol.lower()}",
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


def _src7g_invalid_fixture_record(symbol):
    record = _src7g_fixture_record(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _src7g_candidate_payload_for_fixture_mode(symbol, fixture_mode):
    mode = str(fixture_mode or "none").strip().lower()

    if mode == "valid":
        return {"explicit_sml_records": [_src7g_fixture_record(symbol)]}

    if mode == "invalid":
        return {"explicit_sml_records": [_src7g_invalid_fixture_record(symbol)]}

    if mode == "mixed":
        return {
            "explicit_sml_records": [
                _src7g_fixture_record(symbol),
                _src7g_invalid_fixture_record(symbol),
            ]
        }

    return {}


def _src7g_guardrail_failures_for_result(symbol, result):
    failures = []

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
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": result.get(field),
                }
            )

    if result.get("read_only") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "read_only",
                "expected": True,
                "actual": result.get("read_only"),
            }
        )

    if result.get("dry_run") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "dry_run",
                "expected": True,
                "actual": result.get("dry_run"),
            }
        )

    if result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": result.get("not_a_trade_signal"),
            }
        )

    if result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "symbol": symbol,
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": result.get("d3d_execution_recommendation"),
            }
        )

    if int(result.get("guardrail_failure_count") or 0) != 0:
        failures.append(
            {
                "symbol": symbol,
                "field": "guardrail_failure_count",
                "expected": 0,
                "actual": result.get("guardrail_failure_count"),
            }
        )

    return failures


@__ROUTER_VAR__.get("__NEW_ROUTE__")
def src7g_runtime_dry_run_preflight_endpoint(
    symbols: str = "SPY",
    fixture_mode: str = "none",
    json_file_path: str = None,
):
    requested_symbols = _src7g_parse_symbols(symbols)
    normalized_fixture_mode = str(fixture_mode or "none").strip().lower()

    results = []
    guardrail_failures = []
    status_distribution = {}
    source_only_distribution = {}

    total_source_only_ready = 0
    total_production_eligible = 0

    for symbol in requested_symbols:
        if _src7g_run_no_drift_dry_run_eligibility_review is None:
            result = {
                "review": "SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW",
                "review_version": "source_resolution_src7f_no_drift_dry_run_eligibility_review_v1",
                "diagnostic_only": True,
                "dry_run": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed_by_this_review": False,
                "operator_control_unconfirmed_by_this_review": False,
                "not_a_trade_signal": True,
                "candidate": {
                    "symbol": symbol,
                    "campaign_id": f"runtime-probe-{symbol.lower()}",
                },
                "source_binding_requirement_satisfied": False,
                "no_drift_requirement_satisfied": False,
                "source_only_dry_run_eligibility_satisfied": False,
                "production_d3d_eligibility_satisfied": False,
                "d3d_execution_authorized": False,
                "production_mutation_authorized": False,
                "operator_control_confirmed": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "src7f_makes_any_campaign_d3d_eligible": False,
                "guardrail_failure_count": 0,
                "guardrail_failures": [],
                "runtime_decision": {
                    "src7f_status": "SRC7G_BLOCKED_IMPORT_FAILED",
                    "next_action": "STOP_UNTIL_SRC7F_IMPORT_REPAIRED",
                    "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                    "src7f_makes_any_campaign_d3d_eligible": False,
                    "reason": _src7g_import_error or "SRC7F import failed.",
                },
            }
        else:
            candidate = {
                "symbol": symbol,
                "campaign_id": f"runtime-probe-{symbol.lower()}",
            }
            candidate_payload = _src7g_candidate_payload_for_fixture_mode(symbol, normalized_fixture_mode)

            result = _src7g_run_no_drift_dry_run_eligibility_review(
                candidate=candidate,
                candidate_payload=candidate_payload,
                json_file_path=json_file_path,
                source_priority_policy=[
                    "existing_non_mutating_runtime_payload_explicit_sml_records",
                    "read_only_json_file_explicit_sml_records",
                ],
            )

        status = str((result.get("runtime_decision") or {}).get("src7f_status"))
        status_distribution[status] = status_distribution.get(status, 0) + 1

        source_only_value = str(result.get("source_only_dry_run_eligibility_satisfied"))
        source_only_distribution[source_only_value] = source_only_distribution.get(source_only_value, 0) + 1

        if result.get("source_only_dry_run_eligibility_satisfied") is True:
            total_source_only_ready += 1

        if result.get("production_d3d_eligibility_satisfied") is True:
            total_production_eligible += 1

        guardrail_failures.extend(_src7g_guardrail_failures_for_result(symbol, result))
        results.append(result)

    fixture_used = normalized_fixture_mode in ["valid", "invalid", "mixed"]

    if fixture_used and total_source_only_ready > 0:
        preflight_status = "SRC7G_FIXTURE_SOURCE_ONLY_DRY_RUN_PREFLIGHT_CONFIRMED"
        next_action = "PROBE_RUNTIME_MODE_OR_PROCEED_TO_SRC7H_RUNTIME_SOURCE_MATERIALIZATION_PLAN"
        source_gap_flags = [
            "SRC7G_FIXTURE_ONLY_SOURCE_READY",
            "SRC7G_NO_PRODUCTION_RUNTIME_EVIDENCE_CREATED",
            "SRC7G_PRODUCTION_D3D_ELIGIBILITY_FALSE",
            "SRC7G_D3D_REMAINS_BLOCKED",
        ]
    elif total_source_only_ready > 0:
        preflight_status = "SRC7G_RUNTIME_SOURCE_ONLY_DRY_RUN_PREFLIGHT_READY"
        next_action = "PROCEED_TO_SRC7H_PRODUCTION_BLOCK_REVIEW_BEFORE_ANY_D3D"
        source_gap_flags = [
            "SRC7G_RUNTIME_SOURCE_ONLY_READY",
            "SRC7G_PRODUCTION_D3D_ELIGIBILITY_FALSE",
            "SRC7G_D3D_REMAINS_BLOCKED_PENDING_FINAL_DOCTRINE_REVIEW",
        ]
    else:
        preflight_status = "SRC7G_NO_RUNTIME_SOURCE_ONLY_DRY_RUN_PREFLIGHT_READY"
        next_action = "PROCEED_TO_SRC7H_RUNTIME_EXPLICIT_SML_SOURCE_MATERIALIZATION_PLAN"
        source_gap_flags = [
            "SRC7G_ENDPOINT_DEPLOYED",
            "SRC7G_NO_RUNTIME_EXPLICIT_SML_SOURCE_READY",
            "SRC7G_D3D_REMAINS_BLOCKED",
        ]

    return {
        "engine": "SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT",
        "version": "source_resolution_src7g_runtime_dry_run_preflight_endpoint_v1",
        "audit_status": "PASS_SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "dry_run": True,
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
            "symbol_count_source_only_dry_run_ready": total_source_only_ready,
            "symbol_count_source_only_dry_run_not_ready": len(results) - total_source_only_ready,
            "symbol_count_production_d3d_eligible": total_production_eligible,
        },
        "runtime_distributions": {
            "src7f_status_distribution": status_distribution,
            "source_only_dry_run_eligibility_distribution": source_only_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "preflight_status": preflight_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7g_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC7G exposes runtime dry-run source-only preflight readiness. It does not persist, mutate, confirm operator control, or authorize D3D.",
        },
    }
# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT END ===
'''
    return block.replace("__ROUTER_VAR__", router_var).replace("__NEW_ROUTE__", new_route)


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"SRC7G endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "src7g_runtime_dry_run_preflight_endpoint_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# SRC7G - Runtime Dry-Run Preflight Endpoint

SRC7G adds a deployed read-only dry-run endpoint:

`/api/campaign/src7g-runtime-dry-run-preflight-endpoint`

## Purpose

SRC7G exposes the SRC7F no-drift dry-run eligibility review through the deployed backend.

It can prove that source-only dry-run readiness is possible when valid explicit SML evidence is supplied.

## Strict Boundary

SRC7G is read-only and dry-run only.

SRC7G does not persist records.
SRC7G does not write to Supabase.
SRC7G does not mutate campaigns.
SRC7G does not execute D3D.
SRC7G does not authorize D3D.
SRC7G does not confirm operator control.
SRC7G does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Important Limitation

Fixture-mode success is not runtime production evidence.

Runtime mode may still return no explicit SML records until a real explicit structural-location source is supplied.

D3D remains blocked.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT_BUILDER",
        "version": "source_resolution_src7g_runtime_dry_run_preflight_endpoint_builder_v1",
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
    print("FINAL RESULT: PASS - SRC7G runtime dry-run preflight endpoint written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
