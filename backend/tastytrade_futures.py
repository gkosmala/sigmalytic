
# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Tastytrade futures market data — read-only foundation.

import requests

from backend.tastytrade_oauth import (
    USER_AGENT,
    tastytrade_oauth,
)

BASE_URL = "https://api.tastyworks.com"
TIMEOUT = 20


class FuturesDataError(RuntimeError):
    pass


def _get(path, params=None):
    token = tastytrade_oauth.get_access_token()

    try:
        response = requests.get(
            BASE_URL + path,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            params=params,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FuturesDataError(
            f"Tastytrade request failed: {path}"
        ) from exc


def get_dxlink_credentials():
    """Obtain market-data authorization; never log tokens."""
    payload = _get("/api-quote-tokens")
    data = payload.get("data", {})

    token = data.get("token")
    url = data.get("dxlink-url")

    if not token or not url or not url.startswith("wss://"):
        raise FuturesDataError(
            "Invalid DXLink authorization response."
        )

    return {
        "token": token,
        "url": url,
        "level": data.get("level"),
        "expires_at": data.get("expires-at"),
    }


def discover_futures():
    """Discover contracts and their exact DXLink symbols."""
    payload = _get("/instruments/futures")
    data = payload.get("data", {})

    if not isinstance(data, dict):
        raise FuturesDataError("Invalid futures catalog.")

    items = data.get("items", [])
    if not isinstance(items, list):
        raise FuturesDataError("Invalid futures items.")

    contracts = []

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")
        streamer_symbol = item.get("streamer-symbol")

        if not symbol or not streamer_symbol:
            continue

        contracts.append({
            "symbol": symbol,
            "streamer_symbol": streamer_symbol,
            "root": item.get("product-code"),
            "expiration": item.get("expiration-date"),
            "tick_size": item.get("tick-size"),
            "exchange": item.get("exchange"),
            "is_tradeable": item.get("is-tradeable"),
        })

    return contracts
