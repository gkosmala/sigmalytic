#!/usr/bin/env python3
"""
Sigmalytic V2 Step 7 — Legacy fallback quarantine audit.

Purpose:
    Find fallback logic that could advance campaign state based only on scores
    or incomplete evidence.

Mode:
    Read-only source scan only.
    No file patch.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SEARCH_TERMS = [
    "Legacy BIRTH fallback",
    "fallback",
    "birth score present",
    "full evidence payload is not yet available",
    "survival_score",
    "master_survival_score",
    "score present",
    "campaign_score",
    "composite_score",
]

HIGH_RISK_TERMS = [
    "Legacy BIRTH fallback",
    "birth score present",
    "full evidence payload is not yet available",
    "master_survival_score",
    "survival_score",
]

SAFE_LABELS = [
    "DIAGNOSTIC_ONLY",
    "NOT_OPERATOR_CONTROL_CONFIRMATION",
    "NOT_D3D_AUTHORIZATION",
    "READ_ONLY",
]


def nearby_context(lines: list[str], line_number: int, radius: int = 6) -> str:
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    return "\n".join(f"{i:5}: {lines[i-1]}" for i in range(start, end + 1))


def classify_hit(line: str, context: str) -> str:
    lowered_line = line.lower()
    lowered_context = context.lower()

    if any(term.lower() in lowered_line for term in HIGH_RISK_TERMS):
        if all(label.lower() in lowered_context for label in SAFE_LABELS):
            return "LABELED_DIAGNOSTIC"
        return "NEEDS_QUARANTINE_REVIEW"

    if "fallback" in lowered_line:
        if all(label.lower() in lowered_context for label in SAFE_LABELS):
            return "LABELED_DIAGNOSTIC"
        return "FALLBACK_REVIEW"

    return "SCORE_REFERENCE_REVIEW"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="backend")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"FAIL: root not found: {root}")

    print("=" * 72)
    print("SIGMALYTIC V2 — LEGACY FALLBACK QUARANTINE AUDIT")
    print("MODE: READ-ONLY SOURCE SCAN")
    print("=" * 72)
    print(f"ROOT: {root}")

    hits: list[tuple[Path, int, str, str, str]] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
            continue

        text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()

        for idx, line in enumerate(lines, start=1):
            if any(term.lower() in line.lower() for term in SEARCH_TERMS):
                context = nearby_context(lines, idx)
                classification = classify_hit(line, context)
                hits.append((path, idx, line.strip(), classification, context))

    if not hits:
        print("PASS: no obvious legacy fallback or score-only transition hits found.")
        return 0

    print(f"TOTAL HITS: {len(hits)}")

    needs_review = [
        hit for hit in hits
        if hit[3] in {"NEEDS_QUARANTINE_REVIEW", "FALLBACK_REVIEW", "SCORE_REFERENCE_REVIEW"}
    ]

    for path, line_no, line, classification, context in hits:
        print("-" * 72)
        print(f"{classification}: {path}:{line_no}")
        print(f"LINE: {line}")
        print("CONTEXT:")
        print(context)

    print("=" * 72)

    if needs_review:
        print("FAIL: legacy fallback / score-reference hits require classification.")
        print("REQUIRED NEXT ACTION:")
        print("  classify each hit as diagnostic-only, quarantined, replaced, or removed.")
        print("  no fallback may confirm operator control.")
        print("  no fallback may authorize D3D.")
        print("  no score-only path may advance lifecycle state.")
        print("=" * 72)
        return 1

    print("PASS: all fallback hits appear labeled diagnostic-only.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
