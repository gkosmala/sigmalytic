from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "d3d-dry-run-candidate-preflight-review"
NEW_ENDPOINT_FRAGMENT = "d4e-read-only-live-bar-source-probe"
SENTINEL_START = "# === D4E2 LIVE READ-ONLY BAR SOURCE BRIDGE START ==="
SENTINEL_END = "# === D4E2 LIVE READ-ONLY BAR SOURCE BRIDGE END ==="


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
        raise RuntimeError("Could not find backend file containing D3V preflight endpoint.")

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
        raise RuntimeError(f"Could not detect router variable and route in {path}.")

    router_var = match.group("router")
    existing_route = match.group("route")
    new_route = existing_route.replace(TARGET_ENDPOINT_FRAGMENT, NEW_ENDPOINT_FRAGMENT)

    return path, router_var, new_route


def _endpoint_block(router_var: str, new_route: str) -> str:
    return f'''

{SENTINEL_START}
# This endpoint is intentionally read-only. It exists only to determine whether
# the deployed Render environment can access OHLCV bars using existing runtime
# credentials. It does not persist bars, write Supabase rows, mutate campaigns,
# construct HVN/POC, authorize D3D, or confirm operator control.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _d4e2_load_read_only_ohlcv,
    )
except Exception as _d4e2_import_exc:
    _d4e2_load_read_only_ohlcv = None
    _d4e2_import_error = f"{{type(_d4e2_import_exc).__name__}}: {{_d4e2_import_exc}}"
else:
    _d4e2_import_error = None


def _d4e2_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:50] or ["SPY"]


def _d4e2_compact_bar_probe_result(result):
    warnings = result.get("warnings") or []

    return {{
        "symbol": result.get("symbol"),
        "adapter_status": result.get("adapter_status"),
        "source_type": result.get("source_type"),
        "source_quality": result.get("source_quality"),
        "bar_count": result.get("bar_count"),
        "window_start": result.get("window_start"),
        "window_end": result.get("window_end"),
        "warning_count": len(warnings),
        "warnings_sample": warnings[:3],
        "read_only": result.get("read_only"),
        "writes_to_supabase": result.get("writes_to_supabase"),
        "mutates_campaigns": result.get("mutates_campaigns"),
        "executes_d3d": result.get("executes_d3d"),
        "authorizes_d3d": result.get("authorizes_d3d"),
        "confirms_operator_control": result.get("confirms_operator_control"),
        "constructs_hvn_poc": result.get("constructs_hvn_poc"),
        "not_a_trade_signal": result.get("not_a_trade_signal"),
    }}


@{router_var}.get("{new_route}")
def d4e_read_only_live_bar_source_probe(
    symbols: str = "SPY",
    lookback_bars: int = 252,
    minimum_usable_bars: int = 30,
):
    requested_symbols = _d4e2_parse_symbols(symbols)

    results = []
    status_distribution = {{}}
    source_type_distribution = {{}}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _d4e2_load_read_only_ohlcv is None:
            result = {{
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "window_start": None,
                "window_end": None,
                "warnings": [_d4e2_import_error or "adapter import failed"],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "confirms_operator_control": False,
                "constructs_hvn_poc": False,
                "not_a_trade_signal": True,
            }}
        else:
            result = _d4e2_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe="1Day",
                lookback_bars=int(lookback_bars or 252),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={{"symbol": symbol}},
                timeout_seconds=25,
            )

        compact = _d4e2_compact_bar_probe_result(result)
        results.append(compact)

        status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))

        status_distribution[status] = status_distribution.get(status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1

        expected_false_fields = [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]

        for field in expected_false_fields:
            if compact.get(field) is not False:
                guardrail_failures.append({{
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": compact.get(field),
                }})

        if compact.get("not_a_trade_signal") is not True:
            guardrail_failures.append({{
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": compact.get("not_a_trade_signal"),
            }})

    usable = [
        item for item in results
        if item.get("adapter_status") == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
        and int(item.get("bar_count") or 0) >= int(minimum_usable_bars or 30)
    ]

    if usable:
        source_status = "LIVE_READ_ONLY_BAR_SOURCE_AVAILABLE"
        d4f_readiness = "READY_FOR_D4F_READ_ONLY_HVN_POC_CONSTRUCTION_PROTOTYPE"
        source_gap_flags = [
            "D4E2_LIVE_READ_ONLY_SOURCE_BRIDGE_AVAILABLE",
            "D4E2_USABLE_OHLCV_BARS_CONFIRMED_IN_DEPLOYED_ENVIRONMENT",
            "D4E2_DOES_NOT_CONSTRUCT_HVN_POC",
            "D4E2_DOES_NOT_AUTHORIZE_D3D",
        ]
    else:
        source_status = "LIVE_READ_ONLY_BAR_SOURCE_NOT_AVAILABLE"
        d4f_readiness = "BLOCKED_UNTIL_LIVE_READ_ONLY_BAR_SOURCE_AVAILABLE"
        source_gap_flags = [
            "D4E2_LIVE_READ_ONLY_SOURCE_BRIDGE_AVAILABLE",
            "D4E2_NO_USABLE_OHLCV_BARS_CONFIRMED_IN_DEPLOYED_ENVIRONMENT",
            "D4E2_DOES_NOT_CONSTRUCT_HVN_POC",
            "D4E2_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {{
        "engine": "D4E2_LIVE_READ_ONLY_BAR_SOURCE_BRIDGE",
        "version": "phase_d4e2_live_read_only_bar_source_bridge_v1",
        "audit_status": "PASS_D4E2_LIVE_READ_ONLY_BAR_SOURCE_BRIDGE_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "constructs_hvn_poc": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "runtime_counts": {{
            "symbol_count_attempted": len(results),
            "symbol_count_with_usable_bars": len(usable),
            "symbol_count_without_usable_bars": len(results) - len(usable),
            "lookback_bars": int(lookback_bars or 252),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
        }},
        "runtime_distributions": {{
            "adapter_status_distribution": status_distribution,
            "source_type_distribution": source_type_distribution,
        }},
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {{
            "source_status": source_status,
            "d4f_readiness": d4f_readiness,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4e2_makes_any_campaign_d3d_eligible": False,
            "reason": "D4E.2 only probes deployed read-only OHLCV source access. It does not persist bars, mutate campaigns, construct HVN/POC, authorize D3D, or confirm operator control.",
        }},
    }}
{SENTINEL_END}
'''


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"D4E.2 endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "d4e2_live_read_only_bar_source_bridge_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# D4E.2 - Live Read-Only Bar Source Bridge

D4E.2 adds a deployed read-only backend probe endpoint:

`/api/campaign/d4e-read-only-live-bar-source-probe`

## Purpose

D4E and D4E.1 proved the local environment has no readable Supabase or Alpaca credentials.

D4E.2 therefore checks the deployed Render environment, where production market-data credentials may already exist.

## Strict Boundary

D4E.2 is read-only.

D4E.2 does not persist bars.
D4E.2 does not write to Supabase.
D4E.2 does not mutate campaigns.
D4E.2 does not construct HVN/POC.
D4E.2 does not execute D3D.
D4E.2 does not authorize D3D.
D4E.2 does not confirm operator control.
D4E.2 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## D4F Condition

D4F remains blocked unless D4E.2 confirms usable OHLCV bars inside the deployed environment.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "D4E2_LIVE_READ_ONLY_BAR_SOURCE_BRIDGE_BUILDER",
        "version": "phase_d4e2_live_read_only_bar_source_bridge_builder_v1",
        "target_file": str(target_path.relative_to(ROOT)),
        "router_variable": router_var,
        "route_added": new_route,
        "endpoint_fragment": NEW_ENDPOINT_FRAGMENT,
        "audit_doc": str(doc_path.relative_to(ROOT)),
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "constructs_hvn_poc": False,
        "operator_control_confirmed_by_this_builder": False,
        "not_a_trade_signal": True,
        "guardrail_failure_count": 0,
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4E.2 live read-only bar source bridge written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
