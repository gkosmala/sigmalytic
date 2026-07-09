#!/usr/bin/env python3
"""
Sigmalytic V2 Step 11 — Documentation completeness audit.

Mode:
    Local documentation audit only.
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
from pathlib import Path
from typing import Any

REQUIRED_DOCS = {
    "architecture": [
        "architecture",
        "live surface",
        "sigmalytic_app_today",
        "main-content",
    ],
    "doctrine": [
        "operator control is evidence",
        "not a score",
        "d3d",
        "tested supply exhaustion",
        "active demand",
        "structurally meaningful location",
        "absence of contrary failure",
    ],
    "deployment": [
        "render",
        "clear build cache",
        "post-deploy verification",
        "rollback",
    ],
    "regression": [
        "smoke test",
        "no-drift",
        "buttons",
        "dash layout",
        "dash dependencies",
    ],
    "rollback": [
        "f431a61",
        "preserve",
        "restore",
        "stable-v2-d3f1b-live-ui-unfreeze-remove-global-panel-mount-read-only-2026-07-08",
    ],
    "operator_control": [
        "tested supply exhaustion evidence",
        "active demand validation evidence",
        "support validation evidence",
        "structural location evidence",
        "absence of contrary failure evidence",
    ],
    "alerts": [
        "alerts are diagnostic",
        "read-only",
        "cannot mutate campaigns",
        "cannot authorize d3d",
        "cannot create trade signals",
    ],
    "billing": [
        "stripe",
        "billing remain last",
    ],
}


def collect_text(root: Path) -> str:
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".rst"}:
            continue
        parts.append(path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(parts).lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--report", default="audit_step11_documentation_completeness.json")
    args = parser.parse_args()

    root = Path(args.docs)
    report_path = Path(args.report)

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 11 DOCUMENTATION COMPLETENESS AUDIT")
    print("MODE: LOCAL DOC AUDIT / READ-ONLY")
    print("=" * 72)

    failures: list[str] = []
    passes: list[str] = []

    if not root.exists():
        failures.append(f"docs folder does not exist: {root}")
        all_text = ""
    else:
        all_text = collect_text(root)

    if not all_text.strip():
        failures.append("no readable documentation text found")

    for category, terms in REQUIRED_DOCS.items():
        missing = [term for term in terms if term.lower() not in all_text]
        if missing:
            failures.append(f"{category}: missing terms {missing}")
        else:
            passes.append(category)
            print(f"PASS: documentation category covered: {category}")

    report: dict[str, Any] = {
        "mode": "LOCAL_DOC_AUDIT_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "docs_root": str(root),
        "passed_categories": passes,
        "failures": failures,
        "doctrine": {
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written: {report_path}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(f"FAIL: {failure}")
        print("=" * 72)
        print("FAIL: STEP 11 DOCUMENTATION COMPLETENESS AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 11 COMPLETE — DOCUMENTATION COMPLETENESS AUDIT PASSED")
    print("PASS: architecture, doctrine, deployment, regression, rollback, alerts, and billing-last rules are documented.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
