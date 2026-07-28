#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step37_verify_get_only_production_coverage_reader.json")

STEP35 = Path("audit_step35_pipeline_production_coverage_source_locator.json")
STEP36 = Path("audit_step36_add_get_only_production_coverage_reader.json")
READINESS = Path("v2_readiness.json")

READER = Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py")
SNAPSHOT = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")
ROUTER = Path("backend/campaign_pipeline_validation_api.py")
MAIN = Path("backend/main.py")

REQUIRED_FIELDS = [
    "contract_version",
    "mode",
    "validation_complete",
    "readiness_can_advance",
    "universe_count",
    "bars_symbols_count",
    "symbols_missing_bars",
    "record_min_bars",
    "pagination_complete",
    "schema_payload_alignment",
    "write_path_not_executed_during_validation",
    "doctrine",
]

REQUIRED_DOCTRINE_FLAGS = [
    "no_nightly_run",
    "no_supabase_write",
    "no_campaign_mutation",
    "no_d3d",
    "no_operator_control_confirmation",
    "no_trade_signal",
    "no_stripe",
]


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
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


def load_router_module() -> Any:
    spec = importlib.util.spec_from_file_location("campaign_pipeline_validation_api", ROUTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create import spec for router module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_forbidden_runtime_calls(path: Path, failures: list[str]) -> None:
    text = read(path)

    forbidden = [
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

    for term in forbidden:
        if term in text:
            failures.append(f"{path} contains forbidden mutation/execution term: {term}")
        else:
            print("PASS: forbidden term absent:", path, term)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 37 LOCAL PRODUCTION COVERAGE READER VERIFICATION")
    print("MODE: LOCAL VERIFY / GET-ONLY READER / NO DEPLOY / NO WRITE")
    print("=" * 72)

    failures: list[str] = []

    for report_path in [STEP35, STEP36]:
        report = load_json(report_path)
        if report.get("status") != "PASS":
            failures.append(f"required report is not PASS: {report_path}")
        else:
            print("PASS: required report PASS:", report_path)

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

    for path in [READER, SNAPSHOT, ROUTER, MAIN]:
        syntax_check(path, failures)

    for path in [READER, SNAPSHOT]:
        verify_forbidden_runtime_calls(path, failures)

    reader_text = read(READER)
    snapshot_text = read(SNAPSHOT)
    router_text = read(ROUTER)
    main_text = read(MAIN)

    required_reader_terms = [
        "build_get_only_production_coverage_snapshot",
        "GET_ONLY_PRODUCTION_COVERAGE_READER_NO_NIGHTLY_RUN_NO_WRITE",
        "urllib.request.Request",
        'method="GET"',
        "write_path_not_executed_during_validation",
        "readiness_can_advance",
    ]

    for term in required_reader_terms:
        if term not in reader_text:
            failures.append(f"coverage reader missing term: {term}")
        else:
            print("PASS: coverage reader term present:", term)

    required_snapshot_terms = [
        "build_get_only_production_coverage_snapshot",
        "build_campaign_pipeline_read_only_validation_snapshot",
        "readiness_can_advance",
        "campaign_pipeline_validated_remains_false",
    ]

    for term in required_snapshot_terms:
        if term not in snapshot_text:
            failures.append(f"snapshot module missing term: {term}")
        else:
            print("PASS: snapshot module term present:", term)

    required_router_terms = [
        "get_campaign_pipeline_validation_snapshot",
        "build_campaign_pipeline_read_only_validation_snapshot",
        '@campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")',
    ]

    for term in required_router_terms:
        if term not in router_text:
            failures.append(f"router missing term: {term}")
        else:
            print("PASS: router term present:", term)

    if "campaign_pipeline_validation_router" not in main_text:
        failures.append("main.py missing campaign_pipeline_validation_router wiring")
    else:
        print("PASS: main.py isolated router wiring present")

    snapshot = None

    try:
        router_module = load_router_module()
        builder = getattr(router_module, "get_campaign_pipeline_validation_snapshot", None)

        if not callable(builder):
            failures.append("router snapshot builder is not callable")
        else:
            snapshot = builder()
    except Exception as exc:
        failures.append(f"router snapshot execution failed: {exc}")

    if not isinstance(snapshot, dict):
        failures.append("router snapshot result is not dict")
    else:
        print("PASS: router snapshot executed locally")

        for field in REQUIRED_FIELDS:
            if field not in snapshot:
                failures.append(f"snapshot missing field: {field}")
            else:
                print("PASS: snapshot field present:", field)

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("snapshot readiness_can_advance must remain false")
        else:
            print("PASS: snapshot readiness_can_advance=False")

        if snapshot.get("write_path_not_executed_during_validation") is not True:
            failures.append("write_path_not_executed_during_validation must be true")
        else:
            print("PASS: write_path_not_executed_during_validation=True")

        doctrine = snapshot.get("doctrine") or {}
        for flag in REQUIRED_DOCTRINE_FLAGS:
            if doctrine.get(flag) is not True:
                failures.append(f"snapshot doctrine flag must be true: {flag}")
            else:
                print("PASS: snapshot doctrine flag true:", flag)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_VERIFY_GET_ONLY_READER_NO_DEPLOY_NO_WRITE",
        "failures": failures,
        "snapshot_preview": snapshot,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "GET-only production coverage reader verified locally. Deploy/live verification required before any readiness update.",
        },
        "doctrine": {
            "local_verify_only": True,
            "no_deploy": True,
            "get_only_reader": True,
            "no_nightly_run": True,
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

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 37 LOCAL PRODUCTION COVERAGE READER VERIFICATION FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 37 COMPLETE — LOCAL GET-ONLY PRODUCTION COVERAGE READER VERIFIED")
    print("PASS: readiness remains false; billing remains blocked pending deploy/live verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
