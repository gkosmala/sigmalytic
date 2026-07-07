from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ADAPTER_NAME = "D4E_READ_ONLY_OHLCV_ADAPTER"
ADAPTER_VERSION = "phase_d4e_read_only_ohlcv_adapter_v1"

ROOT = Path(__file__).resolve().parents[2]

WRITES_TO_SUPABASE = False
MUTATES_CAMPAIGNS = False
EXECUTES_D3D = False
AUTHORIZES_D3D = False
CONFIRMS_OPERATOR_CONTROL = False
CONSTRUCTS_HVN_POC = False
NOT_A_TRADE_SIGNAL = True

DEFAULT_TIMEFRAME = "1Day"
DEFAULT_LOOKBACK_BARS = 252
DEFAULT_MIN_USABLE_BARS = 30
DEFAULT_TIMEOUT_SECONDS = 20
MAX_RECENT_WINDOW_AGE_DAYS = 10


def _load_env_files() -> None:
    env_paths = [
        ROOT / ".env",
        ROOT / ".env.local",
        ROOT / "backend" / ".env",
        ROOT / "backend" / ".env.local",
    ]

    for path in env_paths:
        if not path.exists():
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for raw_line in lines:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


def _env_first(names: List[str]) -> Optional[str]:
    _load_env_files()

    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()

    return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_bar_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _bars_are_recent_enough(
    bars: List[Dict[str, Any]],
    max_age_days: int = MAX_RECENT_WINDOW_AGE_DAYS,
) -> bool:
    if not bars:
        return False

    latest = _parse_bar_timestamp(bars[-1].get("timestamp"))

    if latest is None:
        return False

    age = _now_utc() - latest

    return age <= timedelta(days=max_age_days)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        number = float(value)
    except Exception:
        return None

    if not math.isfinite(number):
        return None

    return number


def _pick(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        if name in row and row.get(name) is not None:
            return row.get(name)

    return None


def _normalize_bar(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    timestamp = _pick(row, ["timestamp", "time", "date", "datetime", "t"])
    open_price = _safe_float(_pick(row, ["open", "o"]))
    high_price = _safe_float(_pick(row, ["high", "h"]))
    low_price = _safe_float(_pick(row, ["low", "l"]))
    close_price = _safe_float(_pick(row, ["close", "c", "price"]))
    volume = _safe_float(_pick(row, ["volume", "v", "vol"]))

    if timestamp is None:
        return None

    if open_price is None or high_price is None or low_price is None or close_price is None or volume is None:
        return None

    if high_price < low_price:
        return None

    if volume <= 0:
        return None

    return {
        "timestamp": str(timestamp),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


def _normalize_bars(rows: Any, lookback_bars: int) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    bars: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        normalized = _normalize_bar(row)

        if normalized:
            bars.append(normalized)

    bars = sorted(bars, key=lambda item: item["timestamp"])

    if lookback_bars > 0:
        bars = bars[-lookback_bars:]

    return bars


def _status_result(
    *,
    symbol: str,
    adapter_status: str,
    source_type: str = "NONE",
    bars: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[str]] = None,
    source_quality: str = "UNAVAILABLE",
    timeframe: str = DEFAULT_TIMEFRAME,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> Dict[str, Any]:
    clean_bars = bars or []

    return {
        "adapter": ADAPTER_NAME,
        "version": ADAPTER_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "source_type": source_type,
        "source_quality": source_quality,
        "adapter_status": adapter_status,
        "bar_count": len(clean_bars),
        "bars": clean_bars,
        "window_start": window_start,
        "window_end": window_end,
        "warnings": warnings or [],
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "confirms_operator_control": False,
        "constructs_hvn_poc": False,
        "not_a_trade_signal": True,
    }


def _extract_payload_bars(candidate_payload: Optional[Dict[str, Any]], lookback_bars: int) -> List[Dict[str, Any]]:
    if not isinstance(candidate_payload, dict):
        return []

    candidate_keys = [
        "bars",
        "daily_bars",
        "ohlcv",
        "ohlcv_bars",
        "price_bars",
        "historical_bars",
        "market_data_bars",
    ]

    for key in candidate_keys:
        bars = _normalize_bars(candidate_payload.get(key), lookback_bars)

        if bars:
            return bars

    return []


def _supabase_table_candidates() -> List[str]:
    explicit = _env_first([
        "D4E_SUPABASE_BARS_TABLE",
        "SIGMALYTIC_BAR_TABLE",
        "SUPABASE_BARS_TABLE",
    ])

    tables: List[str] = []

    if explicit:
        tables.append(explicit)

    tables.extend([
        "daily_bars",
        "market_data_bars",
        "historical_bars",
        "stock_bars",
        "bars",
        "sip_daily_bars",
    ])

    seen = set()
    ordered: List[str] = []

    for table in tables:
        if table and table not in seen:
            ordered.append(table)
            seen.add(table)

    return ordered


def _load_from_supabase_rest(
    *,
    symbol: str,
    lookback_bars: int,
    timeout_seconds: int,
) -> Dict[str, Any]:
    supabase_url = _env_first(["SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"])
    supabase_key = _env_first([
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ])

    if not supabase_url or not supabase_key:
        return _status_result(
            symbol=symbol,
            adapter_status="ADAPTER_BLOCKED_SUPABASE_ENV_MISSING",
            source_type="SUPABASE_REST_READ_ONLY",
            warnings=["SUPABASE_URL and readable Supabase key were not available in local environment."],
        )

    base_url = supabase_url.rstrip("/")
    limit = max(int(lookback_bars or DEFAULT_LOOKBACK_BARS), DEFAULT_MIN_USABLE_BARS)

    warnings: List[str] = []

    select_fields = "timestamp,open,high,low,close,volume"
    query = urllib.parse.urlencode({
        "symbol": f"eq.{symbol}",
        "select": select_fields,
        "order": "timestamp.desc",
        "limit": str(limit),
    })

    headers = {
        "Accept": "application/json",
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "User-Agent": "Sigmalytic-D4E-Read-Only-OHLCV-Adapter/1.0",
    }

    for table in _supabase_table_candidates():
        url = f"{base_url}/rest/v1/{urllib.parse.quote(table)}?{query}"
        request = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            warnings.append(f"{table}: read failed: {type(exc).__name__}: {exc}")
            continue

        try:
            payload = json.loads(raw)
        except Exception as exc:
            warnings.append(f"{table}: non-json response: {type(exc).__name__}: {exc}")
            continue

        bars = _normalize_bars(payload, lookback_bars)

        if bars:
            return _status_result(
                symbol=symbol,
                adapter_status="ADAPTER_OK_BARS_LOADED_READ_ONLY",
                source_type=f"SUPABASE_REST_READ_ONLY:{table}",
                source_quality="USABLE_OHLCV_BARS",
                bars=bars,
                warnings=warnings[-3:],
                window_start=bars[0]["timestamp"],
                window_end=bars[-1]["timestamp"],
            )

        warnings.append(f"{table}: no usable OHLCV bars returned.")

    return _status_result(
        symbol=symbol,
        adapter_status="ADAPTER_BLOCKED_NO_SUPABASE_BARS_FOUND",
        source_type="SUPABASE_REST_READ_ONLY",
        warnings=warnings[-8:],
    )


def _alpaca_credentials() -> Dict[str, Optional[str]]:
    return {
        "key": _env_first([
            "ALPACA_API_KEY",
            "ALPACA_API_KEY_ID",
            "APCA_API_KEY_ID",
            "APCA_API_KEY",
        ]),
        "secret": _env_first([
            "ALPACA_SECRET_KEY",
            "ALPACA_API_SECRET",
            "APCA_API_SECRET_KEY",
            "APCA_API_SECRET",
        ]),
    }


def _load_from_alpaca_rest(
    *,
    symbol: str,
    timeframe: str,
    lookback_bars: int,
    timeout_seconds: int,
) -> Dict[str, Any]:
    credentials = _alpaca_credentials()
    key = credentials["key"]
    secret = credentials["secret"]

    if not key or not secret:
        return _status_result(
            symbol=symbol,
            adapter_status="ADAPTER_BLOCKED_ALPACA_ENV_MISSING",
            source_type="ALPACA_REST_READ_ONLY",
            timeframe=timeframe,
            warnings=["Alpaca API key/secret were not available in local environment."],
        )

    end_dt = _now_utc()
    start_dt = end_dt - timedelta(days=max(lookback_bars * 3, 365))

    feeds = [
        feed.strip()
        for feed in os.environ.get("D4E_ALPACA_FEEDS", "sip,iex").split(",")
        if feed.strip()
    ]

    warnings: List[str] = []

    for feed in feeds:
        params = urllib.parse.urlencode({
            "symbols": symbol,
            "timeframe": timeframe,
            "start": _iso_datetime(start_dt),
            "end": _iso_datetime(end_dt),
            "limit": str(max(lookback_bars, DEFAULT_MIN_USABLE_BARS)),
            "adjustment": "raw",
            "feed": feed,
            "sort": "desc",
        })

        url = f"https://data.alpaca.markets/v2/stocks/bars?{params}"

        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "User-Agent": "Sigmalytic-D4E-Read-Only-OHLCV-Adapter/1.0",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            warnings.append(f"alpaca feed {feed}: read failed: {type(exc).__name__}: {exc}")
            continue

        try:
            payload = json.loads(raw)
        except Exception as exc:
            warnings.append(f"alpaca feed {feed}: non-json response: {type(exc).__name__}: {exc}")
            continue

        raw_bars = []

        if isinstance(payload, dict):
            bars_by_symbol = payload.get("bars")

            if isinstance(bars_by_symbol, dict):
                raw_bars = bars_by_symbol.get(symbol) or bars_by_symbol.get(symbol.upper()) or []

        bars = _normalize_bars(raw_bars, lookback_bars)

        if bars:
            if not _bars_are_recent_enough(bars):
                warnings.append(
                    f"alpaca feed {feed}: stale OHLCV window rejected; latest bar was {bars[-1].get('timestamp')}."
                )
                continue

            return _status_result(
                symbol=symbol,
                adapter_status="ADAPTER_OK_BARS_LOADED_READ_ONLY",
                source_type=f"ALPACA_REST_READ_ONLY:{feed}",
                source_quality="USABLE_RECENT_OHLCV_BARS",
                timeframe=timeframe,
                bars=bars,
                warnings=warnings[-3:],
                window_start=bars[0]["timestamp"],
                window_end=bars[-1]["timestamp"],
            )

        warnings.append(f"alpaca feed {feed}: no usable OHLCV bars returned.")

    return _status_result(
        symbol=symbol,
        adapter_status="ADAPTER_BLOCKED_NO_ALPACA_BARS_FOUND",
        source_type="ALPACA_REST_READ_ONLY",
        timeframe=timeframe,
        warnings=warnings[-8:],
    )


def load_read_only_ohlcv_bars_for_d4b_candidate(
    *,
    symbol: str,
    campaign_id: Optional[Any] = None,
    campaign_state: Optional[str] = None,
    requested_timeframe: str = DEFAULT_TIMEFRAME,
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    source_priority_policy: Optional[List[str]] = None,
    candidate_payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    minimum_usable_bars: int = DEFAULT_MIN_USABLE_BARS,
) -> Dict[str, Any]:
    clean_symbol = str(symbol or "").strip().upper()

    if not clean_symbol:
        return _status_result(
            symbol="",
            adapter_status="ADAPTER_BLOCKED_MISSING_SYMBOL",
            warnings=["Symbol is required."],
            timeframe=requested_timeframe,
        )

    priority = source_priority_policy or [
        "existing_non_mutating_runtime_payload_bars",
        "supabase_rest_read_only",
        "alpaca_rest_read_only",
    ]

    warnings: List[str] = []

    for source in priority:
        source_key = str(source).strip().lower()

        if source_key == "existing_non_mutating_runtime_payload_bars":
            bars = _extract_payload_bars(candidate_payload, lookback_bars)

            if bars:
                status = "ADAPTER_OK_BARS_LOADED_READ_ONLY" if len(bars) >= minimum_usable_bars else "ADAPTER_BLOCKED_INSUFFICIENT_BARS"
                return _status_result(
                    symbol=clean_symbol,
                    adapter_status=status,
                    source_type="EXISTING_RUNTIME_PAYLOAD_READ_ONLY",
                    source_quality="USABLE_OHLCV_BARS" if status.startswith("ADAPTER_OK") else "INSUFFICIENT_OHLCV_BARS",
                    timeframe=requested_timeframe,
                    bars=bars,
                    warnings=[],
                    window_start=bars[0]["timestamp"],
                    window_end=bars[-1]["timestamp"],
                )

            warnings.append("existing runtime candidate payload had no usable OHLCV bars.")

        elif source_key == "supabase_rest_read_only":
            result = _load_from_supabase_rest(
                symbol=clean_symbol,
                lookback_bars=lookback_bars,
                timeout_seconds=timeout_seconds,
            )

            if result["adapter_status"] == "ADAPTER_OK_BARS_LOADED_READ_ONLY":
                if result["bar_count"] >= minimum_usable_bars:
                    result["warnings"] = warnings + result.get("warnings", [])
                    return result

                result["adapter_status"] = "ADAPTER_BLOCKED_INSUFFICIENT_BARS"

            warnings.extend(result.get("warnings", []))

        elif source_key == "alpaca_rest_read_only":
            result = _load_from_alpaca_rest(
                symbol=clean_symbol,
                timeframe=requested_timeframe,
                lookback_bars=lookback_bars,
                timeout_seconds=timeout_seconds,
            )

            if result["adapter_status"] == "ADAPTER_OK_BARS_LOADED_READ_ONLY":
                if result["bar_count"] >= minimum_usable_bars:
                    result["warnings"] = warnings + result.get("warnings", [])
                    return result

                result["adapter_status"] = "ADAPTER_BLOCKED_INSUFFICIENT_BARS"

            warnings.extend(result.get("warnings", []))

        else:
            warnings.append(f"unknown read-only source priority entry skipped: {source}")

    return _status_result(
        symbol=clean_symbol,
        adapter_status="ADAPTER_BLOCKED_NO_READ_ONLY_BAR_SOURCE_AVAILABLE",
        source_type="NONE",
        source_quality="UNAVAILABLE",
        timeframe=requested_timeframe,
        warnings=warnings[-12:],
    )
