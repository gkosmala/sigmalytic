#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

REPORT = Path("audit_step35_pipeline_production_coverage_source_locator.json")

TARGET_FILES = [
    Path("backend/campaign_engine/nightly_campaign_pipeline.py"),
    Path("backend/campaign_engine/campaign_discovery_engine.py"),
    Path("backend/campaign_engine/campaign_store.py"),
    Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py"),
    Path("backend/campaign_pipeline_validation_api.py"),
    Path("backend/campaign_api.py"),
    Path("backend/main.py"),
]

COVERAGE_TERMS = {
    "universe_count": ["universe_count", "universe", "alpaca_universe", "live universe"],
    "bars_symbols_count": ["bars_symbols", "alpaca_bars_symbols", "bars_symbols_count", "records_built"],
    "symbols_missing_bars": ["missing_bars", "symbols_missing_bars", "missing symbols", "no bars"],
    "record_min_bars": ["record_min_bars", "min_bars", "record_min", "minimum bars"],
    "pagination_complete": ["pagination_complete", "pagination", "next_page", "page_token", "stopped pagination"],
    "schema_payload_alignment": ["schema_payload", "payload", "schema", "campaigns"],
    "supabase_read_path": ["select(", ".select", "supabase", "from_("],
}

WRITE_TERMS = [
    ".insert(",
    ".upsert(",
    ".update(",
    ".delete(",
    ".rpc(",
    "run_full_nightly(",
    "execute_d3d(",
    "authorize_d3d(",
    "stripe.",
]


def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def syntax_check(path: Path) -> dict[str, Any]:
    text = read(path)
    if not text:
        return {"exists": False, "ok": False, "error": "missing or empty"}

    try:
        ast.parse(text, filename=str(path))
        return {"exists": True, "ok": True, "error": None}
    except SyntaxError as exc:
        return {"exists": True, "ok": False, "error": f"{exc.msg} line {exc.lineno}"}


def line_hits(path: Path, terms: list[str]) -> list[dict[str, Any]]:
    text = read(path)
    hits: list[dict[str, Any]] = []

    for idx, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        for term in terms:
            if term.lower() in lower:
                hits.append({
                    "path": str(path),
                    "line": idx,
                    "term": term,
                    "text": line.strip()[:240],
                })

    return hits


def extract_functions(path: Path) -> list[dict[str, Any]]:
    text = read(path)
    if not text:
        return []

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    funcs: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({
                "path": str(path),
                "name": node.name,
                "line": getattr(node, "lineno", None),
            })

    return funcs


def classify_candidate_read_sources(all_hits: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for path in TARGET_FILES:
        path_text = str(path)
        hits_for_path = []

        for term_group, hits in all_hits.items():
            path_hits = [hit for hit in hits if hit["path"] == path_text]
            if path_hits:
                hits_for_path.append(term_group)

        if hits_for_path:
            candidates.append({
                "path": path_text,
                "coverage_groups_present": sorted(set(hits_for_path)),
                "coverage_group_count": len(set(hits_for_path)),
            })

    candidates.sort(key=lambda item: item["coverage_group_count"], reverse=True)
    return candidates


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 35 PRODUCTION COVERAGE SOURCE LOCATOR")
    print("MODE: LOCAL SOURCE AUDIT ONLY / NO DB CALL / NO DEPLOY / NO WRITE")
    print("=" * 72)

    failures: list[str] = []

    syntax_results = {str(path): syntax_check(path) for path in TARGET_FILES}

    for path, result in syntax_results.items():
        if result["ok"]:
            print("PASS: syntax clean:", path)
        else:
            failures.append(f"syntax/missing issue: {path}: {result['error']}")

    all_hits: dict[str, list[dict[str, Any]]] = {}

    for group, terms in COVERAGE_TERMS.items():
        hits: list[dict[str, Any]] = []
        for path in TARGET_FILES:
            hits.extend(line_hits(path, terms))
        all_hits[group] = hits
        print(f"GROUP {group}: hits={len(hits)}")

    write_hits: list[dict[str, Any]] = []
    for path in TARGET_FILES:
        write_hits.extend(line_hits(path, WRITE_TERMS))

    functions: list[dict[str, Any]] = []
    for path in TARGET_FILES:
        functions.extend(extract_functions(path))

    relevant_functions = [
        func for func in functions
        if any(token in func["name"].lower() for token in [
            "snapshot",
            "coverage",
            "pipeline",
            "campaign",
            "store",
            "read",
            "fetch",
            "select",
            "build",
        ])
    ]

    candidate_sources = classify_candidate_read_sources(all_hits)

    required_groups = [
        "universe_count",
        "bars_symbols_count",
        "symbols_missing_bars",
        "record_min_bars",
        "pagination_complete",
        "schema_payload_alignment",
    ]

    missing_groups = [group for group in required_groups if not all_hits.get(group)]

    if missing_groups:
        print("WARN: missing source evidence groups:", ", ".join(missing_groups))
    else:
        print("PASS: all required production coverage source groups located in source text")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_SOURCE_LOCATOR_ONLY_NO_DB_CALL_NO_DEPLOY_NO_WRITE",
        "failures": failures,
        "syntax_results": syntax_results,
        "coverage_hits": all_hits,
        "candidate_sources": candidate_sources,
        "relevant_functions": relevant_functions,
        "write_term_hits_classification": {
            "note": (
                "These are source inventory hits only. Step 35 does not execute any code path, "
                "does not call Supabase, and does not mutate campaigns."
            ),
            "hits": write_hits,
        },
        "next_step": {
            "recommended": "Add a GET-only coverage reader that uses only safe read/select paths and returns real live coverage counts without running nightly or writing Supabase.",
            "campaign_pipeline_validated_can_advance_now": False,
        },
        "doctrine": {
            "local_source_audit_only": True,
            "no_db_call": True,
            "no_deploy": True,
            "no_nightly_run": True,
            "no_alpaca_call": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Report written:", REPORT)

    print("\nTOP CANDIDATE SOURCES")
    for item in candidate_sources[:8]:
        print(
            "CANDIDATE:",
            item["path"],
            "groups=" + ",".join(item["coverage_groups_present"]),
        )

    print("\nRELEVANT FUNCTIONS")
    for func in relevant_functions[:80]:
        print(f"FUNC: {func['path']}:{func['line']} {func['name']}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 35 PRODUCTION COVERAGE SOURCE LOCATOR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 35 COMPLETE — PRODUCTION COVERAGE SOURCE LOCATOR PASSED")
    print("PASS: no DB call, no nightly run, no Supabase write, no campaign mutation, no D3D, no trade signal, no Stripe.")
    print("NEXT: add GET-only production coverage reader.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
