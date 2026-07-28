#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step28b_install_isolated_pipeline_validation_router.json")

ROUTER_FILE = Path("backend/campaign_pipeline_validation_api.py")
SNAPSHOT_MODULE = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")
MAIN_FILE = Path("backend/main.py")

IMPORT_MARKER = "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_IMPORT"
INCLUDE_MARKER = "STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_INCLUDE"

ROUTER_TEXT = '''"""
Sigmalytic V2 — Campaign Pipeline Validation API.

Read-only diagnostic router.

This router does not run the nightly pipeline.
This router does not call Alpaca.
This router does not write Supabase.
This router does not mutate campaigns.
This router does not authorize D3D.
This router does not confirm operator control.
This router does not create trade signals.
This router does not touch Stripe.
"""
from __future__ import annotations

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

try:
    from campaign_engine.campaign_pipeline_read_only_validation_snapshot import (
        build_campaign_pipeline_read_only_validation_snapshot,
    )
except Exception:
    from backend.campaign_engine.campaign_pipeline_read_only_validation_snapshot import (
        build_campaign_pipeline_read_only_validation_snapshot,
    )


if APIRouter is not None:
    campaign_pipeline_validation_router = APIRouter(
        prefix="/api/campaigns/read-only",
        tags=["campaign-pipeline-validation-read-only"],
    )
else:
    campaign_pipeline_validation_router = None


def get_campaign_pipeline_validation_snapshot():
    """
    Build the GET-only campaign pipeline validation snapshot.

    This function is diagnostic-only and does not mutate production state.
    """
    return build_campaign_pipeline_read_only_validation_snapshot()


if campaign_pipeline_validation_router is not None:
    @campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")
    def campaign_pipeline_read_only_validation_snapshot():
        """
        GET-only campaign pipeline validation snapshot.

        No nightly run.
        No Alpaca call.
        No Supabase write.
        No campaign mutation.
        No D3D.
        No operator-control confirmation.
        No trade signal.
        No Stripe.
        """
        return get_campaign_pipeline_validation_snapshot()


__all__ = [
    "campaign_pipeline_validation_router",
    "get_campaign_pipeline_validation_snapshot",
]
'''


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


def find_fastapi_app_name(text: str) -> str | None:
    tree = ast.parse(text)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        value = node.value
        if not isinstance(value, ast.Call):
            continue

        func = value.func
        func_name = ""

        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name != "FastAPI":
            continue

        for target in node.targets:
            if isinstance(target, ast.Name):
                return target.id

    return None


def patch_main(failures: list[str], changes: list[str]) -> None:
    text = read(MAIN_FILE)

    try:
        ast.parse(text, filename=str(MAIN_FILE))
    except SyntaxError as exc:
        failures.append(f"backend/main.py syntax invalid before patch: {exc.msg} line {exc.lineno}")
        return

    app_name = find_fastapi_app_name(text)

    if not app_name:
        failures.append("could not identify FastAPI app variable in backend/main.py")
        return

    import_line = (
        f"# {IMPORT_MARKER}\n"
        "try:\n"
        "    from campaign_pipeline_validation_api import campaign_pipeline_validation_router\n"
        "except Exception:\n"
        "    from backend.campaign_pipeline_validation_api import campaign_pipeline_validation_router\n"
    )

    include_line = (
        f"\n# {INCLUDE_MARKER}\n"
        "if campaign_pipeline_validation_router is not None:\n"
        f"    {app_name}.include_router(campaign_pipeline_validation_router)\n"
    )

    if IMPORT_MARKER not in text:
        text = import_line + "\n" + text
        changes.append("added isolated router import to backend/main.py")
    else:
        changes.append("isolated router import already present in backend/main.py")

    if INCLUDE_MARKER not in text:
        text = text.rstrip() + "\n" + include_line
        changes.append("added isolated router include to backend/main.py")
    else:
        changes.append("isolated router include already present in backend/main.py")

    write(MAIN_FILE, text)


def load_router_module(failures: list[str]) -> Any | None:
    spec = importlib.util.spec_from_file_location("campaign_pipeline_validation_api", ROUTER_FILE)

    if spec is None or spec.loader is None:
        failures.append("could not create import spec for isolated router module")
        return None

    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        failures.append(f"isolated router module import failed: {exc}")
        return None

    return module


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 28B ISOLATED READ-ONLY PIPELINE ROUTER INSTALL")
    print("MODE: LOCAL ISOLATED ROUTER PATCH / NO NIGHTLY RUN / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    changes: list[str] = []

    write(ROUTER_FILE, ROUTER_TEXT)
    changes.append(f"wrote isolated read-only router: {ROUTER_FILE}")

    patch_main(failures, changes)

    for path in [ROUTER_FILE, SNAPSHOT_MODULE, MAIN_FILE]:
        syntax_check(path, failures)

    router_text = read(ROUTER_FILE)
    for required in [
        "APIRouter",
        'prefix="/api/campaigns/read-only"',
        '@campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")',
        "build_campaign_pipeline_read_only_validation_snapshot",
        "No nightly run",
        "No Supabase write",
        "No campaign mutation",
        "No D3D",
        "No operator-control confirmation",
        "No trade signal",
        "No Stripe",
    ]:
        if required not in router_text:
            failures.append(f"router file missing required text: {required}")

    main_text = read(MAIN_FILE)
    for required in [
        IMPORT_MARKER,
        INCLUDE_MARKER,
        "campaign_pipeline_validation_router",
        ".include_router(campaign_pipeline_validation_router)",
    ]:
        if required not in main_text:
            failures.append(f"backend/main.py missing required router wiring text: {required}")

    if "STEP26_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ENDPOINT" in read(Path("backend/campaign_api.py")):
        failures.append("old Step 26 route marker still present in campaign_api.py")

    module = load_router_module(failures)
    snapshot = None

    if module is not None:
        builder = getattr(module, "get_campaign_pipeline_validation_snapshot", None)

        if not callable(builder):
            failures.append("get_campaign_pipeline_validation_snapshot is not callable")
        else:
            snapshot = builder()

            if not isinstance(snapshot, dict):
                failures.append("snapshot result is not dict")
            else:
                if snapshot.get("validation_complete") is not False:
                    failures.append("snapshot validation_complete must remain false")

                if snapshot.get("readiness_can_advance") is not False:
                    failures.append("snapshot readiness_can_advance must remain false")

                if snapshot.get("write_path_not_executed_during_validation") is not True:
                    failures.append("snapshot write_path_not_executed_during_validation must be true")

                doctrine = snapshot.get("doctrine") or {}
                for key in [
                    "no_nightly_run",
                    "no_alpaca_call_from_this_module",
                    "no_supabase_write",
                    "no_campaign_mutation",
                    "no_d3d",
                    "no_operator_control_confirmation",
                    "no_trade_signal",
                    "no_stripe",
                    "campaign_pipeline_validated_remains_false",
                ]:
                    if doctrine.get(key) is not True:
                        failures.append(f"snapshot doctrine flag must be true: {key}")

    report = {
        "mode": "LOCAL_ISOLATED_ROUTER_PATCH_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "changes": changes,
        "failures": failures,
        "endpoint": "/api/campaigns/read-only/pipeline-validation-snapshot",
        "snapshot_preview": snapshot,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "Isolated read-only route installed locally; deploy and live GET verification still required.",
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
            "campaign_pipeline_validated_remains_false": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for change in changes:
        print("PASS:", change)

    if snapshot is not None:
        print("PASS: isolated router snapshot callable executed")
        print("PASS: validation_complete:", snapshot.get("validation_complete"))
        print("PASS: readiness_can_advance:", snapshot.get("readiness_can_advance"))
        print("PASS: write_path_not_executed_during_validation:", snapshot.get("write_path_not_executed_during_validation"))

    print("Report written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 28B ISOLATED ROUTER INSTALL FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 28B COMPLETE — ISOLATED READ-ONLY PIPELINE ROUTER INSTALLED LOCALLY")
    print("PASS: campaign_pipeline_validated remains false pending deploy/live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
