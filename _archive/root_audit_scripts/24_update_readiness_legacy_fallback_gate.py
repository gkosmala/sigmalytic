#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

READINESS = Path("v2_readiness.json")
STEP23B = Path("audit_step23b_focused_legacy_fallback_quarantine_patch.json")
STEP23C = Path("audit_step23c_focused_legacy_fallback_quarantine_verification.json")
REPORT = Path("audit_step24_legacy_fallback_readiness_update.json")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 24 LEGACY FALLBACK READINESS UPDATE")
    print("MODE: LOCAL JSON UPDATE / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []

    readiness = load_json(READINESS)
    step23b = load_json(STEP23B)
    step23c = load_json(STEP23C)

    if step23b.get("status") != "PASS":
        failures.append("Step 23B focused legacy fallback quarantine patch is not PASS")

    if step23c.get("status") != "PASS":
        failures.append("Step 23C focused legacy fallback verification is not PASS")

    step23b_doctrine = step23b.get("doctrine") or {}
    required_23b_flags = {
        "legacy_birth_fallback_quarantined": True,
        "score_derived_birth_labeling_quarantined": True,
        "research_duplicate_signal_birth_quarantined": True,
        "operator_control_is_evidence_not_score": True,
        "no_supabase_write": True,
        "no_campaign_mutation": True,
        "no_d3d": True,
        "no_operator_control_confirmation": True,
        "no_trade_signal": True,
        "no_stripe": True,
    }

    for key, expected in required_23b_flags.items():
        if step23b_doctrine.get(key) is not expected:
            failures.append(f"Step 23B doctrine flag not satisfied: {key}")

    step23c_readiness = step23c.get("readiness") or {}
    if step23c_readiness.get("legacy_fallbacks_quarantined_can_advance") is not True:
        failures.append("Step 23C did not authorize legacy_fallbacks_quarantined readiness advancement")

    if step23c_readiness.get("campaign_pipeline_validated_remains_false") is not True:
        failures.append("Step 23C did not preserve campaign_pipeline_validated=false boundary")

    forbidden_false_fields = [
        "d3d_authorized",
        "operator_control_confirmed_by_score",
        "campaign_mutation_without_d3d_law",
    ]

    for field in forbidden_false_fields:
        if readiness.get(field) is not False:
            failures.append(f"readiness forbidden field must remain false: {field}")

    if readiness.get("operator_control_evidence_hardened") is not True:
        failures.append("operator_control_evidence_hardened must already be true before advancing legacy fallback gate")

    if failures:
        report = {
            "status": "FAIL",
            "updated": False,
            "failures": failures,
            "doctrine": {
                "no_supabase_write": True,
                "no_campaign_mutation": True,
                "no_d3d": True,
                "no_operator_control_confirmation": True,
                "no_trade_signal": True,
                "no_stripe": True,
            },
        }
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

        print("FAILURES")
        for failure in failures:
            print("FAIL:", failure)

        print("Report written:", REPORT)
        print("=" * 72)
        print("FAIL: STEP 24 READINESS UPDATE FAILED")
        print("=" * 72)
        return 1

    readiness["legacy_fallbacks_quarantined"] = True
    readiness["campaign_pipeline_validated"] = False

    readiness["d3d_authorized"] = False
    readiness["operator_control_confirmed_by_score"] = False
    readiness["campaign_mutation_without_d3d_law"] = False

    READINESS.write_text(json.dumps(readiness, indent=2), encoding="utf-8")

    report = {
        "status": "PASS",
        "updated": True,
        "operator_control_evidence_hardened": readiness["operator_control_evidence_hardened"],
        "legacy_fallbacks_quarantined": True,
        "campaign_pipeline_validated": False,
        "billing_should_remain_blocked": True,
        "remaining_gate": "campaign_pipeline_validated",
        "doctrine": {
            "legacy_fallbacks_quarantined": True,
            "operator_control_is_evidence_not_score": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("PASS: Step 23B patch report PASS verified")
    print("PASS: Step 23C verification report PASS verified")
    print("PASS: v2_readiness.json updated: legacy_fallbacks_quarantined=true")
    print("PASS: campaign_pipeline_validated remains false")
    print("PASS: D3D remains false")
    print("PASS: operator_control_confirmed_by_score remains false")
    print("PASS: campaign_mutation_without_d3d_law remains false")
    print("PASS: billing remains blocked until campaign_pipeline_validated=true")
    print("Report written:", REPORT)
    print("=" * 72)
    print("PASS: STEP 24 COMPLETE — LEGACY FALLBACK READINESS GATE UPDATED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
