#!/usr/bin/env python3
"""
Sigmalytic V2 Step 6 — Wyckoff/Livermore/Weis evidence reconciliation.

Purpose:
    Confirm that method-specific evidence remains separated and is not collapsed
    into a generic score.

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

REQUIRED = {
    "wyckoff": [
        "accumulation",
        "absorption",
        "supply_demand_relationship",
    ],
    "livermore": [
        "pivotal_point",
        "line_of_least_resistance",
        "continuation_or_failure",
    ],
    "weis": [
        "effort_vs_result",
        "wave_behavior",
        "supply_exhaustion_or_demand_emergence",
    ],
}

FORBIDDEN_COLLAPSE_FIELDS = [
    "single_master_score",
    "operator_control_score",
    "score_confirms_operator_control",
]


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("campaign evidence root must be a JSON object")
    return payload


def truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in {"false", "none", "null", "0", "n/a", "na"}
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-evidence", required=True)
    args = parser.parse_args()

    path = Path(args.campaign_evidence)
    if not path.exists():
        raise SystemExit(f"FAIL: campaign evidence file not found: {path}")

    payload = load_json_object(path)
    failures: list[str] = []

    print("=" * 72)
    print("SIGMALYTIC V2 — WYCKOFF / LIVERMORE / WEIS RECONCILIATION")
    print("MODE: READ-ONLY / LOCAL SNAPSHOT ONLY")
    print("=" * 72)
    print(f"Evidence file: {path}")

    for method, fields in REQUIRED.items():
        block = payload.get(method)

        if not isinstance(block, dict):
            failures.append(f"missing method block: {method}")
            continue

        print(f"\nCHECK METHOD: {method.upper()}")

        for field in fields:
            if field not in block:
                failures.append(f"missing {method}.{field}")
            elif not truthy(block.get(field)):
                failures.append(f"empty {method}.{field}")
            else:
                print(f"PASS: {method}.{field} exists and is non-empty")

    print("\nCHECK: Forbidden collapse fields")

    for field in FORBIDDEN_COLLAPSE_FIELDS:
        if field in payload:
            failures.append(f"forbidden collapse field present: {field}")
        else:
            print(f"PASS: forbidden collapse field absent: {field}")

    if failures:
        print("=" * 72)
        print("FAIL: WLW evidence reconciliation failed.")
        for failure in failures:
            print("  ", failure)
        print("DO NOT collapse Wyckoff/Livermore/Weis into a generic score.")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: method-specific evidence remains separated.")
    print("PASS: no generic score collapse detected.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
