#!/usr/bin/env python3
"""
Sigmalytic V2 Step 7B — Signal Birth score-dependency quarantine.

Purpose:
    Quarantine score-derived lifecycle birth eligibility in backend/signal_birth_engine.py.

Mode:
    Local source patch only.
    No Supabase write.
    No campaign database mutation.
    No D3D authorization.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

TARGET = Path("backend/signal_birth_engine.py")
BACKUP = Path("backend/signal_birth_engine.py.step7b.bak")

MARKER = "STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE"

OLD_BIRTH_SCORE = """        birth_score = self._safe_score(
            master_index * 0.60
            + resistance_score * 0.15
            + resolution_score * 0.15
            + survival_score * 0.10
        )
"""

NEW_BIRTH_SCORE = """        # STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE
        # Scores below are retained as backward-compatible diagnostics only.
        # They are NOT_OPERATOR_CONTROL_CONFIRMATION and NOT_D3D_AUTHORIZATION.
        # They SHALL NOT advance lifecycle state pending evidence-only transition law.
        birth_score = self._safe_score(
            master_index * 0.60
            + resistance_score * 0.20
            + resolution_score * 0.20
        )
"""

OLD_BIRTH_ELIGIBLE = """        birth_eligible = (
            master_index >= 65.0
            and resolution_score >= 60.0
            and survival_score >= 50.0
            and confirmation_count >= 2
        )
"""

NEW_BIRTH_ELIGIBLE = """        score_birth_conditions_diagnostic = (
            master_index >= 65.0
            and resolution_score >= 60.0
            and confirmation_count >= 2
        )
        # STEP7B: lifecycle birth advancement is disabled until evidence-only law exists.
        birth_eligible = False
"""

OLD_EXPLANATION = """        explanation = (
            f"Signal Birth {birth_state}; birth_score={birth_score}; "
            f"MCI={master_index}, resistance={resistance_score}, "
            f"resolution={resolution_score}, survival={survival_score}, "
            f"confirmations={confirmation_count}/3."
        )
"""

NEW_EXPLANATION = """        explanation = (
            f"Signal Birth {birth_state}; diagnostic_birth_score={birth_score}; "
            f"MCI={master_index}, resistance={resistance_score}, "
            f"resolution={resolution_score}, confirmations={confirmation_count}/3. "
            "STEP7B quarantine active: score-derived birth eligibility disabled pending evidence-only lifecycle law."
        )
"""


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1), True
    if count == 0 and new in text:
        print(f"PASS: {label} already patched.")
        return text, False
    raise RuntimeError(f"{label}: expected exactly one match, found {count}")


def verify(text: str) -> None:
    forbidden = [
        "+ survival_score * 0.10",
        "and survival_score >= 50.0",
        'f"resolution={resolution_score}, survival={survival_score}, "',
    ]

    for item in forbidden:
        if item in text:
            raise AssertionError(f"forbidden score-dependency remains: {item}")

    required = [
        MARKER,
        "birth_eligible = False",
        "NOT_OPERATOR_CONTROL_CONFIRMATION",
        "NOT_D3D_AUTHORIZATION",
        "score-derived birth eligibility disabled pending evidence-only lifecycle law",
    ]

    for item in required:
        if item not in text:
            raise AssertionError(f"required quarantine marker missing: {item}")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 7B SIGNAL BIRTH QUARANTINE")
    print("MODE: LOCAL SOURCE PATCH ONLY")
    print("=" * 72)

    if not TARGET.exists():
        return fail(f"target file not found: {TARGET}")

    original = TARGET.read_text(encoding="utf-8-sig", errors="replace")

    if not BACKUP.exists():
        shutil.copy2(TARGET, BACKUP)
        print(f"PASS: backup created: {BACKUP}")
    else:
        print(f"PASS: backup already exists: {BACKUP}")

    text = original

    text, _ = replace_once(text, OLD_BIRTH_SCORE, NEW_BIRTH_SCORE, "birth_score quarantine")
    text, _ = replace_once(text, OLD_BIRTH_ELIGIBLE, NEW_BIRTH_ELIGIBLE, "birth_eligible quarantine")
    text, _ = replace_once(text, OLD_EXPLANATION, NEW_EXPLANATION, "explanation quarantine")

    verify(text)

    if text != original:
        TARGET.write_text(text, encoding="utf-8")
        print(f"PASS: patched {TARGET}")
    else:
        print("PASS: target already in Step 7B quarantine state.")

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
        return fail("patched file failed Python syntax check")

    print("PASS: patched file compiles cleanly.")

    patched_text = TARGET.read_text(encoding="utf-8-sig", errors="replace")
    verify(patched_text)
    print("PASS: quarantine verification passed.")

    print("=" * 72)
    print("PASS: STEP 7B COMPLETE — SIGNAL BIRTH SCORE DEPENDENCY QUARANTINED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
