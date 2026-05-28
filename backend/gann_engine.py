# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Gann Geometry Engine
================================================================================
File    : gann_engine.py
Version : 1.0.0
Date    : 2026-05-24

PURPOSE
-------
Calculates W.D. Gann geometric angle vectors from structural pivot points
and writes them to the Supabase geometric_structures cache table.

The 1x1 angle (45 degrees) is the most important — it represents the perfect
balance of price and time. Price above the 1x1 = bullish. Below = bearish.

CADENCE
-------
Run once manually to seed your 14 Intelligence Layer symbols.
Schedule nightly at 20:00 UTC alongside wyckoff_anchor.py.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

import os
import math
import pandas as pd
from datetime import datetime, timedelta, timezone
import requests as _requests
from supabase import create_client, Client

# ── Credentials ───────────────────────────────────────────────────────────────
SUPABASE_URL    = os.environ.get("SUPABASE_URL",              "")
SUPABASE_KEY    = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ALPACA_KEY      = os.environ.get("ALPACA_API_KEY",            "")
ALPACA_SECRET   = os.environ.get("ALPACA_API_SECRET",         "")
ALPACA_BASE_URL = os.environ.get("ALPACA_BASE_URL",           "https://data.alpaca.markets")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ── Intelligence Layer symbols ────────────────────────────────────────────────
INTELLIGENCE_SYMBOLS = [
    "SPY", "QQQ", "IWM",
    "AAPL", "NVDA", "TSLA", "AMD",
    "GOOG", "META", "AMZN", "MSFT",
    "NFLX", "GLD", "SMH"
]

# ── Gann angle ratio matrix ───────────────────────────────────────────────────
# Each ratio represents Price Units per Time Unit
# 1x1 = perfect balance (45 degrees) — the most important angle
GANN_RATIOS = {
    "Gann_8x1" : 8.000,
    "Gann_4x1" : 4.000,
    "Gann_3x1" : 3.000,
    "Gann_2x1" : 2.000,
    "Gann_1x1" : 1.000,   # Cardinal angle — highest significance
    "Gann_1x2" : 0.500,
    "Gann_1x3" : 0.333,
    "Gann_1x4" : 0.250,
    "Gann_1x8" : 0.125,
}

# Scoring weight per angle when price touches it
# 1x1 scores highest — outer angles score less
GANN_ANGLE_SCORES = {
    "Gann_1x1" : 15,
    "Gann_2x1" : 10,
    "Gann_1x2" : 10,
    "Gann_3x1" : 8,
    "Gann_1x3" : 8,
    "Gann_4x1" : 6,
    "Gann_1x4" : 6,
    "Gann_8x1" : 4,
    "Gann_1x8" : 4,
}


# ================================================================================
# STEP 1 — FETCH DAILY BARS
# ================================================================================

def fetch_daily_bars(ticker: str, lookback_days: int = 365) -> pd.DataFrame:
    """Pulls daily OHLCV bars from Alpaca using requests (no SDK dependency)."""
    if not ALPACA_KEY:
        return pd.DataFrame()

    end_date   = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=lookback_days)

    try:
        r = _requests.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{ticker}/bars",
            headers={
                "APCA-API-KEY-ID"    : ALPACA_KEY,
                "APCA-API-SECRET-KEY": ALPACA_SECRET,
            },
            params={
                "timeframe": "1Day",
                "start"    : start_date.strftime("%Y-%m-%d"),
                "end"      : end_date.strftime("%Y-%m-%d"),
                "feed"     : "sip",
                "limit"    : min(lookback_days, 1000),
                "sort"     : "asc",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return pd.DataFrame()

        bars = r.json().get("bars", [])
        if not bars:
            return pd.DataFrame()

        df = pd.DataFrame(bars)
        df = df.rename(columns={"t":"timestamp","o":"open","h":"high","l":"low","c":"close","v":"volume"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    except Exception:
        return pd.DataFrame()


# ================================================================================
# STEP 2 — DETECT STRUCTURAL PIVOT
# ================================================================================

def detect_macro_pivot(df: pd.DataFrame) -> dict:
    """
    Finds the most recent significant macro pivot (high or low).
    Uses a 20-bar lookback on each side to confirm a true swing point.
    Returns the pivot price, timestamp, type (HIGH or LOW), and bar index.
    """
    if len(df) < 45:
        return {}

    left  = 20
    right = 20
    best_pivot = {}

    for i in range(left, len(df) - right):
        window = df.iloc[i - left : i + right + 1]
        bar    = df.iloc[i]

        is_swing_high = bar['high'] >= window['high'].max()
        is_swing_low  = bar['low']  <= window['low'].min()

        if is_swing_high:
            best_pivot = {
                "price"    : float(bar['high']),
                "timestamp": bar['timestamp'],
                "type"     : "HIGH",
                "bar_index": i
            }

        if is_swing_low:
            best_pivot = {
                "price"    : float(bar['low']),
                "timestamp": bar['timestamp'],
                "type"     : "LOW",
                "bar_index": i
            }

    return best_pivot


# ================================================================================
# STEP 3 — CALCULATE ASSET MULTIPLIER
# ================================================================================

def calculate_asset_multiplier(df: pd.DataFrame) -> float:
    """
    Calibrates the price-per-bar movement for this specific asset.
    Uses the average daily range (ATR proxy) as the natural price unit.
    This scales the Gann angles correctly per symbol — a $500 stock
    moves differently per bar than a $10 stock.
    """
    if len(df) < 20:
        return 1.0

    recent = df.tail(20)
    avg_range = (recent['high'] - recent['low']).mean()
    return round(float(avg_range), 4)


# ================================================================================
# STEP 4 — GENERATE AND STORE GANN VECTORS
# ================================================================================

def generate_and_store_gann_vectors(ticker: str, df: pd.DataFrame) -> dict:
    """
    Detects the macro pivot, calculates all 9 Gann angle vectors,
    and writes them to the Supabase geometric_structures cache table.

    Each vector is stored as a row with:
    - structure_type : angle name (e.g. 'Gann_1x1')
    - price_level    : pivot anchor price (Y0)
    - time_anchor    : pivot timestamp (T0)
    - base_slope     : signed slope per timeframe step
    - asset_multiplier: price-per-bar scaling factor
    - timeframe_minutes: 1440 (daily bars = 1440 minutes)
    """
    if df.empty or len(df) < 45:
        return {"status": "skipped", "reason": "Insufficient bar depth."}

    pivot = detect_macro_pivot(df)
    if not pivot:
        return {"status": "none_found", "reason": "No macro pivot detected."}

    asset_multiplier = calculate_asset_multiplier(df)

    # Direction: bullish fan from LOW, bearish fan from HIGH
    direction = 1.0 if pivot["type"] == "LOW" else -1.0

    # Deactivate old Gann vectors for this ticker
    if supabase:
        supabase.table("geometric_structures") \
            .update({"is_active": False}) \
            .eq("ticker", ticker) \
            .in_("structure_type", list(GANN_RATIOS.keys())) \
            .execute()

    # Build new vector records
    new_vectors = []
    for angle_name, base_ratio in GANN_RATIOS.items():
        signed_slope = base_ratio * direction

        new_vectors.append({
            "ticker"          : ticker,
            "structure_type"  : angle_name,
            "price_level"     : pivot["price"],
            "time_anchor"     : str(pivot["timestamp"]),
            "base_slope"      : signed_slope,
            "asset_multiplier": asset_multiplier,
            "timeframe_minutes": 1440,   # daily bars
            "is_active"       : True
        })

    if supabase:
        supabase.table("geometric_structures").insert(new_vectors).execute()

    return {
        "status"          : "anchored",
        "ticker"          : ticker,
        "pivot_type"      : pivot["type"],
        "pivot_price"     : pivot["price"],
        "pivot_time"      : str(pivot["timestamp"]),
        "asset_multiplier": asset_multiplier,
        "vectors_written" : len(new_vectors)
    }


# ================================================================================
# STEP 5 — LIVE PRICE CHECK (used by 60-second scan loop)
# ================================================================================

def check_gann_confluence_live(ticker: str, live_price: float) -> list:
    """
    Queries Supabase for active Gann vectors for this ticker.
    Projects each vector to the current time and checks if live price
    is within 0.08% of any projected level.

    Returns a list of matching vectors with their score contribution.
    Called by the 60-second scan loop via supabase.rpc().
    """
    try:
        from supabase import create_client
        current_time = datetime.now(timezone.utc).isoformat()

        response = supabase.rpc(
            "match_gann_confluence",
            {
                "p_ticker"        : ticker,
                "p_current_price" : live_price,
                "p_check_time"    : current_time
            }
        ).execute()

        matches = response.data or []

        # Attach score contribution per angle
        for match in matches:
            angle = match.get("vector_angle", "")
            match["score_contribution"] = GANN_ANGLE_SCORES.get(angle, 5)

        return matches

    except Exception as e:
        print(f"  {ticker} Gann confluence check error: {str(e)}")
        return []


# ================================================================================
# STEP 6 — SEED INTELLIGENCE UNIVERSE
# ================================================================================

def seed_gann_vectors(symbols: list = INTELLIGENCE_SYMBOLS) -> None:
    """
    Seeds all Intelligence Layer symbols with Gann fan vectors.
    Run once manually, then nightly at 20:00 UTC.
    """
    print("=" * 64)
    print("  SIGMALYTIC — Gann Vector Seeding Sequence")
    print("=" * 64)

    for symbol in symbols:
        try:
            df     = fetch_daily_bars(symbol, lookback_days=365)

            if df.empty:
                print(f"  {symbol:<6} ⚠️  No daily bars returned from Alpaca.")
                continue

            result = generate_and_store_gann_vectors(symbol, df)
            status = result["status"]

            if status == "anchored":
                print(
                    f"  {symbol:<6} ✅  Pivot={result['pivot_type']} "
                    f"@ ${result['pivot_price']:.2f} | "
                    f"Multiplier={result['asset_multiplier']:.4f} | "
                    f"{result['vectors_written']} vectors written"
                )
            else:
                reason = result.get("reason", "Unknown")
                print(f"  {symbol:<6} ⏭️   {status.upper()} — {reason}")

        except Exception as e:
            print(f"  {symbol:<6} ❌  Exception: {str(e)}")

    print("=" * 64)
    print("  Gann seeding complete. Check Supabase geometric_structures.")
    print("=" * 64)


# ================================================================================
# NIGHTLY RECALCULATION
# ================================================================================

def run_nightly_gann_recalculation() -> None:
    """
    Nightly maintenance. Re-scans Intelligence Layer symbols
    to update Gann vectors when new macro pivots form.
    Wire into backend scheduler at 20:00 UTC alongside wyckoff_anchor.py.
    """
    print(f"[{datetime.now(timezone.utc).isoformat()}] Nightly Gann recalculation starting...")
    seed_gann_vectors(INTELLIGENCE_SYMBOLS)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Nightly Gann recalculation complete.")


# ================================================================================
# ENTRY POINT
# ================================================================================

if __name__ == "__main__":
    seed_gann_vectors()
