#!/usr/bin/env python3
"""
Sigmalytic V2 Step 7D — Post-quarantine audit.

Purpose:
    Verify the Step 7B/7C Signal Birth quarantine remains intact and that the
    former score-derived lifecycle birth path is no longer active.

Mode:
    Read-only local audit report.
    No source patch.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

TARGET = Path("backend/signal_birth_engine.py")
REPORT = Path("audit_step7d_post_quarantine_audit.json")

REQUIRED_MARKERS = [
    "STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
    "birth_eligible = False",
    "score_birth_conditions_diagnostic",
    "NOT_OPERATOR_CONTROL_CONFIRMATION",
    "NOT_D3D_AUTHORIZATION",
    "score-derived birth eligibility disabled pending evidence-only lifecycle law",
]

FORBIDDEN_ACTIVE_PATTERNS = [
    "+ survival_score * 0.10",
    "and survival_score >= 50.0",
    'f"resolution={resolution_score}, survival={survival_score}, "',
    "Legacy BIRTH fallback: birth score present",
    "full evidence payload is not yet available",
]

DIAGNOSTIC_ALLOWED_PATTERNS = [
    "survival_score = self._safe_score",
    "survival_score=survival_score",
    "diagnostic_birth_score",
    "score_birth_conditions_diagnostic",
]


def line_hits(text: str, pattern: str) -> list[int]:
    hits: list[int] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if pattern in line:
            hits.append(idx)
    return hits


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 7D POST-QUARANTINE AUDIT")
    print("MODE: READ-ONLY LOCAL AUDIT")
    print("=" * 72)

    failures: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    if not TARGET.exists():
        failures.append(f"target missing: {TARGET}")
    else:
        text = TARGET.read_text(encoding="utf-8-sig", errors="replace")

        try:
            ast.parse(text, filename=str(TARGET))
            info.append("Python AST parses clean.")
        except Exception as exc:
            failures.append(f"Python AST parse failed: {exc}")

        for marker in REQUIRED_MARKERS:
            hits = line_hits(text, marker)
            if hits:
                info.append(f"required quarantine marker present: {marker} at lines {hits}")
            else:
                failures.append(f"required quarantine marker missing: {marker}")

        for pattern in FORBIDDEN_ACTIVE_PATTERNS:
            hits = line_hits(text, pattern)
            if hits:
                failures.append(f"forbidden active score/fallback pattern remains: {pattern} at lines {hits}")
            else:
                info.append(f"forbidden active pattern absent: {pattern}")

        for pattern in DIAGNOSTIC_ALLOWED_PATTERNS:
            hits = line_hits(text, pattern)
            if hits:
                warnings.append(f"diagnostic/compatibility pattern remains: {pattern} at lines {hits}")

        if "birth_state = \"CAMPAIGN_BIRTH\"" in text:
            if "birth_eligible = False" in text and "STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE" in text:
                warnings.append(
                    "CAMPAIGN_BIRTH branch remains in source but is disabled by birth_eligible=False quarantine."
                )
            else:
                failures.append("CAMPAIGN_BIRTH branch remains without verified quarantine.")

    report: dict[str, Any] = {
        "mode": "READ_ONLY_LOCAL_AUDIT_NO_PATCH",
        "target": str(TARGET),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "info": info,
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "d3d_remains_blocked": True,
            "no_campaign_mutation": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True
        }
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Report written: {REPORT}")

    print("\nINFO")
    for item in info:
        print(f"PASS: {item}")

    if warnings:
        print("\nWARNINGS")
        for item in warnings:
            print(f"WARN: {item}")

    if failures:
        print("\nFAILURES")
        for item in failures:
            print(f"FAIL: {item}")
        print("=" * 72)
        print("FAIL: STEP 7D POST-QUARANTINE AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 7D COMPLETE — FORMER SCORE-DERIVED BIRTH PATH IS QUARANTINED")
    print("PASS: D3D remains blocked.")
    print("PASS: no operator-control confirmation occurred.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
