from __future__ import annotations
from typing import Any, Dict, List, Optional
from backend.alerts.live_data_adapter import run_read_only_live_alert_review
COMPONENT = "ALERT_LIVE_READINESS_AUDIT_READ_ONLY"
VERSION = "alert_live_readiness_audit_read_only_v1"
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
}
def _guardrails() -> Dict[str, Any]:
    return {
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
        "component": COMPONENT,
        "version": VERSION,
    }
def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
def _as_bool(value: Any) -> bool:
    return value is True
def _guardrail_failures_from_live_review(live_review: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
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
    ]
    expected_true = [
        "diagnostic_only",
        "read_only",
        "not_a_trade_signal",
    ]
    for key in expected_false:
        if live_review.get(key) is not False:
            failures.append(f"live_review.{key} was not False")
    for key in expected_true:
        if live_review.get(key) is not True:
            failures.append(f"live_review.{key} was not True")
    if live_review.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append("live_review.d3d_execution_recommendation was not DO_NOT_EXECUTE_D3D")
    try:
        live_guardrail_failure_count = int(live_review.get("guardrail_failure_count") or 0)
    except Exception:
        live_guardrail_failure_count = 1
    if live_guardrail_failure_count != 0:
        failures.append("live_review.guardrail_failure_count was not zero")
    return failures
def build_read_only_live_readiness_audit_from_review(
    *,
    live_review: Dict[str, Any],
) -> Dict[str, Any]:
    live_review = _as_dict(live_review)
    symbol = str(live_review.get("symbol") or "").upper()
    requested_timeframe = str(live_review.get("requested_timeframe") or "")
    bar_adapter = _as_dict(live_review.get("bar_adapter"))
    explicit_source_adapter = _as_dict(live_review.get("explicit_source_adapter"))
    guardrail_failures = _guardrail_failures_from_live_review(live_review)
    review_ready = _as_bool(live_review.get("review_ready"))
    explicit_source_available = _as_bool(live_review.get("explicit_source_available"))
    bar_source_quality = bar_adapter.get("source_quality")
    bar_adapter_status = bar_adapter.get("adapter_status")
    live_review_status = live_review.get("live_review_status")
    recent_bars_accepted = (
        review_ready
        and bar_source_quality == "USABLE_RECENT_OHLCV_BARS"
        and bar_adapter_status == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
    )
    readiness_reasons: List[str] = []
    if not live_review.get("ok"):
        readiness_status = "LIVE_REVIEW_UNAVAILABLE_READ_ONLY"
        readiness_reasons.append("Live review did not return ok=true.")
    elif guardrail_failures:
        readiness_status = "LIVE_REVIEW_GUARDRAIL_FAILURE_READ_ONLY"
        readiness_reasons.append("Live review failed one or more read-only no-drift guardrails.")
    elif recent_bars_accepted and explicit_source_available:
        readiness_status = "LIVE_READINESS_AUDIT_READY_READ_ONLY"
        readiness_reasons.append("Recent read-only OHLCV bars were accepted.")
        readiness_reasons.append("Explicit structural source was available.")
    elif not review_ready:
        readiness_status = "LIVE_READINESS_AUDIT_BLOCKED_READ_ONLY"
        readiness_reasons.append("Live review was not ready.")
    else:
        readiness_status = "LIVE_READINESS_AUDIT_NOT_READY_READ_ONLY"
        readiness_reasons.append("Live review was available but did not satisfy recent-bar and explicit-source readiness.")
    if not explicit_source_available:
        readiness_reasons.append("Explicit structural source was not available.")
    if bar_source_quality != "USABLE_RECENT_OHLCV_BARS":
        readiness_reasons.append(f"Bar source quality was {bar_source_quality}.")
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "symbol": symbol,
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
        "readiness_status": readiness_status,
        "readiness_reasons": readiness_reasons,
        "live_review_status": live_review_status,
        "live_review_ready": review_ready,
        "recent_bars_accepted": recent_bars_accepted,
        "explicit_source_available": explicit_source_available,
        "bar_adapter_status": bar_adapter_status,
        "bar_source_quality": bar_source_quality,
        "bar_source_type": bar_adapter.get("source_type"),
        "bar_count": bar_adapter.get("bar_count"),
        "bar_window_start": bar_adapter.get("window_start"),
        "bar_window_end": bar_adapter.get("window_end"),
        "explicit_source_adapter_status": explicit_source_adapter.get("adapter_status"),
        "explicit_source_quality": explicit_source_adapter.get("source_quality"),
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "live_review_summary": {
            "ok": live_review.get("ok"),
            "component": live_review.get("component"),
            "version": live_review.get("version"),
            "review_ready": live_review.get("review_ready"),
            "live_review_status": live_review.get("live_review_status"),
            "operator_control_confirmed": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "not_a_trade_signal": True,
        },
        "guardrails": _guardrails(),
    }
def run_read_only_live_readiness_audit(
    *,
    symbol: str,
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    timeout_seconds: int = 30,
    candidate_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    live_review = run_read_only_live_alert_review(
        symbol=symbol,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        timeout_seconds=timeout_seconds,
        candidate_payload=candidate_payload,
    )
    return build_read_only_live_readiness_audit_from_review(
        live_review=live_review,
    )
