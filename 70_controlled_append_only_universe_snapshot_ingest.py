#!/usr/bin/env python3
from __future__ import annotations

"""
SIGMALYTIC V2 — CONTROLLED APPEND-ONLY UNIVERSE SNAPSHOT INGEST

Default mode is DRY-RUN ONLY.

This script does not write unless ALL of the following are true:
1. --execute is passed.
2. --authorization-phrase exactly equals:
   I explicitly authorize one append-only persisted universe snapshot ingest.
3. Supabase URL and service-role key are available locally.
4. Alpaca API credentials are available locally.
5. Preflight confirms only the two allowed persisted-universe tables are write targets.

Allowed write scope under explicit authorization:
- public.campaign_universe_snapshots: insert one snapshot header.
- public.campaign_universe_symbols: insert normalized symbols for that snapshot.

Forbidden:
- campaigns mutation
- daily_bars mutation
- readiness mutation
- D3D authorization
- operator-control confirmation
- trade signal
- Stripe/billing activation
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUTHORIZATION_PHRASE = "I explicitly authorize one append-only persisted universe snapshot ingest."

REPORT_PATH = Path("audit_step70_controlled_append_only_universe_snapshot_ingest_run.json")
READINESS_PATH = Path("v2_readiness.json")

ALLOWED_TABLES = {
    "campaign_universe_snapshots",
    "campaign_universe_symbols",
}

FORBIDDEN_TABLE_TERMS = [
    "campaigns",
    "daily_bars",
    "readiness",
    "d3d",
    "operator_control",
    "trade_signal",
    "stripe",
    "billing",
]

SOURCE_NAME = "ALPACA_ASSETS_ACTIVE_TRADABLE"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def http_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: Any | None = None,
    timeout: int = 60,
) -> tuple[int, Any]:
    body: bytes | None = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body,
        method=method,
        headers=headers or {},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            if not text:
                return int(response.status), None
            return int(response.status), json.loads(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = text
        return int(exc.code), parsed


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def load_local_env_files() -> None:
    for candidate in [
        Path(".env"),
        Path(".env.local"),
        Path(".env.production"),
        Path("backend/.env"),
        Path("backend/.env.local"),
        Path("backend/.env.production"),
    ]:
        load_env_file(candidate)


def get_env_any(names: list[str]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def fetch_alpaca_active_tradable_assets() -> list[dict[str, Any]]:
    alpaca_key, key_source = get_env_any(["ALPACA_API_KEY", "APCA_API_KEY_ID", "ALPACA_KEY_ID"])
    alpaca_secret, secret_source = get_env_any(["ALPACA_SECRET_KEY", "APCA_API_SECRET_KEY", "ALPACA_API_SECRET"])

    if not alpaca_key or not alpaca_secret:
        raise RuntimeError("missing Alpaca API credentials in local environment files or environment variables")

    # STEP72T_ALPACA_ENDPOINT_FALLBACK_ACTIVE
    # Try explicit override first, then paper, then live.
    # This remains Alpaca READ ONLY and performs no Supabase write.
    headers = {
        "APCA-API-KEY-ID": alpaca_key,
        "APCA-API-SECRET-KEY": alpaca_secret,
        "Accept": "application/json",
    }

    endpoint_candidates: list[str] = []

    explicit_base_url = os.environ.get("ALPACA_TRADING_BASE_URL") or os.environ.get("APCA_API_BASE_URL")
    if explicit_base_url:
        endpoint_candidates.append(explicit_base_url.rstrip("/") + "/v2/assets?status=active&asset_class=us_equity")

    endpoint_candidates.extend(
        [
            "https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity",
            "https://api.alpaca.markets/v2/assets?status=active&asset_class=us_equity",
        ]
    )

    last_errors: list[str] = []
    data = None
    selected_endpoint = None

    for url in endpoint_candidates:
        status, candidate_data = http_json("GET", url, headers=headers)

        if status >= 200 and status < 300 and isinstance(candidate_data, list):
            data = candidate_data
            selected_endpoint = url
            break

        last_errors.append(f"{url} -> HTTP {status}: {candidate_data}")

    if data is None:
        raise RuntimeError("Alpaca assets request failed for all endpoint candidates: " + " | ".join(last_errors))

    if not isinstance(data, list):
        raise RuntimeError("Alpaca assets response was not a list")

    filtered: list[dict[str, Any]] = []

    for asset in data:
        if not isinstance(asset, dict):
            continue

        symbol = normalize_symbol(str(asset.get("symbol") or ""))
        if not symbol:
            continue

        if asset.get("status") != "active":
            continue

        if asset.get("tradable") is not True:
            continue

        filtered.append(
            {
                "symbol": symbol,
                "asset_class": asset.get("class") or asset.get("asset_class"),
                "exchange": asset.get("exchange"),
                "status": asset.get("status"),
                "tradable": asset.get("tradable"),
                "marginable": asset.get("marginable"),
                "shortable": asset.get("shortable"),
                "easy_to_borrow": asset.get("easy_to_borrow"),
                "fractionable": asset.get("fractionable"),
                "raw_source": asset,
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for row in filtered:
        deduped[row["symbol"]] = row

    return [deduped[symbol] for symbol in sorted(deduped)]


def build_snapshot_rows(symbol_rows: list[dict[str, Any]], authorization_ref: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not symbol_rows:
        raise RuntimeError("cannot build snapshot from empty symbol universe")

    snapshot_id = str(uuid.uuid4())
    as_of_utc = utc_now()
    symbols = [row["symbol"] for row in symbol_rows]
    symbols_hash = hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()

    snapshot = {
        "snapshot_id": snapshot_id,
        "source": SOURCE_NAME,
        "as_of_utc": as_of_utc,
        "universe_count": len(symbols),
        "active_count": len(symbols),
        "tradable_count": len(symbols),
        "symbols_hash": symbols_hash,
        "created_by": "sigmalytic_v2_step70_controlled_append_only_universe_snapshot_ingest",
        "write_authorization_ref": authorization_ref,
        "is_current": True,
    }

    constituent_rows: list[dict[str, Any]] = []

    for row in symbol_rows:
        constituent_rows.append(
            {
                "snapshot_id": snapshot_id,
                "symbol": row["symbol"],
                "asset_class": row.get("asset_class"),
                "exchange": row.get("exchange"),
                "status": row.get("status"),
                "tradable": row.get("tradable"),
                "marginable": row.get("marginable"),
                "shortable": row.get("shortable"),
                "easy_to_borrow": row.get("easy_to_borrow"),
                "fractionable": row.get("fractionable"),
                "raw_source": row.get("raw_source"),
            }
        )

    return snapshot, constituent_rows


def supabase_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def post_supabase_rows(base_url: str, service_key: str, table: str, rows: list[dict[str, Any]] | dict[str, Any]) -> tuple[int, Any]:
    if table not in ALLOWED_TABLES:
        raise RuntimeError(f"write target is not allowed: {table}")

    for forbidden in FORBIDDEN_TABLE_TERMS:
        if forbidden in table:
            raise RuntimeError(f"forbidden write target term detected in table name: {table}")

    url = f"{base_url.rstrip('/')}/rest/v1/{urllib.parse.quote(table)}"
    return http_json("POST", url, headers=supabase_headers(service_key), payload=rows)


def chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def validate_readiness_blocked() -> list[str]:
    failures: list[str] = []

    readiness = read_json(READINESS_PATH)

    required_false = [
        "campaign_pipeline_validated",
        "d3d_authorized",
        "operator_control_confirmed_by_score",
        "campaign_mutation_without_d3d_law",
    ]

    for key in required_false:
        if readiness.get(key) is not False:
            failures.append(f"readiness field must remain false: {key}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="perform the explicitly authorized append-only ingest")
    parser.add_argument("--authorization-phrase", default="", help="required exact phrase for write execution")
    parser.add_argument("--authorization-ref", default="STEP70_USER_AUTHORIZATION_PENDING", help="authorization reference stored in snapshot")
    parser.add_argument("--dry-run-limit", type=int, default=10)
    args = parser.parse_args()

    load_local_env_files()

    failures: list[str] = []
    warnings: list[str] = []
    started_at = utc_now()

    readiness_failures = validate_readiness_blocked()
    failures.extend(readiness_failures)

    execute_allowed = args.execute and args.authorization_phrase == AUTHORIZATION_PHRASE

    if args.execute and args.authorization_phrase != AUTHORIZATION_PHRASE:
        failures.append("execute requested but authorization phrase did not match exactly")

    supabase_url, supabase_url_source = get_env_any(["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"])
    service_key, service_key_source = get_env_any(["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"])

    if args.execute:
        if not supabase_url:
            failures.append("execute requested but SUPABASE_URL/NEXT_PUBLIC_SUPABASE_URL is unavailable")
        if not service_key:
            failures.append("execute requested but SUPABASE_SERVICE_ROLE_KEY is unavailable")

    symbol_rows: list[dict[str, Any]] = []
    snapshot: dict[str, Any] | None = None
    constituent_rows: list[dict[str, Any]] = []

    try:
        symbol_rows = fetch_alpaca_active_tradable_assets()
        snapshot, constituent_rows = build_snapshot_rows(symbol_rows, args.authorization_ref)
    except Exception as exc:
        failures.append(str(exc))

    if snapshot and snapshot["universe_count"] <= 0:
        failures.append("universe_count must be positive")

    if snapshot and snapshot["universe_count"] != len(constituent_rows):
        failures.append("universe_count must equal constituent row count")

    if not execute_allowed:
        if args.execute:
            warnings.append("execution requested but blocked by failed preflight/authorization")
        else:
            warnings.append("dry run only; no Supabase write attempted")

    write_attempted = False
    write_results: list[dict[str, Any]] = []

    if execute_allowed and not failures and supabase_url and service_key and snapshot:
        write_attempted = True

        # Insert snapshot header first.
        status, data = post_supabase_rows(supabase_url, service_key, "campaign_universe_snapshots", snapshot)
        write_results.append({"table": "campaign_universe_snapshots", "status": status, "response": data})

        if status < 200 or status >= 300:
            failures.append(f"snapshot header insert failed with HTTP {status}: {data}")
        else:
            for index, batch in enumerate(chunked(constituent_rows, 500), start=1):
                status, data = post_supabase_rows(supabase_url, service_key, "campaign_universe_symbols", batch)
                write_results.append({"table": "campaign_universe_symbols", "batch": index, "status": status})

                if status < 200 or status >= 300:
                    failures.append(f"symbol batch {index} insert failed with HTTP {status}: {data}")
                    break

                time.sleep(0.1)

    report = {
        "status": "PASS" if not failures else "FAIL",
        "mode": "EXECUTE_APPEND_ONLY_INGEST" if execute_allowed else "DRY_RUN_ONLY_NO_SUPABASE_WRITE",
        "started_at": started_at,
        "ended_at": utc_now(),
        "failures": failures,
        "warnings": warnings,
        "execute_requested": bool(args.execute),
        "execute_allowed": bool(execute_allowed and not failures),
        "write_attempted": write_attempted,
        "allowed_tables": sorted(ALLOWED_TABLES),
        "source": SOURCE_NAME,
        "supabase_url_available": bool(supabase_url),
        "supabase_url_source": supabase_url_source,
        "service_role_key_available": bool(service_key),
        "service_role_key_source": service_key_source,
        "snapshot_preview": snapshot,
        "symbol_count": len(symbol_rows),
        "dry_run_symbols_preview": [row["symbol"] for row in symbol_rows[: args.dry_run_limit]],
        "write_results": write_results,
        "readiness": {
            "mutated": False,
            "campaign_pipeline_validated_can_advance_now": False,
            "billing_remains_blocked": True,
        },
        "doctrine": {
            "append_only_ingest": True,
            "write_gate_requires_exact_authorization_phrase": True,
            "no_campaign_mutation": True,
            "no_daily_bars_mutation": True,
            "no_readiness_advance": True,
            "no_nightly_run": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if failures:
        print("FAIL: CONTROLLED UNIVERSE SNAPSHOT INGEST PRECHECK/RUN FAILED")
        for failure in failures:
            print("FAIL:", failure)
        print("REPORT:", REPORT_PATH)
        return 1

    if write_attempted:
        print("PASS: CONTROLLED APPEND-ONLY UNIVERSE SNAPSHOT INGEST EXECUTED")
    else:
        print("PASS: CONTROLLED APPEND-ONLY UNIVERSE SNAPSHOT INGEST DRY RUN COMPLETE")

    print("REPORT:", REPORT_PATH)
    print("SYMBOL_COUNT:", len(symbol_rows))
    print("WRITE_ATTEMPTED:", write_attempted)
    print("campaign_pipeline_validated remains false; billing remains blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

