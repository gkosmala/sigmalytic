from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_append_only_write_approval_packet_audit import (
    run_read_only_controlled_append_only_write_approval_packet_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_decision_console_audit_read_only_v1"
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
}
CONSOLE_CHAIN_STEPS = [
    "source_coverage_completion",
    "evidence_payload_completeness",
    "operator_control_evidence",
    "d3d_dry_run_gate",
    "controlled_persistence_contract",
    "controlled_persistence_activation_readiness",
    "write_permission_manifest",
    "persistence_payload_simulation",
    "supabase_target_table_schema_existence",
    "append_only_write_preflight_authorization_gate",
    "controlled_append_only_write_approval_packet",
]
CONSOLE_DECISION_FIELDS = [
    "symbol",
    "final_console_decision_status",
    "final_console_decision_label",
    "blocked",
    "hypothetically_reviewable",
    "explicit_human_approval_required_before_any_write",
    "target_table",
    "table_exists",
    "all_proposed_columns_exist",
    "approval_packet_status",
    "approval_packet_blockers",
    "absolute_prohibitions",
    "doctrine_statement",
]
ABSOLUTE_CONSOLE_PROHIBITIONS = [
    "no_database_write_from_console",
    "no_supabase_insert_from_console",
    "no_supabase_update_from_console",
    "no_supabase_upsert_from_console",
    "no_supabase_delete_from_console",
    "no_supabase_rpc_from_console",
    "no_campaign_table_mutation",
    "no_operator_control_confirmation",
    "no_composite_operator_control_confirmation",
    "no_d3d_authorization",
    "no_trade_signal",
    "no_score_rank_state_probability_or_edge_change",
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
def _chain_card(
    *,
    name: str,
    status: Any,
    read_only: bool = True,
    writes_to_supabase: bool = False,
    mutates_campaigns: bool = False,
    authorizes_d3d: bool = False,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "diagnostic_only": True,
        "read_only": read_only,
        "writes_to_supabase": writes_to_supabase,
        "mutates_campaigns": mutates_campaigns,
        "authorizes_d3d": authorizes_d3d,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
    }
def _console_cards(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        _chain_card(name="source_coverage_completion", status=packet.get("source_coverage_completion_status")),
        _chain_card(name="evidence_payload_completeness", status=packet.get("evidence_payload_completeness_status")),
        _chain_card(name="operator_control_evidence", status=packet.get("operator_control_evidence_audit_status")),
        _chain_card(name="d3d_dry_run_gate", status=packet.get("d3d_dry_run_gate_audit_status")),
        _chain_card(name="controlled_persistence_contract", status=packet.get("controlled_persistence_contract_audit_status")),
        _chain_card(name="controlled_persistence_activation_readiness", status=packet.get("controlled_persistence_activation_readiness_audit_status")),
        _chain_card(name="write_permission_manifest", status=packet.get("write_permission_manifest_audit_status")),
        _chain_card(name="persistence_payload_simulation", status=packet.get("persistence_payload_simulation_audit_status")),
        _chain_card(name="supabase_target_table_schema_existence", status=packet.get("supabase_target_table_schema_existence_audit_status")),
        _chain_card(name="append_only_write_preflight_authorization_gate", status=packet.get("append_only_write_preflight_authorization_gate_status")),
        _chain_card(name="controlled_append_only_write_approval_packet", status=packet.get("controlled_append_only_write_approval_packet_audit_status")),
    ]
def _decision_row(row: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    approval_complete = row.get("approval_packet_hypothetically_complete") is True
    guardrail_clear = _as_int(packet.get("guardrail_failure_count")) == 0
    human_approval_required = packet.get("explicit_human_approval_required_before_any_write") is True
    blockers: List[str] = []
    if not approval_complete:
        blockers.append("APPROVAL_PACKET_NOT_COMPLETE_READ_ONLY")
    if not guardrail_clear:
        blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if not human_approval_required:
        blockers.append("EXPLICIT_HUMAN_APPROVAL_REQUIREMENT_MISSING_READ_ONLY")
    if row.get("actual_write_performed") is not False:
        blockers.append("ACTUAL_WRITE_NOT_ALLOWED_READ_ONLY")
    if row.get("approval_packet_authorized") is not False:
        blockers.append("APPROVAL_PACKET_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("approval_packet_write_authorized") is not False:
        blockers.append("APPROVAL_PACKET_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("append_only_write_execution_allowed") is not False:
        blockers.append("APPEND_ONLY_WRITE_EXECUTION_NOT_ALLOWED_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    hypothetically_reviewable = approval_complete and guardrail_clear and human_approval_required and not blockers
    final_status = (
        "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if hypothetically_reviewable
        else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY"
    )
    final_label = (
        "Reviewable; explicit human approval still required before any write."
        if hypothetically_reviewable
        else "Blocked; review blockers before any write can be considered."
    )
    if not blockers:
        blockers.append("NO_CONSOLE_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "final_console_decision_status": final_status,
        "final_console_decision_label": final_label,
        "blocked": not hypothetically_reviewable,
        "hypothetically_reviewable": hypothetically_reviewable,
        "decision_console_authorized": False,
        "decision_console_execution_allowed": False,
        "approval_packet_authorized": False,
        "approval_packet_write_authorized": False,
        "append_only_write_preflight_authorized": False,
        "append_only_write_preflight_gate_clear": False,
        "append_only_write_execution_allowed": False,
        "schema_existence_audit_authorized": False,
        "schema_write_authorized": False,
        "simulated_write_only": True,
        "actual_write_performed": False,
        "write_permission_manifest_authorized": False,
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "persistence_activation_authorized": False,
        "production_activation_authorized": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "console_blockers": blockers,
        "approval_packet_status": row.get("controlled_append_only_write_approval_packet_status"),
        "approval_packet_hypothetically_complete": approval_complete,
        "approval_packet_blockers": list(row.get("approval_packet_blockers") or []),
        "approval_payload_preview": row.get("approval_payload_preview") or {},
        "append_only_write_preflight_status": row.get("append_only_write_preflight_status"),
        "append_only_write_preflight_hypothetically_clear": row.get("append_only_write_preflight_hypothetically_clear") is True,
        "preflight_blockers": list(row.get("preflight_blockers") or []),
        "target_table": row.get("target_table"),
        "proposed_columns": list(row.get("proposed_columns") or []),
        "missing_proposed_columns": list(row.get("missing_proposed_columns") or []),
        "table_exists": row.get("table_exists") is True,
        "all_proposed_columns_exist": row.get("all_proposed_columns_exist") is True,
        "explicit_human_approval_required_before_any_write": True,
        "console_decision_fields": list(CONSOLE_DECISION_FIELDS),
        "absolute_console_prohibitions": list(ABSOLUTE_CONSOLE_PROHIBITIONS),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
    }
def build_read_only_controlled_persistence_decision_console_from_approval_packet(
    *,
    approval_packet: Dict[str, Any],
) -> Dict[str, Any]:
    approval_rows = _as_list(approval_packet.get("controlled_append_only_write_approval_packet_rows"))
    decision_rows = [
        _decision_row(row, approval_packet)
        for row in approval_rows
        if isinstance(row, dict)
    ]
    reviewable_rows = [
        row for row in decision_rows
        if row["hypothetically_reviewable"] is True
    ]
    blocked_rows = [
        row for row in decision_rows
        if row["blocked"] is True
    ]
    guardrail_failure_count = _as_int(approval_packet.get("guardrail_failure_count"))
    console_status = (
        "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if decision_rows and not blocked_rows and guardrail_failure_count == 0
        else "CONTROLLED_PERSISTENCE_DECISION_CONSOLE_BLOCKED_READ_ONLY"
    )
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
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
        "controlled_persistence_decision_console_audit_status": console_status,
        "controlled_append_only_write_approval_packet_audit_status": approval_packet.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": approval_packet.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": approval_packet.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": approval_packet.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": approval_packet.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": approval_packet.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": approval_packet.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": approval_packet.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": approval_packet.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": approval_packet.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": approval_packet.get("source_coverage_completion_status"),
        "console_chain_steps": list(CONSOLE_CHAIN_STEPS),
        "console_cards": _console_cards(approval_packet),
        "console_decision_fields": list(CONSOLE_DECISION_FIELDS),
        "absolute_console_prohibitions": list(ABSOLUTE_CONSOLE_PROHIBITIONS),
        "coverage_is_complete": approval_packet.get("coverage_is_complete") is True,
        "requested_symbols": approval_packet.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(approval_packet.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(approval_packet.get("audited_symbol_count")),
        "controlled_persistence_decision_console_row_count": len(decision_rows),
        "decision_console_reviewable_symbol_count": len(reviewable_rows),
        "decision_console_blocked_symbol_count": len(blocked_rows),
        "decision_console_reviewable_symbols": [row["symbol"] for row in reviewable_rows],
        "decision_console_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "target_table": approval_packet.get("target_table"),
        "proposed_columns": list(approval_packet.get("proposed_columns") or []),
        "missing_proposed_columns": list(approval_packet.get("missing_proposed_columns") or []),
        "table_exists": approval_packet.get("table_exists") is True,
        "all_proposed_columns_exist": approval_packet.get("all_proposed_columns_exist") is True,
        "schema_probe_status": approval_packet.get("schema_probe_status"),
        "schema_probe_method": approval_packet.get("schema_probe_method"),
        "schema_probe_is_read_only": approval_packet.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "controlled_persistence_decision_console_rows": decision_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(approval_packet.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_decision_console_applies_no_changes": True,
        "controlled_persistence_decision_console_is_read_only": True,
        "controlled_persistence_decision_console_never_writes": True,
        "controlled_persistence_decision_console_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_decision_console_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    approval_packet = run_read_only_controlled_append_only_write_approval_packet_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_decision_console_from_approval_packet(
        approval_packet=approval_packet,
    )
