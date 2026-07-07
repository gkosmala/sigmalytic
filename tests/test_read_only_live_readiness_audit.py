from __future__ import annotations
from backend.alerts.live_readiness_audit import build_read_only_live_readiness_audit_from_review
def _base_live_review():
    return {
        "ok": True,
        "component": "ALERT_LIVE_DATA_ADAPTER_READ_ONLY",
        "version": "alert_live_data_adapter_read_only_v1",
        "symbol": "SPY",
        "requested_timeframe": "1Min",
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
        "live_review_status": "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE",
        "review_ready": True,
        "explicit_source_available": True,
        "guardrail_failure_count": 0,
        "bar_adapter": {
            "adapter_status": "ADAPTER_OK_BARS_LOADED_READ_ONLY",
            "source_quality": "USABLE_RECENT_OHLCV_BARS",
            "source_type": "ALPACA_REST_READ_ONLY:sip",
            "bar_count": 390,
            "window_start": "2026-07-07T13:00:00Z",
            "window_end": "2026-07-07T19:59:00Z",
        },
        "explicit_source_adapter": {
            "adapter_status": "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY",
            "source_quality": "VALID_EXPLICIT_STRUCTURAL_LOCATION_RECORDS",
        },
    }
def test_live_readiness_audit_ready_read_only():
    result = build_read_only_live_readiness_audit_from_review(
        live_review=_base_live_review(),
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_LIVE_READINESS_AUDIT_READ_ONLY"
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
    assert result["guardrail_failure_count"] == 0
    assert result["readiness_status"] == "LIVE_READINESS_AUDIT_READY_READ_ONLY"
    assert result["recent_bars_accepted"] is True
    assert result["explicit_source_available"] is True
def test_live_readiness_audit_blocks_stale_or_unready_read_only():
    review = _base_live_review()
    review["review_ready"] = False
    review["live_review_status"] = "BLOCKED_INSUFFICIENT_20_BAR_WINDOW"
    review["bar_adapter"]["source_quality"] = "STALE_OR_UNAVAILABLE_OHLCV_BARS"
    result = build_read_only_live_readiness_audit_from_review(
        live_review=review,
    )
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["readiness_status"] == "LIVE_READINESS_AUDIT_BLOCKED_READ_ONLY"
    assert result["recent_bars_accepted"] is False
def test_live_readiness_audit_detects_guardrail_failure_without_authorizing_anything():
    review = _base_live_review()
    review["writes_to_supabase"] = True
    result = build_read_only_live_readiness_audit_from_review(
        live_review=review,
    )
    assert result["ok"] is True
    assert result["writes_to_supabase"] is False
    assert result["mutates_campaigns"] is False
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["readiness_status"] == "LIVE_REVIEW_GUARDRAIL_FAILURE_READ_ONLY"
    assert result["guardrail_failure_count"] == 1
if __name__ == "__main__":
    test_live_readiness_audit_ready_read_only()
    test_live_readiness_audit_blocks_stale_or_unready_read_only()
    test_live_readiness_audit_detects_guardrail_failure_without_authorizing_anything()
    print("LIVE_READINESS_AUDIT_MANUAL_TESTS_PASS")
