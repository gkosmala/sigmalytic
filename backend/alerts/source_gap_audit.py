from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.live_readiness_batch_audit import run_read_only_live_readiness_batch_audit
COMPONENT = "ALERT_SOURCE_GAP_AUDIT_READ_ONLY"
VERSION = "alert_source_gap_audit_read_only_v1"
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
def _as_bool(value: Any) -> bool:
    return value is True
def _clean_symbols(symbols: Any) -> str:
    if symbols is None:
        return "SPY,QQQ,IWM"
    return str(symbols).strip() or "SPY,QQQ,IWM"
def _gap_reasons(row: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    if _as_bool(row.get("recent_bars_accepted")) is False:
        reasons.append("RECENT_OHLCV_BARS_NOT_ACCEPTED")
    if _as_bool(row.get("explicit_source_available")) is False:
        reasons.append("EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE")
    if row.get("bar_source_quality") != "USABLE_RECENT_OHLCV_BARS":
        reasons.append("BAR_SOURCE_QUALITY_NOT_USABLE_RECENT_OHLCV_BARS")
    if row.get("bar_adapter_status") != "ADAPTER_OK_BARS_LOADED_READ_ONLY":
        reasons.append("BAR_ADAPTER_NOT_OK")
    if int(row.get("guardrail_failure_count") or 0) != 0:
        reasons.append("NESTED_GUARDRAIL_FAILURE_PRESENT")
    if row.get("readiness_status") != "LIVE_READINESS_AUDIT_READY_READ_ONLY":
        reasons.append("LIVE_READINESS_NOT_READY")
    return reasons
def build_read_only_alert_source_gap_audit_from_batch(
    *,
    batch: Dict[str, Any],
) -> Dict[str, Any]:
    audit_results = list(batch.get("audit_results") or [])
    rows: List[Dict[str, Any]] = []
    source_ready_symbols: List[str] = []
    missing_explicit_source_symbols: List[str] = []
    missing_recent_bar_symbols: List[str] = []
    blocked_symbols: List[str] = []
    reason_counts: Dict[str, int] = {}
    for item in audit_results:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper()
        reasons = _gap_reasons(item)
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if not reasons:
            source_ready_symbols.append(symbol)
        else:
            blocked_symbols.append(symbol)
        if "EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE" in reasons:
            missing_explicit_source_symbols.append(symbol)
        if "RECENT_OHLCV_BARS_NOT_ACCEPTED" in reasons:
            missing_recent_bar_symbols.append(symbol)
        rows.append({
            "symbol": symbol,
            "source_gap_status": "SOURCE_READY_READ_ONLY" if not reasons else "SOURCE_GAP_BLOCKED_READ_ONLY",
            "gap_reasons": reasons,
            "readiness_status": item.get("readiness_status"),
            "live_review_status": item.get("live_review_status"),
            "recent_bars_accepted": _as_bool(item.get("recent_bars_accepted")),
            "explicit_source_available": _as_bool(item.get("explicit_source_available")),
            "bar_adapter_status": item.get("bar_adapter_status"),
            "bar_source_quality": item.get("bar_source_quality"),
            "bar_source_type": item.get("bar_source_type"),
            "bar_count": item.get("bar_count"),
            "bar_window_start": item.get("bar_window_start"),
            "bar_window_end": item.get("bar_window_end"),
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
        })
    source_gap_status = (
        "ALERT_SOURCE_GAP_AUDIT_READY_READ_ONLY"
        if rows and len(source_ready_symbols) == len(rows)
        else "ALERT_SOURCE_GAP_AUDIT_GAPS_FOUND_READ_ONLY"
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
        "source_gap_status": source_gap_status,
        "requested_symbols": batch.get("requested_symbols") or [],
        "requested_symbol_count": int(batch.get("requested_symbol_count") or 0),
        "audited_symbol_count": len(rows),
        "source_ready_symbol_count": len(source_ready_symbols),
        "blocked_symbol_count": len(blocked_symbols),
        "missing_explicit_source_symbol_count": len(missing_explicit_source_symbols),
        "missing_recent_bar_symbol_count": len(missing_recent_bar_symbols),
        "source_ready_symbols": source_ready_symbols,
        "blocked_symbols": blocked_symbols,
        "missing_explicit_source_symbols": missing_explicit_source_symbols,
        "missing_recent_bar_symbols": missing_recent_bar_symbols,
        "reason_counts": reason_counts,
        "source_gap_rows": rows,
        "upstream_batch_status": batch.get("batch_readiness_status"),
        "upstream_guardrail_failure_count": int(batch.get("guardrail_failure_count") or 0),
        "guardrail_failure_count": int(batch.get("guardrail_failure_count") or 0),
        "guardrail_failures": list(batch.get("guardrail_failures") or []),
        "guardrails": _guardrails(),
    }
def run_read_only_alert_source_gap_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    batch = run_read_only_live_readiness_batch_audit(
        symbols=_clean_symbols(symbols),
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_alert_source_gap_audit_from_batch(batch=batch)
