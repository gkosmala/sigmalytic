from __future__ import annotations
from backend.alerts.alert_console_view_model_audit import (
    build_read_only_alert_console_view_model_from_snapshot,
)
def test_console_view_model_builds_ui_contract_without_drift():
    snapshot = {
        "console_snapshot_status": "ALERT_CONSOLE_SOURCE_REMEDIATION_REQUIRED_READ_ONLY",
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ACTION_REQUIRED_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY",
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "ready_card_count": 1,
        "blocked_card_count": 1,
        "ready_symbols": ["SPY"],
        "blocked_symbols": ["QQQ"],
        "top_console_actions": ["ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCES_READ_ONLY"],
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "console_cards": [
            {
                "symbol": "SPY",
                "display_status": "SOURCE_READY_READ_ONLY",
                "blocking_class": "NO_BLOCK_READ_ONLY",
                "severity": "NO_ACTION_REQUIRED_READ_ONLY",
                "gap_reasons": [],
                "remediation_steps": ["NO_REMEDIATION_REQUIRED_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "display_status": "BLOCKED_PENDING_SOURCE_REMEDIATION_READ_ONLY",
                "blocking_class": "EXPLICIT_SOURCE_BLOCK_READ_ONLY",
                "severity": "SOURCE_REQUIRED_READ_ONLY",
                "gap_reasons": ["EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE"],
                "remediation_steps": ["ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCE_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_alert_console_view_model_from_snapshot(
        snapshot=snapshot,
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_CONSOLE_VIEW_MODEL_AUDIT_READ_ONLY"
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
    assert result["view_model_status"] == "ALERT_CONSOLE_VIEW_MODEL_READY_READ_ONLY"
    assert result["view_model_symbol_card_count"] == 2
    view_model = result["view_model"]
    assert view_model["header"]["status"] == "ALERT_CONSOLE_SOURCE_REMEDIATION_REQUIRED_READ_ONLY"
    assert view_model["action_banner"]["banner_type"] == "SOURCE_REMEDIATION_REQUIRED_READ_ONLY"
    assert view_model["footer"]["operator_control_confirmed"] is False
    assert view_model["footer"]["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert view_model["footer"]["can_execute_d3d"] is False
    qqq = [card for card in view_model["symbol_cards"] if card["symbol"] == "QQQ"][0]
    assert qqq["automated_fix_applied"] is False
    assert qqq["operator_control_confirmed"] is False
    assert qqq["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert qqq["can_execute_d3d"] is False
def test_console_view_model_all_ready_banner_read_only():
    snapshot = {
        "console_snapshot_status": "ALERT_CONSOLE_READY_FOR_REVIEW_READ_ONLY",
        "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_ALL_READY_READ_ONLY",
        "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY",
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY",
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "ready_card_count": 1,
        "blocked_card_count": 0,
        "ready_symbols": ["SPY"],
        "blocked_symbols": [],
        "top_console_actions": ["NO_SOURCE_REMEDIATION_ACTION_REQUIRED_READ_ONLY"],
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "console_cards": [
            {
                "symbol": "SPY",
                "display_status": "SOURCE_READY_READ_ONLY",
                "blocking_class": "NO_BLOCK_READ_ONLY",
                "severity": "NO_ACTION_REQUIRED_READ_ONLY",
                "gap_reasons": [],
                "remediation_steps": ["NO_REMEDIATION_REQUIRED_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_alert_console_view_model_from_snapshot(
        snapshot=snapshot,
    )
    assert result["view_model"]["action_banner"]["banner_type"] == "READY_FOR_REVIEW_READ_ONLY"
    assert result["view_model_symbol_card_count"] == 1
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_console_view_model_builds_ui_contract_without_drift()
    test_console_view_model_all_ready_banner_read_only()
    print("ALERT_CONSOLE_VIEW_MODEL_AUDIT_MANUAL_TESTS_PASS")
