#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step29_verify_isolated_pipeline_validation_router.json")

STEP26E = Path("audit_step26e_safe_module_only_pipeline_snapshot_repair.json")
STEP28B = Path("audit_step28b_install_isolated_pipeline_validation_router.json")
READINESS = Path("v2_readiness.json")

MAIN_FILE = Path("backend/main.py")
CAMPAIGN_API = Path("backend/campaign_api.py")
ROUTER_FILE = Path("backend/campaign_pipeline_validation_api.py")
SNAPSHOT_MODULE = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")

REQUIRED_SNAPSHOT_FIELDS = [
    "universe_count",
    "bars_symbols_count",
    "symbols_missing_bars",
    "record_min_bars",
    "pagination_complete",
    "schema_payload_alignment",
    "write_path_not_executed_during_validation",
]

REQUIRED_DOCTRINE_FLAGS = [
    "no_nightly_run",
    "no_alpaca_call_from_this_module",
    "no_supabase_write",
    "no_campaign_mutation",
    "no_d3d",
    "no_operator_control_confirmation",
    "no_trade_signal",
    "no_stripe",
    "campaign_pipeline_validated_remains_false",
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
    spec = importlib.util.spec_from_file_location("campaign_pipeline_validation_api", ROUTER_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create import spec for isolated router module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 29 LOCAL READ-ONLY ROUTE VERIFICATION")
    print("MODE: LOCAL VERIFY / NO NIGHTLY RUN / NO DATABASE WRITE / NO DEPLOY")
    print("=" * 72)

    failures: list[str] = []

    for path in [STEP26E, STEP28B, READINESS]:
        data = load_json(path)
        if data.get("status") != "PASS" and path != READINESS:
            failures.append(f"required report is not PASS: {path}")
        else:
            print("PASS: required JSON loaded:", path)

    readiness = load_json(READINESS)

    if readiness.get("campaign_pipeline_validated") is not False:
        failures.append("campaign_pipeline_validated must remain false before live validation")
    else:
        print("PASS: campaign_pipeline_validated remains false")

    if readiness.get("operator_control_evidence_hardened") is not True:
        failures.append("operator_control_evidence_hardened must be true")

    if readiness.get("legacy_fallbacks_quarantined") is not True:
        failures.append("legacy_fallbacks_quarantined must be true")

    for field in [
        "d3d_authorized",
        "operator_control_confirmed_by_score",
        "campaign_mutation_without_d3d_law",
    ]:
        if readiness.get(field) is not False:
            failures.append(f"{field} must remain false")
        else:
            print(f"PASS: {field}=False")

    for path in [MAIN_FILE, CAMPAIGN_API, ROUTER_FILE, SNAPSHOT_MODULE]:
        syntax_check(path, failures)

    main_text = read(MAIN_FILE)
    router_text = read(ROUTER_FILE)
    campaign_api_text = read(CAMPAIGN_API)

    required_main_terms = [
        "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_IMPORT",
        "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_INCLUDE",
        "campaign_pipeline_validation_router",
        ".include_router(campaign_pipeline_validation_router)",
    ]

    for term in required_main_terms:
        if term not in main_text:
            failures.append(f"backend/main.py missing required term: {term}")
        else:
            print("PASS: backend/main.py term present:", term)

    required_router_terms = [
        "campaign_pipeline_validation_router",
        'prefix="/api/campaigns/read-only"',
        '@campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")',
        "get_campaign_pipeline_validation_snapshot",
        "build_campaign_pipeline_read_only_validation_snapshot",
    ]

    for term in required_router_terms:
        if term not in router_text:
            failures.append(f"router file missing required term: {term}")
        else:
            print("PASS: router term present:", term)

    if "STEP26_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ENDPOINT" in campaign_api_text:
        failures.append("old failed Step 26 route marker still present in campaign_api.py")
    else:
        print("PASS: old failed Step 26 route marker absent from campaign_api.py")

    module = load_router_module()
    builder = getattr(module, "get_campaign_pipeline_validation_snapshot", None)

    if not callable(builder):
        failures.append("get_campaign_pipeline_validation_snapshot is not callable")
        snapshot = None
    else:
        snapshot = builder()

    if not isinstance(snapshot, dict):
        failures.append("snapshot result is not a dict")
    else:
        print("PASS: isolated router snapshot callable executed")

        for field in REQUIRED_SNAPSHOT_FIELDS:
            if field not in snapshot:
                failures.append(f"snapshot missing required field: {field}")
            else:
                print("PASS: snapshot field present:", field)

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
            print("PASS: write_path_not_executed_during_validation=True")

        doctrine = snapshot.get("doctrine") or {}
        for flag in REQUIRED_DOCTRINE_FLAGS:
            if doctrine.get(flag) is not True:
                failures.append(f"snapshot doctrine flag must be true: {flag}")
            else:
                print("PASS: snapshot doctrine flag true:", flag)

    report = {
        "mode": "LOCAL_ROUTE_VERIFY_NO_NIGHTLY_RUN_NO_DATABASE_WRITE_NO_DEPLOY",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "snapshot_preview": snapshot,
        "endpoint": "/api/campaigns/read-only/pipeline-validation-snapshot",
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "Local isolated router verified. Deploy and live GET-only verification still required.",
        },
        "doctrine": {
            "get_only_route": True,
            "no_nightly_run": True,
            "no_alpaca_call_from_route": True,
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
        print("FAIL: STEP 29 LOCAL ROUTE VERIFICATION FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 29 COMPLETE — LOCAL READ-ONLY ROUTE VERIFIED")
    print("PASS: campaign_pipeline_validated remains false pending deploy/live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
