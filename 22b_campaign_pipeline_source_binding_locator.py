#!/usr/bin/env python3
"""
Sigmalytic V2 Step 22B — Campaign Pipeline Source Binding Locator.

Purpose:
    Broaden the too-narrow Step 22 source audit by locating where universe,
    Alpaca/bar fetching, Supabase persistence, schema payload, and legacy
    fallback references actually live.

Mode:
    Local read-only source locator only.
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

ROOTS = [Path("backend")]
REPORT = Path("audit_step22b_campaign_pipeline_source_binding_locator.json")

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

TERM_GROUPS = {
    "universe_loading": [
        "universe",
        "alpaca",
        "symbols",
    ],
    "bar_fetching": [
        "alpaca",
        "bars",
    ],
    "supabase_persistence": [
        "supabase",
        "insert",
        "upsert",
        "write",
    ],
    "schema_payload_alignment": [
        "payload",
        "schema",
        "campaigns",
    ],
    "pagination": [
        "pagination",
        "page",
        "next_page",
        "limit",
    ],
    "legacy_fallback": [
        "legacy birth fallback",
        "birth score present",
        "full evidence payload is not yet available",
    ],
}

PIPELINE_HINTS = [
    "campaign",
    "nightly",
    "pipeline",
    "alpaca",
    "supabase",
    "universe",
    "bars",
    "state",
    "store",
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


def line_hits(path: Path, text: str, terms: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        lower = line.lower()
        matched = [term for term in terms if term.lower() in lower]
        if matched:
            hits.append({
                "path": str(path),
                "line": idx,
                "matched": matched,
                "text": line.strip(),
            })
    return hits


def file_has_pipeline_hint(path: Path, text: str) -> bool:
    target = f"{path.as_posix()} {text[:5000]}".lower()
    return any(hint in target for hint in PIPELINE_HINTS)


def import_summary(path: Path, text: str) -> list[str]:
    imports: list[str] = []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}".strip("."))
    return imports


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 22B PIPELINE SOURCE BINDING LOCATOR")
    print("MODE: LOCAL READ-ONLY LOCATOR / NO NIGHTLY RUN / NO WRITE")
    print("=" * 72)

    files: list[Path] = []
    for root in ROOTS:
        if root.exists():
            files.extend(path for path in root.rglob("*.py") if should_scan(path))

    files = sorted(files)

    group_hits: dict[str, list[dict[str, Any]]] = {group: [] for group in TERM_GROUPS}
    pipeline_related_files: list[str] = []
    syntax_failures: list[dict[str, Any]] = []
    imports_by_file: dict[str, list[str]] = {}

    for path in files:
        text = safe_read(path)

        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            syntax_failures.append({
                "path": str(path),
                "error": f"{exc.msg} at line {exc.lineno}",
            })

        if file_has_pipeline_hint(path, text):
            pipeline_related_files.append(str(path))
            imports_by_file[str(path)] = import_summary(path, text)

        for group, terms in TERM_GROUPS.items():
            hits = line_hits(path, text, terms)
            group_hits[group].extend(hits)

    missing_groups = [
        group for group, hits in group_hits.items()
        if group != "legacy_fallback" and not hits
    ]

    legacy_hits = group_hits["legacy_fallback"]

    report = {
        "mode": "LOCAL_READ_ONLY_SOURCE_LOCATOR_NO_NIGHTLY_RUN_NO_WRITE",
        "status": "PASS" if not missing_groups and not syntax_failures else "FAIL",
        "summary": {
            "files_scanned": len(files),
            "pipeline_related_files": len(pipeline_related_files),
            "syntax_failures": len(syntax_failures),
            "missing_groups": missing_groups,
            "legacy_fallback_hits": len(legacy_hits),
        },
        "missing_groups": missing_groups,
        "syntax_failures": syntax_failures,
        "pipeline_related_files": pipeline_related_files[:300],
        "imports_by_pipeline_related_file": imports_by_file,
        "group_hits_preview": {
            group: hits[:80]
            for group, hits in group_hits.items()
        },
        "legacy_fallback_hits": legacy_hits,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "Source bindings located only. A production-read-only coverage snapshot is still required before campaign_pipeline_validated can become true.",
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

    print(f"Files scanned: {len(files)}")
    print(f"Pipeline-related files: {len(pipeline_related_files)}")
    print(f"Syntax failures: {len(syntax_failures)}")
    print(f"Missing groups: {missing_groups}")
    print(f"Legacy fallback hits: {len(legacy_hits)}")
    print(f"Report written: {REPORT}")

    print("\nGROUP HIT COUNTS")
    for group, hits in group_hits.items():
        print(f"{group}: {len(hits)}")

    print("\nTOP SOURCE BINDING HITS")
    for group in ["universe_loading", "bar_fetching", "supabase_persistence", "schema_payload_alignment", "pagination"]:
        print(f"\n{group}")
        for hit in group_hits[group][:20]:
            print(f"HIT: {hit['path']}:{hit['line']} — {hit['text']}")

    if legacy_hits:
        print("\nLEGACY FALLBACK HITS")
        for hit in legacy_hits[:40]:
            print(f"LEGACY: {hit['path']}:{hit['line']} — {hit['text']}")

    if syntax_failures:
        print("\nSYNTAX FAILURES")
        for failure in syntax_failures:
            print(f"FAIL: {failure['path']} — {failure['error']}")

    if missing_groups or syntax_failures:
        print("=" * 72)
        print("FAIL: STEP 22B SOURCE BINDING LOCATOR FAILED")
        print("SEND FULL OUTPUT")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 22B COMPLETE — PIPELINE SOURCE BINDINGS LOCATED")
    print("PASS: campaign_pipeline_validated remains false pending production-read-only coverage snapshot.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
