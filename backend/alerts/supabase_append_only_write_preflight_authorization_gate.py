from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.supabase_target_table_schema_existence_audit import (
    run_read_only_supabase_target_table_schema_existence_audit,
)
COMPONENT = "SUPABASE_APPEND_ONLY_WRITE_PREFLIGHT_AUTHORIZATION_GATE_READ_ONLY"
VERSION = "supabase_append_only_write_preflight_authorization_gate_read_only_v1"
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
}
PREFLIGHT_REQUIRED_UPSTREAM_STATUSES = [
    "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY",
    "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY",
    "WRITE_PERMISSION_MANIFEST_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY",
    "CONTROLLED_PERSISTENCE_ACTIVATION_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY",
    "CONTROLLED_PERSISTENCE_CONTRACT_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
    "D3D_DRY_RUN_GATE_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY",
]
APPEND_ONLY_PREFLIGHT_REQUIREMENTS = [
    "target_table_exists",
    "all_proposed_columns_exist",
    "payload_simulation_valid",
    "write_permission_manifest_ready",
    "controlled_persistence_activation_ready",
    "controlled_persistence_contract_ready",
    "d3d_dry_run_gate_hypothetically_clear",
    "zero_guardrail_failures",
    "append_only_mode_declared",
    "no_upsert_allowed",
    "no_update_allowed",
    "no_delete_allowed",
    "no_rpc_allowed",
    "no_campaign_table_mutation",
    "no_operator_control_confirmation",
    "no_d3d_execution",
    "explicit_human_approval_still_required",
]
ABSOLUTE_PREFLIGHT_PROHIBITIONS = [
    "no_supabase_write_in_this_gate",
    "no_insert_in_this_gate",
    "no_update_in_this_gate",
    "no_upsert_in_this_gate",
    "no_delete_in_this_gate",
    "no_rpc_in_this_gate",
    "no_campaign_mutation",
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
def _text(value: Any) -> str:
    return str(value or "").strip()
def _append_only_controls(schema_audit: Dict[str, Any]) -> Dict[str, Any]:
    schema_probe = schema_audit.get("schema_probe") or {}
    proposed_target = schema_audit.get("proposed_supabase_target") or {}
    write_limits = schema_audit.get("write_limits_if_later_authorized") or {}
    if not isinstance(schema_probe, dict):
        schema_probe = {}
    if not isinstance(proposed_target, dict):
        proposed_target = {}
    if not isinstance(write_limits, dict):
        write_limits = {}
    return {
        "target_table": _text(schema_audit.get("target_table")),
        "table_exists": schema_audit.get("table_exists") is True,
        "all_proposed_columns_exist": schema_audit.get("all_proposed_columns_exist") is True,
        "schema_probe_status": schema_audit.get("schema_probe_status"),
        "schema_probe_method": schema_audit.get("schema_probe_method"),
        "schema_probe_is_read_only": schema_audit.get("schema_probe_is_read_only") is True,
        "write_mode": proposed_target.get("write_mode") or "APPEND_ONLY_IF_LATER_EXPLICITLY_AUTHORIZED",
        "append_only_declared": write_limits.get("append_only") is True,
        "upsert_allowed": proposed_target.get("upsert_allowed") is True,
        "update_allowed": proposed_target.get("update_allowed") is True,
        "delete_allowed": proposed_target.get("delete_allowed") is True,
        "rpc_allowed": proposed_target.get("rpc_allowed") is True,
        "campaign_table_mutation_allowed": write_limits.get("campaign_table_mutation_allowed") is True,
        "operator_control_confirmation_allowed": write_limits.get("operator_control_confirmation_allowed") is True,
        "d3d_execution_allowed": write_limits.get("d3d_execution_allowed") is True,
        "max_symbols_per_request": write_limits.get("max_symbols_per_request"),
        "max_rows_per_symbol_per_request": write_limits.get("max_rows_per_symbol_per_request"),
    }
def _preflight_row(row: Dict[str, Any], upstream: Dict[str, Any], controls: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    schema_ready = row.get("schema_existence_hypothetically_ready") is True
    table_exists = row.get("table_exists") is True
    columns_exist = row.get("all_proposed_columns_exist") is True
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    preflight_blockers: List[str] = []
    if not schema_ready:
        preflight_blockers.append("SUPABASE_SCHEMA_EXISTENCE_NOT_READY_READ_ONLY")
    if not table_exists:
        preflight_blockers.append("TARGET_TABLE_NOT_CONFIRMED_READ_ONLY")
    if not columns_exist:
        preflight_blockers.append("TARGET_COLUMNS_NOT_CONFIRMED_READ_ONLY")
    if not guardrail_clear:
        preflight_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if controls.get("append_only_declared") is not True:
        preflight_blockers.append("APPEND_ONLY_MODE_NOT_DECLARED_READ_ONLY")
    if controls.get("upsert_allowed") is True:
        preflight_blockers.append("UPSERT_NOT_ALLOWED_FOR_APPEND_ONLY_PREFLIGHT_READ_ONLY")
    if controls.get("update_allowed") is True:
        preflight_blockers.append("UPDATE_NOT_ALLOWED_FOR_APPEND_ONLY_PREFLIGHT_READ_ONLY")
    if controls.get("delete_allowed") is True:
        preflight_blockers.append("DELETE_NOT_ALLOWED_FOR_APPEND_ONLY_PREFLIGHT_READ_ONLY")
    if controls.get("rpc_allowed") is True:
        preflight_blockers.append("RPC_NOT_ALLOWED_FOR_APPEND_ONLY_PREFLIGHT_READ_ONLY")
    if controls.get("campaign_table_mutation_allowed") is True:
        preflight_blockers.append("CAMPAIGN_TABLE_MUTATION_NOT_ALLOWED_READ_ONLY")
    if controls.get("operator_control_confirmation_allowed") is True:
        preflight_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if controls.get("d3d_execution_allowed") is True:
        preflight_blockers.append("D3D_EXECUTION_NOT_ALLOWED_READ_ONLY")
    if row.get("actual_write_performed") is not False:
        preflight_blockers.append("ACTUAL_WRITE_NOT_ALLOWED_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        preflight_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        preflight_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        preflight_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        preflight_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        preflight_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        preflight_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    preflight_hypothetically_clear = (
        schema_ready
        and table_exists
        and columns_exist
        and guardrail_clear
        and controls.get("append_only_declared") is True
        and controls.get("upsert_allowed") is not True
        and controls.get("update_allowed") is not True
        and controls.get("delete_allowed") is not True
        and controls.get("rpc_allowed") is not True
        and controls.get("campaign_table_mutation_allowed") is not True
        and controls.get("operator_control_confirmation_allowed") is not True
        and controls.get("d3d_execution_allowed") is not True
        and not preflight_blockers
    )
    preflight_status = (
        "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
        if preflight_hypothetically_clear
        else "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY"
    )
    if not preflight_blockers:
        preflight_blockers.append("NO_PREFLIGHT_BLOCKER_BUT_EXPLICIT_WRITE_APPROVAL_STILL_REQUIRED_READ_ONLY")
    return {
        "symbol": symbol,
        "append_only_write_preflight_status": preflight_status,
        "append_only_write_preflight_hypothetically_clear": preflight_hypothetically_clear,
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
        "preflight_blockers": preflight_blockers,
        "append_only_controls": dict(controls),
        "append_only_preflight_requirements": list(APPEND_ONLY_PREFLIGHT_REQUIREMENTS),
        "absolute_preflight_prohibitions": list(ABSOLUTE_PREFLIGHT_PROHIBITIONS),
        "supabase_target_table_schema_existence_status": row.get("supabase_target_table_schema_existence_status"),
        "schema_existence_hypothetically_ready": schema_ready,
        "schema_blockers": list(row.get("schema_blockers") or []),
        "table_exists": table_exists,
        "all_proposed_columns_exist": columns_exist,
        "missing_proposed_columns": list(row.get("missing_proposed_columns") or []),
        "target_table": row.get("target_table"),
        "proposed_columns": list(row.get("proposed_columns") or []),
        "persistence_payload_simulation_status": row.get("persistence_payload_simulation_status"),
        "persistence_payload_simulation_hypothetically_valid": row.get("persistence_payload_simulation_hypothetically_valid") is True,
        "write_permission_manifest_status": row.get("write_permission_manifest_status"),
        "write_permission_manifest_hypothetically_ready": row.get("write_permission_manifest_hypothetically_ready") is True,
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
def build_read_only_supabase_append_only_write_preflight_authorization_gate_from_schema_audit(
    *,
    schema_audit: Dict[str, Any],
) -> Dict[str, Any]:
    schema_rows = _as_list(schema_audit.get("supabase_target_table_schema_existence_rows"))
    controls = _append_only_controls(schema_audit)
    preflight_rows = [
        _preflight_row(row, schema_audit, controls)
        for row in schema_rows
        if isinstance(row, dict)
    ]
    hypothetically_clear_rows = [
        row for row in preflight_rows
        if row["append_only_write_preflight_hypothetically_clear"] is True
    ]
    blocked_rows = [
        row for row in preflight_rows
        if row["append_only_write_preflight_hypothetically_clear"] is not True
    ]
    guardrail_failure_count = _as_int(schema_audit.get("guardrail_failure_count"))
    preflight_gate_status = (
        "APPEND_ONLY_WRITE_PREFLIGHT_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
        if preflight_rows and not blocked_rows and guardrail_failure_count == 0
        else "APPEND_ONLY_WRITE_PREFLIGHT_BLOCKED_READ_ONLY"
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
        "append_only_write_preflight_authorization_gate_status": preflight_gate_status,
        "supabase_target_table_schema_existence_audit_status": schema_audit.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": schema_audit.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": schema_audit.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": schema_audit.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": schema_audit.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": schema_audit.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": schema_audit.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": schema_audit.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": schema_audit.get("source_coverage_completion_status"),
        "coverage_is_complete": schema_audit.get("coverage_is_complete") is True,
        "requested_symbols": schema_audit.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(schema_audit.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(schema_audit.get("audited_symbol_count")),
        "append_only_write_preflight_row_count": len(preflight_rows),
        "append_only_write_preflight_hypothetically_clear_symbol_count": len(hypothetically_clear_rows),
        "append_only_write_preflight_blocked_symbol_count": len(blocked_rows),
        "append_only_write_preflight_hypothetically_clear_symbols": [row["symbol"] for row in hypothetically_clear_rows],
        "append_only_write_preflight_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "append_only_controls": dict(controls),
        "append_only_preflight_requirements": list(APPEND_ONLY_PREFLIGHT_REQUIREMENTS),
        "absolute_preflight_prohibitions": list(ABSOLUTE_PREFLIGHT_PROHIBITIONS),
        "preflight_required_upstream_statuses": list(PREFLIGHT_REQUIRED_UPSTREAM_STATUSES),
        "target_table": schema_audit.get("target_table"),
        "proposed_columns": list(schema_audit.get("proposed_columns") or []),
        "missing_proposed_columns": list(schema_audit.get("missing_proposed_columns") or []),
        "table_exists": schema_audit.get("table_exists") is True,
        "all_proposed_columns_exist": schema_audit.get("all_proposed_columns_exist") is True,
        "schema_probe_status": schema_audit.get("schema_probe_status"),
        "schema_probe_method": schema_audit.get("schema_probe_method"),
        "schema_probe_is_read_only": schema_audit.get("schema_probe_is_read_only") is True,
        "supabase_url_present": schema_audit.get("supabase_url_present") is True,
        "supabase_key_present": schema_audit.get("supabase_key_present") is True,
        "supabase_key_source": schema_audit.get("supabase_key_source") or "",
        "supabase_append_only_write_preflight_authorization_gate_rows": preflight_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(schema_audit.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "supabase_append_only_write_preflight_authorization_gate_applies_no_changes": True,
        "supabase_append_only_write_preflight_authorization_gate_is_read_only": True,
        "supabase_append_only_write_preflight_authorization_gate_never_writes": True,
        "supabase_append_only_write_preflight_authorization_gate_never_authorizes": True,
        "explicit_human_approval_required_before_any_write": True,
        "guardrails": _guardrails(),
    }
def run_read_only_supabase_append_only_write_preflight_authorization_gate(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    schema_audit = run_read_only_supabase_target_table_schema_existence_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_supabase_append_only_write_preflight_authorization_gate_from_schema_audit(
        schema_audit=schema_audit,
    )
