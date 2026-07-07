from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_contract_audit import (
    run_read_only_controlled_persistence_contract_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_ACTIVATION_READINESS_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_activation_readiness_audit_read_only_v1"
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
}
REQUIRED_ACTIVATION_PRECONDITIONS = [
    "source_coverage_complete",
    "evidence_payload_complete",
    "operator_control_evidence_complete",
    "d3d_dry_run_gate_reviewable",
    "controlled_persistence_contract_reviewable",
    "zero_guardrail_failures",
]
ACTIVATION_REMAINS_PROHIBITED_UNTIL_EXPLICIT_APPROVAL = [
    "supabase_write_authorization",
    "campaign_mutation_authorization",
    "operator_control_confirmation_authorization",
    "d3d_execution_authorization",
    "production_activation_authorization",
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
def _contract_reviewable(row: Dict[str, Any]) -> bool:
    return row.get("persistence_contract_hypothetically_reviewable") is True
def _activation_row(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    contract_reviewable = _contract_reviewable(row)
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    readiness_blockers: List[str] = []
    if not contract_reviewable:
        readiness_blockers.append("CONTROLLED_PERSISTENCE_CONTRACT_NOT_REVIEWABLE_READ_ONLY")
    if not guardrail_clear:
        readiness_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        readiness_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        readiness_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        readiness_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        readiness_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        readiness_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        readiness_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    activation_hypothetically_ready = (
        contract_reviewable
        and guardrail_clear
        and not readiness_blockers
    )
    activation_readiness_status = (
        "CONTROLLED_PERSISTENCE_ACTIVATION_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY"
        if activation_hypothetically_ready
        else "CONTROLLED_PERSISTENCE_ACTIVATION_BLOCKED_READ_ONLY"
    )
    if not readiness_blockers:
        readiness_blockers.append("NO_READINESS_BLOCKER_BUT_ACTIVATION_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "controlled_persistence_activation_readiness_status": activation_readiness_status,
        "activation_hypothetically_ready": activation_hypothetically_ready,
        "persistence_activation_authorized": False,
        "production_activation_authorized": False,
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "activation_readiness_blockers": readiness_blockers,
        "required_activation_preconditions": list(REQUIRED_ACTIVATION_PRECONDITIONS),
        "activation_remains_prohibited_until_explicit_approval": list(ACTIVATION_REMAINS_PROHIBITED_UNTIL_EXPLICIT_APPROVAL),
        "allowed_persistence_fields_if_later_authorized": list(row.get("allowed_persistence_fields_if_later_authorized") or []),
        "absolutely_prohibited_persistence_fields": list(row.get("absolutely_prohibited_persistence_fields") or []),
        "controlled_persistence_contract_status": row.get("controlled_persistence_contract_status"),
        "persistence_contract_hypothetically_reviewable": contract_reviewable,
        "contract_blockers": list(row.get("contract_blockers") or []),
        "d3d_dry_run_gate_status": row.get("d3d_dry_run_gate_status"),
        "dry_run_gate_clear": row.get("dry_run_gate_clear") is True,
        "operator_control_evidence_status": row.get("operator_control_evidence_status"),
        "operator_control_evidence_complete": row.get("operator_control_evidence_complete") is True,
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "controlled_persistence_contract_audit_status": upstream.get("controlled_persistence_contract_audit_status"),
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
def build_read_only_controlled_persistence_activation_readiness_from_contract(
    *,
    contract: Dict[str, Any],
) -> Dict[str, Any]:
    contract_rows = _as_list(contract.get("controlled_persistence_contract_rows"))
    readiness_rows = [
        _activation_row(row, contract)
        for row in contract_rows
        if isinstance(row, dict)
    ]
    hypothetically_ready_rows = [
        row for row in readiness_rows
        if row["activation_hypothetically_ready"] is True
    ]
    blocked_rows = [
        row for row in readiness_rows
        if row["activation_hypothetically_ready"] is not True
    ]
    guardrail_failure_count = _as_int(contract.get("guardrail_failure_count"))
    controlled_persistence_activation_readiness_audit_status = (
        "CONTROLLED_PERSISTENCE_ACTIVATION_HYPOTHETICALLY_READY_BUT_NOT_AUTHORIZED_READ_ONLY"
        if readiness_rows and not blocked_rows and guardrail_failure_count == 0
        else "CONTROLLED_PERSISTENCE_ACTIVATION_BLOCKED_READ_ONLY"
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
        "controlled_persistence_activation_readiness_audit_status": controlled_persistence_activation_readiness_audit_status,
        "controlled_persistence_contract_audit_status": contract.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": contract.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": contract.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": contract.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": contract.get("source_coverage_completion_status"),
        "coverage_is_complete": contract.get("coverage_is_complete") is True,
        "requested_symbols": contract.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(contract.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(contract.get("audited_symbol_count")),
        "controlled_persistence_activation_readiness_row_count": len(readiness_rows),
        "controlled_persistence_activation_hypothetically_ready_symbol_count": len(hypothetically_ready_rows),
        "controlled_persistence_activation_blocked_symbol_count": len(blocked_rows),
        "controlled_persistence_activation_hypothetically_ready_symbols": [row["symbol"] for row in hypothetically_ready_rows],
        "controlled_persistence_activation_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "required_activation_preconditions": list(REQUIRED_ACTIVATION_PRECONDITIONS),
        "activation_remains_prohibited_until_explicit_approval": list(ACTIVATION_REMAINS_PROHIBITED_UNTIL_EXPLICIT_APPROVAL),
        "allowed_persistence_fields_if_later_authorized": list(contract.get("allowed_persistence_fields_if_later_authorized") or []),
        "absolutely_prohibited_persistence_fields": list(contract.get("absolutely_prohibited_persistence_fields") or []),
        "controlled_persistence_activation_readiness_rows": readiness_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(contract.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_activation_readiness_applies_no_changes": True,
        "controlled_persistence_activation_readiness_is_read_only": True,
        "controlled_persistence_activation_readiness_never_writes": True,
        "controlled_persistence_activation_readiness_never_activates": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_activation_readiness_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    contract = run_read_only_controlled_persistence_contract_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_activation_readiness_from_contract(
        contract=contract,
    )
