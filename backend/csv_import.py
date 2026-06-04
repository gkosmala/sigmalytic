# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/refresh_active_universe.py
----------------------------------
Builds a clean, up-to-date active equity universe for the Sigmalytic radar.

What it does:
1. Pulls active US equity assets from Alpaca /v2/assets.
2. Keeps major listed exchanges only.
3. Removes inactive, non-tradable, OTC-like, warrants, units, rights, preferreds.
4. Verifies each symbol has recent daily bar history.
5. Writes backend/data/russell1000.csv by default so existing radar_service.py can keep using it.

Run from project root:
    python backend/refresh_active_universe.py

Optional:
    python backend/refresh_active_universe.py --limit 1500
    python backend/refresh_active_universe.py --output backend/data/active_universe.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests

ALPACA_TRADING_BASE = os.getenv("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets")
ALPACA_DATA_BASE = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED = os.getenv("ALPACA_FEED", "iex")
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

MAJOR_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA"}

# Avoid symbols likely to break clean common-stock scanning.
BAD_SYMBOL_PATTERNS = [
    r"\.",      # BRK.B style class shares; Alpaca may use BRK.B but snapshots often vary
    r"/",       # odd symbol format
    r"\$",      # preferred/warrant style
    r"-",       # preferred/unit variants
]

BAD_NAME_TERMS = [
    " warrant", " warrants", " right", " rights", " unit", " units",
    " preferred", " preference", " depositary", " notes due", " baby bond",
    " etn", " bond", " trust preferred",
]

BENCHMARKS = ["SPY", "QQQ", "IWM", "GLD", "SMH"]


def headers() -> Dict[str, str]:
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        raise RuntimeError("Missing ALPACA_API_KEY or ALPACA_API_SECRET environment variables")
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def get_assets() -> List[dict]:
    url = f"{ALPACA_TRADING_BASE}/v2/assets"
    params = {"status": "active", "asset_class": "us_equity"}
    r = requests.get(url, headers=headers(), params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Alpaca assets request failed {r.status_code}: {r.text[:500]}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected assets response: {str(data)[:500]}")
    return data


def is_clean_common_equity(asset: dict) -> bool:
    symbol = str(asset.get("symbol", "")).upper().strip()
    name = str(asset.get("name", "")).lower().strip()
    exchange = str(asset.get("exchange", "")).upper().strip()

    if not symbol or len(symbol) > 5:
        return False
    if exchange not in MAJOR_EXCHANGES:
        return False
    if not asset.get("tradable", False):
        return False
    if not asset.get("fractionable", False) and exchange not in {"NYSE", "NASDAQ"}:
        # Soft quality filter; avoids many odd securities but still allows major exchange names.
        pass
    if any(re.search(p, symbol) for p in BAD_SYMBOL_PATTERNS):
        return False
    if any(term in name for term in BAD_NAME_TERMS):
        return False
    if not symbol.isalpha():
        return False
    return True


def get_bar_count(symbol: str, min_bars: int = 50) -> Tuple[int, float]:
    end_dt = datetime.now(timezone.utc) + timedelta(days=1)
    start_dt = end_dt - timedelta(days=420)  # enough calendar days for ~252 trading days
    params = {
        "timeframe": "1Day",
        "start": start_dt.strftime("%Y-%m-%d"),
        "end": end_dt.strftime("%Y-%m-%d"),
        "feed": ALPACA_FEED,
        "adjustment": "raw",
        "sort": "asc",
        "limit": 252,
    }
    url = f"{ALPACA_DATA_BASE}/v2/stocks/{symbol}/bars"
    r = requests.get(url, headers=headers(), params=params, timeout=15)
    if r.status_code != 200:
        return 0, 0.0
    bars = r.json().get("bars") or []
    clean = [b for b in bars if b.get("c") and b.get("v") is not None]
    if not clean:
        return 0, 0.0
    last_volume = float(clean[-1].get("v") or 0)
    return len(clean), last_volume


def write_csv(symbols: Iterable[str], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol"])
        for sym in symbols:
            writer.writerow([sym])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="backend/data/russell1000.csv")
    ap.add_argument("--limit", type=int, default=1400, help="Maximum validated symbols to write")
    ap.add_argument("--min-bars", type=int, default=50, help="Minimum recent daily bars required")
    ap.add_argument("--min-volume", type=float, default=50000, help="Minimum latest daily volume")
    ap.add_argument("--sleep", type=float, default=0.03, help="Pause between bar checks")
    args = ap.parse_args()

    print("Loading Alpaca active US equity assets...")
    assets = get_assets()
    print(f"Assets returned: {len(assets)}")

    candidates = [a for a in assets if is_clean_common_equity(a)]
    candidates.sort(key=lambda a: str(a.get("symbol", "")))
    print(f"Clean listed common-stock candidates: {len(candidates)}")

    validated: List[str] = []
    rejected_no_bars = 0
    rejected_volume = 0

    for i, asset in enumerate(candidates, start=1):
        sym = str(asset.get("symbol", "")).upper().strip()
        try:
            count, last_vol = get_bar_count(sym, min_bars=args.min_bars)
            if count < args.min_bars:
                rejected_no_bars += 1
            elif last_vol < args.min_volume:
                rejected_volume += 1
            else:
                validated.append(sym)
                if len(validated) >= args.limit:
                    break
        except Exception as e:
            rejected_no_bars += 1
            print(f"WARN {sym}: {e}")

        if i % 100 == 0:
            print(
                f"Checked {i}/{len(candidates)} | valid={len(validated)} | "
                f"no_bars={rejected_no_bars} | low_volume={rejected_volume}"
            )
        time.sleep(args.sleep)

    # Ensure benchmarks exist even if they failed volume filtering.
    for b in BENCHMARKS:
        if b not in validated:
            count, _ = get_bar_count(b, min_bars=20)
            if count >= 20:
                validated.append(b)

    validated = sorted(dict.fromkeys(validated))
    output = Path(args.output)
    write_csv(validated, output)

    print("\nUniverse refresh complete")
    print(f"Written: {output}")
    print(f"Symbols written: {len(validated)}")
    print(f"Rejected no/low bars: {rejected_no_bars}")
    print(f"Rejected low latest volume: {rejected_volume}")
    print("First 20:", ", ".join(validated[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# ------------------------------------------------------------------
# FastAPI compatibility export
# backend.main imports: from csv_import import csv_router
# ------------------------------------------------------------------

try:
    from fastapi import APIRouter

    csv_router = APIRouter(
        prefix="/api/csv",
        tags=["csv"]
    )
except Exception:
    csv_router = None