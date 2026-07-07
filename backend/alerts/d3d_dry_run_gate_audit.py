from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.operator_control_evidence_audit import (
    run_read_only_operator_control_evidence_audit,
)
COMPONENT = "D3D_DRY_RUN_GATE_AUDIT_READ_ONLY"
VERSION = "d3d_dry_run_gate_audit_read_only_v1"
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
def _row_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    evidence_status = str(row.get("operator_control_evidence_status") or "")
    evidence_complete = row.get("operator_control_evidence_complete") is True
    blocked_reasons = [
        str(item)
        for item in _as_list(row.get("blocked_reasons"))
        if str(item) != "NO_OPERATOR_CONTROL_EVIDENCE_BLOCKER_READ_ONLY"
    ]
    if not evidence_complete:
        blocked_reasons.append("OPERATOR_CONTROL_EVIDENCE_NOT_COMPLETE_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        blocked_reasons.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_IN_DRY_RUN_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        blocked_reasons.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_IN_DRY_RUN_READ_ONLY")
    dry_run_gate_clear = evidence_complete and not blocked_reasons
    dry_run_gate_status = (
        "D3D_DRY_RUN_GATE_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
        if dry_run_gate_clear
        else "D3D_DRY_RUN_GATE_BLOCKED_READ_ONLY"
    )
    if not blocked_reasons:
        blocked_reasons.append("NO_DRY_RUN_GATE_BLOCKER_BUT_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "d3d_dry_run_gate_status": dry_run_gate_status,
        "dry_run_gate_clear": dry_run_gate_clear,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "operator_control_evidence_status": evidence_status,
        "operator_control_evidence_complete": evidence_complete,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "dry_run_blocked_reasons": blocked_reasons,
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
def build_read_only_d3d_dry_run_gate_from_operator_control(
    *,
    operator: Dict[str, Any],
) -> Dict[str, Any]:
    operator_rows = _as_list(operator.get("operator_control_rows"))
    dry_run_rows = [
        _row_gate(row)
        for row in operator_rows
        if isinstance(row, dict)
    ]
    hypothetically_clear_rows = [
        row for row in dry_run_rows
        if row["dry_run_gate_clear"] is True
    ]
    blocked_rows = [
        row for row in dry_run_rows
        if row["dry_run_gate_clear"] is not True
    ]
    guardrail_failure_count = _as_int(operator.get("guardrail_failure_count"))
    d3d_dry_run_gate_audit_status = (
        "D3D_DRY_RUN_GATE_HYPOTHETICALLY_CLEAR_BUT_NOT_AUTHORIZED_READ_ONLY"
        if dry_run_rows and not blocked_rows and guardrail_failure_count == 0
        else "D3D_DRY_RUN_GATE_BLOCKED_READ_ONLY"
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
        "d3d_dry_run_gate_audit_status": d3d_dry_run_gate_audit_status,
        "operator_control_evidence_audit_status": operator.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": operator.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": operator.get("source_coverage_completion_status"),
        "coverage_is_complete": operator.get("coverage_is_complete") is True,
        "requested_symbols": operator.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(operator.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(operator.get("audited_symbol_count")),
        "d3d_dry_run_gate_row_count": len(dry_run_rows),
        "d3d_dry_run_gate_hypothetically_clear_symbol_count": len(hypothetically_clear_rows),
        "d3d_dry_run_gate_blocked_symbol_count": len(blocked_rows),
        "d3d_dry_run_gate_hypothetically_clear_symbols": [row["symbol"] for row in hypothetically_clear_rows],
        "d3d_dry_run_gate_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "d3d_dry_run_rows": dry_run_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(operator.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "dry_run_gate_applies_no_changes": True,
        "dry_run_gate_is_read_only": True,
        "dry_run_gate_never_authorizes_execution": True,
        "guardrails": _guardrails(),
    }
def run_read_only_d3d_dry_run_gate_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    operator = run_read_only_operator_control_evidence_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_d3d_dry_run_gate_from_operator_control(
        operator=operator,
    )

