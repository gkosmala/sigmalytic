from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body
from backend.alerts import (
    Bar,
    ExplicitStructuralSource,
    GUARDRAILS,
    assert_no_drift_guardrails,
    run_read_only_alert_review,
)
router = APIRouter(prefix="/api/alerts", tags=["alerts-read-only"])
READ_ONLY_API_GUARDRAILS: Dict[str, Any] = {
    "api_bridge": "ALERT_A_B_C_READ_ONLY_API_BRIDGE",
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
def _safe_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except Exception as exc:
        raise ValueError(f"invalid numeric field {field_name}") from exc
def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
def _bar_from_dict(item: Dict[str, Any], index: int) -> Bar:
    if not isinstance(item, dict):
        raise ValueError(f"bar {index} must be an object")
    timestamp = item.get("timestamp_utc") or item.get("timestamp") or item.get("t") or ""
    return Bar(
        timestamp_utc=str(timestamp),
        open=_safe_float(item.get("open", item.get("o")), f"bars[{index}].open"),
        high=_safe_float(item.get("high", item.get("h")), f"bars[{index}].high"),
        low=_safe_float(item.get("low", item.get("l")), f"bars[{index}].low"),
        close=_safe_float(item.get("close", item.get("c")), f"bars[{index}].close"),
        volume=_safe_float(item.get("volume", item.get("v", 0)), f"bars[{index}].volume"),
    )
def _bars_from_payload(payload: Dict[str, Any]) -> List[Bar]:
    raw_bars = payload.get("bars") or []
    if not isinstance(raw_bars, list):
        raise ValueError("bars must be a list")
    return [_bar_from_dict(item, index) for index, item in enumerate(raw_bars)]
def _structural_source_from_payload(payload: Dict[str, Any]) -> Optional[ExplicitStructuralSource]:
    raw = payload.get("structural_source") or payload.get("explicit_structural_source")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("structural_source must be an object")
    symbol = str(raw.get("symbol") or payload.get("symbol") or "").upper().strip()
    return ExplicitStructuralSource(
        symbol=symbol,
        level_type=str(raw.get("level_type") or ""),
        price_low=_safe_float(raw.get("price_low"), "structural_source.price_low"),
        price_mid=_safe_float(raw.get("price_mid"), "structural_source.price_mid"),
        price_high=_safe_float(raw.get("price_high"), "structural_source.price_high"),
        source_method=str(raw.get("source_method") or ""),
        source_reference=str(raw.get("source_reference") or ""),
        is_explicit=_safe_bool(raw.get("is_explicit")),
        is_inferred=_safe_bool(raw.get("is_inferred")),
        is_proxy=_safe_bool(raw.get("is_proxy")),
    )
def _enforce_api_no_drift() -> None:
    assert_no_drift_guardrails()
    for key, expected in READ_ONLY_API_GUARDRAILS.items():
        if key == "api_bridge":
            continue
        if READ_ONLY_API_GUARDRAILS.get(key) != GUARDRAILS.get(key):
            raise RuntimeError(f"NO-DRIFT API FAILURE: {key} diverges from alert guardrails")
@router.get("/read-only/status")
def read_only_alert_status() -> Dict[str, Any]:
    _enforce_api_no_drift()
    return {
        "ok": True,
        "component": "ALERT_A_B_C_READ_ONLY_API_BRIDGE",
        "guardrails": dict(READ_ONLY_API_GUARDRAILS),
        "operator_control_confirmed": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "not_a_trade_signal": True,
    }
@router.post("/read-only/review")
def read_only_alert_review(payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
    _enforce_api_no_drift()
    payload = payload or {}
    symbol = str(payload.get("symbol") or "").upper().strip()
    try:
        bars = _bars_from_payload(payload)
        structural_source = _structural_source_from_payload(payload)
        review = run_read_only_alert_review(
            symbol,
            bars,
            structural_source,
        )
        return {
            "ok": True,
            "component": "ALERT_A_B_C_READ_ONLY_API_BRIDGE",
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
            "review": review,
        }
    except Exception as exc:
        return {
            "ok": False,
            "component": "ALERT_A_B_C_READ_ONLY_API_BRIDGE",
            "error": str(exc)[:300],
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        }
