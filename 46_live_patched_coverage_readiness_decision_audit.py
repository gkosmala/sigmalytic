#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step46_live_patched_coverage_readiness_decision_audit.json")

STEP45 = Path("audit_step45_live_patched_http206_schema_fallback_coverage_reader_verification.json")
READINESS = Path("v2_readiness.json")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError(f"JSON root must be object: {path}")
    return data


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def prop(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return None


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 46 LIVE PATCHED COVERAGE READINESS DECISION AUDIT")
    print("MODE: LOCAL REPORT AUDIT ONLY / NO READINESS MUTATION / NO DATABASE WRITE")
    print("=" * 72)

    failures: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    step45 = read_json(STEP45)
    readiness = read_json(READINESS)

    if step45.get("status") != "PASS":
        failures.append("Step 45 live patched coverage reader report is not PASS")
    else:
        checks.append("Step 45 live patched coverage reader report PASS")
        print("PASS: Step 45 report PASS")

    snapshot = step45.get("snapshot")
    if not isinstance(snapshot, dict):
        failures.append("Step 45 snapshot is missing or not an object")
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
        "contract_version",
        "mode",
        "coverage_reader_attempted",
        "validation_complete",
        "readiness_can_advance",
        "persisted_universe_available",
        "universe_count",
        "bars_symbols_count",
        "symbols_missing_bars",
        "record_min_bars",
        "pagination_complete",
        "schema_payload_alignment",
        "write_path_not_executed_during_validation",
        "source_tables",
        "source_queries",
        "source_counts",
        "source_columns",
        "read_attempts",
        "table_summaries",
        "doctrine",
    ]

    for field in required_snapshot_fields:
        if field not in snapshot:
            failures.append(f"snapshot missing required field: {field}")
        else:
            checks.append(f"snapshot field present: {field}")
            print("PASS: snapshot field present:", field)

    mode = str(snapshot.get("mode") or "")
    if "HTTP206_SCHEMA_FALLBACKS" not in mode:
        failures.append("snapshot mode does not show HTTP206_SCHEMA_FALLBACKS patch")
    else:
        print("PASS: snapshot mode shows HTTP206_SCHEMA_FALLBACKS patch")

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
        "http_206_is_accepted_as_successful_read",
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

    source_tables = snapshot.get("source_tables") or {}
    source_counts = snapshot.get("source_counts") or {}
    source_columns = snapshot.get("source_columns") or {}

    symbols_missing_bars = snapshot.get("symbols_missing_bars")
    missing_bars_ok = isinstance(symbols_missing_bars, list) and len(symbols_missing_bars) == 0

    coverage_decision_checks = {
        "validation_complete_true": snapshot.get("validation_complete") is True,
        "persisted_universe_available_true": snapshot.get("persisted_universe_available") is True,
        "universe_count_positive": positive_int(snapshot.get("universe_count")),
        "bars_symbols_count_positive": positive_int(snapshot.get("bars_symbols_count")),
        "record_min_bars_positive": positive_int(snapshot.get("record_min_bars")),
        "pagination_complete_true": snapshot.get("pagination_complete") is True,
        "schema_payload_alignment_true": snapshot.get("schema_payload_alignment") is True,
        "symbols_missing_bars_empty": missing_bars_ok,
        "source_table_universe_present": bool(prop(source_tables, "universe")),
        "source_table_bars_present": bool(prop(source_tables, "bars")),
        "source_table_campaigns_present": bool(prop(source_tables, "campaigns")),
        "source_columns_bars_present": bool(prop(source_columns, "bars")),
        "source_columns_campaigns_present": bool(prop(source_columns, "campaigns")),
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

    print("\nLIVE PATCHED COVERAGE VALUES")
    print("validation_complete:", snapshot.get("validation_complete"))
    print("persisted_universe_available:", snapshot.get("persisted_universe_available"))
    print("universe_count:", snapshot.get("universe_count"))
    print("bars_symbols_count:", snapshot.get("bars_symbols_count"))
    print("record_min_bars:", snapshot.get("record_min_bars"))
    print("pagination_complete:", snapshot.get("pagination_complete"))
    print("schema_payload_alignment:", snapshot.get("schema_payload_alignment"))
    print("symbols_missing_bars_count:", len(symbols_missing_bars) if isinstance(symbols_missing_bars, list) else "INVALID")
    print("source_tables:", source_tables)
    print("source_counts:", source_counts)
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
        "live_patched_coverage_values": {
            "validation_complete": snapshot.get("validation_complete"),
            "persisted_universe_available": snapshot.get("persisted_universe_available"),
            "universe_count": snapshot.get("universe_count"),
            "bars_symbols_count": snapshot.get("bars_symbols_count"),
            "record_min_bars": snapshot.get("record_min_bars"),
            "pagination_complete": snapshot.get("pagination_complete"),
            "schema_payload_alignment": snapshot.get("schema_payload_alignment"),
            "symbols_missing_bars_count": len(symbols_missing_bars) if isinstance(symbols_missing_bars, list) else None,
            "source_tables": source_tables,
            "source_queries": snapshot.get("source_queries"),
            "source_counts": source_counts,
            "source_columns": source_columns,
            "read_attempts": snapshot.get("read_attempts"),
            "table_summaries": snapshot.get("table_summaries"),
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
        print("FAIL: STEP 46 LIVE PATCHED COVERAGE READINESS DECISION AUDIT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 46 COMPLETE — LIVE PATCHED COVERAGE READINESS DECISION AUDIT PASSED")
    print("DECISION:", decision)
    print("PASS: no readiness mutation, no database write, no campaign mutation, no D3D, no trade signal, no Stripe.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
