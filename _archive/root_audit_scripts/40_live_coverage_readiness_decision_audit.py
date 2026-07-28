#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step40_live_coverage_readiness_decision_audit.json")

STEP39 = Path("audit_step39_live_get_only_production_coverage_reader_verification.json")
READINESS = Path("v2_readiness.json")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def as_bool(value: Any) -> bool:
    return value is True


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 40 LIVE COVERAGE READINESS DECISION AUDIT")
    print("MODE: LOCAL REPORT AUDIT ONLY / NO READINESS MUTATION / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    step39 = read_json(STEP39)
    readiness = read_json(READINESS)

    if step39.get("status") != "PASS":
        failures.append("Step 39 live coverage reader report is not PASS")
    else:
        checks.append("Step 39 live coverage reader report PASS")
        print("PASS: Step 39 report PASS")

    snapshot = step39.get("snapshot")

    if not isinstance(snapshot, dict):
        failures.append("Step 39 snapshot is missing or not an object")
        snapshot = {}

    required_readiness_before = {
        "operator_control_evidence_hardened": True,
        "legacy_fallbacks_quarantined": True,
        "campaign_pipeline_validated": False,
        "d3d_authorized": False,
        "operator_control_confirmed_by_score": False,
        "campaign_mutation_without_d3d_law": False,
    }

    for key, expected in required_readiness_before.items():
        actual = readiness.get(key)
        if actual is not expected:
            failures.append(f"readiness {key} expected {expected}, got {actual}")
        else:
            checks.append(f"readiness {key}={expected}")
            print(f"PASS: readiness {key}={expected}")

    required_snapshot_fields = [
        "coverage_reader_attempted",
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

    for field in required_snapshot_fields:
        if field not in snapshot:
            failures.append(f"snapshot missing required field: {field}")
        else:
            checks.append(f"snapshot field present: {field}")
            print("PASS: snapshot field present:", field)

    if snapshot.get("coverage_reader_attempted") is not True:
        failures.append("coverage_reader_attempted must be true")
    else:
        print("PASS: coverage_reader_attempted=True")

    if snapshot.get("readiness_can_advance") is not False:
        failures.append("snapshot readiness_can_advance must remain false before explicit readiness update")
    else:
        print("PASS: snapshot readiness_can_advance=False")

    if snapshot.get("write_path_not_executed_during_validation") is not True:
        failures.append("write_path_not_executed_during_validation must be true")
    else:
        print("PASS: write_path_not_executed_during_validation=True")

    doctrine = snapshot.get("doctrine") or {}

    for flag in [
        "no_nightly_run",
        "no_supabase_write",
        "no_campaign_mutation",
        "no_d3d",
        "no_operator_control_confirmation",
        "no_trade_signal",
        "no_stripe",
    ]:
        if doctrine.get(flag) is not True:
            failures.append(f"snapshot doctrine flag must be true: {flag}")
        else:
            print("PASS: snapshot doctrine flag true:", flag)

    validation_complete = snapshot.get("validation_complete") is True
    universe_count_ok = positive_int(snapshot.get("universe_count"))
    bars_symbols_count_ok = positive_int(snapshot.get("bars_symbols_count"))
    record_min_bars_ok = positive_int(snapshot.get("record_min_bars"))
    pagination_complete_ok = snapshot.get("pagination_complete") is True
    schema_payload_alignment_ok = snapshot.get("schema_payload_alignment") is True
    symbols_missing_bars = snapshot.get("symbols_missing_bars")

    if not isinstance(symbols_missing_bars, list):
        failures.append("symbols_missing_bars must be a list")
        missing_bars_ok = False
    else:
        missing_bars_ok = len(symbols_missing_bars) == 0

    coverage_decision_checks = {
        "validation_complete_true": validation_complete,
        "universe_count_positive": universe_count_ok,
        "bars_symbols_count_positive": bars_symbols_count_ok,
        "record_min_bars_positive": record_min_bars_ok,
        "pagination_complete_true": pagination_complete_ok,
        "schema_payload_alignment_true": schema_payload_alignment_ok,
        "symbols_missing_bars_empty": missing_bars_ok,
        "write_path_not_executed_true": snapshot.get("write_path_not_executed_during_validation") is True,
    }

    for key, value in coverage_decision_checks.items():
        if value:
            print("PASS: decision check:", key)
        else:
            warnings.append(f"coverage decision check not satisfied: {key}")
            print("WARN: decision check not satisfied:", key)

    can_update_campaign_pipeline_validated = bool(
        not failures
        and all(coverage_decision_checks.values())
    )

    if can_update_campaign_pipeline_validated:
        decision = "READY_FOR_SEPARATE_READINESS_UPDATE_TO_CAMPAIGN_PIPELINE_VALIDATED_TRUE"
    else:
        decision = "NOT_READY_FOR_READINESS_UPDATE_KEEP_CAMPAIGN_PIPELINE_VALIDATED_FALSE"

    print("\nLIVE COVERAGE VALUES")
    print("validation_complete:", snapshot.get("validation_complete"))
    print("universe_count:", snapshot.get("universe_count"))
    print("bars_symbols_count:", snapshot.get("bars_symbols_count"))
    print("record_min_bars:", snapshot.get("record_min_bars"))
    print("pagination_complete:", snapshot.get("pagination_complete"))
    print("schema_payload_alignment:", snapshot.get("schema_payload_alignment"))
    print("symbols_missing_bars_count:", len(symbols_missing_bars) if isinstance(symbols_missing_bars, list) else "INVALID")
    print("decision:", decision)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_REPORT_AUDIT_ONLY_NO_READINESS_MUTATION_NO_DATABASE_WRITE",
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "coverage_decision_checks": coverage_decision_checks,
        "decision": decision,
        "can_update_campaign_pipeline_validated": can_update_campaign_pipeline_validated,
        "live_coverage_values": {
            "validation_complete": snapshot.get("validation_complete"),
            "universe_count": snapshot.get("universe_count"),
            "bars_symbols_count": snapshot.get("bars_symbols_count"),
            "record_min_bars": snapshot.get("record_min_bars"),
            "pagination_complete": snapshot.get("pagination_complete"),
            "schema_payload_alignment": snapshot.get("schema_payload_alignment"),
            "symbols_missing_bars_count": len(symbols_missing_bars) if isinstance(symbols_missing_bars, list) else None,
            "source_tables": snapshot.get("source_tables"),
            "source_counts": snapshot.get("source_counts"),
            "read_attempts": snapshot.get("read_attempts"),
        },
        "readiness": {
            "mutated": False,
            "campaign_pipeline_validated_current": readiness.get("campaign_pipeline_validated"),
            "campaign_pipeline_validated_can_be_updated_next": can_update_campaign_pipeline_validated,
        },
        "doctrine": {
            "local_report_audit_only": True,
            "no_readiness_mutation": True,
            "no_database_write": True,
            "no_campaign_mutation": True,
            "no_nightly_run": True,
            "no_alpaca_call": True,
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
        print("FAIL: STEP 40 LIVE COVERAGE READINESS DECISION AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 40 COMPLETE — LIVE COVERAGE READINESS DECISION AUDIT PASSED")
    print("DECISION:", decision)
    print("PASS: no readiness mutation, no database write, no campaign mutation, no D3D, no trade signal, no Stripe.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
