from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ENGINE = "D4E1_READ_ONLY_BAR_SOURCE_CONFIGURATION_DIAGNOSTIC"
VERSION = "phase_d4e1_read_only_bar_source_configuration_diagnostic_v1"

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
D3V_ENDPOINT = "/api/campaign/d3d-dry-run-candidate-preflight-review"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.market_data.read_only_ohlcv_adapter import (  # noqa: E402
    load_read_only_ohlcv_bars_for_d4b_candidate,
)


ENV_FILES = [
    ROOT / ".env",
    ROOT / ".env.local",
    ROOT / "backend" / ".env",
    ROOT / "backend" / ".env.local",
]

SUPABASE_URL_KEYS = ["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"]
SUPABASE_KEY_KEYS = [
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
]

ALPACA_KEY_KEYS = [
    "ALPACA_API_KEY",
    "ALPACA_API_KEY_ID",
    "APCA_API_KEY_ID",
    "APCA_API_KEY",
]

ALPACA_SECRET_KEYS = [
    "ALPACA_SECRET_KEY",
    "ALPACA_API_SECRET",
    "APCA_API_SECRET_KEY",
    "APCA_API_SECRET",
]

SUPABASE_TABLE_CANDIDATES = [
    "daily_bars",
    "market_data_bars",
    "historical_bars",
    "stock_bars",
    "bars",
    "sip_daily_bars",
    "alpaca_bars",
    "ohlcv_bars",
    "price_bars",
    "cached_daily_bars",
    "cached_ohlcv_bars",
]


def _load_env_files() -> List[Dict[str, Any]]:
    loaded: List[Dict[str, Any]] = []

    for path in ENV_FILES:
        record = {
            "path": str(path.relative_to(ROOT)) if path.exists() else str(path),
            "exists": path.exists(),
            "loaded_key_count": 0,
        }

        if not path.exists():
            loaded.append(record)
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            record["read_error"] = f"{type(exc).__name__}: {exc}"
            loaded.append(record)
            continue

        loaded_count = 0

        for raw_line in lines:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and value and key not in os.environ:
                os.environ[key] = value
                loaded_count += 1

        record["loaded_key_count"] = loaded_count
        loaded.append(record)

    return loaded


def _env_presence(keys: List[str]) -> Dict[str, Any]:
    present_keys = []

    for key in keys:
        value = os.environ.get(key)

        if value:
            present_keys.append({
                "key": key,
                "present": True,
                "length": len(value),
                "prefix_only": value[:4] + "***" if len(value) >= 4 else "***",
            })

    return {
        "any_present": bool(present_keys),
        "present_keys": present_keys,
        "missing_keys": [key for key in keys if not os.environ.get(key)],
    }


def _env_first(keys: List[str]) -> Optional[str]:
    for key in keys:
        value = os.environ.get(key)

        if value:
            return value.strip()

    return None


def _fetch_json(path: str, timeout_seconds: int = 120) -> Dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D4E1-Read-Only-Bar-Source-Diagnostic/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")

    payload = json.loads(raw)

    if not isinstance(payload, dict):
        raise RuntimeError("D3V endpoint returned non-object JSON.")

    return payload


def _rows_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ["rows", "review_rows", "validation_rows", "campaign_rows", "results", "items", "data"]:
        value = payload.get(key)

        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}

    return bool(value)


def _sanitize_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    text = text.replace(os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("SUPABASE_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("SUPABASE_ANON_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("ALPACA_API_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("ALPACA_API_KEY_ID", ""), "[REDACTED]")
    text = text.replace(os.environ.get("APCA_API_KEY_ID", ""), "[REDACTED]")
    text = text.replace(os.environ.get("APCA_API_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("ALPACA_SECRET_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("ALPACA_API_SECRET", ""), "[REDACTED]")
    text = text.replace(os.environ.get("APCA_API_SECRET_KEY", ""), "[REDACTED]")
    text = text.replace(os.environ.get("APCA_API_SECRET", ""), "[REDACTED]")
    return text[:500]


def _supabase_probe(candidate_symbols: List[str]) -> Dict[str, Any]:
    supabase_url = _env_first(SUPABASE_URL_KEYS)
    supabase_key = _env_first(SUPABASE_KEY_KEYS)

    if not supabase_url or not supabase_key:
        return {
            "status": "SUPABASE_PROBE_BLOCKED_ENV_MISSING",
            "reason": "SUPABASE_URL/NEXT_PUBLIC_SUPABASE_URL and readable Supabase key were not both present locally.",
            "tables_checked": [],
        }

    base_url = supabase_url.rstrip("/")
    headers = {
        "Accept": "application/json",
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Prefer": "count=exact",
        "User-Agent": "Sigmalytic-D4E1-Read-Only-Bar-Source-Diagnostic/1.0",
    }

    explicit_table = os.environ.get("D4E_SUPABASE_BARS_TABLE") or os.environ.get("SIGMALYTIC_BAR_TABLE") or os.environ.get("SUPABASE_BARS_TABLE")
    tables = []

    if explicit_table:
        tables.append(explicit_table)

    for table in SUPABASE_TABLE_CANDIDATES:
        if table not in tables:
            tables.append(table)

    checked = []

    for table in tables:
        query = urllib.parse.urlencode({
            "select": "*",
            "limit": "1",
        })

        url = f"{base_url}/rest/v1/{urllib.parse.quote(table)}?{query}"
        request = urllib.request.Request(url, headers=headers, method="GET")

        record: Dict[str, Any] = {
            "table": table,
            "reachable": False,
            "sample_row_returned": False,
            "sample_columns": [],
            "symbol_column_present": False,
            "ohlcv_like_columns_present": [],
            "candidate_symbol_probe": None,
        }

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", None)
        except Exception as exc:
            record["error"] = _sanitize_error(exc)
            checked.append(record)
            continue

        record["reachable"] = True
        record["http_status"] = status_code

        try:
            payload = json.loads(raw)
        except Exception as exc:
            record["error"] = f"non-json response: {_sanitize_error(exc)}"
            checked.append(record)
            continue

        if isinstance(payload, list) and payload:
            first = payload[0]

            if isinstance(first, dict):
                columns = sorted(first.keys())
                record["sample_row_returned"] = True
                record["sample_columns"] = columns[:50]
                record["symbol_column_present"] = "symbol" in columns
                record["ohlcv_like_columns_present"] = [
                    col for col in ["timestamp", "time", "date", "datetime", "open", "high", "low", "close", "volume", "o", "h", "l", "c", "v"]
                    if col in columns
                ]

        if candidate_symbols:
            symbol = candidate_symbols[0]
            symbol_query = urllib.parse.urlencode({
                "select": "*",
                "symbol": f"eq.{symbol}",
                "limit": "1",
            })
            symbol_url = f"{base_url}/rest/v1/{urllib.parse.quote(table)}?{symbol_query}"
            symbol_request = urllib.request.Request(symbol_url, headers=headers, method="GET")

            symbol_record = {
                "symbol": symbol,
                "row_returned": False,
            }

            try:
                with urllib.request.urlopen(symbol_request, timeout=20) as response:
                    symbol_raw = response.read().decode("utf-8", errors="replace")
                symbol_payload = json.loads(symbol_raw)
                symbol_record["row_returned"] = isinstance(symbol_payload, list) and bool(symbol_payload)
            except Exception as exc:
                symbol_record["error"] = _sanitize_error(exc)

            record["candidate_symbol_probe"] = symbol_record

        checked.append(record)

    reachable_tables = [item["table"] for item in checked if item.get("reachable")]
    tables_with_sample_rows = [item["table"] for item in checked if item.get("sample_row_returned")]
    tables_with_ohlcv_columns = [
        item["table"]
        for item in checked
        if len(item.get("ohlcv_like_columns_present") or []) >= 5
    ]

    if tables_with_ohlcv_columns:
        status = "SUPABASE_PROBE_FOUND_REACHABLE_OHLCV_LIKE_TABLE"
    elif reachable_tables:
        status = "SUPABASE_PROBE_FOUND_REACHABLE_TABLES_BUT_NO_CONFIRMED_OHLCV_SCHEMA"
    else:
        status = "SUPABASE_PROBE_NO_REACHABLE_CANDIDATE_TABLES"

    return {
        "status": status,
        "reachable_tables": reachable_tables,
        "tables_with_sample_rows": tables_with_sample_rows,
        "tables_with_ohlcv_like_columns": tables_with_ohlcv_columns,
        "tables_checked": checked,
    }


def _alpaca_probe(candidate_symbols: List[str]) -> Dict[str, Any]:
    key = _env_first(ALPACA_KEY_KEYS)
    secret = _env_first(ALPACA_SECRET_KEYS)

    if not key or not secret:
        return {
            "status": "ALPACA_PROBE_BLOCKED_ENV_MISSING",
            "reason": "Alpaca key and secret were not both present locally.",
            "feeds_checked": [],
        }

    symbols = []

    if candidate_symbols:
        symbols.append(candidate_symbols[0])

    symbols.append("SPY")

    unique_symbols = []

    for symbol in symbols:
        symbol = str(symbol).strip().upper()

        if symbol and symbol not in unique_symbols:
            unique_symbols.append(symbol)

    end_dt = datetime.now(timezone.utc).replace(microsecond=0)
    start_dt = end_dt - timedelta(days=45)

    feeds = [
        feed.strip()
        for feed in os.environ.get("D4E_ALPACA_FEEDS", "sip,iex").split(",")
        if feed.strip()
    ]

    checked = []

    for symbol in unique_symbols:
        for feed in feeds:
            params = urllib.parse.urlencode({
                "symbols": symbol,
                "timeframe": "1Day",
                "start": start_dt.isoformat().replace("+00:00", "Z"),
                "end": end_dt.isoformat().replace("+00:00", "Z"),
                "limit": "5",
                "adjustment": "raw",
                "feed": feed,
            })

            url = f"https://data.alpaca.markets/v2/stocks/bars?{params}"
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "APCA-API-KEY-ID": key,
                    "APCA-API-SECRET-KEY": secret,
                    "User-Agent": "Sigmalytic-D4E1-Read-Only-Bar-Source-Diagnostic/1.0",
                },
                method="GET",
            )

            record = {
                "symbol": symbol,
                "feed": feed,
                "reachable": False,
                "bars_returned": 0,
            }

            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                    record["http_status"] = getattr(response, "status", None)
            except Exception as exc:
                record["error"] = _sanitize_error(exc)
                checked.append(record)
                continue

            record["reachable"] = True

            try:
                payload = json.loads(raw)
            except Exception as exc:
                record["error"] = f"non-json response: {_sanitize_error(exc)}"
                checked.append(record)
                continue

            bars = []

            if isinstance(payload, dict) and isinstance(payload.get("bars"), dict):
                bars = payload["bars"].get(symbol) or []

            if isinstance(bars, list):
                record["bars_returned"] = len(bars)

            checked.append(record)

    if any(item.get("bars_returned", 0) > 0 for item in checked):
        status = "ALPACA_PROBE_FOUND_READABLE_BARS"
    elif any(item.get("reachable") for item in checked):
        status = "ALPACA_PROBE_REACHABLE_BUT_NO_BARS_RETURNED"
    else:
        status = "ALPACA_PROBE_NOT_REACHABLE_OR_NOT_AUTHORIZED"

    return {
        "status": status,
        "feeds_checked": checked,
    }


def _adapter_sample_probe(candidate_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    samples = []

    for row in candidate_rows[:5]:
        symbol = row.get("symbol")

        if not symbol:
            continue

        result = load_read_only_ohlcv_bars_for_d4b_candidate(
            symbol=str(symbol),
            campaign_id=row.get("campaign_id"),
            campaign_state=row.get("campaign_state"),
            requested_timeframe=os.environ.get("D4E_TIMEFRAME", "1Day"),
            lookback_bars=int(os.environ.get("D4E_LOOKBACK_BARS", "252")),
            minimum_usable_bars=int(os.environ.get("D4E_MINIMUM_USABLE_BARS", "30")),
            source_priority_policy=[
                "existing_non_mutating_runtime_payload_bars",
                "supabase_rest_read_only",
                "alpaca_rest_read_only",
            ],
            candidate_payload=row,
            timeout_seconds=int(os.environ.get("D4E_SOURCE_TIMEOUT_SECONDS", "20")),
        )

        samples.append({
            "symbol": result.get("symbol"),
            "adapter_status": result.get("adapter_status"),
            "source_type": result.get("source_type"),
            "bar_count": result.get("bar_count"),
            "warnings": result.get("warnings", [])[:8],
        })

    return {
        "sample_count": len(samples),
        "samples": samples,
    }


def _diagnosis(
    supabase_env: Dict[str, Any],
    alpaca_env: Dict[str, Any],
    supabase_probe: Dict[str, Any],
    alpaca_probe: Dict[str, Any],
) -> Dict[str, Any]:
    findings = []
    next_actions = []

    if not supabase_env["url"]["any_present"] or not supabase_env["key"]["any_present"]:
        findings.append("Local Supabase readable environment variables are missing or incomplete.")
        next_actions.append("Provide local read-only Supabase URL/key or configure D4E to use the correct deployed read-only source.")

    if not alpaca_env["key"]["any_present"] or not alpaca_env["secret"]["any_present"]:
        findings.append("Local Alpaca environment variables are missing or incomplete.")
        next_actions.append("Provide local Alpaca API key/secret using one of the supported variable names.")

    if supabase_probe.get("status") == "SUPABASE_PROBE_FOUND_REACHABLE_OHLCV_LIKE_TABLE":
        findings.append("Supabase has at least one reachable OHLCV-like table candidate.")
        next_actions.append("Set D4E_SUPABASE_BARS_TABLE to the confirmed OHLCV table if D4E did not auto-detect it.")

    if alpaca_probe.get("status") == "ALPACA_PROBE_FOUND_READABLE_BARS":
        findings.append("Alpaca credentials can read at least one tested bar source.")
        next_actions.append("Rerun D4E with the same environment; if candidates still fail, inspect candidate symbol validity and feed availability.")

    if (
        supabase_probe.get("status") != "SUPABASE_PROBE_FOUND_REACHABLE_OHLCV_LIKE_TABLE"
        and alpaca_probe.get("status") != "ALPACA_PROBE_FOUND_READABLE_BARS"
    ):
        findings.append("No confirmed read-only OHLCV bar source is currently available to D4E.")
        next_actions.append("Do not run D4F yet. Resolve Supabase or Alpaca read-only bar access first.")

    return {
        "findings": findings,
        "next_actions": next_actions,
    }


def main() -> int:
    env_file_report = _load_env_files()

    d3v_payload = _fetch_json(D3V_ENDPOINT)
    rows = _rows_from_payload(d3v_payload)
    candidate_rows = [
        row for row in rows
        if _bool(row.get("d3v_preflight_candidate"))
    ]

    candidate_symbols = [
        str(row.get("symbol")).strip().upper()
        for row in candidate_rows
        if row.get("symbol")
    ]

    supabase_env = {
        "url": _env_presence(SUPABASE_URL_KEYS),
        "key": _env_presence(SUPABASE_KEY_KEYS),
    }

    alpaca_env = {
        "key": _env_presence(ALPACA_KEY_KEYS),
        "secret": _env_presence(ALPACA_SECRET_KEYS),
    }

    supabase_probe = _supabase_probe(candidate_symbols)
    alpaca_probe = _alpaca_probe(candidate_symbols)
    adapter_sample_probe = _adapter_sample_probe(candidate_rows)
    diagnosis = _diagnosis(supabase_env, alpaca_env, supabase_probe, alpaca_probe)

    source_gap_flags = [
        "D4E1_READ_ONLY_SOURCE_CONFIGURATION_DIAGNOSTIC_COMPLETED",
        "D4E1_DOES_NOT_SUPPLY_BARS_TO_D4B",
        "D4E1_DOES_NOT_CONSTRUCT_HVN_POC",
        "D4E1_DOES_NOT_AUTHORIZE_D3D",
    ]

    if supabase_probe.get("status") == "SUPABASE_PROBE_FOUND_REACHABLE_OHLCV_LIKE_TABLE":
        source_gap_flags.append("D4E1_SUPABASE_OHLCV_LIKE_SOURCE_FOUND")
    else:
        source_gap_flags.append("D4E1_SUPABASE_OHLCV_SOURCE_NOT_CONFIRMED")

    if alpaca_probe.get("status") == "ALPACA_PROBE_FOUND_READABLE_BARS":
        source_gap_flags.append("D4E1_ALPACA_READABLE_BARS_CONFIRMED")
    else:
        source_gap_flags.append("D4E1_ALPACA_READABLE_BARS_NOT_CONFIRMED")

    if (
        "D4E1_SUPABASE_OHLCV_LIKE_SOURCE_FOUND" in source_gap_flags
        or "D4E1_ALPACA_READABLE_BARS_CONFIRMED" in source_gap_flags
    ):
        source_gap_flags.append("D4E1_NEXT_STEP_RERUN_D4E_WITH_CONFIRMED_SOURCE")
        source_resolution_status = "READ_ONLY_SOURCE_POSSIBLY_AVAILABLE_CONFIGURE_D4E_AND_RERUN"
    else:
        source_gap_flags.append("D4E1_NEXT_STEP_RESOLVE_READ_ONLY_SOURCE_BEFORE_D4F")
        source_resolution_status = "READ_ONLY_SOURCE_NOT_CONFIRMED_D4F_BLOCKED"

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4E1_READ_ONLY_BAR_SOURCE_CONFIGURATION_DIAGNOSTIC_COMPLETED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "constructs_hvn_poc": False,
        "not_a_trade_signal": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "env_file_report": env_file_report,
        "d3v_context": {
            "endpoint": D3V_ENDPOINT,
            "version": d3v_payload.get("version"),
            "endpoint_status": d3v_payload.get("endpoint_status"),
            "total_rows": len(rows),
            "candidate_rows": len(candidate_rows),
            "candidate_symbols_sample": candidate_symbols[:30],
        },
        "environment_presence": {
            "supabase": supabase_env,
            "alpaca": alpaca_env,
        },
        "supabase_probe": supabase_probe,
        "alpaca_probe": alpaca_probe,
        "adapter_sample_probe": adapter_sample_probe,
        "diagnosis": diagnosis,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "runtime_decision": {
            "source_resolution_status": source_resolution_status,
            "d4f_readiness": "BLOCKED_UNTIL_D4E_REPORTS_USABLE_OHLCV_BARS",
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4e1_makes_any_campaign_d3d_eligible": False,
            "reason": "D4E.1 diagnoses read-only bar-source configuration only. It does not supply bars to D4B, construct HVN/POC, mutate campaigns, authorize D3D, or confirm operator control.",
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4E.1 read-only bar source configuration diagnostic completed without mutation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
