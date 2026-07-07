from __future__ import annotations
from typing import Any, Dict, List, Optional
from backend.alerts.live_readiness_audit import run_read_only_live_readiness_audit
COMPONENT = "ALERT_LIVE_READINESS_BATCH_AUDIT_READ_ONLY"
VERSION = "alert_live_readiness_batch_audit_read_only_v1"
MAX_BATCH_SYMBOLS = 10
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
def _clean_symbols(symbols: Any, *, max_symbols: int = MAX_BATCH_SYMBOLS) -> List[str]:
    if symbols is None:
        raw_items: List[str] = []
    elif isinstance(symbols, str):
        raw_items = symbols.replace(";", ",").replace("|", ",").split(",")
    elif isinstance(symbols, list):
        raw_items = [str(item) for item in symbols]
    else:
        raw_items = [str(symbols)]
    cleaned: List[str] = []
    seen = set()
    for raw in raw_items:
        symbol = str(raw).strip().upper()
        if not symbol:
            continue
        if len(symbol) > 12:
            continue
        if not all(ch.isalnum() or ch in {".", "-", "^"} for ch in symbol):
            continue
        if symbol in seen:
            continue
        cleaned.append(symbol)
        seen.add(symbol)
        if len(cleaned) >= max_symbols:
            break
    return cleaned
def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
def _status_bucket(status: Any) -> str:
    text = str(status or "UNKNOWN_READINESS_STATUS").strip()
    if not text:
        return "UNKNOWN_READINESS_STATUS"
    return text
def _compact_audit_result(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _as_dict(result)
    return {
        "symbol": result.get("symbol"),
        "ok": result.get("ok") is True,
        "readiness_status": result.get("readiness_status"),
        "live_review_status": result.get("live_review_status"),
        "recent_bars_accepted": result.get("recent_bars_accepted") is True,
        "explicit_source_available": result.get("explicit_source_available") is True,
        "bar_adapter_status": result.get("bar_adapter_status"),
        "bar_source_quality": result.get("bar_source_quality"),
        "bar_source_type": result.get("bar_source_type"),
        "bar_count": result.get("bar_count"),
        "bar_window_start": result.get("bar_window_start"),
        "bar_window_end": result.get("bar_window_end"),
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
        "guardrail_failure_count": int(result.get("guardrail_failure_count") or 0),
        "guardrail_failures": list(result.get("guardrail_failures") or []),
    }
def build_read_only_live_readiness_batch_audit_from_results(
    *,
    requested_symbols: List[str],
    audit_results: List[Dict[str, Any]],
    requested_timeframe: str = "1Min",
) -> Dict[str, Any]:
    compact_results = [_compact_audit_result(result) for result in audit_results]
    readiness_counts: Dict[str, int] = {}
    ready_symbols: List[str] = []
    blocked_symbols: List[str] = []
    unavailable_symbols: List[str] = []
    guardrail_failures: List[str] = []
    for result in compact_results:
        symbol = str(result.get("symbol") or "").upper()
        status = _status_bucket(result.get("readiness_status"))
        readiness_counts[status] = readiness_counts.get(status, 0) + 1
        if status == "LIVE_READINESS_AUDIT_READY_READ_ONLY":
            ready_symbols.append(symbol)
        elif status == "LIVE_REVIEW_UNAVAILABLE_READ_ONLY":
            unavailable_symbols.append(symbol)
        else:
            blocked_symbols.append(symbol)
        for failure in result.get("guardrail_failures") or []:
            guardrail_failures.append(f"{symbol}: {failure}")
        if int(result.get("guardrail_failure_count") or 0) != 0:
            guardrail_failures.append(f"{symbol}: nested guardrail_failure_count was non-zero")
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "requested_symbols": requested_symbols,
        "requested_symbol_count": len(requested_symbols),
        "audited_symbol_count": len(compact_results),
        "requested_timeframe": requested_timeframe,
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
        "batch_readiness_status": (
            "LIVE_READINESS_BATCH_READY_READ_ONLY"
            if compact_results and len(ready_symbols) == len(compact_results) and not guardrail_failures
            else "LIVE_READINESS_BATCH_MIXED_OR_BLOCKED_READ_ONLY"
        ),
        "ready_symbol_count": len(ready_symbols),
        "blocked_symbol_count": len(blocked_symbols),
        "unavailable_symbol_count": len(unavailable_symbols),
        "ready_symbols": ready_symbols,
        "blocked_symbols": blocked_symbols,
        "unavailable_symbols": unavailable_symbols,
        "readiness_counts": readiness_counts,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "audit_results": compact_results,
        "guardrails": _guardrails(),
    }
def run_read_only_live_readiness_batch_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    timeout_seconds: int = 30,
    max_symbols: int = MAX_BATCH_SYMBOLS,
) -> Dict[str, Any]:
    clean_symbols = _clean_symbols(symbols, max_symbols=max_symbols)
    if not clean_symbols:
        return {
            "ok": False,
            "component": COMPONENT,
            "version": VERSION,
            "requested_symbols": [],
            "requested_symbol_count": 0,
            "audited_symbol_count": 0,
            "requested_timeframe": requested_timeframe,
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
            "batch_readiness_status": "LIVE_READINESS_BATCH_BLOCKED_NO_SYMBOLS_READ_ONLY",
            "ready_symbol_count": 0,
            "blocked_symbol_count": 0,
            "unavailable_symbol_count": 0,
            "ready_symbols": [],
            "blocked_symbols": [],
            "unavailable_symbols": [],
            "readiness_counts": {},
            "guardrail_failure_count": 0,
            "guardrail_failures": [],
            "audit_results": [],
            "guardrails": _guardrails(),
        }
    results: List[Dict[str, Any]] = []
    for symbol in clean_symbols:
        try:
            result = run_read_only_live_readiness_audit(
                symbol=symbol,
                requested_timeframe=requested_timeframe,
                lookback_bars=lookback_bars,
                minimum_usable_bars=minimum_usable_bars,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            result = {
                "ok": False,
                "symbol": symbol,
                "readiness_status": "LIVE_REVIEW_UNAVAILABLE_READ_ONLY",
                "live_review_status": "EXCEPTION_BLOCKED_READ_ONLY",
                "recent_bars_accepted": False,
                "explicit_source_available": False,
                "bar_adapter_status": "EXCEPTION_BLOCKED_READ_ONLY",
                "bar_source_quality": "UNAVAILABLE_READ_ONLY",
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
                "guardrail_failure_count": 0,
                "guardrail_failures": [f"read-only audit exception: {type(exc).__name__}: {exc}"],
            }
        results.append(result)
    return build_read_only_live_readiness_batch_audit_from_results(
        requested_symbols=clean_symbols,
        audit_results=results,
        requested_timeframe=requested_timeframe,
    )
