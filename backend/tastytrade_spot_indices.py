# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Read-only spot-index observations from the existing tastytrade DXLink stream.
from datetime import datetime, timezone
import math
import time
from fastapi import APIRouter
from backend.tastytrade_futures_service import tastytrade_futures_service

router = APIRouter()
INDEX_SYMBOLS = {
    "SPX": ('SPX', '$SPX', '.SPX', 'SPX:X', 'SPX.X', '$SPX.X', 'SPX:XCBO', 'SPX:INDEX', 'SPX.CBOE'),
    "VIX": ("VIX", "$VIX", ".VIX", "VIX:X"),
}

# SIGMALYTIC_SPX_REST_FALLBACK_V2
# Strict read-only index observation; never manufacture a price or quote time.
import threading
import requests
from backend.tastytrade_oauth import tastytrade_oauth, USER_AGENT

_spx_rest_lock = threading.Lock()
_spx_rest_cache = {"checked": 0.0, "observation": None, "reason": "not_requested"}

def _spx_rest_observation():
    now = time.time()
    with _spx_rest_lock:
        if now - _spx_rest_cache["checked"] < 15:
            return _spx_rest_cache["observation"], _spx_rest_cache["reason"]
        _spx_rest_cache.update(checked=now, observation=None, reason="no_usable_spx_index_quote")
        try:
            token = tastytrade_oauth.get_access_token()
            response = requests.get(
                "https://api.tastyworks.com/market-data/by-type",
                params={"index": "SPX"},
                headers={"Authorization": "Bearer " + token,
                         "User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
            if response.status_code != 200:
                _spx_rest_cache["reason"] = "index_rest_http_" + str(response.status_code)
                return None, _spx_rest_cache["reason"]
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                _spx_rest_cache["reason"] = "unexpected_index_rest_schema"
                return None, _spx_rest_cache["reason"]
            for item in items:
                if not isinstance(item, dict) or str(item.get("symbol", "")).upper() != "SPX":
                    continue
                raw = item.get("last")
                try:
                    price = float(raw)
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(price) or price <= 0:
                    continue
                stamp = item.get("updated-at")
                if not isinstance(stamp, str):
                    _spx_rest_cache["reason"] = "missing_market_timestamp"
                    continue
                try:
                    observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    if observed.tzinfo is None:
                        _spx_rest_cache["reason"] = "timestamp_without_timezone"
                        continue
                    age = (datetime.now(timezone.utc) - observed).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    _spx_rest_cache["reason"] = "invalid_market_timestamp"
                    continue
                # Intraday only. Outside cash trading hours an old close is not a live cash index.
                if age < -30 or age > 120:
                    _spx_rest_cache["reason"] = "stale_spx_index_quote"
                    continue
                observation = {
                    "symbol": "SPX", "streamer_symbol": "SPX", "last": price,
                    "source": "tastytrade_index_rest",
                    "entitlement": str(tastytrade_futures_service.stream.entitlement_level or "unknown"),
                    "as_of": observed.isoformat(),
                }
                _spx_rest_cache.update(observation=observation, reason="ok")
                return observation, "ok"
            return None, _spx_rest_cache["reason"]
        except Exception as exc:
            _spx_rest_cache["reason"] = "index_rest_" + type(exc).__name__
            return None, _spx_rest_cache["reason"]

@router.get("/api/indices/spot")
def spot_indices():
    stream = tastytrade_futures_service.stream
    quotes = tastytrade_futures_service.quotes()
    indices = {}
    for name, candidates in INDEX_SYMBOLS.items():
        best = None
        for symbol in candidates:
            q = quotes.get(symbol)
            if not q or q.get("stale", True):
                continue
            trade = q.get("trade") or {}
            raw = trade.get("price")
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(price) or price <= 0:
                continue
            received = q.get("received_at")
            epoch = q.get("received_epoch", 0)
            if not received or time.time() - epoch > 120:
                continue
            if best is None or epoch > best[0]:
                best = (epoch, {
                    "symbol": name,
                    "streamer_symbol": symbol,
                    "last": price,
                    "source": "tastytrade_dxlink",
                    "entitlement": str(stream.entitlement_level or "unknown"),
                    "as_of": received,
                })
        if best:
            indices[name] = best[1]
    spx_rest_status = "not_needed"
    if "SPX" not in indices:
        rest_observation, spx_rest_status = _spx_rest_observation()
        if rest_observation is not None:
            indices["SPX"] = rest_observation
    return {
        "mode": "read_only",
        "indices": indices,
        "available": {name: name in indices for name in INDEX_SYMBOLS},
        "spx_rest_status": spx_rest_status,
        "spx_candidates_received": [symbol for symbol in INDEX_SYMBOLS["SPX"] if symbol in quotes],
        "entitlement": str(stream.entitlement_level or "unknown"),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
