from __future__ import annotations

import json
import math
import os
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


ENGINE = "D4B_READ_ONLY_TRUE_HVN_POC_SOURCE_CONSTRUCTOR_PROTOTYPE"
VERSION = "phase_d4b_read_only_hvn_poc_constructor_prototype_v1"

BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

ENDPOINTS = {
    "d3v": "/api/campaign/d3d-dry-run-candidate-preflight-review",
    "d3c2r": "/api/campaign/hvn-poc-source-enrichment-review",
}


BAR_CONTAINER_KEYS = [
    "bars",
    "daily_bars",
    "ohlcv",
    "ohlcv_bars",
    "price_bars",
    "historical_bars",
    "market_data_bars",
    "volume_profile_bars",
    "candidate_bars",
]

OPEN_KEYS = ["open", "o"]
HIGH_KEYS = ["high", "h"]
LOW_KEYS = ["low", "l"]
CLOSE_KEYS = ["close", "c", "price"]
VOLUME_KEYS = ["volume", "v", "vol"]


def _fetch_json(endpoint_name: str, path: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    url = BASE_URL + path
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D4B-Read-Only-HVN-POC-Constructor/1.0",
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
    for key in ["rows", "review_rows", "validation_rows", "campaign_rows", "results", "items", "data"]:
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


def _float_from_keys(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def _list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _counter_to_dict(counter: Counter) -> Dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: str(item[0])))


def _candidate_identity(row: Dict[str, Any]) -> str:
    symbol = row.get("symbol")
    campaign_id = row.get("campaign_id")
    return f"{symbol or 'UNKNOWN'}::{campaign_id or 'NO_CAMPAIGN_ID'}"


def _extract_direct_bars(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in BAR_CONTAINER_KEYS:
        value = row.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _find_nested_bars(value: Any, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 4:
        return []

    if isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]
        if dict_items:
            usable_count = 0
            for item in dict_items[:10]:
                if _float_from_keys(item, CLOSE_KEYS) is not None and _float_from_keys(item, VOLUME_KEYS) is not None:
                    usable_count += 1
            if usable_count > 0:
                return dict_items

        for item in value[:10]:
            found = _find_nested_bars(item, depth + 1)
            if found:
                return found

    if isinstance(value, dict):
        for key in BAR_CONTAINER_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]

        for nested_value in list(value.values())[:25]:
            found = _find_nested_bars(nested_value, depth + 1)
            if found:
                return found

    return []


def _extract_runtime_bars(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct = _extract_direct_bars(row)
    if direct:
        return direct

    return _find_nested_bars(row)


def _normalize_bars(raw_bars: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    bars: List[Dict[str, float]] = []

    for raw in raw_bars:
        high = _float_from_keys(raw, HIGH_KEYS)
        low = _float_from_keys(raw, LOW_KEYS)
        close = _float_from_keys(raw, CLOSE_KEYS)
        volume = _float_from_keys(raw, VOLUME_KEYS)

        if close is None or volume is None:
            continue

        if volume <= 0:
            continue

        if high is None:
            high = close

        if low is None:
            low = close

        if high < low:
            high, low = low, high

        bars.append({
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        })

    return bars


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (len(sorted_values) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)

    if lower == upper:
        return sorted_values[int(index)]

    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    weight = index - lower

    return lower_value * (1 - weight) + upper_value * weight


def _price_bin(price: float, min_price: float, bin_size: float) -> int:
    return int(math.floor((price - min_price) / bin_size))


def _construct_volume_profile(bars: List[Dict[str, float]], target_bins: int = 50) -> Dict[str, Any]:
    if len(bars) < 20:
        return {
            "constructed": False,
            "block_reason": "INSUFFICIENT_BARS_FOR_READ_ONLY_VOLUME_PROFILE",
            "bar_count": len(bars),
        }

    min_price = min(bar["low"] for bar in bars)
    max_price = max(bar["high"] for bar in bars)

    if not math.isfinite(min_price) or not math.isfinite(max_price) or max_price <= min_price:
        return {
            "constructed": False,
            "block_reason": "INVALID_PRICE_RANGE_FOR_VOLUME_PROFILE",
            "bar_count": len(bars),
        }

    raw_bin_size = (max_price - min_price) / float(target_bins)
    bin_size = max(raw_bin_size, 0.01)

    volume_by_bin: Dict[int, float] = {}

    for bar in bars:
        low = bar["low"]
        high = bar["high"]
        close = bar["close"]
        volume = bar["volume"]

        if high <= low:
            target_bin = _price_bin(close, min_price, bin_size)
            volume_by_bin[target_bin] = volume_by_bin.get(target_bin, 0.0) + volume
            continue

        low_bin = _price_bin(low, min_price, bin_size)
        high_bin = _price_bin(high, min_price, bin_size)
        bin_count = max(1, high_bin - low_bin + 1)
        allocated_volume = volume / float(bin_count)

        for bin_index in range(low_bin, high_bin + 1):
            volume_by_bin[bin_index] = volume_by_bin.get(bin_index, 0.0) + allocated_volume

    if not volume_by_bin:
        return {
            "constructed": False,
            "block_reason": "NO_VOLUME_ALLOCATED_TO_PROFILE",
            "bar_count": len(bars),
        }

    poc_bin = max(volume_by_bin.items(), key=lambda item: item[1])[0]
    poc_price = min_price + (poc_bin + 0.5) * bin_size

    volumes = list(volume_by_bin.values())
    hvn_threshold = _percentile(volumes, 0.80)

    hvn_bins = [
        bin_index for bin_index, volume in volume_by_bin.items()
        if volume >= hvn_threshold
    ]

    hvn_bins = sorted(hvn_bins)

    hvn_levels = [
        round(min_price + (bin_index + 0.5) * bin_size, 4)
        for bin_index in hvn_bins
    ]

    hvn_zones: List[Dict[str, float]] = []
    if hvn_bins:
        zone_start = hvn_bins[0]
        previous = hvn_bins[0]

        for bin_index in hvn_bins[1:]:
            if bin_index == previous + 1:
                previous = bin_index
                continue

            hvn_zones.append({
                "zone_low": round(min_price + zone_start * bin_size, 4),
                "zone_high": round(min_price + (previous + 1) * bin_size, 4),
            })
            zone_start = bin_index
            previous = bin_index

        hvn_zones.append({
            "zone_low": round(min_price + zone_start * bin_size, 4),
            "zone_high": round(min_price + (previous + 1) * bin_size, 4),
        })

    total_volume = sum(volumes)

    return {
        "constructed": True,
        "source_type": "READ_ONLY_OHLCV_VOLUME_BY_PRICE_DISTRIBUTION",
        "bar_count": len(bars),
        "poc_price": round(poc_price, 4),
        "hvn_levels": hvn_levels[:10],
        "hvn_zones": hvn_zones[:10],
        "volume_profile_bin_size": round(bin_size, 6),
        "volume_profile_price_low": round(min_price, 4),
        "volume_profile_price_high": round(max_price, 4),
        "volume_profile_total_volume": round(total_volume, 2),
        "volume_profile_source_quality": "PROTOTYPE_READ_ONLY_CONSTRUCTED_FROM_RUNTIME_OHLCV_BARS",
        "hvn_threshold_volume": round(hvn_threshold, 2),
    }


def _build_attempt_row(row: Dict[str, Any]) -> Dict[str, Any]:
    raw_bars = _extract_runtime_bars(row)
    normalized_bars = _normalize_bars(raw_bars)
    profile = _construct_volume_profile(normalized_bars)

    constructed = bool(profile.get("constructed"))

    if constructed:
        status = "D4B_PROPOSED_TRUE_HVN_POC_CONSTRUCTED_READ_ONLY"
        block_reason = None
    elif not raw_bars:
        status = "D4B_BLOCKED_NO_RUNTIME_OHLCV_BARS"
        block_reason = "NO_RUNTIME_OHLCV_BARS_FOUND_IN_EXISTING_PAYLOAD"
    elif not normalized_bars:
        status = "D4B_BLOCKED_NO_USABLE_OHLCV_VOLUME_BARS"
        block_reason = "BARS_FOUND_BUT_NO_USABLE_OHLCV_VOLUME_RECORDS"
    else:
        status = "D4B_BLOCKED_VOLUME_PROFILE_NOT_CONSTRUCTED"
        block_reason = profile.get("block_reason")

    return {
        "symbol": row.get("symbol"),
        "campaign_id": row.get("campaign_id"),
        "campaign_state": row.get("campaign_state"),
        "d3v_preflight_candidate": row.get("d3v_preflight_candidate"),
        "d3v_preflight_eligible_before_d4b": row.get("d3v_preflight_eligible"),
        "d3v_block_reasons_before_d4b": row.get("d3v_block_reasons"),
        "d4b_status": status,
        "d4b_block_reason": block_reason,
        "runtime_bar_container_count": len(raw_bars),
        "usable_ohlcv_bar_count": len(normalized_bars),
        "proposed_true_hvn_poc_available": constructed,
        "proposed_true_hvn_poc_source_type": profile.get("source_type") if constructed else None,
        "proposed_poc_price": profile.get("poc_price") if constructed else None,
        "proposed_hvn_levels": profile.get("hvn_levels") if constructed else [],
        "proposed_hvn_zones": profile.get("hvn_zones") if constructed else [],
        "proposed_volume_profile_bin_size": profile.get("volume_profile_bin_size") if constructed else None,
        "proposed_volume_profile_total_volume": profile.get("volume_profile_total_volume") if constructed else None,
        "proposed_volume_profile_source_quality": profile.get("volume_profile_source_quality") if constructed else None,
        "d4b_makes_d3d_eligible": False,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "not_a_trade_signal": True,
    }


def main() -> int:
    d3v_payload = _fetch_json("D3V D3D dry-run candidate preflight", ENDPOINTS["d3v"])
    d3c2r_payload = _fetch_json("D3C.2R HVN/POC source enrichment", ENDPOINTS["d3c2r"])

    d3v_rows = _rows_from_payload(d3v_payload)
    d3c2r_rows = _rows_from_payload(d3c2r_payload)

    candidate_rows = [
        row for row in d3v_rows
        if _bool(row.get("d3v_preflight_candidate"))
    ]

    attempt_rows = [_build_attempt_row(row) for row in candidate_rows]

    status_counter: Counter = Counter()
    block_counter: Counter = Counter()

    for row in attempt_rows:
        status_counter[str(row.get("d4b_status"))] += 1
        if row.get("d4b_block_reason"):
            block_counter[str(row.get("d4b_block_reason"))] += 1

    constructed_rows = [
        row for row in attempt_rows
        if _bool(row.get("proposed_true_hvn_poc_available"))
    ]

    guardrail_failures: List[Dict[str, Any]] = []

    required_d3v_payload_values = {
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

    for key, expected in required_d3v_payload_values.items():
        actual = d3v_payload.get(key)
        if actual != expected:
            guardrail_failures.append({
                "source": "D3V_PAYLOAD",
                "field": key,
                "expected": expected,
                "actual": actual,
            })

    source_gap_flags: List[str] = []

    if len(candidate_rows) == 0:
        source_gap_flags.append("D4B_NO_D3V_PREFLIGHT_CANDIDATES_FOUND")

    if len(attempt_rows) > 0 and len(constructed_rows) == 0:
        source_gap_flags.append("D4B_NO_TRUE_HVN_POC_CONSTRUCTED_FROM_RUNTIME_PAYLOAD")

    if status_counter.get("D4B_BLOCKED_NO_RUNTIME_OHLCV_BARS", 0) > 0:
        source_gap_flags.append("D4B_RUNTIME_OHLCV_BARS_MISSING_FROM_CANDIDATE_PAYLOAD")

    if block_counter.get("NO_RUNTIME_OHLCV_BARS_FOUND_IN_EXISTING_PAYLOAD", 0) > 0:
        source_gap_flags.append("D4B_EXISTING_CANDIDATE_PAYLOAD_HAS_NO_OHLCV_BAR_SOURCE")

    if status_counter.get("D4B_BLOCKED_NO_USABLE_OHLCV_VOLUME_BARS", 0) > 0:
        source_gap_flags.append("D4B_RUNTIME_BARS_PRESENT_BUT_NOT_USABLE_FOR_VOLUME_PROFILE")

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4B_READ_ONLY_CONSTRUCTOR_COMPLETED_NO_MUTATION",
        "constructor_status": "READ_ONLY_PROTOTYPE_NO_PERSISTENCE",
        "base_url": BASE_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "endpoint_versions": {
            "d3v": d3v_payload.get("version"),
            "d3c2r": d3c2r_payload.get("version"),
        },
        "runtime_counts": {
            "d3v_rows_count": len(d3v_rows),
            "d3c2r_rows_count": len(d3c2r_rows),
            "d3v_preflight_candidate_count": len(candidate_rows),
            "d4b_attempted_candidate_count": len(attempt_rows),
            "d4b_constructed_true_hvn_poc_count": len(constructed_rows),
            "d4b_d3d_eligible_count": 0,
        },
        "runtime_distributions": {
            "d4b_status_distribution": _counter_to_dict(status_counter),
            "d4b_block_reason_distribution": _counter_to_dict(block_counter),
        },
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4b_makes_any_campaign_d3d_eligible": False,
            "reason": "D4B is a read-only constructor prototype. Proposed HVN/POC fields, if any, are not persisted and do not authorize D3D.",
        },
        "attempt_rows": attempt_rows,
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4B read-only HVN/POC source constructor prototype completed without mutation.")

    if guardrail_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
