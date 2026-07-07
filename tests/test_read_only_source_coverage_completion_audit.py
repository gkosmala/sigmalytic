from __future__ import annotations
from backend.alerts.source_coverage_completion_audit import (
    build_read_only_source_coverage_completion_from_dashboard,
)
def _card(symbol: str, blocking_class: str, gap_reasons):
    return {
        "symbol": symbol,
        "blocking_class": blocking_class,
        "display_status": "SOURCE_READY_READ_ONLY",
        "gap_reasons": gap_reasons,
        "remediation_steps": [],
    }
def test_source_coverage_completion_detects_explicit_source_gap_without_drift():
    dashboard = {
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ACTION_REQUIRED_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY",
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "dashboard_rows": [
            _card("SPY", "NO_BLOCK_READ_ONLY", []),
            _card(
                "QQQ",
                "EXPLICIT_SOURCE_BLOCK_READ_ONLY",
                ["EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE"],
            ),
        ],
    }
    result = build_read_only_source_coverage_completion_from_dashboard(
        dashboard=dashboard,
    )
    assert result["ok"] is True
    assert result["component"] == "SOURCE_COVERAGE_COMPLETION_AUDIT_READ_ONLY"
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
    assert result["source_coverage_completion_status"] == "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY"
    assert result["coverage_is_complete"] is False
    assert result["coverage_complete_symbols"] == ["SPY"]
    assert result["coverage_blocked_symbols"] == ["QQQ"]
    assert result["missing_explicit_source_symbols"] == ["QQQ"]
    assert result["missing_recent_ohlcv_symbols"] == []
    assert result["coverage_audit_applies_no_changes"] is True
    assert result["coverage_audit_is_read_only"] is True
def test_source_coverage_completion_ready_without_drift():
    dashboard = {
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ALL_READY_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY",
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "dashboard_rows": [
            _card("SPY", "NO_BLOCK_READ_ONLY", []),
        ],
    }
    result = build_read_only_source_coverage_completion_from_dashboard(
        dashboard=dashboard,
    )
    assert result["source_coverage_completion_status"] == "SOURCE_COVERAGE_COMPLETE_READ_ONLY"
    assert result["coverage_is_complete"] is True
    assert result["coverage_complete_symbols"] == ["SPY"]
    assert result["coverage_blocked_symbols"] == []
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_source_coverage_completion_detects_explicit_source_gap_without_drift()
    test_source_coverage_completion_ready_without_drift()
    print("SOURCE_COVERAGE_COMPLETION_AUDIT_MANUAL_TESTS_PASS")
