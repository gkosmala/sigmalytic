from __future__ import annotations
from backend.alerts.supabase_target_table_schema_existence_audit import (
    build_read_only_supabase_target_table_schema_existence_from_simulation,
)
def test_supabase_target_table_schema_existence_blocks_when_table_missing_no_drift():
    simulation = {
        "persistence_payload_simulation_audit_status": "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY",
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
        "proposed_supabase_target": {"target_table": "alert_readiness_audit_events"},
        "proposed_allowed_columns": ["symbol", "audit_component"],
        "persistence_payload_simulation_rows": [
            {
                "symbol": "SPY",
                "persistence_payload_simulation_hypothetically_valid": False,
                "persistence_payload_simulation_status": "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY",
                "write_permission_manifest_authorized": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "write_permission_manifest_hypothetically_ready": False,
                "permission_blockers": ["CONTROLLED_PERSISTENCE_ACTIVATION_NOT_READY_READ_ONLY"],
                "simulation_blockers": ["WRITE_PERMISSION_MANIFEST_NOT_READY_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "persistence_payload_simulation_hypothetically_valid": False,
                "persistence_payload_simulation_status": "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY",
                "write_permission_manifest_authorized": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "write_permission_manifest_hypothetically_ready": False,
                "permission_blockers": ["CONTROLLED_PERSISTENCE_ACTIVATION_NOT_READY_READ_ONLY"],
                "simulation_blockers": ["WRITE_PERMISSION_MANIFEST_NOT_READY_READ_ONLY"],
            },
        ],
    }
    schema_probe = {
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "schema_probe_attempted": True,
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "missing_proposed_columns": ["symbol", "audit_component"],
        "schema_probe_status": "SUPABASE_TARGET_TABLE_NOT_FOUND_READ_ONLY",
        "schema_probe_http_status": 404,
        "schema_probe_error_excerpt": "relation does not exist",
        "supabase_url_present": True,
        "supabase_key_present": True,
        "supabase_key_source": "SUPABASE_SERVICE_ROLE_KEY",
    }
    result = build_read_only_supabase_target_table_schema_existence_from_simulation(
        simulation=simulation,
        schema_probe=schema_probe,
    )
    assert result["ok"] is True
    assert result["component"] == "SUPABASE_TARGET_TABLE_SCHEMA_EXISTENCE_AUDIT_READ_ONLY"
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
    assert result["schema_existence_audit_authorized"] is False
    assert result["schema_write_authorized"] is False
    assert result["supabase_target_table_schema_existence_audit_status"] == "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY"
    assert result["schema_existence_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["supabase_target_table_schema_existence_applies_no_changes"] is True
    assert result["supabase_target_table_schema_existence_is_read_only"] is True
    assert result["supabase_target_table_schema_existence_never_writes"] is True
    assert result["supabase_target_table_schema_existence_never_authorizes"] is True
def test_supabase_target_table_schema_existence_ready_but_not_authorized_no_drift():
    simulation = {
        "persistence_payload_simulation_audit_status": "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY",
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
        "proposed_supabase_target": {"target_table": "alert_readiness_audit_events"},
        "proposed_allowed_columns": ["symbol", "audit_component"],
        "persistence_payload_simulation_rows": [
            {
                "symbol": "SPY",
                "persistence_payload_simulation_hypothetically_valid": True,
                "persistence_payload_simulation_status": "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY",
                "write_permission_manifest_authorized": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "write_permission_manifest_hypothetically_ready": True,
                "permission_blockers": ["NO_PERMISSION_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY"],
                "simulation_blockers": ["NO_SIMULATION_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY"],
            },
        ],
    }
    schema_probe = {
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "schema_probe_attempted": True,
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "table_exists": True,
        "all_proposed_columns_exist": True,
        "missing_proposed_columns": [],
        "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
        "schema_probe_http_status": 200,
        "schema_probe_error_excerpt": "",
        "supabase_url_present": True,
        "supabase_key_present": True,
        "supabase_key_source": "SUPABASE_SERVICE_ROLE_KEY",
    }
    result = build_read_only_supabase_target_table_schema_existence_from_simulation(
        simulation=simulation,
        schema_probe=schema_probe,
    )
    assert result["supabase_target_table_schema_existence_audit_status"] == "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY"
    assert result["schema_existence_ready_symbols"] == ["SPY"]
    assert result["schema_existence_audit_authorized"] is False
    assert result["schema_write_authorized"] is False
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
if __name__ == "__main__":
    test_supabase_target_table_schema_existence_blocks_when_table_missing_no_drift()
    test_supabase_target_table_schema_existence_ready_but_not_authorized_no_drift()
    print("SUPABASE_TARGET_TABLE_SCHEMA_EXISTENCE_AUDIT_MANUAL_TESTS_PASS")
