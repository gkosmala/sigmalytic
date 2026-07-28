#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step49a_repair_non_mutating_universe_snapshot_contract.json")

STEP48 = Path("audit_step48_read_only_universe_source_locator.json")
READINESS = Path("v2_readiness.json")

CONTRACT = Path("backend/campaign_engine/campaign_pipeline_universe_snapshot_contract.py")

CONTRACT_TEXT = '''"""
Sigmalytic V2 — Campaign Pipeline Universe Snapshot Contract.

This contract is intentionally non-mutating.

It does not call external data providers.
It does not call any database.
It does not run the nightly pipeline.
It does not write to any database.
It does not mutate campaigns.
It does not authorize D3D.
It does not confirm operator control.
It does not create trade signals.
It does not touch billing.

Purpose:
    Represent the universe-source status discovered by read-only audits.

Important:
    Absence of a persisted universe table is not treated as success.
    A bars-symbol universe proxy may be reported as diagnostic evidence only,
    but it cannot be silently promoted into a live universe count.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_NON_MUTATING_UNIVERSE_SNAPSHOT_CONTRACT_2026_07_09"

UNIVERSE_SOURCE_STATUS = {
    "persisted_universe_table_required_for_full_validation": True,
    "persisted_universe_table_confirmed": False,
    "external_live_universe_call_allowed": False,
    "bars_symbol_universe_proxy_allowed_as_diagnostic_only": True,
    "bars_symbol_universe_proxy_can_replace_live_universe": False,
}


def build_non_mutating_universe_snapshot(
    *,
    persisted_universe_table: str | None = None,
    persisted_universe_count: int | None = None,
    bars_symbol_count: int | None = None,
    campaign_symbol_count: int | None = None,
    locator_status: str | None = None,
    locator_recommendation_status: str | None = None,
) -> dict[str, Any]:
    persisted_universe_available = bool(
        persisted_universe_table
        and isinstance(persisted_universe_count, int)
        and persisted_universe_count > 0
    )

    bars_symbol_universe_proxy_available = bool(
        isinstance(bars_symbol_count, int)
        and bars_symbol_count > 0
    )

    full_universe_validation_complete = bool(
        persisted_universe_available
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "NON_MUTATING_UNIVERSE_SNAPSHOT_CONTRACT_NO_DB_CALL_NO_EXTERNAL_UNIVERSE_CALL_NO_WRITE",
        "locator_status": locator_status,
        "locator_recommendation_status": locator_recommendation_status,

        "persisted_universe_available": persisted_universe_available,
        "persisted_universe_table": persisted_universe_table,
        "persisted_universe_count": persisted_universe_count,

        "bars_symbol_universe_proxy_available": bars_symbol_universe_proxy_available,
        "bars_symbol_count": bars_symbol_count,
        "campaign_symbol_count": campaign_symbol_count,

        "full_universe_validation_complete": full_universe_validation_complete,
        "readiness_can_advance": False,
        "reason": (
            "A persisted universe table/count is required for full campaign pipeline validation. "
            "Bars-symbol coverage is useful diagnostic evidence but is not silently promoted "
            "into a live universe source."
        ),
        "source_status": dict(UNIVERSE_SOURCE_STATUS),
        "doctrine": {
            "non_mutating_contract_only": True,
            "no_database_call": True,
            "no_external_universe_call": True,
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


__all__ = [
    "CONTRACT_VERSION",
    "UNIVERSE_SOURCE_STATUS",
    "build_non_mutating_universe_snapshot",
]
'''


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(read(path))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


def verify_no_runtime_integrations(path: Path, failures: list[str]) -> None:
    text = read(path)

    forbidden_runtime_terms = [
        "import urllib",
        "import requests",
        "from supabase",
        "create_client(",
        ".table(",
        ".insert(",
        ".upsert(",
        ".update(",
        ".delete(",
        ".rpc(",
        "run_full_nightly(",
        "execute_d3d(",
        "authorize_d3d(",
        "stripe.",
        "alpaca_trade_api",
    ]

    for term in forbidden_runtime_terms:
        if term in text:
            failures.append(f"{path} contains forbidden runtime integration term: {term}")
        else:
            print("PASS: forbidden runtime integration absent:", term)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 49A REPAIR NON-MUTATING UNIVERSE SNAPSHOT CONTRACT AUDIT")
    print("MODE: LOCAL PATCH + AUDIT / NO DB CALL / NO EXTERNAL UNIVERSE CALL / NO WRITE")
    print("=" * 72)

    failures: list[str] = []

    step48 = read_json(STEP48)
    readiness = read_json(READINESS)

    if step48.get("status") != "PASS":
        failures.append("Step 48 report is not PASS")
    else:
        print("PASS: Step 48 report PASS")

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

    write(CONTRACT, CONTRACT_TEXT)

    syntax_check(CONTRACT, failures)
    verify_no_runtime_integrations(CONTRACT, failures)

    namespace: dict[str, Any] = {}
    exec(compile(read(CONTRACT), str(CONTRACT), "exec"), namespace)

    builder = namespace.get("build_non_mutating_universe_snapshot")
    if not callable(builder):
        failures.append("contract builder is not callable")
        snapshot = None
    else:
        recommendation = step48.get("read_only_adapter_recommendation") or {}
        snapshot = builder(
            persisted_universe_table=None,
            persisted_universe_count=None,
            bars_symbol_count=None,
            campaign_symbol_count=None,
            locator_status=step48.get("status"),
            locator_recommendation_status=recommendation.get("status"),
        )

    if isinstance(snapshot, dict):
        for field in [
            "contract_version",
            "mode",
            "persisted_universe_available",
            "bars_symbol_universe_proxy_available",
            "full_universe_validation_complete",
            "readiness_can_advance",
            "source_status",
            "doctrine",
        ]:
            if field not in snapshot:
                failures.append(f"snapshot missing field: {field}")
            else:
                print("PASS: universe snapshot field present:", field)

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("universe snapshot readiness_can_advance must remain false")
        else:
            print("PASS: universe snapshot readiness_can_advance=False")

        if snapshot.get("persisted_universe_available") is not False:
            failures.append("persisted_universe_available should remain false without confirmed table")
        else:
            print("PASS: persisted_universe_available remains false without confirmed table")

        doctrine = snapshot.get("doctrine") or {}
        for flag in [
            "non_mutating_contract_only",
            "no_database_call",
            "no_external_universe_call",
            "no_supabase_write",
            "no_campaign_mutation",
            "no_nightly_run",
            "no_d3d",
            "no_operator_control_confirmation",
            "no_trade_signal",
            "no_stripe",
            "billing_remains_blocked",
        ]:
            if doctrine.get(flag) is not True:
                failures.append(f"doctrine flag must be true: {flag}")
            else:
                print("PASS: doctrine flag true:", flag)

    else:
        failures.append("universe snapshot did not return dict")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_PATCH_AND_AUDIT_NO_DB_CALL_NO_EXTERNAL_UNIVERSE_CALL_NO_WRITE",
        "failures": failures,
        "created": [str(CONTRACT)],
        "step48_summary": {
            "status": step48.get("status"),
            "recommendation": step48.get("read_only_adapter_recommendation"),
            "ranked_candidate_count": len(step48.get("ranked_candidates") or []),
            "safe_candidate_count": len(step48.get("safe_candidate_functions") or []),
        },
        "snapshot_preview": snapshot,
        "readiness": {
            "mutated": False,
            "campaign_pipeline_validated_current": readiness.get("campaign_pipeline_validated"),
            "campaign_pipeline_validated_can_advance_now": False,
            "reason": "Universe contract added locally only and cannot advance readiness without a persisted universe table/count.",
        },
        "repair_note": (
            "Step 49 failed because its verifier overblocked doctrine labels containing "
            "supabase/alpaca. Step 49A verifies actual runtime integration tokens instead."
        ),
        "doctrine": {
            "local_patch_only": True,
            "no_database_call": True,
            "no_external_universe_call": True,
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
    print("Report written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 49A REPAIR NON-MUTATING UNIVERSE SNAPSHOT CONTRACT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 49A COMPLETE — NON-MUTATING UNIVERSE SNAPSHOT CONTRACT CREATED")
    print("PASS: no DB call, no external universe call, no write, no mutation, no nightly run, no D3D, no trade signal, no Stripe.")
    print("NEXT: wire this contract into the coverage reader as an explicit blocker, then commit/tag.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
