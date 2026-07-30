from __future__ import annotations
from backend.alerts.live_readiness_batch_audit import (
    build_read_only_live_readiness_batch_audit_from_results,
)
def _result(symbol, status="LIVE_READINESS_AUDIT_READY_READ_ONLY"):
    ready = status == "LIVE_READINESS_AUDIT_READY_READ_ONLY"
    return {
        "ok": True,
        "symbol": symbol,
        "readiness_status": status,
        "live_review_status": "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE" if ready else "BLOCKED_INSUFFICIENT_20_BAR_WINDOW",
        "recent_bars_accepted": ready,
        "explicit_source_available": ready,
        "bar_adapter_status": "ADAPTER_OK_BARS_LOADED_READ_ONLY" if ready else "ADAPTER_BLOCKED_NO_ALPACA_BARS_FOUND",
        "bar_source_quality": "USABLE_RECENT_OHLCV_BARS" if ready else "UNAVAILABLE_READ_ONLY",
        "bar_source_type": "ALPACA_REST_READ_ONLY:sip",
        "bar_count": 390 if ready else 0,
        "bar_window_start": "2026-07-07T13:00:00Z" if ready else None,
        "bar_window_end": "2026-07-07T19:59:00Z" if ready else None,
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
        "can_execute_d3d": False,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
    }
def test_batch_audit_all_ready_read_only():
    result = build_read_only_live_readiness_batch_audit_from_results(
        requested_symbols=["SPY", "QQQ"],
        audit_results=[_result("SPY"), _result("QQQ")],
        requested_timeframe="1Min",
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_LIVE_READINESS_BATCH_AUDIT_READ_ONLY"
    assert result["diagnostic_only"] is True
    assert result["read_only"] is True
    assert result["writes_to_supabase"] is False
    assert result["mutates_campaigns"] is False
    assert result["executes_d3d"] is False
    assert result["authorizes_d3d"] is False
    assert result["operator_control_confirmed"] is False
    assert result["not_a_trade_signal"] is True
    assert result["changes_scores"] is False
    assert result["changes_ranks"] is False
    assert result["changes_states"] is False
    assert result["changes_probabilities"] is False
    assert result["changes_edge"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["batch_readiness_status"] == "LIVE_READINESS_BATCH_READY_READ_ONLY"
    assert result["ready_symbol_count"] == 2
    assert result["blocked_symbol_count"] == 0
    assert result["guardrail_failure_count"] == 0
def test_batch_audit_mixed_read_only():
    result = build_read_only_live_readiness_batch_audit_from_results(
        requested_symbols=["SPY", "NOPE"],
        audit_results=[
            _result("SPY"),
            _result("NOPE", "LIVE_READINESS_AUDIT_BLOCKED_READ_ONLY"),
        ],
        requested_timeframe="1Min",
    )
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["batch_readiness_status"] == "LIVE_READINESS_BATCH_MIXED_OR_BLOCKED_READ_ONLY"
    assert result["ready_symbol_count"] == 1
    assert result["blocked_symbol_count"] == 1
def test_batch_audit_guardrail_failure_does_not_authorize_anything():
    bad = _result("SPY")
    bad["guardrail_failure_count"] = 1
    bad["guardrail_failures"] = ["example nested failure"]
    result = build_read_only_live_readiness_batch_audit_from_results(
        requested_symbols=["SPY"],
        audit_results=[bad],
        requested_timeframe="1Min",
    )
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["batch_readiness_status"] == "LIVE_READINESS_BATCH_MIXED_OR_BLOCKED_READ_ONLY"
    assert result["guardrail_failure_count"] >= 1
if __name__ == "__main__":
    test_batch_audit_all_ready_read_only()
    test_batch_audit_mixed_read_only()
    test_batch_audit_guardrail_failure_does_not_authorize_anything()
    print("LIVE_READINESS_BATCH_AUDIT_MANUAL_TESTS_PASS")
