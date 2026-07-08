from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_status_center_ui_mount_audit import (
    run_read_only_controlled_persistence_status_center_ui_mount_audit,
)
# === STEP 8E READ-ONLY FRONTEND PANEL FILE-LOCATION IMPORT BRIDGE START ===
# File-location import bridge only.
# Required because frontend/status_center.py and frontend/status_center/ collide under package import.
# This bridge loads the read-only panel model by absolute file path.
# It does not write to Supabase.
# It does not mutate campaigns.
# It does not execute or authorize D3D.
# It does not confirm operator control.
# It does not create a trade signal.

from importlib import util as _status_center_panel_importlib_util
from pathlib import Path as _status_center_panel_Path

_STATUS_CENTER_PANEL_PATH = (
    _status_center_panel_Path(__file__).resolve().parents[2]
    / "frontend"
    / "status_center"
    / "controlled_persistence_status_center_panel.py"
)

_STATUS_CENTER_PANEL_SPEC = _status_center_panel_importlib_util.spec_from_file_location(
    "sigmalytic_controlled_persistence_status_center_panel_read_only",
    _STATUS_CENTER_PANEL_PATH,
)

if _STATUS_CENTER_PANEL_SPEC is None or _STATUS_CENTER_PANEL_SPEC.loader is None:
    raise ImportError(
        f"Unable to load read-only Status Center panel from {_STATUS_CENTER_PANEL_PATH}"
    )

_STATUS_CENTER_PANEL_MODULE = _status_center_panel_importlib_util.module_from_spec(
    _STATUS_CENTER_PANEL_SPEC
)
_STATUS_CENTER_PANEL_SPEC.loader.exec_module(_STATUS_CENTER_PANEL_MODULE)

ALLOWED_UI_ACTIONS = getattr(_STATUS_CENTER_PANEL_MODULE, "ALLOWED_UI_ACTIONS")
DISPLAY_SECTIONS = getattr(_STATUS_CENTER_PANEL_MODULE, "DISPLAY_SECTIONS")
DOCTRINE_STATEMENT = getattr(_STATUS_CENTER_PANEL_MODULE, "DOCTRINE_STATEMENT")
PROHIBITED_UI_ACTIONS = getattr(_STATUS_CENTER_PANEL_MODULE, "PROHIBITED_UI_ACTIONS")
READ_ONLY_STATUS_BADGES = getattr(_STATUS_CENTER_PANEL_MODULE, "READ_ONLY_STATUS_BADGES")
STATUS_CENTER_MOUNT_ID = getattr(_STATUS_CENTER_PANEL_MODULE, "STATUS_CENTER_MOUNT_ID")
STATUS_CENTER_PANEL_TITLE = getattr(_STATUS_CENTER_PANEL_MODULE, "STATUS_CENTER_PANEL_TITLE")
STATUS_CENTER_SOURCE_ENDPOINT = getattr(_STATUS_CENTER_PANEL_MODULE, "STATUS_CENTER_SOURCE_ENDPOINT")
build_controlled_persistence_status_center_panel_model = getattr(_STATUS_CENTER_PANEL_MODULE, "build_controlled_persistence_status_center_panel_model")
read_only_status_center_mount_descriptor = getattr(_STATUS_CENTER_PANEL_MODULE, "read_only_status_center_mount_descriptor")

# === STEP 8E READ-ONLY FRONTEND PANEL FILE-LOCATION IMPORT BRIDGE END ===
COMPONENT = "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_status_center_ui_implementation_wiring_audit_read_only_v1"
GUARDRAILS: Dict[str, Any] = {
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
    "simulated_write_only": True,
    "actual_write_performed": False,
    "schema_existence_audit_authorized": False,
    "schema_write_authorized": False,
    "append_only_write_preflight_authorized": False,
    "append_only_write_preflight_gate_clear": False,
    "append_only_write_execution_allowed": False,
    "approval_packet_authorized": False,
    "approval_packet_write_authorized": False,
    "decision_console_authorized": False,
    "decision_console_execution_allowed": False,
    "frontend_contract_authorized": False,
    "frontend_mutation_authorized": False,
    "frontend_execution_allowed": False,
    "status_center_ui_mount_authorized": False,
    "status_center_ui_mutation_authorized": False,
    "status_center_ui_execution_allowed": False,
    "status_center_ui_implementation_authorized": False,
    "status_center_ui_implementation_execution_allowed": False,
    "status_center_panel_mutation_authorized": False,
    "status_center_panel_runtime_activation_authorized": False,
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
def _validate_panel_model(panel_model: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if panel_model.get("status_center_mount_id") != STATUS_CENTER_MOUNT_ID:
        failures.append("STATUS_CENTER_MOUNT_ID_MISMATCH")
    if panel_model.get("status_center_source_endpoint") != STATUS_CENTER_SOURCE_ENDPOINT:
        failures.append("STATUS_CENTER_SOURCE_ENDPOINT_MISMATCH")
    if panel_model.get("read_only") is not True:
        failures.append("PANEL_NOT_READ_ONLY")
    if panel_model.get("writes_to_supabase") is not False:
        failures.append("PANEL_WRITES_TO_SUPABASE_DRIFT")
    if panel_model.get("mutates_campaigns") is not False:
        failures.append("PANEL_MUTATES_CAMPAIGNS_DRIFT")
    if panel_model.get("operator_control_confirmed") is not False:
        failures.append("PANEL_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if panel_model.get("composite_operator_control_confirmed") is not False:
        failures.append("PANEL_COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if panel_model.get("d3d_execution_authorized") is not False:
        failures.append("PANEL_D3D_AUTHORIZATION_DRIFT")
    if panel_model.get("not_a_trade_signal") is not True:
        failures.append("PANEL_TRADE_SIGNAL_DRIFT")
    if panel_model.get("actual_write_performed") is not False:
        failures.append("PANEL_ACTUAL_WRITE_DRIFT")
    if panel_model.get("has_write_button") is not False:
        failures.append("PANEL_WRITE_BUTTON_PRESENT_DRIFT")
    if panel_model.get("has_execute_button") is not False:
        failures.append("PANEL_EXECUTE_BUTTON_PRESENT_DRIFT")
    if panel_model.get("has_hidden_mutation_handler") is not False:
        failures.append("PANEL_HIDDEN_MUTATION_HANDLER_PRESENT_DRIFT")
    if panel_model.get("has_status_center_write_side_effect") is not False:
        failures.append("PANEL_STATUS_CENTER_WRITE_SIDE_EFFECT_PRESENT_DRIFT")
    if "no_write_button" not in _as_list(panel_model.get("prohibited_ui_actions")):
        failures.append("PANEL_MISSING_NO_WRITE_BUTTON_PROHIBITION")
    if "no_hidden_mutation_handler" not in _as_list(panel_model.get("prohibited_ui_actions")):
        failures.append("PANEL_MISSING_NO_HIDDEN_MUTATION_HANDLER_PROHIBITION")
    if "no_status_center_write_side_effect" not in _as_list(panel_model.get("prohibited_ui_actions")):
        failures.append("PANEL_MISSING_NO_STATUS_CENTER_WRITE_SIDE_EFFECT_PROHIBITION")
    if "VIEW_ONLY" not in _as_list(panel_model.get("allowed_ui_actions")):
        failures.append("PANEL_MISSING_VIEW_ONLY_ACTION")
    if "COPY_REVIEW_PACKET" not in _as_list(panel_model.get("allowed_ui_actions")):
        failures.append("PANEL_MISSING_COPY_REVIEW_PACKET_ACTION")
    if "REFRESH_READ_ONLY" not in _as_list(panel_model.get("allowed_ui_actions")):
        failures.append("PANEL_MISSING_REFRESH_READ_ONLY_ACTION")
    if "Operator control is evidence, not a score" not in str(panel_model.get("doctrine_statement") or ""):
        failures.append("PANEL_DOCTRINE_STATEMENT_MISSING")
    return failures
def build_read_only_controlled_persistence_status_center_ui_implementation_wiring_from_mount(
    *,
    mount_payload: Dict[str, Any],
) -> Dict[str, Any]:
    mount_descriptor = read_only_status_center_mount_descriptor()
    panel_model = build_controlled_persistence_status_center_panel_model(
        mount_payload=mount_payload,
    )
    panel_failures = _validate_panel_model(panel_model)
    guardrail_failure_count = _as_int(mount_payload.get("guardrail_failure_count"))
    mount_status = str(mount_payload.get("controlled_persistence_status_center_ui_mount_audit_status") or "")
    mount_ready = mount_status in {
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_READY_READ_ONLY",
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_MOUNT_BLOCKED_READ_ONLY",
    }
    implementation_ready = (
        mount_ready
        and guardrail_failure_count == 0
        and not panel_failures
        and bool(panel_model.get("decision_rows"))
    )
    implementation_status = (
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_READY_READ_ONLY"
        if implementation_ready
        else "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_BLOCKED_READ_ONLY"
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
        "simulated_write_only": True,
        "actual_write_performed": False,
        "schema_existence_audit_authorized": False,
        "schema_write_authorized": False,
        "append_only_write_preflight_authorized": False,
        "append_only_write_preflight_gate_clear": False,
        "append_only_write_execution_allowed": False,
        "approval_packet_authorized": False,
        "approval_packet_write_authorized": False,
        "decision_console_authorized": False,
        "decision_console_execution_allowed": False,
        "frontend_contract_authorized": False,
        "frontend_mutation_authorized": False,
        "frontend_execution_allowed": False,
        "status_center_ui_mount_authorized": False,
        "status_center_ui_mutation_authorized": False,
        "status_center_ui_execution_allowed": False,
        "status_center_ui_implementation_authorized": False,
        "status_center_ui_implementation_execution_allowed": False,
        "status_center_panel_mutation_authorized": False,
        "status_center_panel_runtime_activation_authorized": False,
        "controlled_persistence_status_center_ui_implementation_wiring_audit_status": implementation_status,
        "controlled_persistence_status_center_ui_mount_audit_status": mount_payload.get("controlled_persistence_status_center_ui_mount_audit_status"),
        "controlled_persistence_decision_console_frontend_contract_audit_status": mount_payload.get("controlled_persistence_decision_console_frontend_contract_audit_status"),
        "controlled_persistence_decision_console_audit_status": mount_payload.get("controlled_persistence_decision_console_audit_status"),
        "controlled_append_only_write_approval_packet_audit_status": mount_payload.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": mount_payload.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": mount_payload.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": mount_payload.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": mount_payload.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": mount_payload.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": mount_payload.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": mount_payload.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": mount_payload.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": mount_payload.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": mount_payload.get("source_coverage_completion_status"),
        "status_center_mount_id": STATUS_CENTER_MOUNT_ID,
        "status_center_panel_title": STATUS_CENTER_PANEL_TITLE,
        "status_center_source_endpoint": STATUS_CENTER_SOURCE_ENDPOINT,
        "status_center_mount_descriptor": mount_descriptor,
        "status_center_panel_model": panel_model,
        "display_sections": list(DISPLAY_SECTIONS),
        "read_only_status_badges": list(READ_ONLY_STATUS_BADGES),
        "allowed_ui_actions": list(ALLOWED_UI_ACTIONS),
        "prohibited_ui_actions": list(PROHIBITED_UI_ACTIONS),
        "panel_validation_failure_count": len(panel_failures),
        "panel_validation_failures": panel_failures,
        "panel_row_count": _as_int(panel_model.get("panel_row_count")),
        "panel_chain_card_count": _as_int(panel_model.get("panel_chain_card_count")),
        "blocked_symbols": list(panel_model.get("blocked_symbols") or []),
        "reviewable_symbols": list(panel_model.get("reviewable_symbols") or []),
        "target_table": mount_payload.get("target_table"),
        "proposed_columns": list(mount_payload.get("proposed_columns") or []),
        "missing_proposed_columns": list(mount_payload.get("missing_proposed_columns") or []),
        "table_exists": mount_payload.get("table_exists") is True,
        "all_proposed_columns_exist": mount_payload.get("all_proposed_columns_exist") is True,
        "schema_probe_status": mount_payload.get("schema_probe_status"),
        "schema_probe_method": mount_payload.get("schema_probe_method"),
        "schema_probe_is_read_only": mount_payload.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(mount_payload.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_status_center_ui_implementation_wiring_applies_no_changes": True,
        "controlled_persistence_status_center_ui_implementation_wiring_is_read_only": True,
        "controlled_persistence_status_center_ui_implementation_wiring_never_writes": True,
        "controlled_persistence_status_center_ui_implementation_wiring_never_authorizes": True,
        "controlled_persistence_status_center_ui_implementation_wiring_has_no_write_button": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_status_center_ui_implementation_wiring_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    mount_payload = run_read_only_controlled_persistence_status_center_ui_mount_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_status_center_ui_implementation_wiring_from_mount(
        mount_payload=mount_payload,
    )
