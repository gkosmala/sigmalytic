from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.source_gap_audit import run_read_only_alert_source_gap_audit
COMPONENT = "ALERT_SOURCE_GAP_REMEDIATION_AUDIT_READ_ONLY"
VERSION = "alert_source_gap_remediation_audit_read_only_v1"
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
def _remediation_steps_for_reasons(reasons: List[str]) -> List[str]:
    steps: List[str] = []
    if "EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE" in reasons:
        steps.append("ATTACH_OR_VERIFY_EXPLICIT_STRUCTURAL_SOURCE_READ_ONLY")
        steps.append("RECHECK_SOURCE_RESOLUTION_FOR_SYMBOL_READ_ONLY")
    if "RECENT_OHLCV_BARS_NOT_ACCEPTED" in reasons:
        steps.append("RECHECK_RECENT_OHLCV_FEED_WINDOW_READ_ONLY")
        steps.append("VERIFY_ALPACA_RECENT_BAR_SORTING_AND_WINDOW_READ_ONLY")
    if "BAR_SOURCE_QUALITY_NOT_USABLE_RECENT_OHLCV_BARS" in reasons:
        steps.append("VERIFY_BAR_SOURCE_QUALITY_READ_ONLY")
    if "BAR_ADAPTER_NOT_OK" in reasons:
        steps.append("INSPECT_BAR_ADAPTER_STATUS_READ_ONLY")
    if "NESTED_GUARDRAIL_FAILURE_PRESENT" in reasons:
        steps.append("STOP_AND_INSPECT_NESTED_GUARDRAILS_READ_ONLY")
    if "LIVE_READINESS_NOT_READY" in reasons:
        steps.append("RERUN_LIVE_READINESS_AFTER_SOURCE_GAPS_RESOLVED_READ_ONLY")
    if not steps:
        steps.append("NO_REMEDIATION_REQUIRED_READ_ONLY")
    return steps
def _blocking_class(reasons: List[str]) -> str:
    if "NESTED_GUARDRAIL_FAILURE_PRESENT" in reasons:
        return "GUARDRAIL_BLOCK_READ_ONLY"
    if "EXPLICIT_STRUCTURAL_SOURCE_NOT_AVAILABLE" in reasons:
        return "EXPLICIT_SOURCE_BLOCK_READ_ONLY"
    if "RECENT_OHLCV_BARS_NOT_ACCEPTED" in reasons:
        return "RECENT_BAR_BLOCK_READ_ONLY"
    if reasons:
        return "READINESS_BLOCK_READ_ONLY"
    return "NO_BLOCK_READ_ONLY"
def build_read_only_alert_source_gap_remediation_audit_from_gap(
    *,
    gap: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _as_list(gap.get("source_gap_rows"))
    remediation_rows: List[Dict[str, Any]] = []
    no_action_symbols: List[str] = []
    explicit_source_block_symbols: List[str] = []
    recent_bar_block_symbols: List[str] = []
    guardrail_block_symbols: List[str] = []
    other_readiness_block_symbols: List[str] = []
    remediation_step_counts: Dict[str, int] = {}
    blocking_class_counts: Dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _clean_symbol(row.get("symbol"))
        reasons = [str(reason) for reason in _as_list(row.get("gap_reasons"))]
        blocking_class = _blocking_class(reasons)
        steps = _remediation_steps_for_reasons(reasons)
        blocking_class_counts[blocking_class] = blocking_class_counts.get(blocking_class, 0) + 1
        for step in steps:
            remediation_step_counts[step] = remediation_step_counts.get(step, 0) + 1
        if blocking_class == "NO_BLOCK_READ_ONLY":
            no_action_symbols.append(symbol)
        elif blocking_class == "EXPLICIT_SOURCE_BLOCK_READ_ONLY":
            explicit_source_block_symbols.append(symbol)
        elif blocking_class == "RECENT_BAR_BLOCK_READ_ONLY":
            recent_bar_block_symbols.append(symbol)
        elif blocking_class == "GUARDRAIL_BLOCK_READ_ONLY":
            guardrail_block_symbols.append(symbol)
        else:
            other_readiness_block_symbols.append(symbol)
        remediation_rows.append({
            "symbol": symbol,
            "source_gap_status": row.get("source_gap_status"),
            "blocking_class": blocking_class,
            "gap_reasons": reasons,
            "remediation_steps": steps,
            "remediation_is_read_only": True,
            "automated_fix_applied": False,
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
            "diagnostic_only": True,
            "read_only": True,
        })
    remediation_status = (
        "ALERT_SOURCE_GAP_REMEDIATION_NOT_REQUIRED_READ_ONLY"
        if remediation_rows and len(no_action_symbols) == len(remediation_rows)
        else "ALERT_SOURCE_GAP_REMEDIATION_REQUIRED_READ_ONLY"
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
        "remediation_status": remediation_status,
        "source_gap_status": gap.get("source_gap_status"),
        "requested_symbols": gap.get("requested_symbols") or [],
        "requested_symbol_count": int(gap.get("requested_symbol_count") or 0),
        "audited_symbol_count": int(gap.get("audited_symbol_count") or 0),
        "remediation_row_count": len(remediation_rows),
        "no_action_symbol_count": len(no_action_symbols),
        "blocked_symbol_count": (
            len(explicit_source_block_symbols)
            + len(recent_bar_block_symbols)
            + len(guardrail_block_symbols)
            + len(other_readiness_block_symbols)
        ),
        "explicit_source_block_symbol_count": len(explicit_source_block_symbols),
        "recent_bar_block_symbol_count": len(recent_bar_block_symbols),
        "guardrail_block_symbol_count": len(guardrail_block_symbols),
        "other_readiness_block_symbol_count": len(other_readiness_block_symbols),
        "no_action_symbols": no_action_symbols,
        "explicit_source_block_symbols": explicit_source_block_symbols,
        "recent_bar_block_symbols": recent_bar_block_symbols,
        "guardrail_block_symbols": guardrail_block_symbols,
        "other_readiness_block_symbols": other_readiness_block_symbols,
        "blocking_class_counts": blocking_class_counts,
        "remediation_step_counts": remediation_step_counts,
        "remediation_rows": remediation_rows,
        "upstream_guardrail_failure_count": int(gap.get("guardrail_failure_count") or 0),
        "guardrail_failure_count": int(gap.get("guardrail_failure_count") or 0),
        "guardrail_failures": list(gap.get("guardrail_failures") or []),
        "guardrails": _guardrails(),
    }
def run_read_only_alert_source_gap_remediation_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    gap = run_read_only_alert_source_gap_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_alert_source_gap_remediation_audit_from_gap(gap=gap)
