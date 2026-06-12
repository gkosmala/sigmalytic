# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/supabase_bars.py
------------------------
Supabase persistence layer for daily bar cache.

Solves the restart problem: instead of fetching 1,479 symbols × 252 bars
from Alpaca on every startup (25-30 min), load from Supabase in ~5 seconds.

Alpaca remains the authoritative source — nightly refresh writes to Supabase.
Supabase becomes the fast startup cache.

Table schema (create in Supabase SQL editor):
─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_bars (
    symbol      TEXT        NOT NULL,
    date        DATE        NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      BIGINT,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS daily_bars_symbol_idx ON daily_bars(symbol);
CREATE INDEX IF NOT EXISTS daily_bars_date_idx   ON daily_bars(date DESC);
─────────────────────────────────────────────
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

log = logging.getLogger("supabase_bars")

# ── Supabase connection ───────────────────────────────────────────────────────

def _get_client():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None, None
    return url, key

def _headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

# ── Load bars from Supabase ───────────────────────────────────────────────────

def load_bars_from_supabase(min_bars: int = 20) -> Dict[str, List[dict]]:
    """
    Load daily bars from Supabase into the format used by HISTORICAL_BARS cache.
    Returns {symbol: [{"t": date, "o": open, "h": high, "l": low, "c": close, "v": vol}]}
    """
    url, key = _get_client()
    if not url:
        log.warning("Supabase not configured — skipping bar load")
        return {}

    log.info("Loading daily bars from Supabase...")
    t0 = time.time()

    all_bars: Dict[str, List[dict]] = {}
    page_size = 10000
    offset = 0

    while True:
        try:
            hdrs = {**_headers(key),
                    "Range-Unit": "items",
                    "Range": f"{offset}-{offset + page_size - 1}"}
            r = requests.get(
                f"{url}/rest/v1/daily_bars",
                headers=hdrs,
                params={
                    "select": "symbol,date,open,high,low,close,volume",
                    "order": "symbol.asc,date.asc",
                },
                timeout=60,
            )
            if r.status_code not in (200, 206):
                log.warning(f"Supabase bar load error: {r.status_code} {r.text[:200]}")
                break

            batch = r.json()
            if not batch:
                break

            for row in batch:
                sym = row["symbol"]
                if sym not in all_bars:
                    all_bars[sym] = []
                all_bars[sym].append({
                    "t": row["date"],
                    "o": float(row["open"] or 0),
                    "h": float(row["high"] or 0),
                    "l": float(row["low"] or 0),
                    "c": float(row["close"] or 0),
                    "v": int(row["volume"] or 0),
                })

            offset += len(batch)
            if len(batch) < page_size:
                break

        except Exception as e:
            log.error(f"Supabase bar load exception at offset {offset}: {e}")
            break

    # Filter out symbols with too few bars
    usable = {sym: bars for sym, bars in all_bars.items() if len(bars) >= min_bars}

    elapsed = time.time() - t0
    log.info(f"Supabase bar load complete — {len(usable)}/{len(all_bars)} symbols "
             f"in {elapsed:.1f}s")
    return usable


# ── Save bars to Supabase ─────────────────────────────────────────────────────

def save_bars_to_supabase(bars_cache: Dict[str, List[dict]],
                           batch_size: int = 5000) -> int:
    """
    Save HISTORICAL_BARS cache to Supabase daily_bars table.
    Uses upsert (merge-duplicates) so re-running is safe.
    Returns number of rows written.
    """
    url, key = _get_client()
    if not url:
        log.warning("Supabase not configured — skipping bar save")
        return 0

    log.info(f"Saving bars to Supabase — {len(bars_cache)} symbols...")
    t0 = time.time()
    total_written = 0
    errors = 0

    # Flatten to rows
    rows = []
    for symbol, bars in bars_cache.items():
        for bar in bars:
            date_str = bar.get("t", "")
            if not date_str:
                continue
            # Normalize date format
            date_str = str(date_str)[:10]
            rows.append({
                "symbol": symbol,
                "date": date_str,
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v"),
            })

    log.info(f"  Total rows to write: {len(rows):,}")

    # Write in batches
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            r = requests.post(
                f"{url}/rest/v1/daily_bars",
                headers=_headers(key),
                json=batch,
                timeout=60,
            )
            if r.status_code in (200, 201):
                total_written += len(batch)
            else:
                log.warning(f"  Batch {i//batch_size} write error: {r.status_code} {r.text[:200]}")
                errors += 1
        except Exception as e:
            log.error(f"  Batch {i//batch_size} exception: {e}")
            errors += 1

        if (i // batch_size) % 20 == 0:
            log.info(f"  Written {total_written:,}/{len(rows):,} rows...")

    elapsed = time.time() - t0
    log.info(f"Supabase bar save complete — {total_written:,} rows in {elapsed:.1f}s "
             f"({errors} errors)")
    return total_written


# ── Check if Supabase has usable bar data ─────────────────────────────────────

def supabase_bars_available(min_symbols: int = 500) -> bool:
    """Quick check — does Supabase have enough bar data to use as startup cache?"""
    url, key = _get_client()
    if not url:
        return False
    try:
        r = requests.get(
            f"{url}/rest/v1/daily_bars",
            headers={**_headers(key), "Prefer": "count=exact"},
            params={"select": "symbol", "limit": 1},
            timeout=10,
        )
        content_range = r.headers.get("Content-Range", "0/0")
        total = int(content_range.split("/")[-1]) if "/" in content_range else 0
        # Usable if at least 500 symbols worth of data present
        available = total >= min_symbols * 20
        log.info(f"Supabase bar check: {total:,} rows — {'available' if available else 'insufficient'}")
        return available
    except Exception as e:
        log.warning(f"Supabase bar check failed: {e}")
        return False


# ── Status ────────────────────────────────────────────────────────────────────

def supabase_bars_status() -> dict:
    """Return status info for the health endpoint."""
    url, key = _get_client()
    if not url:
        return {"configured": False, "available": False, "rows": 0}
    try:
        r = requests.get(
            f"{url}/rest/v1/daily_bars",
            headers={**_headers(key), "Prefer": "count=exact"},
            params={"select": "symbol", "limit": 1},
            timeout=10,
        )
        content_range = r.headers.get("Content-Range", "0/0")
        total = int(content_range.split("/")[-1]) if "/" in content_range else 0
        return {"configured": True, "available": total > 0, "rows": total}
    except Exception as e:
        return {"configured": True, "available": False, "rows": 0, "error": str(e)}
