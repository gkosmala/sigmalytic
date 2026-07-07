from __future__ import annotations
from backend.alerts.alert_console_frontend_contract_audit import (
    build_read_only_alert_console_frontend_contract_from_view_model,
)
def _base_card(symbol: str):
    return {
        "symbol": symbol,
        "title": symbol,
        "display_status": "SOURCE_READY_READ_ONLY",
        "blocking_class": "NO_BLOCK_READ_ONLY",
        "severity": "NO_ACTION_REQUIRED_READ_ONLY",
        "gap_reasons": [],
        "remediation_steps": ["NO_REMEDIATION_REQUIRED_READ_ONLY"],
        "automated_fix_applied": False,
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
    }
def test_frontend_contract_ready_without_drift():
    view_payload = {
        "view_model_status": "ALERT_CONSOLE_VIEW_MODEL_READY_READ_ONLY",
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
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "view_model": {
            "header": {"title": "Alert Console", "read_only": True, "not_a_trade_signal": True},
            "action_banner": {"banner_type": "READY_FOR_REVIEW_READ_ONLY"},
            "summary_tiles": [],
            "symbol_cards": [_base_card("SPY")],
            "footer": {
                "operator_control_confirmed": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "not_a_trade_signal": True,
                "read_only": True,
            },
        },
    }
    result = build_read_only_alert_console_frontend_contract_from_view_model(
        view_payload=view_payload,
    )
    assert result["ok"] is True
    assert result["component"] == "ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY"
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
    assert result["frontend_contract_status"] == "ALERT_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY"
    assert result["frontend_contract_is_safe_to_render"] is True
    assert result["frontend_contract_is_read_only"] is True
    assert result["frontend_contract_applies_no_changes"] is True
    assert result["missing_contract_failure_count"] == 0
    assert result["guardrail_failure_count"] == 0
def test_frontend_contract_blocks_missing_keys_read_only():
    view_payload = {
        "view_model_status": "ALERT_CONSOLE_VIEW_MODEL_READY_READ_ONLY",
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "view_model": {
            "header": {"title": "Alert Console"},
            "action_banner": {},
            "summary_tiles": [],
            "symbol_cards": [{"symbol": "QQQ"}],
        },
    }
    result = build_read_only_alert_console_frontend_contract_from_view_model(
        view_payload=view_payload,
    )
    assert result["frontend_contract_status"] == "ALERT_CONSOLE_FRONTEND_CONTRACT_BLOCKED_READ_ONLY"
    assert result["frontend_contract_is_safe_to_render"] is False
    assert result["missing_contract_failure_count"] > 0
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_frontend_contract_ready_without_drift()
    test_frontend_contract_blocks_missing_keys_read_only()
    print("ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_MANUAL_TESTS_PASS")
