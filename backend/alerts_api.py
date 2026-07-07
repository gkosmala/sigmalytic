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
# === ALERT LIVE DATA ADAPTER ENDPOINT START ===
try:
    from backend.alerts.live_data_adapter import run_read_only_live_alert_review
except Exception as _alert_live_import_exc:
    run_read_only_live_alert_review = None
    _alert_live_import_error = f"{type(_alert_live_import_exc).__name__}: {_alert_live_import_exc}"
else:
    _alert_live_import_error = None
@router.get("/read-only/live-review")
def alert_read_only_live_review(
    symbol: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
):
    if run_read_only_live_alert_review is None:
        return {
            "ok": False,
            "component": "ALERT_LIVE_DATA_ADAPTER_READ_ONLY",
            "reason": "LIVE_DATA_ADAPTER_IMPORT_FAILED",
            "import_error": _alert_live_import_error,
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
    return run_read_only_live_alert_review(
        symbol=symbol,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        timeout_seconds=30,
    )
# === ALERT LIVE DATA ADAPTER ENDPOINT END ===
# === ALERT LIVE READINESS AUDIT ENDPOINT START ===
try:
    from backend.alerts.live_readiness_audit import run_read_only_live_readiness_audit
except Exception as _live_readiness_audit_import_error:
    run_read_only_live_readiness_audit = None
    LIVE_READINESS_AUDIT_IMPORT_ERROR = str(_live_readiness_audit_import_error)
@router.get("/read-only/live-readiness-audit")
def alert_read_only_live_readiness_audit(
    symbol: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
):
    if run_read_only_live_readiness_audit is None:
        return {
            "ok": False,
            "component": "ALERT_LIVE_READINESS_AUDIT_READ_ONLY",
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
            "readiness_status": "LIVE_READINESS_AUDIT_IMPORT_BLOCKED_READ_ONLY",
            "import_error": LIVE_READINESS_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_live_readiness_audit(
        symbol=symbol,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
    )
# === ALERT LIVE READINESS AUDIT ENDPOINT END ===
# === ALERT LIVE READINESS BATCH AUDIT ENDPOINT START ===
try:
    from backend.alerts.live_readiness_batch_audit import run_read_only_live_readiness_batch_audit
except Exception as _live_readiness_batch_audit_import_error:
    run_read_only_live_readiness_batch_audit = None
    LIVE_READINESS_BATCH_AUDIT_IMPORT_ERROR = str(_live_readiness_batch_audit_import_error)
@router.get("/read-only/live-readiness-batch-audit")
def alert_read_only_live_readiness_batch_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_live_readiness_batch_audit is None:
        return {
            "ok": False,
            "component": "ALERT_LIVE_READINESS_BATCH_AUDIT_READ_ONLY",
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
            "batch_readiness_status": "LIVE_READINESS_BATCH_IMPORT_BLOCKED_READ_ONLY",
            "import_error": LIVE_READINESS_BATCH_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_live_readiness_batch_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT LIVE READINESS BATCH AUDIT ENDPOINT END ===
# === ALERT SOURCE GAP AUDIT ENDPOINT START ===
try:
    from backend.alerts.source_gap_audit import run_read_only_alert_source_gap_audit
except Exception as _alert_source_gap_audit_import_error:
    run_read_only_alert_source_gap_audit = None
    ALERT_SOURCE_GAP_AUDIT_IMPORT_ERROR = str(_alert_source_gap_audit_import_error)
@router.get("/read-only/source-gap-audit")
def alert_read_only_source_gap_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_source_gap_audit is None:
        return {
            "ok": False,
            "component": "ALERT_SOURCE_GAP_AUDIT_READ_ONLY",
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
            "source_gap_status": "ALERT_SOURCE_GAP_AUDIT_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_SOURCE_GAP_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_source_gap_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT SOURCE GAP AUDIT ENDPOINT END ===
# === ALERT SOURCE GAP REMEDIATION AUDIT ENDPOINT START ===
try:
    from backend.alerts.source_gap_remediation_audit import run_read_only_alert_source_gap_remediation_audit
except Exception as _alert_source_gap_remediation_audit_import_error:
    run_read_only_alert_source_gap_remediation_audit = None
    ALERT_SOURCE_GAP_REMEDIATION_AUDIT_IMPORT_ERROR = str(_alert_source_gap_remediation_audit_import_error)
@router.get("/read-only/source-gap-remediation-audit")
def alert_read_only_source_gap_remediation_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_source_gap_remediation_audit is None:
        return {
            "ok": False,
            "component": "ALERT_SOURCE_GAP_REMEDIATION_AUDIT_READ_ONLY",
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
            "remediation_status": "ALERT_SOURCE_GAP_REMEDIATION_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_SOURCE_GAP_REMEDIATION_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_source_gap_remediation_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT SOURCE GAP REMEDIATION AUDIT ENDPOINT END ===
# === ALERT SOURCE GAP DASHBOARD AUDIT ENDPOINT START ===
try:
    from backend.alerts.source_gap_dashboard_audit import run_read_only_alert_source_gap_dashboard_audit
except Exception as _alert_source_gap_dashboard_audit_import_error:
    run_read_only_alert_source_gap_dashboard_audit = None
    ALERT_SOURCE_GAP_DASHBOARD_AUDIT_IMPORT_ERROR = str(_alert_source_gap_dashboard_audit_import_error)
@router.get("/read-only/source-gap-dashboard-audit")
def alert_read_only_source_gap_dashboard_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_source_gap_dashboard_audit is None:
        return {
            "ok": False,
            "component": "ALERT_SOURCE_GAP_DASHBOARD_AUDIT_READ_ONLY",
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
            "dashboard_status": "ALERT_SOURCE_GAP_DASHBOARD_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_SOURCE_GAP_DASHBOARD_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_source_gap_dashboard_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT SOURCE GAP DASHBOARD AUDIT ENDPOINT END ===
# === ALERT CONSOLE SNAPSHOT AUDIT ENDPOINT START ===
try:
    from backend.alerts.alert_console_snapshot_audit import run_read_only_alert_console_snapshot_audit
except Exception as _alert_console_snapshot_audit_import_error:
    run_read_only_alert_console_snapshot_audit = None
    ALERT_CONSOLE_SNAPSHOT_AUDIT_IMPORT_ERROR = str(_alert_console_snapshot_audit_import_error)
@router.get("/read-only/console-snapshot-audit")
def alert_read_only_console_snapshot_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_console_snapshot_audit is None:
        return {
            "ok": False,
            "component": "ALERT_CONSOLE_SNAPSHOT_AUDIT_READ_ONLY",
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
            "console_snapshot_status": "ALERT_CONSOLE_SNAPSHOT_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_CONSOLE_SNAPSHOT_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_console_snapshot_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT CONSOLE SNAPSHOT AUDIT ENDPOINT END ===
# === ALERT CONSOLE VIEW MODEL AUDIT ENDPOINT START ===
try:
    from backend.alerts.alert_console_view_model_audit import run_read_only_alert_console_view_model_audit
except Exception as _alert_console_view_model_audit_import_error:
    run_read_only_alert_console_view_model_audit = None
    ALERT_CONSOLE_VIEW_MODEL_AUDIT_IMPORT_ERROR = str(_alert_console_view_model_audit_import_error)
@router.get("/read-only/console-view-model-audit")
def alert_read_only_console_view_model_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_console_view_model_audit is None:
        return {
            "ok": False,
            "component": "ALERT_CONSOLE_VIEW_MODEL_AUDIT_READ_ONLY",
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
            "view_model_status": "ALERT_CONSOLE_VIEW_MODEL_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_CONSOLE_VIEW_MODEL_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_console_view_model_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT CONSOLE VIEW MODEL AUDIT ENDPOINT END ===
# === ALERT CONSOLE FRONTEND CONTRACT AUDIT ENDPOINT START ===
try:
    from backend.alerts.alert_console_frontend_contract_audit import run_read_only_alert_console_frontend_contract_audit
except Exception as _alert_console_frontend_contract_audit_import_error:
    run_read_only_alert_console_frontend_contract_audit = None
    ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_IMPORT_ERROR = str(_alert_console_frontend_contract_audit_import_error)
@router.get("/read-only/console-frontend-contract-audit")
def alert_read_only_console_frontend_contract_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_alert_console_frontend_contract_audit is None:
        return {
            "ok": False,
            "component": "ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_READ_ONLY",
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
            "frontend_contract_status": "ALERT_CONSOLE_FRONTEND_CONTRACT_IMPORT_BLOCKED_READ_ONLY",
            "import_error": ALERT_CONSOLE_FRONTEND_CONTRACT_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_alert_console_frontend_contract_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === ALERT CONSOLE FRONTEND CONTRACT AUDIT ENDPOINT END ===
# === SOURCE COVERAGE COMPLETION AUDIT ENDPOINT START ===
try:
    from backend.alerts.source_coverage_completion_audit import run_read_only_source_coverage_completion_audit
except Exception as _source_coverage_completion_audit_import_error:
    run_read_only_source_coverage_completion_audit = None
    SOURCE_COVERAGE_COMPLETION_AUDIT_IMPORT_ERROR = str(_source_coverage_completion_audit_import_error)
@router.get("/read-only/source-coverage-completion-audit")
def alert_read_only_source_coverage_completion_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_source_coverage_completion_audit is None:
        return {
            "ok": False,
            "component": "SOURCE_COVERAGE_COMPLETION_AUDIT_READ_ONLY",
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
            "source_coverage_completion_status": "SOURCE_COVERAGE_COMPLETION_IMPORT_BLOCKED_READ_ONLY",
            "import_error": SOURCE_COVERAGE_COMPLETION_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_source_coverage_completion_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === SOURCE COVERAGE COMPLETION AUDIT ENDPOINT END ===
# === EVIDENCE PAYLOAD COMPLETENESS AUDIT ENDPOINT START ===
try:
    from backend.alerts.evidence_payload_completeness_audit import run_read_only_evidence_payload_completeness_audit
except Exception as _evidence_payload_completeness_audit_import_error:
    run_read_only_evidence_payload_completeness_audit = None
    EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_IMPORT_ERROR = str(_evidence_payload_completeness_audit_import_error)
@router.get("/read-only/evidence-payload-completeness-audit")
def alert_read_only_evidence_payload_completeness_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_evidence_payload_completeness_audit is None:
        return {
            "ok": False,
            "component": "EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_READ_ONLY",
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
            "evidence_payload_completeness_status": "EVIDENCE_PAYLOAD_COMPLETENESS_IMPORT_BLOCKED_READ_ONLY",
            "import_error": EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_evidence_payload_completeness_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === EVIDENCE PAYLOAD COMPLETENESS AUDIT ENDPOINT END ===
# === OPERATOR CONTROL EVIDENCE AUDIT ENDPOINT START ===
try:
    from backend.alerts.operator_control_evidence_audit import run_read_only_operator_control_evidence_audit
except Exception as _operator_control_evidence_audit_import_error:
    run_read_only_operator_control_evidence_audit = None
    OPERATOR_CONTROL_EVIDENCE_AUDIT_IMPORT_ERROR = str(_operator_control_evidence_audit_import_error)
@router.get("/read-only/operator-control-evidence-audit")
def alert_read_only_operator_control_evidence_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_operator_control_evidence_audit is None:
        return {
            "ok": False,
            "component": "OPERATOR_CONTROL_EVIDENCE_AUDIT_READ_ONLY",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "operator_control_evidence_audit_status": "OPERATOR_CONTROL_EVIDENCE_IMPORT_BLOCKED_READ_ONLY",
            "import_error": OPERATOR_CONTROL_EVIDENCE_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_operator_control_evidence_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === OPERATOR CONTROL EVIDENCE AUDIT ENDPOINT END ===
# === D3D DRY-RUN GATE AUDIT ENDPOINT START ===
try:
    from backend.alerts.d3d_dry_run_gate_audit import run_read_only_d3d_dry_run_gate_audit
except Exception as _d3d_dry_run_gate_audit_import_error:
    run_read_only_d3d_dry_run_gate_audit = None
    D3D_DRY_RUN_GATE_AUDIT_IMPORT_ERROR = str(_d3d_dry_run_gate_audit_import_error)
@router.get("/read-only/d3d-dry-run-gate-audit")
def alert_read_only_d3d_dry_run_gate_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_d3d_dry_run_gate_audit is None:
        return {
            "ok": False,
            "component": "D3D_DRY_RUN_GATE_AUDIT_READ_ONLY",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "d3d_execution_authorized": False,
            "d3d_dry_run_gate_audit_status": "D3D_DRY_RUN_GATE_IMPORT_BLOCKED_READ_ONLY",
            "import_error": D3D_DRY_RUN_GATE_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_d3d_dry_run_gate_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === D3D DRY-RUN GATE AUDIT ENDPOINT END ===
# === CONTROLLED PERSISTENCE CONTRACT AUDIT ENDPOINT START ===
try:
    from backend.alerts.controlled_persistence_contract_audit import run_read_only_controlled_persistence_contract_audit
except Exception as _controlled_persistence_contract_audit_import_error:
    run_read_only_controlled_persistence_contract_audit = None
    CONTROLLED_PERSISTENCE_CONTRACT_AUDIT_IMPORT_ERROR = str(_controlled_persistence_contract_audit_import_error)
@router.get("/read-only/controlled-persistence-contract-audit")
def alert_read_only_controlled_persistence_contract_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_controlled_persistence_contract_audit is None:
        return {
            "ok": False,
            "component": "CONTROLLED_PERSISTENCE_CONTRACT_AUDIT_READ_ONLY",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "d3d_execution_authorized": False,
            "persistence_write_authorized": False,
            "supabase_write_authorized": False,
            "campaign_mutation_authorized": False,
            "controlled_persistence_contract_audit_status": "CONTROLLED_PERSISTENCE_CONTRACT_IMPORT_BLOCKED_READ_ONLY",
            "import_error": CONTROLLED_PERSISTENCE_CONTRACT_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_controlled_persistence_contract_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === CONTROLLED PERSISTENCE CONTRACT AUDIT ENDPOINT END ===
# === CONTROLLED PERSISTENCE ACTIVATION READINESS AUDIT ENDPOINT START ===
try:
    from backend.alerts.controlled_persistence_activation_readiness_audit import run_read_only_controlled_persistence_activation_readiness_audit
except Exception as _controlled_persistence_activation_readiness_audit_import_error:
    run_read_only_controlled_persistence_activation_readiness_audit = None
    CONTROLLED_PERSISTENCE_ACTIVATION_READINESS_AUDIT_IMPORT_ERROR = str(_controlled_persistence_activation_readiness_audit_import_error)
@router.get("/read-only/controlled-persistence-activation-readiness-audit")
def alert_read_only_controlled_persistence_activation_readiness_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_controlled_persistence_activation_readiness_audit is None:
        return {
            "ok": False,
            "component": "CONTROLLED_PERSISTENCE_ACTIVATION_READINESS_AUDIT_READ_ONLY",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "d3d_execution_authorized": False,
            "persistence_write_authorized": False,
            "supabase_write_authorized": False,
            "campaign_mutation_authorized": False,
            "persistence_activation_authorized": False,
            "production_activation_authorized": False,
            "controlled_persistence_activation_readiness_audit_status": "CONTROLLED_PERSISTENCE_ACTIVATION_READINESS_IMPORT_BLOCKED_READ_ONLY",
            "import_error": CONTROLLED_PERSISTENCE_ACTIVATION_READINESS_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_controlled_persistence_activation_readiness_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === CONTROLLED PERSISTENCE ACTIVATION READINESS AUDIT ENDPOINT END ===
# === PERSISTENCE WRITE PERMISSION MANIFEST AUDIT ENDPOINT START ===
try:
    from backend.alerts.persistence_write_permission_manifest_audit import run_read_only_persistence_write_permission_manifest_audit
except Exception as _persistence_write_permission_manifest_audit_import_error:
    run_read_only_persistence_write_permission_manifest_audit = None
    PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_IMPORT_ERROR = str(_persistence_write_permission_manifest_audit_import_error)
@router.get("/read-only/persistence-write-permission-manifest-audit")
def alert_read_only_persistence_write_permission_manifest_audit(
    symbols: str = "SPY,QQQ,IWM",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
):
    if run_read_only_persistence_write_permission_manifest_audit is None:
        return {
            "ok": False,
            "component": "PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_READ_ONLY",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "can_execute_d3d": False,
            "d3d_execution_authorized": False,
            "persistence_write_authorized": False,
            "supabase_write_authorized": False,
            "campaign_mutation_authorized": False,
            "persistence_activation_authorized": False,
            "production_activation_authorized": False,
            "write_permission_manifest_authorized": False,
            "write_permission_manifest_audit_status": "WRITE_PERMISSION_MANIFEST_IMPORT_BLOCKED_READ_ONLY",
            "import_error": PERSISTENCE_WRITE_PERMISSION_MANIFEST_AUDIT_IMPORT_ERROR,
        }
    return run_read_only_persistence_write_permission_manifest_audit(
        symbols=symbols,
        requested_timeframe=timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
# === PERSISTENCE WRITE PERMISSION MANIFEST AUDIT ENDPOINT END ===
