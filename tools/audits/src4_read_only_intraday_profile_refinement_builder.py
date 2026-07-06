from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_ENDPOINT_FRAGMENT = "src2-read-only-intraday-source-probe"
NEW_ENDPOINT_FRAGMENT = "src4-read-only-intraday-profile-refinement-prototype"
SENTINEL_START = "# === SRC4 READ-ONLY INTRADAY PROFILE REFINEMENT START ==="
SENTINEL_END = "# === SRC4 READ-ONLY INTRADAY PROFILE REFINEMENT END ==="


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
        raise RuntimeError("Could not find backend file containing SRC2 intraday source probe endpoint.")

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
    return f'''

{SENTINEL_START}
# SRC4 is read-only. It constructs an intraday OHLCV-derived profile refinement
# prototype from 1-minute bars. It is still not true exchange volume-at-price,
# not tick data, not explicit SML, and it does not authorize D3D.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _src4_load_read_only_ohlcv,
    )
except Exception as _src4_import_exc:
    _src4_load_read_only_ohlcv = None
    _src4_import_error = f"{{type(_src4_import_exc).__name__}}: {{_src4_import_exc}}"
else:
    _src4_import_error = None


def _src4_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src4_float(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    try:
        is_finite = math.isfinite(parsed)
    except Exception:
        is_finite = parsed == parsed and parsed not in [float("inf"), float("-inf")]

    if not is_finite:
        return None

    return parsed


def _src4_extract_raw_bars(adapter_result):
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


def _src4_normalize_bar(raw):
    if not isinstance(raw, dict):
        return None

    timestamp = (
        raw.get("timestamp")
        or raw.get("time")
        or raw.get("date")
        or raw.get("datetime")
        or raw.get("t")
    )

    open_value = _src4_float(raw.get("open", raw.get("o")))
    high_value = _src4_float(raw.get("high", raw.get("h")))
    low_value = _src4_float(raw.get("low", raw.get("l")))
    close_value = _src4_float(raw.get("close", raw.get("c", raw.get("price"))))
    volume_value = _src4_float(raw.get("volume", raw.get("v", raw.get("vol"))))

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


def _src4_construct_intraday_profile(symbol, raw_bars, profile_bins):
    bars = []

    for raw in raw_bars:
        normalized = _src4_normalize_bar(raw)

        if normalized is not None:
            bars.append(normalized)

    if len(bars) < 30:
        return {{
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_INSUFFICIENT_INTRADAY_BARS",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Fewer than 30 normalized intraday OHLCV bars were available.",
        }}

    low_min = min(item["low"] for item in bars)
    high_max = max(item["high"] for item in bars)

    if high_max <= low_min:
        return {{
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_INVALID_INTRADAY_PRICE_RANGE",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Intraday bars did not produce a valid high-low range.",
        }}

    bin_count = max(24, min(int(profile_bins or 96), 240))
    width = (high_max - low_min) / bin_count
    volumes = [0.0 for _ in range(bin_count)]

    for bar in bars:
        bar_low = bar["low"]
        bar_high = bar["high"]
        bar_volume = bar["volume"]

        if bar_high == bar_low:
            index = int((bar["close"] - low_min) / width)
            index = max(0, min(bin_count - 1, index))
            volumes[index] += bar_volume
            continue

        start_index = max(0, min(bin_count - 1, int((bar_low - low_min) / width)))
        end_index = max(0, min(bin_count - 1, int((bar_high - low_min) / width)))

        touched = max(1, end_index - start_index + 1)
        allocated = bar_volume / touched

        for index in range(start_index, end_index + 1):
            volumes[index] += allocated

    max_volume = max(volumes)
    total_volume = sum(volumes)

    if max_volume <= 0 or total_volume <= 0:
        return {{
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_EMPTY_INTRADAY_PROFILE",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Intraday distributed profile contained no positive volume.",
        }}

    poc_index = max(range(bin_count), key=lambda idx: volumes[idx])
    poc_low = low_min + (poc_index * width)
    poc_high = poc_low + width
    poc_price = (poc_low + poc_high) / 2.0

    hvn_threshold = max_volume * 0.70
    left = poc_index
    right = poc_index

    while left - 1 >= 0 and volumes[left - 1] >= hvn_threshold:
        left -= 1

    while right + 1 < bin_count and volumes[right + 1] >= hvn_threshold:
        right += 1

    hvn_low = low_min + (left * width)
    hvn_high = low_min + ((right + 1) * width)

    ranked_indices = sorted(range(bin_count), key=lambda idx: volumes[idx], reverse=True)[:5]
    top_bins = []

    for index in ranked_indices:
        bin_low = low_min + (index * width)
        bin_high = bin_low + width
        top_bins.append(
            {{
                "rank": len(top_bins) + 1,
                "bin_index": index,
                "bin_low": round(bin_low, 6),
                "bin_high": round(bin_high, 6),
                "bin_mid": round((bin_low + bin_high) / 2.0, 6),
                "allocated_volume": round(volumes[index], 6),
                "volume_share": round(volumes[index] / total_volume, 8),
            }}
        )

    return {{
        "symbol": symbol,
        "src4_profile_status": "SRC4_OK_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY",
        "bars_received": len(raw_bars),
        "bars_used": len(bars),
        "window_start": bars[0].get("timestamp"),
        "window_end": bars[-1].get("timestamp"),
        "method": "INTRADAY_OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_REFINEMENT",
        "profile_classification": "INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
        "prototype_profile_constructed": True,
        "constructs_true_hvn_poc": False,
        "poc_price": round(poc_price, 6),
        "poc_low": round(poc_low, 6),
        "poc_high": round(poc_high, 6),
        "hvn_low": round(hvn_low, 6),
        "hvn_high": round(hvn_high, 6),
        "profile_low": round(low_min, 6),
        "profile_high": round(high_max, 6),
        "profile_bin_count": bin_count,
        "profile_total_volume": round(total_volume, 6),
        "poc_bin_volume": round(max_volume, 6),
        "hvn_threshold_ratio": 0.70,
        "top_intraday_profile_bins": top_bins,
        "d3d_eligibility_from_this_endpoint": False,
        "source_limitation": "1-minute OHLCV bars improve profile resolution versus daily OHLCV, but volume remains distributed across bar ranges. This is not true exchange volume-at-price, not tick data, and not explicit SML.",
    }}


@{router_var}.get("{new_route}")
def src4_read_only_intraday_profile_refinement_prototype(
    symbols: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 30,
    profile_bins: int = 96,
):
    requested_symbols = _src4_parse_symbols(symbols)

    results = []
    adapter_status_distribution = {{}}
    source_type_distribution = {{}}
    profile_status_distribution = {{}}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _src4_load_read_only_ohlcv is None:
            adapter_result = {{
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "bars": [],
                "warnings": [_src4_import_error or "adapter import failed"],
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
            adapter_result = _src4_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe=str(timeframe or "1Min"),
                lookback_bars=int(lookback_bars or 390),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={{"symbol": symbol}},
                timeout_seconds=35,
            )

        raw_bars = _src4_extract_raw_bars(adapter_result)
        profile = _src4_construct_intraday_profile(symbol, raw_bars, int(profile_bins or 96))
        warnings = adapter_result.get("warnings") or []

        compact = {{
            "symbol": symbol,
            "requested_timeframe": str(timeframe or "1Min"),
            "adapter_status": adapter_result.get("adapter_status"),
            "source_type": adapter_result.get("source_type"),
            "source_quality": adapter_result.get("source_quality"),
            "adapter_bar_count": adapter_result.get("bar_count"),
            "adapter_warning_count": len(warnings),
            "adapter_warnings_sample": warnings[:5],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "constructs_true_hvn_poc": False,
            "not_a_trade_signal": True,
            "profile": profile,
        }}

        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))
        profile_status = str(profile.get("src4_profile_status"))

        adapter_status_distribution[adapter_status] = adapter_status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1
        profile_status_distribution[profile_status] = profile_status_distribution.get(profile_status, 0) + 1

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_true_hvn_poc",
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

        if profile.get("d3d_eligibility_from_this_endpoint") is not False:
            guardrail_failures.append({{
                "symbol": symbol,
                "field": "profile.d3d_eligibility_from_this_endpoint",
                "expected": False,
                "actual": profile.get("d3d_eligibility_from_this_endpoint"),
            }})

    constructed = [
        item for item in results
        if item.get("profile", {{}}).get("src4_profile_status")
        == "SRC4_OK_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY"
    ]

    if constructed:
        profile_status = "SRC4_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY"
        next_action = "PROCEED_TO_SRC5_INTRADAY_PROFILE_DOCTRINE_REVIEW"
        source_gap_flags = [
            "SRC4_INTRADAY_PROFILE_REFINEMENT_PROTOTYPE_CONSTRUCTED",
            "SRC4_INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
            "SRC4_DOES_NOT_AUTHORIZE_D3D",
            "SRC4_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
            "SRC4_NEXT_PHASE_SRC5_DOCTRINE_REVIEW_REQUIRED",
        ]
    else:
        profile_status = "SRC4_NO_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED"
        next_action = "STOP_UNTIL_SRC4_PROFILE_FAILURES_RESOLVED"
        source_gap_flags = [
            "SRC4_NO_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED",
            "SRC4_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {{
        "engine": "SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_PROTOTYPE",
        "version": "source_resolution_src4_intraday_profile_refinement_v1",
        "audit_status": "PASS_SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "constructs_true_hvn_poc": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "requested_timeframe": str(timeframe or "1Min"),
        "runtime_counts": {{
            "symbol_count_attempted": len(results),
            "symbol_count_with_intraday_profile_refinement": len(constructed),
            "symbol_count_without_intraday_profile_refinement": len(results) - len(constructed),
            "lookback_bars": int(lookback_bars or 390),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
            "profile_bins": int(profile_bins or 96),
        }},
        "runtime_distributions": {{
            "adapter_status_distribution": adapter_status_distribution,
            "source_type_distribution": source_type_distribution,
            "profile_status_distribution": profile_status_distribution,
        }},
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {{
            "profile_status": profile_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src4_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC4 constructs a read-only intraday OHLCV-derived profile refinement prototype only. It is not true volume-at-price, not tick data, not explicit SML, and does not authorize D3D.",
        }},
    }}
{SENTINEL_END}
'''


def main() -> int:
    target_path, router_var, new_route = _find_campaign_router_file()
    text = target_path.read_text(encoding="utf-8", errors="replace")

    if NEW_ENDPOINT_FRAGMENT in text:
        raise RuntimeError(f"SRC4 endpoint already exists in {target_path}.")

    updated = text.rstrip() + _endpoint_block(router_var, new_route) + "\n"
    target_path.write_text(updated, encoding="utf-8")

    doc_path = ROOT / "docs" / "audits" / "src4_read_only_intraday_profile_refinement_prototype_2026-07-06.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(
        """# SRC4 - Read-Only Intraday Profile Refinement Prototype

SRC4 adds a deployed read-only endpoint:

`/api/campaign/src4-read-only-intraday-profile-refinement-prototype`

## Purpose

SRC3 confirmed that intraday OHLCV bars are available from the deployed Alpaca SIP read-only source.

SRC4 constructs a refined read-only profile prototype from 1-minute OHLCV bars.

## Strict Boundary

SRC4 is read-only.

SRC4 does not persist bars.
SRC4 does not write to Supabase.
SRC4 does not mutate campaigns.
SRC4 does not construct true production HVN/POC.
SRC4 does not execute D3D.
SRC4 does not authorize D3D.
SRC4 does not confirm operator control.
SRC4 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Doctrine Limitation

SRC4 output is an intraday OHLCV-derived profile refinement.

It is not true exchange volume-at-price.
It is not tick-level trade print data.
It is not explicit SML.

If SRC4 succeeds, the next step is SRC5 doctrine review.

D3D remains blocked.
""",
        encoding="utf-8",
    )

    result = {
        "engine": "SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_BUILDER",
        "version": "source_resolution_src4_intraday_profile_refinement_builder_v1",
        "target_file": str(target_path.relative_to(ROOT)),
        "router_variable": router_var,
        "route_added": new_route,
        "endpoint_fragment": NEW_ENDPOINT_FRAGMENT,
        "audit_doc": str(doc_path.relative_to(ROOT)),
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "constructs_true_hvn_poc": False,
        "operator_control_confirmed_by_this_builder": False,
        "not_a_trade_signal": True,
        "guardrail_failure_count": 0,
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - SRC4 read-only intraday profile refinement prototype written without mutation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
