# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/radar_settings.py
-------------------------
The radar bar count: how many completed daily bars the Weis setup state reads.
Weis gives no number (ranges are drawn with judgment), so the user sets it.

One global integer, stored in Redis (`radar:bar_count`, no expiry) so it is
shared by the web service, the radar worker and the swing preview and can be
changed at any time without a deploy.

    GET  /api/admin/radar-bar-count
    POST /api/admin/radar-bar-count   {"bar_count": 252}
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException

DEFAULT_BAR_COUNT = 289
MIN_BAR_COUNT = 60
MAX_BAR_COUNT = 1000
REDIS_KEY = "radar:bar_count"
_CACHE_SECONDS = 30

_client = None
_cached: Optional[tuple] = None  # (value, fetched_at)


def _redis():
    global _client
    if _client is not None:
        return _client
    try:
        import redis
        url = os.getenv("REDIS_URL", "")
        if not url:
            return None
        _client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
    except Exception:
        _client = None
    return _client


def validate(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError("Bar count must be a whole number.")
    if isinstance(value, float) and value != n:
        raise ValueError("Bar count must be a whole number.")
    if n < MIN_BAR_COUNT or n > MAX_BAR_COUNT:
        raise ValueError(f"Bar count must be between {MIN_BAR_COUNT} and {MAX_BAR_COUNT}.")
    return n


def get_bar_count(client=None, force: bool = False) -> int:
    """Current setting; the default when unset or Redis is unreachable."""
    global _cached
    now = time.time()
    if client is None and not force and _cached and now - _cached[1] < _CACHE_SECONDS:
        return _cached[0]
    value = DEFAULT_BAR_COUNT
    try:
        c = client or _redis()
        raw = c.get(REDIS_KEY) if c is not None else None
        if raw is not None:
            value = validate(raw)
    except Exception:
        value = DEFAULT_BAR_COUNT
    if client is None:
        _cached = (value, now)
    return value


def set_bar_count(value: Any, client=None) -> int:
    global _cached
    n = validate(value)
    c = client or _redis()
    if c is None:
        raise RuntimeError("Redis is not available, so the setting cannot be saved.")
    c.set(REDIS_KEY, str(n))
    if client is None:
        _cached = (n, time.time())
    return n


def daily_lookback_days(bar_count: int) -> int:
    """Calendar days of daily bars to fetch so `bar_count` completed bars exist."""
    return max(420, int(bar_count * 1.7))


def _admin_dependency():
    try:
        from backend.main import require_admin
    except Exception:  # pragma: no cover
        from main import require_admin
    return require_admin


def _admin(authorization: str = Header(default="")) -> str:
    return _admin_dependency()(authorization)


radar_settings_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _payload(n: int) -> Dict[str, Any]:
    return {"bar_count": n, "default": DEFAULT_BAR_COUNT, "min": MIN_BAR_COUNT, "max": MAX_BAR_COUNT}


@radar_settings_router.get("/radar-bar-count")
def read_bar_count(_admin_email: str = Depends(_admin)):
    return _payload(get_bar_count(force=True))


@radar_settings_router.post("/radar-bar-count")
def write_bar_count(body: Dict[str, Any] = Body(...), _admin_email: str = Depends(_admin)):
    try:
        n = set_bar_count(body.get("bar_count"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return _payload(n)
