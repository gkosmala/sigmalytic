from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_decision_console_audit import (
    run_read_only_controlled_persistence_decision_console_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_decision_console_frontend_contract_audit_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
GUARDRAILS: Dict[str, Any] = {
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
FRONTEND_CONTRACT_SCHEMA_VERSION = "controlled_persistence_decision_console_frontend_contract_v1"
FRONTEND_CONTRACT_REQUIRED_PROPS = [
    "component",
    "version",
    "frontend_contract_schema_version",
    "summary_panel",
    "chain_cards",
    "decision_rows",
    "status_badges",
    "blocked_symbols",
    "reviewable_symbols",
    "target_table",
    "schema_probe_status",
    "explicit_human_approval_required_before_any_write",
    "absolute_frontend_prohibitions",
    "doctrine_statement",
    "guardrails",
]
FRONTEND_STATUS_BADGES = [
    "READ_ONLY",
    "NO_DATABASE_WRITE",
    "NO_SUPABASE_INSERT",
    "NO_CAMPAIGN_MUTATION",
    "NO_OPERATOR_CONTROL_CONFIRMATION",
    "NO_D3D_AUTHORIZATION",
    "NO_TRADE_SIGNAL",
    "HUMAN_APPROVAL_REQUIRED_BEFORE_WRITE",
]
FRONTEND_ALLOWED_DISPLAY_COMPONENTS = [
    "summary_panel",
    "audit_chain_cards",
    "symbol_decision_table",
    "blocker_list",
    "target_table_panel",
    "doctrine_panel",
    "absolute_prohibition_panel",
    "human_approval_required_banner",
]
ABSOLUTE_FRONTEND_PROHIBITIONS = [
    "no_write_button",
    "no_execute_button",
    "no_confirm_operator_control_button",
    "no_confirm_composite_operator_control_button",
    "no_authorize_d3d_button",
    "no_trade_signal_button",
    "no_score_rank_state_probability_or_edge_change",
    "no_supabase_insert_update_upsert_delete_rpc",
    "no_campaign_table_mutation",
]
def _guardrails() -> Dict[str, Any]:
    payload = dict(GUARDRAILS)
    payload["component"] = COMPONENT
    payload["version"] = VERSION
    return payload
def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []
def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0
def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _severity_for_row(row: Dict[str, Any]) -> str:
    if row.get("hypothetically_reviewable") is True:
        return "REVIEWABLE_READ_ONLY"
    return "BLOCKED_READ_ONLY"
def _primary_message_for_row(row: Dict[str, Any]) -> str:
    if row.get("hypothetically_reviewable") is True:
        return "Reviewable in the decision console, but explicit human approval is still required before any future write."
    return "Blocked in the decision console. Review blockers before any future write can be considered."
def _frontend_summary_panel(console: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": "Controlled Persistence Decision Console",
        "subtitle": "Read-only frontend contract for reviewing controlled persistence readiness without writing.",
        "controlled_persistence_decision_console_audit_status": console.get("controlled_persistence_decision_console_audit_status"),
        "audited_symbol_count": _as_int(console.get("audited_symbol_count")),
        "reviewable_symbol_count": _as_int(console.get("decision_console_reviewable_symbol_count")),
        "blocked_symbol_count": _as_int(console.get("decision_console_blocked_symbol_count")),
        "reviewable_symbols": list(console.get("decision_console_reviewable_symbols") or []),
        "blocked_symbols": list(console.get("decision_console_blocked_symbols") or []),
        "target_table": console.get("target_table"),
        "table_exists": console.get("table_exists") is True,
        "all_proposed_columns_exist": console.get("all_proposed_columns_exist") is True,
        "schema_probe_status": console.get("schema_probe_status"),
        "explicit_human_approval_required_before_any_write": True,
        "status_badges": list(FRONTEND_STATUS_BADGES),
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "not_a_trade_signal": True,
    }
def _frontend_chain_cards(console: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for card in _as_list(console.get("console_cards")):
        if not isinstance(card, dict):
            continue
        cards.append(
            {
                "name": card.get("name"),
                "status": card.get("status"),
                "display_label": str(card.get("name") or "").replace("_", " ").title(),
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
        )
    return cards
def _frontend_decision_row(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    severity = _severity_for_row(row)
    return {
        "symbol": symbol,
        "row_key": f"controlled-persistence-decision-console-{symbol}",
        "card_title": f"{symbol} Controlled Persistence Decision",
        "status_badge": row.get("final_console_decision_status"),
        "severity": severity,
        "primary_message": _primary_message_for_row(row),
        "final_console_decision_status": row.get("final_console_decision_status"),
        "final_console_decision_label": row.get("final_console_decision_label"),
        "blocked": row.get("blocked") is True,
        "hypothetically_reviewable": row.get("hypothetically_reviewable") is True,
        "console_blockers": list(row.get("console_blockers") or []),
        "approval_packet_status": row.get("approval_packet_status"),
        "approval_packet_blockers": list(row.get("approval_packet_blockers") or []),
        "append_only_write_preflight_status": row.get("append_only_write_preflight_status"),
        "preflight_blockers": list(row.get("preflight_blockers") or []),
        "target_table": row.get("target_table"),
        "proposed_columns": list(row.get("proposed_columns") or []),
        "missing_proposed_columns": list(row.get("missing_proposed_columns") or []),
        "table_exists": row.get("table_exists") is True,
        "all_proposed_columns_exist": row.get("all_proposed_columns_exist") is True,
        "explicit_human_approval_required_before_any_write": True,
        "allowed_ui_actions": ["VIEW_ONLY", "COPY_REVIEW_PACKET"],
        "prohibited_ui_actions": list(ABSOLUTE_FRONTEND_PROHIBITIONS),
        "doctrine_statement": DOCTRINE_STATEMENT,
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
def build_read_only_controlled_persistence_decision_console_frontend_contract_from_console(
    *,
    console: Dict[str, Any],
) -> Dict[str, Any]:
    console_rows = _as_list(console.get("controlled_persistence_decision_console_rows"))
    frontend_rows = [
        _frontend_decision_row(row)
        for row in console_rows
        if isinstance(row, dict)
    ]
    reviewable_rows = [
        row for row in frontend_rows
        if row["hypothetically_reviewable"] is True
    ]
    blocked_rows = [
        row for row in frontend_rows
        if row["blocked"] is True
    ]
    guardrail_failure_count = _as_int(console.get("guardrail_failure_count"))
    frontend_contract_audit_status = (
        "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY"
        if frontend_rows and guardrail_failure_count == 0
        else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_BLOCKED_READ_ONLY"
    )
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "frontend_contract_schema_version": FRONTEND_CONTRACT_SCHEMA_VERSION,
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
        "controlled_persistence_decision_console_frontend_contract_audit_status": frontend_contract_audit_status,
        "controlled_persistence_decision_console_audit_status": console.get("controlled_persistence_decision_console_audit_status"),
        "controlled_append_only_write_approval_packet_audit_status": console.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": console.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": console.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": console.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": console.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": console.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": console.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": console.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": console.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": console.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": console.get("source_coverage_completion_status"),
        "frontend_contract_required_props": list(FRONTEND_CONTRACT_REQUIRED_PROPS),
        "frontend_status_badges": list(FRONTEND_STATUS_BADGES),
        "frontend_allowed_display_components": list(FRONTEND_ALLOWED_DISPLAY_COMPONENTS),
        "absolute_frontend_prohibitions": list(ABSOLUTE_FRONTEND_PROHIBITIONS),
        "summary_panel": _frontend_summary_panel(console),
        "chain_cards": _frontend_chain_cards(console),
        "decision_rows": frontend_rows,
        "blocked_symbols": [row["symbol"] for row in blocked_rows],
        "reviewable_symbols": [row["symbol"] for row in reviewable_rows],
        "frontend_contract_row_count": len(frontend_rows),
        "frontend_contract_reviewable_symbol_count": len(reviewable_rows),
        "frontend_contract_blocked_symbol_count": len(blocked_rows),
        "status_center_mount_suggestion": "alerts.controlledPersistenceDecisionConsole",
        "frontend_contract_display_mode": "READ_ONLY_REVIEW_CONSOLE",
        "target_table": console.get("target_table"),
        "proposed_columns": list(console.get("proposed_columns") or []),
        "missing_proposed_columns": list(console.get("missing_proposed_columns") or []),
        "table_exists": console.get("table_exists") is True,
        "all_proposed_columns_exist": console.get("all_proposed_columns_exist") is True,
        "schema_probe_status": console.get("schema_probe_status"),
        "schema_probe_method": console.get("schema_probe_method"),
        "schema_probe_is_read_only": console.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(console.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_decision_console_frontend_contract_applies_no_changes": True,
        "controlled_persistence_decision_console_frontend_contract_is_read_only": True,
        "controlled_persistence_decision_console_frontend_contract_never_writes": True,
        "controlled_persistence_decision_console_frontend_contract_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_decision_console_frontend_contract_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    console = run_read_only_controlled_persistence_decision_console_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_decision_console_frontend_contract_from_console(
        console=console,
    )
