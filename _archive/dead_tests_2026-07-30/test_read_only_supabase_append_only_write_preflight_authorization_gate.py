from __future__ import annotations
from backend.alerts.supabase_append_only_write_preflight_authorization_gate import (
    build_read_only_supabase_append_only_write_preflight_authorization_gate_from_schema_audit,
)
def test_append_only_preflight_gate_blocks_when_schema_missing_no_drift():
    schema_audit = {
        "supabase_target_table_schema_existence_audit_status": "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY",
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
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": ["symbol", "audit_component"],
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_NOT_FOUND_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "supabase_url_present": True,
        "supabase_key_present": True,
        "supabase_key_source": "SUPABASE_SERVICE_ROLE_KEY",
        "proposed_supabase_target": {
            "target_table": "alert_readiness_audit_events",
            "write_mode": "APPEND_ONLY_IF_LATER_EXPLICITLY_AUTHORIZED",
            "upsert_allowed": False,
            "update_allowed": False,
            "delete_allowed": False,
            "rpc_allowed": False,
        },
        "write_limits_if_later_authorized": {
            "append_only": True,
            "campaign_table_mutation_allowed": False,
            "operator_control_confirmation_allowed": False,
            "d3d_execution_allowed": False,
        },
        "supabase_target_table_schema_existence_rows": [
            {
                "symbol": "SPY",
                "schema_existence_hypothetically_ready": False,
                "supabase_target_table_schema_existence_status": "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY",
                "table_exists": False,
                "all_proposed_columns_exist": False,
                "missing_proposed_columns": ["symbol", "audit_component"],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "schema_blockers": ["SUPABASE_TARGET_TABLE_NOT_CONFIRMED_READ_ONLY"],
            },
            {
                "symbol": "QQQ",
                "schema_existence_hypothetically_ready": False,
                "supabase_target_table_schema_existence_status": "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY",
                "table_exists": False,
                "all_proposed_columns_exist": False,
                "missing_proposed_columns": ["symbol", "audit_component"],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "schema_blockers": ["SUPABASE_TARGET_TABLE_NOT_CONFIRMED_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_supabase_append_only_write_preflight_authorization_gate_from_schema_audit(
        schema_audit=schema_audit,
    )
    assert result["ok"] is True
    assert result["component"] == "SUPABASE_APPEND_ONLY_WRITE_PREFLIGHT_AUTHORIZATION_GATE_READ_ONLY"
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
    assert result["append_only_write_preflight_authorized"] is False
    assert result["append_only_write_preflight_gate_clear"] is False
    assert result["append_only_write_execution_allowed"] is False
    assert result["append_only_write_preflight_authorization_gate_status"] == "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY"
    assert result["append_only_write_preflight_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["supabase_append_only_write_preflight_authorization_gate_applies_no_changes"] is True
    assert result["supabase_append_only_write_preflight_authorization_gate_is_read_only"] is True
    assert result["supabase_append_only_write_preflight_authorization_gate_never_writes"] is True
    assert result["supabase_append_only_write_preflight_authorization_gate_never_authorizes"] is True
def test_append_only_preflight_gate_hypothetical_clear_but_not_authorized_no_drift():
    schema_audit = {
        "supabase_target_table_schema_existence_audit_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY",
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
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": [],
        "table_exists": True,
        "all_proposed_columns_exist": True,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "supabase_url_present": True,
        "supabase_key_present": True,
        "supabase_key_source": "SUPABASE_SERVICE_ROLE_KEY",
        "proposed_supabase_target": {
            "target_table": "alert_readiness_audit_events",
            "write_mode": "APPEND_ONLY_IF_LATER_EXPLICITLY_AUTHORIZED",
            "upsert_allowed": False,
            "update_allowed": False,
            "delete_allowed": False,
            "rpc_allowed": False,
        },
        "write_limits_if_later_authorized": {
            "append_only": True,
            "campaign_table_mutation_allowed": False,
            "operator_control_confirmation_allowed": False,
            "d3d_execution_allowed": False,
        },
        "supabase_target_table_schema_existence_rows": [
            {
                "symbol": "SPY",
                "schema_existence_hypothetically_ready": True,
                "supabase_target_table_schema_existence_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY",
                "table_exists": True,
                "all_proposed_columns_exist": True,
                "missing_proposed_columns": [],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "schema_blockers": ["NO_SCHEMA_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_supabase_append_only_write_preflight_authorization_gate_from_schema_audit(
        schema_audit=schema_audit,
    )
    assert result["append_only_write_preflight_authorization_gate_status"] == "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
    assert result["append_only_write_preflight_hypothetically_clear_symbols"] == ["SPY"]
    assert result["append_only_write_preflight_authorized"] is False
    assert result["append_only_write_preflight_gate_clear"] is False
    assert result["append_only_write_execution_allowed"] is False
    assert result["persistence_write_authorized"] is False
    assert result["supabase_write_authorized"] is False
    assert result["campaign_mutation_authorized"] is False
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_authorized"] is False
    assert result["can_execute_d3d"] is False
    assert result["actual_write_performed"] is False
    assert result["explicit_human_approval_required_before_any_write"] is True
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_append_only_preflight_gate_blocks_when_schema_missing_no_drift()
    test_append_only_preflight_gate_hypothetical_clear_but_not_authorized_no_drift()
    print("SUPABASE_APPEND_ONLY_WRITE_PREFLIGHT_AUTHORIZATION_GATE_MANUAL_TESTS_PASS")
