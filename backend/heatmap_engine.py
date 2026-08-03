# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/heatmap_engine.py
----------------------------
Sector/Industry Heat Map -- groups the tracked universe by sector and
industry (using the real Russell 1000 classification sourced directly
from iShares' own official fund holdings export), colored by real
price performance at a selectable time frame (hourly, daily, weekly,
monthly), similar in concept to Barchart's Industry Heat Map
(barchart.com/stocks/sectors/industry-heat-map) -- a hierarchical,
treemap-style view where segments are sized and colored by
performance, with a time-frame toggle.

Reuses the same proven, parallelized multi-symbol historical-bars
fetch pattern already verified working in reports_engine.py's market
movers section (this same class of fetch, at a larger scale, was the
source of a real timeout bug fixed earlier the same night -- keeping
the parallelization here is deliberate, not optional).
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_SECTOR_LOOKUP_PATH = os.path.join(os.path.dirname(__file__), "data", "russell1000_sector_industry.csv")
_sector_lookup_cache: Optional[Dict[str, Dict[str, str]]] = None


def _load_sector_lookup() -> Dict[str, Dict[str, str]]:
    """
    Loads the ticker -> {sector, industry, name} lookup once and caches
    it in memory -- this is a small (~1000-row), effectively static
    reference file (real sector/industry classifications change rarely),
    so re-reading it from disk on every request would be wasteful.
    """
    global _sector_lookup_cache
    if _sector_lookup_cache is not None:
        return _sector_lookup_cache

    lookup: Dict[str, Dict[str, str]] = {}
    try:
        with open(_SECTOR_LOOKUP_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = (row.get("ticker") or "").strip()
                if ticker:
                    lookup[ticker] = {
                        "name": row.get("name") or "",
                        "sector": row.get("sector") or "Unknown",
                        "industry": row.get("industry") or "Unknown",
                    }
    except Exception:
        lookup = {}

    _sector_lookup_cache = lookup
    return lookup


# Each time frame maps to a bar timeframe/lookback and a specific rule
# for which two closes to compare -- "hourly" needs real intraday bars;
# the others use daily bars with a lookback window long enough to reach
# back the requested number of trading days.
_TIMEFRAME_CONFIG = {
    "hourly": {"bar_timeframe": "1Hour", "lookback_days": 3, "periods_back": 1},
    "daily": {"bar_timeframe": "1Day", "lookback_days": 5, "periods_back": 1},
    "weekly": {"bar_timeframe": "1Day", "lookback_days": 12, "periods_back": 5},
    "monthly": {"bar_timeframe": "1Day", "lookback_days": 35, "periods_back": 21},
}


def _fetch_change_pct_for_timeframe(timeframe: str) -> Dict[str, Dict[str, Any]]:
    """
    Fetches real bars for every symbol in the sector lookup and computes
    each one's % change for the requested time frame. Returns
    {ticker: {"change_pct": float, "price": float, "volume": float}}.
    """
    import requests as _requests
    import concurrent.futures as _futures

    config = _TIMEFRAME_CONFIG.get(timeframe)
    if not config:
        return {}

    lookup = _load_sector_lookup()
    symbols = list(lookup.keys())
    if not symbols:
        return {}

    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")
    if not key or not secret:
        print(f"[HEATMAP] {timeframe}: missing Alpaca credentials", flush=True)
        return {}

    end_dt = datetime.now(timezone.utc) + timedelta(days=1)
    start_dt = end_dt - timedelta(days=config["lookback_days"] + 1)
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    url = f"{base_url}/v2/stocks/bars"

    def _fetch_batch(batch: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        batch_bars: Dict[str, List[Dict[str, Any]]] = {}
        params = {
            "symbols": ",".join(batch),
            "timeframe": config["bar_timeframe"],
            "start": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "feed": "iex",
            "limit": 1000,
        }
        page_token = None
        for _page in range(5):
            if page_token:
                params["page_token"] = page_token
            try:
                r = _requests.get(url, headers=headers, params=params, timeout=15)
                if not r.ok:
                    print(f"[HEATMAP] {timeframe}: batch HTTP {r.status_code} -- {r.text[:200]}", flush=True)
                    break
                payload = r.json() or {}
            except Exception as exc:
                print(f"[HEATMAP] {timeframe}: batch request failed -- {exc}", flush=True)
                break

            for sym, bar_list in (payload.get("bars") or {}).items():
                batch_bars.setdefault(sym, []).extend(bar_list)

            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return batch_bars

    batch_size = 200
    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    with _futures.ThreadPoolExecutor(max_workers=min(8, len(batches) or 1)) as executor:
        for result in executor.map(_fetch_batch, batches):
            bars_by_symbol.update(result)

    print(f"[HEATMAP] {timeframe}: collected bars for {len(bars_by_symbol)} of {len(symbols)} symbols", flush=True)

    periods_back = config["periods_back"]
    result: Dict[str, Dict[str, Any]] = {}
    for sym, bar_list in bars_by_symbol.items():
        if len(bar_list) <= periods_back:
            continue
        try:
            latest = bar_list[-1]
            reference = bar_list[-1 - periods_back]
            latest_close = float(latest["c"])
            reference_close = float(reference["c"])
            if reference_close <= 0:
                continue
            change_pct = (latest_close - reference_close) / reference_close * 100
            volume = sum(float(b.get("v") or 0) for b in bar_list[-periods_back:])
        except Exception:
            continue
        result[sym] = {"change_pct": change_pct, "price": latest_close, "volume": volume}

    return result


def build_heatmap_data(timeframe: str = "daily") -> Dict[str, Any]:
    """
    Returns sector-grouped and industry-grouped performance data for
    the requested time frame, ready for a treemap-style visualization:
    each sector node, each industry node beneath it, and each symbol
    beneath that -- sized by volume, colored by % change.
    """
    timeframe = (timeframe or "daily").lower()
    if timeframe not in _TIMEFRAME_CONFIG:
        timeframe = "daily"

    lookup = _load_sector_lookup()
    changes = _fetch_change_pct_for_timeframe(timeframe)

    symbols_out = []
    for ticker, meta in lookup.items():
        change_data = changes.get(ticker)
        if not change_data:
            continue
        symbols_out.append({
            "ticker": ticker,
            "name": meta.get("name"),
            "sector": meta.get("sector"),
            "industry": meta.get("industry"),
            "change_pct": change_data["change_pct"],
            "price": change_data["price"],
            "volume": change_data["volume"],
        })

    reason = ""
    if not symbols_out:
        if not lookup:
            reason = "sector/industry lookup file failed to load"
        elif not changes:
            reason = "no price data returned from Alpaca for this time frame (check credentials/logs)"
        else:
            reason = "lookup and price data both loaded, but had no overlapping symbols"
        print(f"[HEATMAP] {timeframe}: empty result -- {reason}", flush=True)

    return {
        "ok": True,
        "timeframe": timeframe,
        "reason": reason,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "symbol_count": len(symbols_out),
        "symbols": symbols_out,
    }
