from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.source_gap_dashboard_audit import (
    run_read_only_alert_source_gap_dashboard_audit,
)
COMPONENT = "SOURCE_COVERAGE_COMPLETION_AUDIT_READ_ONLY"
VERSION = "source_coverage_completion_audit_read_only_v1"
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
def _coverage_row(card: Dict[str, Any]) -> Dict[str, Any]:
    gap_reasons = [str(item) for item in _as_list(card.get("gap_reasons"))]
    remediation_steps = [str(item) for item in _as_list(card.get("remediation_steps"))]
    blocking_class = str(card.get("blocking_class") or "")
    explicit_source_present = (
        "EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE" not in gap_reasons
        and blocking_class != "EXPLICIT_SOURCE_BLOCK_READ_ONLY"
    )
    recent_ohlcv_present = (
        "RECENT_OHLCV_BARS_NOT_ACCEPTED" not in gap_reasons
        and "BAR_SOURCE_QUALITY_NOT_USABLE_RECENT_OHLCV_BARS" not in gap_reasons
        and "BAR_ADAPTER_NOT_OK" not in gap_reasons
        and blocking_class != "RECENT_BAR_BLOCK_READ_ONLY"
    )
    guardrail_clear = "NESTED_GUARDRAIL_FAILURE_PRESENT" not in gap_reasons
    coverage_complete = (
        explicit_source_present
        and recent_ohlcv_present
        and guardrail_clear
    )
    blockers: List[str] = []
    if not explicit_source_present:
        blockers.append("EXPLICIT_STRUCTURAL_SOURCE_COVERAGE_MISSING_READ_ONLY")
    if not recent_ohlcv_present:
        blockers.append("RECENT_OHLCV_COVERAGE_MISSING_READ_ONLY")
    if not guardrail_clear:
        blockers.append("NESTED_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if not blockers:
        blockers.append("NO_SOURCE_COVERAGE_BLOCKER_READ_ONLY")
    return {
        "symbol": _symbol(card.get("symbol")),
        "coverage_complete": coverage_complete,
        "explicit_structural_source_present": explicit_source_present,
        "recent_ohlcv_source_present": recent_ohlcv_present,
        "guardrail_clear": guardrail_clear,
        "blocking_class": blocking_class,
        "display_status": str(card.get("display_status") or ""),
        "gap_reasons": gap_reasons,
        "coverage_blockers": blockers,
        "remediation_steps": remediation_steps,
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
def build_read_only_source_coverage_completion_from_dashboard(
    *,
    dashboard: Dict[str, Any],
) -> Dict[str, Any]:
    dashboard_rows = _as_list(dashboard.get("dashboard_rows"))
    coverage_rows = [
        _coverage_row(row)
        for row in dashboard_rows
        if isinstance(row, dict)
    ]
    complete_rows = [row for row in coverage_rows if row["coverage_complete"] is True]
    blocked_rows = [row for row in coverage_rows if row["coverage_complete"] is not True]
    missing_explicit_rows = [
        row for row in coverage_rows
        if row["explicit_structural_source_present"] is not True
    ]
    missing_recent_ohlcv_rows = [
        row for row in coverage_rows
        if row["recent_ohlcv_source_present"] is not True
    ]
    guardrail_blocked_rows = [
        row for row in coverage_rows
        if row["guardrail_clear"] is not True
    ]
    guardrail_failure_count = _as_int(dashboard.get("guardrail_failure_count")) + len(guardrail_blocked_rows)
    source_coverage_completion_status = (
        "SOURCE_COVERAGE_COMPLETE_READ_ONLY"
        if coverage_rows and not blocked_rows and guardrail_failure_count == 0
        else "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY"
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
        "source_coverage_completion_status": source_coverage_completion_status,
        "dashboard_status": dashboard.get("dashboard_status"),
        "remediation_status": dashboard.get("remediation_status"),
        "source_gap_status": dashboard.get("source_gap_status"),
        "requested_symbols": dashboard.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(dashboard.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(dashboard.get("audited_symbol_count")),
        "coverage_row_count": len(coverage_rows),
        "coverage_complete_symbol_count": len(complete_rows),
        "coverage_blocked_symbol_count": len(blocked_rows),
        "missing_explicit_source_symbol_count": len(missing_explicit_rows),
        "missing_recent_ohlcv_symbol_count": len(missing_recent_ohlcv_rows),
        "guardrail_blocked_symbol_count": len(guardrail_blocked_rows),
        "coverage_complete_symbols": [row["symbol"] for row in complete_rows],
        "coverage_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "missing_explicit_source_symbols": [row["symbol"] for row in missing_explicit_rows],
        "missing_recent_ohlcv_symbols": [row["symbol"] for row in missing_recent_ohlcv_rows],
        "guardrail_blocked_symbols": [row["symbol"] for row in guardrail_blocked_rows],
        "coverage_rows": coverage_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(dashboard.get("guardrail_failures") or []),
        "coverage_is_complete": source_coverage_completion_status == "SOURCE_COVERAGE_COMPLETE_READ_ONLY",
        "coverage_audit_applies_no_changes": True,
        "coverage_audit_is_read_only": True,
        "guardrails": _guardrails(),
    }
def run_read_only_source_coverage_completion_audit(
    *,
    symbols: Any = "SPY",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    dashboard = run_read_only_alert_source_gap_dashboard_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_source_coverage_completion_from_dashboard(
        dashboard=dashboard,
    )
