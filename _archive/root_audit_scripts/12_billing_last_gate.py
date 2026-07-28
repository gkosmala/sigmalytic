#!/usr/bin/env python3
"""
Sigmalytic V2 Step 12 — Billing/Stripe last-gate verifier.

Purpose:
    Prevent Stripe/billing from being advanced before the core intelligence
    product is stable, no-drift protected, evidence-safe, and deployment-safe.

Mode:
    Local JSON gate validation only.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe call.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_TRUE = [
    "live_ui_preserved",
    "manual_smoke_test_passed",
    "automated_ui_regression_passed",
    "d3e9_complete",
    "d3f2_callback_safe_if_present",
    "operator_control_evidence_hardened",
    "campaign_pipeline_validated",
    "legacy_fallbacks_quarantined",
    "lifecycle_transition_law_complete",
    "alerts_read_only_guarded",
    "deployment_observability_complete",
    "documentation_complete",
]

REQUIRED_FALSE = [
    "d3d_authorized",
    "operator_control_confirmed_by_score",
    "campaign_mutation_without_d3d_law",
]


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("readiness root must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", required=True)
    args = parser.parse_args()

    path = Path(args.readiness)
    if not path.exists():
        raise SystemExit(f"FAIL: readiness file not found: {path}")

    data = load_json_object(path)
    failures: list[str] = []

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 12 BILLING / STRIPE LAST GATE")
    print("MODE: LOCAL JSON GATE / READ-ONLY / NO STRIPE")
    print("=" * 72)

    for field in REQUIRED_TRUE:
        if data.get(field) is not True:
            failures.append(f"required true field not satisfied: {field}")
        else:
            print(f"PASS: {field}=True")

    for field in REQUIRED_FALSE:
        if data.get(field) is not False:
            failures.append(f"required false field not satisfied: {field}")
        else:
            print(f"PASS: {field}=False")

    if failures:
        print("=" * 72)
        print("FAIL: Stripe/billing must remain last. Unmet prerequisites:")
        for failure in failures:
            print(f"  {failure}")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: Billing may be considered; all core product gates are satisfied.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
