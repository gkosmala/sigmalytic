from __future__ import annotations
from backend.alerts.controlled_persistence_status_center_frontend_visual_smoke_test_audit import (
    build_read_only_status_center_frontend_visual_smoke_test_from_wiring,
)
def _panel_row(symbol, *, blocked=True):
    return {
        "symbol": symbol,
        "row_key": f"status-center-controlled-persistence-{symbol}",
        "render_component": "StatusCenterControlledPersistenceReadOnlyRow",
        "card_title": f"{symbol} Controlled Persistence Decision",
        "status_badge": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY" if blocked else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "severity": "BLOCKED_READ_ONLY" if blocked else "REVIEWABLE_READ_ONLY",
        "primary_message": "Blocked in the decision console. Review blockers before any future write can be considered." if blocked else "Reviewable in the decision console, but explicit human approval is still required before any future write.",
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
        "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET", "REFRESH_READ_ONLY"],
        "prohibited_ui_actions": [
            "no_write_button",
            "no_execute_button",
            "no_confirm_operator_control_button",
            "no_confirm_composite_operator_control_button",
            "no_authorize_d3d_button",
            "no_trade_signal_button",
            "no_score_rank_state_probability_or_edge_change",
            "no_supabase_insert_update_upsert_delete_rpc",
            "no_campaign_table_mutation",
            "no_hidden_mutation_handler",
            "no_status_center_write_side_effect",
        ],
        "explicit_human_approval_required_before_any_write": True,
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
        "actual_write_performed": False,
        "status_center_ui_implementation_authorized": False,
        "status_center_ui_implementation_execution_allowed": False,
        "status_center_ui_implementation_writes": False,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "doctrine_statement": "Operator control is evidence, not a score.",
    }
def _wiring_payload(rows):
    return {
        "ok": True,
        "component": "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_AUDIT_READ_ONLY",
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
        "status_center_panel_model": {
            "component": "CONTROLLED_PERSISTENCE_STATUS_CENTER_PANEL_READ_ONLY",
            "status_center_mount_id": "alerts.controlledPersistenceDecisionConsole",
            "status_center_panel_title": "Controlled Persistence Decision Console",
            "status_center_source_endpoint": "/api/alerts/read-only/controlled-persistence-status-center-ui-mount-audit",
            "status_center_http_method": "GET",
            "status_center_render_mode": "READ_ONLY_REVIEW_PANEL",
            "status_center_refresh_mode": "READ_ONLY_ENDPOINT_REFRESH_ONLY",
            "display_sections": [
                "summary_panel",
                "read_only_status_badges",
                "audit_chain_cards",
                "symbol_decision_table",
                "blocker_list",
                "target_table_panel",
                "schema_probe_panel",
                "doctrine_panel",
                "absolute_prohibition_panel",
                "human_approval_required_banner",
            ],
            "summary_panel": {
                "title": "Controlled Persistence Decision Console",
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "not_a_trade_signal": True,
                "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET", "REFRESH_READ_ONLY"],
                "prohibited_ui_actions": [
                    "no_write_button",
                    "no_execute_button",
                    "no_confirm_operator_control_button",
                    "no_confirm_composite_operator_control_button",
                    "no_authorize_d3d_button",
                    "no_trade_signal_button",
                    "no_score_rank_state_probability_or_edge_change",
                    "no_supabase_insert_update_upsert_delete_rpc",
                    "no_campaign_table_mutation",
                    "no_hidden_mutation_handler",
                    "no_status_center_write_side_effect",
                ],
                "explicit_human_approval_required_before_any_write": True,
            },
            "chain_cards": [
                {
                    "name": "source_coverage_completion",
                    "status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
                    "display_label": "Source Coverage Completion",
                    "render_component": "StatusCenterControlledPersistenceReadOnlyAuditCard",
                    "read_only": True,
                    "writes_to_supabase": False,
                    "mutates_campaigns": False,
                    "authorizes_d3d": False,
                    "operator_control_confirmed": False,
                    "composite_operator_control_confirmed": False,
                    "not_a_trade_signal": True,
                }
            ],
            "decision_rows": rows,
            "read_only_status_badges": [
                "READ_ONLY_UI_IMPLEMENTATION",
                "NO_DATABASE_WRITE",
                "NO_SUPABASE_INSERT",
                "NO_CAMPAIGN_MUTATION",
                "NO_OPERATOR_CONTROL_CONFIRMATION",
                "NO_D3D_AUTHORIZATION",
                "NO_TRADE_SIGNAL",
                "HUMAN_APPROVAL_REQUIRED_BEFORE_WRITE",
            ],
            "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET", "REFRESH_READ_ONLY"],
            "prohibited_ui_actions": [
                "no_write_button",
                "no_execute_button",
                "no_confirm_operator_control_button",
                "no_confirm_composite_operator_control_button",
                "no_authorize_d3d_button",
                "no_trade_signal_button",
                "no_score_rank_state_probability_or_edge_change",
                "no_supabase_insert_update_upsert_delete_rpc",
                "no_campaign_table_mutation",
                "no_hidden_mutation_handler",
                "no_status_center_write_side_effect",
            ],
            "panel_row_count": len(rows),
            "panel_chain_card_count": 1,
            "blocked_symbols": [row["symbol"] for row in rows if row["blocked"]],
            "reviewable_symbols": [row["symbol"] for row in rows if row["hypothetically_reviewable"]],
            "target_table": "alert_readiness_audit_events",
            "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
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
            "actual_write_performed": False,
            "status_center_ui_implementation_authorized": False,
            "status_center_ui_implementation_execution_allowed": False,
            "status_center_ui_implementation_writes": False,
            "has_write_button": False,
            "has_execute_button": False,
            "has_hidden_mutation_handler": False,
            "has_status_center_write_side_effect": False,
            "status_center_panel_implementation_never_writes": True,
            "status_center_panel_implementation_never_authorizes": True,
            "doctrine_statement": "Operator control is evidence, not a score.",
        },
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": [],
        "table_exists": True,
        "all_proposed_columns_exist": True,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "panel_validation_failure_count": 0,
        "panel_validation_failures": [],
    }
def test_visual_smoke_test_passes_for_read_only_panel_model():
    wiring_payload = _wiring_payload([
        _panel_row("SPY", blocked=True),
        _panel_row("QQQ", blocked=True),
    ])
    result = build_read_only_status_center_frontend_visual_smoke_test_from_wiring(
        wiring_payload=wiring_payload,
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_AUDIT_READ_ONLY"
    assert result["visual_smoke_test_schema_version"] == "controlled_persistence_status_center_frontend_visual_smoke_test_v1"
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
    assert result["visual_smoke_test_authorized"] is False
    assert result["visual_smoke_test_execution_allowed"] is False
    assert result["visual_smoke_test_mutation_authorized"] is False
    assert result["visual_smoke_pass"] is True
    assert result["visual_smoke_failure_count"] == 0
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_audit_status"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_PASS_READ_ONLY"
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_is_read_only"] is True
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_never_writes"] is True
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_never_authorizes"] is True
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_has_no_write_button"] is True
    assert result["has_write_button"] is False
    assert result["has_execute_button"] is False
    assert result["has_hidden_mutation_handler"] is False
    assert result["has_status_center_write_side_effect"] is False
    assert "no_write_button" in result["prohibited_ui_actions"]
    assert "VIEW_ONLY" in result["allowed_ui_actions"]
    assert "COPY_REVIEW_PACKET" in result["allowed_ui_actions"]
    assert "REFRESH_READ_ONLY" in result["allowed_ui_actions"]
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
def test_visual_smoke_test_blocks_if_write_button_present():
    wiring_payload = _wiring_payload([
        _panel_row("SPY", blocked=False),
    ])
    wiring_payload["status_center_panel_model"]["has_write_button"] = True
    result = build_read_only_status_center_frontend_visual_smoke_test_from_wiring(
        wiring_payload=wiring_payload,
    )
    assert result["visual_smoke_pass"] is False
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_audit_status"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_BLOCKED_READ_ONLY"
    assert "PANEL_WRITE_BUTTON_PRESENT_DRIFT" in result["visual_smoke_failures"]
    assert result["writes_to_supabase"] is False
    assert result["actual_write_performed"] is False
    assert result["visual_smoke_test_authorized"] is False
    assert result["visual_smoke_test_execution_allowed"] is False
    assert result["visual_smoke_test_mutation_authorized"] is False
    assert result["controlled_persistence_status_center_frontend_visual_smoke_test_never_writes"] is True
if __name__ == "__main__":
    test_visual_smoke_test_passes_for_read_only_panel_model()
    test_visual_smoke_test_blocks_if_write_button_present()
    print("CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_AUDIT_MANUAL_TESTS_PASS")
