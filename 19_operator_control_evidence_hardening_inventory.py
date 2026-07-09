#!/usr/bin/env python3
"""
Sigmalytic V2 Step 19 — Operator-Control Evidence Hardening Inventory.

Purpose:
    Locate all operator-control related code paths and classify whether any
    production code still risks deriving operator control from scores, ranks,
    probabilities, gamma overlays, outcomes, or trade-signal logic.

Mode:
    Local read-only audit only.
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
import re
from pathlib import Path
from typing import Any

ROOT = Path(".")
REPORT = Path("audit_step19_operator_control_evidence_hardening_inventory.json")

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
}

PRODUCTION_DIRS = {
    "backend",
    "frontend",
}

AUDIT_PREFIX_RE = re.compile(r"^\d{2}[a-zA-Z]?_")

OPERATOR_TERMS = [
    "operator_control",
    "operator control",
    "operator_dominance",
    "operator dominance",
    "control_confirmed",
    "operator_confirmed",
    "composite_operator_control",
]

FORBIDDEN_SCORE_TERMS = [
    "score",
    "rank",
    "tier",
    "probability",
    "expected_return",
    "expected return",
    "edge",
    "gamma",
    "gex",
    "outcome",
    "target",
    "trade_signal",
    "signal",
    "survival_score",
    "campaign_score",
    "composite_score",
    "master_score",
]

REQUIRED_EVIDENCE_TERMS = [
    "tested_supply_exhaustion",
    "active_demand_validation",
    "support_validation",
    "structural_location",
    "absence_of_contrary_failure",
]


def should_scan(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_DIRS:
        return False
    if path.suffix.lower() != ".py":
        return False
    if AUDIT_PREFIX_RE.match(path.name):
        return False
    return True


def is_production_file(path: Path) -> bool:
    return bool(path.parts and path.parts[0] in PRODUCTION_DIRS)


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def line_has_any(line: str, terms: list[str]) -> bool:
    lower = line.lower()
    return any(term.lower() in lower for term in terms)


def ast_parse_ok(path: Path, text: str) -> tuple[bool, str | None]:
    try:
        ast.parse(text)
        return True, None
    except SyntaxError as exc:
        return False, f"{exc.msg} at line {exc.lineno}"


def classify_line(path: Path, line_no: int, line: str) -> dict[str, Any] | None:
    lower = line.lower()

    has_operator = line_has_any(line, OPERATOR_TERMS)
    has_forbidden = line_has_any(line, FORBIDDEN_SCORE_TERMS)
    has_required_evidence = line_has_any(line, REQUIRED_EVIDENCE_TERMS)

    if not has_operator and not has_required_evidence:
        return None

    severity = "INFO"
    category = "OPERATOR_OR_EVIDENCE_REFERENCE"

    if has_operator and has_forbidden and is_production_file(path):
        severity = "REVIEW"
        category = "OPERATOR_REFERENCE_NEAR_SCORE_OR_SIGNAL_TERM"

        confirmation_words = [
            "confirm",
            "confirmed",
            "eligible",
            "authorize",
            "advance",
            "transition",
            "mutate",
            "persist",
            "write",
            "birth",
            "d3d",
        ]

        if any(word in lower for word in confirmation_words):
            severity = "BLOCKER"
            category = "POTENTIAL_SCORE_DERIVED_OPERATOR_CONTROL_PATH"

    if has_required_evidence:
        severity = "INFO"
        category = "REQUIRED_EVIDENCE_TERM_PRESENT"

    return {
        "severity": severity,
        "category": category,
        "path": str(path),
        "line": line_no,
        "text": line.strip(),
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 19 OPERATOR-CONTROL EVIDENCE HARDENING INVENTORY")
    print("MODE: LOCAL READ-ONLY AUDIT / NO PRODUCTION MUTATION")
    print("=" * 72)

    findings: list[dict[str, Any]] = []
    syntax_failures: list[dict[str, str]] = []

    files = sorted(path for path in ROOT.rglob("*.py") if should_scan(path))

    for path in files:
        text = safe_read(path)
        ok, syntax_error = ast_parse_ok(path, text)
        if not ok:
            syntax_failures.append({"path": str(path), "error": syntax_error or "syntax error"})
            continue

        for idx, line in enumerate(text.splitlines(), start=1):
            finding = classify_line(path, idx, line)
            if finding:
                findings.append(finding)

    blockers = [f for f in findings if f["severity"] == "BLOCKER"]
    reviews = [f for f in findings if f["severity"] == "REVIEW"]
    infos = [f for f in findings if f["severity"] == "INFO"]

    evidence_presence = {
        term: [
            f for f in findings
            if term.lower() in f["text"].lower()
        ]
        for term in REQUIRED_EVIDENCE_TERMS
    }

    missing_evidence_terms = [
        term for term, hits in evidence_presence.items()
        if not hits
    ]

    report = {
        "mode": "LOCAL_READ_ONLY_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not blockers and not syntax_failures else "FAIL",
        "summary": {
            "files_scanned": len(files),
            "findings_total": len(findings),
            "blockers": len(blockers),
            "reviews": len(reviews),
            "infos": len(infos),
            "syntax_failures": len(syntax_failures),
            "missing_required_evidence_terms": missing_evidence_terms,
        },
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
        "syntax_failures": syntax_failures,
        "blockers": blockers,
        "reviews": reviews,
        "infos": infos[:250],
        "missing_required_evidence_terms": missing_evidence_terms,
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Files scanned: {len(files)}")
    print(f"Findings total: {len(findings)}")
    print(f"Blockers: {len(blockers)}")
    print(f"Reviews: {len(reviews)}")
    print(f"Info findings: {len(infos)}")
    print(f"Syntax failures: {len(syntax_failures)}")
    print(f"Missing required evidence terms: {missing_evidence_terms}")
    print(f"Report written: {REPORT}")

    if syntax_failures:
        print("\nSYNTAX FAILURES")
        for item in syntax_failures:
            print(f"FAIL: {item['path']} — {item['error']}")

    if blockers:
        print("\nBLOCKERS")
        for finding in blockers[:80]:
            print(f"BLOCKER: {finding['path']}:{finding['line']} — {finding['category']} — {finding['text']}")

    if reviews:
        print("\nREVIEWS")
        for finding in reviews[:80]:
            print(f"REVIEW: {finding['path']}:{finding['line']} — {finding['category']} — {finding['text']}")

    if blockers or syntax_failures:
        print("=" * 72)
        print("FAIL: STEP 19 INVENTORY FOUND OPERATOR-CONTROL HARDENING BLOCKERS")
        print("SEND FULL OUTPUT")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 19 COMPLETE — NO BLOCKING SCORE-DERIVED OPERATOR-CONTROL PATH FOUND")
    print("PASS: proceed to operator-control evidence contract hardening.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
