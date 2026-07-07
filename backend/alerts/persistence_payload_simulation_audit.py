from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.persistence_write_permission_manifest_audit import (
    run_read_only_persistence_write_permission_manifest_audit,
)
COMPONENT = "PERSISTENCE_PAYLOAD_SIMULATION_AUDIT_READ_ONLY"
VERSION = "persistence_payload_simulation_audit_read_only_v1"
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
}
REQUIRED_SIMULATED_PAYLOAD_KEYS = [
    "symbol",
    "audit_component",
    "audit_version",
    "source_coverage_completion_status",
    "evidence_payload_completeness_status",
    "operator_control_evidence_audit_status",
    "d3d_dry_run_gate_audit_status",
    "controlled_persistence_contract_audit_status",
    "controlled_persistence_activation_readiness_audit_status",
    "write_permission_manifest_audit_status",
    "activation_hypothetically_ready",
    "write_permission_manifest_hypothetically_ready",
    "permission_blockers",
    "activation_readiness_blockers",
    "allowed_persistence_fields_if_later_authorized",
    "absolutely_prohibited_persistence_fields",
    "absolutely_prohibited_columns",
    "doctrine_statement",
    "read_only_guardrails",
    "created_by_read_only_audit",
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
def _simulated_payload(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": _symbol(row.get("symbol")),
        "audit_component": COMPONENT,
        "audit_version": VERSION,
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "controlled_persistence_contract_audit_status": upstream.get("controlled_persistence_contract_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": upstream.get("controlled_persistence_activation_readiness_audit_status"),
        "write_permission_manifest_audit_status": upstream.get("write_permission_manifest_audit_status"),
        "activation_hypothetically_ready": row.get("activation_hypothetically_ready") is True,
        "write_permission_manifest_hypothetically_ready": row.get("write_permission_manifest_hypothetically_ready") is True,
        "permission_blockers": list(row.get("permission_blockers") or []),
        "activation_readiness_blockers": list(row.get("activation_readiness_blockers") or []),
        "allowed_persistence_fields_if_later_authorized": list(row.get("allowed_persistence_fields_if_later_authorized") or []),
        "absolutely_prohibited_persistence_fields": list(row.get("absolutely_prohibited_persistence_fields") or []),
        "absolutely_prohibited_columns": list(row.get("absolutely_prohibited_columns") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "read_only_guardrails": _guardrails(),
        "created_by_read_only_audit": True,
    }
def _payload_validation(row: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    missing_required_keys = [
        key for key in REQUIRED_SIMULATED_PAYLOAD_KEYS
        if key not in payload
    ]
    prohibited_columns = set(str(item) for item in _as_list(row.get("absolutely_prohibited_columns")))
    payload_keys = set(payload.keys())
    prohibited_top_level_keys_present = sorted(payload_keys.intersection(prohibited_columns))
    payload_valid = (
        not missing_required_keys
        and not prohibited_top_level_keys_present
    )
    return {
        "payload_valid": payload_valid,
        "missing_required_payload_keys": missing_required_keys,
        "prohibited_top_level_payload_keys_present": prohibited_top_level_keys_present,
    }
def _simulation_row(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    manifest_ready = row.get("write_permission_manifest_hypothetically_ready") is True
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    simulation_blockers: List[str] = []
    if not manifest_ready:
        simulation_blockers.append("WRITE_PERMISSION_MANIFEST_NOT_READY_READ_ONLY")
    if not guardrail_clear:
        simulation_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if row.get("write_permission_manifest_authorized") is not False:
        simulation_blockers.append("WRITE_PERMISSION_MANIFEST_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        simulation_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        simulation_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        simulation_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        simulation_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        simulation_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        simulation_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    payload = _simulated_payload(row, upstream)
    validation = _payload_validation(row, payload)
    if not validation["payload_valid"]:
        simulation_blockers.append("SIMULATED_PAYLOAD_SCHEMA_INVALID_READ_ONLY")
    simulation_hypothetically_valid = (
        manifest_ready
        and guardrail_clear
        and validation["payload_valid"]
        and not simulation_blockers
    )
    simulation_status = (
        "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY"
        if simulation_hypothetically_valid
        else "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY"
    )
    if not simulation_blockers:
        simulation_blockers.append("NO_SIMULATION_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "persistence_payload_simulation_status": simulation_status,
        "persistence_payload_simulation_hypothetically_valid": simulation_hypothetically_valid,
        "simulated_payload": payload,
        "simulated_payload_key_count": len(payload.keys()),
        "required_simulated_payload_keys": list(REQUIRED_SIMULATED_PAYLOAD_KEYS),
        "missing_required_payload_keys": validation["missing_required_payload_keys"],
        "prohibited_top_level_payload_keys_present": validation["prohibited_top_level_payload_keys_present"],
        "simulation_blockers": simulation_blockers,
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
        "write_permission_manifest_status": row.get("write_permission_manifest_status"),
        "write_permission_manifest_hypothetically_ready": manifest_ready,
        "permission_blockers": list(row.get("permission_blockers") or []),
        "proposed_supabase_target": dict(row.get("proposed_supabase_target") or {}),
        "proposed_allowed_columns": list(row.get("proposed_allowed_columns") or []),
        "absolutely_prohibited_columns": list(row.get("absolutely_prohibited_columns") or []),
        "rollback_expectations": list(row.get("rollback_expectations") or []),
        "write_limits_if_later_authorized": dict(row.get("write_limits_if_later_authorized") or {}),
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
def build_read_only_persistence_payload_simulation_from_manifest(
    *,
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    manifest_rows = _as_list(manifest.get("persistence_write_permission_manifest_rows"))
    simulation_rows = [
        _simulation_row(row, manifest)
        for row in manifest_rows
        if isinstance(row, dict)
    ]
    valid_rows = [
        row for row in simulation_rows
        if row["persistence_payload_simulation_hypothetically_valid"] is True
    ]
    blocked_rows = [
        row for row in simulation_rows
        if row["persistence_payload_simulation_hypothetically_valid"] is not True
    ]
    guardrail_failure_count = _as_int(manifest.get("guardrail_failure_count"))
    payload_simulation_audit_status = (
        "PERSISTENCE_PAYLOAD_SIMULATION_VALID_BUT_NOT_AUTHORIZED_READ_ONLY"
        if simulation_rows and not blocked_rows and guardrail_failure_count == 0
        else "PERSISTENCE_PAYLOAD_SIMULATION_BLOCKED_READ_ONLY"
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
        "persistence_payload_simulation_audit_status": payload_simulation_audit_status,
        "write_permission_manifest_audit_status": manifest.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": manifest.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": manifest.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": manifest.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": manifest.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": manifest.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": manifest.get("source_coverage_completion_status"),
        "coverage_is_complete": manifest.get("coverage_is_complete") is True,
        "requested_symbols": manifest.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(manifest.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(manifest.get("audited_symbol_count")),
        "persistence_payload_simulation_row_count": len(simulation_rows),
        "persistence_payload_simulation_valid_symbol_count": len(valid_rows),
        "persistence_payload_simulation_blocked_symbol_count": len(blocked_rows),
        "persistence_payload_simulation_valid_symbols": [row["symbol"] for row in valid_rows],
        "persistence_payload_simulation_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "required_simulated_payload_keys": list(REQUIRED_SIMULATED_PAYLOAD_KEYS),
        "proposed_supabase_target": dict(manifest.get("proposed_supabase_target") or {}),
        "proposed_allowed_columns": list(manifest.get("proposed_allowed_columns") or []),
        "absolutely_prohibited_columns": list(manifest.get("absolutely_prohibited_columns") or []),
        "rollback_expectations": list(manifest.get("rollback_expectations") or []),
        "write_limits_if_later_authorized": dict(manifest.get("write_limits_if_later_authorized") or {}),
        "persistence_payload_simulation_rows": simulation_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(manifest.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "persistence_payload_simulation_applies_no_changes": True,
        "persistence_payload_simulation_is_read_only": True,
        "persistence_payload_simulation_never_writes": True,
        "persistence_payload_simulation_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_persistence_payload_simulation_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    manifest = run_read_only_persistence_write_permission_manifest_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_persistence_payload_simulation_from_manifest(
        manifest=manifest,
    )
