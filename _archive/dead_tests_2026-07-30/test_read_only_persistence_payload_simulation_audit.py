from __future__ import annotations
from backend.alerts.persistence_payload_simulation_audit import (
    build_read_only_persistence_payload_simulation_from_manifest,
)
def test_persistence_payload_simulation_blocks_when_manifest_blocked_no_drift():
    manifest = {
        "write_permission_manifest_audit_status": "WRITE_PERMISSION_MANIFEST_BLOCKED_READ_ONLY",
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
        "proposed_supabase_target": {"target_table_status": "PROPOSED_ONLY_NOT_AUTHORIZED_READ_ONLY"},
        "proposed_allowed_columns": ["symbol"],
        "absolutely_prohibited_columns": ["operator_control_confirmed"],
        "rollback_expectations": ["NO_WRITE_HAS_OCCURRED_IN_THIS_AUDIT"],
        "write_limits_if_later_authorized": {"append_only": True},
        "persistence_write_permission_manifest_rows": [
            {
                "symbol": "SPY",
                "write_permission_manifest_hypothetically_ready": False,
                "write_permission_manifest_authorized": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_hypothetically_ready": False,
                "permission_blockers": ["CONTROLLED_PERSISTENCE_ACTIVATION_NOT_READY_READ_ONLY"],
                "activation_readiness_blockers": ["CONTROLLED_PERSISTENCE_CONTRACT_NOT_REVIEWABLE_READ_ONLY"],
                "absolutely_prohibited_columns": ["operator_control_confirmed"],
            },
            {
                "symbol": "QQQ",
                "write_permission_manifest_hypothetically_ready": False,
                "write_permission_manifest_authorized": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_hypothetically_ready": False,
                "permission_blockers": ["CONTROLLED_PERSISTENCE_ACTIVATION_NOT_READY_READ_ONLY"],
                "activation_readiness_blockers": ["CONTROLLED_PERSISTENCE_CONTRACT_NOT_REVIEWABLE_READ_ONLY"],
                "absolutely_prohibited_columns": ["operator_control_confirmed"],
            },
        ],
    }
    result = build_read_only_persistence_payload_simulation_from_manifest(
        manifest=manifest,
    )
    assert result["ok"] is True
    assert result["component"] == "PERSISTENCE_PAYLOAD_SIMULATION_AUDIT_READ_ONLY"
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
    assert result["write_permission_manifest_authorized"] is False
    assert result["actual_write_performed"] is False
    assert result["persistence_payload_simulation_audit_status"] == "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY"
    assert result["persistence_payload_simulation_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["persistence_payload_simulation_applies_no_changes"] is True
    assert result["persistence_payload_simulation_is_read_only"] is True
    assert result["persistence_payload_simulation_never_writes"] is True
    assert result["persistence_payload_simulation_never_authorizes"] is True
def test_persistence_payload_simulation_valid_but_not_authorized_no_drift():
    manifest = {
        "write_permission_manifest_audit_status": "WRITE_PERMISSION_MANIFEST_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY",
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
        "proposed_supabase_target": {"target_table_status": "PROPOSED_ONLY_NOT_AUTHORIZED_READ_ONLY"},
        "proposed_allowed_columns": ["symbol"],
        "absolutely_prohibited_columns": ["operator_control_confirmed", "can_execute_d3d"],
        "rollback_expectations": ["NO_WRITE_HAS_OCCURRED_IN_THIS_AUDIT"],
        "write_limits_if_later_authorized": {"append_only": True},
        "persistence_write_permission_manifest_rows": [
            {
                "symbol": "SPY",
                "write_permission_manifest_hypothetically_ready": True,
                "write_permission_manifest_authorized": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "activation_hypothetically_ready": True,
                "permission_blockers": ["NO_PERMISSION_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY"],
                "activation_readiness_blockers": ["NO_READINESS_BLOCKER_BUT_ACTIVATION_STILL_NOT_AUTHORIZED_READ_ONLY"],
                "allowed_persistence_fields_if_later_authorized": ["symbol"],
                "absolutely_prohibited_persistence_fields": ["operator_control_confirmed"],
                "absolutely_prohibited_columns": ["operator_control_confirmed", "can_execute_d3d"],
            },
        ],
    }
    result = build_read_only_persistence_payload_simulation_from_manifest(
        manifest=manifest,
    )
    assert result["persistence_payload_simulation_audit_status"] == "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY"
    assert result["persistence_payload_simulation_valid_symbols"] == ["SPY"]
    assert result["write_permission_manifest_authorized"] is False
    assert result["persistence_write_authorized"] is False
    assert result["supabase_write_authorized"] is False
    assert result["campaign_mutation_authorized"] is False
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_authorized"] is False
    assert result["can_execute_d3d"] is False
    assert result["actual_write_performed"] is False
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
    payload = result["persistence_payload_simulation_rows"][0]["simulated_payload"]
    assert "operator_control_confirmed" not in payload
    assert "can_execute_d3d" not in payload
if __name__ == "__main__":
    test_persistence_payload_simulation_blocks_when_manifest_blocked_no_drift()
    test_persistence_payload_simulation_valid_but_not_authorized_no_drift()
    print("PERSISTENCE_PAYLOAD_SIMULATION_AUDIT_MANUAL_TESTS_PASS")
