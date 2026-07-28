#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step48_read_only_universe_source_locator.json")

READINESS = Path("v2_readiness.json")

SCAN_PATHS = [
    Path("backend/campaign_engine/nightly_campaign_pipeline.py"),
    Path("backend/campaign_engine/campaign_discovery_engine.py"),
    Path("backend/campaign_engine/campaign_store.py"),
    Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py"),
    Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py"),
    Path("backend/campaign_api.py"),
    Path("backend/campaign_pipeline_validation_api.py"),
    Path("backend/main.py"),
]

UNIVERSE_TERMS = [
    "universe",
    "alpaca_universe",
    "live_universe",
    "load_universe",
    "get_universe",
    "fetch_universe",
    "symbols",
    "asset",
    "tradable",
    "active",
    "alpaca",
]

CALL_RISK_TERMS = [
    "insert",
    "upsert",
    "update",
    "delete",
    "rpc",
    "commit",
    "execute",
    "run_full_nightly",
    "write",
    "mutate",
]

SAFE_READ_TERMS = [
    "get",
    "select",
    "fetch",
    "load",
    "read",
    "list",
]


def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(read(path))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def line_hits(text: str, terms: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lines = text.splitlines()

    for idx, line in enumerate(lines, start=1):
        lower = line.lower()
        matched = [term for term in terms if term.lower() in lower]
        if matched:
            hits.append({
                "line": idx,
                "matched": matched,
                "text": line.strip()[:260],
            })

    return hits


def function_inventory(path: Path, text: str) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return inventory

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = getattr(node, "name", "")
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)

            if not start:
                continue

            block_lines = text.splitlines()[start - 1:end] if end else text.splitlines()[start - 1:start + 40]
            block_text = "\n".join(block_lines).lower()

            universe_score = sum(1 for term in UNIVERSE_TERMS if term in block_text or term in name.lower())
            risk_terms = [term for term in CALL_RISK_TERMS if term in block_text]
            safe_terms = [term for term in SAFE_READ_TERMS if term in block_text or term in name.lower()]

            if universe_score > 0:
                inventory.append({
                    "path": str(path),
                    "type": node.__class__.__name__,
                    "name": name,
                    "line_start": start,
                    "line_end": end,
                    "universe_score": universe_score,
                    "safe_terms": safe_terms,
                    "risk_terms": risk_terms,
                    "preview": " ".join(line.strip() for line in block_lines[:12])[:600],
                })

    return inventory


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 48 READ-ONLY UNIVERSE SOURCE LOCATOR")
    print("MODE: LOCAL SOURCE AUDIT ONLY / NO DB CALL / NO ALPACA CALL / NO WRITE")
    print("=" * 72)

    failures: list[str] = []
    findings: dict[str, Any] = {}

    readiness = read_json(READINESS)

    required_readiness = {
        "operator_control_evidence_hardened": True,
        "legacy_fallbacks_quarantined": True,
        "campaign_pipeline_validated": False,
        "d3d_authorized": False,
        "operator_control_confirmed_by_score": False,
        "campaign_mutation_without_d3d_law": False,
    }

    for key, expected in required_readiness.items():
        actual = readiness.get(key)
        if actual is not expected:
            failures.append(f"readiness {key} expected {expected}, got {actual}")
        else:
            print(f"PASS: readiness {key}={expected}")

    all_functions: list[dict[str, Any]] = []

    for path in SCAN_PATHS:
        text = read(path)

        if not text:
            findings[str(path)] = {
                "exists": False,
                "universe_line_hits": [],
                "risk_line_hits": [],
                "functions": [],
            }
            print("WARN: missing source file:", path)
            continue

        universe_hits = line_hits(text, UNIVERSE_TERMS)
        risk_hits = line_hits(text, CALL_RISK_TERMS)
        functions = function_inventory(path, text)
        all_functions.extend(functions)

        findings[str(path)] = {
            "exists": True,
            "universe_line_hits": universe_hits[:80],
            "risk_line_hits": risk_hits[:80],
            "functions": functions,
        }

        print("SCAN:", path)
        print("  universe_line_hits:", len(universe_hits))
        print("  risk_line_hits:", len(risk_hits))
        print("  universe_functions:", len(functions))

    ranked_candidates = sorted(
        all_functions,
        key=lambda item: (
            item.get("universe_score", 0),
            len(item.get("safe_terms", [])),
            -len(item.get("risk_terms", [])),
        ),
        reverse=True,
    )

    safe_candidate_functions = [
        item for item in ranked_candidates
        if item.get("universe_score", 0) > 0
        and len(item.get("risk_terms", [])) == 0
    ]

    read_only_adapter_recommendation = None

    if safe_candidate_functions:
        top = safe_candidate_functions[0]
        read_only_adapter_recommendation = {
            "status": "CANDIDATE_SAFE_SOURCE_FOUND",
            "candidate": top,
            "next_step": (
                "Create an isolated read-only universe adapter around this source, "
                "but do not call it from production readiness until locally audited."
            ),
        }
    else:
        read_only_adapter_recommendation = {
            "status": "NO_SAFE_CALLABLE_SOURCE_CONFIRMED",
            "next_step": (
                "Create an explicit non-mutating universe snapshot contract that reports "
                "the absence of a persisted universe source, or manually add a persisted universe "
                "read table through an authorized separate data operation outside this audit path."
            ),
        }

    print("\nRANKED UNIVERSE SOURCE CANDIDATES")
    for item in ranked_candidates[:20]:
        print(
            "CANDIDATE:",
            item["path"],
            item["type"],
            item["name"],
            "lines",
            str(item["line_start"]) + "-" + str(item["line_end"]),
            "universe_score=" + str(item["universe_score"]),
            "safe_terms=" + ",".join(item["safe_terms"]),
            "risk_terms=" + ",".join(item["risk_terms"]),
        )

    print("\nSAFE CANDIDATE FUNCTIONS")
    if safe_candidate_functions:
        for item in safe_candidate_functions[:10]:
            print(
                "SAFE:",
                item["path"],
                item["type"],
                item["name"],
                "lines",
                str(item["line_start"]) + "-" + str(item["line_end"]),
            )
    else:
        print("NONE")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_SOURCE_AUDIT_ONLY_NO_DB_CALL_NO_ALPACA_CALL_NO_WRITE",
        "failures": failures,
        "findings": findings,
        "ranked_candidates": ranked_candidates[:50],
        "safe_candidate_functions": safe_candidate_functions[:25],
        "read_only_adapter_recommendation": read_only_adapter_recommendation,
        "readiness": {
            "campaign_pipeline_validated_current": readiness.get("campaign_pipeline_validated"),
            "campaign_pipeline_validated_can_advance_now": False,
            "reason": "Universe source locator does not mutate readiness. It only identifies whether a safe non-mutating universe source exists.",
        },
        "doctrine": {
            "local_source_audit_only": True,
            "no_database_call": True,
            "no_alpaca_call": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_nightly_run": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nReport written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 48 READ-ONLY UNIVERSE SOURCE LOCATOR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 48 COMPLETE — READ-ONLY UNIVERSE SOURCE LOCATOR PASSED")
    print("PASS: no DB call, no Alpaca call, no write, no mutation, no nightly run, no D3D, no trade signal, no Stripe.")
    print("SEND RANKED UNIVERSE SOURCE CANDIDATES AND SAFE CANDIDATE FUNCTIONS")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
