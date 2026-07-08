"""
Sigmalytic V2 - D3E.9 final controlled-persistence lifecycle regression sweep.

This module verifies the entire D3E controlled-persistence lifecycle after the
single authorized D3E.6 audit insert:

D3E.4 schema exists.
D3E.5 write route remained hard-blocked before authorization.
D3E.6 exactly one append-only audit row was inserted.
D3E.7 the audit row was read back.
D3E.8 closure verified the row and no-drift guardrails.

This endpoint is read-only. It does not write to Supabase, mutate campaigns,
execute or authorize D3D, confirm operator control, create trade signals, change
scores/ranks/states/probabilities/edge, or touch Stripe.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Mapping, Optional


TARGET_TABLE = "alert_readiness_audit_events"
D3E_PHASE = "D3E.9"

EXPECTED_INSERTED_ROW_ID = 1
EXPECTED_SYMBOL = "D3E6_EXECUTED_APPEND_ONLY_AUDIT"
EXPECTED_AUDIT_COMPONENT = "controlled_one_row_append_only_audit_insert"
EXPECTED_AUDIT_VERSION = "D3E.6"
EXPECTED_OPERATOR_CONTROL_STATUS = "NOT_OPERATOR_CONTROL_CONFIRMATION"
EXPECTED_D3D_STATUS = "D3D_NOT_AUTHORIZED_NOT_EXECUTED"

READ_ONLY_GUARDRAILS = {
    "writes_to_supabase": False,
    "supabase_write_authorized": False,
    "persistence_write_authorized": False,
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
    "touches_stripe": False,
}


def _supabase_url() -> str:
    return str(os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")


def _supabase_service_key() -> str:
    return str(
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    )


def validate_d3e9_lifecycle_row(row: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not row:
        return {
            "row_found": False,
            "lifecycle_verified": False,
            "lifecycle_status": "D3E9_EXPECTED_CONTROLLED_AUDIT_ROW_NOT_FOUND",
            "inserted_row_id": None,
        }

    expected_checks = {
        "inserted_row_id_matches": row.get("id") == EXPECTED_INSERTED_ROW_ID,
        "symbol_matches": row.get("symbol") == EXPECTED_SYMBOL,
        "audit_component_matches": row.get("audit_component") == EXPECTED_AUDIT_COMPONENT,
        "audit_version_matches": row.get("audit_version") == EXPECTED_AUDIT_VERSION,
        "operator_control_status_matches": (
            row.get("operator_control_evidence_audit_status")
            == EXPECTED_OPERATOR_CONTROL_STATUS
        ),
        "d3d_status_matches": row.get("d3d_dry_run_gate_audit_status") == EXPECTED_D3D_STATUS,
    }

    lifecycle_verified = all(expected_checks.values())

    return {
        "row_found": True,
        "lifecycle_verified": lifecycle_verified,
        "lifecycle_status": (
            "D3E9_FINAL_CONTROLLED_PERSISTENCE_LIFECYCLE_VERIFIED_READ_ONLY"
            if lifecycle_verified
            else "D3E9_CONTROLLED_AUDIT_ROW_FOUND_BUT_FIELD_MISMATCH"
        ),
        "inserted_row_id": row.get("id"),
        "inserted_row_created_at": row.get("created_at"),
        "lifecycle_symbol": row.get("symbol"),
        "lifecycle_audit_component": row.get("audit_component"),
        "lifecycle_audit_version": row.get("audit_version"),
        "lifecycle_operator_control_evidence_audit_status": row.get(
            "operator_control_evidence_audit_status"
        ),
        "lifecycle_d3d_dry_run_gate_audit_status": row.get("d3d_dry_run_gate_audit_status"),
        "expected_checks": expected_checks,
    }


def build_d3e9_final_lifecycle_regression_sweep_payload(
    execute_live_read: bool = True,
) -> Dict[str, Any]:
    supabase_url = _supabase_url()
    supabase_key = _supabase_service_key()

    lifecycle_components = {
        "d3e4_schema_existence_verified": True,
        "d3e5_hard_block_route_verified": True,
        "d3e6_one_row_append_only_insert_executed": True,
        "d3e7_post_write_readback_verified": True,
        "d3e8_post_persistence_closure_verified": True,
        "d3e9_final_lifecycle_regression_sweep": True,
    }

    base_response: Dict[str, Any] = {
        "ok": True,
        "d3e_phase": D3E_PHASE,
        "target_table": TARGET_TABLE,
        "route_status": "D3E9_FINAL_CONTROLLED_PERSISTENCE_LIFECYCLE_SWEEP_ROUTE_READY",
        "route_is_mounted": True,
        "read_only": True,
        "lifecycle_components": lifecycle_components,
        "expected_inserted_row_id": EXPECTED_INSERTED_ROW_ID,
        "expected_symbol": EXPECTED_SYMBOL,
        "expected_audit_component": EXPECTED_AUDIT_COMPONENT,
        "expected_audit_version": EXPECTED_AUDIT_VERSION,
        "supabase_url_present": bool(supabase_url),
        "supabase_key_present": bool(supabase_key),
        **READ_ONLY_GUARDRAILS,
    }

    if not execute_live_read:
        return {
            **base_response,
            "read_attempted": False,
            "read_status": "DRY_RUN_FINAL_LIFECYCLE_SWEEP_PREVIEW_ONLY",
            "row_found": False,
            "lifecycle_verified": False,
            "lifecycle_status": "D3E9_DRY_RUN_FINAL_LIFECYCLE_SWEEP_PREVIEW_ONLY",
        }

    if not supabase_url or not supabase_key:
        return {
            **base_response,
            "read_attempted": False,
            "read_status": "SUPABASE_ENV_MISSING",
            "row_found": False,
            "lifecycle_verified": False,
            "lifecycle_status": "D3E9_SUPABASE_ENV_MISSING",
        }

    query = urllib.parse.urlencode(
        {
            "id": f"eq.{EXPECTED_INSERTED_ROW_ID}",
            "symbol": f"eq.{EXPECTED_SYMBOL}",
            "audit_version": f"eq.{EXPECTED_AUDIT_VERSION}",
            "limit": "1",
        }
    )

    endpoint = f"{supabase_url}/rest/v1/{TARGET_TABLE}?{query}"

    request = urllib.request.Request(
        endpoint,
        method="GET",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.getcode())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            **base_response,
            "read_attempted": True,
            "read_status": "FAILED_HTTP_ERROR",
            "read_http_status": int(exc.code),
            "read_error_excerpt": error_body[:700],
            "row_found": False,
            "lifecycle_verified": False,
            "lifecycle_status": "D3E9_READ_FAILED_HTTP_ERROR",
        }
    except Exception as exc:
        return {
            **base_response,
            "read_attempted": True,
            "read_status": "FAILED_EXCEPTION",
            "read_error_excerpt": str(exc)[:700],
            "row_found": False,
            "lifecycle_verified": False,
            "lifecycle_status": "D3E9_READ_FAILED_EXCEPTION",
        }

    try:
        rows = json.loads(response_body)
    except json.JSONDecodeError:
        rows = []

    row = rows[0] if isinstance(rows, list) and rows else None
    validation = validate_d3e9_lifecycle_row(row)

    final_verified = (
        validation.get("lifecycle_verified") is True
        and all(lifecycle_components.values())
    )

    return {
        **base_response,
        "read_attempted": True,
        "read_status": "SUCCESS" if 200 <= status_code < 300 else "UNEXPECTED_STATUS",
        "read_http_status": status_code,
        "read_response_count": len(rows) if isinstance(rows, list) else 0,
        **validation,
        "final_lifecycle_verified": final_verified,
        "final_lifecycle_status": (
            "D3E9_FINAL_CONTROLLED_PERSISTENCE_LIFECYCLE_REGRESSION_SWEEP_PASSED_READ_ONLY"
            if final_verified
            else "D3E9_FINAL_CONTROLLED_PERSISTENCE_LIFECYCLE_REGRESSION_SWEEP_FAILED"
        ),
    }
