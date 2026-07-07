from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.source_coverage_completion_audit import (
    run_read_only_source_coverage_completion_audit,
)
COMPONENT = "EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_READ_ONLY"
VERSION = "evidence_payload_completeness_audit_read_only_v1"
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
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
REQUIRED_EVIDENCE_FAMILIES = [
    "wyckoff_evidence",
    "livermore_evidence",
    "weis_evidence",
    "tested_supply_exhaustion",
    "active_demand_support_validation",
    "structurally_meaningful_location",
    "absence_of_contrary_failure",
]
REQUIRED_STRUCTURAL_LOCATION_INPUTS = [
    "prior_resistance_or_supply_zone",
    "base_or_range_context",
    "breakout_or_spring_location",
    "volume_price_context",
    "multi_timeframe_alignment_context",
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
def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
def _missing_required_keys(payload: Dict[str, Any], required_keys: List[str]) -> List[str]:
    return [key for key in required_keys if key not in payload]
def _row_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("evidence_payload")
    if isinstance(payload, dict):
        return payload
    payload = row.get("evidence")
    if isinstance(payload, dict):
        return payload
    return {}
def _structural_location_payload(evidence_payload: Dict[str, Any]) -> Dict[str, Any]:
    direct = evidence_payload.get("structurally_meaningful_location")
    if isinstance(direct, dict):
        return direct
    alt = evidence_payload.get("structural_location")
    if isinstance(alt, dict):
        return alt
    return {}
def _evidence_row(row: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    coverage_complete = row.get("coverage_complete") is True
    coverage_blockers = _as_list(row.get("coverage_blockers"))
    evidence_payload = _row_payload(row)
    structural_location_payload = _structural_location_payload(evidence_payload)
    missing_evidence_families = _missing_required_keys(
        evidence_payload,
        REQUIRED_EVIDENCE_FAMILIES,
    )
    missing_structural_location_inputs = _missing_required_keys(
        structural_location_payload,
        REQUIRED_STRUCTURAL_LOCATION_INPUTS,
    )
    if not coverage_complete:
        evidence_payload_status = "EVIDENCE_PAYLOAD_BLOCKED_BY_SOURCE_COVERAGE_READ_ONLY"
    elif not evidence_payload:
        evidence_payload_status = "EVIDENCE_PAYLOAD_MISSING_READ_ONLY"
    elif missing_evidence_families or missing_structural_location_inputs:
        evidence_payload_status = "EVIDENCE_PAYLOAD_INCOMPLETE_READ_ONLY"
    else:
        evidence_payload_status = "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY"
    evidence_payload_complete = evidence_payload_status == "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY"
    return {
        "symbol": symbol,
        "coverage_complete": coverage_complete,
        "coverage_blockers": coverage_blockers,
        "evidence_payload_status": evidence_payload_status,
        "evidence_payload_present": bool(evidence_payload),
        "evidence_payload_complete": evidence_payload_complete,
        "required_evidence_families": list(REQUIRED_EVIDENCE_FAMILIES),
        "missing_evidence_families": missing_evidence_families,
        "required_structural_location_inputs": list(REQUIRED_STRUCTURAL_LOCATION_INPUTS),
        "missing_structural_location_inputs": missing_structural_location_inputs,
        "doctrine_statement": DOCTRINE_STATEMENT,
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
def build_read_only_evidence_payload_completeness_from_source_coverage(
    *,
    coverage: Dict[str, Any],
) -> Dict[str, Any]:
    coverage_rows = _as_list(coverage.get("coverage_rows"))
    evidence_rows = [
        _evidence_row(row)
        for row in coverage_rows
        if isinstance(row, dict)
    ]
    complete_rows = [
        row for row in evidence_rows
        if row["evidence_payload_complete"] is True
    ]
    blocked_by_coverage_rows = [
        row for row in evidence_rows
        if row["evidence_payload_status"] == "EVIDENCE_PAYLOAD_BLOCKED_BY_SOURCE_COVERAGE_READ_ONLY"
    ]
    missing_payload_rows = [
        row for row in evidence_rows
        if row["evidence_payload_status"] == "EVIDENCE_PAYLOAD_MISSING_READ_ONLY"
    ]
    incomplete_payload_rows = [
        row for row in evidence_rows
        if row["evidence_payload_status"] == "EVIDENCE_PAYLOAD_INCOMPLETE_READ_ONLY"
    ]
    evidence_payload_completeness_status = (
        "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY"
        if evidence_rows and len(complete_rows) == len(evidence_rows)
        else "EVIDENCE_PAYLOAD_INCOMPLETE_OR_BLOCKED_READ_ONLY"
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
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "evidence_payload_completeness_status": evidence_payload_completeness_status,
        "source_coverage_completion_status": coverage.get("source_coverage_completion_status"),
        "coverage_is_complete": coverage.get("coverage_is_complete") is True,
        "requested_symbols": coverage.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(coverage.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(coverage.get("audited_symbol_count")),
        "evidence_row_count": len(evidence_rows),
        "evidence_payload_complete_symbol_count": len(complete_rows),
        "evidence_payload_blocked_by_coverage_symbol_count": len(blocked_by_coverage_rows),
        "evidence_payload_missing_symbol_count": len(missing_payload_rows),
        "evidence_payload_incomplete_symbol_count": len(incomplete_payload_rows),
        "evidence_payload_complete_symbols": [row["symbol"] for row in complete_rows],
        "evidence_payload_blocked_by_coverage_symbols": [row["symbol"] for row in blocked_by_coverage_rows],
        "evidence_payload_missing_symbols": [row["symbol"] for row in missing_payload_rows],
        "evidence_payload_incomplete_symbols": [row["symbol"] for row in incomplete_payload_rows],
        "required_evidence_families": list(REQUIRED_EVIDENCE_FAMILIES),
        "required_structural_location_inputs": list(REQUIRED_STRUCTURAL_LOCATION_INPUTS),
        "evidence_rows": evidence_rows,
        "guardrail_failure_count": _as_int(coverage.get("guardrail_failure_count")),
        "guardrail_failures": list(coverage.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "evidence_audit_applies_no_changes": True,
        "evidence_audit_is_read_only": True,
        "guardrails": _guardrails(),
    }
def run_read_only_evidence_payload_completeness_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    coverage = run_read_only_source_coverage_completion_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_evidence_payload_completeness_from_source_coverage(
        coverage=coverage,
    )

