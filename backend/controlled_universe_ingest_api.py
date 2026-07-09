"""
Sigmalytic V2 — Controlled Persisted Universe Ingest API.

This router is NOT read-only.

It is hard-gated and does not execute unless all execution gates pass:
- explicit request execute=true
- exact authorization phrase
- Render/backend environment variable SIGMALYTIC_CONTROLLED_UNIVERSE_INGEST_ENABLED=true
- Supabase server-side key available in backend environment
- Alpaca backend credentials available in backend environment
- persisted universe tables are still empty/current snapshot absent

Allowed write scope, only after all gates:
- INSERT into public.campaign_universe_snapshots
- INSERT into public.campaign_universe_symbols

This router does not mutate campaigns.
This router does not mutate daily_bars.
This router does not advance readiness.
This router does not authorize D3D.
This router does not confirm operator control.
This router does not create trade signals.
This router does not touch Stripe.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]


AUTHORIZATION_PHRASE = "I explicitly authorize one append-only persisted universe snapshot ingest."
AUTHORIZATION_REF = "STEP76_BACKEND_CONTROLLED_APPEND_ONLY_UNIVERSE_SNAPSHOT_INGEST_ROUTE_2026_07_09"
SOURCE_NAME = "ALPACA_ASSETS_ACTIVE_TRADABLE"
BATCH_SIZE = 500


if APIRouter is not None:
    controlled_universe_ingest_router = APIRouter(
        prefix="/api/campaigns/controlled",
        tags=["controlled-universe-ingest"],
    )
else:
    controlled_universe_ingest_router = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _supabase_url() -> str:
    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).strip().rstrip("/")

    if not url:
        raise RuntimeError("SUPABASE_URL/NEXT_PUBLIC_SUPABASE_URL missing")

    if not url.startswith("https://"):
        raise RuntimeError("Supabase URL must be full https URL")

    return url


def _supabase_key() -> str:
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or ""
    ).strip()

    if not key:
        raise RuntimeError("server-side Supabase key missing")

    if key.startswith("sb_publishable_"):
        raise RuntimeError("publishable Supabase key is not allowed for controlled ingest")

    if not (key.startswith("sb_secret_") or key.startswith("eyJ")):
        raise RuntimeError("Supabase key is not recognized as secret/service_role format")

    return key


def _supabase_headers() -> dict[str, str]:
    key = _supabase_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: Any | None = None,
    timeout: int = 90,
) -> tuple[int, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers=headers or {},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            if text:
                try:
                    body = json.loads(text)
                except Exception:
                    body = text
            else:
                body = None
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except Exception:
            body = text
        return int(exc.code), body


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _fetch_alpaca_assets() -> tuple[str, list[dict[str, Any]]]:
    key = (
        os.environ.get("APCA_API_KEY_ID")
        or os.environ.get("ALPACA_API_KEY")
        or ""
    ).strip()
    secret = (
        os.environ.get("APCA_API_SECRET_KEY")
        or os.environ.get("ALPACA_SECRET_KEY")
        or os.environ.get("ALPACA_API_SECRET")
        or ""
    ).strip()

    if not key or not secret:
        raise RuntimeError("Alpaca backend credentials missing")

    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }

    candidates: list[str] = []

    explicit = (
        os.environ.get("ALPACA_TRADING_BASE_URL")
        or os.environ.get("APCA_API_BASE_URL")
        or ""
    ).strip().rstrip("/")

    if explicit:
        candidates.append(explicit + "/v2/assets?status=active&asset_class=us_equity")

    candidates.extend(
        [
            "https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity",
            "https://api.alpaca.markets/v2/assets?status=active&asset_class=us_equity",
        ]
    )

    errors: list[str] = []

    for url in candidates:
        status, body = _http_json(url, headers=headers, timeout=90)

        if 200 <= status < 300 and isinstance(body, list):
            rows: list[dict[str, Any]] = []

            for asset in body:
                if not isinstance(asset, dict):
                    continue

                symbol = _normalize_symbol(asset.get("symbol"))

                if not symbol:
                    continue

                if asset.get("status") != "active":
                    continue

                if asset.get("tradable") is not True:
                    continue

                rows.append(
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

            deduped = {row["symbol"]: row for row in rows}
            ordered = [deduped[symbol] for symbol in sorted(deduped)]
            return url, ordered

        errors.append(f"{url} -> HTTP {status}: {body}")

    raise RuntimeError("Alpaca asset fetch failed: " + " | ".join(errors))


def _supabase_get(table: str, query: str) -> tuple[int, Any]:
    url = f"{_supabase_url()}/rest/v1/{table}?{query}"
    return _http_json(url, method="GET", headers=_supabase_headers(), timeout=90)


def _supabase_insert(table: str, payload: Any) -> tuple[int, Any]:
    url = f"{_supabase_url()}/rest/v1/{table}"
    headers = _supabase_headers()
    headers["Prefer"] = "return=representation"
    return _http_json(url, method="POST", headers=headers, payload=payload, timeout=120)


def _current_universe_precheck() -> dict[str, Any]:
    current_status, current_body = _supabase_get(
        "campaign_universe_snapshots",
        "select=snapshot_id&is_current=eq.true&limit=1",
    )

    symbols_status, symbols_body = _supabase_get(
        "campaign_universe_symbols",
        "select=symbol&limit=1",
    )

    current_exists = isinstance(current_body, list) and len(current_body) > 0
    symbol_exists = isinstance(symbols_body, list) and len(symbols_body) > 0

    return {
        "current_snapshot_status": current_status,
        "current_snapshot_exists": current_exists,
        "current_snapshot_body": current_body,
        "symbol_probe_status": symbols_status,
        "symbol_rows_exist": symbol_exists,
        "symbol_probe_body": symbols_body,
        "empty_for_first_ingest": (
            200 <= current_status < 300
            and 200 <= symbols_status < 300
            and not current_exists
            and not symbol_exists
        ),
    }


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_snapshot_and_symbols(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot_id = str(uuid.uuid4())
    symbols = [row["symbol"] for row in rows]
    symbols_hash = hashlib.sha256("\n".join(symbols).encode("utf-8")).hexdigest()

    snapshot = {
        "snapshot_id": snapshot_id,
        "source": SOURCE_NAME,
        "as_of_utc": _utc_now(),
        "universe_count": len(rows),
        "active_count": len(rows),
        "tradable_count": len(rows),
        "symbols_hash": symbols_hash,
        "created_by": "sigmalytic_v2_step76_backend_controlled_universe_ingest",
        "write_authorization_ref": AUTHORIZATION_REF,
        "is_current": True,
    }

    symbol_payload = []

    for row in rows:
        symbol_payload.append(
            {
                "snapshot_id": snapshot_id,
                "symbol": row.get("symbol"),
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

    return snapshot, symbol_payload


def build_controlled_universe_ingest_result(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}

    execute_requested = bool(payload.get("execute") is True)
    authorization_phrase = str(payload.get("authorization_phrase") or "")
    authorization_ok = authorization_phrase == AUTHORIZATION_PHRASE
    env_execute_enabled = _truthy(os.environ.get("SIGMALYTIC_CONTROLLED_UNIVERSE_INGEST_ENABLED"))

    failures: list[str] = []
    warnings: list[str] = []
    write_results: list[dict[str, Any]] = []

    if execute_requested and not authorization_ok:
        failures.append("exact authorization phrase missing")

    if execute_requested and not env_execute_enabled:
        failures.append("SIGMALYTIC_CONTROLLED_UNIVERSE_INGEST_ENABLED is not true")

    supabase_env_ok = False
    alpaca_env_ok = False

    try:
        _supabase_url()
        _supabase_key()
        supabase_env_ok = True
    except Exception as exc:
        if execute_requested:
            failures.append(str(exc))
        else:
            warnings.append(str(exc))

    try:
        if (
            os.environ.get("APCA_API_KEY_ID")
            or os.environ.get("ALPACA_API_KEY")
        ) and (
            os.environ.get("APCA_API_SECRET_KEY")
            or os.environ.get("ALPACA_SECRET_KEY")
            or os.environ.get("ALPACA_API_SECRET")
        ):
            alpaca_env_ok = True
        else:
            raise RuntimeError("Alpaca backend credentials missing")
    except Exception as exc:
        if execute_requested:
            failures.append(str(exc))
        else:
            warnings.append(str(exc))

    precheck: dict[str, Any] | None = None
    selected_alpaca_endpoint: str | None = None
    rows: list[dict[str, Any]] = []

    if supabase_env_ok:
        precheck = _current_universe_precheck()
        if not precheck.get("empty_for_first_ingest"):
            message = "persisted universe is not empty or precheck failed"
            if execute_requested:
                failures.append(message)
            else:
                warnings.append(message)

    if alpaca_env_ok:
        selected_alpaca_endpoint, rows = _fetch_alpaca_assets()
        if not rows:
            message = "Alpaca returned zero active/tradable symbols"
            if execute_requested:
                failures.append(message)
            else:
                warnings.append(message)

    snapshot: dict[str, Any] | None = None
    symbol_payload: list[dict[str, Any]] = []

    if rows:
        snapshot, symbol_payload = _build_snapshot_and_symbols(rows)

    execute_allowed = (
        execute_requested
        and authorization_ok
        and env_execute_enabled
        and supabase_env_ok
        and alpaca_env_ok
        and precheck is not None
        and precheck.get("empty_for_first_ingest") is True
        and snapshot is not None
        and len(symbol_payload) > 0
        and not failures
    )

    write_attempted = False

    if execute_allowed and snapshot is not None:
        write_attempted = True

        status, body = _supabase_insert("campaign_universe_snapshots", snapshot)
        write_results.append(
            {
                "table": "campaign_universe_snapshots",
                "status": status,
                "response": body,
            }
        )

        if not (200 <= status < 300):
            failures.append(f"snapshot insert failed HTTP {status}")
        else:
            for index, batch in enumerate(_chunked(symbol_payload, BATCH_SIZE), start=1):
                batch_status, batch_body = _supabase_insert("campaign_universe_symbols", batch)
                write_results.append(
                    {
                        "table": "campaign_universe_symbols",
                        "batch": index,
                        "status": batch_status,
                        "response_preview": batch_body[:2] if isinstance(batch_body, list) else batch_body,
                    }
                )

                if not (200 <= batch_status < 300):
                    failures.append(f"symbol batch {index} insert failed HTTP {batch_status}")
                    break

    result = {
        "status": "PASS" if not failures and (not execute_requested or write_attempted) else "FAIL",
        "mode": "EXECUTE_APPEND_ONLY_INGEST" if execute_requested else "DRY_RUN_ONLY_NO_WRITE",
        "execute_requested": execute_requested,
        "execute_allowed": execute_allowed,
        "write_attempted": write_attempted,
        "authorization_ok": authorization_ok,
        "env_execute_enabled": env_execute_enabled,
        "authorization_ref": AUTHORIZATION_REF,
        "source": SOURCE_NAME,
        "selected_alpaca_endpoint": selected_alpaca_endpoint,
        "symbol_count": len(rows),
        "snapshot_preview": {
            "snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
            "universe_count": snapshot.get("universe_count") if snapshot else None,
            "symbols_hash": snapshot.get("symbols_hash") if snapshot else None,
            "is_current": snapshot.get("is_current") if snapshot else None,
        },
        "precheck": precheck,
        "failures": failures,
        "warnings": warnings,
        "write_results": write_results,
        "doctrine": {
            "allowed_write_tables_only": [
                "campaign_universe_snapshots",
                "campaign_universe_symbols",
            ],
            "no_campaign_mutation": True,
            "no_daily_bars_mutation": True,
            "no_readiness_advance": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
    }

    return result


if controlled_universe_ingest_router is not None:
    @controlled_universe_ingest_router.post("/persisted-universe-ingest")
    def controlled_persisted_universe_ingest(payload: dict[str, Any] | None = None):
        """
        Controlled backend-only persisted universe ingest.

        Default body can be omitted or {"execute": false}; that is dry-run only.
        Execute requires the exact authorization phrase and backend env execution flag.
        """
        return build_controlled_universe_ingest_result(payload)


__all__ = [
    "controlled_universe_ingest_router",
    "build_controlled_universe_ingest_result",
]
