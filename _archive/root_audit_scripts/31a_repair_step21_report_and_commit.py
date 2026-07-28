#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT = Path("audit_step31a_repair_step21_report_and_commit.json")

STEP20 = Path("audit_step20_operator_control_evidence_contract.json")
STEP21_TARGET = Path("audit_step21_update_readiness_operator_control_gate.json")
READINESS = Path("v2_readiness.json")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 31A REPAIR STEP 21 REPORT")
    print("MODE: LOCAL REPORT REPAIR ONLY / NO DEPLOY / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    changes: list[str] = []

    step20 = read_json(STEP20)
    readiness = read_json(READINESS)

    if step20.get("status") != "PASS":
        failures.append("Step 20 operator-control evidence contract report is not PASS")

    required_readiness = {
        "operator_control_evidence_hardened": True,
        "campaign_pipeline_validated": False,
        "d3d_authorized": False,
        "operator_control_confirmed_by_score": False,
        "campaign_mutation_without_d3d_law": False,
    }

    for key, expected in required_readiness.items():
        actual = readiness.get(key)
        if actual is not expected:
            failures.append(f"readiness {key} expected {expected}, got {actual}")
        else:
            print(f"PASS: readiness {key}={expected}")

    if not failures:
        compatibility_report = {
            "status": "PASS",
            "mode": "COMPATIBILITY_RECREATED_FROM_VERIFIED_READINESS_STATE_NO_MUTATION",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "reason": (
                "Step 31 expected this exact Step 21 audit filename. "
                "The verified readiness state already shows operator_control_evidence_hardened=True "
                "while D3D, score-confirmed operator control, campaign mutation, and campaign pipeline validation remain blocked."
            ),
            "source_reports": {
                "step20_operator_control_evidence_contract": str(STEP20),
                "readiness": str(READINESS),
            },
            "readiness_verified": {
                key: readiness.get(key)
                for key in required_readiness
            },
            "doctrine": {
                "no_deploy": True,
                "no_nightly_run": True,
                "no_alpaca_call": True,
                "no_supabase_write": True,
                "no_campaign_mutation": True,
                "no_d3d": True,
                "no_operator_control_confirmation": True,
                "no_trade_signal": True,
                "no_stripe": True,
                "billing_remains_blocked": True,
            },
        }

        write_json(STEP21_TARGET, compatibility_report)
        changes.append(f"recreated missing compatibility report: {STEP21_TARGET}")
        print("PASS: recreated missing Step 21 compatibility report:", STEP21_TARGET)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_STEP21_REPORT_REPAIR_NO_DEPLOY_NO_DATABASE_WRITE",
        "changes": changes,
        "failures": failures,
        "doctrine": {
            "no_deploy": True,
            "no_nightly_run": True,
            "no_alpaca_call": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    write_json(REPORT, report)
    print("Report written:", REPORT)

    if failures:
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 31A REPORT REPAIR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 31A REPORT REPAIR COMPLETE")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
