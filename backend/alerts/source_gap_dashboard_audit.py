from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.source_gap_remediation_audit import (
    run_read_only_alert_source_gap_remediation_audit,
)
COMPONENT = "ALERT_SOURCE_GAP_DASHBOARD_AUDIT_READ_ONLY"
VERSION = "alert_source_gap_dashboard_audit_read_only_v1"
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
def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _severity_from_blocking_class(blocking_class: str) -> str:
    if blocking_class == "GUARDRAIL_BLOCK_READ_ONLY":
        return "STOP_INSPECT_GUARDRAILS_READ_ONLY"
    if blocking_class == "EXPLICIT_SOURCE_BLOCK_READ_ONLY":
        return "SOURCE_REQUIRED_READ_ONLY"
    if blocking_class == "RECENT_BAR_BLOCK_READ_ONLY":
        return "RECENT_BAR_REQUIRED_READ_ONLY"
    if blocking_class == "READINESS_BLOCK_READ_ONLY":
        return "READINESS_RECHECK_REQUIRED_READ_ONLY"
    return "NO_ACTION_REQUIRED_READ_ONLY"
def _display_status(blocking_class: str) -> str:
    if blocking_class == "NO_BLOCK_READ_ONLY":
        return "SOURCE_READY_READ_ONLY"
    return "BLOCKED_PENDING_SOURCE_REMEDIATION_READ_ONLY"
def build_read_only_alert_source_gap_dashboard_from_remediation(
    *,
    remediation: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _as_list(remediation.get("remediation_rows"))
    dashboard_rows: List[Dict[str, Any]] = []
    ready_cards: List[Dict[str, Any]] = []
    blocked_cards: List[Dict[str, Any]] = []
    severity_counts: Dict[str, int] = {}
    blocking_class_counts: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _clean_symbol(row.get("symbol"))
        blocking_class = str(row.get("blocking_class") or "READINESS_BLOCK_READ_ONLY")
        severity = _severity_from_blocking_class(blocking_class)
        display_status = _display_status(blocking_class)
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        blocking_class_counts[blocking_class] = blocking_class_counts.get(blocking_class, 0) + 1
        card = {
            "symbol": symbol,
            "display_status": display_status,
            "severity": severity,
            "blocking_class": blocking_class,
            "gap_reasons": _as_list(row.get("gap_reasons")),
            "remediation_steps": _as_list(row.get("remediation_steps")),
            "automated_fix_applied": False,
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
        dashboard_rows.append(card)
        if blocking_class == "NO_BLOCK_READ_ONLY":
            ready_cards.append(card)
        else:
            blocked_cards.append(card)
    dashboard_status = (
        "ALERT_SOURCE_GAP_DASHBOARD_ALL_READY_READ_ONLY"
        if dashboard_rows and len(ready_cards) == len(dashboard_rows)
        else "ALERT_SOURCE_GAP_DASHBOARD_ACTION_REQUIRED_READ_ONLY"
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
        "dashboard_status": dashboard_status,
        "remediation_status": remediation.get("remediation_status"),
        "source_gap_status": remediation.get("source_gap_status"),
        "requested_symbols": remediation.get("requested_symbols") or [],
        "requested_symbol_count": int(remediation.get("requested_symbol_count") or 0),
        "audited_symbol_count": int(remediation.get("audited_symbol_count") or 0),
        "dashboard_row_count": len(dashboard_rows),
        "ready_card_count": len(ready_cards),
        "blocked_card_count": len(blocked_cards),
        "severity_counts": severity_counts,
        "blocking_class_counts": blocking_class_counts,
        "ready_cards": ready_cards,
        "blocked_cards": blocked_cards,
        "dashboard_rows": dashboard_rows,
        "upstream_guardrail_failure_count": int(remediation.get("guardrail_failure_count") or 0),
        "guardrail_failure_count": int(remediation.get("guardrail_failure_count") or 0),
        "guardrail_failures": list(remediation.get("guardrail_failures") or []),
        "guardrails": _guardrails(),
    }
def run_read_only_alert_source_gap_dashboard_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    remediation = run_read_only_alert_source_gap_remediation_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_alert_source_gap_dashboard_from_remediation(
        remediation=remediation,
    )
