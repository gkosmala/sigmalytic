from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.d3d_dry_run_gate_audit import (
    run_read_only_d3d_dry_run_gate_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_CONTRACT_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_contract_audit_read_only_v1"
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
}
PERSISTENCE_CONTRACT_FIELDS = [
    "symbol",
    "source_coverage_completion_status",
    "evidence_payload_completeness_status",
    "operator_control_evidence_audit_status",
    "d3d_dry_run_gate_status",
    "dry_run_blocked_reasons",
    "doctrine_statement",
    "audit_timestamp_source",
    "read_only_contract_version",
]
ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS = [
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
def _contract_row(row: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    dry_run_gate_clear = row.get("dry_run_gate_clear") is True
    dry_run_blocked_reasons = [
        str(item)
        for item in _as_list(row.get("dry_run_blocked_reasons"))
    ]
    contract_blockers: List[str] = []
    if not dry_run_gate_clear:
        contract_blockers.append("D3D_DRY_RUN_GATE_NOT_CLEAR_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        contract_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        contract_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False and row.get("d3d_execution_authorized") is not None:
        contract_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("can_execute_d3d") is not False:
        contract_blockers.append("CAN_EXECUTE_D3D_NOT_ALLOWED_READ_ONLY")
    if not contract_blockers:
        contract_blockers.append("NO_CONTRACT_BLOCKER_BUT_PERSISTENCE_STILL_NOT_AUTHORIZED_READ_ONLY")
    persistence_contract_status = (
        "CONTROLLED_PERSISTENCE_CONTRACT_HYPOTHETICALLY_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if dry_run_gate_clear and contract_blockers == ["NO_CONTRACT_BLOCKER_BUT_PERSISTENCE_STILL_NOT_AUTHORIZED_READ_ONLY"]
        else "CONTROLLED_PERSISTENCE_CONTRACT_BLOCKED_READ_ONLY"
    )
    return {
        "symbol": symbol,
        "controlled_persistence_contract_status": persistence_contract_status,
        "persistence_contract_hypothetically_reviewable": persistence_contract_status == "CONTROLLED_PERSISTENCE_CONTRACT_HYPOTHETICALLY_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY",
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "allowed_persistence_fields_if_later_authorized": list(PERSISTENCE_CONTRACT_FIELDS),
        "absolutely_prohibited_persistence_fields": list(ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS),
        "contract_blockers": contract_blockers,
        "dry_run_blocked_reasons": dry_run_blocked_reasons,
        "d3d_dry_run_gate_status": row.get("d3d_dry_run_gate_status"),
        "dry_run_gate_clear": dry_run_gate_clear,
        "operator_control_evidence_status": row.get("operator_control_evidence_status"),
        "operator_control_evidence_complete": row.get("operator_control_evidence_complete") is True,
        "source_coverage_completion_status": upstream.get("source_coverage_completion_status"),
        "evidence_payload_completeness_status": upstream.get("evidence_payload_completeness_status"),
        "operator_control_evidence_audit_status": upstream.get("operator_control_evidence_audit_status"),
        "d3d_dry_run_gate_audit_status": upstream.get("d3d_dry_run_gate_audit_status"),
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
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
def build_read_only_controlled_persistence_contract_from_d3d_gate(
    *,
    d3d_gate: Dict[str, Any],
) -> Dict[str, Any]:
    dry_run_rows = _as_list(d3d_gate.get("d3d_dry_run_rows"))
    contract_rows = [
        _contract_row(row, d3d_gate)
        for row in dry_run_rows
        if isinstance(row, dict)
    ]
    reviewable_rows = [
        row for row in contract_rows
        if row["persistence_contract_hypothetically_reviewable"] is True
    ]
    blocked_rows = [
        row for row in contract_rows
        if row["persistence_contract_hypothetically_reviewable"] is not True
    ]
    guardrail_failure_count = _as_int(d3d_gate.get("guardrail_failure_count"))
    controlled_persistence_contract_audit_status = (
        "CONTROLLED_PERSISTENCE_CONTRACT_REVIEWABLE_BUT_NOT_AUTHORIZED_READ_ONLY"
        if contract_rows and not blocked_rows and guardrail_failure_count == 0
        else "CONTROLLED_PERSISTENCE_CONTRACT_BLOCKED_READ_ONLY"
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
        "controlled_persistence_contract_audit_status": controlled_persistence_contract_audit_status,
        "d3d_dry_run_gate_audit_status": d3d_gate.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": d3d_gate.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": d3d_gate.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": d3d_gate.get("source_coverage_completion_status"),
        "coverage_is_complete": d3d_gate.get("coverage_is_complete") is True,
        "requested_symbols": d3d_gate.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(d3d_gate.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(d3d_gate.get("audited_symbol_count")),
        "controlled_persistence_contract_row_count": len(contract_rows),
        "controlled_persistence_contract_reviewable_symbol_count": len(reviewable_rows),
        "controlled_persistence_contract_blocked_symbol_count": len(blocked_rows),
        "controlled_persistence_contract_reviewable_symbols": [row["symbol"] for row in reviewable_rows],
        "controlled_persistence_contract_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "allowed_persistence_fields_if_later_authorized": list(PERSISTENCE_CONTRACT_FIELDS),
        "absolutely_prohibited_persistence_fields": list(ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS),
        "controlled_persistence_contract_rows": contract_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(d3d_gate.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_contract_applies_no_changes": True,
        "controlled_persistence_contract_is_read_only": True,
        "controlled_persistence_contract_never_writes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_contract_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    d3d_gate = run_read_only_d3d_dry_run_gate_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_contract_from_d3d_gate(
        d3d_gate=d3d_gate,
    )
