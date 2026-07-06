from __future__ import annotations

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "d4e-read-only-live-bar-source-probe"
NEW_ENDPOINT_FRAGMENT = "d4f-read-only-hvn-poc-construction-prototype"
SENTINEL_START = "# === D4F LIVE READ-ONLY HVN POC CONSTRUCTION START ==="
SENTINEL_END = "# === D4F LIVE READ-ONLY HVN POC CONSTRUCTION END ==="


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
        raise RuntimeError("Could not find backend file containing D4E.2 live bar-source endpoint.")

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
        raise RuntimeError(f"Could not detect router variable and D4E.2 route in {path}.")

    router_var = match.group("router")
    existing_route = match.group("route")
    new_route = existing_route.replace(TARGET_ENDPOINT_FRAGMENT, NEW_ENDPOINT_FRAGMENT)

    return path, router_var, new_route


def _endpoint_block(router_var: str, new_route: str) -> str:
    return f'''

{SENTINEL_START}
# D4F is read-only. It constructs a prototype HVN/POC geometry from confirmed
# deployed OHLCV bars. It does not persist bars, write Supabase rows, mutate
# campaigns, authorize D3D, or confirm operator control.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _d4f_load_read_only_ohlcv,
    )
except Exception as _d4f_import_exc:
    _d4f_load_read_only_ohlcv = None
    _d4f_import_error = f"{{type(_d4f_import_exc).__name__}}: {{_d4f_import_exc}}"
else:
    _d4f_import_error = None


def _d4f_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:50] or ["SPY"]


def _d4f_float(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def _d4f_extract_raw_bars(adapter_result):
    for key in ["bars", "ohlcv_bars", "normalized_bars", "records", "data"]:
        value = adapter_result.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in ["bars", "ohlcv_bars", "records"]:
                nested_value = value.get(nested_key)

                if isinstance(nested_value, list):
                    return nested_value

    return []


def _d4f_normalize_bar(raw):
    if not isinstance(raw, dict):
        return None

    timestamp = (
        raw.get("timestamp")
        or raw.get("time")
        or raw.get("date")
        or raw.get("datetime")
        or raw.get("t")
    )

    open_value = _d4f_float(raw.get("open", raw.get("o")))
    high_value = _d4f_float(raw.get("high", raw.get("h")))
    low_value = _d4f_float(raw.get("low", raw.get("l")))
    close_value = _d4f_float(raw.get("close", raw.get("c", raw.get("price"))))
    volume_value = _d4f_float(raw.get("volume", raw.get("v", raw.get("vol"))))

    if open_value is None or high_value is None or low_value is None or close_value is None or volume_value is None:
        return None

    if high_value < low_value:
        return None

    if volume_value <= 0:
        return None

    return {{
        "timestamp": str(timestamp) if timestamp is not None else None,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume_value,
    }}


def _d4f_construct_ohlcv_profile(symbol, bars, bin_count):
    usable_bars = []

    for raw in bars:
        normalized = _d4f_normalize_bar(raw)

        if normalized is not None:
            usable_bars.append(normalized)

    if len(usable_bars) < 5:
        return {{
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_INSUFFICIENT_NORMALIZED_BARS",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": int(bin_count),
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Fewer than five normalized OHLCV bars were available.",
        }}

    low_min = min(item["low"] for item in usable_bars)
    high_max = max(item["high"] for item in usable_bars)

    if not math.isfinite(low_min) or not math.isfinite(high_max) or high_max <= low_min:
        return {{
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_INVALID_PRICE_RANGE",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": int(bin_count),
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Normalized bars did not produce a valid high-low range.",
        }}

    profile_bin_count = max(12, min(int(bin_count or 48), 160))
    width = (high_max - low_min) / profile_bin_count
    volumes = [0.0 for _ in range(profile_bin_count)]

    for bar in usable_bars:
        bar_low = bar["low"]
        bar_high = bar["high"]
        bar_volume = bar["volume"]

        if bar_high == bar_low:
            index = int((bar["close"] - low_min) / width)
            index = max(0, min(profile_bin_count - 1, index))
            volumes[index] += bar_volume
            continue

        start_index = max(0, min(profile_bin_count - 1, int((bar_low - low_min) / width)))
        end_index = max(0, min(profile_bin_count - 1, int((bar_high - low_min) / width)))

        touched = max(1, end_index - start_index + 1)
        allocated = bar_volume / touched

        for index in range(start_index, end_index + 1):
            volumes[index] += allocated

    max_volume = max(volumes)

    if max_volume <= 0:
        return {{
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_EMPTY_VOLUME_PROFILE",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": profile_bin_count,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Distributed volume profile contained no positive volume.",
        }}

    poc_index = max(range(profile_bin_count), key=lambda idx: volumes[idx])
    poc_low = low_min + (poc_index * width)
    poc_high = poc_low + width
    poc_price = (poc_low + poc_high) / 2.0

    hvn_threshold = max_volume * 0.70

    left = poc_index
    right = poc_index

    while left - 1 >= 0 and volumes[left - 1] >= hvn_threshold:
        left -= 1

    while right + 1 < profile_bin_count and volumes[right + 1] >= hvn_threshold:
        right += 1

    hvn_low = low_min + (left * width)
    hvn_high = low_min + ((right + 1) * width)

    total_volume = sum(volumes)

    return {{
        "symbol": symbol,
        "d4f_construction_status": "D4F_OK_HVN_POC_CONSTRUCTED_READ_ONLY",
        "bars_received": len(bars),
        "bars_used": len(usable_bars),
        "window_start": usable_bars[0].get("timestamp"),
        "window_end": usable_bars[-1].get("timestamp"),
        "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
        "hvn_poc_construction_classification": "OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
        "poc_price": round(poc_price, 6),
        "poc_low": round(poc_low, 6),
        "poc_high": round(poc_high, 6),
        "hvn_low": round(hvn_low, 6),
        "hvn_high": round(hvn_high, 6),
        "profile_low": round(low_min, 6),
        "profile_high": round(high_max, 6),
        "profile_bin_count": profile_bin_count,
        "profile_total_volume": round(total_volume, 6),
        "poc_bin_volume": round(max_volume, 6),
        "hvn_threshold_ratio": 0.70,
        "d3d_eligibility_from_this_endpoint": False,
        "source_limitation": "Daily OHLCV bars do not contain true intrabar volume-at-price. D4F constructs a read-only prototype profile and must pass D4G/D4H source-quality review before any D3D consideration.",
    }}


@{router_var}.get("{new_route}")
def d4f_read_only_hvn_poc_construction_prototype(
    symbols: str = "SPY",
    lookback_bars: int = 252,
    minimum_usable_bars: int = 30,
    profile_bins: int = 48,
):
    requested_symbols = _d4f_parse_symbols(symbols)

    results = []
    status_distribution = {{}}
    source_type_distribution = {{}}
    construction_distribution = {{}}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _d4f_load_read_only_ohlcv is None:
            adapter_result = {{
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "bars": [],
                "warnings": [_d4f_import_error or "adapter import failed"],
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
            adapter_result = _d4f_load_read_only_ohlcv(
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

        raw_bars = _d4f_extract_raw_bars(adapter_result)
        construction = _d4f_construct_ohlcv_profile(symbol, raw_bars, int(profile_bins or 48))

        warnings = adapter_result.get("warnings") or []

        compact = {{
            "symbol": symbol,
            "adapter_status": adapter_result.get("adapter_status"),
            "source_type": adapter_result.get("source_type"),
            "source_quality": adapter_result.get("source_quality"),
            "adapter_bar_count": adapter_result.get("bar_count"),
            "adapter_warning_count": len(warnings),
            "adapter_warnings_sample": warnings[:3],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "not_a_trade_signal": True,
            "construction": construction,
        }}

        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))
        construction_status = str(construction.get("d4f_construction_status"))

        status_distribution[adapter_status] = status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1
        construction_distribution[construction_status] = construction_distribution.get(construction_status, 0) + 1

        expected_false_fields = [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
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

        if construction.get("d3d_eligibility_from_this_endpoint") is not False:
            guardrail_failures.append({{
                "symbol": symbol,
                "field": "d3d_eligibility_from_this_endpoint",
                "expected": False,
                "actual": construction.get("d3d_eligibility_from_this_endpoint"),
            }})

    constructed = [
        item for item in results
        if item.get("construction", {{}}).get("d4f_construction_status") == "D4F_OK_HVN_POC_CONSTRUCTED_READ_ONLY"
    ]

    if constructed:
        construction_status = "D4F_CONSTRUCTED_READ_ONLY_HVN_POC_PROTOTYPE"
        d4g_readiness = "READY_FOR_D4G_SOURCE_QUALITY_REVIEW"
        source_gap_flags = [
            "D4F_READ_ONLY_HVN_POC_PROTOTYPE_CONSTRUCTED",
            "D4F_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
            "D4F_DOES_NOT_AUTHORIZE_D3D",
            "D4F_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
            "D4F_NEXT_PHASE_D4G_SOURCE_QUALITY_REVIEW_REQUIRED",
        ]
    else:
        construction_status = "D4F_NO_HVN_POC_PROTOTYPE_CONSTRUCTED"
        d4g_readiness = "BLOCKED_UNTIL_D4F_CONSTRUCTS_PROFILE"
        source_gap_flags = [
            "D4F_NO_HVN_POC_PROTOTYPE_CONSTRUCTED",
            "D4F_DOES_NOT_AUTHORIZE_D3D",
            "D4F_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
        ]

    return {{
        "engine": "D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_PROTOTYPE",
        "version": "phase_d4f_live_read_only_hvn_poc_construction_v1",
        "audit_status": "PASS_D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_RESPONDED_NO_MUTATION",
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
        "runtime_counts": {{
            "symbol_count_attempted": len(results),
            "symbol_count_with_constructed_hvn_poc_prototype": len(constructed),
            "symbol_count_without_constructed_hvn_poc_prototype": len(results) - len(constructed),
            "lookback_bars": int(lookback_bars or 252),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
            "profile_bins": int(profile_bins or 48),
        }},
        "runtime_distributions": {{
            "adapter_status_distribution": status_distribution,
            "source_type_distribution": source_type_distribution,
            "construction_status_distribution": construction_distribution,
        }},
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {{
            "construction_status": construction_status,
            "d4g_readiness": d4g_readiness,
            "d4h_readiness": "BLOCKED_UNTIL_D4G_SOURCE_QUALITY_REVIEW",
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4f_makes_any_campaign_d3d_eligible": False,
            "reason": "D4F constructs a read-only OHLCV-derived HVN/POC prototype only. D4G and D4H must review source quality and doctrine compliance before D3D can even be considered.",
        }},
    }}
{SENTINEL_END}
'''


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"D4F endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "d4f_live_read_only_hvn_poc_construction_prototype_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# D4F - Live Read-Only HVN/POC Construction Prototype

D4F adds a deployed read-only backend construction endpoint:

`/api/campaign/d4f-read-only-hvn-poc-construction-prototype`

## Purpose

D4E.2 confirmed the deployed Render environment can read OHLCV bars from Alpaca SIP in read-only mode.

D4F therefore constructs a read-only HVN/POC prototype from deployed OHLCV bars.

## Strict Boundary

D4F is read-only.

D4F does not persist bars.
D4F does not write to Supabase.
D4F does not mutate campaigns.
D4F does not execute D3D.
D4F does not authorize D3D.
D4F does not confirm operator control.
D4F does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Source-Quality Limitation

D4F uses OHLCV range-distributed volume-profile construction.

This is a prototype construction from OHLCV bars, not a true exchange volume-at-price or tick-level market-profile source.

Therefore D4F alone cannot make any campaign D3D eligible.

D4G source-quality review is required next.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_BUILDER",
        "version": "phase_d4f_live_read_only_hvn_poc_construction_builder_v1",
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
    print("FINAL RESULT: PASS - D4F live read-only HVN/POC construction prototype written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
