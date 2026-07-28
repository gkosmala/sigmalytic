#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

READINESS = Path("v2_readiness.json")
SEMANTIC_AUDIT = Path("audit_step19a_semantic_operator_control_hardening_audit.json")
CONTRACT_AUDIT = Path("audit_step20_operator_control_evidence_contract.json")
REPORT = Path("audit_step21_operator_control_readiness_update.json")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 21 OPERATOR-CONTROL READINESS UPDATE")
    print("MODE: LOCAL JSON UPDATE / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []

    readiness = load_json(READINESS)
    semantic = load_json(SEMANTIC_AUDIT)
    contract = load_json(CONTRACT_AUDIT)

    if semantic.get("status") != "PASS":
        failures.append("Step 19A semantic operator-control audit is not PASS")

    if contract.get("status") != "PASS":
        failures.append("Step 20 operator-control evidence contract audit is not PASS")

    contract_doctrine = contract.get("doctrine") or {}
    required_contract_flags = {
        "operator_control_is_evidence_not_score": True,
        "score_rank_probability_gamma_only_rejected": True,
        "no_supabase_write": True,
        "no_campaign_mutation": True,
        "no_d3d": True,
        "no_operator_control_confirmation": True,
        "no_trade_signal": True,
        "no_stripe": True,
    }

    for key, expected in required_contract_flags.items():
        if contract_doctrine.get(key) is not expected:
            failures.append(f"Step 20 doctrine flag not satisfied: {key}")

    semantic_doctrine = semantic.get("doctrine") or {}
    if semantic_doctrine.get("text_only_doctrine_strings_not_blockers") is not True:
        failures.append("Step 19A did not preserve semantic false-positive protection")

    forbidden_true_fields = [
        "d3d_authorized",
        "operator_control_confirmed_by_score",
        "campaign_mutation_without_d3d_law",
    ]

    for field in forbidden_true_fields:
        if readiness.get(field) is not False:
            failures.append(f"readiness forbidden field must remain false: {field}")

    if failures:
        report = {
            "status": "FAIL",
            "failures": failures,
            "updated": False,
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
        print("FAIL: STEP 21 READINESS UPDATE FAILED")
        print("=" * 72)
        return 1

    readiness["operator_control_evidence_hardened"] = True

    readiness["campaign_pipeline_validated"] = bool(readiness.get("campaign_pipeline_validated") is True)
    readiness["legacy_fallbacks_quarantined"] = bool(readiness.get("legacy_fallbacks_quarantined") is True)

    readiness["d3d_authorized"] = False
    readiness["operator_control_confirmed_by_score"] = False
    readiness["campaign_mutation_without_d3d_law"] = False

    READINESS.write_text(json.dumps(readiness, indent=2), encoding="utf-8")

    report = {
        "status": "PASS",
        "updated": True,
        "operator_control_evidence_hardened": True,
        "campaign_pipeline_validated": readiness["campaign_pipeline_validated"],
        "legacy_fallbacks_quarantined": readiness["legacy_fallbacks_quarantined"],
        "billing_should_remain_blocked": not (
            readiness["campaign_pipeline_validated"]
            and readiness["legacy_fallbacks_quarantined"]
        ),
        "doctrine": {
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

    print("PASS: Step 19A semantic audit PASS verified")
    print("PASS: Step 20 contract audit PASS verified")
    print("PASS: v2_readiness.json updated: operator_control_evidence_hardened=true")
    print("PASS: D3D remains false")
    print("PASS: operator_control_confirmed_by_score remains false")
    print("PASS: campaign_mutation_without_d3d_law remains false")
    print("PASS: billing remains blocked until campaign_pipeline_validated and legacy_fallbacks_quarantined are true")
    print("Report written:", REPORT)
    print("=" * 72)
    print("PASS: STEP 21 COMPLETE — OPERATOR-CONTROL READINESS GATE UPDATED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
