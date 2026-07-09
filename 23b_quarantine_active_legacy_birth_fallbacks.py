#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step23b_focused_legacy_fallback_quarantine_patch.json")

STATE_ENGINE = Path("backend/campaign_engine/campaign_state_engine.py")
ROOT_SIGNAL_BIRTH = Path("backend/signal_birth_engine.py")
RESEARCH_SIGNAL_BIRTH = Path("backend/research_engine/signal_birth_engine.py")

STATE_ENGINE_OLD = '''            # Temporary compatibility fallback. This preserves the already-working
            # discovery flow until the explicit evidence payload is fully wired
            # into every campaign record. Only BIRTH may use this fallback.
            if birth_score >= 55:
                return {
                    "state": CampaignState.BIRTH,
                    "transition_score": evidence_density_score,
                    "advance_allowed": True,
                    "failure_risk": False,
                    "reason": (
                        "Legacy BIRTH fallback: birth score present, but full evidence payload "
                        "is not yet available."
                    ),
                    "transition_reason": ["legacy_birth_score_fallback"],
                }

'''

STATE_ENGINE_NEW = '''            # STEP23B_COMPAT_STATE_ADVANCEMENT_QUARANTINE_ACTIVE
            # Score-derived compatibility advancement is disabled.
            # Lifecycle advancement requires evidence-only transition law.
            # Scores may remain diagnostic only and SHALL NOT advance state.
            score_compatibility_advancement_diagnostic = bool(float(birth_score or 0) >= 55)
            _ = score_compatibility_advancement_diagnostic

'''

RESEARCH_FORMULA_OLD = '''        birth_score = self._safe_score(
            master_index * 0.60
            + resistance_score * 0.15
            + resolution_score * 0.15
            + survival_score * 0.10
        )

        confirmation_count = int(master.get("confirmation_count", 0) or 0)
        agreement_score = self._safe_score(master.get("agreement_score", 0.0))

        birth_eligible = (
            master_index >= 65.0
            and resolution_score >= 60.0
            and survival_score >= 50.0
            and confirmation_count >= 2
        )
'''

RESEARCH_FORMULA_NEW = '''        # STEP23B_RESEARCH_SIGNAL_BIRTH_SCORE_DEPENDENCY_QUARANTINE_ACTIVE
        # Scores below are retained as backward-compatible diagnostics only.
        # They are NOT_OPERATOR_CONTROL_CONFIRMATION and NOT_D3D_AUTHORIZATION.
        # They SHALL NOT advance lifecycle state pending evidence-only transition law.
        birth_score = self._safe_score(
            master_index * 0.60
            + resistance_score * 0.20
            + resolution_score * 0.20
        )

        confirmation_count = int(master.get("confirmation_count", 0) or 0)
        agreement_score = self._safe_score(master.get("agreement_score", 0.0))

        score_birth_conditions_diagnostic = (
            master_index >= 65.0
            and resolution_score >= 60.0
            and confirmation_count >= 2
        )
        _ = score_birth_conditions_diagnostic
        birth_eligible = False
'''

STATE_LABEL_OLD = '''        if birth_score >= 85.0 and birth_eligible:
            birth_state = "CAMPAIGN_BIRTH"
        elif birth_score >= 70.0 and birth_eligible:
            birth_state = "EARLY_CAMPAIGN"
        elif birth_score >= 55.0:
            birth_state = "POTENTIAL_BIRTH"
        else:
            birth_state = "NO_BIRTH"
'''

STATE_LABEL_NEW = '''        # STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE
        # Score thresholds remain diagnostic only and cannot assign lifecycle birth labels.
        if birth_eligible:
            birth_state = "EVIDENCE_ONLY_BIRTH_PENDING"
        else:
            birth_state = "NO_BIRTH"
'''


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def replace_once(path: Path, old: str, new: str, label: str, failures: list[str], changes: list[str]) -> None:
    text = read(path)

    if old not in text:
        if new in text:
            changes.append(f"already patched: {label}: {path}")
            return
        failures.append(f"required snippet not found for {label}: {path}")
        return

    updated = text.replace(old, new, 1)
    write(path, updated)
    changes.append(f"patched: {label}: {path}")


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
    except SyntaxError as exc:
        failures.append(f"syntax failure after patch: {path}: {exc.msg} line {exc.lineno}")


def verify_no_text(path: Path, forbidden: list[str], failures: list[str]) -> None:
    text = read(path)
    for item in forbidden:
        if item in text:
            failures.append(f"forbidden text still present in {path}: {item}")


def verify_has_text(path: Path, required: list[str], failures: list[str]) -> None:
    text = read(path)
    for item in required:
        if item not in text:
            failures.append(f"required text missing in {path}: {item}")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 23B FOCUSED LEGACY FALLBACK QUARANTINE PATCH")
    print("MODE: LOCAL SOURCE PATCH + AUDIT / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []
    changes: list[str] = []

    replace_once(
        STATE_ENGINE,
        STATE_ENGINE_OLD,
        STATE_ENGINE_NEW,
        "campaign_state_engine active compatibility BIRTH fallback quarantine",
        failures,
        changes,
    )

    replace_once(
        RESEARCH_SIGNAL_BIRTH,
        RESEARCH_FORMULA_OLD,
        RESEARCH_FORMULA_NEW,
        "research_engine signal birth survival-score dependency quarantine",
        failures,
        changes,
    )

    replace_once(
        RESEARCH_SIGNAL_BIRTH,
        STATE_LABEL_OLD,
        STATE_LABEL_NEW,
        "research_engine signal birth score label quarantine",
        failures,
        changes,
    )

    replace_once(
        ROOT_SIGNAL_BIRTH,
        STATE_LABEL_OLD,
        STATE_LABEL_NEW,
        "root signal birth score label quarantine",
        failures,
        changes,
    )

    for path in [STATE_ENGINE, ROOT_SIGNAL_BIRTH, RESEARCH_SIGNAL_BIRTH]:
        syntax_check(path, failures)

    verify_no_text(
        STATE_ENGINE,
        [
            "Legacy BIRTH fallback: birth score present",
            "is not yet available.",
            '"transition_reason": ["legacy_birth_score_fallback"]',
            'if birth_score >= 55:',
        ],
        failures,
    )

    verify_no_text(
        RESEARCH_SIGNAL_BIRTH,
        [
            "+ survival_score * 0.10",
            "and survival_score >= 50.0",
            "if birth_score >= 85.0 and birth_eligible:",
            "elif birth_score >= 70.0 and birth_eligible:",
            "elif birth_score >= 55.0:",
        ],
        failures,
    )

    verify_no_text(
        ROOT_SIGNAL_BIRTH,
        [
            "if birth_score >= 85.0 and birth_eligible:",
            "elif birth_score >= 70.0 and birth_eligible:",
            "elif birth_score >= 55.0:",
        ],
        failures,
    )

    verify_has_text(
        STATE_ENGINE,
        [
            "STEP23B_COMPAT_STATE_ADVANCEMENT_QUARANTINE_ACTIVE",
            "Score-derived compatibility advancement is disabled.",
            "Scores may remain diagnostic only and SHALL NOT advance state.",
        ],
        failures,
    )

    verify_has_text(
        RESEARCH_SIGNAL_BIRTH,
        [
            "STEP23B_RESEARCH_SIGNAL_BIRTH_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
            "NOT_OPERATOR_CONTROL_CONFIRMATION",
            "NOT_D3D_AUTHORIZATION",
            "birth_eligible = False",
            "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
        ],
        failures,
    )

    verify_has_text(
        ROOT_SIGNAL_BIRTH,
        [
            "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
            'birth_state = "NO_BIRTH"',
        ],
        failures,
    )

    report: dict[str, Any] = {
        "mode": "LOCAL_SOURCE_PATCH_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "changes": changes,
        "failures": failures,
        "patched_files": [
            str(STATE_ENGINE),
            str(ROOT_SIGNAL_BIRTH),
            str(RESEARCH_SIGNAL_BIRTH),
        ],
        "doctrine": {
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
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for change in changes:
        print("PASS:", change)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("Report written:", REPORT)
        print("=" * 72)
        print("FAIL: STEP 23B PATCH FAILED")
        print("=" * 72)
        return 1

    print("Report written:", REPORT)
    print("=" * 72)
    print("PASS: STEP 23B COMPLETE — ACTIVE LEGACY FALLBACKS QUARANTINED")
    print("PASS: no Supabase write, no campaign mutation, no D3D, no operator-control confirmation, no trade signal, no Stripe.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
