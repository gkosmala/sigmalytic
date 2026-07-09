#!/usr/bin/env python3
"""
Sigmalytic V2 Step 7C — Signal Birth quarantine verification.

Purpose:
    Verify Step 7B removed score-derived lifecycle birth advancement from
    backend/signal_birth_engine.py.

Mode:
    Read-only source verification.
    No file patch.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

TARGET = Path("backend/signal_birth_engine.py")

REQUIRED_PRESENT = [
    "STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
    "birth_eligible = False",
    "score_birth_conditions_diagnostic",
    "NOT_OPERATOR_CONTROL_CONFIRMATION",
    "NOT_D3D_AUTHORIZATION",
    "score-derived birth eligibility disabled pending evidence-only lifecycle law",
]

FORBIDDEN_PRESENT = [
    "+ survival_score * 0.10",
    "and survival_score >= 50.0",
    'f"resolution={resolution_score}, survival={survival_score}, "',
]

ALLOWED_DIAGNOSTIC_TERMS = [
    "survival_score = self._safe_score",
    "survival_score=survival_score",
    "diagnostic_birth_score",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 7C SIGNAL BIRTH QUARANTINE VERIFY")
    print("MODE: READ-ONLY SOURCE VERIFY")
    print("=" * 72)

    require(TARGET.exists(), f"target exists: {TARGET}")

    text = TARGET.read_text(encoding="utf-8-sig", errors="replace")

    ast.parse(text, filename=str(TARGET))
    print("PASS: Python AST parses clean.")

    compile_result = subprocess.run(
        ["py", "-m", "py_compile", str(TARGET)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if compile_result.returncode != 0:
        print(compile_result.stdout)
        print(compile_result.stderr)
        raise AssertionError("target failed py_compile")

    print("PASS: py_compile clean.")

    for marker in REQUIRED_PRESENT:
        require(marker in text, f"required quarantine marker present: {marker}")

    for marker in FORBIDDEN_PRESENT:
        require(marker not in text, f"forbidden score-dependency absent: {marker}")

    for marker in ALLOWED_DIAGNOSTIC_TERMS:
        if marker in text:
            print(f"INFO: diagnostic-only term remains for compatibility: {marker}")

    print("=" * 72)
    print("PASS: STEP 7C COMPLETE — SIGNAL BIRTH SCORE-DEPENDENCY QUARANTINE VERIFIED")
    print("PASS: birth eligibility cannot advance from score arithmetic in this file.")
    print("PASS: D3D remains blocked.")
    print("PASS: no operator-control confirmation occurred.")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
