#!/usr/bin/env python3
"""
Sigmalytic V2 Step 7A — Legacy fallback quarantine classification.

Purpose:
    Classify Step 7 fallback/score-reference hits into:
      1. true lifecycle score-dependency blockers,
      2. evidence metric outputs needing label,
      3. legacy scoreboard/snapshot references outside operator-control,
      4. harmless frontend/admin/demo fallbacks.

Mode:
    Read-only source scan plus local audit report write only.
    No production patch.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    category: str
    severity: str
    disposition: str
    text: str


def line_context(lines: list[str], line_number: int, radius: int = 4) -> str:
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    return "\n".join(f"{i:5}: {lines[i-1]}" for i in range(start, end + 1))


def classify(path: Path, line: str, context: str) -> tuple[str, str, str]:
    p = str(path).replace("\\", "/").lower()
    l = line.lower()
    c = context.lower()

    if p.endswith("backend/signal_birth_engine.py"):
        if (
            "birth_score" in c
            or "birth_eligible" in c
            or "survival_score >=" in c
            or "+ survival_score" in c
        ):
            return (
                "TRUE_LIFECYCLE_SCORE_DEPENDENCY",
                "BLOCKER",
                "Quarantine/replace before V2 completion: lifecycle birth eligibility still depends on score arithmetic.",
            )
        return (
            "SIGNAL_BIRTH_SCORE_FIELD_REVIEW",
            "REVIEW",
            "Classify as transitional diagnostic evidence only unless removed from lifecycle decision logic.",
        )

    if p.endswith("backend/research_engine/wyckoff_verdict_engine.py"):
        return (
            "WYCKOFF_EVIDENCE_METRIC_OUTPUT",
            "REVIEW",
            "Likely method evidence metric output; must be labeled non-confirming and not used as operator-control confirmation.",
        )

    if p.endswith("backend/scoreboard_service.py"):
        if "insert into scoreboard_signals" in c or "signal_type" in c:
            return (
                "LEGACY_SCOREBOARD_SIGNAL_PATH",
                "REVIEW",
                "Outside operator-control lifecycle, but must remain non-D3D, non-operator-control, and non-campaign-mutation.",
            )
        return (
            "LEGACY_SCOREBOARD_SCORE_REFERENCE",
            "LOW",
            "Scoreboard analytics/reference path; label as not operator-control evidence if touched later.",
        )

    if p.endswith("backend/sms_alerts.py"):
        return (
            "ALERT_SCORE_DISPLAY_REFERENCE",
            "REVIEW",
            "Alert display must remain diagnostic/read-only and non-confirming.",
        )

    if p.endswith("backend/snapshot_service.py"):
        if "fallback" in l or "fallback" in c:
            return (
                "ADMIN_REPORT_FALLBACK",
                "LOW",
                "Frontend/admin safety fallback, not campaign lifecycle; label diagnostic-only if edited.",
            )
        return (
            "SNAPSHOT_SCORE_REFERENCE",
            "LOW",
            "Snapshot/reporting score reference; not operator-control evidence unless used by lifecycle transition.",
        )

    if p.endswith("backend/supabase_isolation.py"):
        return (
            "DEMO_AUTH_FALLBACK",
            "LOW",
            "Demo user fallback; not campaign lifecycle. Separate security/product review, not operator-control evidence.",
        )

    if "fallback" in l:
        return (
            "UNCLASSIFIED_FALLBACK",
            "REVIEW",
            "Fallback requires manual classification: diagnostic-only, quarantined, replaced, or removed.",
        )

    return (
        "UNCLASSIFIED_SCORE_REFERENCE",
        "REVIEW",
        "Score reference requires manual classification to ensure it cannot confirm operator control or authorize D3D.",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="backend")
    parser.add_argument("--report", default="audit_step7_legacy_fallback_classification.json")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"FAIL: root not found: {root}")

    findings: list[Finding] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
            continue

        text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()

        for idx, line in enumerate(lines, start=1):
            if not any(term.lower() in line.lower() for term in SEARCH_TERMS):
                continue

            context = line_context(lines, idx)
            category, severity, disposition = classify(path, line, context)
            findings.append(
                Finding(
                    file=str(path),
                    line=idx,
                    category=category,
                    severity=severity,
                    disposition=disposition,
                    text=line.strip(),
                )
            )

    summary: dict[str, int] = {}
    severity_summary: dict[str, int] = {}

    for finding in findings:
        summary[finding.category] = summary.get(finding.category, 0) + 1
        severity_summary[finding.severity] = severity_summary.get(finding.severity, 0) + 1

    report = {
        "mode": "LOCAL_AUDIT_REPORT_ONLY_NO_PRODUCTION_PATCH",
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "does_not_authorize_d3d": True,
            "does_not_mutate_campaigns": True,
            "does_not_confirm_operator_control": True,
            "does_not_create_trade_signal": True,
            "does_not_touch_stripe": True
        },
        "summary_by_category": summary,
        "summary_by_severity": severity_summary,
        "findings": [asdict(finding) for finding in findings]
    }

    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 7A LEGACY FALLBACK CLASSIFICATION")
    print("MODE: LOCAL AUDIT REPORT ONLY / NO PRODUCTION PATCH")
    print("=" * 72)
    print(f"Findings classified: {len(findings)}")
    print(f"Report written: {args.report}")

    print("\nSUMMARY BY SEVERITY")
    for severity in ["BLOCKER", "REVIEW", "LOW"]:
        print(f"{severity}: {severity_summary.get(severity, 0)}")

    print("\nSUMMARY BY CATEGORY")
    for category, count in sorted(summary.items()):
        print(f"{category}: {count}")

    blockers = [f for f in findings if f.severity == "BLOCKER"]
    reviews = [f for f in findings if f.severity == "REVIEW"]

    if blockers:
        print("\nBLOCKERS")
        for finding in blockers:
            print(f"- {finding.file}:{finding.line} [{finding.category}] {finding.text}")
            print(f"  {finding.disposition}")

    if reviews:
        print("\nREVIEW ITEMS")
        for finding in reviews[:25]:
            print(f"- {finding.file}:{finding.line} [{finding.category}] {finding.text}")

    print("=" * 72)

    if blockers:
        print("FAIL: Step 7A found true lifecycle score-dependency blockers.")
        print("NEXT: quarantine/replace these before lifecycle law can be finalized.")
        print("=" * 72)
        return 2

    if reviews:
        print("WARN: Step 7A found review items but no blocking lifecycle dependency.")
        print("=" * 72)
        return 1

    print("PASS: Step 7A found no blockers or review items.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
