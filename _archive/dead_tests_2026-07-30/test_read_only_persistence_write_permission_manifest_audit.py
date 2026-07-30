from __future__ import annotations
from backend.alerts.persistence_write_permission_manifest_audit import (
    build_read_only_persistence_write_permission_manifest_from_activation_readiness,
)
def test_write_permission_manifest_blocks_when_activation_not_ready_no_drift():
    readiness = {
        "controlled_persistence_activation_readiness_audit_status": "CONTROLLED_PERSISTENCE_ACTIVATION_BLOCKED_READ_ONLY",
        "controlled_persistence_contract_audit_status": "CONTROLLED_PERSISTENCE_CONTRACT_BLOCKED_READ_ONLY",
        "d3d_dry_run_gate_audit_status": "D3D_DRY_RUN_GATE_BLOCKED_READ_ONLY",
        "operator_control_evidence_audit_status": "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY",
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_INCOMPLETE_OR_BLOCKED_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
        "coverage_is_complete": False,
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "controlled_persistence_activation_readiness_rows": [
            {
                "symbol": "SPY",
                "activation_hypothetically_ready": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_readiness_blockers": ["CONTROLLED_PERSISTENCE_CONTRACT_NOT_REVIEWABLE_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "activation_hypothetically_ready": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_readiness_blockers": ["CONTROLLED_PERSISTENCE_CONTRACT_NOT_REVIEWABLE_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_persistence_write_permission_manifest_from_activation_readiness(
        readiness=readiness,
    )
    assert result["ok"] is True
    assert result["component"] == "PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_READ_ONLY"
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
    assert result["persistence_write_authorized"] is False
    assert result["supabase_write_authorized"] is False
    assert result["campaign_mutation_authorized"] is False
    assert result["persistence_activation_authorized"] is False
    assert result["production_activation_authorized"] is False
    assert result["write_permission_manifest_authorized"] is False
    assert result["write_permission_manifest_audit_status"] == "WRITE_PERMISSION_MANIFEST_BLOCKED_READ_ONLY"
    assert result["write_permission_manifest_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["write_permission_manifest_applies_no_changes"] is True
    assert result["write_permission_manifest_is_read_only"] is True
    assert result["write_permission_manifest_never_writes"] is True
    assert result["write_permission_manifest_never_authorizes"] is True
def test_write_permission_manifest_hypothetical_but_not_authorized_no_drift():
    readiness = {
        "controlled_persistence_activation_readiness_audit_status": "CONTROLLED_PERSISTENCE_ACTIVATION_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY",
        "controlled_persistence_contract_audit_status": "CONTROLLED_PERSISTENCE_CONTRACT_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "d3d_dry_run_gate_audit_status": "D3D_DRY_RUN_GATE_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY",
        "operator_control_evidence_audit_status": "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY",
        "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY",
        "source_coverage_completion_status": "SOURCE_COVERAGE_COMPLETE_READ_ONLY",
        "coverage_is_complete": True,
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "controlled_persistence_activation_readiness_rows": [
            {
                "symbol": "SPY",
                "activation_hypothetically_ready": True,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_readiness_blockers": ["NO_READINESS_BLOCKER_BUT_ACTIVATION_STILL_NOT_AUTHORIZED_READ_ONLY"],
                "allowed_persistence_fields_if_later_authorized": ["symbol"],
                "absolutely_prohibited_persistence_fields": ["operator_control_confirmed"],
            },
        ],
    }
    result = build_read_only_persistence_write_permission_manifest_from_activation_readiness(
        readiness=readiness,
    )
    assert result["write_permission_manifest_audit_status"] == "WRITE_PERMISSION_MANIFEST_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY"
    assert result["write_permission_manifest_hypothetically_ready_symbols"] == ["SPY"]
    assert result["write_permission_manifest_authorized"] is False
    assert result["persistence_write_authorized"] is False
    assert result["supabase_write_authorized"] is False
    assert result["campaign_mutation_authorized"] is False
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_authorized"] is False
    assert result["can_execute_d3d"] is False
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_write_permission_manifest_blocks_when_activation_not_ready_no_drift()
    test_write_permission_manifest_hypothetical_but_not_authorized_no_drift()
    print("PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_MANUAL_TESTS_PASS")
