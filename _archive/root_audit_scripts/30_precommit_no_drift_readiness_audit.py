#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

REPORT = Path("audit_step30_precommit_no_drift_readiness_audit.json")

READINESS = Path("v2_readiness.json")

SUCCESS_REPORTS = [
    Path("audit_step26e_safe_module_only_pipeline_snapshot_repair.json"),
    Path("audit_step27_route_topology_preflight.json"),
    Path("audit_step28b_install_isolated_pipeline_validation_router.json"),
    Path("audit_step29_verify_isolated_pipeline_validation_router.json"),
]

FAILED_ARTIFACTS_TO_REMOVE = [
    Path("26_add_campaign_pipeline_read_only_snapshot_endpoint.py"),
    Path("audit_step26_add_campaign_pipeline_read_only_snapshot_endpoint.json"),
    Path("26a_repair_campaign_pipeline_read_only_snapshot_endpoint.py"),
    Path("audit_step26a_repair_campaign_pipeline_read_only_snapshot_endpoint.json"),
    Path("26c_module_only_pipeline_snapshot_reset.py"),
    Path("audit_step26c_module_only_pipeline_snapshot_reset.json"),
    Path("28_install_pipeline_snapshot_route.py"),
    Path("audit_step28_install_pipeline_snapshot_route.json"),
]

SYNTAX_FILES = [
    Path("backend/main.py"),
    Path("backend/campaign_api.py"),
    Path("backend/campaign_pipeline_validation_api.py"),
    Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py"),
    Path("backend/campaign_engine/operator_control_evidence_contract.py"),
    Path("backend/campaign_engine/campaign_state_engine.py"),
    Path("backend/signal_birth_engine.py"),
    Path("backend/research_engine/signal_birth_engine.py"),
]

MAIN_FILE = Path("backend/main.py")
CAMPAIGN_API = Path("backend/campaign_api.py")
ROUTER_FILE = Path("backend/campaign_pipeline_validation_api.py")
SNAPSHOT_MODULE = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(read(path))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except Exception as exc:
        failures.append(f"syntax/import-read failure: {path}: {exc}")


def remove_failed_artifacts() -> list[str]:
    removed: list[str] = []

    for path in FAILED_ARTIFACTS_TO_REMOVE:
        if path.exists():
            path.unlink()
            removed.append(str(path))

    return removed


def git_status() -> list[str]:
    completed = subprocess.run(
        ["git", "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    return [line.rstrip() for line in completed.stdout.splitlines() if line.strip()]


def load_router_snapshot() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("campaign_pipeline_validation_api", ROUTER_FILE)

    if spec is None or spec.loader is None:
        raise RuntimeError("could not create import spec for isolated router module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    builder = getattr(module, "get_campaign_pipeline_validation_snapshot", None)

    if not callable(builder):
        raise RuntimeError("get_campaign_pipeline_validation_snapshot is not callable")

    snapshot = builder()

    if not isinstance(snapshot, dict):
        raise RuntimeError("snapshot result is not dict")

    return snapshot


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 30 PRE-COMMIT NO-DRIFT AUDIT")
    print("MODE: LOCAL CLEANUP + AUDIT / NO DEPLOY / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    removed = remove_failed_artifacts()

    for item in removed:
        print("PASS: removed failed intermediate artifact:", item)

    readiness = load_json(READINESS)

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

    for report_path in SUCCESS_REPORTS:
        data = load_json(report_path)

        if data.get("status") != "PASS":
            failures.append(f"success report is not PASS: {report_path}")
        else:
            print("PASS: required success report PASS:", report_path)

    for path in SYNTAX_FILES:
        syntax_check(path, failures)

    main_text = read(MAIN_FILE)
    campaign_api_text = read(CAMPAIGN_API)
    router_text = read(ROUTER_FILE)
    snapshot_text = read(SNAPSHOT_MODULE)

    required_main_terms = [
        "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_IMPORT",
        "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_INCLUDE",
        ".include_router(campaign_pipeline_validation_router)",
    ]

    for term in required_main_terms:
        if term not in main_text:
            failures.append(f"backend/main.py missing router wiring term: {term}")
        else:
            print("PASS: backend/main.py wiring term present:", term)

    forbidden_campaign_api_terms = [
        "STEP26_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ENDPOINT",
        "STEP28_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ROUTE",
        "pipeline-validation-snapshot",
    ]

    for term in forbidden_campaign_api_terms:
        if term in campaign_api_text:
            failures.append(f"backend/campaign_api.py still contains failed direct-route term: {term}")
        else:
            print("PASS: backend/campaign_api.py absent failed direct-route term:", term)

    required_router_terms = [
        'prefix="/api/campaigns/read-only"',
        '@campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")',
        "get_campaign_pipeline_validation_snapshot",
        "build_campaign_pipeline_read_only_validation_snapshot",
    ]

    for term in required_router_terms:
        if term not in router_text:
            failures.append(f"isolated router missing term: {term}")
        else:
            print("PASS: isolated router term present:", term)

    required_snapshot_terms = [
        "build_campaign_pipeline_read_only_validation_snapshot",
        "universe_count",
        "bars_symbols_count",
        "symbols_missing_bars",
        "record_min_bars",
        "pagination_complete",
        "schema_payload_alignment",
        "write_path_not_executed_during_validation",
        "campaign_pipeline_validated_remains_false",
    ]

    for term in required_snapshot_terms:
        if term not in snapshot_text:
            failures.append(f"snapshot module missing term: {term}")
        else:
            print("PASS: snapshot module term present:", term)

    snapshot = None

    try:
        snapshot = load_router_snapshot()
        print("PASS: isolated router snapshot callable executed")
    except Exception as exc:
        failures.append(f"isolated router snapshot execution failed: {exc}")

    if isinstance(snapshot, dict):
        if snapshot.get("validation_complete") is not False:
            failures.append("snapshot validation_complete must remain false")
        else:
            print("PASS: snapshot validation_complete=False")

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("snapshot readiness_can_advance must remain false")
        else:
            print("PASS: snapshot readiness_can_advance=False")

        if snapshot.get("write_path_not_executed_during_validation") is not True:
            failures.append("snapshot write_path_not_executed_during_validation must be true")
        else:
            print("PASS: snapshot write_path_not_executed_during_validation=True")

    status_lines = git_status()

    dirty_cache_lines = [
        line for line in status_lines
        if "__pycache__" in line or line.endswith(".pyc") or line.endswith(".pyo")
    ]

    if dirty_cache_lines:
        failures.append("dirty pycache/bytecode artifacts detected in git status")
        for line in dirty_cache_lines:
            failures.append(f"dirty cache artifact: {line}")
    else:
        print("PASS: no dirty pycache/bytecode artifacts detected")

    report = {
        "mode": "LOCAL_PRECOMMIT_NO_DRIFT_AUDIT_NO_DEPLOY_NO_DATABASE_WRITE",
        "status": "PASS" if not failures else "FAIL",
        "removed_failed_artifacts": removed,
        "failures": failures,
        "git_status_short": status_lines,
        "endpoint": "/api/campaigns/read-only/pipeline-validation-snapshot",
        "readiness": {
            "operator_control_evidence_hardened": readiness.get("operator_control_evidence_hardened"),
            "legacy_fallbacks_quarantined": readiness.get("legacy_fallbacks_quarantined"),
            "campaign_pipeline_validated": readiness.get("campaign_pipeline_validated"),
            "billing_should_remain_blocked": True,
        },
        "doctrine": {
            "no_deploy": True,
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

    print("\nGIT STATUS")
    if status_lines:
        for line in status_lines:
            print(line)
    else:
        print("clean")

    print("\nReport written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 30 PRE-COMMIT NO-DRIFT AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 30 COMPLETE — PRE-COMMIT NO-DRIFT AUDIT PASSED")
    print("PASS: ready for commit/tag/push after billing gate remains blocked.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
