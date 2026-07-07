from __future__ import annotations
from typing import Any, Dict, List
from backend.alerts.controlled_persistence_status_center_frontend_visual_smoke_test_audit import (
    run_read_only_controlled_persistence_status_center_frontend_visual_smoke_test_audit,
)
COMPONENT = "CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_READ_ONLY"
VERSION = "controlled_persistence_end_to_end_no_drift_regression_sweep_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
REGRESSION_SWEEP_SCHEMA_VERSION = "controlled_persistence_end_to_end_no_drift_regression_sweep_v1"
EXPECTED_AUDIT_CHAIN = [
    "source_coverage_completion",
    "evidence_payload_completeness",
    "operator_control_evidence",
    "d3d_dry_run_gate",
    "controlled_persistence_contract",
    "controlled_persistence_activation_readiness",
    "persistence_write_permission_manifest",
    "persistence_payload_simulation",
    "supabase_target_table_schema_existence",
    "supabase_append_only_write_preflight_authorization_gate",
    "controlled_append_only_write_approval_packet",
    "controlled_persistence_decision_console",
    "controlled_persistence_decision_console_frontend_contract",
    "controlled_persistence_status_center_ui_mount",
    "controlled_persistence_status_center_ui_implementation_wiring",
    "controlled_persistence_status_center_frontend_visual_smoke_test",
    "controlled_persistence_end_to_end_no_drift_regression_sweep",
]
EXPECTED_ENDPOINT_CHAIN = [
    "/api/alerts/read-only/source-coverage-completion-audit",
    "/api/alerts/read-only/evidence-payload-completeness-audit",
    "/api/alerts/read-only/operator-control-evidence-audit",
    "/api/alerts/read-only/d3d-dry-run-gate-audit",
    "/api/alerts/read-only/controlled-persistence-contract-audit",
    "/api/alerts/read-only/controlled-persistence-activation-readiness-audit",
    "/api/alerts/read-only/persistence-write-permission-manifest-audit",
    "/api/alerts/read-only/persistence-payload-simulation-audit",
    "/api/alerts/read-only/supabase-target-table-schema-existence-audit",
    "/api/alerts/read-only/supabase-append-only-write-preflight-authorization-gate",
    "/api/alerts/read-only/controlled-append-only-write-approval-packet-audit",
    "/api/alerts/read-only/controlled-persistence-decision-console-audit",
    "/api/alerts/read-only/controlled-persistence-decision-console-frontend-contract-audit",
    "/api/alerts/read-only/controlled-persistence-status-center-ui-mount-audit",
    "/api/alerts/read-only/controlled-persistence-status-center-ui-implementation-wiring-audit",
    "/api/alerts/read-only/controlled-persistence-status-center-frontend-visual-smoke-test-audit",
    "/api/alerts/read-only/controlled-persistence-end-to-end-no-drift-regression-sweep",
]
REQUIRED_STATUS_FIELDS = [
    "controlled_persistence_status_center_frontend_visual_smoke_test_audit_status",
    "controlled_persistence_status_center_ui_implementation_wiring_audit_status",
    "controlled_persistence_status_center_ui_mount_audit_status",
    "controlled_persistence_decision_console_frontend_contract_audit_status",
    "controlled_persistence_decision_console_audit_status",
    "controlled_append_only_write_approval_packet_audit_status",
    "append_only_write_preflight_authorization_gate_status",
    "supabase_target_table_schema_existence_audit_status",
    "persistence_payload_simulation_audit_status",
    "write_permission_manifest_audit_status",
    "controlled_persistence_activation_readiness_audit_status",
    "controlled_persistence_contract_audit_status",
    "d3d_dry_run_gate_audit_status",
    "operator_control_evidence_audit_status",
    "evidence_payload_completeness_status",
    "source_coverage_completion_status",
]
FALSE_NO_DRIFT_FLAGS = [
    "writes_to_supabase",
    "mutates_campaigns",
    "executes_d3d",
    "authorizes_d3d",
    "operator_control_confirmed",
    "composite_operator_control_confirmed",
    "changes_scores",
    "changes_ranks",
    "changes_states",
    "changes_probabilities",
    "changes_edge",
    "can_execute_d3d",
    "d3d_execution_authorized",
    "persistence_write_authorized",
    "supabase_write_authorized",
    "campaign_mutation_authorized",
    "persistence_activation_authorized",
    "production_activation_authorized",
    "write_permission_manifest_authorized",
    "actual_write_performed",
    "schema_existence_audit_authorized",
    "schema_write_authorized",
    "append_only_write_preflight_authorized",
    "append_only_write_preflight_gate_clear",
    "append_only_write_execution_allowed",
    "approval_packet_authorized",
    "approval_packet_write_authorized",
    "decision_console_authorized",
    "decision_console_execution_allowed",
    "frontend_contract_authorized",
    "frontend_mutation_authorized",
    "frontend_execution_allowed",
    "status_center_ui_mount_authorized",
    "status_center_ui_mutation_authorized",
    "status_center_ui_execution_allowed",
    "status_center_ui_implementation_authorized",
    "status_center_ui_implementation_execution_allowed",
    "status_center_panel_mutation_authorized",
    "status_center_panel_runtime_activation_authorized",
    "visual_smoke_test_authorized",
    "visual_smoke_test_execution_allowed",
    "visual_smoke_test_mutation_authorized",
    "regression_sweep_authorized",
    "regression_sweep_execution_allowed",
    "regression_sweep_mutation_authorized",
    "has_write_button",
    "has_execute_button",
    "has_hidden_mutation_handler",
    "has_status_center_write_side_effect",
]
TRUE_NO_DRIFT_FLAGS = [
    "diagnostic_only",
    "read_only",
    "not_a_trade_signal",
    "simulated_write_only",
]
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
    "regression_sweep_authorized": False,
    "regression_sweep_execution_allowed": False,
    "regression_sweep_mutation_authorized": False,
    "has_write_button": False,
    "has_execute_button": False,
    "has_hidden_mutation_handler": False,
    "has_status_center_write_side_effect": False,
}
def _guardrails() -> Dict[str, Any]:
    payload = dict(GUARDRAILS)
    payload["component"] = COMPONENT
    payload["version"] = VERSION
    return payload
def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0
def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []
def _walk_payload(node: Any, path: str = "$") -> List[str]:
    failures: List[str] = []
    if isinstance(node, dict):
        for flag in FALSE_NO_DRIFT_FLAGS:
            if flag in node and node.get(flag) is not False:
                failures.append(f"{path}.{flag}_MUST_BE_FALSE")
        for flag in TRUE_NO_DRIFT_FLAGS:
            if flag in node and node.get(flag) is not True:
                failures.append(f"{path}.{flag}_MUST_BE_TRUE")
        if node.get("d3d_execution_recommendation") not in {None, "DO_NOT_EXECUTE_D3D"}:
            failures.append(f"{path}.d3d_execution_recommendation_MUST_BE_DO_NOT_EXECUTE_D3D")
        for key, value in node.items():
            failures.extend(_walk_payload(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            failures.extend(_walk_payload(item, f"{path}[{index}]"))
    return failures
def _required_top_level_flag_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for flag in FALSE_NO_DRIFT_FLAGS:
        if payload.get(flag) is not False:
            failures.append(f"TOP_LEVEL_{flag}_MUST_BE_FALSE")
    for flag in TRUE_NO_DRIFT_FLAGS:
        if payload.get(flag) is not True:
            failures.append(f"TOP_LEVEL_{flag}_MUST_BE_TRUE")
    if payload.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append("TOP_LEVEL_D3D_EXECUTION_RECOMMENDATION_MUST_BE_DO_NOT_EXECUTE_D3D")
    return failures
def _required_status_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for field in REQUIRED_STATUS_FIELDS:
        value = payload.get(field)
        if value is None or str(value).strip() == "":
            failures.append(f"STATUS_FIELD_MISSING_{field}")
    return failures
def _doctrine_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    statement = str(payload.get("doctrine_statement") or "")
    if "Operator control is evidence, not a score" not in statement:
        failures.append("DOCTRINE_MISSING_OPERATOR_CONTROL_EVIDENCE_NOT_SCORE")
    if "Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations" not in statement:
        failures.append("DOCTRINE_MISSING_FORBIDDEN_INFERENCE_RULE")
    if "Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure" not in statement:
        failures.append("DOCTRINE_MISSING_COMPOSITE_OPERATOR_CONTROL_DEFINITION")
    return failures
def build_read_only_controlled_persistence_end_to_end_no_drift_regression_sweep_from_visual_smoke(
    *,
    visual_smoke_payload: Dict[str, Any],
) -> Dict[str, Any]:
    failures: List[str] = []
    failures.extend(_required_top_level_flag_failures(visual_smoke_payload))
    failures.extend(_walk_payload(visual_smoke_payload))
    failures.extend(_required_status_failures(visual_smoke_payload))
    failures.extend(_doctrine_failures(visual_smoke_payload))
    if visual_smoke_payload.get("ok") is not True:
        failures.append("VISUAL_SMOKE_PAYLOAD_OK_NOT_TRUE")
    if visual_smoke_payload.get("component") != "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_AUDIT_READ_ONLY":
        failures.append("VISUAL_SMOKE_COMPONENT_MISMATCH")
    if visual_smoke_payload.get("visual_smoke_pass") is not True:
        failures.append("VISUAL_SMOKE_PASS_NOT_TRUE")
    if _as_int(visual_smoke_payload.get("visual_smoke_failure_count")) != 0:
        failures.append("VISUAL_SMOKE_FAILURE_COUNT_NOT_ZERO")
    if _as_int(visual_smoke_payload.get("guardrail_failure_count")) != 0:
        failures.append("GUARDRAIL_FAILURE_COUNT_NOT_ZERO")
    if _as_int(visual_smoke_payload.get("panel_validation_failure_count")) != 0:
        failures.append("PANEL_VALIDATION_FAILURE_COUNT_NOT_ZERO")
    if visual_smoke_payload.get("has_write_button") is not False:
        failures.append("WRITE_BUTTON_PRESENT")
    if visual_smoke_payload.get("has_execute_button") is not False:
        failures.append("EXECUTE_BUTTON_PRESENT")
    if visual_smoke_payload.get("has_hidden_mutation_handler") is not False:
        failures.append("HIDDEN_MUTATION_HANDLER_PRESENT")
    if visual_smoke_payload.get("has_status_center_write_side_effect") is not False:
        failures.append("STATUS_CENTER_WRITE_SIDE_EFFECT_PRESENT")
    allowed_visual_status = {
        "CONTROLLED_PERSISTENCE_STATUS_CENTER_FRONTEND_VISUAL_SMOKE_TEST_PASS_READ_ONLY",
    }
    if visual_smoke_payload.get("controlled_persistence_status_center_frontend_visual_smoke_test_audit_status") not in allowed_visual_status:
        failures.append("VISUAL_SMOKE_STATUS_NOT_PASS_READ_ONLY")
    chain_completion = [
        {
            "audit": name,
            "expected_endpoint": endpoint,
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
            "actual_write_performed": False,
        }
        for name, endpoint in zip(EXPECTED_AUDIT_CHAIN, EXPECTED_ENDPOINT_CHAIN)
    ]
    sweep_pass = len(failures) == 0
    sweep_status = (
        "CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_PASS_READ_ONLY"
        if sweep_pass
        else "CONTROLLED_PERSISTENCE_END_TO_END_NO_DRIFT_REGRESSION_SWEEP_BLOCKED_READ_ONLY"
    )
    return {
        "ok": True,
        "component": COMPONENT,
        "version": VERSION,
        "regression_sweep_schema_version": REGRESSION_SWEEP_SCHEMA_VERSION,
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
        "regression_sweep_authorized": False,
        "regression_sweep_execution_allowed": False,
        "regression_sweep_mutation_authorized": False,
        "has_write_button": False,
        "has_execute_button": False,
        "has_hidden_mutation_handler": False,
        "has_status_center_write_side_effect": False,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_status": sweep_status,
        "controlled_persistence_status_center_frontend_visual_smoke_test_audit_status": visual_smoke_payload.get("controlled_persistence_status_center_frontend_visual_smoke_test_audit_status"),
        "controlled_persistence_status_center_ui_implementation_wiring_audit_status": visual_smoke_payload.get("controlled_persistence_status_center_ui_implementation_wiring_audit_status"),
        "controlled_persistence_status_center_ui_mount_audit_status": visual_smoke_payload.get("controlled_persistence_status_center_ui_mount_audit_status"),
        "controlled_persistence_decision_console_frontend_contract_audit_status": visual_smoke_payload.get("controlled_persistence_decision_console_frontend_contract_audit_status"),
        "controlled_persistence_decision_console_audit_status": visual_smoke_payload.get("controlled_persistence_decision_console_audit_status"),
        "controlled_append_only_write_approval_packet_audit_status": visual_smoke_payload.get("controlled_append_only_write_approval_packet_audit_status"),
        "append_only_write_preflight_authorization_gate_status": visual_smoke_payload.get("append_only_write_preflight_authorization_gate_status"),
        "supabase_target_table_schema_existence_audit_status": visual_smoke_payload.get("supabase_target_table_schema_existence_audit_status"),
        "persistence_payload_simulation_audit_status": visual_smoke_payload.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": visual_smoke_payload.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": visual_smoke_payload.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": visual_smoke_payload.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": visual_smoke_payload.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": visual_smoke_payload.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": visual_smoke_payload.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": visual_smoke_payload.get("source_coverage_completion_status"),
        "sweep_pass": sweep_pass,
        "sweep_failure_count": len(failures),
        "sweep_failures": failures,
        "expected_audit_chain": list(EXPECTED_AUDIT_CHAIN),
        "expected_endpoint_chain": list(EXPECTED_ENDPOINT_CHAIN),
        "chain_completion": chain_completion,
        "visual_smoke_pass": visual_smoke_payload.get("visual_smoke_pass") is True,
        "visual_smoke_failure_count": _as_int(visual_smoke_payload.get("visual_smoke_failure_count")),
        "guardrail_failure_count": _as_int(visual_smoke_payload.get("guardrail_failure_count")),
        "panel_validation_failure_count": _as_int(visual_smoke_payload.get("panel_validation_failure_count")),
        "panel_row_count": _as_int(visual_smoke_payload.get("panel_row_count")),
        "panel_chain_card_count": _as_int(visual_smoke_payload.get("panel_chain_card_count")),
        "reviewable_symbols": list(visual_smoke_payload.get("reviewable_symbols") or []),
        "blocked_symbols": list(visual_smoke_payload.get("blocked_symbols") or []),
        "target_table": visual_smoke_payload.get("target_table"),
        "proposed_columns": list(visual_smoke_payload.get("proposed_columns") or []),
        "missing_proposed_columns": list(visual_smoke_payload.get("missing_proposed_columns") or []),
        "table_exists": visual_smoke_payload.get("table_exists") is True,
        "all_proposed_columns_exist": visual_smoke_payload.get("all_proposed_columns_exist") is True,
        "schema_probe_status": visual_smoke_payload.get("schema_probe_status"),
        "schema_probe_method": visual_smoke_payload.get("schema_probe_method"),
        "schema_probe_is_read_only": visual_smoke_payload.get("schema_probe_is_read_only") is True,
        "explicit_human_approval_required_before_any_write": True,
        "doctrine_statement": DOCTRINE_STATEMENT,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_applies_no_changes": True,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_is_read_only": True,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_never_writes": True,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_never_authorizes": True,
        "controlled_persistence_end_to_end_no_drift_regression_sweep_has_no_write_button": True,
        "guardrails": _guardrails(),
    }
def run_read_only_controlled_persistence_end_to_end_no_drift_regression_sweep(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    visual_smoke_payload = run_read_only_controlled_persistence_status_center_frontend_visual_smoke_test_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_controlled_persistence_end_to_end_no_drift_regression_sweep_from_visual_smoke(
        visual_smoke_payload=visual_smoke_payload,
    )
