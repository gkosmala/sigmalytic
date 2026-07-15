from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.evidence_payload_completeness_audit import (
    run_read_only_evidence_payload_completeness_audit,
)
COMPONENT = "OPERATOR_CONTROL_EVIDENCE_AUDIT_READ_ONLY"
VERSION = "operator_control_evidence_audit_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
GUARDRAILS: Dict[str, Any] = {
    "diagnostic_only": True,
    "read_only": True,
    "writes_to_supabase": False,
    "mutates_campaigns": False,
    "executes_d3d": False,
    "authorizes_d3d": False,
    "operator_control_confirmed": False,
    "not_a_trade_signal": True,
    "changes_scores": False,
    "changes_ranks": False,
    "changes_states": False,
    "changes_probabilities": False,
    "changes_edge": False,
    "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
    "can_execute_d3d": False,
}
REQUIRED_OPERATOR_CONTROL_EVIDENCE = [
    "tested_supply_exhaustion",
    "active_demand_support_validation",
    "structurally_meaningful_location",
    "absence_of_contrary_failure",
]
FORBIDDEN_INFERENCE_SOURCES = [
    "score",
    "rank",
    "gamma_overlay",
    "probability_output",
    "downstream_price_result",
    "future_return",
    "trade_signal",
    "edge_calculation",
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
def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _missing_keys(payload: Dict[str, Any], required_keys: List[str]) -> List[str]:
    return [key for key in required_keys if key not in payload]
def _truthy_evidence(value: Any) -> bool:
    if isinstance(value, dict):
        return len(value.keys()) > 0
    if isinstance(value, list):
        return len(value) > 0
    return value not in (None, "", False)
def _present_but_empty_keys(payload: Dict[str, Any], required_keys: List[str]) -> List[str]:
    empty: List[str] = []
    for key in required_keys:
        if key in payload and not _truthy_evidence(payload.get(key)):
            empty.append(key)
    return empty
def _extract_evidence_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("evidence_payload")
    if isinstance(payload, dict):
        return payload
    payload = row.get("evidence")
    if isinstance(payload, dict):
        return payload
    return {}
def _operator_control_row(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    evidence_payload_status = str(row.get("evidence_payload_status") or "")
    evidence_payload_complete = row.get("evidence_payload_complete") is True
    evidence_payload = _extract_evidence_payload(row)
    missing_operator_control_evidence = _missing_keys(
        evidence_payload,
        REQUIRED_OPERATOR_CONTROL_EVIDENCE,
    )
    empty_operator_control_evidence = _present_but_empty_keys(
        evidence_payload,
        REQUIRED_OPERATOR_CONTROL_EVIDENCE,
    )
    blocked_reasons: List[str] = []
    if not evidence_payload_complete:
        blocked_reasons.append("EVIDENCE_PAYLOAD_NOT_COMPLETE_READ_ONLY")
    if missing_operator_control_evidence:
        blocked_reasons.append("OPERATOR_CONTROL_EVIDENCE_FAMILIES_MISSING_READ_ONLY")
    if empty_operator_control_evidence:
        blocked_reasons.append("OPERATOR_CONTROL_EVIDENCE_PRESENT_BUT_EMPTY_READ_ONLY")
    operator_control_evidence_complete = (
        evidence_payload_complete
        and not missing_operator_control_evidence
        and not empty_operator_control_evidence
    )
    operator_control_evidence_status = (
        "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY"
        if operator_control_evidence_complete
        else "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY"
    )
    if not blocked_reasons:
        blocked_reasons.append("NO_OPERATOR_CONTROL_EVIDENCE_BLOCKER_READ_ONLY")
    return {
        "symbol": symbol,
        "operator_control_evidence_status": operator_control_evidence_status,
        "operator_control_evidence_complete": operator_control_evidence_complete,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "evidence_payload_status": evidence_payload_status,
        "evidence_payload_complete": evidence_payload_complete,
        "required_operator_control_evidence": list(REQUIRED_OPERATOR_CONTROL_EVIDENCE),
        "missing_operator_control_evidence": missing_operator_control_evidence,
        "empty_operator_control_evidence": empty_operator_control_evidence,
        "blocked_reasons": blocked_reasons,
        "forbidden_inference_sources": list(FORBIDDEN_INFERENCE_SOURCES),
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
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
    }
def build_read_only_operator_control_evidence_from_evidence_payload(
    *,
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_rows = _as_list(evidence.get("evidence_rows"))
    operator_rows = [
        _operator_control_row(row)
        for row in evidence_rows
        if isinstance(row, dict)
    ]
    complete_rows = [
        row for row in operator_rows
        if row["operator_control_evidence_complete"] is True
    ]
    blocked_rows = [
        row for row in operator_rows
        if row["operator_control_evidence_complete"] is not True
    ]
    operator_control_evidence_audit_status = (
        "OPERATOR_CONTROL_EVIDENCE_COMPLETE_READ_ONLY"
        if operator_rows and len(complete_rows) == len(operator_rows)
        else "OPERATOR_CONTROL_EVIDENCE_INCOMPLETE_OR_BLOCKED_READ_ONLY"
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
        "operator_control_evidence_audit_status": operator_control_evidence_audit_status,
        "evidence_payload_completeness_status": evidence.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": evidence.get("source_coverage_completion_status"),
        "coverage_is_complete": evidence.get("coverage_is_complete") is True,
        "requested_symbols": evidence.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(evidence.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(evidence.get("audited_symbol_count")),
        "operator_control_evidence_row_count": len(operator_rows),
        "operator_control_evidence_complete_symbol_count": len(complete_rows),
        "operator_control_evidence_blocked_symbol_count": len(blocked_rows),
        "operator_control_evidence_complete_symbols": [row["symbol"] for row in complete_rows],
        "operator_control_evidence_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "required_operator_control_evidence": list(REQUIRED_OPERATOR_CONTROL_EVIDENCE),
        "forbidden_inference_sources": list(FORBIDDEN_INFERENCE_SOURCES),
        "operator_control_rows": operator_rows,
        "guardrail_failure_count": _as_int(evidence.get("guardrail_failure_count")),
        "guardrail_failures": list(evidence.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "operator_control_audit_applies_no_changes": True,
        "operator_control_audit_is_read_only": True,
        "guardrails": _guardrails(),
    }
def run_read_only_operator_control_evidence_audit(
    *,
    symbols: Any = "SPY",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    evidence = run_read_only_evidence_payload_completeness_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_operator_control_evidence_from_evidence_payload(
        evidence=evidence,
    )

