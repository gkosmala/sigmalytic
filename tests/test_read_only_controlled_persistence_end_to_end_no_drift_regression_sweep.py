from __future__ import annotations
from backend.alerts.controlled_persistence_end_to_end_no_drift_regression_sweep import (
    build_read_only_controlled_persistence_end_to_end_no_drift_regression_sweep_from_visual_smoke,
)
def _visual_smoke_payload():
    return {
        "ok": True,
        "component": "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_AUDIT_READ_ONLY",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "d3d_execution_authorized": False,
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "persistence_activation_authorized": False,
        "production_activation_authorized": False,
        "write_permission_manifest_authorized": False,
        "simulated_write_only": True,
        "actual_write_performed": False,
        "schema_existence_audit_authorized": False,
        "schema_write_authorized": False,
        "append_only_write_preflight_authorized": False,
        "append_only_write_preflight_gate_clear": False,
        "append_only_write_execution_allowed": False,
        "approval_packet_authorized": False,
        "approval_packet_write_authorized": False,
        "decision_console_authorized": False,
        "decision_console_execution_allowed": False,
        "frontend_contract_authorized": False,
        "frontend_mutation_authorized": False,
        "frontend_execution_allowed": False,
        "status_center_ui_mount_authorized": False,
        "status_center_ui_mutation_authorized": False,
        "status_center_ui_execution_allowed": False,
        "status_center_ui_implementation_authorized": False,
        "status_center_ui_implementation_execution_allowed": False,
        "status_center_panel_mutation_authorized": False,
        "status_center_panel_runtime_activation_authorized": False,
        "visual_smoke_test_authorized": False,
        "visual_smoke_test_execution_allowed": False,
        "visual_smoke_test_mutation_authorized": False,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "controlled_persistence_status_center_frontend_visual_smoke_test_audit_status": "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_PASS_READ_ONLY",
        "controlled_persistence_status_center_ui_implementation_wiring_audit_status": "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_READY_READ_ONLY",
        "controlled_persistence_status_center_ui_mount_audit_status": "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_READY_READ_ONLY",
        "controlled_persistence_decision_console_frontend_contract_audit_status": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY",
        "controlled_persistence_decision_console_audit_status": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY",
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
        "visual_smoke_pass": True,
        "visual_smoke_failure_count": 0,
        "guardrail_failure_count": 0,
        "panel_validation_failure_count": 0,
        "panel_row_count": 2,
        "panel_chain_card_count": 1,
        "reviewable_symbols": ["SPY"],
        "blocked_symbols": ["QQQ"],
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": [],
        "table_exists": True,
        "all_proposed_columns_exist": True,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "explicit_human_approval_required_before_any_write": True,
        "doctrine_statement": "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure.",
        "visual_smoke_row_results": [
            {
                "symbol": "SPY",
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "not_a_trade_signal": True,
                "actual_write_performed": False,
                "has_write_button": False,
                "has_execute_button": False,
                "has_hidden_mutation_handler": False,
                "has_status_center_write_side_effect": False,
            }
        ],
        "visual_render_tree": {
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "d3d_execution_authorized": False,
            "not_a_trade_signal": True,
            "has_write_button": False,
            "has_execute_button": False,
            "has_hidden_mutation_handler": False,
            "has_status_center_write_side_effect": False,
        },
    }
def test_end_to_end_no_drift_regression_sweep_passes_clean_visual_smoke_payload():
    result = build_read_only_controlled_persistence_end_to_end_no_drift_regression_sweep_from_visual_smoke(
        visual_smoke_payload=_visual_smoke_payload(),
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_READ_ONLY"
    assert result["regression_sweep_schema_version"] == "controlled_persistence_end_to_end_no_drift_regression_sweep_v1"
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
    assert result["regression_sweep_authorized"] is False
    assert result["regression_sweep_execution_allowed"] is False
    assert result["regression_sweep_mutation_authorized"] is False
    assert result["has_write_button"] is False
    assert result["has_execute_button"] is False
    assert result["has_hidden_mutation_handler"] is False
    assert result["has_status_center_write_side_effect"] is False
    assert result["sweep_pass"] is True
    assert result["sweep_failure_count"] == 0
    assert result["controlled_persistence_end_to_end_no_drift_regression_sweep_status"] == "CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_PASS_READ_ONLY"
    assert result["controlled_persistence_end_to_end_no_drift_regression_sweep_is_read_only"] is True
    assert result["controlled_persistence_end_to_end_no_drift_regression_sweep_never_writes"] is True
    assert result["controlled_persistence_end_to_end_no_drift_regression_sweep_never_authorizes"] is True
    assert result["controlled_persistence_end_to_end_no_drift_regression_sweep_has_no_write_button"] is True
    assert len(result["expected_audit_chain"]) == 17
    assert len(result["expected_endpoint_chain"]) == 17
    assert len(result["chain_completion"]) == 17
    assert result["visual_smoke_pass"] is True
    assert result["visual_smoke_failure_count"] == 0
    assert result["guardrail_failure_count"] == 0
    assert result["panel_validation_failure_count"] == 0
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_end_to_end_no_drift_regression_sweep_passes_clean_visual_smoke_payload()
    print("CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_MANUAL_TESTS_PASS")
