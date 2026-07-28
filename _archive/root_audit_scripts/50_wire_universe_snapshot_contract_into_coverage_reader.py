#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step50_wire_universe_snapshot_contract_into_coverage_reader.json")

STEP49A = Path("audit_step49a_repair_non_mutating_universe_snapshot_contract.json")
READINESS = Path("v2_readiness.json")

READER = Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py")
CONTRACT = Path("backend/campaign_engine/campaign_pipeline_universe_snapshot_contract.py")
SNAPSHOT = Path("backend/campaign_engine/campaign_pipeline_read_only_validation_snapshot.py")
ROUTER = Path("backend/campaign_pipeline_validation_api.py")

READER_TEXT = '''"""
Sigmalytic V2 — Campaign Pipeline Production Coverage Reader.

GET-only read/select diagnostics.

This module does not run the nightly pipeline.
This module does not call Alpaca.
This module does not write Supabase.
This module does not mutate campaigns.
This module does not authorize D3D.
This module does not confirm operator control.
This module does not create trade signals.
This module does not touch Stripe.

Important live behavior:
    Supabase REST may return HTTP 206 Partial Content for successful ranged
    GET/select requests. HTTP 206 is accepted as a successful read response.

Universe-source doctrine:
    A persisted universe source is required for full campaign pipeline
    validation. Bars-symbol coverage is diagnostic only and cannot silently
    replace the live/persisted universe source.

Readiness remains false until a separate explicit readiness-update audit.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_CAMPAIGN_PIPELINE_PRODUCTION_COVERAGE_READER_2026_07_09_UNIVERSE_CONTRACT"

MAX_SYMBOL_ROWS = 50000

CAMPAIGN_TABLE_CANDIDATES = (
    "campaigns",
    "campaign_registry",
    "campaign_state",
)

BAR_TABLE_CANDIDATES = (
    "daily_bars",
    "market_bars",
    "bars",
    "alpaca_bars",
    "price_bars",
    "symbol_bars",
)

UNIVERSE_TABLE_CANDIDATES = (
    "alpaca_universe",
    "live_universe",
    "universe",
    "symbols",
)

SYMBOL_KEYS = (
    "symbol",
    "ticker",
    "asset_symbol",
    "asset",
    "name",
)


def _build_universe_contract_snapshot(**kwargs: Any) -> dict[str, Any]:
    try:
        from campaign_engine.campaign_pipeline_universe_snapshot_contract import (
            build_non_mutating_universe_snapshot,
        )
    except Exception:
        try:
            from backend.campaign_engine.campaign_pipeline_universe_snapshot_contract import (
                build_non_mutating_universe_snapshot,
            )
        except Exception as exc:
            return {
                "contract_available": False,
                "error": str(exc),
                "readiness_can_advance": False,
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
                },
            }

    snapshot = build_non_mutating_universe_snapshot(**kwargs)
    snapshot["contract_available"] = True
    snapshot["readiness_can_advance"] = False
    return snapshot


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _supabase_credentials() -> dict[str, Any]:
    url = (
        _env("SUPABASE_URL")
        or _env("VITE_SUPABASE_URL")
        or _env("NEXT_PUBLIC_SUPABASE_URL")
    )

    key = (
        _env("SUPABASE_SERVICE_ROLE_KEY")
        or _env("SUPABASE_SERVICE_KEY")
        or _env("SUPABASE_ANON_KEY")
        or _env("VITE_SUPABASE_ANON_KEY")
        or _env("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )

    return {
        "has_url": bool(url),
        "has_key": bool(key),
        "url": url,
        "key": key,
    }


def _content_range_count(content_range: str | None) -> int | None:
    if not content_range or "/" not in content_range:
        return None

    right = content_range.rsplit("/", 1)[-1]
    if right.isdigit():
        return int(right)

    return None


def _rest_get(table: str, query: str) -> dict[str, Any]:
    creds = _supabase_credentials()

    if not creds["has_url"] or not creds["has_key"]:
        return {
            "ok": False,
            "table": table,
            "query": query,
            "reason": "missing Supabase URL or key environment variable",
            "status": None,
            "rows": [],
            "count": None,
            "content_range": None,
            "columns": [],
        }

    base = str(creds["url"]).rstrip("/")
    endpoint = f"{base}/rest/v1/{urllib.parse.quote(table)}?{query}"

    request = urllib.request.Request(
        endpoint,
        method="GET",
        headers={
            "apikey": str(creds["key"]),
            "Authorization": "Bearer " + str(creds["key"]),
            "Accept": "application/json",
            "Prefer": "count=exact",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 0) or 0)
            content_range = response.headers.get("Content-Range")
            parsed = json.loads(body) if body else []
            rows = parsed if isinstance(parsed, list) else []
            columns = _columns_from_rows(rows)

            return {
                "ok": status in (200, 206),
                "table": table,
                "query": query,
                "reason": None if status in (200, 206) else f"HTTP {status}",
                "status": status,
                "rows": rows,
                "count": _content_range_count(content_range),
                "content_range": content_range,
                "columns": columns,
            }
    except Exception as exc:
        return {
            "ok": False,
            "table": table,
            "query": query,
            "reason": str(exc),
            "status": None,
            "rows": [],
            "count": None,
            "content_range": None,
            "columns": [],
        }


def _columns_from_rows(rows: list[Any]) -> list[str]:
    columns: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        for key in row.keys():
            columns.add(str(key))

    return sorted(columns)


def _symbol_key(columns: list[str]) -> str | None:
    for key in SYMBOL_KEYS:
        if key in columns:
            return key
    return None


def _first_working_table(candidates: tuple[str, ...], queries: tuple[str, ...]) -> dict[str, Any]:
    attempts = []

    for table in candidates:
        for query in queries:
            result = _rest_get(table, query)

            attempts.append({
                "table": table,
                "query": query,
                "ok": result.get("ok"),
                "status": result.get("status"),
                "count": result.get("count"),
                "reason": result.get("reason"),
                "columns": result.get("columns"),
            })

            if result.get("ok"):
                result["attempts"] = attempts
                return result

    return {
        "ok": False,
        "table": None,
        "query": None,
        "reason": "no candidate table/query returned a successful GET/select result",
        "status": None,
        "rows": [],
        "count": None,
        "content_range": None,
        "columns": [],
        "attempts": attempts,
    }


def _extract_symbol(row: dict[str, Any], preferred_key: str | None = None) -> str | None:
    keys = [preferred_key] if preferred_key else []
    keys.extend([key for key in SYMBOL_KEYS if key not in keys])

    for key in keys:
        if not key:
            continue

        value = row.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip().upper()

    return None


def _distinct_symbols(rows: list[dict[str, Any]], preferred_key: str | None = None) -> list[str]:
    symbols = set()

    for row in rows:
        if isinstance(row, dict):
            symbol = _extract_symbol(row, preferred_key=preferred_key)
            if symbol:
                symbols.add(symbol)

    return sorted(symbols)


def _bars_by_symbol(rows: list[dict[str, Any]], preferred_key: str | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        symbol = _extract_symbol(row, preferred_key=preferred_key)
        if not symbol:
            continue

        counts[symbol] = counts.get(symbol, 0) + 1

    return counts


def _table_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": result.get("table"),
        "query": result.get("query"),
        "ok": result.get("ok"),
        "status": result.get("status"),
        "count": result.get("count"),
        "content_range": result.get("content_range"),
        "columns": result.get("columns"),
        "reason": result.get("reason"),
    }


def build_get_only_production_coverage_snapshot() -> dict[str, Any]:
    creds = _supabase_credentials()

    symbol_select_queries = (
        "select=symbol&limit=" + str(MAX_SYMBOL_ROWS),
        "select=ticker&limit=" + str(MAX_SYMBOL_ROWS),
        "select=asset_symbol&limit=" + str(MAX_SYMBOL_ROWS),
        "select=*&limit=1000",
    )

    campaign_queries = (
        "select=*&limit=1000",
        "select=symbol&limit=1000",
        "select=ticker&limit=1000",
    )

    universe_result = _first_working_table(UNIVERSE_TABLE_CANDIDATES, symbol_select_queries)
    bars_result = _first_working_table(BAR_TABLE_CANDIDATES, symbol_select_queries)
    campaigns_result = _first_working_table(CAMPAIGN_TABLE_CANDIDATES, campaign_queries)

    universe_symbol_key = _symbol_key(universe_result.get("columns") or [])
    bars_symbol_key = _symbol_key(bars_result.get("columns") or [])
    campaign_symbol_key = _symbol_key(campaigns_result.get("columns") or [])

    universe_symbols = _distinct_symbols(universe_result.get("rows") or [], preferred_key=universe_symbol_key)
    bars_symbols = _distinct_symbols(bars_result.get("rows") or [], preferred_key=bars_symbol_key)
    campaign_symbols = _distinct_symbols(campaigns_result.get("rows") or [], preferred_key=campaign_symbol_key)

    bars_by_symbol = _bars_by_symbol(bars_result.get("rows") or [], preferred_key=bars_symbol_key)

    universe_count = len(universe_symbols) if universe_symbols else universe_result.get("count")
    bars_symbols_count = len(bars_symbols) if bars_symbols else None

    persisted_universe_available = bool(universe_result.get("ok") and universe_symbols)

    if persisted_universe_available and bars_symbols:
        symbols_missing_bars = sorted(set(universe_symbols) - set(bars_symbols))
    else:
        symbols_missing_bars = []

    record_min_bars = min(bars_by_symbol.values()) if bars_by_symbol else None

    pagination_complete = bool(
        bars_result.get("ok")
        and bars_result.get("status") in (200, 206)
        and isinstance(bars_result.get("rows"), list)
        and len(bars_result.get("rows") or []) < MAX_SYMBOL_ROWS
    )

    schema_payload_alignment = bool(campaigns_result.get("ok") and campaigns_result.get("columns"))

    universe_contract_snapshot = _build_universe_contract_snapshot(
        persisted_universe_table=universe_result.get("table") if persisted_universe_available else None,
        persisted_universe_count=universe_count if persisted_universe_available else None,
        bars_symbol_count=bars_symbols_count,
        campaign_symbol_count=len(campaign_symbols),
        locator_status="PASS",
        locator_recommendation_status="UNIVERSE_SOURCE_BLOCKER_EXPLICIT",
    )

    full_universe_validation_complete = bool(
        universe_contract_snapshot.get("full_universe_validation_complete") is True
    )

    validation_complete = bool(
        full_universe_validation_complete
        and universe_count
        and bars_symbols_count
        and isinstance(record_min_bars, int)
        and pagination_complete is True
        and schema_payload_alignment is True
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "GET_ONLY_PRODUCTION_COVERAGE_READER_WITH_NON_MUTATING_UNIVERSE_CONTRACT_NO_NIGHTLY_RUN_NO_WRITE",
        "coverage_reader_attempted": True,
        "validation_complete": validation_complete,
        "readiness_can_advance": False,
        "reason": (
            "GET-only production coverage reader executed with HTTP 206 support, schema fallback probes, "
            "and explicit non-mutating universe-source contract. Readiness remains false unless a persisted "
            "universe source is confirmed by the universe contract."
        ),

        "universe_count": universe_count,
        "bars_symbols_count": bars_symbols_count,
        "symbols_missing_bars": symbols_missing_bars,
        "record_min_bars": record_min_bars,
        "pagination_complete": pagination_complete,
        "schema_payload_alignment": schema_payload_alignment,
        "write_path_not_executed_during_validation": True,

        "persisted_universe_available": persisted_universe_available,
        "full_universe_validation_complete": full_universe_validation_complete,
        "universe_contract_snapshot": universe_contract_snapshot,

        "source_tables": {
            "universe": universe_result.get("table"),
            "bars": bars_result.get("table"),
            "campaigns": campaigns_result.get("table"),
        },
        "source_queries": {
            "universe": universe_result.get("query"),
            "bars": bars_result.get("query"),
            "campaigns": campaigns_result.get("query"),
        },
        "source_counts": {
            "universe_rows": universe_result.get("count"),
            "bars_rows_total_count": bars_result.get("count"),
            "bars_rows_returned": len(bars_result.get("rows") or []),
            "campaign_rows_total_count": campaigns_result.get("count"),
            "campaign_rows_returned": len(campaigns_result.get("rows") or []),
            "campaign_symbols_count": len(campaign_symbols),
        },
        "source_columns": {
            "universe": universe_result.get("columns"),
            "bars": bars_result.get("columns"),
            "campaigns": campaigns_result.get("columns"),
        },
        "read_attempts": {
            "has_supabase_url": creds["has_url"],
            "has_supabase_key": creds["has_key"],
            "universe": universe_result.get("attempts", []),
            "bars": bars_result.get("attempts", []),
            "campaigns": campaigns_result.get("attempts", []),
        },
        "table_summaries": {
            "universe": _table_summary(universe_result),
            "bars": _table_summary(bars_result),
            "campaigns": _table_summary(campaigns_result),
        },
        "doctrine": {
            "get_only": True,
            "http_206_is_accepted_as_successful_read": True,
            "non_mutating_universe_contract_wired": True,
            "bars_symbol_universe_proxy_is_diagnostic_only": True,
            "no_nightly_run": True,
            "no_alpaca_call_from_this_reader": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "campaign_pipeline_validated_remains_false_until_explicit_readiness_update": True,
        },
    }


__all__ = [
    "CONTRACT_VERSION",
    "build_get_only_production_coverage_snapshot",
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
    path.write_text(text, encoding="utf-8")


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


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
    print("SIGMALYTIC V2 — STEP 50 WIRE UNIVERSE SNAPSHOT CONTRACT")
    print("MODE: LOCAL PATCH + AUDIT / NO DEPLOY / NO WRITE / NO NIGHTLY RUN")
    print("=" * 72)

    failures: list[str] = []

    step49a = read_json(STEP49A)
    readiness = read_json(READINESS)

    if step49a.get("status") != "PASS":
        failures.append("Step 49A report is not PASS")
    else:
        print("PASS: Step 49A report PASS")

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

    write(READER, READER_TEXT)

    for path in [READER, CONTRACT, SNAPSHOT, ROUTER]:
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
            "_build_universe_contract_snapshot",
            "build_non_mutating_universe_snapshot",
            "universe_contract_snapshot",
            "full_universe_validation_complete",
            "bars_symbol_universe_proxy_is_diagnostic_only",
            "non_mutating_universe_contract_wired",
            "GET_ONLY_PRODUCTION_COVERAGE_READER_WITH_NON_MUTATING_UNIVERSE_CONTRACT",
        ],
        failures,
    )

    namespace: dict[str, Any] = {}
    exec(compile(read(READER), str(READER), "exec"), namespace)

    builder = namespace.get("build_get_only_production_coverage_snapshot")
    if not callable(builder):
        failures.append("coverage reader builder is not callable")
        snapshot = None
    else:
        snapshot = builder()

    if isinstance(snapshot, dict):
        for field in [
            "contract_version",
            "mode",
            "validation_complete",
            "readiness_can_advance",
            "persisted_universe_available",
            "full_universe_validation_complete",
            "universe_contract_snapshot",
            "doctrine",
        ]:
            if field not in snapshot:
                failures.append(f"snapshot missing field: {field}")
            else:
                print("PASS: snapshot field present:", field)

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("readiness_can_advance must remain false")
        else:
            print("PASS: readiness_can_advance=False")

        if "NON_MUTATING_UNIVERSE_CONTRACT" not in str(snapshot.get("mode")):
            failures.append("snapshot mode does not show universe contract wiring")
        else:
            print("PASS: snapshot mode shows universe contract wiring")

        doctrine = snapshot.get("doctrine") or {}
        if doctrine.get("non_mutating_universe_contract_wired") is not True:
            failures.append("non_mutating_universe_contract_wired doctrine flag must be true")
        else:
            print("PASS: non_mutating_universe_contract_wired=True")

        if doctrine.get("bars_symbol_universe_proxy_is_diagnostic_only") is not True:
            failures.append("bars_symbol_universe_proxy_is_diagnostic_only doctrine flag must be true")
        else:
            print("PASS: bars_symbol_universe_proxy_is_diagnostic_only=True")

        contract_snapshot = snapshot.get("universe_contract_snapshot")
        if not isinstance(contract_snapshot, dict):
            failures.append("universe_contract_snapshot must be object")
        else:
            print("PASS: universe_contract_snapshot is object")

            if contract_snapshot.get("readiness_can_advance") is not False:
                failures.append("universe_contract_snapshot readiness_can_advance must remain false")
            else:
                print("PASS: universe_contract_snapshot readiness_can_advance=False")
    else:
        failures.append("coverage reader snapshot did not return dict")

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_PATCH_AND_AUDIT_NO_DEPLOY_NO_WRITE_NO_NIGHTLY_RUN",
        "failures": failures,
        "changed": [str(READER)],
        "snapshot_preview": snapshot,
        "readiness": {
            "mutated": False,
            "campaign_pipeline_validated_current": readiness.get("campaign_pipeline_validated"),
            "campaign_pipeline_validated_can_advance_now": False,
            "reason": "Universe contract wired locally. Live deploy/GET verification required; readiness still false.",
        },
        "doctrine": {
            "local_patch_only": True,
            "get_only_reader": True,
            "non_mutating_universe_contract_wired": True,
            "bars_symbol_universe_proxy_is_diagnostic_only": True,
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
        print("FAIL: STEP 50 WIRE UNIVERSE SNAPSHOT CONTRACT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 50 COMPLETE — UNIVERSE SNAPSHOT CONTRACT WIRED INTO COVERAGE READER LOCALLY")
    print("PASS: readiness remains false; billing remains blocked pending commit/push/live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
