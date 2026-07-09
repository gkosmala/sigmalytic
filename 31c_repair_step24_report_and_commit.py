#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT = Path("audit_step31c_repair_step24_report_and_commit.json")

STEP23B = Path("audit_step23b_focused_legacy_fallback_quarantine_patch.json")
STEP23C = Path("audit_step23c_verify_focused_legacy_fallback_quarantine.json")
STEP24_TARGET = Path("audit_step24_update_readiness_legacy_fallback_gate.json")
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
    print("SIGMALYTIC V2 — STEP 31C REPAIR STEP 24 REPORT")
    print("MODE: LOCAL REPORT REPAIR ONLY / NO DEPLOY / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    checks: list[str] = []

    step23b = read_json(STEP23B)
    step23c = read_json(STEP23C)
    readiness = read_json(READINESS)

    if step23b.get("status") != "PASS":
        failures.append("Step 23B report is not PASS")
    else:
        checks.append("Step 23B report PASS")

    if step23c.get("status") != "PASS":
        failures.append("Step 23C report is not PASS")
    else:
        checks.append("Step 23C report PASS")

    required_readiness = {
        "operator_control_evidence_hardened": True,
        "legacy_fallbacks_quarantined": True,
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
            checks.append(f"readiness {key}={expected}")
            print(f"PASS: readiness {key}={expected}")

    if not failures:
        compatibility_report = {
            "status": "PASS",
            "mode": "COMPATIBILITY_RECREATED_FROM_VERIFIED_READINESS_STATE_NO_MUTATION",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "reason": (
                "Step 31 expected this exact Step 24 audit filename. "
                "The verified readiness state confirms legacy_fallbacks_quarantined=True "
                "while campaign_pipeline_validated remains False and billing remains blocked."
            ),
            "source_reports": {
                "step23b": str(STEP23B),
                "step23c": str(STEP23C),
                "readiness": str(READINESS),
            },
            "checks": checks,
            "readiness_verified": {
                key: readiness.get(key)
                for key in required_readiness
            },
            "billing_gate": {
                "should_remain_blocked": True,
                "reason": "campaign_pipeline_validated remains False",
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
            },
        }

        write_json(STEP24_TARGET, compatibility_report)
        print("PASS: recreated missing Step 24 compatibility report:", STEP24_TARGET)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_STEP24_REPORT_REPAIR_NO_DEPLOY_NO_DATABASE_WRITE",
        "failures": failures,
        "checks": checks,
        "created_report": str(STEP24_TARGET) if not failures else None,
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
        print("FAIL: STEP 31C REPORT REPAIR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 31C REPORT REPAIR COMPLETE")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
