from __future__ import annotations
from backend.alerts.controlled_persistence_status_center_ui_mount_audit import (
    build_read_only_controlled_persistence_status_center_ui_mount_from_frontend_contract,
)
def _frontend_row(symbol, *, blocked=True):
    return {
        "symbol": symbol,
        "row_key": f"controlled-persistence-decision-console-{symbol}",
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
        "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET"],
        "prohibited_ui_actions": ["no_write_button"],
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
    }
def _frontend_contract(rows):
    return {
        "ok": True,
        "component": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY",
        "frontend_contract_schema_version": "controlled_persistence_decision_console_frontend_contract_v1",
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
        "summary_panel": {
            "audited_symbol_count": len(rows),
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
                "name": "source_coverage_completion",
                "status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
                "display_label": "Source Coverage Completion",
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
        "blocked_symbols": [row["symbol"] for row in rows if row["blocked"]],
        "reviewable_symbols": [row["symbol"] for row in rows if row["hypothetically_reviewable"]],
        "frontend_contract_row_count": len(rows),
        "frontend_contract_reviewable_symbol_count": len([row for row in rows if row["hypothetically_reviewable"]]),
        "frontend_contract_blocked_symbol_count": len([row for row in rows if row["blocked"]]),
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
def test_status_center_ui_mount_renders_blocked_rows_without_authorization_or_write():
    frontend_contract = _frontend_contract([
        _frontend_row("SPY", blocked=True),
        _frontend_row("QQQ", blocked=True),
    ])
    result = build_read_only_controlled_persistence_status_center_ui_mount_from_frontend_contract(
        frontend_contract=frontend_contract,
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_AUDIT_READ_ONLY"
    assert result["status_center_ui_mount_schema_version"] == "controlled_persistence_status_center_ui_mount_v1"
    assert result["status_center_mount_id"] == "alerts.controlledPersistenceDecisionConsole"
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
    assert result["status_center_ui_mount_authorized"] is False
    assert result["status_center_ui_mutation_authorized"] is False
    assert result["status_center_ui_execution_allowed"] is False
    assert result["controlled_persistence_status_center_ui_mount_audit_status"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_READY_READ_ONLY"
    assert result["controlled_persistence_status_center_ui_mount_is_read_only"] is True
    assert result["controlled_persistence_status_center_ui_mount_never_writes"] is True
    assert result["controlled_persistence_status_center_ui_mount_never_authorizes"] is True
    assert result["controlled_persistence_status_center_ui_mount_has_no_write_button"] is True
    assert result["blocked_symbols"] == ["SPY", "QQQ"]
    assert "no_write_button" in result["mount_prohibited_ui_actions"]
    assert "VIEW_ONLY" in result["mount_allowed_ui_actions"]
    assert "COPY_REVIEW_PACKET" in result["mount_allowed_ui_actions"]
    assert "REFRESH_READ_ONLY" in result["mount_allowed_ui_actions"]
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
def test_status_center_ui_mount_renders_reviewable_row_but_no_authorization_or_write():
    frontend_contract = _frontend_contract([
        _frontend_row("SPY", blocked=False),
    ])
    frontend_contract["controlled_persistence_decision_console_audit_status"] = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
    frontend_contract["blocked_symbols"] = []
    frontend_contract["reviewable_symbols"] = ["SPY"]
    frontend_contract["frontend_contract_reviewable_symbol_count"] = 1
    frontend_contract["frontend_contract_blocked_symbol_count"] = 0
    result = build_read_only_controlled_persistence_status_center_ui_mount_from_frontend_contract(
        frontend_contract=frontend_contract,
    )
    assert result["controlled_persistence_status_center_ui_mount_audit_status"] == "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_READY_READ_ONLY"
    assert result["reviewable_symbols"] == ["SPY"]
    assert result["status_center_ui_mount_reviewable_symbol_count"] == 1
    assert result["status_center_ui_mount_blocked_symbol_count"] == 0
    assert result["status_center_ui_mount_authorized"] is False
    assert result["status_center_ui_mutation_authorized"] is False
    assert result["status_center_ui_execution_allowed"] is False
    assert result["frontend_contract_authorized"] is False
    assert result["frontend_mutation_authorized"] is False
    assert result["frontend_execution_allowed"] is False
    assert result["persistence_write_authorized"] is False
    assert result["supabase_write_authorized"] is False
    assert result["campaign_mutation_authorized"] is False
    assert result["operator_control_confirmed"] is False
    assert result["composite_operator_control_confirmed"] is False
    assert result["d3d_execution_authorized"] is False
    assert result["can_execute_d3d"] is False
    assert result["actual_write_performed"] is False
    assert result["explicit_human_approval_required_before_any_write"] is True
    row = result["decision_rows"][0]
    assert row["allowed_ui_actions"] == ["VIEW_ONLY", "COPY_REVIEW_PACKET", "REFRESH_READ_ONLY"]
    assert "no_write_button" in row["prohibited_ui_actions"]
    assert row["writes_to_supabase"] is False
    assert row["actual_write_performed"] is False
    assert row["status_center_ui_mount_authorized"] is False
if __name__ == "__main__":
    test_status_center_ui_mount_renders_blocked_rows_without_authorization_or_write()
    test_status_center_ui_mount_renders_reviewable_row_but_no_authorization_or_write()
    print("CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_AUDIT_MANUAL_TESTS_PASS")
