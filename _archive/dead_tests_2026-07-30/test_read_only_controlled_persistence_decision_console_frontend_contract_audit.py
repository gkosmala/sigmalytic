from __future__ import annotations
from backend.alerts.controlled_persistence_decision_console_frontend_contract_audit import (
    build_read_only_controlled_persistence_decision_console_frontend_contract_from_console,
)
def _base_console(rows):
    return {
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
        "audited_symbol_count": len(rows),
        "decision_console_reviewable_symbol_count": 0,
        "decision_console_blocked_symbol_count": len(rows),
        "decision_console_reviewable_symbols": [],
        "decision_console_blocked_symbols": [row["symbol"] for row in rows],
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": ["symbol"],
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "schema_probe_status": "SUPABASE_TARGET_TABLE_NOT_FOUND_READ_ONLY",
        "schema_probe_method": "POSTGREST_GET_LIMIT_ZERO_READ_ONLY",
        "schema_probe_is_read_only": True,
        "explicit_human_approval_required_before_any_write": True,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "console_cards": [
            {
                "name": "source_coverage_completion",
                "status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
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
        "controlled_persistence_decision_console_rows": rows,
    }
def _blocked_row(symbol):
    return {
        "symbol": symbol,
        "final_console_decision_status": "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY",
        "final_console_decision_label": "Blocked; review blockers before any write can be considered.",
        "blocked": True,
        "hypothetically_reviewable": False,
        "console_blockers": ["APPROVAL_PACKET_NOT_COMPLETE_READ_ONLY"],
        "approval_packet_status": "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY",
        "approval_packet_blockers": ["APPEND_ONLY_PREFLIGHT_NOT_CLEAR_READ_ONLY"],
        "approval_payload_preview": {"symbol": symbol},
        "append_only_write_preflight_status": "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY",
        "append_only_write_preflight_hypothetically_clear": False,
        "preflight_blockers": ["SUPABASE_SCHEMA_EXISTENCE_NOT_READY_READ_ONLY"],
        "target_table": "alert_readiness_audit_events",
        "proposed_columns": ["symbol", "audit_component"],
        "missing_proposed_columns": ["symbol"],
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "explicit_human_approval_required_before_any_write": True,
        "actual_write_performed": False,
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
    }
def test_frontend_contract_renders_blocked_console_no_drift():
    console = _base_console([_blocked_row("SPY"), _blocked_row("QQQ")])
    result = build_read_only_controlled_persistence_decision_console_frontend_contract_from_console(
        console=console,
    )
    assert result["ok"] is True
    assert result["component"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY"
    assert result["frontend_contract_schema_version"] == "controlled_persistence_decision_console_frontend_contract_v1"
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
    assert result["frontend_contract_authorized"] is False
    assert result["frontend_mutation_authorized"] is False
    assert result["frontend_execution_allowed"] is False
    assert result["controlled_persistence_decision_console_frontend_contract_audit_status"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY"
    assert result["frontend_contract_blocked_symbol_count"] == 2
    assert result["blocked_symbols"] == ["SPY", "QQQ"]
    assert result["controlled_persistence_decision_console_frontend_contract_is_read_only"] is True
    assert result["controlled_persistence_decision_console_frontend_contract_never_writes"] is True
    assert result["controlled_persistence_decision_console_frontend_contract_never_authorizes"] is True
    assert "no_write_button" in result["absolute_frontend_prohibitions"]
    assert "Operator control is evidence, not a score" in result["doctrine_statement"]
def test_frontend_contract_renders_reviewable_console_but_no_authorization_no_drift():
    row = _blocked_row("SPY")
    row["final_console_decision_status"] = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
    row["final_console_decision_label"] = "Reviewable; explicit human approval still required before any write."
    row["blocked"] = False
    row["hypothetically_reviewable"] = True
    row["console_blockers"] = ["NO_CONSOLE_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY"]
    row["table_exists"] = True
    row["all_proposed_columns_exist"] = True
    row["missing_proposed_columns"] = []
    console = _base_console([row])
    console["controlled_persistence_decision_console_audit_status"] = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
    console["decision_console_reviewable_symbol_count"] = 1
    console["decision_console_blocked_symbol_count"] = 0
    console["decision_console_reviewable_symbols"] = ["SPY"]
    console["decision_console_blocked_symbols"] = []
    console["missing_proposed_columns"] = []
    console["table_exists"] = True
    console["all_proposed_columns_exist"] = True
    console["schema_probe_status"] = "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY"
    result = build_read_only_controlled_persistence_decision_console_frontend_contract_from_console(
        console=console,
    )
    assert result["controlled_persistence_decision_console_frontend_contract_audit_status"] == "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY"
    assert result["frontend_contract_reviewable_symbol_count"] == 1
    assert result["reviewable_symbols"] == ["SPY"]
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
    frontend_row = result["decision_rows"][0]
    assert frontend_row["allowed_ui_actions"] == ["VIEW_ONLY", "COPY_REVIEW_PACKET"]
    assert "no_confirm_operator_control_button" in frontend_row["prohibited_ui_actions"]
    assert frontend_row["writes_to_supabase"] is False
    assert frontend_row["actual_write_performed"] is False
if __name__ == "__main__":
    test_frontend_contract_renders_blocked_console_no_drift()
    test_frontend_contract_renders_reviewable_console_but_no_authorization_no_drift()
    print("CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_AUDIT_MANUAL_TESTS_PASS")
