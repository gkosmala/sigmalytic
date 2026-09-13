# STEP66_PERSISTED_UNIVERSE_TABLES_WIRED_GET_ONLY
# Persisted universe source tables are read by GET/select only.
# Bars-symbol coverage remains diagnostic only and is not promoted into a universe source.
"""
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
    "campaign_universe_symbols",
    "campaign_universe_snapshots",
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
        "select=*&limit=" + str(MAX_SYMBOL_ROWS),
    )

    campaign_queries = (
        "select=*&limit=" + str(MAX_SYMBOL_ROWS),
        "select=symbol&limit=" + str(MAX_SYMBOL_ROWS),
        "select=ticker&limit=" + str(MAX_SYMBOL_ROWS),
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
