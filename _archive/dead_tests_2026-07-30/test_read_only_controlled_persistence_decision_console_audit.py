from __future__ import annotations
from backend.alerts.controlled_persistence_decision_console_audit import (
    build_read_only_controlled_persistence_decision_console_from_approval_packet,
)
def test_controlled_persistence_decision_console_blocks_when_approval_packet_blocked_no_drift():
    approval_packet = {
        "controlled_append_only_write_approval_packet_audit_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY",
        "append_only_write_preflight_authorization_gate_status": "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY",
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
        "missing_proposed_columns": ["symbol"],
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_NOT_FOUND_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "explicit_human_approval_required_before_any_write": True,
        "controlled_append_only_write_approval_packet_rows": [
            {
                "symbol": "SPY",
                "controlled_append_only_write_approval_packet_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY",
                "approval_packet_hypothetically_complete": False,
                "approval_packet_authorized": False,
                "approval_packet_write_authorized": False,
                "append_only_write_preflight_authorized": False,
                "append_only_write_preflight_gate_clear": False,
                "append_only_write_execution_allowed": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "approval_packet_blockers": ["APPEND_ONLY_PREFLIGHT_NOT_CLEAR_READ_ONLY"],
                "approval_payload_preview": {"symbol": "SPY"},
                "append_only_write_preflight_status": "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY",
                "append_only_write_preflight_hypothetically_clear": False,
                "preflight_blockers": ["SUPABASE_SCHEMA_EXISTENCE_NOT_READY_READ_ONLY"],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "missing_proposed_columns": ["symbol"],
                "table_exists": False,
                "all_proposed_columns_exist": False,
            },
            {
                "symbol": "QQQ",
                "controlled_append_only_write_approval_packet_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY",
                "approval_packet_hypothetically_complete": False,
                "approval_packet_authorized": False,
                "approval_packet_write_authorized": False,
                "append_only_write_preflight_authorized": False,
                "append_only_write_preflight_gate_clear": False,
                "append_only_write_execution_allowed": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "approval_packet_blockers": ["APPEND_ONLY_PREFLIGHT_NOT_CLEAR_READ_ONLY"],
                "approval_payload_preview": {"symbol": "QQQ"},
                "append_only_write_preflight_status": "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY",
                "append_only_write_preflight_hypothetically_clear": False,
                "preflight_blockers": ["SUPABASE_SCHEMA_EXISTENCE_NOT_READY_READ_ONLY"],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "missing_proposed_columns": ["symbol"],
                "table_exists": False,
                "all_proposed_columns_exist": False,
            },
        ],
    }
    result = build_read_only_controlled_persistence_decision_console_from_approval_packet(
        approval_packet=approval_packet,
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_AUDIT_READ_ONLY"
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
    assert result["actual_write_performed"] is False
    assert result["approval_packet_authorized"] is False
    assert result["approval_packet_write_authorized"] is False
    assert result["decision_console_authorized"] is False
    assert result["decision_console_execution_allowed"] is False
    assert result["controlled_persistence_decision_console_audit_status"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY"
    assert result["decision_console_blocked_symbols"] == ["SPY", "QQQ"]
    assert result["controlled_persistence_decision_console_applies_no_changes"] is True
    assert result["controlled_persistence_decision_console_is_read_only"] is True
    assert result["controlled_persistence_decision_console_never_writes"] is True
    assert result["controlled_persistence_decision_console_never_authorizes"] is True
def test_controlled_persistence_decision_console_reviewable_but_not_authorized_no_drift():
    approval_packet = {
        "controlled_append_only_write_approval_packet_audit_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_COMPLETE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "append_only_write_preflight_authorization_gate_status": "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY",
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
        "explicit_human_approval_required_before_any_write": True,
        "controlled_append_only_write_approval_packet_rows": [
            {
                "symbol": "SPY",
                "controlled_append_only_write_approval_packet_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_COMPLETE_BUT_NOT_AUTHORIZED_READ_ONLY",
                "approval_packet_hypothetically_complete": True,
                "approval_packet_authorized": False,
                "approval_packet_write_authorized": False,
                "append_only_write_preflight_authorized": False,
                "append_only_write_preflight_gate_clear": False,
                "append_only_write_execution_allowed": False,
                "actual_write_performed": False,
                "persistence_write_authorized": False,
                "supabase_write_authorized": False,
                "campaign_mutation_authorized": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "can_execute_d3d": False,
                "approval_packet_blockers": ["NO_PACKET_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY"],
                "approval_payload_preview": {"symbol": "SPY"},
                "append_only_write_preflight_status": "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY",
                "append_only_write_preflight_hypothetically_clear": True,
                "preflight_blockers": ["NO_PREFLIGHT_BLOCKER_BUT_EXPLICIT_WRITE_APPROVAL_STILL_REQUIRED_READ_ONLY"],
                "target_table": "alert_readiness_audit_events",
                "proposed_columns": ["symbol", "audit_component"],
                "missing_proposed_columns": [],
                "table_exists": True,
                "all_proposed_columns_exist": True,
            },
        ],
    }
    result = build_read_only_controlled_persistence_decision_console_from_approval_packet(
        approval_packet=approval_packet,
    )
    assert result["controlled_persistence_decision_console_audit_status"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
    assert result["decision_console_reviewable_symbols"] == ["SPY"]
    assert result["decision_console_authorized"] is False
    assert result["decision_console_execution_allowed"] is False
    assert result["approval_packet_authorized"] is False
    assert result["approval_packet_write_authorized"] is False
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
    test_controlled_persistence_decision_console_blocks_when_approval_packet_blocked_no_drift()
    test_controlled_persistence_decision_console_reviewable_but_not_authorized_no_drift()
    print("CONTROLLED_PERSISTENCE_DECISION_CONSOLE_AUDIT_MANUAL_TESTS_PASS")
