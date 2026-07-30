from __future__ import annotations
from backend.alerts.source_gap_audit import build_read_only_alert_source_gap_audit_from_batch
def test_source_gap_audit_detects_missing_explicit_source_without_drift():
    batch = {
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "batch_readiness_status": "LIVE_READINESS_BATCH_MIXED_OR_BLOCKED_READ_ONLY",
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "audit_results": [
            {
                "symbol": "SPY",
                "readiness_status": "LIVE_READINESS_AUDIT_READY_READ_ONLY",
                "live_review_status": "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE",
                "recent_bars_accepted": True,
                "explicit_source_available": True,
                "bar_adapter_status": "ADAPTER_OK_BARS_LOADED_READ_ONLY",
                "bar_source_quality": "USABLE_RECENT_OHLCV_BARS",
                "bar_source_type": "ALPACA_REST_READ_ONLY:sip",
                "bar_count": 390,
                "guardrail_failure_count": 0,
                "guardrail_failures": [],
            },
            {
                "symbol": "QQQ",
                "readiness_status": "LIVE_READINESS_AUDIT_NOT_READY_READ_ONLY",
                "live_review_status": "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE",
                "recent_bars_accepted": True,
                "explicit_source_available": False,
                "bar_adapter_status": "ADAPTER_OK_BARS_LOADED_READ_ONLY",
                "bar_source_quality": "USABLE_RECENT_OHLCV_BARS",
                "bar_source_type": "ALPACA_REST_READ_ONLY:sip",
                "bar_count": 390,
                "guardrail_failure_count": 0,
                "guardrail_failures": [],
            },
        ],
    }
    result = build_read_only_alert_source_gap_audit_from_batch(batch=batch)
    assert result["ok"] is True
    assert result["component"] == "ALERT_SOURCE_GAP_AUDIT_READ_ONLY"
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
    assert result["source_gap_status"] == "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY"
    assert result["source_ready_symbols"] == ["SPY"]
    assert result["missing_explicit_source_symbols"] == ["QQQ"]
    assert result["missing_recent_bar_symbols"] == []
    assert result["reason_counts"]["EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE"] == 1
    assert result["reason_counts"]["LIVE_READINESS_NOT_READY"] == 1
def test_source_gap_audit_all_ready_read_only():
    batch = {
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "batch_readiness_status": "LIVE_READINESS_BATCH_READY_READ_ONLY",
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "audit_results": [
            {
                "symbol": "SPY",
                "readiness_status": "LIVE_READINESS_AUDIT_READY_READ_ONLY",
                "live_review_status": "LIVE_READ_ONLY_ALERT_REVIEW_COMPLETE",
                "recent_bars_accepted": True,
                "explicit_source_available": True,
                "bar_adapter_status": "ADAPTER_OK_BARS_LOADED_READ_ONLY",
                "bar_source_quality": "USABLE_RECENT_OHLCV_BARS",
                "bar_source_type": "ALPACA_REST_READ_ONLY:sip",
                "bar_count": 390,
                "guardrail_failure_count": 0,
                "guardrail_failures": [],
            },
        ],
    }
    result = build_read_only_alert_source_gap_audit_from_batch(batch=batch)
    assert result["source_gap_status"] == "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY"
    assert result["source_ready_symbol_count"] == 1
    assert result["blocked_symbol_count"] == 0
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_source_gap_audit_detects_missing_explicit_source_without_drift()
    test_source_gap_audit_all_ready_read_only()
    print("ALERT_SOURCE_GAP_AUDIT_MANUAL_TESTS_PASS")
