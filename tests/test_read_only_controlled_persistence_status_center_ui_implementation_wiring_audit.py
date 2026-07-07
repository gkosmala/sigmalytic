from __future__ import annotations
from backend.alerts.controlled_persistence_status_center_ui_implementation_wiring_audit import (
    build_read_only_controlled_persistence_status_center_ui_implementation_wiring_from_mount,
)
from frontend.status_center.controlled_persistence_status_center_panel import (
    build_controlled_persistence_status_center_panel_model,
    read_only_status_center_mount_descriptor,
)
def _mount_row(symbol, *, blocked=True):
    return {
        "mount_id": "alerts.controlledPersistenceDecisionConsole",
        "symbol": symbol,
        "row_key": f"status-center-controlled-persistence-{symbol}",
        "render_component": "StatusCenterReadOnlyDecisionRow",
        "card_title": f"{symbol} Controlled Persistence Decision",
        "status_badge": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY" if blocked else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "severity": "BLOCKED_READ_ONLY" if blocked else "REVIEWABLE_READ_ONLY",
        "primary_message": "Blocked in the decision console. Review blockers before any future write can be considered." if blocked else "Reviewable in the decision console, but explicit human approval is still required before any future write.",
        "final_console_decision_status": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY" if blocked else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "final_console_decision_label": "Blocked; review blockers before any write can be considered." if blocked else "Reviewable; explicit human approval still required before any write.",
        "blocked": blocked,
        "hypothetically_reviewable": not blocked,
        "console_blockers": ["APPROVAL_PACKET_NOT_COMPLETE_READ_ONLY"] if blocked else ["NO_CONSOLE_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY"],
        "approval_packet_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY" if blocked else "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_COMPLETE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "approval_packet_blockers": ["APPEND_ONLY_PREFLIGHT_NOT_CLEAR_READ_ONLY"] if blocked else ["NO_PACKET_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY"],
        "append_only_write_preflight_status": "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY" if blocked else "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY",
        "preflight_blockers": ["SUPABASE_SCHEMA_EXISTENCE_NOT_READY_READ_ONLY"] if blocked else ["NO_PREFLIGHT_BLOCKER_BUT_EXPLICIT_WRITE_APPROVAL_STILL_REQUIRED_READ_ONLY"],
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": ["symbol"] if blocked else [],
        "table_exists": not blocked,
        "all_proposed_columns_exist": not blocked,
        "explicit_human_approval_required_before_any_write": True,
        "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET", "REFRESH_READ_ONLY"],
        "prohibited_ui_actions": ["no_write_button", "no_hidden_mutation_handler", "no_status_center_write_side_effect"],
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
    }
def _mount_payload(rows):
    return {
        "ok": True,
        "component": "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_AUDIT_READ_ONLY",
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
        "status_center_ui_mount_row_count": len(rows),
        "status_center_ui_mount_reviewable_symbol_count": len([row for row in rows if row["hypothetically_reviewable"]]),
        "status_center_ui_mount_blocked_symbol_count": len([row for row in rows if row["blocked"]]),
        "reviewable_symbols": [row["symbol"] for row in rows if row["hypothetically_reviewable"]],
        "blocked_symbols": [row["symbol"] for row in rows if row["blocked"]],
        "summary_panel": {
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "d3d_execution_authorized": False,
            "not_a_trade_signal": True,
            "explicit_human_approval_required_before_any_write": True,
        },
        "chain_cards": [
            {
                "mount_id": "alerts.controlledPersistenceDecisionConsole",
                "name": "source_coverage_completion",
                "status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
                "display_label": "Source Coverage Completion",
                "render_component": "StatusCenterReadOnlyAuditCard",
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "changes_scores": False,
                "changes_ranks": False,
                "changes_states": False,
                "changes_probabilities": False,
                "changes_edge": False,
            }
        ],
        "decision_rows": rows,
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": [],
        "table_exists": True,
        "all_proposed_columns_exist": True,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "explicit_human_approval_required_before_any_write": True,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
    }
def test_frontend_panel_model_has_no_write_controls_or_mutation_side_effects():
    mount_payload = _mount_payload([
        _mount_row("SPY", blocked=True),
        _mount_row("QQQ", blocked=True),
    ])
    descriptor = read_only_status_center_mount_descriptor()
    panel = build_controlled_persistence_status_center_panel_model(mount_payload=mount_payload)
    assert descriptor["status_center_mount_id"] == "alerts.controlledPersistenceDecisionConsole"
    assert descriptor["status_center_http_method"] == "GET"
    assert descriptor["read_only"] is True
    assert descriptor["writes_to_supabase"] is False
    assert descriptor["actual_write_performed"] is False
    assert descriptor["has_write_button"] is False
    assert descriptor["has_hidden_mutation_handler"] is False
    assert descriptor["has_status_center_write_side_effect"] is False
    assert "no_write_button" in descriptor["prohibited_ui_actions"]
    assert panel["component"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_PANEL_READ_ONLY"
    assert panel["read_only"] is True
    assert panel["writes_to_supabase"] is False
    assert panel["mutates_campaigns"] is False
    assert panel["operator_control_confirmed"] is False
    assert panel["composite_operator_control_confirmed"] is False
    assert panel["d3d_execution_authorized"] is False
    assert panel["not_a_trade_signal"] is True
    assert panel["actual_write_performed"] is False
    assert panel["has_write_button"] is False
    assert panel["has_execute_button"] is False
    assert panel["has_hidden_mutation_handler"] is False
    assert panel["has_status_center_write_side_effect"] is False
    assert panel["status_center_panel_implementation_never_writes"] is True
    assert panel["status_center_panel_implementation_never_authorizes"] is True
    assert panel["panel_row_count"] == 2
    assert "Operator control is evidence, not a score" in panel["doctrine_statement"]
def test_status_center_ui_implementation_wiring_audit_ready_but_not_authorized_no_drift():
    mount_payload = _mount_payload([
        _mount_row("SPY", blocked=False),
    ])
    mount_payload["controlled_persistence_decision_console_audit_status"] = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
    result = build_read_only_controlled_persistence_status_center_ui_implementation_wiring_from_mount(
        mount_payload=mount_payload,
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_AUDIT_READ_ONLY"
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
    assert result["status_center_ui_implementation_authorized"] is False
    assert result["status_center_ui_implementation_execution_allowed"] is False
    assert result["status_center_panel_mutation_authorized"] is False
    assert result["status_center_panel_runtime_activation_authorized"] is False
    assert result["controlled_persistence_status_center_ui_implementation_wiring_audit_status"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_READY_READ_ONLY"
    assert result["panel_validation_failure_count"] == 0
    assert result["has_write_button"] is False
    assert result["has_hidden_mutation_handler"] is False
    assert result["has_status_center_write_side_effect"] is False
    assert result["controlled_persistence_status_center_ui_implementation_wiring_never_writes"] is True
    assert result["controlled_persistence_status_center_ui_implementation_wiring_never_authorizes"] is True
    assert result["explicit_human_approval_required_before_any_write"] is True
    assert "no_write_button" in result["prohibited_ui_actions"]
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
if __name__ == "__main__":
    test_frontend_panel_model_has_no_write_controls_or_mutation_side_effects()
    test_status_center_ui_implementation_wiring_audit_ready_but_not_authorized_no_drift()
    print("CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_AUDIT_MANUAL_TESTS_PASS")
