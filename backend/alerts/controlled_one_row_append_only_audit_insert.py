"""
Sigmalytic V2 - D3E.6 controlled one-row append-only audit insert.

This module creates the controlled insert mechanism only.
It never mutates campaigns.
It never executes or authorizes D3D.
It never confirms operator control.
It never creates trade signals.
It never touches Stripe.

Execution remains locked unless the caller supplies the exact D3E.6 authorization phrase,
sets dry_run to False, and uses the controlled route intentionally.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


TARGET_TABLE = "alert_readiness_audit_events"
D3E_PHASE = "D3E.6"
D3E6_AUTHORIZATION_PHRASE = "AUTHORIZE_D3E6_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_NOW"

DOCTRINE_STATEMENT = (
    "Operator control is evidence, not a score. "
    "Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, "
    "probability outputs, downstream price results, future returns, trade signals, "
    "or probability/edge calculations. Composite Operator Control requires tested supply "
    "exhaustion, active demand/support validation, structurally meaningful location, "
    "and absence of contrary failure."
)

READ_ONLY_GUARDRAILS = {
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

ALLOWED_PERSISTENCE_FIELDS_IF_AUTHORIZED = [
    "symbol",
    "audit_component",
    "audit_version",
    "source_coverage_completion_status",
    "evidence_payload_completeness_status",
    "operator_control_evidence_audit_status",
    "d3d_dry_run_gate_audit_status",
    "controlled_persistence_contract_audit_status",
    "controlled_persistence_activation_readiness_audit_status",
    "activation_hypothetically_ready",
    "activation_readiness_blockers",
    "read_only_guardrails",
    "allowed_persistence_fields_if_later_authorized",
    "absolutely_prohibited_persistence_fields",
    "doctrine_statement",
    "payload",
]

ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS = [
    "campaign_state_mutation",
    "campaign_score_mutation",
    "campaign_rank_mutation",
    "probability_mutation",
    "edge_mutation",
    "expected_return_mutation",
    "operator_control_confirmation",
    "composite_operator_control_confirmation",
    "d3d_authorization",
    "d3d_execution",
    "trade_signal_creation",
    "stripe_payment_state",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_url() -> str:
    return str(os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")


def _supabase_service_key() -> str:
    return str(
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    )


def build_d3e6_audit_row(request_payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(request_payload or {})

    return {
        "symbol": str(payload.get("symbol") or "D3E6_AUDIT"),
        "audit_component": "controlled_one_row_append_only_audit_insert",
        "audit_version": "D3E.6",
        "source_coverage_completion_status": "D3E6_ROUTE_BUILD_COMPLETE",
        "evidence_payload_completeness_status": "CONTROLLED_AUDIT_EVENT_PAYLOAD_COMPLETE",
        "operator_control_evidence_audit_status": "NOT_OPERATOR_CONTROL_CONFIRMATION",
        "d3d_dry_run_gate_audit_status": "D3D_NOT_AUTHORIZED_NOT_EXECUTED",
        "controlled_persistence_contract_audit_status": "APPEND_ONLY_AUDIT_INSERT_CONTRACT",
        "controlled_persistence_activation_readiness_audit_status": (
            "ONE_ROW_APPEND_ONLY_AUDIT_INSERT_AUTHORIZATION_REQUIRED"
        ),
        "activation_hypothetically_ready": False,
        "activation_readiness_blockers": [
            "D3E6 exact execution authorization required",
            "dry_run must be false for the one-row insert execution step",
            "campaign mutation remains prohibited",
            "D3D authorization and execution remain prohibited",
            "operator-control confirmation remains prohibited",
            "Stripe remains untouched",
        ],
        "read_only_guardrails": dict(READ_ONLY_GUARDRAILS),
        "allowed_persistence_fields_if_later_authorized": list(
            ALLOWED_PERSISTENCE_FIELDS_IF_AUTHORIZED
        ),
        "absolutely_prohibited_persistence_fields": list(
            ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS
        ),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "payload": {
            "d3e_phase": D3E_PHASE,
            "created_at_utc": _utc_now_iso(),
            "request_source": str(payload.get("source") or "d3e6_controlled_insert"),
            "requested_by_operator": True,
            "one_row_only": True,
            "append_only": True,
            "schema_required_status": (
                "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY"
            ),
            "doctrine_guardrails": dict(READ_ONLY_GUARDRAILS),
        },
    }


def build_d3e6_readiness_payload() -> Dict[str, Any]:
    supabase_url_present = bool(_supabase_url())
    supabase_key_present = bool(_supabase_service_key())

    return {
        "ok": True,
        "d3e_phase": D3E_PHASE,
        "target_table": TARGET_TABLE,
        "route_status": "D3E6_CONTROLLED_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_ROUTE_READY_BUT_NOT_EXECUTED",
        "route_is_mounted": True,
        "execution_requires_exact_authorization_phrase": True,
        "authorization_phrase_required": D3E6_AUTHORIZATION_PHRASE,
        "dry_run_default": True,
        "one_row_only": True,
        "append_only": True,
        "supabase_url_present": supabase_url_present,
        "supabase_key_present": supabase_key_present,
        "writes_to_supabase": False,
        "supabase_write_authorized": False,
        "persistence_write_authorized": False,
        **READ_ONLY_GUARDRAILS,
    }


def execute_d3e6_controlled_one_row_insert(
    request_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload = dict(request_payload or {})
    authorization_phrase = str(payload.get("authorization_phrase") or "")
    dry_run = bool(payload.get("dry_run", True))

    authorized = authorization_phrase == D3E6_AUTHORIZATION_PHRASE
    audit_row = build_d3e6_audit_row(payload)

    base_response = {
        "ok": True,
        "d3e_phase": D3E_PHASE,
        "target_table": TARGET_TABLE,
        "route_is_mounted": True,
        "one_row_only": True,
        "append_only": True,
        "authorization_phrase_recognized": authorized,
        "dry_run": dry_run,
        "audit_row_preview": audit_row,
        **READ_ONLY_GUARDRAILS,
    }

    if not authorized:
        return {
            **base_response,
            "route_status": "D3E6_EXECUTION_BLOCKED_AUTHORIZATION_PHRASE_NOT_RECOGNIZED",
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "insert_attempted": False,
            "insert_status": "NOT_ATTEMPTED",
        }

    if dry_run:
        return {
            **base_response,
            "route_status": "D3E6_DRY_RUN_PREVIEW_ONLY_NO_INSERT_EXECUTED",
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "insert_attempted": False,
            "insert_status": "DRY_RUN_ONLY",
        }

    supabase_url = _supabase_url()
    supabase_key = _supabase_service_key()

    if not supabase_url or not supabase_key:
        return {
            **base_response,
            "route_status": "D3E6_EXECUTION_BLOCKED_SUPABASE_ENV_MISSING",
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "insert_attempted": False,
            "insert_status": "SUPABASE_ENV_MISSING",
            "supabase_url_present": bool(supabase_url),
            "supabase_key_present": bool(supabase_key),
        }

    endpoint = f"{supabase_url}/rest/v1/{TARGET_TABLE}"
    body = json.dumps(audit_row).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
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
            "route_status": "D3E6_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_FAILED",
            "writes_to_supabase": False,
            "supabase_write_authorized": True,
            "persistence_write_authorized": True,
            "insert_attempted": True,
            "insert_status": "FAILED_HTTP_ERROR",
            "insert_http_status": int(exc.code),
            "insert_error_excerpt": error_body[:700],
        }
    except Exception as exc:
        return {
            **base_response,
            "route_status": "D3E6_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_FAILED",
            "writes_to_supabase": False,
            "supabase_write_authorized": True,
            "persistence_write_authorized": True,
            "insert_attempted": True,
            "insert_status": "FAILED_EXCEPTION",
            "insert_error_excerpt": str(exc)[:700],
        }

    success = 200 <= status_code < 300

    return {
        **base_response,
        "route_status": (
            "D3E6_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_EXECUTED"
            if success
            else "D3E6_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_UNEXPECTED_STATUS"
        ),
        "writes_to_supabase": bool(success),
        "supabase_write_authorized": True,
        "persistence_write_authorized": True,
        "insert_attempted": True,
        "insert_status": "SUCCESS" if success else "UNEXPECTED_STATUS",
        "insert_http_status": status_code,
        "insert_response_excerpt": response_body[:700],
    }
