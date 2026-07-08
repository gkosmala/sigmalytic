"""
Sigmalytic V2 - D3E.5 controlled append-only audit write route hard-block.

This module intentionally does not write to Supabase.
It does not mutate campaigns.
It does not execute or authorize D3D.
It does not confirm operator control.
It does not create trade signals.
It does not touch Stripe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


TARGET_TABLE = "alert_readiness_audit_events"
D3E_PHASE = "D3E.5"
FUTURE_D3E6_CONFIRMATION_PHRASE = "CONFIRM_APPEND_ONLY_AUDIT_WRITE_D3E6"

DOCTRINE_STATEMENT = (
    "Operator control is evidence, not a score. "
    "Composite Operator Control cannot be inferred from scores, ranks, gamma overlays, "
    "probability outputs, downstream price results, future returns, trade signals, "
    "or probability/edge calculations. Composite Operator Control requires tested supply "
    "exhaustion, active demand/support validation, structurally meaningful location, "
    "and absence of contrary failure."
)

ALLOWED_PERSISTENCE_FIELDS_IF_LATER_AUTHORIZED = [
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


def build_controlled_append_only_audit_write_route_payload(
    request_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a hard-blocked D3E.5 route payload.

    D3E.5 creates a controlled route surface only. It never performs a Supabase write.
    A future D3E.6 step may authorize one controlled append-only audit event only after
    a separate explicit authorization gate is implemented and verified.
    """

    payload = dict(request_payload or {})
    supplied_confirmation_phrase = str(payload.get("confirmation_phrase") or "")
    future_phrase_recognized = supplied_confirmation_phrase == FUTURE_D3E6_CONFIRMATION_PHRASE

    return {
        "ok": True,
        "d3e_phase": D3E_PHASE,
        "target_table": TARGET_TABLE,
        "route_status": (
            "CONTROLLED_APPEND_ONLY_AUDIT_WRITE_ROUTE_EXISTS_"
            "BUT_EXECUTION_BLOCKED_UNTIL_D3E6_EXPLICIT_AUTHORIZATION"
        ),
        "route_is_mounted": True,
        "execution_blocked": True,
        "dry_run_only": True,
        "d3e6_required_before_any_write": True,
        "future_confirmation_phrase_required": FUTURE_D3E6_CONFIRMATION_PHRASE,
        "future_confirmation_phrase_recognized": future_phrase_recognized,
        "schema_required_status": (
            "SUPABASE_TARGET_TABLE_SCHEMA_EXISTS_BUT_WRITES_NOT_AUTHORIZED_READ_ONLY"
        ),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "doctrine_statement": DOCTRINE_STATEMENT,
        "allowed_persistence_fields_if_later_authorized": list(
            ALLOWED_PERSISTENCE_FIELDS_IF_LATER_AUTHORIZED
        ),
        "absolutely_prohibited_persistence_fields": list(
            ABSOLUTELY_PROHIBITED_PERSISTENCE_FIELDS
        ),
        "writes_to_supabase": False,
        "supabase_write_authorized": False,
        "persistence_write_authorized": False,
        "append_only": True,
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
        "request_payload_keys_seen": sorted(str(key) for key in payload.keys()),
    }
