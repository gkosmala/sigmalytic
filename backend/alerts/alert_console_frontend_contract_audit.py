from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.alert_console_view_model_audit import (
    run_read_only_alert_console_view_model_audit,
)
COMPONENT = "ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY"
VERSION = "alert_console_frontend_contract_audit_read_only_v1"
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
REQUIRED_TOP_LEVEL_VIEW_MODEL_KEYS = [
    "header",
    "action_banner",
    "summary_tiles",
    "symbol_cards",
    "footer",
]
REQUIRED_SYMBOL_CARD_KEYS = [
    "symbol",
    "title",
    "display_status",
    "blocking_class",
    "severity",
    "gap_reasons",
    "remediation_steps",
    "diagnostic_only",
    "read_only",
    "writes_to_supabase",
    "mutates_campaigns",
    "executes_d3d",
    "authorizes_d3d",
    "operator_control_confirmed",
    "not_a_trade_signal",
    "changes_scores",
    "changes_ranks",
    "changes_states",
    "changes_probabilities",
    "changes_edge",
    "d3d_execution_recommendation",
    "can_execute_d3d",
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
def _missing_keys(payload: Any, required_keys: List[str]) -> List[str]:
    if not isinstance(payload, dict):
        return list(required_keys)
    return [key for key in required_keys if key not in payload]
def _guardrail_failures_for_card(card: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    expected_false = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed",
        "changes_scores",
        "changes_ranks",
        "changes_states",
        "changes_probabilities",
        "changes_edge",
        "can_execute_d3d",
    ]
    for key in expected_false:
        if card.get(key) is not False:
            failures.append(
                {
                    "card_index": index,
                    "symbol": card.get("symbol"),
                    "field": key,
                    "expected": False,
                    "actual": card.get(key),
                }
            )
    expected_true = [
        "diagnostic_only",
        "read_only",
        "not_a_trade_signal",
    ]
    for key in expected_true:
        if card.get(key) is not True:
            failures.append(
                {
                    "card_index": index,
                    "symbol": card.get("symbol"),
                    "field": key,
                    "expected": True,
                    "actual": card.get(key),
                }
            )
    if card.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "card_index": index,
                "symbol": card.get("symbol"),
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": card.get("d3d_execution_recommendation"),
            }
        )
    return failures
def build_read_only_alert_console_frontend_contract_from_view_model(
    *,
    view_payload: Dict[str, Any],
) -> Dict[str, Any]:
    view_model = view_payload.get("view_model") or {}
    missing_view_model_keys = _missing_keys(
        view_model,
        REQUIRED_TOP_LEVEL_VIEW_MODEL_KEYS,
    )
    symbol_cards = _as_list(view_model.get("symbol_cards"))
    symbol_card_contract_failures: List[Dict[str, Any]] = []
    symbol_card_guardrail_failures: List[Dict[str, Any]] = []
    for index, card in enumerate(symbol_cards):
        if not isinstance(card, dict):
            symbol_card_contract_failures.append(
                {
                    "card_index": index,
                    "symbol": None,
                    "missing_keys": list(REQUIRED_SYMBOL_CARD_KEYS),
                    "reason": "SYMBOL_CARD_NOT_OBJECT_READ_ONLY",
                }
            )
            continue
        missing_card_keys = _missing_keys(card, REQUIRED_SYMBOL_CARD_KEYS)
        if missing_card_keys:
            symbol_card_contract_failures.append(
                {
                    "card_index": index,
                    "symbol": card.get("symbol"),
                    "missing_keys": missing_card_keys,
                    "reason": "SYMBOL_CARD_CONTRACT_MISSING_KEYS_READ_ONLY",
                }
            )
        symbol_card_guardrail_failures.extend(
            _guardrail_failures_for_card(card, index)
        )
    missing_contract_failure_count = len(missing_view_model_keys) + len(symbol_card_contract_failures)
    guardrail_failure_count = (
        _as_int(view_payload.get("guardrail_failure_count"))
        + len(symbol_card_guardrail_failures)
    )
    frontend_contract_status = (
        "ALERT_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY"
        if missing_contract_failure_count == 0 and guardrail_failure_count == 0
        else "ALERT_CONSOLE_FRONTEND_CONTRACT_BLOCKED_READ_ONLY"
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
        "frontend_contract_status": frontend_contract_status,
        "view_model_status": view_payload.get("view_model_status"),
        "console_snapshot_status": view_payload.get("console_snapshot_status"),
        "dashboard_status": view_payload.get("dashboard_status"),
        "remediation_status": view_payload.get("remediation_status"),
        "source_gap_status": view_payload.get("source_gap_status"),
        "requested_symbols": view_payload.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(view_payload.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(view_payload.get("audited_symbol_count")),
        "ready_card_count": _as_int(view_payload.get("ready_card_count")),
        "blocked_card_count": _as_int(view_payload.get("blocked_card_count")),
        "ready_symbols": _as_list(view_payload.get("ready_symbols")),
        "blocked_symbols": _as_list(view_payload.get("blocked_symbols")),
        "view_model_symbol_card_count": len(symbol_cards),
        "required_view_model_keys": list(REQUIRED_TOP_LEVEL_VIEW_MODEL_KEYS),
        "required_symbol_card_keys": list(REQUIRED_SYMBOL_CARD_KEYS),
        "missing_view_model_keys": missing_view_model_keys,
        "symbol_card_contract_failures": symbol_card_contract_failures,
        "symbol_card_guardrail_failures": symbol_card_guardrail_failures,
        "missing_contract_failure_count": missing_contract_failure_count,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(view_payload.get("guardrail_failures") or []) + symbol_card_guardrail_failures,
        "frontend_contract_is_safe_to_render": frontend_contract_status == "ALERT_CONSOLE_FRONTEND_CONTRACT_READY_READ_ONLY",
        "frontend_contract_is_read_only": True,
        "frontend_contract_applies_no_changes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_alert_console_frontend_contract_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    view_payload = run_read_only_alert_console_view_model_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_alert_console_frontend_contract_from_view_model(
        view_payload=view_payload,
    )
