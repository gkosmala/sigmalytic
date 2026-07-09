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
