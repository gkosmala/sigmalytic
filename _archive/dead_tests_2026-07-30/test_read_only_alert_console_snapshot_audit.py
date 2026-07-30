from __future__ import annotations
from backend.alerts.alert_console_snapshot_audit import (
    build_read_only_alert_console_snapshot_from_dashboard,
)
def test_console_snapshot_builds_action_summary_without_drift():
    dashboard = {
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ACTION_REQUIRED_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY",
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "severity_counts": {"SOURCE_REQUIRED_READ_ONLY": 1},
        "blocking_class_counts": {
            "NO_BLOCK_READ_ONLY": 1,
            "EXPLICIT_SOURCE_BLOCK_READ_ONLY": 1,
        },
        "ready_cards": [
            {"symbol": "SPY", "blocking_class": "NO_BLOCK_READ_ONLY"},
        ],
        "blocked_cards": [
            {"symbol": "QQQ", "blocking_class": "EXPLICIT_SOURCE_BLOCK_READ_ONLY"},
        ],
        "dashboard_rows": [
            {"symbol": "SPY", "blocking_class": "NO_BLOCK_READ_ONLY"},
            {"symbol": "QQQ", "blocking_class": "EXPLICIT_SOURCE_BLOCK_READ_ONLY"},
        ],
    }
    result = build_read_only_alert_console_snapshot_from_dashboard(
        dashboard=dashboard,
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_CONSOLE_SNAPSHOT_AUDIT_READ_ONLY"
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
    assert result["console_snapshot_status"] == "ALERT_CONSOLE_SOURCE_REMEDIATION_REQUIRED_READ_ONLY"
    assert result["ready_symbols"] == ["SPY"]
    assert result["blocked_symbols"] == ["QQQ"]
    assert "ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCES_READ_ONLY" in result["top_console_actions"]
def test_console_snapshot_all_ready_read_only():
    dashboard = {
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ALL_READY_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY",
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "severity_counts": {"NO_ACTION_REQUIRED_READ_ONLY": 1},
        "blocking_class_counts": {"NO_BLOCK_READ_ONLY": 1},
        "ready_cards": [{"symbol": "SPY", "blocking_class": "NO_BLOCK_READ_ONLY"}],
        "blocked_cards": [],
        "dashboard_rows": [{"symbol": "SPY", "blocking_class": "NO_BLOCK_READ_ONLY"}],
    }
    result = build_read_only_alert_console_snapshot_from_dashboard(
        dashboard=dashboard,
    )
    assert result["console_snapshot_status"] == "ALERT_CONSOLE_READY_FOR_REVIEW_READ_ONLY"
    assert result["ready_card_count"] == 1
    assert result["blocked_card_count"] == 0
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_console_snapshot_builds_action_summary_without_drift()
    test_console_snapshot_all_ready_read_only()
    print("ALERT_CONSOLE_SNAPSHOT_AUDIT_MANUAL_TESTS_PASS")
