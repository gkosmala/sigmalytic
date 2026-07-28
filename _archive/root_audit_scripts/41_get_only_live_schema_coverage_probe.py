#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT = Path("audit_step41_get_only_live_schema_coverage_probe.json")

TABLE_CANDIDATES = [
    "campaigns",
    "daily_bars",
    "alpaca_universe",
    "live_universe",
    "universe",
    "symbols",
    "market_bars",
    "bars",
    "alpaca_bars",
    "price_bars",
    "symbol_bars",
    "campaign_registry",
    "campaign_state",
]

FORBIDDEN_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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


def _get(table: str, query: str, range_header: str | None = None) -> dict[str, Any]:
    creds = _supabase_credentials()

    if not creds["has_url"] or not creds["has_key"]:
        return {
            "ok": False,
            "table": table,
            "query": query,
            "status": None,
            "reason": "missing Supabase URL or key",
            "rows": [],
            "count": None,
            "content_range": None,
        }

    base = str(creds["url"]).rstrip("/")
    endpoint = f"{base}/rest/v1/{urllib.parse.quote(table)}?{query}"

    headers = {
        "apikey": str(creds["key"]),
        "Authorization": "Bearer " + str(creds["key"]),
        "Accept": "application/json",
        "Prefer": "count=exact",
    }

    if range_header:
        headers["Range"] = range_header

    request = urllib.request.Request(
        endpoint,
        method="GET",
        headers=headers,
    )

    if request.get_method().upper() in FORBIDDEN_METHODS:
        return {
            "ok": False,
            "table": table,
            "query": query,
            "status": None,
            "reason": "blocked non-GET method",
            "rows": [],
            "count": None,
            "content_range": None,
        }

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 0) or 0)
            content_range = response.headers.get("Content-Range")

            try:
                parsed = json.loads(body) if body else []
            except Exception:
                parsed = []

            rows = parsed if isinstance(parsed, list) else []

            count = None
            if content_range and "/" in content_range:
                right = content_range.rsplit("/", 1)[-1]
                if right.isdigit():
                    count = int(right)

            return {
                "ok": status in (200, 206),
                "table": table,
                "query": query,
                "status": status,
                "reason": None if status in (200, 206) else f"HTTP {status}",
                "rows": rows,
                "count": count,
                "content_range": content_range,
            }
    except Exception as exc:
        return {
            "ok": False,
            "table": table,
            "query": query,
            "status": None,
            "reason": str(exc),
            "rows": [],
            "count": None,
            "content_range": None,
        }


def _columns_from_rows(rows: list[Any]) -> list[str]:
    columns: set[str] = set()

    for row in rows:
        if isinstance(row, dict):
            columns.update(str(key) for key in row.keys())

    return sorted(columns)


def _symbol_key(columns: list[str]) -> str | None:
    for key in ["symbol", "ticker", "asset_symbol", "asset", "name"]:
        if key in columns:
            return key
    return None


def _sample_table(table: str) -> dict[str, Any]:
    star = _get(table, "select=*&limit=3")
    columns = _columns_from_rows(star.get("rows") or [])
    symbol_key = _symbol_key(columns)

    symbol_sample = None
    symbol_count_probe = None

    if symbol_key:
        encoded_key = urllib.parse.quote(symbol_key)
        symbol_sample = _get(table, f"select={encoded_key}&limit=25")
        symbol_count_probe = {
            "symbol_key": symbol_key,
            "rows_returned": len(symbol_sample.get("rows") or []),
            "symbols_seen": sorted({
                str(row.get(symbol_key)).upper()
                for row in (symbol_sample.get("rows") or [])
                if isinstance(row, dict) and row.get(symbol_key)
            }),
        }

    return {
        "table": table,
        "ok": star.get("ok"),
        "status": star.get("status"),
        "count": star.get("count"),
        "content_range": star.get("content_range"),
        "reason": star.get("reason"),
        "columns": columns,
        "symbol_key": symbol_key,
        "sample_rows": star.get("rows"),
        "symbol_count_probe": symbol_count_probe,
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 41 GET-ONLY LIVE SCHEMA/COVERAGE PROBE")
    print("MODE: LIVE SUPABASE REST GET ONLY / NO WRITE / NO MUTATION / NO RPC")
    print("=" * 72)

    creds = _supabase_credentials()

    failures: list[str] = []

    if not creds["has_url"]:
        failures.append("missing Supabase URL env")
    else:
        print("PASS: Supabase URL env present")

    if not creds["has_key"]:
        failures.append("missing Supabase key env")
    else:
        print("PASS: Supabase key env present")

    table_results = []

    for table in TABLE_CANDIDATES:
        print(f"PROBE TABLE: {table}")
        result = _sample_table(table)
        table_results.append(result)

        print(
            "TABLE_RESULT:",
            table,
            "ok=" + str(result["ok"]),
            "status=" + str(result["status"]),
            "count=" + str(result["count"]),
            "symbol_key=" + str(result["symbol_key"]),
            "columns=" + ",".join(result["columns"][:20]),
        )

    successful_tables = [
        item for item in table_results
        if item.get("ok") is True
    ]

    candidate_tables = {
        "campaigns": [
            item for item in successful_tables
            if "campaign" in str(item.get("table", "")).lower()
        ],
        "bars": [
            item for item in successful_tables
            if "bar" in str(item.get("table", "")).lower() or item.get("table") == "daily_bars"
        ],
        "universe_or_symbols": [
            item for item in successful_tables
            if item.get("table") in {"alpaca_universe", "live_universe", "universe", "symbols"}
        ],
    }

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "LIVE_SUPABASE_REST_GET_ONLY_SCHEMA_PROBE_NO_WRITE_NO_MUTATION_NO_RPC",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "failures": failures,
        "credentials": {
            "has_supabase_url": creds["has_url"],
            "has_supabase_key": creds["has_key"],
        },
        "table_results": table_results,
        "candidate_tables": candidate_tables,
        "next_step": {
            "recommended": (
                "Patch the GET-only coverage reader to treat HTTP 206 as successful, "
                "use discovered live table columns, and derive coverage from actual successful GET/select probes."
            ),
            "readiness_can_advance_now": False,
        },
        "doctrine": {
            "live_get_only": True,
            "no_post": True,
            "no_put": True,
            "no_patch": True,
            "no_delete": True,
            "no_rpc": True,
            "no_supabase_write": True,
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
    print("Report written:", REPORT)

    print("\nSUCCESSFUL TABLES")
    for item in successful_tables:
        print(
            "SUCCESS:",
            item["table"],
            "status=" + str(item["status"]),
            "count=" + str(item["count"]),
            "symbol_key=" + str(item["symbol_key"]),
            "columns=" + ",".join(item["columns"][:30]),
        )

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 41 GET-ONLY LIVE SCHEMA/COVERAGE PROBE FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 41 COMPLETE — GET-ONLY LIVE SCHEMA/COVERAGE PROBE PASSED")
    print("PASS: no write, no mutation, no RPC, no nightly run, no D3D, no trade signal, no Stripe.")
    print("SEND SUCCESSFUL TABLES OUTPUT")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
