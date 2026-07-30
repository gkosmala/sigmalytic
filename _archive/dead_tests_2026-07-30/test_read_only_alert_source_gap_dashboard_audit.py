from __future__ import annotations
from backend.alerts.source_gap_dashboard_audit import (
    build_read_only_alert_source_gap_dashboard_from_remediation,
)
def test_source_gap_dashboard_audit_builds_action_cards_without_drift():
    remediation = {
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY",
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "remediation_rows": [
            {
                "symbol": "SPY",
                "blocking_class": "NO_BLOCK_READ_ONLY",
                "gap_reasons": [],
                "remediation_steps": ["NO_REMEDIATION_REQUIRED_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "blocking_class": "EXPLICIT_SOURCE_BLOCK_READ_ONLY",
                "gap_reasons": ["EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE"],
                "remediation_steps": ["ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCE_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_alert_source_gap_dashboard_from_remediation(
        remediation=remediation,
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_SOURCE_GAP_DASHBOARD_AUDIT_READ_ONLY"
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
    assert result["dashboard_status"] == "ALERT_SOURCE_GAP_DASHBOARD_ACTION_REQUIRED_READ_ONLY"
    assert result["ready_card_count"] == 1
    assert result["blocked_card_count"] == 1
    assert result["severity_counts"]["SOURCE_REQUIRED_READ_ONLY"] == 1
    qqq = [row for row in result["dashboard_rows"] if row["symbol"] == "QQQ"][0]
    assert qqq["display_status"] == "BLOCKED_PENDING_SOURCE_REMEDIATION_READ_ONLY"
    assert qqq["automated_fix_applied"] is False
    assert qqq["operator_control_confirmed"] is False
    assert qqq["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert qqq["can_execute_d3d"] is False
def test_source_gap_dashboard_audit_all_ready_read_only():
    remediation = {
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY",
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "remediation_rows": [
            {
                "symbol": "SPY",
                "blocking_class": "NO_BLOCK_READ_ONLY",
                "gap_reasons": [],
                "remediation_steps": ["NO_REMEDIATION_REQUIRED_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_alert_source_gap_dashboard_from_remediation(
        remediation=remediation,
    )
    assert result["dashboard_status"] == "ALERT_SOURCE_GAP_DASHBOARD_ALL_READY_READ_ONLY"
    assert result["ready_card_count"] == 1
    assert result["blocked_card_count"] == 0
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_source_gap_dashboard_audit_builds_action_cards_without_drift()
    test_source_gap_dashboard_audit_all_ready_read_only()
    print("ALERT_SOURCE_GAP_DASHBOARD_AUDIT_MANUAL_TESTS_PASS")
