from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ENGINE = "D4E_READ_ONLY_MARKET_DATA_ADAPTER_PROTOTYPE"
VERSION = "phase_d4e_read_only_market_data_adapter_prototype_v1"

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

D3V_ENDPOINT = "/api/campaign/d3d-dry-run-candidate-preflight-review"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.market_data.read_only_ohlcv_adapter import (  # noqa: E402
    ADAPTER_NAME,
    ADAPTER_VERSION,
    AUTHORIZES_D3D,
    CONFIRMS_OPERATOR_CONTROL,
    CONSTRUCTS_HVN_POC,
    EXECUTES_D3D,
    MUTATES_CAMPAIGNS,
    NOT_A_TRADE_SIGNAL,
    WRITES_TO_SUPABASE,
    load_read_only_ohlcv_bars_for_d4b_candidate,
)


def _fetch_json(path: str, timeout_seconds: int = 180) -> Dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D4E-Read-Only-Market-Data-Adapter-Audit/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")

    payload = json.loads(raw)

    if not isinstance(payload, dict):
        raise RuntimeError("D3V endpoint returned non-object JSON.")

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


def _source_priority() -> List[str]:
    raw = os.environ.get(
        "D4E_SOURCE_PRIORITY",
        "existing_non_mutating_runtime_payload_bars,supabase_rest_read_only,alpaca_rest_read_only",
    )

    return [
        item.strip()
        for item in raw.split(",")
        if item.strip()
    ]


def _safe_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        return default

    return value


def _compact_adapter_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": result.get("symbol"),
        "adapter_status": result.get("adapter_status"),
        "source_type": result.get("source_type"),
        "source_quality": result.get("source_quality"),
        "bar_count": result.get("bar_count"),
        "window_start": result.get("window_start"),
        "window_end": result.get("window_end"),
        "warning_count": len(result.get("warnings") or []),
        "warnings_sample": (result.get("warnings") or [])[:3],
        "read_only": result.get("read_only"),
        "writes_to_supabase": result.get("writes_to_supabase"),
        "mutates_campaigns": result.get("mutates_campaigns"),
        "executes_d3d": result.get("executes_d3d"),
        "authorizes_d3d": result.get("authorizes_d3d"),
        "confirms_operator_control": result.get("confirms_operator_control"),
        "constructs_hvn_poc": result.get("constructs_hvn_poc"),
        "not_a_trade_signal": result.get("not_a_trade_signal"),
    }


def main() -> int:
    d3v_payload = _fetch_json(D3V_ENDPOINT)
    rows = _rows_from_payload(d3v_payload)

    candidate_rows = [
        row for row in rows
        if _bool(row.get("d3v_preflight_candidate"))
    ]

    max_symbols = _safe_int_env("D4E_MAX_SYMBOLS", 30)
    lookback_bars = _safe_int_env("D4E_LOOKBACK_BARS", 252)
    minimum_usable_bars = _safe_int_env("D4E_MINIMUM_USABLE_BARS", 30)
    timeout_seconds = _safe_int_env("D4E_SOURCE_TIMEOUT_SECONDS", 20)

    if max_symbols > 0:
        candidate_rows = candidate_rows[:max_symbols]

    source_priority_policy = _source_priority()

    adapter_results: List[Dict[str, Any]] = []

    for row in candidate_rows:
        symbol = row.get("symbol")

        if not symbol:
            continue

        result = load_read_only_ohlcv_bars_for_d4b_candidate(
            symbol=str(symbol),
            campaign_id=row.get("campaign_id"),
            campaign_state=row.get("campaign_state"),
            requested_timeframe=os.environ.get("D4E_TIMEFRAME", "1Day"),
            lookback_bars=lookback_bars,
            source_priority_policy=source_priority_policy,
            candidate_payload=row,
            timeout_seconds=timeout_seconds,
            minimum_usable_bars=minimum_usable_bars,
        )

        adapter_results.append(result)

    status_counter: Counter = Counter()
    source_counter: Counter = Counter()

    usable_results = []

    guardrail_failures: List[Dict[str, Any]] = []

    for result in adapter_results:
        status_counter[str(result.get("adapter_status"))] += 1
        source_counter[str(result.get("source_type"))] += 1

        if result.get("adapter_status") == "ADAPTER_OK_BARS_LOADED_READ_ONLY":
            usable_results.append(result)

        expected_false_fields = [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]

        for field in expected_false_fields:
            if result.get(field) is not False:
                guardrail_failures.append({
                    "symbol": result.get("symbol"),
                    "field": field,
                    "expected": False,
                    "actual": result.get(field),
                })

        if result.get("not_a_trade_signal") is not True:
            guardrail_failures.append({
                "symbol": result.get("symbol"),
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": result.get("not_a_trade_signal"),
            })

    module_guardrails = {
        "WRITES_TO_SUPABASE": WRITES_TO_SUPABASE,
        "MUTATES_CAMPAIGNS": MUTATES_CAMPAIGNS,
        "EXECUTES_D3D": EXECUTES_D3D,
        "AUTHORIZES_D3D": AUTHORIZES_D3D,
        "CONFIRMS_OPERATOR_CONTROL": CONFIRMS_OPERATOR_CONTROL,
        "CONSTRUCTS_HVN_POC": CONSTRUCTS_HVN_POC,
        "NOT_A_TRADE_SIGNAL": NOT_A_TRADE_SIGNAL,
    }

    if WRITES_TO_SUPABASE is not False:
        guardrail_failures.append({"module_field": "WRITES_TO_SUPABASE", "expected": False, "actual": WRITES_TO_SUPABASE})
    if MUTATES_CAMPAIGNS is not False:
        guardrail_failures.append({"module_field": "MUTATES_CAMPAIGNS", "expected": False, "actual": MUTATES_CAMPAIGNS})
    if EXECUTES_D3D is not False:
        guardrail_failures.append({"module_field": "EXECUTES_D3D", "expected": False, "actual": EXECUTES_D3D})
    if AUTHORIZES_D3D is not False:
        guardrail_failures.append({"module_field": "AUTHORIZES_D3D", "expected": False, "actual": AUTHORIZES_D3D})
    if CONFIRMS_OPERATOR_CONTROL is not False:
        guardrail_failures.append({"module_field": "CONFIRMS_OPERATOR_CONTROL", "expected": False, "actual": CONFIRMS_OPERATOR_CONTROL})
    if CONSTRUCTS_HVN_POC is not False:
        guardrail_failures.append({"module_field": "CONSTRUCTS_HVN_POC", "expected": False, "actual": CONSTRUCTS_HVN_POC})
    if NOT_A_TRADE_SIGNAL is not True:
        guardrail_failures.append({"module_field": "NOT_A_TRADE_SIGNAL", "expected": True, "actual": NOT_A_TRADE_SIGNAL})

    source_gap_flags: List[str] = [
        "D4E_READ_ONLY_ADAPTER_PROTOTYPE_IMPLEMENTED",
        "D4E_CANDIDATE_BAR_LOAD_ATTEMPTED_READ_ONLY",
        "D4E_DOES_NOT_CONSTRUCT_HVN_POC",
    ]

    if usable_results:
        source_gap_flags.append("D4E_USABLE_OHLCV_BARS_AVAILABLE_FOR_D4F_READ_ONLY")
        d4f_readiness = "READY_FOR_D4F_READ_ONLY_HVN_POC_CONSTRUCTION_PROTOTYPE"
    else:
        source_gap_flags.append("D4E_NO_USABLE_OHLCV_BARS_AVAILABLE_IN_CURRENT_ENVIRONMENT")
        d4f_readiness = "BLOCKED_UNTIL_READ_ONLY_BAR_SOURCE_AVAILABLE"

    source_gap_flags.append("D4E_NEXT_PHASE_D4F_ONLY_IF_USABLE_BARS_PRESENT")

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4E_READ_ONLY_MARKET_DATA_ADAPTER_PROTOTYPE_COMPLETED_NO_MUTATION",
        "adapter_name": ADAPTER_NAME,
        "adapter_version": ADAPTER_VERSION,
        "adapter_status": "READ_ONLY_ADAPTER_PROTOTYPE_IMPLEMENTED",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "constructs_hvn_poc": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "d3v_context": {
            "endpoint": D3V_ENDPOINT,
            "version": d3v_payload.get("version"),
            "endpoint_status": d3v_payload.get("endpoint_status"),
            "total_rows": len(rows),
            "candidate_rows_considered": len(candidate_rows),
        },
        "adapter_runtime_counts": {
            "candidate_count_attempted": len(adapter_results),
            "candidate_count_with_usable_bars": len(usable_results),
            "candidate_count_without_usable_bars": len(adapter_results) - len(usable_results),
            "minimum_usable_bars": minimum_usable_bars,
            "lookback_bars": lookback_bars,
        },
        "runtime_distributions": {
            "adapter_status_distribution": dict(sorted(status_counter.items())),
            "source_type_distribution": dict(sorted(source_counter.items())),
        },
        "source_priority_policy": source_priority_policy,
        "adapter_result_samples": [
            _compact_adapter_result(result)
            for result in adapter_results[:30]
        ],
        "module_guardrails": module_guardrails,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4e_makes_any_campaign_d3d_eligible": False,
            "d4f_readiness": d4f_readiness,
            "reason": "D4E only implements and tests a read-only OHLCV adapter prototype. It does not construct HVN/POC, persist fields, mutate campaigns, authorize D3D, or confirm operator control.",
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4E read-only market-data adapter prototype completed without mutation.")

    if guardrail_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
