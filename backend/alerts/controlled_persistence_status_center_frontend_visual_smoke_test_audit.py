from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_status_center_ui_implementation_wiring_audit import (
    run_read_only_controlled_persistence_status_center_ui_implementation_wiring_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_AUDIT_READ_ONLY"
VERSION = "controlled_persistence_status_center_frontend_visual_smoke_test_audit_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
VISUAL_SMOKE_TEST_SCHEMA_VERSION = "controlled_persistence_status_center_frontend_visual_smoke_test_v1"
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
    "visual_smoke_test_authorized": False,
    "visual_smoke_test_execution_allowed": False,
    "visual_smoke_test_mutation_authorized": False,
}
REQUIRED_RENDER_SECTIONS = [
    "summary_panel",
    "read_only_status_badges",
    "audit_chain_cards",
    "symbol_decision_table",
    "blocker_list",
    "target_table_panel",
    "schema_probe_panel",
    "doctrine_panel",
    "absolute_prohibition_panel",
    "human_approval_required_banner",
]
REQUIRED_READ_ONLY_ACTIONS = [
    "VIEW_ONLY",
    "COPY_REVIEW_PACKET",
    "REFRESH_READ_ONLY",
]
REQUIRED_PROHIBITED_ACTIONS = [
    "no_write_button",
    "no_execute_button",
    "no_confirm_operator_control_button",
    "no_confirm_composite_operator_control_button",
    "no_authorize_d3d_button",
    "no_trade_signal_button",
    "no_score_rank_state_probability_or_edge_change",
    "no_supabase_insert_update_upsert_delete_rpc",
    "no_campaign_table_mutation",
    "no_hidden_mutation_handler",
    "no_status_center_write_side_effect",
]
REQUIRED_STATUS_BADGES = [
    "READ_ONLY_UI_IMPLEMENTATION",
    "NO_DATABASE_WRITE",
    "NO_SUPABASE_INSERT",
    "NO_CAMPAIGN_MUTATION",
    "NO_OPERATOR_CONTROL_CONFIRMATION",
    "NO_D3D_AUTHORIZATION",
    "NO_TRADE_SIGNAL",
    "HUMAN_APPROVAL_REQUIRED_BEFORE_WRITE",
]
RENDER_COMPONENT_ALLOWLIST = [
    "StatusCenterControlledPersistenceReadOnlyRow",
    "StatusCenterControlledPersistenceReadOnlyAuditCard",
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
def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _panel_model(wiring_payload: Dict[str, Any]) -> Dict[str, Any]:
    panel = wiring_payload.get("status_center_panel_model")
    if isinstance(panel, dict):
        return panel
    return {}
def _check_list_contains(
    *,
    source: Any,
    required: List[str],
    prefix: str,
) -> List[str]:
    values = _as_list(source)
    failures: List[str] = []
    for item in required:
        if item not in values:
            failures.append(f"{prefix}_MISSING_{item}")
    return failures
def _row_visual_checks(row: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if row.get("read_only") is not True:
        failures.append("ROW_NOT_READ_ONLY")
    if row.get("writes_to_supabase") is not False:
        failures.append("ROW_WRITES_TO_SUPABASE_DRIFT")
    if row.get("mutates_campaigns") is not False:
        failures.append("ROW_MUTATES_CAMPAIGNS_DRIFT")
    if row.get("operator_control_confirmed") is not False:
        failures.append("ROW_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if row.get("composite_operator_control_confirmed") is not False:
        failures.append("ROW_COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if row.get("d3d_execution_authorized") is not False:
        failures.append("ROW_D3D_AUTHORIZATION_DRIFT")
    if row.get("not_a_trade_signal") is not True:
        failures.append("ROW_TRADE_SIGNAL_DRIFT")
    if row.get("can_execute_d3d") is not False:
        failures.append("ROW_CAN_EXECUTE_D3D_DRIFT")
    if row.get("actual_write_performed") is not False:
        failures.append("ROW_ACTUAL_WRITE_DRIFT")
    if row.get("has_write_button") is not False:
        failures.append("ROW_WRITE_BUTTON_PRESENT_DRIFT")
    if row.get("has_execute_button") is not False:
        failures.append("ROW_EXECUTE_BUTTON_PRESENT_DRIFT")
    if row.get("has_hidden_mutation_handler") is not False:
        failures.append("ROW_HIDDEN_MUTATION_HANDLER_PRESENT_DRIFT")
    if row.get("has_status_center_write_side_effect") is not False:
        failures.append("ROW_STATUS_CENTER_WRITE_SIDE_EFFECT_PRESENT_DRIFT")
    if row.get("render_component") not in RENDER_COMPONENT_ALLOWLIST:
        failures.append("ROW_RENDER_COMPONENT_NOT_ALLOWLISTED")
    failures.extend(
        _check_list_contains(
            source=row.get("allowed_ui_actions"),
            required=REQUIRED_READ_ONLY_ACTIONS,
            prefix="ROW_ALLOWED_UI_ACTION",
        )
    )
    failures.extend(
        _check_list_contains(
            source=row.get("prohibited_ui_actions"),
            required=REQUIRED_PROHIBITED_ACTIONS,
            prefix="ROW_PROHIBITED_UI_ACTION",
        )
    )
    if "Operator control is evidence, not a score" not in str(row.get("doctrine_statement") or ""):
        failures.append("ROW_DOCTRINE_STATEMENT_MISSING")
    return failures
def _card_visual_checks(card: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if card.get("read_only") is not True:
        failures.append("CARD_NOT_READ_ONLY")
    if card.get("writes_to_supabase") is not False:
        failures.append("CARD_WRITES_TO_SUPABASE_DRIFT")
    if card.get("mutates_campaigns") is not False:
        failures.append("CARD_MUTATES_CAMPAIGNS_DRIFT")
    if card.get("authorizes_d3d") is not False:
        failures.append("CARD_AUTHORIZES_D3D_DRIFT")
    if card.get("operator_control_confirmed") is not False:
        failures.append("CARD_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if card.get("composite_operator_control_confirmed") is not False:
        failures.append("CARD_COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if card.get("not_a_trade_signal") is not True:
        failures.append("CARD_TRADE_SIGNAL_DRIFT")
    if card.get("render_component") not in RENDER_COMPONENT_ALLOWLIST:
        failures.append("CARD_RENDER_COMPONENT_NOT_ALLOWLISTED")
    return failures
def _summary_visual_checks(summary: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if summary.get("read_only") is not True:
        failures.append("SUMMARY_NOT_READ_ONLY")
    if summary.get("writes_to_supabase") is not False:
        failures.append("SUMMARY_WRITES_TO_SUPABASE_DRIFT")
    if summary.get("mutates_campaigns") is not False:
        failures.append("SUMMARY_MUTATES_CAMPAIGNS_DRIFT")
    if summary.get("operator_control_confirmed") is not False:
        failures.append("SUMMARY_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if summary.get("composite_operator_control_confirmed") is not False:
        failures.append("SUMMARY_COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if summary.get("d3d_execution_authorized") is not False:
        failures.append("SUMMARY_D3D_AUTHORIZATION_DRIFT")
    if summary.get("not_a_trade_signal") is not True:
        failures.append("SUMMARY_TRADE_SIGNAL_DRIFT")
    if summary.get("explicit_human_approval_required_before_any_write") is not True:
        failures.append("SUMMARY_HUMAN_APPROVAL_REQUIREMENT_MISSING")
    failures.extend(
        _check_list_contains(
            source=summary.get("allowed_ui_actions"),
            required=REQUIRED_READ_ONLY_ACTIONS,
            prefix="SUMMARY_ALLOWED_UI_ACTION",
        )
    )
    failures.extend(
        _check_list_contains(
            source=summary.get("prohibited_ui_actions"),
            required=REQUIRED_PROHIBITED_ACTIONS,
            prefix="SUMMARY_PROHIBITED_UI_ACTION",
        )
    )
    return failures
def _build_visual_render_tree(panel: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "render_root": "StatusCenter",
        "mount_id": panel.get("status_center_mount_id"),
        "panel_title": panel.get("status_center_panel_title"),
        "source_endpoint": panel.get("status_center_source_endpoint"),
        "http_method": panel.get("status_center_http_method"),
        "render_mode": panel.get("status_center_render_mode"),
        "refresh_mode": panel.get("status_center_refresh_mode"),
        "sections": list(panel.get("display_sections") or []),
        "summary_panel_present": isinstance(panel.get("summary_panel"), dict),
        "chain_card_count": len(_as_list(panel.get("chain_cards"))),
        "decision_row_count": len(_as_list(panel.get("decision_rows"))),
        "blocked_symbol_count": len(_as_list(panel.get("blocked_symbols"))),
        "reviewable_symbol_count": len(_as_list(panel.get("reviewable_symbols"))),
        "allowed_ui_actions": list(panel.get("allowed_ui_actions") or []),
        "prohibited_ui_actions": list(panel.get("prohibited_ui_actions") or []),
        "read_only_status_badges": list(panel.get("read_only_status_badges") or []),
        "explicit_human_approval_required_before_any_write": True,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "not_a_trade_signal": True,
    }
def build_read_only_status_center_frontend_visual_smoke_test_from_wiring(
    *,
    wiring_payload: Dict[str, Any],
) -> Dict[str, Any]:
    panel = _panel_model(wiring_payload)
    summary = panel.get("summary_panel")
    if not isinstance(summary, dict):
        summary = {}
    rows = [
        row
        for row in _as_list(panel.get("decision_rows"))
        if isinstance(row, dict)
    ]
    cards = [
        card
        for card in _as_list(panel.get("chain_cards"))
        if isinstance(card, dict)
    ]
    visual_failures: List[str] = []
    if not panel:
        visual_failures.append("PANEL_MODEL_MISSING")
    if panel.get("component") != "CONTROLLED_PERSISTENCE_STATUS_CENTER_PANEL_READ_ONLY":
        visual_failures.append("PANEL_COMPONENT_MISMATCH")
    if panel.get("status_center_mount_id") != "alerts.controlledPersistenceDecisionConsole":
        visual_failures.append("PANEL_MOUNT_ID_MISMATCH")
    if panel.get("status_center_source_endpoint") != "/api/alerts/read-only/controlled-persistence-status-center-ui-mount-audit":
        visual_failures.append("PANEL_SOURCE_ENDPOINT_MISMATCH")
    if panel.get("status_center_http_method") != "GET":
        visual_failures.append("PANEL_HTTP_METHOD_MISMATCH")
    if panel.get("read_only") is not True:
        visual_failures.append("PANEL_NOT_READ_ONLY")
    if panel.get("writes_to_supabase") is not False:
        visual_failures.append("PANEL_WRITES_TO_SUPABASE_DRIFT")
    if panel.get("mutates_campaigns") is not False:
        visual_failures.append("PANEL_MUTATES_CAMPAIGNS_DRIFT")
    if panel.get("operator_control_confirmed") is not False:
        visual_failures.append("PANEL_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if panel.get("composite_operator_control_confirmed") is not False:
        visual_failures.append("PANEL_COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_DRIFT")
    if panel.get("d3d_execution_authorized") is not False:
        visual_failures.append("PANEL_D3D_AUTHORIZATION_DRIFT")
    if panel.get("not_a_trade_signal") is not True:
        visual_failures.append("PANEL_TRADE_SIGNAL_DRIFT")
    if panel.get("actual_write_performed") is not False:
        visual_failures.append("PANEL_ACTUAL_WRITE_DRIFT")
    if panel.get("has_write_button") is not False:
        visual_failures.append("PANEL_WRITE_BUTTON_PRESENT_DRIFT")
    if panel.get("has_execute_button") is not False:
        visual_failures.append("PANEL_EXECUTE_BUTTON_PRESENT_DRIFT")
    if panel.get("has_hidden_mutation_handler") is not False:
        visual_failures.append("PANEL_HIDDEN_MUTATION_HANDLER_PRESENT_DRIFT")
    if panel.get("has_status_center_write_side_effect") is not False:
        visual_failures.append("PANEL_STATUS_CENTER_WRITE_SIDE_EFFECT_PRESENT_DRIFT")
    if not rows:
        visual_failures.append("PANEL_DECISION_ROWS_MISSING")
    if not cards:
        visual_failures.append("PANEL_CHAIN_CARDS_MISSING")
    visual_failures.extend(
        _check_list_contains(
            source=panel.get("display_sections"),
            required=REQUIRED_RENDER_SECTIONS,
            prefix="PANEL_DISPLAY_SECTION",
        )
    )
    visual_failures.extend(
        _check_list_contains(
            source=panel.get("allowed_ui_actions"),
            required=REQUIRED_READ_ONLY_ACTIONS,
            prefix="PANEL_ALLOWED_UI_ACTION",
        )
    )
    visual_failures.extend(
        _check_list_contains(
            source=panel.get("prohibited_ui_actions"),
            required=REQUIRED_PROHIBITED_ACTIONS,
            prefix="PANEL_PROHIBITED_UI_ACTION",
        )
    )
    visual_failures.extend(
        _check_list_contains(
            source=panel.get("read_only_status_badges"),
            required=REQUIRED_STATUS_BADGES,
            prefix="PANEL_STATUS_BADGE",
        )
    )
    visual_failures.extend(_summary_visual_checks(summary))
    row_results: List[Dict[str, Any]] = []
    for row in rows:
        row_failures = _row_visual_checks(row)
        visual_failures.extend([f"{_symbol(row.get('symbol'))}:{failure}" for failure in row_failures])
        row_results.append(
            {
                "symbol": _symbol(row.get("symbol")),
                "render_component": row.get("render_component"),
                "visual_smoke_row_status": "ROW_VISUAL_SMOKE_PASS_READ_ONLY" if not row_failures else "ROW_VISUAL_SMOKE_BLOCKED_READ_ONLY",
                "visual_smoke_failures": row_failures,
                "allowed_ui_actions": list(row.get("allowed_ui_actions") or []),
                "prohibited_ui_actions": list(row.get("prohibited_ui_actions") or []),
                "has_write_button": False,
                "has_execute_button": False,
                "has_hidden_mutation_handler": False,
                "has_status_center_write_side_effect": False,
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "not_a_trade_signal": True,
                "actual_write_performed": False,
            }
        )
    card_results: List[Dict[str, Any]] = []
    for card in cards:
        card_failures = _card_visual_checks(card)
        visual_failures.extend([f"{str(card.get('name') or 'UNKNOWN_CARD')}:{failure}" for failure in card_failures])
        card_results.append(
            {
                "name": card.get("name"),
                "render_component": card.get("render_component"),
                "visual_smoke_card_status": "CARD_VISUAL_SMOKE_PASS_READ_ONLY" if not card_failures else "CARD_VISUAL_SMOKE_BLOCKED_READ_ONLY",
                "visual_smoke_failures": card_failures,
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "operator_control_confirmed": False,
                "composite_operator_control_confirmed": False,
                "d3d_execution_authorized": False,
                "not_a_trade_signal": True,
            }
        )
    wiring_status = str(wiring_payload.get("controlled_persistence_status_center_ui_implementation_wiring_audit_status") or "")
    wiring_ready = wiring_status in {
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_READY_READ_ONLY",
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_UI_IMPLEMENTATION_WIRING_BLOCKED_READ_ONLY",
    }
    guardrail_failure_count = _as_int(wiring_payload.get("guardrail_failure_count"))
    panel_validation_failure_count = _as_int(wiring_payload.get("panel_validation_failure_count"))
    visual_smoke_pass = (
        wiring_ready
        and guardrail_failure_count == 0
        and panel_validation_failure_count == 0
        and not visual_failures
    )
    visual_smoke_status = (
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_PASS_READ_ONLY"
        if visual_smoke_pass
        else "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_BLOCKED_READ_ONLY"
    )
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "visual_smoke_test_schema_version": VISUAL_SMOKE_TEST_SCHEMA_VERSION,
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
        "visual_smoke_test_authorized": False,
        "visual_smoke_test_execution_allowed": False,
        "visual_smoke_test_mutation_authorized": False,
        "controlled_persistence_status_center_frontend_visual_smoke_test_audit_status": visual_smoke_status,
        "controlled_persistence_status_center_ui_implementation_wiring_audit_status": wiring_payload.get("controlled_persistence_status_center_ui_implementation_wiring_audit_status"),
        "controlled_persistence_status_center_ui_mount_audit_status": wiring_payload.get("controlled_persistence_status_center_ui_mount_audit_status"),
        "controlled_persistence_decision_console_frontend_contract_audit_status": wiring_payload.get("controlled_persistence_decision_console_frontend_contract_audit_status"),
        "controlled_persistence_decision_console_audit_status": wiring_payload.get("controlled_persistence_decision_console_audit_status"),
        "controlled_append_only_write_approval_packet_audit_status": wiring_payload.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": wiring_payload.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": wiring_payload.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": wiring_payload.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": wiring_payload.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": wiring_payload.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": wiring_payload.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": wiring_payload.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": wiring_payload.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": wiring_payload.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": wiring_payload.get("source_coverage_completion_status"),
        "visual_smoke_pass": visual_smoke_pass,
        "visual_smoke_failure_count": len(visual_failures),
        "visual_smoke_failures": visual_failures,
        "visual_render_tree": _build_visual_render_tree(panel),
        "visual_smoke_row_results": row_results,
        "visual_smoke_card_results": card_results,
        "required_render_sections": list(REQUIRED_RENDER_SECTIONS),
        "required_read_only_actions": list(REQUIRED_READ_ONLY_ACTIONS),
        "required_prohibited_actions": list(REQUIRED_PROHIBITED_ACTIONS),
        "required_status_badges": list(REQUIRED_STATUS_BADGES),
        "render_component_allowlist": list(RENDER_COMPONENT_ALLOWLIST),
        "status_center_mount_id": panel.get("status_center_mount_id"),
        "status_center_panel_title": panel.get("status_center_panel_title"),
        "status_center_source_endpoint": panel.get("status_center_source_endpoint"),
        "status_center_http_method": panel.get("status_center_http_method"),
        "display_sections": list(panel.get("display_sections") or []),
        "allowed_ui_actions": list(panel.get("allowed_ui_actions") or []),
        "prohibited_ui_actions": list(panel.get("prohibited_ui_actions") or []),
        "read_only_status_badges": list(panel.get("read_only_status_badges") or []),
        "panel_row_count": _as_int(panel.get("panel_row_count")),
        "panel_chain_card_count": _as_int(panel.get("panel_chain_card_count")),
        "blocked_symbols": list(panel.get("blocked_symbols") or []),
        "reviewable_symbols": list(panel.get("reviewable_symbols") or []),
        "target_table": wiring_payload.get("target_table"),
        "proposed_columns": list(wiring_payload.get("proposed_columns") or []),
        "missing_proposed_columns": list(wiring_payload.get("missing_proposed_columns") or []),
        "table_exists": wiring_payload.get("table_exists") is True,
        "all_proposed_columns_exist": wiring_payload.get("all_proposed_columns_exist") is True,
        "schema_probe_status": wiring_payload.get("schema_probe_status"),
        "schema_probe_method": wiring_payload.get("schema_probe_method"),
        "schema_probe_is_read_only": wiring_payload.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(wiring_payload.get("guardrail_failures") or []),
        "panel_validation_failure_count": panel_validation_failure_count,
        "panel_validation_failures": list(wiring_payload.get("panel_validation_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_status_center_frontend_visual_smoke_test_applies_no_changes": True,
        "controlled_persistence_status_center_frontend_visual_smoke_test_is_read_only": True,
        "controlled_persistence_status_center_frontend_visual_smoke_test_never_writes": True,
        "controlled_persistence_status_center_frontend_visual_smoke_test_never_authorizes": True,
        "controlled_persistence_status_center_frontend_visual_smoke_test_has_no_write_button": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_status_center_frontend_visual_smoke_test_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    wiring_payload = run_read_only_controlled_persistence_status_center_ui_implementation_wiring_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_status_center_frontend_visual_smoke_test_from_wiring(
        wiring_payload=wiring_payload,
    )
