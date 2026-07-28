#!/usr/bin/env python3
"""
Sigmalytic V2 Step 22 — Campaign Pipeline Validation Inventory.

Purpose:
    Inventory the production campaign pipeline without executing the nightly
    write path. This validates source coverage and identifies whether the
    remaining campaign_pipeline_validated gate can be safely advanced later.

Mode:
    Local read-only source audit only.
    No nightly run.
    No Alpaca call.
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

REPORT = Path("audit_step22_campaign_pipeline_validation_inventory.json")

REQUIRED_FILES = {
    "nightly_pipeline": Path("backend/campaign_engine/nightly_campaign_pipeline.py"),
    "campaign_state_engine": Path("backend/campaign_engine/campaign_state_engine.py"),
    "campaign_store": Path("backend/campaign_engine/campaign_store.py"),
    "campaign_api": Path("backend/campaign_api.py"),
}

REQUIRED_SOURCE_TERMS = {
    "universe_loading": [
        "universe",
        "alpaca",
    ],
    "bar_fetching": [
        "bars",
        "bar",
    ],
    "campaign_evaluation": [
        "campaign",
        "evaluate",
    ],
    "persistence_boundary": [
        "supabase",
        "insert",
        "upsert",
        "write",
    ],
    "state_handling": [
        "campaign_state",
        "state",
    ],
}

BLOCKING_DRIFT_PATTERNS = [
    r"operator_control_confirmed\s*=\s*True",
    r"authorizes_d3d\s*=\s*True",
    r"executes_d3d\s*=\s*True",
    r"trade_signal\s*=\s*True",
    r"touches_stripe\s*=\s*True",
]

WARNING_PATTERNS = [
    r"Stopped pagination after 20 pages",
    r"Legacy BIRTH fallback",
    r"birth score present",
    r"full evidence payload is not yet available",
    r"survival_score\s*>=\s*50",
    r"\+\s*survival_score\s*\*\s*0\.10",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_ok(path: Path, text: str) -> tuple[bool, str | None]:
    try:
        ast.parse(text, filename=str(path))
        return True, None
    except SyntaxError as exc:
        return False, f"{exc.msg} at line {exc.lineno}"


def scan_terms(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return all(term.lower() in lower for term in terms)


def grep_patterns(path: Path, text: str, patterns: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append({
                    "path": str(path),
                    "line": idx,
                    "pattern": pattern,
                    "text": line.strip(),
                })
    return findings


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 22 CAMPAIGN PIPELINE VALIDATION INVENTORY")
    print("MODE: LOCAL READ-ONLY SOURCE AUDIT / NO NIGHTLY RUN / NO WRITE")
    print("=" * 72)

    failures: list[str] = []
    warnings: list[str] = []
    source_texts: dict[str, str] = {}
    syntax_results: dict[str, Any] = {}

    for label, path in REQUIRED_FILES.items():
        if not path.exists():
            failures.append(f"missing required file: {label}: {path}")
            continue

        text = read_text(path)
        source_texts[label] = text

        ok, err = parse_ok(path, text)
        syntax_results[label] = {"path": str(path), "ok": ok, "error": err}
        if not ok:
            failures.append(f"syntax failure: {path}: {err}")
        else:
            print(f"PASS: syntax clean: {path}")

    combined = "\n".join(source_texts.values())

    term_results: dict[str, bool] = {}
    for category, terms in REQUIRED_SOURCE_TERMS.items():
        present = scan_terms(combined, terms)
        term_results[category] = present
        if present:
            print(f"PASS: source coverage term group present: {category}")
        else:
            failures.append(f"missing source coverage term group: {category} requires {terms}")

    blocking_findings: list[dict[str, Any]] = []
    warning_findings: list[dict[str, Any]] = []

    for label, text in source_texts.items():
        path = REQUIRED_FILES[label]
        blocking_findings.extend(grep_patterns(path, text, BLOCKING_DRIFT_PATTERNS))
        warning_findings.extend(grep_patterns(path, text, WARNING_PATTERNS))

    for finding in blocking_findings:
        failures.append(
            f"blocking drift pattern in {finding['path']}:{finding['line']}: {finding['text']}"
        )

    for finding in warning_findings:
        warnings.append(
            f"warning pattern in {finding['path']}:{finding['line']}: {finding['text']}"
        )

    readiness_can_advance_now = False
    reason = (
        "This is an inventory only. campaign_pipeline_validated must remain false "
        "until a production-read-only pipeline coverage snapshot confirms universe count, "
        "bar coverage, minimum bar depth, pagination completeness, schema alignment, "
        "and no write-side execution during validation."
    )

    report = {
        "mode": "LOCAL_READ_ONLY_SOURCE_AUDIT_NO_NIGHTLY_RUN_NO_WRITE",
        "status": "PASS" if not failures else "FAIL",
        "readiness_can_advance_now": readiness_can_advance_now,
        "reason": reason,
        "failures": failures,
        "warnings": warnings,
        "syntax_results": syntax_results,
        "term_results": term_results,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
        "required_future_pipeline_validation_snapshot": {
            "universe_count": "required",
            "bars_symbols_count": "required",
            "symbols_missing_bars": "must be empty or explained",
            "record_min_bars": "must meet configured threshold",
            "pagination_complete": "must be true",
            "schema_payload_alignment": "must be true",
            "write_path_not_executed_during_validation": "must be true",
        },
        "doctrine": {
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

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Report written: {REPORT}")
    print(f"Failures: {len(failures)}")
    print(f"Warnings: {len(warnings)}")
    print("Readiness can advance now:", readiness_can_advance_now)

    if warnings:
        print("\nWARNINGS")
        for warning in warnings[:80]:
            print("WARN:", warning)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 22 CAMPAIGN PIPELINE INVENTORY FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 22 COMPLETE — CAMPAIGN PIPELINE INVENTORY PASSED")
    print("PASS: campaign_pipeline_validated remains false pending production-read-only coverage snapshot.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
