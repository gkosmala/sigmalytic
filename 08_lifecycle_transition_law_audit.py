#!/usr/bin/env python3
"""
Sigmalytic V2 Step 8 — Campaign lifecycle transition law audit.

Purpose:
    Validate that each campaign state transition has explicit evidence requirements
    and does not depend on scores, ranks, probabilities, gamma, edge, expected
    return, trade signals, or downstream price outcomes.

Mode:
    Local JSON audit only.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_TRANSITIONS = [
    "NO_CAMPAIGN->BIRTH",
    "BIRTH->CONFIRMED",
    "CONFIRMED->SURVIVING",
    "SURVIVING->EXPANDING",
    "EXPANDING->MATURING",
    "MATURING->DISTRIBUTION_RISK",
    "ANY->CLOSED",
]

FORBIDDEN_DEPENDENCIES = [
    "score",
    "rank",
    "probability",
    "edge",
    "expected_return",
    "gamma",
    "future_return",
    "historical_return",
    "target_hit",
    "trade_signal",
]

REQUIRED_GLOBAL_FALSE = [
    "mutates_campaign",
    "authorizes_d3d",
    "confirms_operator_control",
    "creates_trade_signal",
    "touches_stripe",
]


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("lifecycle law root must be a JSON object")
    return payload


def truthy_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--law", required=True)
    args = parser.parse_args()

    path = Path(args.law)
    if not path.exists():
        raise SystemExit(f"FAIL: law file not found: {path}")

    law = load_json_object(path)
    failures: list[str] = []
    warnings: list[str] = []

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 8 LIFECYCLE TRANSITION LAW AUDIT")
    print("MODE: LOCAL JSON AUDIT / READ-ONLY")
    print("=" * 72)
    print(f"Law file: {path}")

    doctrine = law.get("doctrine")
    if not isinstance(doctrine, dict):
        failures.append("missing doctrine block")
    else:
        if doctrine.get("operator_control_is_evidence_not_score") is not True:
            failures.append("doctrine missing operator_control_is_evidence_not_score=True")
        for field in REQUIRED_GLOBAL_FALSE:
            if doctrine.get(field) is not False:
                failures.append(f"doctrine must set {field}=False")

    transitions = law.get("transitions")
    if not isinstance(transitions, dict):
        failures.append("missing transitions object")
        transitions = {}

    for transition in REQUIRED_TRANSITIONS:
        rule = transitions.get(transition)
        if not isinstance(rule, dict):
            failures.append(f"missing transition law: {transition}")
            continue

        evidence = rule.get("required_evidence")
        if not truthy_list(evidence):
            failures.append(f"transition lacks required_evidence: {transition}")

        if rule.get("audit_explanation_required") is not True:
            failures.append(f"transition lacks audit_explanation_required=True: {transition}")

        explicitly_non_confirming = rule.get("explicitly_non_confirming", False)
        text = json.dumps(rule, sort_keys=True).lower()

        for forbidden in FORBIDDEN_DEPENDENCIES:
            if forbidden in text and explicitly_non_confirming is not True:
                failures.append(
                    f"transition may depend on forbidden source '{forbidden}' without explicit non-confirming flag: {transition}"
                )

        if rule.get("may_mutate_campaign") is not False:
            failures.append(f"transition must set may_mutate_campaign=False until D3D law exists: {transition}")

        if rule.get("may_authorize_d3d") is not False:
            failures.append(f"transition must set may_authorize_d3d=False: {transition}")

        if rule.get("may_create_trade_signal") is not False:
            failures.append(f"transition must set may_create_trade_signal=False: {transition}")

        print(f"CHECKED: {transition}")

    unexpected = sorted(set(transitions.keys()) - set(REQUIRED_TRANSITIONS))
    if unexpected:
        warnings.append(f"unexpected extra transition keys present: {unexpected}")

    if warnings:
        print("\nWARNINGS")
        for warning in warnings:
            print(f"WARN: {warning}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(f"FAIL: {failure}")
        print("=" * 72)
        print("FAIL: lifecycle transition law audit failed.")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: lifecycle transition law is explicit and evidence-based.")
    print("PASS: no transition may mutate campaigns or authorize D3D.")
    print("PASS: no transition may confirm operator control from score/rank/probability/gamma/edge.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
