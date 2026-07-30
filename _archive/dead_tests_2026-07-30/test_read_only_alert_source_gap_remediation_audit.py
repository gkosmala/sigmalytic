from __future__ import annotations
from backend.alerts.source_gap_remediation_audit import (
    build_read_only_alert_source_gap_remediation_audit_from_gap,
)
def test_source_gap_remediation_audit_maps_explicit_source_block_without_drift():
    gap = {
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY",
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "source_gap_rows": [
            {
                "symbol": "SPY",
                "source_gap_status": "SOURCE_READY_READ_ONLY",
                "gap_reasons": [],
            },
            {
                "symbol": "QQQ",
                "source_gap_status": "SOURCE_GAP_BLOCKED_READ_ONLY",
                "gap_reasons": [
                    "EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE",
                    "LIVE_READINESS_NOT_READY",
                ],
            },
        ],
    }
    result = build_read_only_alert_source_gap_remediation_audit_from_gap(gap=gap)
    assert result["ok"] is True
    assert result["component"] == "ALERT_SOURCE_GAP_REMEDIATION_AUDIT_READ_ONLY"
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
    assert result["remediation_status"] == "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY"
    assert result["no_action_symbols"] == ["SPY"]
    assert result["explicit_source_block_symbols"] == ["QQQ"]
    assert result["recent_bar_block_symbols"] == []
    assert result["guardrail_block_symbols"] == []
    assert result["explicit_source_block_symbol_count"] == 1
    qqq = [row for row in result["remediation_rows"] if row["symbol"] == "QQQ"][0]
    assert qqq["blocking_class"] == "EXPLICIT_SOURCE_BLOCK_READ_ONLY"
    assert "ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCE_READ_ONLY" in qqq["remediation_steps"]
    assert qqq["automated_fix_applied"] is False
    assert qqq["operator_control_confirmed"] is False
    assert qqq["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert qqq["can_execute_d3d"] is False
def test_source_gap_remediation_audit_no_action_read_only():
    gap = {
        "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY",
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "source_gap_rows": [
            {
                "symbol": "SPY",
                "source_gap_status": "SOURCE_READY_READ_ONLY",
                "gap_reasons": [],
            },
        ],
    }
    result = build_read_only_alert_source_gap_remediation_audit_from_gap(gap=gap)
    assert result["remediation_status"] == "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY"
    assert result["no_action_symbols"] == ["SPY"]
    assert result["blocked_symbol_count"] == 0
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_source_gap_remediation_audit_maps_explicit_source_block_without_drift()
    test_source_gap_remediation_audit_no_action_read_only()
    print("ALERT_SOURCE_GAP_REMEDIATION_AUDIT_MANUAL_TESTS_PASS")
