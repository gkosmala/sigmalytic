from __future__ import annotations
from backend.alerts.operator_control_evidence_audit import (
    build_read_only_operator_control_evidence_from_evidence_payload,
)
def test_operator_control_evidence_blocks_when_payload_incomplete_no_drift():
    evidence = {
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_INCOMPLETE_OR_BLOCKED_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
        "coverage_is_complete": False,
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "evidence_rows": [
            {
                "symbol": "SPY",
                "evidence_payload_status": "EVIDENCE_PAYLOAD_MISSING_READ_ONLY",
                "evidence_payload_complete": False,
            },
            {
                "symbol": "QQQ",
                "evidence_payload_status": "EVIDENCE_PAYLOAD_BLOCKED_BY_SOURCE_COVERAGE_READ_ONLY",
                "evidence_payload_complete": False,
            },
        ],
    }
    result = build_read_only_operator_control_evidence_from_evidence_payload(
        evidence=evidence,
    )
    assert result["ok"] is True
    assert result["component"] == "OPERATOR_CONTROL_EVIDENCE_AUDIT_READ_ONLY"
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
    assert result["operator_control_evidence_audit_status"] == "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY"
    assert result["operator_control_evidence_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["operator_control_audit_applies_no_changes"] is True
    assert result["operator_control_audit_is_read_only"] is True
def test_operator_control_evidence_complete_but_not_confirmed_no_drift():
    evidence_payload = {
        "tested_supply_exhaustion": {"evidence": "present"},
        "active_demand_support_validation": {"evidence": "present"},
        "structurally_meaningful_location": {"evidence": "present"},
        "absence_of_contrary_failure": {"evidence": "present"},
    }
    evidence = {
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_COMPLETE_READ_ONLY",
        "coverage_is_complete": True,
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "evidence_rows": [
            {
                "symbol": "SPY",
                "evidence_payload_status": "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY",
                "evidence_payload_complete": True,
                "evidence_payload": evidence_payload,
            },
        ],
    }
    result = build_read_only_operator_control_evidence_from_evidence_payload(
        evidence=evidence,
    )
    assert result["operator_control_evidence_audit_status"] == "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY"
    assert result["operator_control_evidence_complete_symbols"] == ["SPY"]
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_operator_control_evidence_blocks_when_payload_incomplete_no_drift()
    test_operator_control_evidence_complete_but_not_confirmed_no_drift()
    print("OPERATOR_CONTROL_EVIDENCE_AUDIT_MANUAL_TESTS_PASS")
