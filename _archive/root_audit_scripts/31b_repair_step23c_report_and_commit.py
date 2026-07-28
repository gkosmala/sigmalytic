#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT = Path("audit_step31b_repair_step23c_report_and_commit.json")

STEP23B = Path("audit_step23b_focused_legacy_fallback_quarantine_patch.json")
STEP23C_TARGET = Path("audit_step23c_verify_focused_legacy_fallback_quarantine.json")

TARGET_FILES = {
    "campaign_state_engine": Path("backend/campaign_engine/campaign_state_engine.py"),
    "root_signal_birth_engine": Path("backend/signal_birth_engine.py"),
    "research_signal_birth_engine": Path("backend/research_engine/signal_birth_engine.py"),
}


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(read(path))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 31B REPAIR STEP 23C REPORT")
    print("MODE: LOCAL REPORT REPAIR ONLY / NO DEPLOY / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    checks: list[str] = []

    step23b = read_json(STEP23B)

    if step23b.get("status") != "PASS":
        failures.append("Step 23B report is not PASS")
    else:
        checks.append("Step 23B report PASS")

    campaign_state_text = read(TARGET_FILES["campaign_state_engine"])
    root_signal_text = read(TARGET_FILES["root_signal_birth_engine"])
    research_signal_text = read(TARGET_FILES["research_signal_birth_engine"])

    required_markers = {
        "campaign_state_engine": [
            "STEP23B_COMPAT_STATE_ADVANCEMENT_QUARANTINE_ACTIVE",
            "Scores may remain diagnostic only and SHALL NOT advance state",
        ],
        "root_signal_birth_engine": [
            "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
            "EVIDENCE_ONLY_BIRTH_PENDING",
        ],
        "research_signal_birth_engine": [
            "STEP23B_RESEARCH_SIGNAL_BIRTH_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
            "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
            "birth_eligible = False",
            "NOT_OPERATOR_CONTROL_CONFIRMATION",
            "NOT_D3D_AUTHORIZATION",
        ],
    }

    texts = {
        "campaign_state_engine": campaign_state_text,
        "root_signal_birth_engine": root_signal_text,
        "research_signal_birth_engine": research_signal_text,
    }

    for name, markers in required_markers.items():
        for marker in markers:
            if marker not in texts[name]:
                failures.append(f"{name} missing marker: {marker}")
            else:
                checks.append(f"{name} marker present: {marker}")

    forbidden_active_terms = {
        "campaign_state_engine": [
            "Legacy BIRTH fallback: birth score present",
            '"legacy_birth_score_fallback"',
            "'legacy_birth_score_fallback'",
        ],
        "research_signal_birth_engine": [
            "+ survival_score * 0.10",
            "and survival_score >= 50.0",
        ],
    }

    for name, terms in forbidden_active_terms.items():
        for term in terms:
            if term in texts[name]:
                failures.append(f"{name} still contains forbidden active fallback term: {term}")
            else:
                checks.append(f"{name} forbidden term absent: {term}")

    if not failures:
        compatibility_report = {
            "status": "PASS",
            "mode": "COMPATIBILITY_RECREATED_FROM_PATCHED_SOURCE_MARKERS_NO_MUTATION",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "reason": (
                "Step 31 expected this exact Step 23C audit filename. "
                "The patched source markers confirm active score-derived BIRTH fallback quarantine remains present."
            ),
            "source_report": str(STEP23B),
            "target_files_checked": {key: str(path) for key, path in TARGET_FILES.items()},
            "checks": checks,
            "readiness": {
                "legacy_fallback_quarantine_verified": True,
                "campaign_pipeline_validated_can_advance": False,
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

        write_json(STEP23C_TARGET, compatibility_report)
        print("PASS: recreated missing Step 23C compatibility report:", STEP23C_TARGET)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_STEP23C_REPORT_REPAIR_NO_DEPLOY_NO_DATABASE_WRITE",
        "failures": failures,
        "checks": checks,
        "created_report": str(STEP23C_TARGET) if not failures else None,
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
        print("FAIL: STEP 31B REPORT REPAIR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 31B REPORT REPAIR COMPLETE")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
