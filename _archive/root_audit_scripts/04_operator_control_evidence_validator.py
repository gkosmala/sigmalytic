#!/usr/bin/env python3
"""
Sigmalytic V2 Step 4 — Operator-control evidence validator v1.1.

Purpose:
    Enforce the doctrine that operator control is evidence, not a score.

Mode:
    Local JSON validation only.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No production operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_EVIDENCE = [
    "tested_supply_exhaustion_evidence",
    "active_demand_validation_evidence",
    "structural_location_evidence",
    "absence_of_contrary_failure_evidence",
]

OPTIONAL_SUPPORTING_EVIDENCE = [
    "support_validation_evidence",
    "evidence_timestamp",
    "evidence_source",
    "operator_control_evidence_version",
]

FORBIDDEN_CONFIRMATION_SOURCES = [
    "composite_score",
    "campaign_score",
    "survival_score",
    "rank",
    "tier",
    "probability",
    "edge",
    "expected_return",
    "gamma_overlay",
    "options_overlay",
    "historical_return",
    "future_return",
    "target_hit",
    "trade_signal",
]


@dataclass(frozen=True)
class ValidationResult:
    status: str
    reasons: list[str]


def truthy_evidence(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        return bool(normalized) and normalized not in {"false", "none", "null", "0", "n/a", "na"}
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("payload root must be a JSON object")
    return payload


def validate(payload: dict[str, Any]) -> ValidationResult:
    reasons: list[str] = []

    for field in REQUIRED_EVIDENCE:
        if truthy_evidence(payload.get(field)):
            reasons.append(f"PASS: required evidence present: {field}")
        else:
            reasons.append(f"FAIL: required evidence missing/empty: {field}")

    for field in OPTIONAL_SUPPORTING_EVIDENCE:
        if field in payload:
            if truthy_evidence(payload.get(field)):
                reasons.append(f"INFO: optional supporting evidence present: {field}")
            else:
                reasons.append(f"WARN: optional supporting evidence empty: {field}")

    for field in FORBIDDEN_CONFIRMATION_SOURCES:
        value = payload.get(field)
        if value not in (None, "", [], {}):
            reasons.append(
                f"WARN: forbidden confirmation source present but non-confirming only: {field}={value!r}"
            )

    contrary_failure_present = payload.get("contrary_failure_present")
    if contrary_failure_present is True:
        reasons.append("FAIL: contrary failure is present; operator control evidence is conflicted.")

    required_pass = all(truthy_evidence(payload.get(field)) for field in REQUIRED_EVIDENCE)
    no_contrary_failure = contrary_failure_present is not True

    if required_pass and no_contrary_failure:
        status = "EVIDENCE_SUFFICIENT_READ_ONLY_NOT_A_TRADE_SIGNAL"
    else:
        status = "EVIDENCE_INSUFFICIENT_OR_CONFLICTED"

    return ValidationResult(status=status, reasons=reasons)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    args = parser.parse_args()

    path = Path(args.payload)
    if not path.exists():
        raise SystemExit(f"FAIL: payload file not found: {path}")

    payload = load_json_object(path)
    result = validate(payload)

    print(json.dumps(
        {
            "status": result.status,
            "read_only": True,
            "not_a_trade_signal": True,
            "does_not_mutate_campaigns": True,
            "does_not_authorize_d3d": True,
            "does_not_confirm_operator_control_in_production": True,
            "reasons": result.reasons,
        },
        indent=2,
    ))

    if result.status != "EVIDENCE_SUFFICIENT_READ_ONLY_NOT_A_TRADE_SIGNAL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
