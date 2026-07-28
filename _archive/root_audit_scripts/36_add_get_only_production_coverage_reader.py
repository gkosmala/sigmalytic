#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

REPORT = Path("audit_step36_add_get_only_production_coverage_reader.json")

READER = Path("backend/campaign_engine/campaign_pipeline_production_coverage_reader.py")
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

The reader may attempt safe Supabase REST GET/select requests when production
environment variables are available. It never calls insert, upsert, update,
delete, rpc, or any mutation endpoint.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_CAMPAIGN_PIPELINE_PRODUCTION_COVERAGE_READER_2026_07_09"

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


def _rest_get(table: str, query: str) -> dict[str, Any]:
    creds = _supabase_credentials()

    if not creds["has_url"] or not creds["has_key"]:
        return {
            "ok": False,
            "table": table,
            "reason": "missing Supabase URL or key environment variable",
            "status": None,
            "rows": [],
            "count": None,
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
            rows = json.loads(body) if body else []

            count = None
            if content_range and "/" in content_range:
                right = content_range.rsplit("/", 1)[-1]
                if right.isdigit():
                    count = int(right)

            return {
                "ok": status == 200,
                "table": table,
                "reason": None if status == 200 else f"HTTP {status}",
                "status": status,
                "rows": rows if isinstance(rows, list) else [],
                "count": count,
            }
    except Exception as exc:
        return {
            "ok": False,
            "table": table,
            "reason": str(exc),
            "status": None,
            "rows": [],
            "count": None,
        }


def _first_working_table(candidates: tuple[str, ...], query: str) -> dict[str, Any]:
    attempts = []

    for table in candidates:
        result = _rest_get(table, query)
        attempts.append({
            "table": table,
            "ok": result.get("ok"),
            "status": result.get("status"),
            "count": result.get("count"),
            "reason": result.get("reason"),
        })

        if result.get("ok"):
            result["attempts"] = attempts
            return result

    return {
        "ok": False,
        "table": None,
        "reason": "no candidate table returned a successful GET/select result",
        "status": None,
        "rows": [],
        "count": None,
        "attempts": attempts,
    }


def _extract_symbol(row: dict[str, Any]) -> str | None:
    for key in ("symbol", "ticker", "asset_symbol"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _distinct_symbols(rows: list[dict[str, Any]]) -> list[str]:
    symbols = set()

    for row in rows:
        if isinstance(row, dict):
            symbol = _extract_symbol(row)
            if symbol:
                symbols.add(symbol)

    return sorted(symbols)


def _bars_by_symbol(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        symbol = _extract_symbol(row)
        if not symbol:
            continue

        counts[symbol] = counts.get(symbol, 0) + 1

    return counts


def build_get_only_production_coverage_snapshot() -> dict[str, Any]:
    creds = _supabase_credentials()

    universe_query = "select=symbol&limit=50000"
    bars_query = "select=symbol&limit=" + str(MAX_SYMBOL_ROWS)
    campaigns_query = "select=id,symbol&limit=50000"

    universe_result = _first_working_table(UNIVERSE_TABLE_CANDIDATES, universe_query)
    bars_result = _first_working_table(BAR_TABLE_CANDIDATES, bars_query)
    campaigns_result = _first_working_table(CAMPAIGN_TABLE_CANDIDATES, campaigns_query)

    universe_symbols = _distinct_symbols(universe_result.get("rows") or [])
    bars_symbols = _distinct_symbols(bars_result.get("rows") or [])
    campaign_symbols = _distinct_symbols(campaigns_result.get("rows") or [])

    bars_by_symbol = _bars_by_symbol(bars_result.get("rows") or [])

    universe_count = len(universe_symbols) if universe_symbols else universe_result.get("count")
    bars_symbols_count = len(bars_symbols) if bars_symbols else None

    if universe_symbols and bars_symbols:
        symbols_missing_bars = sorted(set(universe_symbols) - set(bars_symbols))
    else:
        symbols_missing_bars = []

    record_min_bars = min(bars_by_symbol.values()) if bars_by_symbol else None

    pagination_complete = bool(
        bars_result.get("ok")
        and isinstance(bars_result.get("rows"), list)
        and len(bars_result.get("rows") or []) < MAX_SYMBOL_ROWS
    )

    schema_payload_alignment = bool(campaigns_result.get("ok") and campaign_symbols)

    validation_complete = bool(
        universe_count
        and bars_symbols_count
        and isinstance(record_min_bars, int)
        and pagination_complete is True
        and schema_payload_alignment is True
        and universe_symbols
    )

    readiness_can_advance = False

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "GET_ONLY_PRODUCTION_COVERAGE_READER_NO_NIGHTLY_RUN_NO_WRITE",
        "coverage_reader_attempted": True,
        "validation_complete": validation_complete,
        "readiness_can_advance": readiness_can_advance,
        "reason": (
            "GET-only production coverage reader executed. Readiness remains false "
            "until an explicit readiness update step verifies complete live coverage "
            "and billing gate remains blocked."
        ),

        "universe_count": universe_count,
        "bars_symbols_count": bars_symbols_count,
        "symbols_missing_bars": symbols_missing_bars,
        "record_min_bars": record_min_bars,
        "pagination_complete": pagination_complete,
        "schema_payload_alignment": schema_payload_alignment,
        "write_path_not_executed_during_validation": True,

        "source_tables": {
            "universe": universe_result.get("table"),
            "bars": bars_result.get("table"),
            "campaigns": campaigns_result.get("table"),
        },
        "source_counts": {
            "universe_rows": universe_result.get("count"),
            "bars_rows_returned": len(bars_result.get("rows") or []),
            "campaign_rows": campaigns_result.get("count"),
            "campaign_symbols_count": len(campaign_symbols),
        },
        "read_attempts": {
            "has_supabase_url": creds["has_url"],
            "has_supabase_key": creds["has_key"],
            "universe": universe_result.get("attempts", []),
            "bars": bars_result.get("attempts", []),
            "campaigns": campaigns_result.get("attempts", []),
        },
        "doctrine": {
            "get_only": True,
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


SNAPSHOT_TEXT = '''"""
Sigmalytic V2 — Campaign Pipeline Read-Only Validation Snapshot.

Read-only diagnostic snapshot builder.

This module does not run the nightly pipeline.
This module does not call Alpaca.
This module does not write Supabase.
This module does not mutate campaigns.
This module does not authorize D3D.
This module does not confirm operator control.
This module does not create trade signals.
This module does not touch Stripe.
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


def _source_only_snapshot() -> dict[str, Any]:
    source_presence = _source_presence()

    schema_payload_alignment = bool(
        source_presence["campaign_evaluation_present"]
        and source_presence["schema_payload_terms_present"]
        and source_presence["supabase_reference_present"]
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "SOURCE_ONLY_READ_ONLY_DIAGNOSTIC_NO_NIGHTLY_RUN_NO_WRITE",
        "coverage_reader_attempted": False,
        "validation_complete": False,
        "readiness_can_advance": False,
        "reason": (
            "Source-only read-only snapshot returned because production coverage "
            "reader was unavailable or failed safely. Production coverage counts "
            "are not confirmed."
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
            "source_only_fallback": True,
            "get_only": True,
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


def build_campaign_pipeline_read_only_validation_snapshot() -> dict[str, Any]:
    try:
        from campaign_engine.campaign_pipeline_production_coverage_reader import (
            build_get_only_production_coverage_snapshot,
        )
    except Exception:
        try:
            from backend.campaign_engine.campaign_pipeline_production_coverage_reader import (
                build_get_only_production_coverage_snapshot,
            )
        except Exception:
            return _source_only_snapshot()

    try:
        snapshot = build_get_only_production_coverage_snapshot()
    except Exception as exc:
        fallback = _source_only_snapshot()
        fallback["coverage_reader_error"] = str(exc)
        return fallback

    snapshot["required_snapshot_fields"] = list(REQUIRED_SNAPSHOT_FIELDS)
    snapshot["readiness_can_advance"] = False
    snapshot["doctrine"]["campaign_pipeline_validated_remains_false"] = True

    return snapshot


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


def syntax_check(path: Path, failures: list[str]) -> None:
    try:
        ast.parse(read(path), filename=str(path))
        print("PASS: syntax clean:", path)
    except SyntaxError as exc:
        failures.append(f"syntax failure: {path}: {exc.msg} line {exc.lineno}")


def verify_no_mutation_terms(path: Path, failures: list[str]) -> None:
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
            failures.append(f"{path} contains forbidden mutation/execution text: {term}")
        else:
            print("PASS: forbidden term absent:", path, term)


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 36 ADD GET-ONLY PRODUCTION COVERAGE READER")
    print("MODE: LOCAL PATCH + AUDIT / NO DEPLOY / NO WRITE / NO NIGHTLY RUN")
    print("=" * 72)

    failures: list[str] = []
    changes: list[str] = []

    write(READER, READER_TEXT)
    changes.append(f"wrote GET-only production coverage reader: {READER}")

    write(SNAPSHOT, SNAPSHOT_TEXT)
    changes.append(f"updated read-only snapshot builder to call coverage reader safely: {SNAPSHOT}")

    for path in [READER, SNAPSHOT, ROUTER]:
        syntax_check(path, failures)

    for path in [READER, SNAPSHOT]:
        verify_no_mutation_terms(path, failures)

    namespace: dict[str, Any] = {}
    exec(compile(read(SNAPSHOT), str(SNAPSHOT), "exec"), namespace)

    builder = namespace.get("build_campaign_pipeline_read_only_validation_snapshot")
    snapshot = builder() if callable(builder) else None

    if not isinstance(snapshot, dict):
        failures.append("snapshot builder did not return dict")
    else:
        required = [
            "universe_count",
            "bars_symbols_count",
            "symbols_missing_bars",
            "record_min_bars",
            "pagination_complete",
            "schema_payload_alignment",
            "write_path_not_executed_during_validation",
            "doctrine",
        ]

        for key in required:
            if key not in snapshot:
                failures.append(f"snapshot missing required key: {key}")
            else:
                print("PASS: snapshot key present:", key)

        if snapshot.get("readiness_can_advance") is not False:
            failures.append("snapshot readiness_can_advance must remain false")
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

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LOCAL_PATCH_AND_AUDIT_NO_DEPLOY_NO_WRITE_NO_NIGHTLY_RUN",
        "changes": changes,
        "failures": failures,
        "snapshot_preview": snapshot,
        "readiness": {
            "campaign_pipeline_validated_can_advance": False,
            "reason": "GET-only production coverage reader installed locally. Deploy/live verification required before any readiness update.",
        },
        "doctrine": {
            "local_patch_only": True,
            "no_deploy": True,
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

    for change in changes:
        print("PASS:", change)

    print("Report written:", REPORT)

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 36 GET-ONLY PRODUCTION COVERAGE READER INSTALL FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 36 COMPLETE — GET-ONLY PRODUCTION COVERAGE READER ADDED LOCALLY")
    print("PASS: no deploy, no nightly run, no write, no campaign mutation, no D3D, no operator-control confirmation, no trade signal, no Stripe.")
    print("NEXT: local verification, commit, push, then live GET verification.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
