#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step23c_focused_legacy_fallback_quarantine_verification.json")

TARGETS = {
    "campaign_state_engine": Path("backend/campaign_engine/campaign_state_engine.py"),
    "root_signal_birth": Path("backend/signal_birth_engine.py"),
    "research_signal_birth": Path("backend/research_engine/signal_birth_engine.py"),
    "campaign_discovery_engine": Path("backend/campaign_engine/campaign_discovery_engine.py"),
}

FORBIDDEN_BY_FILE = {
    "campaign_state_engine": [
        "Legacy BIRTH fallback: birth score present",
        "full evidence payload is not yet available",
        '"transition_reason": ["legacy_birth_score_fallback"]',
        "if birth_score >= 55:",
    ],
    "root_signal_birth": [
        "if birth_score >= 85.0 and birth_eligible:",
        "elif birth_score >= 70.0 and birth_eligible:",
        "elif birth_score >= 55.0:",
    ],
    "research_signal_birth": [
        "+ survival_score * 0.10",
        "and survival_score >= 50.0",
        "if birth_score >= 85.0 and birth_eligible:",
        "elif birth_score >= 70.0 and birth_eligible:",
        "elif birth_score >= 55.0:",
    ],
}

REQUIRED_BY_FILE = {
    "campaign_state_engine": [
        "STEP23B_COMPAT_STATE_ADVANCEMENT_QUARANTINE_ACTIVE",
        "Score-derived compatibility advancement is disabled.",
        "Scores may remain diagnostic only and SHALL NOT advance state.",
    ],
    "root_signal_birth": [
        "STEP7B_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
        "birth_eligible = False",
        "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
        'birth_state = "NO_BIRTH"',
    ],
    "research_signal_birth": [
        "STEP23B_RESEARCH_SIGNAL_BIRTH_SCORE_DEPENDENCY_QUARANTINE_ACTIVE",
        "NOT_OPERATOR_CONTROL_CONFIRMATION",
        "NOT_D3D_AUTHORIZATION",
        "birth_eligible = False",
        "STEP23B_SCORE_STATE_LABEL_QUARANTINE_ACTIVE",
        'birth_state = "NO_BIRTH"',
    ],
}

DISCOVERY_LINE_REVIEW_TERMS = [
    "discovered = birth_score >= self.birth_threshold",
    "survival_score >= self.survival_threshold",
]


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing target file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def syntax_check(name: str, path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print(f"PASS: syntax clean: {path}")
    except SyntaxError as exc:
        failures.append(f"syntax failure {name}: {path}: {exc.msg} line {exc.lineno}")


def verify_forbidden(name: str, text: str, failures: list[str]) -> None:
    for item in FORBIDDEN_BY_FILE.get(name, []):
        if item in text:
            failures.append(f"forbidden text still present in {name}: {item}")
        else:
            print(f"PASS: forbidden text absent in {name}: {item}")


def verify_required(name: str, text: str, failures: list[str]) -> None:
    for item in REQUIRED_BY_FILE.get(name, []):
        if item not in text:
            failures.append(f"required marker missing in {name}: {item}")
        else:
            print(f"PASS: required marker present in {name}: {item}")


def discovery_review(text: str) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        if any(term in line for term in DISCOVERY_LINE_REVIEW_TERMS):
            reviews.append({
                "path": str(TARGETS["campaign_discovery_engine"]),
                "line": idx,
                "text": line.strip(),
                "classification": (
                    "REVIEW_ONLY_DISCOVERY_THRESHOLD_NOT_YET_QUARANTINED; "
                    "does not by itself confirm operator control, authorize D3D, "
                    "or create trade signals, but campaign_pipeline_validated remains false."
                ),
            })

    return reviews


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 23C FOCUSED POST-QUARANTINE VERIFICATION")
    print("MODE: LOCAL READ-ONLY VERIFY / NO PRODUCTION MUTATION")
    print("=" * 72)

    failures: list[str] = []
    reviews: list[dict[str, Any]] = []
    texts: dict[str, str] = {}

    for name, path in TARGETS.items():
        try:
            text = read(path)
            texts[name] = text
            syntax_check(name, path, failures)
        except Exception as exc:
            failures.append(f"could not read/check {name}: {exc}")

    for name, text in texts.items():
        verify_forbidden(name, text, failures)
        verify_required(name, text, failures)

    if "campaign_discovery_engine" in texts:
        reviews.extend(discovery_review(texts["campaign_discovery_engine"]))

    step23b_report = Path("audit_step23b_focused_legacy_fallback_quarantine_patch.json")
    if step23b_report.exists():
        try:
            data = json.loads(step23b_report.read_text(encoding="utf-8-sig"))
            if data.get("status") != "PASS":
                failures.append("Step 23B report status is not PASS")
            else:
                print("PASS: Step 23B report status PASS")
        except Exception as exc:
            failures.append(f"could not parse Step 23B report: {exc}")
    else:
        failures.append("missing Step 23B report")

    report = {
        "mode": "LOCAL_READ_ONLY_POST_QUARANTINE_VERIFY_NO_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "reviews": reviews,
        "readiness": {
            "legacy_fallbacks_quarantined_can_advance": not failures,
            "campaign_pipeline_validated_remains_false": True,
            "campaign_discovery_threshold_review_deferred_to_pipeline_validation": bool(reviews),
        },
        "doctrine": {
            "active_legacy_birth_fallback_quarantined": not failures,
            "root_signal_birth_score_labeling_quarantined": not failures,
            "research_signal_birth_score_dependency_quarantined": not failures,
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

    if reviews:
        print("\nREVIEWS")
        for item in reviews:
            print(f"REVIEW: {item['path']}:{item['line']} — {item['classification']} — {item['text']}")

    print("Report written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 23C POST-QUARANTINE VERIFICATION FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 23C COMPLETE — FOCUSED LEGACY FALLBACK QUARANTINE VERIFIED")
    print("PASS: campaign_pipeline_validated remains false pending production-read-only coverage validation.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
