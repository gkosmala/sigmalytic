from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.alert_console_snapshot_audit import (
    run_read_only_alert_console_snapshot_audit,
)
COMPONENT = "ALERT_CONSOLE_VIEW_MODEL_AUDIT_READ_ONLY"
VERSION = "alert_console_view_model_audit_read_only_v1"
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
def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _action_banner(console_status: str, top_actions: List[Any]) -> Dict[str, Any]:
    actions = [str(action) for action in top_actions if str(action or "").strip()]
    if console_status == "ALERT_CONSOLE_SOURCE_REMEDIATION_REQUIRED_READ_ONLY":
        banner_type = "SOURCE_REMEDIATION_REQUIRED_READ_ONLY"
        banner_label = "Explicit structural source review required"
    elif console_status == "ALERT_CONSOLE_STOP_GUARDRAIL_INSPECTION_REQUIRED_READ_ONLY":
        banner_type = "GUARDRAIL_INSPECTION_REQUIRED_READ_ONLY"
        banner_label = "Guardrail inspection required"
    elif console_status == "ALERT_CONSOLE_READY_FOR_REVIEW_READ_ONLY":
        banner_type = "READY_FOR_REVIEW_READ_ONLY"
        banner_label = "Ready for read-only review"
    else:
        banner_type = "MIXED_REVIEW_REQUIRED_READ_ONLY"
        banner_label = "Read-only review required"
    return {
        "banner_type": banner_type,
        "banner_label": banner_label,
        "top_actions": actions,
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
def _summary_tiles(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "tile_id": "audited_symbols_read_only",
            "label": "Audited symbols",
            "value": _as_int(snapshot.get("audited_symbol_count")),
            "diagnostic_only": True,
            "read_only": True,
            "not_a_trade_signal": True,
        },
        {
            "tile_id": "ready_symbols_read_only",
            "label": "Ready symbols",
            "value": _as_int(snapshot.get("ready_card_count")),
            "diagnostic_only": True,
            "read_only": True,
            "not_a_trade_signal": True,
        },
        {
            "tile_id": "blocked_symbols_read_only",
            "label": "Blocked symbols",
            "value": _as_int(snapshot.get("blocked_card_count")),
            "diagnostic_only": True,
            "read_only": True,
            "not_a_trade_signal": True,
        },
        {
            "tile_id": "guardrail_failures_read_only",
            "label": "Guardrail failures",
            "value": _as_int(snapshot.get("guardrail_failure_count")),
            "diagnostic_only": True,
            "read_only": True,
            "not_a_trade_signal": True,
        },
    ]
def _symbol_card(card: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _clean_symbol(card.get("symbol"))
    display_status = str(card.get("display_status") or "")
    blocking_class = str(card.get("blocking_class") or "")
    severity = str(card.get("severity") or "")
    return {
        "symbol": symbol,
        "title": symbol,
        "display_status": display_status,
        "blocking_class": blocking_class,
        "severity": severity,
        "gap_reasons": _as_list(card.get("gap_reasons")),
        "remediation_steps": _as_list(card.get("remediation_steps")),
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
def _symbol_cards(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for card in _as_list(snapshot.get("console_cards")):
        if not isinstance(card, dict):
            continue
        view_card = _symbol_card(card)
        if view_card["symbol"]:
            cards.append(view_card)
    return cards
def build_read_only_alert_console_view_model_from_snapshot(
    *,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    console_status = str(snapshot.get("console_snapshot_status") or "")
    top_actions = _as_list(snapshot.get("top_console_actions"))
    symbol_cards = _symbol_cards(snapshot)
    view_model = {
        "header": {
            "title": "Alert Console",
            "subtitle": "Read-only source readiness and remediation audit",
            "status": console_status,
            "diagnostic_only": True,
            "read_only": True,
            "not_a_trade_signal": True,
        },
        "action_banner": _action_banner(console_status, top_actions),
        "summary_tiles": _summary_tiles(snapshot),
        "symbol_cards": symbol_cards,
        "footer": {
            "operator_control_confirmed": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "not_a_trade_signal": True,
            "read_only": True,
        },
    }
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
        "view_model_status": "ALERT_CONSOLE_VIEW_MODEL_READY_READ_ONLY",
        "console_snapshot_status": console_status,
        "dashboard_status": snapshot.get("dashboard_status"),
        "remediation_status": snapshot.get("remediation_status"),
        "source_gap_status": snapshot.get("source_gap_status"),
        "requested_symbols": snapshot.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(snapshot.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(snapshot.get("audited_symbol_count")),
        "ready_card_count": _as_int(snapshot.get("ready_card_count")),
        "blocked_card_count": _as_int(snapshot.get("blocked_card_count")),
        "ready_symbols": _as_list(snapshot.get("ready_symbols")),
        "blocked_symbols": _as_list(snapshot.get("blocked_symbols")),
        "top_console_actions": top_actions,
        "view_model_symbol_card_count": len(symbol_cards),
        "view_model": view_model,
        "guardrail_failure_count": _as_int(snapshot.get("guardrail_failure_count")),
        "guardrail_failures": list(snapshot.get("guardrail_failures") or []),
        "guardrails": _guardrails(),
    }
def run_read_only_alert_console_view_model_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    snapshot = run_read_only_alert_console_snapshot_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_alert_console_view_model_from_snapshot(
        snapshot=snapshot,
    )
