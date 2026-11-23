# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Read-only spot-index observations from the existing tastytrade DXLink stream.
from datetime import datetime, timezone
import math
import time
from fastapi import APIRouter
from backend.tastytrade_futures_service import tastytrade_futures_service

router = APIRouter()
INDEX_SYMBOLS = {
    "SPX": ("SPX", "$SPX", ".SPX", "SPX:X"),
    "VIX": ("VIX", "$VIX", ".VIX", "VIX:X"),
}

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
    return {
        "mode": "read_only",
        "indices": indices,
        "available": {name: name in indices for name in INDEX_SYMBOLS},
        "entitlement": str(stream.entitlement_level or "unknown"),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
