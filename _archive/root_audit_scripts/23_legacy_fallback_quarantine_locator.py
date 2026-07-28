#!/usr/bin/env python3
"""
Sigmalytic V2 Step 23 — Legacy Fallback Quarantine Locator.

Purpose:
    Locate remaining lifecycle fallback logic that may still allow score-derived
    or incomplete-evidence campaign state advancement.

Mode:
    Local read-only source locator only.
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

ROOTS = [Path("backend")]
REPORT = Path("audit_step23_legacy_fallback_quarantine_locator.json")

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

AUDIT_PREFIX_RE = re.compile(r"^\d{2}[a-zA-Z]?_")

LEGACY_FALLBACK_PATTERNS = [
    r"Legacy BIRTH fallback",
    r"birth score present",
    r"full evidence payload is not yet available",
    r"legacy.*fallback",
    r"fallback.*birth",
    r"fallback.*campaign",
]

SCORE_DERIVED_LIFECYCLE_PATTERNS = [
    r"survival_score\s*>=\s*50",
    r"\+\s*survival_score\s*\*\s*0\.10",
    r"birth_score\s*>=",
    r"master_score\s*>=",
    r"campaign_score\s*>=",
    r"score.*eligible",
    r"eligible.*score",
]

STATE_ADVANCEMENT_TERMS = [
    "NO_CAMPAIGN",
    "BIRTH",
    "CONFIRMED",
    "SURVIVING",
    "EXPANDING",
    "MATURING",
    "DISTRIBUTION_RISK",
    "CLOSED",
]


def should_scan(path: Path) -> bool:
    if set(path.parts) & EXCLUDED_DIRS:
        return False
    if path.suffix.lower() != ".py":
        return False
    if AUDIT_PREFIX_RE.match(path.name):
        return False
    return True


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def context(lines: list[str], line_no: int, radius: int = 10) -> list[dict[str, Any]]:
    start = max(1, line_no - radius)
    end = min(len(lines), line_no + radius)
    return [
        {"line": idx, "text": lines[idx - 1]}
        for idx in range(start, end + 1)
    ]


def grep_hits(path: Path, text: str, patterns: list[str], category: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                hits.append({
                    "category": category,
                    "path": str(path),
                    "line": idx,
                    "pattern": pattern,
                    "text": line.strip(),
                    "context": context(lines, idx),
                })

    return hits


def state_related_file(path: Path, text: str) -> bool:
    target = f"{path.as_posix()} {text}".lower()
    return any(term.lower() in target for term in STATE_ADVANCEMENT_TERMS)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 23 LEGACY FALLBACK QUARANTINE LOCATOR")
    print("MODE: LOCAL READ-ONLY SOURCE LOCATOR / NO MUTATION")
    print("=" * 72)

    files: list[Path] = []
    for root in ROOTS:
        if root.exists():
            files.extend(path for path in root.rglob("*.py") if should_scan(path))

    files = sorted(files)

    syntax_failures: list[dict[str, Any]] = []
    legacy_hits: list[dict[str, Any]] = []
    score_lifecycle_hits: list[dict[str, Any]] = []
    state_files: list[str] = []

    for path in files:
        text = safe_read(path)

        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            syntax_failures.append({
                "path": str(path),
                "error": f"{exc.msg} at line {exc.lineno}",
            })

        if state_related_file(path, text):
            state_files.append(str(path))

        legacy_hits.extend(
            grep_hits(path, text, LEGACY_FALLBACK_PATTERNS, "LEGACY_FALLBACK_REFERENCE")
        )

        score_lifecycle_hits.extend(
            grep_hits(path, text, SCORE_DERIVED_LIFECYCLE_PATTERNS, "SCORE_DERIVED_LIFECYCLE_REFERENCE")
        )

    blockers = legacy_hits + score_lifecycle_hits

    report = {
        "mode": "LOCAL_READ_ONLY_LEGACY_FALLBACK_LOCATOR_NO_MUTATION",
        "status": "PASS" if not blockers and not syntax_failures else "FAIL",
        "summary": {
            "files_scanned": len(files),
            "state_related_files": len(state_files),
            "legacy_hits": len(legacy_hits),
            "score_lifecycle_hits": len(score_lifecycle_hits),
            "syntax_failures": len(syntax_failures),
            "blockers": len(blockers),
        },
        "syntax_failures": syntax_failures,
        "state_related_files": state_files,
        "legacy_hits": legacy_hits,
        "score_lifecycle_hits": score_lifecycle_hits,
        "blockers": blockers,
        "readiness": {
            "legacy_fallbacks_quarantined_can_advance": False if blockers else True,
            "reason": (
                "Any remaining legacy fallback or score-derived lifecycle reference "
                "must be quarantined before legacy_fallbacks_quarantined can become true."
            ),
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
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Files scanned: {len(files)}")
    print(f"State-related files: {len(state_files)}")
    print(f"Legacy fallback hits: {len(legacy_hits)}")
    print(f"Score lifecycle hits: {len(score_lifecycle_hits)}")
    print(f"Syntax failures: {len(syntax_failures)}")
    print(f"Report written: {REPORT}")

    if syntax_failures:
        print("\nSYNTAX FAILURES")
        for failure in syntax_failures:
            print(f"FAIL: {failure['path']} — {failure['error']}")

    if legacy_hits:
        print("\nLEGACY FALLBACK HITS")
        for hit in legacy_hits[:80]:
            print(f"LEGACY: {hit['path']}:{hit['line']} — {hit['text']}")

    if score_lifecycle_hits:
        print("\nSCORE-DERIVED LIFECYCLE HITS")
        for hit in score_lifecycle_hits[:80]:
            print(f"SCORE: {hit['path']}:{hit['line']} — {hit['text']}")

    if blockers or syntax_failures:
        print("=" * 72)
        print("FAIL: STEP 23 FOUND LEGACY FALLBACK ITEMS TO QUARANTINE")
        print("SEND FULL OUTPUT")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 23 COMPLETE — NO LEGACY FALLBACK ITEMS FOUND")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
