#!/usr/bin/env python3
"""
Sigmalytic V2 Step 9 — Alert readiness guardrail audit.

Purpose:
    Confirm alerts/readiness/notification code remains diagnostic/read-only and
    cannot mutate campaigns, authorize D3D, confirm operator control, create trade
    signals, or touch Stripe.

Mode:
    Read-only source scan.
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
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ALERT_PATH_HINTS = [
    "alert",
    "readiness",
    "notification",
    "sms",
]

FORBIDDEN_PRIMITIVES = [
    ".insert(",
    ".upsert(",
    ".update(",
    ".delete(",
    ".rpc(",
    "requests.post",
    "requests.patch",
    "requests.delete",
    "httpx.post",
    "httpx.patch",
    "httpx.delete",
    "authorize_d3d",
    "executes_d3d=True",
    "operator_control_confirmed=True",
    "create_trade_signal",
    "stripe.",
]

CONTROLLED_D3E_CLOSED_ROUTE_HINTS = [
    "controlled_append_only_audit_write_route.py",
    "controlled_one_row_append_only_audit_insert.py",
]

REPORT = Path("audit_step9_alert_readiness_guardrail.json")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    primitive: str
    severity: str
    classification: str
    text: str


def classify(path: Path, primitive: str, line: str) -> tuple[str, str]:
    normalized = str(path).replace("\\", "/").lower()
    lowered = line.lower()

    if any(hint in normalized for hint in CONTROLLED_D3E_CLOSED_ROUTE_HINTS):
        return (
            "REVIEW",
            "CLOSED_D3E_CONTROLLED_APPEND_ONLY_AUDIT_ROUTE_NOT_ALERT_READINESS",
        )

    if "stripe." in primitive.lower():
        return ("BLOCKER", "STRIPE_PRIMITIVE_IN_ALERT_PATH")

    if "authorize_d3d" in primitive.lower() or "executes_d3d=true" in primitive.lower():
        return ("BLOCKER", "D3D_PRIMITIVE_IN_ALERT_PATH")

    if "operator_control_confirmed=true" in primitive.lower():
        return ("BLOCKER", "OPERATOR_CONTROL_CONFIRMATION_IN_ALERT_PATH")

    if "create_trade_signal" in primitive.lower():
        return ("BLOCKER", "TRADE_SIGNAL_CREATION_IN_ALERT_PATH")

    if any(token in primitive.lower() for token in [".insert(", ".upsert(", ".update(", ".delete(", ".rpc("]):
        if "read_only" in lowered or "diagnostic" in lowered:
            return ("REVIEW", "MUTATION_PRIMITIVE_TEXT_IN_DIAGNOSTIC_CONTEXT")
        return ("BLOCKER", "DATABASE_MUTATION_PRIMITIVE_IN_ALERT_PATH")

    if any(token in primitive.lower() for token in ["requests.post", "requests.patch", "requests.delete", "httpx.post", "httpx.patch", "httpx.delete"]):
        return ("BLOCKER", "HTTP_MUTATION_PRIMITIVE_IN_ALERT_PATH")

    return ("REVIEW", "UNCLASSIFIED_FORBIDDEN_PRIMITIVE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="backend")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"FAIL: root not found: {root}")

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 9 ALERT READINESS GUARDRAIL AUDIT")
    print("MODE: READ-ONLY SOURCE SCAN")
    print("=" * 72)
    print(f"ROOT: {root}")

    findings: list[Finding] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
            continue

        lowered_path = str(path).lower()
        if not any(hint in lowered_path for hint in ALERT_PATH_HINTS):
            continue

        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for idx, line in enumerate(text.splitlines(), start=1):
            lowered_line = line.lower()
            for primitive in FORBIDDEN_PRIMITIVES:
                if primitive.lower() in lowered_line:
                    severity, classification = classify(path, primitive, line)
                    findings.append(
                        Finding(
                            file=str(path),
                            line=idx,
                            primitive=primitive,
                            severity=severity,
                            classification=classification,
                            text=line.strip(),
                        )
                    )

    summary: dict[str, int] = {}
    for finding in findings:
        key = f"{finding.severity}:{finding.classification}"
        summary[key] = summary.get(key, 0) + 1

    blockers = [finding for finding in findings if finding.severity == "BLOCKER"]
    reviews = [finding for finding in findings if finding.severity == "REVIEW"]

    report = {
        "mode": "READ_ONLY_SOURCE_SCAN_NO_PATCH",
        "status": "PASS" if not blockers else "FAIL",
        "summary": summary,
        "blocker_count": len(blockers),
        "review_count": len(reviews),
        "doctrine": {
            "alerts_are_read_only_diagnostic": True,
            "does_not_mutate_campaigns": True,
            "does_not_authorize_d3d": True,
            "does_not_confirm_operator_control": True,
            "does_not_create_trade_signal": True,
            "does_not_touch_stripe": True
        },
        "findings": [asdict(finding) for finding in findings],
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Findings: {len(findings)}")
    print(f"Blockers: {len(blockers)}")
    print(f"Reviews: {len(reviews)}")
    print(f"Report written: {REPORT}")

    if summary:
        print("\nSUMMARY")
        for key, count in sorted(summary.items()):
            print(f"{key}: {count}")

    if blockers:
        print("\nBLOCKERS")
        for finding in blockers:
            print("-" * 72)
            print(f"{finding.file}:{finding.line}")
            print(f"Primitive: {finding.primitive}")
            print(f"Classification: {finding.classification}")
            print(f"Line: {finding.text}")

        print("=" * 72)
        print("FAIL: alert/readiness guardrail blockers found.")
        print("NEXT: quarantine or remove blocker primitives before alerts can be considered safe.")
        print("=" * 72)
        return 1

    if reviews:
        print("\nREVIEW ITEMS")
        for finding in reviews:
            print("-" * 72)
            print(f"{finding.file}:{finding.line}")
            print(f"Primitive: {finding.primitive}")
            print(f"Classification: {finding.classification}")
            print(f"Line: {finding.text}")

    print("=" * 72)
    print("PASS: STEP 9 COMPLETE — NO ALERT READINESS BLOCKERS FOUND")
    print("PASS: alerts remain diagnostic/read-only under this audit.")
    print("PASS: no D3D/operator-control/trade-signal/Stripe blocker found.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
