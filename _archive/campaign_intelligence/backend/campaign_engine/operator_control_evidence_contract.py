"""
Sigmalytic V2 — Operator-Control Evidence Contract.

Doctrine:
    Operator control is evidence, not a score.

    Operator control SHALL NOT be derived from composite score, campaign score,
    survival score, rank, tier, gamma/options overlay, probability, edge,
    expected return, historical outcomes, target projections, future returns,
    trade signals, or probability/edge calculations.

Mode:
    Contract validation only.
    No Supabase write.
    No campaign mutation.
    No D3D authorization.
    No operator-control confirmation mutation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_OPERATOR_CONTROL_EVIDENCE_CONTRACT_2026_07_09"

REQUIRED_EVIDENCE_KEYS = (
    "tested_supply_exhaustion",
    "active_demand_validation",
    "support_validation",
    "structural_location",
    "absence_of_contrary_failure",
)

FORBIDDEN_CONFIRMATION_SOURCE_KEYS = (
    "composite_score",
    "campaign_score",
    "survival_score",
    "master_score",
    "score",
    "rank",
    "tier",
    "probability",
    "edge",
    "expected_return",
    "gamma",
    "gex",
    "historical_outcome",
    "future_return",
    "target_projection",
    "trade_signal",
)

FORBIDDEN_ACTION_FLAGS = (
    "writes_to_supabase",
    "mutates_campaigns",
    "executes_d3d",
    "authorizes_d3d",
    "operator_control_confirmed",
    "creates_trade_signal",
    "touches_stripe",
)


def _is_truthy_action(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "yes", "1", "enabled"}


def _extract_evidence_root(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload.get("operator_control_evidence")
    if isinstance(candidate, dict):
        return candidate

    candidate = payload.get("evidence")
    if isinstance(candidate, dict):
        nested = candidate.get("operator_control_evidence")
        if isinstance(nested, dict):
            return nested

        nested = candidate.get("operator_control")
        if isinstance(nested, dict):
            return nested

        return candidate

    return payload


def _valid_evidence_entry(entry: Any) -> tuple[bool, str]:
    if not isinstance(entry, dict):
        return False, "entry must be a dictionary"

    if entry.get("present") is not True:
        return False, "entry.present must be true"

    source = entry.get("source")
    if not isinstance(source, str) or not source.strip():
        return False, "entry.source must be a non-empty string"

    explanation = entry.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        return False, "entry.explanation must be a non-empty string"

    return True, "valid"


def validate_operator_control_evidence_contract(payload: Any) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "EVIDENCE_INSUFFICIENT_OR_INVALID",
            "evidence_sufficient": False,
            "operator_control_confirmed": False,
            "d3d_authorized": False,
            "trade_signal": False,
            "failures": ["payload must be a dictionary"],
            "warnings": [],
        }

    evidence = _extract_evidence_root(payload)

    for flag in FORBIDDEN_ACTION_FLAGS:
        if _is_truthy_action(payload.get(flag)) or _is_truthy_action(evidence.get(flag)):
            failures.append(f"forbidden action flag must not be true: {flag}")

    for key in FORBIDDEN_CONFIRMATION_SOURCE_KEYS:
        if key in payload or key in evidence:
            warnings.append(f"diagnostic field ignored as confirmation source: {key}")

    for key in REQUIRED_EVIDENCE_KEYS:
        ok, reason = _valid_evidence_entry(evidence.get(key))
        if not ok:
            failures.append(f"required evidence invalid: {key}: {reason}")

    evidence_sufficient = not failures

    return {
        "contract_version": CONTRACT_VERSION,
        "status": (
            "EVIDENCE_SUFFICIENT_READ_ONLY_NOT_A_TRADE_SIGNAL"
            if evidence_sufficient
            else "EVIDENCE_INSUFFICIENT_OR_INVALID"
        ),
        "evidence_sufficient": evidence_sufficient,
        "operator_control_confirmed": False,
        "d3d_authorized": False,
        "trade_signal": False,
        "failures": failures,
        "warnings": warnings,
        "required_evidence_keys": list(REQUIRED_EVIDENCE_KEYS),
        "forbidden_confirmation_source_keys": list(FORBIDDEN_CONFIRMATION_SOURCE_KEYS),
    }


__all__ = [
    "CONTRACT_VERSION",
    "REQUIRED_EVIDENCE_KEYS",
    "FORBIDDEN_CONFIRMATION_SOURCE_KEYS",
    "FORBIDDEN_ACTION_FLAGS",
    "validate_operator_control_evidence_contract",
]
