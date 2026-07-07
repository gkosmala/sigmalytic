from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.source_gap_dashboard_audit import (
    run_read_only_alert_source_gap_dashboard_audit,
)
COMPONENT = "ALERT_CONSOLE_SNAPSHOT_AUDIT_READ_ONLY"
VERSION = "alert_console_snapshot_audit_read_only_v1"
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
def _symbols_from_cards(cards: List[Any]) -> List[str]:
    symbols: List[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        symbol = str(card.get("symbol") or "").strip().upper()
        if symbol:
            symbols.append(symbol)
    return symbols
def _primary_console_status(
    dashboard: Dict[str, Any],
    *,
    dashboard_rows: List[Any],
    ready_cards: List[Any],
    blocked_cards: List[Any],
) -> str:
    guardrail_failure_count = _as_int(dashboard.get("guardrail_failure_count"))
    blocked_card_count = len(blocked_cards)
    ready_card_count = len(ready_cards)
    dashboard_row_count = len(dashboard_rows)
    if guardrail_failure_count > 0:
        return "ALERT_CONSOLE_STOP_GUARDRAIL_INSPECTION_REQUIRED_READ_ONLY"
    if dashboard_row_count <= 0:
        return "ALERT_CONSOLE_NO_SYMBOLS_AUDITED_READ_ONLY"
    if blocked_card_count > 0:
        return "ALERT_CONSOLE_SOURCE_REMEDIATION_REQUIRED_READ_ONLY"
    if ready_card_count == dashboard_row_count:
        return "ALERT_CONSOLE_READY_FOR_REVIEW_READ_ONLY"
    return "ALERT_CONSOLE_MIXED_READINESS_REVIEW_REQUIRED_READ_ONLY"
def _top_console_actions(dashboard: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    severity_counts = dashboard.get("severity_counts") or {}
    if _as_int(dashboard.get("guardrail_failure_count")) > 0:
        actions.append("STOP_AND_INSPECT_GUARDRAILS_READ_ONLY")
    if _as_int(severity_counts.get("SOURCE_REQUIRED_READ_ONLY")) > 0:
        actions.append("ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCES_READ_ONLY")
    if _as_int(severity_counts.get("RECENT_BAR_REQUIRED_READ_ONLY")) > 0:
        actions.append("RECHECK_RECENT_OHLCV_FEED_WINDOWS_READ_ONLY")
    if _as_int(severity_counts.get("READINESS_RECHECK_REQUIRED_READ_ONLY")) > 0:
        actions.append("RERUN_LIVE_READINESS_AFTER_SOURCE_REMEDIATION_READ_ONLY")
    if not actions:
        actions.append("NO_SOURCE_REMEDIATION_ACTION_REQUIRED_READ_ONLY")
    return actions
def build_read_only_alert_console_snapshot_from_dashboard(
    *,
    dashboard: Dict[str, Any],
) -> Dict[str, Any]:
    ready_cards = _as_list(dashboard.get("ready_cards"))
    blocked_cards = _as_list(dashboard.get("blocked_cards"))
    dashboard_rows = _as_list(dashboard.get("dashboard_rows"))
    console_status = _primary_console_status(
        dashboard,
        dashboard_rows=dashboard_rows,
        ready_cards=ready_cards,
        blocked_cards=blocked_cards,
    )
    top_actions = _top_console_actions(dashboard)
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
        "console_snapshot_status": console_status,
        "top_console_actions": top_actions,
        "dashboard_status": dashboard.get("dashboard_status"),
        "remediation_status": dashboard.get("remediation_status"),
        "source_gap_status": dashboard.get("source_gap_status"),
        "requested_symbols": dashboard.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(dashboard.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(dashboard.get("audited_symbol_count")),
        "dashboard_row_count": len(dashboard_rows),
        "ready_card_count": len(ready_cards),
        "blocked_card_count": len(blocked_cards),
        "ready_symbols": _symbols_from_cards(ready_cards),
        "blocked_symbols": _symbols_from_cards(blocked_cards),
        "severity_counts": dashboard.get("severity_counts") or {},
        "blocking_class_counts": dashboard.get("blocking_class_counts") or {},
        "console_cards": dashboard_rows,
        "guardrail_failure_count": _as_int(dashboard.get("guardrail_failure_count")),
        "guardrail_failures": list(dashboard.get("guardrail_failures") or []),
        "guardrails": _guardrails(),
    }
def run_read_only_alert_console_snapshot_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
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
    return build_read_only_alert_console_snapshot_from_dashboard(
        dashboard=dashboard,
    )

