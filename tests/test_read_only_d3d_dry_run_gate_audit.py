from __future__ import annotations
from backend.alerts.d3d_dry_run_gate_audit import (
    build_read_only_d3d_dry_run_gate_from_operator_control,
)
def test_d3d_dry_run_gate_blocks_when_operator_control_evidence_incomplete_no_drift():
    operator = {
        "operator_control_evidence_audit_status": "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY",
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_INCOMPLETE_OR_BLOCKED_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
        "coverage_is_complete": False,
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "operator_control_rows": [
            {
                "symbol": "SPY",
                "operator_control_evidence_status": "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY",
                "operator_control_evidence_complete": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "blocked_reasons": ["EVIDENCE_PAYLOAD_NOT_COMPLETE_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "operator_control_evidence_status": "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY",
                "operator_control_evidence_complete": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "blocked_reasons": ["EVIDENCE_PAYLOAD_NOT_COMPLETE_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_d3d_dry_run_gate_from_operator_control(
        operator=operator,
    )
    assert result["ok"] is True
    assert result["component"] == "D3D_DRY_RUN_GATE_AUDIT_READ_ONLY"
    assert result["diagnostic_only"] is True
    assert result["read_only"] is True
    assert result["writes_to_supabase"] is False
    assert result["mutates_campaigns"] is False
    assert result["executes_d3d"] is False
    assert result["authorizes_d3d"] is False
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["not_a_trade_signal"] is True
    assert result["changes_scores"] is False
    assert result["changes_ranks"] is False
    assert result["changes_states"] is False
    assert result["changes_probabilities"] is False
    assert result["changes_edge"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["d3d_execution_authorized"] is False
    assert result["d3d_dry_run_gate_audit_status"] == "D3D_DRY_RUN_GATE_BLOCKED_READ_ONLY"
    assert result["d3d_dry_run_gate_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["dry_run_gate_applies_no_changes"] is True
    assert result["dry_run_gate_is_read_only"] is True
    assert result["dry_run_gate_never_authorizes_execution"] is True
def test_d3d_dry_run_gate_can_be_hypothetically_clear_but_never_authorized_no_drift():
    operator = {
        "operator_control_evidence_audit_status": "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY",
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_COMPLETE_READ_ONLY",
        "coverage_is_complete": True,
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "operator_control_rows": [
            {
                "symbol": "SPY",
                "operator_control_evidence_status": "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY",
                "operator_control_evidence_complete": True,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "blocked_reasons": ["NO_OPERATOR_CONTROL_EVIDENCE_BLOCKER_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_d3d_dry_run_gate_from_operator_control(
        operator=operator,
    )
    assert result["d3d_dry_run_gate_audit_status"] == "D3D_DRY_RUN_GATE_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
    assert result["d3d_dry_run_gate_hypothetically_clear_symbols"] == ["SPY"]
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["d3d_execution_authorized"] is False
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_d3d_dry_run_gate_blocks_when_operator_control_evidence_incomplete_no_drift()
    test_d3d_dry_run_gate_can_be_hypothetically_clear_but_never_authorized_no_drift()
    print("D3D_DRY_RUN_GATE_AUDIT_MANUAL_TESTS_PASS")
