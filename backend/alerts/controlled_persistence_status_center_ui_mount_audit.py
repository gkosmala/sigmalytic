from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_decision_console_frontend_contract_audit import (
    run_read_only_controlled_persistence_decision_console_frontend_contract_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_status_center_ui_mount_audit_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
STATUS_CENTER_UI_MOUNT_SCHEMA_VERSION = "controlled_persistence_status_center_ui_mount_v1"
STATUS_CENTER_MOUNT_ID = "alerts.controlledPersistenceDecisionConsole"
STATUS_CENTER_PANEL_TITLE = "Controlled Persistence Decision Console"
STATUS_CENTER_SOURCE_ENDPOINT = "/api/alerts/read-only/controlled-persistence-decision-console-frontend-contract-audit"
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
    "status_center_ui_mount_authorized": False,
    "status_center_ui_mutation_authorized": False,
    "status_center_ui_execution_allowed": False,
}
STATUS_CENTER_REQUIRED_MOUNT_PROPS = [
    "status_center_mount_id",
    "status_center_panel_title",
    "status_center_source_endpoint",
    "status_center_ui_mount_schema_version",
    "summary_panel",
    "chain_cards",
    "decision_rows",
    "mount_status_badges",
    "mount_allowed_ui_actions",
    "mount_prohibited_ui_actions",
    "blocked_symbols",
    "reviewable_symbols",
    "target_table",
    "schema_probe_status",
    "explicit_human_approval_required_before_any_write",
    "doctrine_statement",
    "guardrails",
]
STATUS_CENTER_ALLOWED_UI_ACTIONS = [
    "VIEW_ONLY",
    "COPY_REVIEW_PACKET",
    "REFRESH_READ_ONLY",
]
STATUS_CENTER_MOUNT_STATUS_BADGES = [
    "READ_ONLY_UI_MOUNT",
    "NO_DATABASE_WRITE",
    "NO_SUPABASE_INSERT",
    "NO_CAMPAIGN_MUTATION",
    "NO_OPERATOR_CONTROL_CONFIRMATION",
    "NO_D3D_AUTHORIZATION",
    "NO_TRADE_SIGNAL",
    "HUMAN_APPROVAL_REQUIRED_BEFORE_WRITE",
]
STATUS_CENTER_ALLOWED_PANELS = [
    "summary_panel",
    "read_only_status_badge_row",
    "audit_chain_cards",
    "symbol_decision_table",
    "blocker_list",
    "target_table_panel",
    "schema_probe_panel",
    "doctrine_panel",
    "absolute_prohibition_panel",
    "human_approval_required_banner",
]
ABSOLUTE_STATUS_CENTER_UI_PROHIBITIONS = [
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
def _mount_summary_panel(frontend_contract: Dict[str, Any]) -> Dict[str, Any]:
    summary = frontend_contract.get("summary_panel")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "mount_id": STATUS_CENTER_MOUNT_ID,
        "title": STATUS_CENTER_PANEL_TITLE,
        "subtitle": "Display-only Status Center mount for controlled persistence readiness.",
        "source_endpoint": STATUS_CENTER_SOURCE_ENDPOINT,
        "frontend_contract_status": frontend_contract.get("controlled_persistence_decision_console_frontend_contract_audit_status"),
        "decision_console_status": frontend_contract.get("controlled_persistence_decision_console_audit_status"),
        "target_table": frontend_contract.get("target_table"),
        "table_exists": frontend_contract.get("table_exists") is True,
        "all_proposed_columns_exist": frontend_contract.get("all_proposed_columns_exist") is True,
        "schema_probe_status": frontend_contract.get("schema_probe_status"),
        "schema_probe_method": frontend_contract.get("schema_probe_method"),
        "audited_symbol_count": _as_int(summary.get("audited_symbol_count") or frontend_contract.get("frontend_contract_row_count")),
        "reviewable_symbol_count": _as_int(frontend_contract.get("frontend_contract_reviewable_symbol_count")),
        "blocked_symbol_count": _as_int(frontend_contract.get("frontend_contract_blocked_symbol_count")),
        "reviewable_symbols": list(frontend_contract.get("reviewable_symbols") or []),
        "blocked_symbols": list(frontend_contract.get("blocked_symbols") or []),
        "mount_status_badges": list(STATUS_CENTER_MOUNT_STATUS_BADGES),
        "allowed_ui_actions": list(STATUS_CENTER_ALLOWED_UI_ACTIONS),
        "prohibited_ui_actions": list(ABSOLUTE_STATUS_CENTER_UI_PROHIBITIONS),
        "explicit_human_approval_required_before_any_write": True,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "not_a_trade_signal": True,
    }
def _mount_chain_cards(frontend_contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for card in _as_list(frontend_contract.get("chain_cards")):
        if not isinstance(card, dict):
            continue
        cards.append(
            {
                "mount_id": STATUS_CENTER_MOUNT_ID,
                "name": card.get("name"),
                "status": card.get("status"),
                "display_label": card.get("display_label"),
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
        )
    return cards
def _mount_decision_row(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    return {
        "mount_id": STATUS_CENTER_MOUNT_ID,
        "symbol": symbol,
        "row_key": f"status-center-controlled-persistence-{symbol}",
        "render_component": "StatusCenterReadOnlyDecisionRow",
        "card_title": row.get("card_title") or f"{symbol} Controlled Persistence Decision",
        "status_badge": row.get("status_badge"),
        "severity": row.get("severity"),
        "primary_message": row.get("primary_message"),
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
        "allowed_ui_actions": list(STATUS_CENTER_ALLOWED_UI_ACTIONS),
        "prohibited_ui_actions": list(ABSOLUTE_STATUS_CENTER_UI_PROHIBITIONS),
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
        "status_center_ui_mount_authorized": False,
        "status_center_ui_mutation_authorized": False,
        "status_center_ui_execution_allowed": False,
    }
def build_read_only_controlled_persistence_status_center_ui_mount_from_frontend_contract(
    *,
    frontend_contract: Dict[str, Any],
) -> Dict[str, Any]:
    frontend_rows = _as_list(frontend_contract.get("decision_rows"))
    mount_rows = [
        _mount_decision_row(row)
        for row in frontend_rows
        if isinstance(row, dict)
    ]
    reviewable_rows = [
        row for row in mount_rows
        if row["hypothetically_reviewable"] is True
    ]
    blocked_rows = [
        row for row in mount_rows
        if row["blocked"] is True
    ]
    guardrail_failure_count = _as_int(frontend_contract.get("guardrail_failure_count"))
    frontend_contract_status = str(
        frontend_contract.get("controlled_persistence_decision_console_frontend_contract_audit_status") or ""
    )
    frontend_contract_renderable = frontend_contract_status in {
        "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY",
        "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_FRONTEND_CONTRACT_BLOCKED_READ_ONLY",
    }
    ui_mount_ready = bool(mount_rows) and frontend_contract_renderable and guardrail_failure_count == 0
    ui_mount_status = (
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_READY_READ_ONLY"
        if ui_mount_ready
        else "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_BLOCKED_READ_ONLY"
    )
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "status_center_ui_mount_schema_version": STATUS_CENTER_UI_MOUNT_SCHEMA_VERSION,
        "status_center_mount_id": STATUS_CENTER_MOUNT_ID,
        "status_center_panel_title": STATUS_CENTER_PANEL_TITLE,
        "status_center_source_endpoint": STATUS_CENTER_SOURCE_ENDPOINT,
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
        "controlled_persistence_status_center_ui_mount_audit_status": ui_mount_status,
        "controlled_persistence_decision_console_frontend_contract_audit_status": frontend_contract.get("controlled_persistence_decision_console_frontend_contract_audit_status"),
        "controlled_persistence_decision_console_audit_status": frontend_contract.get("controlled_persistence_decision_console_audit_status"),
        "controlled_append_only_write_approval_packet_audit_status": frontend_contract.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": frontend_contract.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": frontend_contract.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": frontend_contract.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": frontend_contract.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": frontend_contract.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": frontend_contract.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": frontend_contract.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": frontend_contract.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": frontend_contract.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": frontend_contract.get("source_coverage_completion_status"),
        "frontend_contract_schema_version": frontend_contract.get("frontend_contract_schema_version"),
        "status_center_required_mount_props": list(STATUS_CENTER_REQUIRED_MOUNT_PROPS),
        "mount_status_badges": list(STATUS_CENTER_MOUNT_STATUS_BADGES),
        "status_center_allowed_panels": list(STATUS_CENTER_ALLOWED_PANELS),
        "mount_allowed_ui_actions": list(STATUS_CENTER_ALLOWED_UI_ACTIONS),
        "mount_prohibited_ui_actions": list(ABSOLUTE_STATUS_CENTER_UI_PROHIBITIONS),
        "summary_panel": _mount_summary_panel(frontend_contract),
        "chain_cards": _mount_chain_cards(frontend_contract),
        "decision_rows": mount_rows,
        "blocked_symbols": [row["symbol"] for row in blocked_rows],
        "reviewable_symbols": [row["symbol"] for row in reviewable_rows],
        "status_center_ui_mount_row_count": len(mount_rows),
        "status_center_ui_mount_reviewable_symbol_count": len(reviewable_rows),
        "status_center_ui_mount_blocked_symbol_count": len(blocked_rows),
        "status_center_mount_point": STATUS_CENTER_MOUNT_ID,
        "status_center_render_mode": "READ_ONLY_REVIEW_PANEL",
        "status_center_refresh_mode": "READ_ONLY_ENDPOINT_REFRESH_ONLY",
        "target_table": frontend_contract.get("target_table"),
        "proposed_columns": list(frontend_contract.get("proposed_columns") or []),
        "missing_proposed_columns": list(frontend_contract.get("missing_proposed_columns") or []),
        "table_exists": frontend_contract.get("table_exists") is True,
        "all_proposed_columns_exist": frontend_contract.get("all_proposed_columns_exist") is True,
        "schema_probe_status": frontend_contract.get("schema_probe_status"),
        "schema_probe_method": frontend_contract.get("schema_probe_method"),
        "schema_probe_is_read_only": frontend_contract.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(frontend_contract.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_status_center_ui_mount_applies_no_changes": True,
        "controlled_persistence_status_center_ui_mount_is_read_only": True,
        "controlled_persistence_status_center_ui_mount_never_writes": True,
        "controlled_persistence_status_center_ui_mount_never_authorizes": True,
        "controlled_persistence_status_center_ui_mount_has_no_write_button": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_status_center_ui_mount_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    frontend_contract = run_read_only_controlled_persistence_decision_console_frontend_contract_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_status_center_ui_mount_from_frontend_contract(
        frontend_contract=frontend_contract,
    )
