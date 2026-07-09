#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

TARGET = Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py")
REPORT = Path("audit_step66_wire_persisted_universe_tables_into_reader.json")
READINESS = Path("v2_readiness.json")

REQUIRED_TABLES = [
    "campaign_universe_symbols",
    "campaign_universe_snapshots",
]

LEGACY_UNIVERSE_CANDIDATES = [
    "alpaca_universe",
    "live_universe",
    "universe",
    "symbols",
]

MARKER = "STEP66_PERSISTED_UNIVERSE_TABLES_WIRED_GET_ONLY"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def has_forbidden_write_calls(source: str) -> list[str]:
    failures: list[str] = []
    tree = ast.parse(source)

    forbidden_attrs = {
        "insert",
        "upsert",
        "update",
        "delete",
        "rpc",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden_attrs:
                failures.append(f"forbidden method call detected: .{node.func.attr}(...) at line {node.lineno}")

    return failures


def patch_reader(source: str) -> tuple[str, list[str]]:
    notes: list[str] = []

    if all(table in source for table in REQUIRED_TABLES) and MARKER in source:
        notes.append("reader already contains Step 66 persisted universe table wiring")
        return source, notes

    lines = source.splitlines()

    if MARKER not in source:
        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1

        lines.insert(insert_at, f"# {MARKER}")
        lines.insert(insert_at + 1, "# Persisted universe source tables are read by GET/select only.")
        lines.insert(insert_at + 2, "# Bars-symbol coverage remains diagnostic only and is not promoted into a universe source.")
        notes.append("inserted Step 66 marker")

    source_with_marker = "\n".join(lines) + "\n"

    if all(table in source_with_marker for table in REQUIRED_TABLES):
        return source_with_marker, notes

    lines = source_with_marker.splitlines()

    candidate_line_index = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for candidate in LEGACY_UNIVERSE_CANDIDATES:
            if f'"{candidate}"' in line or f"'{candidate}'" in line:
                candidate_line_index = i
                break

        if candidate_line_index is not None:
            break

    if candidate_line_index is None:
        raise RuntimeError(
            "could not locate an existing universe candidate list in the reader; "
            "manual patch required before continuing"
        )

    candidate_line = lines[candidate_line_index]
    indent = candidate_line[: len(candidate_line) - len(candidate_line.lstrip())]

    quote = '"'
    if "'" in candidate_line and '"' not in candidate_line:
        quote = "'"

    insert_lines = [
        f"{indent}{quote}campaign_universe_symbols{quote},",
        f"{indent}{quote}campaign_universe_snapshots{quote},",
    ]

    for insert_line in reversed(insert_lines):
        if insert_line.strip().strip(",").strip("'").strip('"') not in "\n".join(lines):
            lines.insert(candidate_line_index, insert_line)

    notes.append("inserted persisted universe table candidates ahead of legacy universe candidates")

    patched = "\n".join(lines) + "\n"

    if not all(table in patched for table in REQUIRED_TABLES):
        raise RuntimeError("patch completed but required persisted universe table names are still missing")

    return patched, notes


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 66 WIRE PERSISTED UNIVERSE TABLES INTO READER")
    print("MODE: LOCAL SOURCE PATCH ONLY / NO DB CALL / NO MIGRATION APPLY / NO WRITE")
    print("=" * 72)

    failures: list[str] = []
    notes: list[str] = []

    if not TARGET.exists():
        failures.append(f"missing target file: {TARGET}")

    readiness = read_json(READINESS)

    required_readiness_false = [
        "campaign_pipeline_validated",
        "d3d_authorized",
        "operator_control_confirmed_by_score",
        "campaign_mutation_without_d3d_law",
    ]

    for key in required_readiness_false:
        if readiness.get(key) is not False:
            failures.append(f"readiness field must remain false: {key}")
        else:
            print(f"PASS: readiness {key}=False")

    if not failures:
        original = TARGET.read_text(encoding="utf-8-sig")
        backup = TARGET.with_suffix(TARGET.suffix + ".step66.bak")
        backup.write_text(original, encoding="utf-8")

        try:
            patched, patch_notes = patch_reader(original)
            notes.extend(patch_notes)

            ast.parse(patched)
            write_failures = has_forbidden_write_calls(patched)

            if write_failures:
                failures.extend(write_failures)
                TARGET.write_text(original, encoding="utf-8")
            else:
                TARGET.write_text(patched, encoding="utf-8")
                print("PASS: reader patched locally")
                for note in notes:
                    print("NOTE:", note)

        except Exception as exc:
            TARGET.write_text(original, encoding="utf-8")
            failures.append(str(exc))

    if TARGET.exists():
        current = TARGET.read_text(encoding="utf-8-sig")

        for table in REQUIRED_TABLES:
            if table not in current:
                failures.append(f"reader missing required persisted universe table: {table}")
            else:
                print("PASS: reader contains table candidate:", table)

        if MARKER not in current:
            failures.append("reader missing Step 66 marker")
        else:
            print("PASS: reader contains Step 66 marker")

        try:
            ast.parse(current)
            print("PASS: reader syntax clean by AST parse")
        except SyntaxError as exc:
            failures.append(f"reader syntax error: {exc}")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_SOURCE_PATCH_ONLY_NO_DB_CALL_NO_MIGRATION_APPLY_NO_WRITE",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "notes": notes,
        "target": str(TARGET),
        "required_tables": REQUIRED_TABLES,
        "readiness": {
            "mutated": False,
            "campaign_pipeline_validated": readiness.get("campaign_pipeline_validated"),
            "campaign_pipeline_validated_can_advance_now": False,
            "billing_remains_blocked": True,
        },
        "doctrine": {
            "get_only_reader_patch": True,
            "no_database_call": True,
            "no_migration_apply": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_nightly_run": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
        "next_step": "local verification, commit/tag/push, deploy, then live GET verification",
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if failures:
        print("FAIL: STEP 66 WIRING FAILED")
        for failure in failures:
            print("FAIL:", failure)
        print("REPORT:", REPORT)
        return 1

    print("=" * 72)
    print("PASS: STEP 66 COMPLETE — PERSISTED UNIVERSE TABLES WIRED INTO GET-ONLY READER LOCALLY")
    print("REPORT:", REPORT)
    print("STATUS: campaign_pipeline_validated remains false; billing remains blocked.")
    print("NEXT: local verification, commit/tag/push, deploy, then live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
