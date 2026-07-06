from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "d4e-read-only-live-bar-source-probe"
NEW_ENDPOINT_FRAGMENT = "src2-read-only-intraday-source-probe"
SENTINEL_START = "# === SRC2 READ-ONLY INTRADAY SOURCE PROBE START ==="
SENTINEL_END = "# === SRC2 READ-ONLY INTRADAY SOURCE PROBE END ==="


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
        raise RuntimeError("Could not find backend file containing D4E read-only source endpoint.")

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
        raise RuntimeError(f"Could not detect router variable and D4E route in {path}.")

    router_var = match.group("router")
    existing_route = match.group("route")
    new_route = existing_route.replace(TARGET_ENDPOINT_FRAGMENT, NEW_ENDPOINT_FRAGMENT)

    return path, router_var, new_route


def _endpoint_block(router_var: str, new_route: str) -> str:
    return f'''

{SENTINEL_START}
# SRC2 is a read-only source-resolution probe. It tests whether the deployed
# market-data adapter can load intraday OHLCV bars. Intraday OHLCV is still not
# true exchange volume-at-price and does not authorize D3D.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _src2_load_read_only_ohlcv,
    )
except Exception as _src2_import_exc:
    _src2_load_read_only_ohlcv = None
    _src2_import_error = f"{{type(_src2_import_exc).__name__}}: {{_src2_import_exc}}"
else:
    _src2_import_error = None


def _src2_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src2_normalize_timeframe(timeframe):
    raw = str(timeframe or "1Min").strip()

    aliases = {{
        "1": "1Min",
        "1m": "1Min",
        "1min": "1Min",
        "1minute": "1Min",
        "5": "5Min",
        "5m": "5Min",
        "5min": "5Min",
        "5minute": "5Min",
        "15": "15Min",
        "15m": "15Min",
        "15min": "15Min",
        "15minute": "15Min",
        "day": "1Day",
        "daily": "1Day",
        "1d": "1Day",
        "1day": "1Day",
    }}

    key = raw.lower().replace(" ", "").replace("_", "")

    return aliases.get(key, raw)


def _src2_compact_result(result):
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
        "warnings_sample": warnings[:5],
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
def src2_read_only_intraday_source_probe(
    symbols: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 30,
):
    requested_symbols = _src2_parse_symbols(symbols)
    requested_timeframe = _src2_normalize_timeframe(timeframe)

    results = []
    status_distribution = {{}}
    source_type_distribution = {{}}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _src2_load_read_only_ohlcv is None:
            result = {{
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "window_start": None,
                "window_end": None,
                "warnings": [_src2_import_error or "adapter import failed"],
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
            result = _src2_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe=requested_timeframe,
                lookback_bars=int(lookback_bars or 390),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={{"symbol": symbol}},
                timeout_seconds=30,
            )

        compact = _src2_compact_result(result)
        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))

        status_distribution[adapter_status] = status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]:
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

    if usable and requested_timeframe != "1Day":
        source_status = "SRC2_INTRADAY_OHLCV_SOURCE_AVAILABLE"
        next_action = "PROCEED_TO_SRC3_INTRADAY_PROFILE_SOURCE_QUALITY_REVIEW"
        source_gap_flags = [
            "SRC2_INTRADAY_OHLCV_CONFIRMED",
            "SRC2_INTRADAY_OHLCV_IS_NOT_TRUE_VOLUME_AT_PRICE",
            "SRC2_DOES_NOT_CONSTRUCT_HVN_POC",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
            "SRC2_NEXT_PHASE_SRC3_REQUIRED",
        ]
    elif usable:
        source_status = "SRC2_DAILY_OHLCV_ONLY_CONFIRMED"
        next_action = "STOP_SRC2_INTRADAY_SOURCE_NOT_CONFIRMED"
        source_gap_flags = [
            "SRC2_DAILY_OHLCV_AVAILABLE",
            "SRC2_INTRADAY_OHLCV_NOT_CONFIRMED",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
        ]
    else:
        source_status = "SRC2_NO_USABLE_INTRADAY_OHLCV_SOURCE_CONFIRMED"
        next_action = "STOP_SRC2_SOURCE_UNAVAILABLE_OR_CONFIGURE_PROVIDER"
        source_gap_flags = [
            "SRC2_NO_USABLE_INTRADAY_OHLCV_BARS",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {{
        "engine": "SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE",
        "version": "source_resolution_src2_read_only_intraday_source_probe_v1",
        "audit_status": "PASS_SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE_RESPONDED_NO_MUTATION",
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
        "requested_timeframe": requested_timeframe,
        "runtime_counts": {{
            "symbol_count_attempted": len(results),
            "symbol_count_with_usable_intraday_bars": len(usable) if requested_timeframe != "1Day" else 0,
            "symbol_count_with_usable_bars": len(usable),
            "symbol_count_without_usable_bars": len(results) - len(usable),
            "lookback_bars": int(lookback_bars or 390),
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
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src2_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC2 only probes intraday OHLCV availability. Intraday OHLCV is still not true exchange volume-at-price and does not authorize D3D.",
        }},
    }}
{SENTINEL_END}
'''


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"SRC2 endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "src2_read_only_intraday_source_probe_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# SRC2 - Read-Only Intraday Source Feasibility Probe

SRC2 adds a deployed read-only endpoint:

`/api/campaign/src2-read-only-intraday-source-probe`

## Purpose

SRC1 confirmed that the system has live read-only daily OHLCV access and a read-only OHLCV-derived D4F profile prototype, but no true D3D structural source.

SRC2 tests whether the deployed Alpaca SIP source can provide intraday OHLCV bars through the existing read-only adapter.

## Strict Boundary

SRC2 is read-only.

SRC2 does not persist bars.
SRC2 does not write to Supabase.
SRC2 does not mutate campaigns.
SRC2 does not construct HVN/POC.
SRC2 does not execute D3D.
SRC2 does not authorize D3D.
SRC2 does not confirm operator control.
SRC2 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Doctrine Limitation

Intraday OHLCV is not true exchange volume-at-price.

If SRC2 confirms intraday OHLCV availability, the next step is SRC3 source-quality review, not D3D.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE_BUILDER",
        "version": "source_resolution_src2_read_only_intraday_source_probe_builder_v1",
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
    print("FINAL RESULT: PASS - SRC2 read-only intraday source probe written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
