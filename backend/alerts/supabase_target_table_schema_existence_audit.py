from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from backend.alerts.persistence_payload_simulation_audit import (
    run_read_only_persistence_payload_simulation_audit,
)
COMPONENT = "SUPABASE_TARGET_TABLE_SCHEMA_EXISTENCE_AUDIT_READ_ONLY"
VERSION = "supabase_target_table_schema_existence_audit_read_only_v1"
DOCTRINE_STATEMENT = "Operator control is evidence, not a score. Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, probability outputs, downstream price results, future returns, trade signals, or probability/edge calculations. Composite Operator Control equals tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure."
SCHEMA_PROBE_METHOD = "POSTGREST_GET_LIMIT_ZERO_READ_ONLY"
SCHEMA_PROBE_TIMEOUT_SECONDS = 8
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
def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()
def _text(value: Any) -> str:
    return str(value or "").strip()
def _target_table(simulation: Dict[str, Any]) -> str:
    proposed = simulation.get("proposed_supabase_target") or {}
    if isinstance(proposed, dict):
        return _text(proposed.get("target_table"))
    return ""
def _proposed_columns(simulation: Dict[str, Any]) -> List[str]:
    columns = []
    for item in _as_list(simulation.get("proposed_allowed_columns")):
        name = _text(item)
        if name and name not in columns:
            columns.append(name)
    return columns
def _supabase_credentials_status() -> Dict[str, Any]:
    supabase_url = _text(os.getenv("SUPABASE_URL"))
    service_key = _text(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    anon_key = _text(os.getenv("SUPABASE_ANON_KEY"))
    selected_key = service_key or anon_key
    selected_key_name = "SUPABASE_SERVICE_ROLE_KEY" if service_key else ("SUPABASE_ANON_KEY" if anon_key else "")
    return {
        "supabase_url_present": bool(supabase_url),
        "supabase_key_present": bool(selected_key),
        "supabase_key_source": selected_key_name,
        "supabase_url": supabase_url,
        "supabase_key": selected_key,
    }
def _read_only_schema_probe(
    *,
    target_table: str,
    proposed_columns: List[str],
) -> Dict[str, Any]:
    credentials = _supabase_credentials_status()
    base_payload: Dict[str, Any] = {
        "schema_probe_method": SCHEMA_PROBE_METHOD,
        "schema_probe_is_read_only": True,
        "schema_probe_attempted": False,
        "schema_probe_timeout_seconds": SCHEMA_PROBE_TIMEOUT_SECONDS,
        "target_table": target_table,
        "proposed_columns": list(proposed_columns),
        "table_exists": False,
        "all_proposed_columns_exist": False,
        "missing_proposed_columns": list(proposed_columns),
        "schema_probe_http_status": None,
        "schema_probe_status": "SUPABASE_SCHEMA_PROBE_NOT_ATTEMPTED_READ_ONLY",
        "schema_probe_error_excerpt": "",
        "supabase_url_present": bool(credentials["supabase_url_present"]),
        "supabase_key_present": bool(credentials["supabase_key_present"]),
        "supabase_key_source": credentials["supabase_key_source"],
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "actual_write_performed": False,
    }
    if not target_table:
        base_payload["schema_probe_status"] = "SUPABASE_TARGET_TABLE_NOT_DECLARED_READ_ONLY"
        return base_payload
    if not proposed_columns:
        base_payload["schema_probe_status"] = "SUPABASE_TARGET_COLUMNS_NOT_DECLARED_READ_ONLY"
        return base_payload
    if not credentials["supabase_url_present"] or not credentials["supabase_key_present"]:
        base_payload["schema_probe_status"] = "SUPABASE_SCHEMA_PROBE_ENV_MISSING_READ_ONLY"
        return base_payload
    supabase_url = str(credentials["supabase_url"]).rstrip("/")
    supabase_key = str(credentials["supabase_key"])
    encoded_table = urllib.parse.quote(target_table, safe="")
    encoded_select = urllib.parse.quote(",".join(proposed_columns), safe=",")
    probe_url = f"{supabase_url}/rest/v1/{encoded_table}?select={encoded_select}&limit=0"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
        "Prefer": "count=exact",
    }
    base_payload["schema_probe_attempted"] = True
    try:
        request = urllib.request.Request(
            probe_url,
            headers=headers,
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=SCHEMA_PROBE_TIMEOUT_SECONDS) as response:
            status_code = int(getattr(response, "status", 0) or 0)
            response.read()
        base_payload["schema_probe_http_status"] = status_code
        base_payload["table_exists"] = 200 <= status_code < 300
        base_payload["all_proposed_columns_exist"] = 200 <= status_code < 300
        base_payload["missing_proposed_columns"] = [] if 200 <= status_code < 300 else list(proposed_columns)
        base_payload["schema_probe_status"] = (
            "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_READ_ONLY"
            if 200 <= status_code < 300
            else "SUPABASE_TARGET_TABLE_SCHEMA_HTTP_BLOCKED_READ_ONLY"
        )
        return base_payload
    except urllib.error.HTTPError as exc:
        body_excerpt = ""
        try:
            raw_body = exc.read()
            body_excerpt = raw_body.decode("utf-8", errors="replace")[:700]
        except Exception:
            body_excerpt = ""
        status_code = int(getattr(exc, "code", 0) or 0)
        base_payload["schema_probe_http_status"] = status_code
        base_payload["schema_probe_error_excerpt"] = body_excerpt
        base_payload["schema_probe_status"] = (
            "SUPABASE_TARGET_TABLE_NOT_FOUND_READ_ONLY"
            if status_code == 404
            else "SUPABASE_TARGET_COLUMNS_OR_POLICY_BLOCKED_READ_ONLY"
        )
        return base_payload
    except Exception as exc:
        base_payload["schema_probe_status"] = "SUPABASE_SCHEMA_PROBE_EXCEPTION_BLOCKED_READ_ONLY"
        base_payload["schema_probe_error_excerpt"] = str(exc)[:700]
        return base_payload
def _schema_row(row: Dict[str, Any], schema_probe: Dict[str, Any], upstream: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _symbol(row.get("symbol"))
    payload_simulation_valid = row.get("persistence_payload_simulation_hypothetically_valid") is True
    table_exists = schema_probe.get("table_exists") is True
    columns_exist = schema_probe.get("all_proposed_columns_exist") is True
    guardrail_clear = _as_int(upstream.get("guardrail_failure_count")) == 0
    schema_blockers: List[str] = []
    if not payload_simulation_valid:
        schema_blockers.append("PERSISTENCE_PAYLOAD_SIMULATION_NOT_VALID_READ_ONLY")
    if not table_exists:
        schema_blockers.append("SUPABASE_TARGET_TABLE_NOT_CONFIRMED_READ_ONLY")
    if not columns_exist:
        schema_blockers.append("SUPABASE_TARGET_COLUMNS_NOT_CONFIRMED_READ_ONLY")
    if not guardrail_clear:
        schema_blockers.append("UPSTREAM_GUARDRAIL_FAILURE_PRESENT_READ_ONLY")
    if row.get("actual_write_performed") is not False:
        schema_blockers.append("ACTUAL_WRITE_NOT_ALLOWED_READ_ONLY")
    if row.get("persistence_write_authorized") is not False:
        schema_blockers.append("PERSISTENCE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("supabase_write_authorized") is not False:
        schema_blockers.append("SUPABASE_WRITE_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("campaign_mutation_authorized") is not False:
        schema_blockers.append("CAMPAIGN_MUTATION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    if row.get("operator_control_confirmed") is not False:
        schema_blockers.append("OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("composite_operator_control_confirmed") is not False:
        schema_blockers.append("COMPOSITE_OPERATOR_CONTROL_CONFIRMATION_NOT_ALLOWED_READ_ONLY")
    if row.get("d3d_execution_authorized") is not False:
        schema_blockers.append("D3D_EXECUTION_AUTHORIZATION_NOT_ALLOWED_READ_ONLY")
    schema_hypothetically_ready = (
        payload_simulation_valid
        and table_exists
        and columns_exist
        and guardrail_clear
        and not schema_blockers
    )
    schema_status = (
        "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY"
        if schema_hypothetically_ready
        else "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY"
    )
    if not schema_blockers:
        schema_blockers.append("NO_SCHEMA_BLOCKER_BUT_WRITES_STILL_NOT_AUTHORIZED_READ_ONLY")
    return {
        "symbol": symbol,
        "supabase_target_table_schema_existence_status": schema_status,
        "schema_existence_hypothetically_ready": schema_hypothetically_ready,
        "schema_existence_audit_authorized": False,
        "schema_write_authorized": False,
        "simulated_write_only": True,
        "actual_write_performed": False,
        "write_permission_manifest_authorized": False,
        "persistence_write_authorized": False,
        "supabase_write_authorized": False,
        "campaign_mutation_authorized": False,
        "persistence_activation_authorized": False,
        "production_activation_authorized": False,
        "operator_control_confirmed": False,
        "composite_operator_control_confirmed": False,
        "d3d_execution_authorized": False,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "can_execute_d3d": False,
        "schema_blockers": schema_blockers,
        "schema_probe": dict(schema_probe),
        "target_table": schema_probe.get("target_table"),
        "proposed_columns": list(schema_probe.get("proposed_columns") or []),
        "missing_proposed_columns": list(schema_probe.get("missing_proposed_columns") or []),
        "table_exists": table_exists,
        "all_proposed_columns_exist": columns_exist,
        "persistence_payload_simulation_status": row.get("persistence_payload_simulation_status"),
        "persistence_payload_simulation_hypothetically_valid": payload_simulation_valid,
        "write_permission_manifest_status": row.get("write_permission_manifest_status"),
        "write_permission_manifest_hypothetically_ready": row.get("write_permission_manifest_hypothetically_ready") is True,
        "permission_blockers": list(row.get("permission_blockers") or []),
        "simulation_blockers": list(row.get("simulation_blockers") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "not_a_trade_signal": True,
        "changes_scores": False,
        "changes_ranks": False,
        "changes_states": False,
        "changes_probabilities": False,
        "changes_edge": False,
    }
def build_read_only_supabase_target_table_schema_existence_from_simulation(
    *,
    simulation: Dict[str, Any],
    schema_probe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    simulation_rows = _as_list(simulation.get("persistence_payload_simulation_rows"))
    target_table = _target_table(simulation)
    proposed_columns = _proposed_columns(simulation)
    resolved_schema_probe = (
        dict(schema_probe)
        if isinstance(schema_probe, dict)
        else _read_only_schema_probe(target_table=target_table, proposed_columns=proposed_columns)
    )
    schema_rows = [
        _schema_row(row, resolved_schema_probe, simulation)
        for row in simulation_rows
        if isinstance(row, dict)
    ]
    ready_rows = [
        row for row in schema_rows
        if row["schema_existence_hypothetically_ready"] is True
    ]
    blocked_rows = [
        row for row in schema_rows
        if row["schema_existence_hypothetically_ready"] is not True
    ]
    guardrail_failure_count = _as_int(simulation.get("guardrail_failure_count"))
    schema_audit_status = (
        "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY"
        if schema_rows and not blocked_rows and guardrail_failure_count == 0
        else "SUPABASE_TARGET_TABLE_SCHEMA_MISSING_OR_BLOCKED_READ_ONLY"
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
        "supabase_target_table_schema_existence_audit_status": schema_audit_status,
        "persistence_payload_simulation_audit_status": simulation.get("persistence_payload_simulation_audit_status"),
        "write_permission_manifest_audit_status": simulation.get("write_permission_manifest_audit_status"),
        "controlled_persistence_activation_readiness_audit_status": simulation.get("controlled_persistence_activation_readiness_audit_status"),
        "controlled_persistence_contract_audit_status": simulation.get("controlled_persistence_contract_audit_status"),
        "d3d_dry_run_gate_audit_status": simulation.get("d3d_dry_run_gate_audit_status"),
        "operator_control_evidence_audit_status": simulation.get("operator_control_evidence_audit_status"),
        "evidence_payload_completeness_status": simulation.get("evidence_payload_completeness_status"),
        "source_coverage_completion_status": simulation.get("source_coverage_completion_status"),
        "coverage_is_complete": simulation.get("coverage_is_complete") is True,
        "requested_symbols": simulation.get("requested_symbols") or [],
        "requested_symbol_count": _as_int(simulation.get("requested_symbol_count")),
        "audited_symbol_count": _as_int(simulation.get("audited_symbol_count")),
        "schema_existence_row_count": len(schema_rows),
        "schema_existence_ready_symbol_count": len(ready_rows),
        "schema_existence_blocked_symbol_count": len(blocked_rows),
        "schema_existence_ready_symbols": [row["symbol"] for row in ready_rows],
        "schema_existence_blocked_symbols": [row["symbol"] for row in blocked_rows],
        "schema_probe": resolved_schema_probe,
        "target_table": resolved_schema_probe.get("target_table"),
        "proposed_columns": list(resolved_schema_probe.get("proposed_columns") or []),
        "missing_proposed_columns": list(resolved_schema_probe.get("missing_proposed_columns") or []),
        "table_exists": resolved_schema_probe.get("table_exists") is True,
        "all_proposed_columns_exist": resolved_schema_probe.get("all_proposed_columns_exist") is True,
        "schema_probe_method": resolved_schema_probe.get("schema_probe_method"),
        "schema_probe_is_read_only": resolved_schema_probe.get("schema_probe_is_read_only") is True,
        "schema_probe_attempted": resolved_schema_probe.get("schema_probe_attempted") is True,
        "schema_probe_status": resolved_schema_probe.get("schema_probe_status"),
        "schema_probe_http_status": resolved_schema_probe.get("schema_probe_http_status"),
        "schema_probe_error_excerpt": resolved_schema_probe.get("schema_probe_error_excerpt") or "",
        "supabase_url_present": resolved_schema_probe.get("supabase_url_present") is True,
        "supabase_key_present": resolved_schema_probe.get("supabase_key_present") is True,
        "supabase_key_source": resolved_schema_probe.get("supabase_key_source") or "",
        "supabase_target_table_schema_existence_rows": schema_rows,
        "guardrail_failure_count": guardrail_failure_count,
        "guardrail_failures": list(simulation.get("guardrail_failures") or []),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "supabase_target_table_schema_existence_applies_no_changes": True,
        "supabase_target_table_schema_existence_is_read_only": True,
        "supabase_target_table_schema_existence_never_writes": True,
        "supabase_target_table_schema_existence_never_authorizes": True,
        "guardrails": _guardrails(),
    }
def run_read_only_supabase_target_table_schema_existence_audit(
    *,
    symbols: Any = "SPY,QQQ,IWM",
    requested_timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 20,
    max_symbols: int = 10,
) -> Dict[str, Any]:
    simulation = run_read_only_persistence_payload_simulation_audit(
        symbols=symbols,
        requested_timeframe=requested_timeframe,
        lookback_bars=lookback_bars,
        minimum_usable_bars=minimum_usable_bars,
        max_symbols=max_symbols,
    )
    return build_read_only_supabase_target_table_schema_existence_from_simulation(
        simulation=simulation,
    )
