from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_activation_readiness_audit import (
    run_read_only_controlled_persistence_activation_readiness_audit,
)
COMPONENT = "PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_READ_ONLY"
VERSION = "persistence_write_permission_manifest_audit_read_only_v1"
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
}
PROPOSED_SUPABASE_TARGET = {
    "target_table": "alert_readiness_audit_events",
    "target_table_status": "PROPOSED_ONLY_NOT_AUTHORIZED_READ_ONLY",
    "write_mode": "APPEND_ONLY_IF_LATER_EXPLICITLY_AUTHORIZED",
    "upsert_allowed": False,
    "update_allowed": False,
    "delete_allowed": False,
    "rpc_allowed": False,
}
PROPOSED_ALLOWED_COLUMNS = [
    "symbol",
    "audit_component",
    "audit_version",
    "source_coverage_completion_status",
    "evidence_payload_completeness_status",
    "operator_control_evidence_audit_status",
    "d3d_dry_run_gate_audit_status",
    "controlled_persistence_contract_audit_status",
    "controlled_persistence_activation_readiness_audit_status",
    "activation_hypothetically_ready",
    "activation_readiness_blockers",
    "allowed_persistence_fields_if_later_authorized",
    "absolutely_prohibited_persistence_fields",
    "doctrine_statement",
    "read_only_guardrails",
    "created_by_read_only_audit",
]
ABSOLUTELY_PROHIBITED_COLUMNS = [
    "operator_control_confirmed",
    "composite_operator_control_confirmed",
    "d3d_execution_authorized",
    "can_execute_d3d",
    "trade_signal",
    "score_change",
    "rank_change",
    "state_change",
    "probability_change",
    "edge_change",
    "future_return",
    "downstream_price_result",
]
ROLLBACK_EXPECTATIONS = [
    "NO_WRITE_HAS_OCCURRED_IN_THIS_AUDIT",
    "NO_ROLLBACK_REQUIRED_FOR_THIS_READ_ONLY_LAYER",
    "IF_LATER_WRITES_ARE_AUTHORIZED_USE_APPEND_ONLY_EVENT_ROWS",
    "IF_LATER_WRITES_ARE_AUTHORIZED_ROLLBACK_BY_DEACTIVATING_OR_MARKING_EVENT_ROWS_NOT_BY_MUTATING_CAMPAIGNS",
]
WRITE_LIMITS_IF_LATER_AUTHORIZED = {
    "max_symbols_per_request": 10,
    "max_rows_per_symbol_per_request": 1,
    "append_only": True,
    "campaign_table_mutation_allowed": False,
    "operator_control_confirmation_allowed": False,
    "d3d_execution_allowed": False,
}
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
def _manifest_row(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    activation_ready = row.get("activation_hypothetically_ready") is True
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    permission_blockers: List[str] = []
    if not activation_ready:
        permission_blockers.append("CONTROLLED_PERSISTENCE_ACTIVATION_NOT_READY_READ_ONLY")
    if not guardrail_clear:
        permission_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        permission_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        permission_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        permission_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        permission_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        permission_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        permission_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    manifest_hypothetically_ready = (
        activation_ready
        and guardrail_clear
        and not permission_blockers
    )
    manifest_status = (
        "WRITE_PERMISSION_MANIFEST_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY"
        if manifest_hypothetically_ready
        else "WRITE_PERMISSION_MANIFEST_BLOCKED_READ_ONLY"
    )
    if not permission_blockers:
        permission_blockers.append("NO_PERMISSION_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY")
    proposed_payload_shape = {
        "symbol": symbol,
        "audit_component": COMPONENT,
        "audit_version": VERSION,
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "controlled_persistence_contract_audit_status": upstream.get("controlled_persistence_contract_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": upstream.get("controlled_persistence_activation_readiness_audit_status"),
        "activation_hypothetically_ready": activation_ready,
        "activation_readiness_blockers": list(row.get("activation_readiness_blockers") or []),
        "allowed_persistence_fields_if_later_authorized": list(row.get("allowed_persistence_fields_if_later_authorized") or []),
        "absolutely_prohibited_persistence_fields": list(row.get("absolutely_prohibited_persistence_fields") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "read_only_guardrails": _guardrails(),
        "created_by_read_only_audit": True,
    }
    return {
        "symbol": symbol,
        "write_permission_manifest_status": manifest_status,
        "write_permission_manifest_hypothetically_ready": manifest_hypothetically_ready,
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
        "permission_blockers": permission_blockers,
        "proposed_supabase_target": dict(PROPOSED_SUPABASE_TARGET),
        "proposed_allowed_columns": list(PROPOSED_ALLOWED_COLUMNS),
        "absolutely_prohibited_columns": list(ABSOLUTELY_PROHIBITED_COLUMNS),
        "proposed_payload_shape": proposed_payload_shape,
        "rollback_expectations": list(ROLLBACK_EXPECTATIONS),
        "write_limits_if_later_authorized": dict(WRITE_LIMITS_IF_LATER_AUTHORIZED),
        "controlled_persistence_activation_readiness_status": row.get("controlled_persistence_activation_readiness_status"),
        "activation_hypothetically_ready": activation_ready,
        "activation_readiness_blockers": list(row.get("activation_readiness_blockers") or []),
        "controlled_persistence_contract_status": row.get("controlled_persistence_contract_status"),
        "d3d_dry_run_gate_status": row.get("d3d_dry_run_gate_status"),
        "operator_control_evidence_status": row.get("operator_control_evidence_status"),
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "controlled_persistence_contract_audit_status": upstream.get("controlled_persistence_contract_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": upstream.get("controlled_persistence_activation_readiness_audit_status"),
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
def build_read_only_persistence_write_permission_manifest_from_activation_readiness(
    *,
    readiness: Dict[str, Any],
) -> Dict[str, Any]:
    readiness_rows = _as_list(readiness.get("controlled_persistence_activation_readiness_rows"))
    manifest_rows = [
        _manifest_row(row, readiness)
        for row in readiness_rows
        if isinstance(row, dict)
    ]
    hypothetically_ready_rows = [
        row for row in manifest_rows
        if row["write_permission_manifest_hypothetically_ready"] is True
    ]
    blocked_rows = [
        row for row in manifest_rows
        if row["write_permission_manifest_hypothetically_ready"] is not True
    ]
    guardrail_failure_count = _as_int(readiness.get("guardrail_failure_count"))
    write_permission_manifest_audit_status = (
        "WRITE_PERMISSION_MANIFEST_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY"
        if manifest_rows and not blocked_rows and guardrail_failure_count == 0
        else "WRITE_PERMISSION_MANIFEST_BLOCKED_READ_ONLY"
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
        "write_permission_manifest_audit_status": write_permission_manifest_audit_status,
        "controlled_persistence_activation_readiness_audit_status": readiness.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": readiness.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": readiness.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": readiness.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": readiness.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": readiness.get("source_coverage_completion_status"),
        "coverage_is_complete": readiness.get("coverage_is_complete") is True,
        "requested_symbols": readiness.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(readiness.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(readiness.get("audited_symbol_count")),
        "write_permission_manifest_row_count": len(manifest_rows),
        "write_permission_manifest_hypothetically_ready_symbol_count": len(hypothetically_ready_rows),
        "write_permission_manifest_blocked_symbol_count": len(blocked_rows),
        "write_permission_manifest_hypothetically_ready_symbols": [row["symbol"] for row in hypothetically_ready_rows],
        "write_permission_manifest_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "proposed_supabase_target": dict(PROPOSED_SUPABASE_TARGET),
        "proposed_allowed_columns": list(PROPOSED_ALLOWED_COLUMNS),
        "absolutely_prohibited_columns": list(ABSOLUTELY_PROHIBITED_COLUMNS),
        "rollback_expectations": list(ROLLBACK_EXPECTATIONS),
        "write_limits_if_later_authorized": dict(WRITE_LIMITS_IF_LATER_AUTHORIZED),
        "persistence_write_permission_manifest_rows": manifest_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(readiness.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "write_permission_manifest_applies_no_changes": True,
        "write_permission_manifest_is_read_only": True,
        "write_permission_manifest_never_writes": True,
        "write_permission_manifest_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_persistence_write_permission_manifest_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    readiness = run_read_only_controlled_persistence_activation_readiness_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_persistence_write_permission_manifest_from_activation_readiness(
        readiness=readiness,
    )
