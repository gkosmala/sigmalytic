from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
from backend.alerts.read_only_alert_fusion import (
    Bar,
    ExplicitStructuralSource,
    GUARDRAILS,
    assert_no_drift_guardrails,
    run_read_only_alert_review,
)
try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate,
    )
except Exception as exc:
    load_read_only_ohlcv_bars_for_d4b_candidate = None
    OHLCV_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    OHLCV_IMPORT_ERROR = None
try:
    from backend.structural_sources.explicit_sml_source_adapter import (
        load_explicit_sml_records_read_only,
    )
except Exception as exc:
    load_explicit_sml_records_read_only = None
    EXPLICIT_SOURCE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
else:
    EXPLICIT_SOURCE_IMPORT_ERROR = None
COMPONENT = "ALERT_LIVE_DATA_ADAPTER_READ_ONLY"
VERSION = "alert_live_data_adapter_read_only_v1"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPLICIT_SML_JSON_PATH = ROOT / "runtime_sources" / "explicit_sml_runtime_source.json"
LIVE_ADAPTER_GUARDRAILS = {
    **GUARDRAILS,
    "component": COMPONENT,
    "version": VERSION,
    "loads_live_bars_read_only": True,
    "loads_explicit_source_read_only": True,
    "writes_to_supabase": False,
    "mutates_campaigns": False,
    "executes_d3d": False,
    "authorizes_d3d": False,
    "operator_control_confirmed": False,
    "not_a_trade_signal": True,
    "changes_scores": False,
    "changes_ranks": False,
    "changes_states": False,
    "changes_probabilities": False,
    "changes_edge": False,
    "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
}
def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed
def _convert_ohlcv_bars(raw_bars: Any) -> list[Bar]:
    if not isinstance(raw_bars, list):
        return []
    converted: list[Bar] = []
    for item in raw_bars:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp_utc") or item.get("timestamp") or item.get("time") or item.get("t")
        open_price = _safe_float(item.get("open") if "open" in item else item.get("o"))
        high_price = _safe_float(item.get("high") if "high" in item else item.get("h"))
        low_price = _safe_float(item.get("low") if "low" in item else item.get("l"))
        close_price = _safe_float(item.get("close") if "close" in item else item.get("c"))
        volume = _safe_float(item.get("volume") if "volume" in item else item.get("v"))
        if not timestamp:
            continue
        if open_price is None or high_price is None or low_price is None or close_price is None or volume is None:
            continue
        if high_price < low_price:
            continue
        if volume <= 0:
            continue
        converted.append(
            Bar(
                timestamp_utc=str(timestamp),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
    return converted
def _selected_explicit_source(source_result: dict[str, Any]) -> Optional[ExplicitStructuralSource]:
    if not isinstance(source_result, dict):
        return None
    for validation in source_result.get("validation_results") or []:
        if not isinstance(validation, dict):
            continue
        if validation.get("record_valid") is not True:
            continue
        normalized = validation.get("normalized_record") or {}
        price_low = _safe_float(normalized.get("price_low"))
        price_mid = _safe_float(normalized.get("price_mid"))
        price_high = _safe_float(normalized.get("price_high"))
        if price_low is None or price_mid is None or price_high is None:
            continue
        return ExplicitStructuralSource(
            symbol=str(normalized.get("symbol") or source_result.get("symbol") or "").upper(),
            level_type=str(normalized.get("level_type") or ""),
            price_low=price_low,
            price_mid=price_mid,
            price_high=price_high,
            source_method=str(normalized.get("source_method") or ""),
            source_reference=str(normalized.get("source_reference") or ""),
            is_explicit=bool(normalized.get("is_explicit") is True),
            is_inferred=False,
            is_proxy=False,
        )
    return None
def _compact_bar_result(bar_result: dict[str, Any]) -> dict[str, Any]:
    warnings = bar_result.get("warnings") or []
    return {
        "adapter_status": bar_result.get("adapter_status"),
        "source_type": bar_result.get("source_type"),
        "source_quality": bar_result.get("source_quality"),
        "timeframe": bar_result.get("timeframe"),
        "bar_count": bar_result.get("bar_count"),
        "window_start": bar_result.get("window_start"),
        "window_end": bar_result.get("window_end"),
        "warning_count": len(warnings),
        "warnings_sample": warnings[:5],
        "read_only": bar_result.get("read_only"),
        "writes_to_supabase": bar_result.get("writes_to_supabase"),
        "mutates_campaigns": bar_result.get("mutates_campaigns"),
        "executes_d3d": bar_result.get("executes_d3d"),
        "authorizes_d3d": bar_result.get("authorizes_d3d"),
        "confirms_operator_control": bar_result.get("confirms_operator_control"),
        "constructs_hvn_poc": bar_result.get("constructs_hvn_poc"),
        "not_a_trade_signal": bar_result.get("not_a_trade_signal"),
    }
def _compact_source_result(source_result: dict[str, Any]) -> dict[str, Any]:
    warnings = source_result.get("warnings") or []
    return {
        "adapter_status": source_result.get("adapter_status"),
        "source_quality": source_result.get("source_quality"),
        "selected_source": source_result.get("selected_source"),
        "raw_record_count": source_result.get("raw_record_count"),
        "symbol_filtered_record_count": source_result.get("symbol_filtered_record_count"),
        "valid_record_count": source_result.get("valid_record_count"),
        "invalid_record_count": source_result.get("invalid_record_count"),
        "warning_count": len(warnings),
        "warnings_sample": warnings[:5],
        "policy_failure_count": source_result.get("policy_failure_count"),
        "read_only": source_result.get("read_only"),
        "writes_to_supabase": source_result.get("writes_to_supabase"),
        "mutates_campaigns": source_result.get("mutates_campaigns"),
        "executes_d3d": source_result.get("executes_d3d"),
        "authorizes_d3d": source_result.get("authorizes_d3d"),
        "operator_control_confirmed_by_this_adapter": source_result.get("operator_control_confirmed_by_this_adapter"),
        "not_a_trade_signal": source_result.get("not_a_trade_signal"),
        "d3d_execution_recommendation": source_result.get("d3d_execution_recommendation"),
    }
def _guardrail_failures(*, bar_result: dict[str, Any], source_result: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for label, result in [
        ("bar_adapter", bar_result),
        ("explicit_source_adapter", source_result),
    ]:
        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
        ]:
            if result.get(field) is not False:
                failures.append(
                    {
                        "adapter": label,
                        "field": field,
                        "expected": False,
                        "actual": result.get(field),
                    }
                )
        if result.get("not_a_trade_signal") is not True:
            failures.append(
                {
                    "adapter": label,
                    "field": "not_a_trade_signal",
                    "expected": True,
                    "actual": result.get("not_a_trade_signal"),
                }
            )
    if bar_result.get("confirms_operator_control") is not False:
        failures.append(
            {
                "adapter": "bar_adapter",
                "field": "confirms_operator_control",
                "expected": False,
                "actual": bar_result.get("confirms_operator_control"),
            }
        )
    if source_result.get("operator_control_confirmed_by_this_adapter") is not False:
        failures.append(
            {
                "adapter": "explicit_source_adapter",
                "field": "operator_control_confirmed_by_this_adapter",
                "expected": False,
                "actual": source_result.get("operator_control_confirmed_by_this_adapter"),
            }
        )
    if source_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "adapter": "explicit_source_adapter",
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": source_result.get("d3d_execution_recommendation"),
            }
        )
    return failures
def run_read_only_live_alert_review(
    *,
    symbol: str,
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    candidate_payload: dict[str, Any] | None = None,
    explicit_sml_json_path: str | None = None,
    timeout_seconds: int = 30,
    bar_source_priority_policy: list[str] | None = None,
    explicit_source_priority_policy: list[str] | None = None,
) -> dict[str, Any]:
    assert_no_drift_guardrails()
    clean_symbol = str(symbol or "").strip().upper()
    if not clean_symbol:
        return {
            "ok": False,
            "component": COMPONENT,
            "version": VERSION,
            "reason": "MISSING_SYMBOL",
            "guardrails": LIVE_ADAPTER_GUARDRAILS,
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        }
    if load_read_only_ohlcv_bars_for_d4b_candidate is None:
        bar_result = {
            "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
            "source_type": "NONE",
            "source_quality": "UNAVAILABLE",
            "timeframe": requested_timeframe,
            "bar_count": 0,
            "bars": [],
            "window_start": None,
            "window_end": None,
            "warnings": [OHLCV_IMPORT_ERROR or "OHLCV adapter import failed."],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "constructs_hvn_poc": False,
            "not_a_trade_signal": True,
        }
    else:
        bar_result = load_read_only_ohlcv_bars_for_d4b_candidate(
            symbol=clean_symbol,
            requested_timeframe=str(requested_timeframe or "1Min"),
            lookback_bars=max(int(lookback_bars or 390), 20),
            minimum_usable_bars=max(int(minimum_usable_bars or 20), 20),
            source_priority_policy=bar_source_priority_policy
            or [
                "existing_non_mutating_runtime_payload_bars",
                "alpaca_rest_read_only",
                "supabase_rest_read_only",
            ],
            candidate_payload=candidate_payload,
            timeout_seconds=int(timeout_seconds or 30),
        )
    if load_explicit_sml_records_read_only is None:
        source_result = {
            "adapter_status": "SRC7B_BLOCKED_IMPORT_FAILED",
            "source_quality": "UNAVAILABLE",
            "selected_source": None,
            "raw_record_count": 0,
            "symbol_filtered_record_count": 0,
            "valid_record_count": 0,
            "invalid_record_count": 0,
            "warnings": [EXPLICIT_SOURCE_IMPORT_ERROR or "Explicit source adapter import failed."],
            "policy_failure_count": 0,
            "validation_results": [],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed_by_this_adapter": False,
            "not_a_trade_signal": True,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        }
    else:
        source_result = load_explicit_sml_records_read_only(
            symbol=clean_symbol,
            candidate_payload=candidate_payload,
            json_file_path=str(explicit_sml_json_path or DEFAULT_EXPLICIT_SML_JSON_PATH),
            source_priority_policy=explicit_source_priority_policy
            or [
                "existing_non_mutating_runtime_payload_explicit_sml_records",
                "read_only_json_file_explicit_sml_records",
            ],
        )
    bars = _convert_ohlcv_bars(bar_result.get("bars") or [])
    explicit_source = _selected_explicit_source(source_result)
    guardrail_failures = _guardrail_failures(
        bar_result=bar_result,
        source_result=source_result,
    )
    if len(bars) < 20:
        review = None
        live_review_status = "BLOCKED_INSUFFICIENT_20_BAR_WINDOW"
    else:
        review = run_read_only_alert_review(
            clean_symbol,
            bars[-20:],
            explicit_source,
        )
        live_review_status = "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE"
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "symbol": clean_symbol,
        "requested_timeframe": str(requested_timeframe or "1Min"),
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "live_review_status": live_review_status,
        "review_ready": bool(len(bars) >= 20),
        "bar_count_supplied_to_alert": len(bars[-20:]) if len(bars) >= 20 else len(bars),
        "explicit_source_available": explicit_source is not None,
        "bar_adapter": _compact_bar_result(bar_result),
        "explicit_source_adapter": _compact_source_result(source_result),
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "review": review,
        "guardrails": LIVE_ADAPTER_GUARDRAILS,
    }
