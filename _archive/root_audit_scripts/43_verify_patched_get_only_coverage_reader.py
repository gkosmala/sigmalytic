#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step43_verify_patched_get_only_coverage_reader.json")

STEP42 = Path("audit_step42_patch_get_only_coverage_reader_http206_and_schema_fallbacks.json")
READINESS = Path("v2_readiness.json")

READER = Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py")
SNAPSHOT = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")
ROUTER = Path("backend/campaign_pipeline_validation_api.py")
MAIN = Path("backend/main.py")

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


def read_json(path: Path) -> dict[str, Any]:
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


def verify_absent(path: Path, terms: list[str], failures: list[str]) -> None:
    text = read(path)

    for term in terms:
        if term in text:
            failures.append(f"{path} contains forbidden term: {term}")
        else:
            print("PASS: forbidden term absent:", path, term)


def verify_present(path: Path, terms: list[str], failures: list[str]) -> None:
    text = read(path)

    for term in terms:
        if term not in text:
            failures.append(f"{path} missing required term: {term}")
        else:
            print("PASS: required term present:", path, term)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 43 LOCAL VERIFY PATCHED GET-ONLY COVERAGE READER")
    print("MODE: LOCAL VERIFY / NO DEPLOY / NO WRITE / NO NIGHTLY RUN")
    print("=" * 72)

    failures: list[str] = []

    step42 = read_json(STEP42)
    if step42.get("status") != "PASS":
        failures.append("Step 42 report is not PASS")
    else:
        print("PASS: Step 42 report PASS")

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

    for path in [READER, SNAPSHOT, ROUTER, MAIN]:
        syntax_check(path, failures)

    verify_absent(
        READER,
        [
            ".insert(",
            ".upsert(",
            ".update(",
            ".delete(",
            ".rpc(",
            "run_full_nightly(",
            "execute_d3d(",
            "authorize_d3d(",
            "stripe.",
        ],
        failures,
    )

    verify_present(
        READER,
        [
            "status in (200, 206)",
            "HTTP 206",
            "GET_ONLY_PRODUCTION_COVERAGE_READER_HTTP206_SCHEMA_FALLBACKS",
            "persisted_universe_available",
            "schema_payload_alignment",
            "write_path_not_executed_during_validation",
            "readiness_can_advance",
            "campaign_pipeline_validated_remains_false_until_explicit_readiness_update",
        ],
        failures,
    )

    verify_present(
        SNAPSHOT,
        [
            "build_get_only_production_coverage_snapshot",
            "build_campaign_pipeline_read_only_validation_snapshot",
            "readiness_can_advance",
            "campaign_pipeline_validated_remains_false",
        ],
        failures,
    )

    snapshot = None

    try:
        router_module = load_router_module()
        builder = getattr(router_module, "get_campaign_pipeline_validation_snapshot", None)

        if not callable(builder):
            failures.append("router get_campaign_pipeline_validation_snapshot is not callable")
        else:
            snapshot = builder()
    except Exception as exc:
        failures.append(f"router snapshot execution failed: {exc}")

    if not isinstance(snapshot, dict):
        failures.append("router snapshot result is not dict")
    else:
        print("PASS: router snapshot executed locally")

        for key in [
            "contract_version",
            "mode",
            "coverage_reader_attempted",
            "validation_complete",
            "readiness_can_advance",
            "universe_count",
            "bars_symbols_count",
            "record_min_bars",
            "pagination_complete",
            "schema_payload_alignment",
            "write_path_not_executed_during_validation",
            "doctrine",
        ]:
            if key not in snapshot:
                failures.append(f"snapshot missing field: {key}")
            else:
                print("PASS: snapshot field present:", key)

        if "HTTP206_SCHEMA_FALLBACKS" not in str(snapshot.get("mode")):
            failures.append("snapshot mode does not include HTTP206_SCHEMA_FALLBACKS")
        else:
            print("PASS: snapshot mode includes HTTP206_SCHEMA_FALLBACKS")

        if snapshot.get("coverage_reader_attempted") is not True:
            failures.append("coverage_reader_attempted must be true")
        else:
            print("PASS: coverage_reader_attempted=True")

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("readiness_can_advance must remain false")
        else:
            print("PASS: readiness_can_advance=False")

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
        "mode": "LOCAL_VERIFY_PATCHED_GET_ONLY_READER_NO_DEPLOY_NO_WRITE_NO_NIGHTLY_RUN",
        "failures": failures,
        "snapshot_preview": snapshot,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "Patched GET-only reader verified locally. Commit/push and live GET verification required before any readiness decision.",
        },
        "doctrine": {
            "local_verify_only": True,
            "get_only_reader": True,
            "http_206_supported": True,
            "no_deploy": True,
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
        print("FAIL: STEP 43 LOCAL VERIFY PATCHED GET-ONLY COVERAGE READER FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 43 COMPLETE — PATCHED GET-ONLY COVERAGE READER VERIFIED LOCALLY")
    print("PASS: readiness remains false; billing remains blocked pending commit/push/live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
