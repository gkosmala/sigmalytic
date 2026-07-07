from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.supabase_append_only_write_preflight_authorization_gate import (
    run_read_only_supabase_append_only_write_preflight_authorization_gate,
)
COMPONENT = "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_AUDIT_READ_ONLY"
VERSION = "controlled_append_only_write_approval_packet_audit_read_only_v1"
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
}
APPROVAL_PACKET_SECTIONS = [
    "doctrine_boundary",
    "proposed_target_table",
    "proposed_columns",
    "proposed_payload_shape",
    "append_only_controls",
    "preflight_status",
    "required_human_approval",
    "absolute_prohibitions",
    "rollback_expectations",
    "write_limits_if_later_authorized",
]
APPROVAL_PACKET_ABSOLUTE_PROHIBITIONS = [
    "no_database_write_in_this_packet",
    "no_supabase_insert_in_this_packet",
    "no_supabase_update_in_this_packet",
    "no_supabase_upsert_in_this_packet",
    "no_supabase_delete_in_this_packet",
    "no_supabase_rpc_in_this_packet",
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
def _build_approval_payload_preview(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": _symbol(row.get("symbol")),
        "audit_component": COMPONENT,
        "audit_version": VERSION,
        "target_table": upstream.get("target_table"),
        "schema_probe_status": upstream.get("schema_probe_status"),
        "append_only_write_preflight_status": row.get("append_only_write_preflight_status"),
        "append_only_write_preflight_hypothetically_clear": row.get("append_only_write_preflight_hypothetically_clear") is True,
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "controlled_persistence_contract_audit_status": upstream.get("controlled_persistence_contract_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": upstream.get("controlled_persistence_activation_readiness_audit_status"),
        "write_permission_manifest_audit_status": upstream.get("write_permission_manifest_audit_status"),
        "persistence_payload_simulation_audit_status": upstream.get("persistence_payload_simulation_audit_status"),
        "supabase_target_table_schema_existence_audit_status": upstream.get("supabase_target_table_schema_existence_audit_status"),
        "append_only_write_preflight_authorization_gate_status": upstream.get("append_only_write_preflight_authorization_gate_status"),
        "preflight_blockers": list(row.get("preflight_blockers") or []),
        "append_only_controls": dict(row.get("append_only_controls") or {}),
        "absolute_preflight_prohibitions": list(row.get("absolute_preflight_prohibitions") or []),
        "approval_packet_absolute_prohibitions": list(APPROVAL_PACKET_ABSOLUTE_PROHIBITIONS),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "read_only_guardrails": _guardrails(),
        "created_by_read_only_approval_packet": True,
    }
def _approval_row(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    preflight_hypothetically_clear = row.get("append_only_write_preflight_hypothetically_clear") is True
    explicit_human_approval_required = upstream.get("explicit_human_approval_required_before_any_write") is True
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    approval_packet_blockers: List[str] = []
    if not preflight_hypothetically_clear:
        approval_packet_blockers.append("APPEND_ONLY_PREFLIGHT_NOT_CLEAR_READ_ONLY")
    if not explicit_human_approval_required:
        approval_packet_blockers.append("EXPLICIT_HUMAN_APPROVAL_REQUIREMENT_MISSING_READ_ONLY")
    if not guardrail_clear:
        approval_packet_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if row.get("actual_write_performed") is not False:
        approval_packet_blockers.append("ACTUAL_WRITE_NOT_ALLOWED_READ_ONLY")
    if row.get("append_only_write_preflight_authorized") is not False:
        approval_packet_blockers.append("PREFLIGHT_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("append_only_write_preflight_gate_clear") is not False:
        approval_packet_blockers.append("PREFLIGHT_GATE_CLEARANCE_NOT_ALLOWED_READ_ONLY")
    if row.get("append_only_write_execution_allowed") is not False:
        approval_packet_blockers.append("APPEND_ONLY_WRITE_EXECUTION_NOT_ALLOWED_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        approval_packet_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        approval_packet_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        approval_packet_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        approval_packet_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        approval_packet_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        approval_packet_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    approval_packet_hypothetically_complete = (
        preflight_hypothetically_clear
        and explicit_human_approval_required
        and guardrail_clear
        and not approval_packet_blockers
    )
    approval_packet_status = (
        "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_COMPLETE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if approval_packet_hypothetically_complete
        else "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY"
    )
    if not approval_packet_blockers:
        approval_packet_blockers.append("NO_PACKET_BLOCKER_BUT_ACTUAL_WRITE_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "controlled_append_only_write_approval_packet_status": approval_packet_status,
        "approval_packet_hypothetically_complete": approval_packet_hypothetically_complete,
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
        "approval_packet_blockers": approval_packet_blockers,
        "approval_packet_sections": list(APPROVAL_PACKET_SECTIONS),
        "approval_packet_absolute_prohibitions": list(APPROVAL_PACKET_ABSOLUTE_PROHIBITIONS),
        "approval_payload_preview": _build_approval_payload_preview(row, upstream),
        "append_only_write_preflight_status": row.get("append_only_write_preflight_status"),
        "append_only_write_preflight_hypothetically_clear": preflight_hypothetically_clear,
        "preflight_blockers": list(row.get("preflight_blockers") or []),
        "append_only_controls": dict(row.get("append_only_controls") or {}),
        "target_table": row.get("target_table"),
        "proposed_columns": list(row.get("proposed_columns") or []),
        "missing_proposed_columns": list(row.get("missing_proposed_columns") or []),
        "table_exists": row.get("table_exists") is True,
        "all_proposed_columns_exist": row.get("all_proposed_columns_exist") is True,
        "explicit_human_approval_required_before_any_write": True,
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
def build_read_only_controlled_append_only_write_approval_packet_from_preflight(
    *,
    preflight: Dict[str, Any],
) -> Dict[str, Any]:
    preflight_rows = _as_list(preflight.get("supabase_append_only_write_preflight_authorization_gate_rows"))
    approval_rows = [
        _approval_row(row, preflight)
        for row in preflight_rows
        if isinstance(row, dict)
    ]
    complete_rows = [
        row for row in approval_rows
        if row["approval_packet_hypothetically_complete"] is True
    ]
    blocked_rows = [
        row for row in approval_rows
        if row["approval_packet_hypothetically_complete"] is not True
    ]
    guardrail_failure_count = _as_int(preflight.get("guardrail_failure_count"))
    approval_packet_audit_status = (
        "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_COMPLETE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if approval_rows and not blocked_rows and guardrail_failure_count == 0
        else "CONTROLLED_APPEND_ONLY_WRITE_APPROVAL_PACKET_BLOCKED_READ_ONLY"
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
        "controlled_append_only_write_approval_packet_audit_status": approval_packet_audit_status,
        "append_only_write_preflight_authorization_gate_status": preflight.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": preflight.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": preflight.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": preflight.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": preflight.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": preflight.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": preflight.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": preflight.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": preflight.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": preflight.get("source_coverage_completion_status"),
        "coverage_is_complete": preflight.get("coverage_is_complete") is True,
        "requested_symbols": preflight.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(preflight.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(preflight.get("audited_symbol_count")),
        "controlled_append_only_write_approval_packet_row_count": len(approval_rows),
        "approval_packet_hypothetically_complete_symbol_count": len(complete_rows),
        "approval_packet_blocked_symbol_count": len(blocked_rows),
        "approval_packet_hypothetically_complete_symbols": [row["symbol"] for row in complete_rows],
        "approval_packet_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "approval_packet_sections": list(APPROVAL_PACKET_SECTIONS),
        "approval_packet_absolute_prohibitions": list(APPROVAL_PACKET_ABSOLUTE_PROHIBITIONS),
        "target_table": preflight.get("target_table"),
        "proposed_columns": list(preflight.get("proposed_columns") or []),
        "missing_proposed_columns": list(preflight.get("missing_proposed_columns") or []),
        "table_exists": preflight.get("table_exists") is True,
        "all_proposed_columns_exist": preflight.get("all_proposed_columns_exist") is True,
        "schema_probe_status": preflight.get("schema_probe_status"),
        "schema_probe_method": preflight.get("schema_probe_method"),
        "schema_probe_is_read_only": preflight.get("schema_probe_is_read_only") is True,
        "append_only_controls": dict(preflight.get("append_only_controls") or {}),
        "append_only_preflight_requirements": list(preflight.get("append_only_preflight_requirements") or []),
        "absolute_preflight_prohibitions": list(preflight.get("absolute_preflight_prohibitions") or []),
        "explicit_human_approval_required_before_any_write": True,
        "controlled_append_only_write_approval_packet_rows": approval_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(preflight.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_append_only_write_approval_packet_applies_no_changes": True,
        "controlled_append_only_write_approval_packet_is_read_only": True,
        "controlled_append_only_write_approval_packet_never_writes": True,
        "controlled_append_only_write_approval_packet_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_append_only_write_approval_packet_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    preflight = run_read_only_supabase_append_only_write_preflight_authorization_gate(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_append_only_write_approval_packet_from_preflight(
        preflight=preflight,
    )
