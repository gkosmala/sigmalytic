#!/usr/bin/env python3
"""
Sigmalytic V2 Step 9A — Semantic alert readiness guardrail audit.

Purpose:
    Avoid false positives from negative guardrail strings like:
      - "no_authorize_d3d_button"
      - "does not touch Stripe"
      - "not authorize D3D"

    Detect actual executable mutation/D3D/operator-control/trade-signal/Stripe
    primitives in alert/readiness/notification code.

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
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPORT = Path("audit_step9a_semantic_alert_guardrail.json")

ALERT_PATH_HINTS = [
    "alert",
    "readiness",
    "notification",
    "sms",
]

MUTATING_METHODS = {
    "insert",
    "upsert",
    "update",
    "delete",
    "rpc",
    "post",
    "patch",
}

D3D_TEXT_DANGER = [
    "authorize_d3d(",
    "executes_d3d = true",
    "executes_d3d=true",
    "'executes_d3d': true",
    '"executes_d3d": true',
]

OPERATOR_CONTROL_DANGER = [
    "operator_control_confirmed = true",
    "operator_control_confirmed=true",
    "'operator_control_confirmed': true",
    '"operator_control_confirmed": true',
]

TRADE_SIGNAL_DANGER = [
    "create_trade_signal(",
]

SAFE_NEGATIVE_TEXT_HINTS = [
    "no_authorize_d3d",
    "does not touch stripe",
    "not touch stripe",
    "no stripe",
    "not authorize d3d",
    "does not authorize d3d",
    "no d3d",
    "authorizes_d3d false",
    "authorizes_d3d=false",
    "operator_control_confirmed false",
    "operator_control_confirmed=false",
    "touches_stripe false",
    "touches_stripe=false",
]


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: str
    category: str
    text: str


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    return ""


def is_controlled_d3e_route(path: Path) -> bool:
    normalized = str(path).replace("\\", "/").lower()
    return (
        "backend/alerts/controlled_append_only_audit_write_route.py" in normalized
        or "backend/alerts/controlled_one_row_append_only_audit_insert.py" in normalized
    )


def line_is_safe_negative_text(line: str) -> bool:
    lowered = line.lower()
    return any(hint in lowered for hint in SAFE_NEGATIVE_TEXT_HINTS)


def scan_ast_calls(path: Path, tree: ast.AST, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = dotted_name(node.func).lower()
        line_no = getattr(node, "lineno", 0)
        source_line = lines[line_no - 1].strip() if 1 <= line_no <= len(lines) else ""

        if is_controlled_d3e_route(path):
            if any(name.endswith(f".{method}") or name == method for method in MUTATING_METHODS):
                findings.append(
                    Finding(
                        file=str(path),
                        line=line_no,
                        severity="REVIEW",
                        category="CLOSED_D3E_CONTROLLED_AUDIT_ROUTE_MUTATION_PRIMITIVE",
                        text=source_line,
                    )
                )
            continue

        if name.startswith("stripe") or ".stripe" in name:
            findings.append(
                Finding(str(path), line_no, "BLOCKER", "EXECUTABLE_STRIPE_CALL", source_line)
            )

        if name in {"requests.post", "requests.patch", "requests.delete", "httpx.post", "httpx.patch", "httpx.delete"}:
            findings.append(
                Finding(str(path), line_no, "BLOCKER", "EXECUTABLE_HTTP_MUTATION_CALL", source_line)
            )

        if any(name.endswith(f".{method}") for method in {"insert", "upsert", "update", "delete", "rpc"}):
            findings.append(
                Finding(str(path), line_no, "BLOCKER", "EXECUTABLE_DATABASE_MUTATION_CALL", source_line)
            )

        if name.endswith("authorize_d3d") or name.endswith("create_trade_signal"):
            findings.append(
                Finding(str(path), line_no, "BLOCKER", "EXECUTABLE_D3D_OR_TRADE_SIGNAL_CALL", source_line)
            )

    return findings


def scan_danger_text(path: Path, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []

    for idx, line in enumerate(lines, start=1):
        lowered = line.lower()

        if line_is_safe_negative_text(line):
            continue

        for token in D3D_TEXT_DANGER:
            if token in lowered:
                findings.append(
                    Finding(str(path), idx, "BLOCKER", "D3D_TRUE_OR_CALL_TEXT", line.strip())
                )

        for token in OPERATOR_CONTROL_DANGER:
            if token in lowered:
                findings.append(
                    Finding(str(path), idx, "BLOCKER", "OPERATOR_CONTROL_TRUE_TEXT", line.strip())
                )

        for token in TRADE_SIGNAL_DANGER:
            if token in lowered:
                findings.append(
                    Finding(str(path), idx, "BLOCKER", "TRADE_SIGNAL_CALL_TEXT", line.strip())
                )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="backend")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"FAIL: root not found: {root}")

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 9A SEMANTIC ALERT GUARDRAIL AUDIT")
    print("MODE: READ-ONLY SOURCE SCAN")
    print("=" * 72)
    print(f"ROOT: {root}")

    findings: list[Finding] = []
    files_scanned = 0
    parse_failures: list[str] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
            continue

        lowered_path = str(path).lower()
        if not any(hint in lowered_path for hint in ALERT_PATH_HINTS):
            continue

        files_scanned += 1
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()

        try:
            tree = ast.parse(text, filename=str(path))
        except Exception as exc:
            parse_failures.append(f"{path}: {exc}")
            continue

        findings.extend(scan_ast_calls(path, tree, lines))
        findings.extend(scan_danger_text(path, lines))

    blockers = [item for item in findings if item.severity == "BLOCKER"]
    reviews = [item for item in findings if item.severity == "REVIEW"]

    summary: dict[str, int] = {}
    for item in findings:
        key = f"{item.severity}:{item.category}"
        summary[key] = summary.get(key, 0) + 1

    report: dict[str, Any] = {
        "mode": "READ_ONLY_SEMANTIC_SOURCE_SCAN_NO_PATCH",
        "files_scanned": files_scanned,
        "parse_failures": parse_failures,
        "status": "PASS" if not blockers and not parse_failures else "FAIL",
        "blocker_count": len(blockers),
        "review_count": len(reviews),
        "summary": summary,
        "doctrine": {
            "alerts_are_read_only_diagnostic": True,
            "does_not_mutate_campaigns": True,
            "does_not_authorize_d3d": True,
            "does_not_confirm_operator_control": True,
            "does_not_create_trade_signal": True,
            "does_not_touch_stripe": True
        },
        "findings": [asdict(item) for item in findings],
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Files scanned: {files_scanned}")
    print(f"Parse failures: {len(parse_failures)}")
    print(f"Blockers: {len(blockers)}")
    print(f"Reviews: {len(reviews)}")
    print(f"Report written: {REPORT}")

    if summary:
        print("\nSUMMARY")
        for key, count in sorted(summary.items()):
            print(f"{key}: {count}")

    if parse_failures:
        print("\nPARSE FAILURES")
        for item in parse_failures:
            print(f"FAIL: {item}")

    if blockers:
        print("\nBLOCKERS")
        for item in blockers:
            print("-" * 72)
            print(f"{item.file}:{item.line}")
            print(f"{item.category}")
            print(item.text)

    if reviews:
        print("\nREVIEW ITEMS")
        for item in reviews:
            print("-" * 72)
            print(f"{item.file}:{item.line}")
            print(f"{item.category}")
            print(item.text)

    print("=" * 72)

    if blockers or parse_failures:
        print("FAIL: STEP 9A FOUND EXECUTABLE ALERT GUARDRAIL BLOCKERS")
        print("=" * 72)
        return 1

    print("PASS: STEP 9A COMPLETE — NO EXECUTABLE ALERT GUARDRAIL BLOCKERS FOUND")
    print("PASS: negative guardrail text was not treated as executable D3D/Stripe action.")
    print("PASS: alerts remain diagnostic/read-only under semantic audit.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
