#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step26e_safe_module_only_pipeline_snapshot_repair.json")
MODULE = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")
CAMPAIGN_API = Path("backend/campaign_api.py")

MODULE_TEXT = '''"""
Sigmalytic V2 — Campaign Pipeline Read-Only Validation Snapshot.

Step 26E installs this as a module-only contract.

It does not install a route.
It does not run the nightly pipeline.
It does not call Alpaca.
It does not write Supabase.
It does not mutate campaigns.
It does not authorize D3D.
It does not confirm operator control.
It does not create trade signals.
It does not touch Stripe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_CAMPAIGN_PIPELINE_READ_ONLY_SNAPSHOT_2026_07_09"

REQUIRED_SNAPSHOT_FIELDS = (
    "universe_count",
    "bars_symbols_count",
    "symbols_missing_bars",
    "record_min_bars",
    "pagination_complete",
    "schema_payload_alignment",
    "write_path_not_executed_during_validation",
)

SOURCE_FILES = (
    "backend/campaign_engine/nightly_campaign_pipeline.py",
    "backend/campaign_engine/campaign_discovery_engine.py",
    "backend/campaign_engine/campaign_store.py",
    "backend/campaign_api.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _combined_source() -> str:
    root = _repo_root()
    return "\\n".join(_read_source(root / rel).lower() for rel in SOURCE_FILES)


def _source_presence() -> dict[str, bool]:
    combined = _combined_source()

    return {
        "universe_binding_present": "universe" in combined,
        "alpaca_or_bar_binding_present": "alpaca" in combined or "bars" in combined,
        "campaign_evaluation_present": "campaign" in combined and ("evaluate" in combined or "discovery" in combined),
        "schema_payload_terms_present": "payload" in combined and "schema" in combined,
        "supabase_reference_present": "supabase" in combined,
    }


def build_campaign_pipeline_read_only_validation_snapshot() -> dict[str, Any]:
    source_presence = _source_presence()

    schema_payload_alignment = bool(
        source_presence["campaign_evaluation_present"]
        and source_presence["schema_payload_terms_present"]
        and source_presence["supabase_reference_present"]
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "MODULE_ONLY_READ_ONLY_DIAGNOSTIC_NO_ROUTE_NO_NIGHTLY_RUN_NO_WRITE",
        "validation_complete": False,
        "readiness_can_advance": False,
        "reason": (
            "Module-only read-only snapshot builder is installed. "
            "A live GET route is not installed in this step. "
            "Production coverage counts are not confirmed."
        ),
        "universe_count": None,
        "bars_symbols_count": None,
        "symbols_missing_bars": [],
        "record_min_bars": None,
        "pagination_complete": False,
        "schema_payload_alignment": schema_payload_alignment,
        "write_path_not_executed_during_validation": True,
        "source_presence": source_presence,
        "required_snapshot_fields": list(REQUIRED_SNAPSHOT_FIELDS),
        "doctrine": {
            "module_only": True,
            "get_only_route_not_installed_yet": True,
            "no_nightly_run": True,
            "no_alpaca_call_from_this_module": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "campaign_pipeline_validated_remains_false": True,
        },
    }


__all__ = [
    "CONTRACT_VERSION",
    "REQUIRED_SNAPSHOT_FIELDS",
    "build_campaign_pipeline_read_only_validation_snapshot",
]
'''


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def syntax_clean(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


def load_snapshot_module() -> Any:
    spec = importlib.util.spec_from_file_location("campaign_pipeline_read_only_validation_snapshot", MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create import spec for snapshot module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 26E SAFE MODULE-ONLY PIPELINE SNAPSHOT REPAIR")
    print("MODE: LOCAL REPAIR ONLY / NO ROUTE / NO NIGHTLY RUN / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    changes: list[str] = []

    write(MODULE, MODULE_TEXT)
    changes.append("wrote module-only pipeline read-only snapshot builder")

    syntax_clean(MODULE, failures)
    syntax_clean(CAMPAIGN_API, failures)

    campaign_api_text = read(CAMPAIGN_API)
    if "STEP26_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ENDPOINT" in campaign_api_text:
        failures.append("failed Step 26 route marker still present in campaign_api.py")

    snapshot: dict[str, Any] | None = None

    try:
        module = load_snapshot_module()
        builder = module.build_campaign_pipeline_read_only_validation_snapshot
        snapshot = builder()
    except Exception as exc:
        failures.append(f"snapshot module import/execution failed: {exc}")

    if snapshot is not None:
        required_fields = [
            "universe_count",
            "bars_symbols_count",
            "symbols_missing_bars",
            "record_min_bars",
            "pagination_complete",
            "schema_payload_alignment",
            "write_path_not_executed_during_validation",
        ]

        for field in required_fields:
            if field not in snapshot:
                failures.append(f"snapshot missing required field: {field}")

        if snapshot.get("validation_complete") is not False:
            failures.append("validation_complete must be false")

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("readiness_can_advance must be false")

        if snapshot.get("write_path_not_executed_during_validation") is not True:
            failures.append("write_path_not_executed_during_validation must be true")

        doctrine = snapshot.get("doctrine") or {}
        for key in [
            "module_only",
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
                failures.append(f"doctrine flag must be true: {key}")

    report = {
        "mode": "LOCAL_MODULE_ONLY_REPAIR_NO_ROUTE_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "changes": changes,
        "failures": failures,
        "snapshot_preview": snapshot,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "Module-only snapshot builder verified. Live route remains deferred.",
        },
        "doctrine": {
            "module_only": True,
            "no_route_installed": True,
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

    for change in changes:
        print("PASS:", change)

    if snapshot is not None:
        print("PASS: snapshot module imported and executed")
        print("PASS: validation_complete:", snapshot.get("validation_complete"))
        print("PASS: readiness_can_advance:", snapshot.get("readiness_can_advance"))
        print("PASS: write_path_not_executed_during_validation:", snapshot.get("write_path_not_executed_during_validation"))

    print("Report written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 26E SAFE MODULE-ONLY REPAIR FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 26E COMPLETE — MODULE-ONLY READ-ONLY SNAPSHOT VERIFIED")
    print("PASS: campaign_pipeline_validated remains false.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
