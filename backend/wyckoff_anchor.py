# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Wyckoff Structural Anchor Engine
================================================================================
File    : wyckoff_anchor.py
Version : 1.0.0
Date    : 2026-05-24

PURPOSE
-------
Detects immutable Wyckoff structural anchors from daily OHLCV data and
persists them to the Supabase geometric_structures cache table.

Anchors detected:
  - SC  (Selling Climax)     — institutional volume climax floor
  - AR  (Automatic Rally)    — immediate short-covering response ceiling
  - ST  (Secondary Test)     — Phase A terminal validation marker

These are NOT rolling variables. Once written to Supabase they are permanent
historical coordinates until a new Wyckoff cycle supersedes them.

CADENCE
-------
Run once manually to seed your 14 Intelligence Layer symbols.
Schedule nightly at 20:00 UTC via your backend cron for ongoing maintenance.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

import os
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

# ── Intelligence Layer symbols (matches your radar_service.py) ────────────────
INTELLIGENCE_SYMBOLS = [
    "SPY", "QQQ", "IWM",
    "AAPL", "NVDA", "TSLA", "AMD",
    "GOOG", "META", "AMZN", "MSFT",
    "NFLX", "GLD", "SMH"
]


# ================================================================================
# STEP 1 — FETCH DAILY BARS FROM ALPACA
# ================================================================================

def fetch_alpaca_daily_bars(ticker: str, lookback_days: int = 365) -> pd.DataFrame:
    """
    Pulls daily OHLCV bars from Alpaca using requests (no SDK dependency).
    """
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

    except Exception as e:
        return pd.DataFrame()


# ================================================================================
# STEP 2 — DETECT AND STORE WYCKOFF ANCHORS
# ================================================================================

def detect_and_store_wyckoff_anchors(ticker: str, df: pd.DataFrame) -> dict:
    """
    Scans macro daily bars to detect and persist three immutable Wyckoff anchors:
      SC_Low  — Selling Climax floor
      AR_High — Automatic Rally ceiling
      ST_Low  — Secondary Test validation

    All three must pass structural validation before anything is written
    to Supabase. Partial matches are rejected — not stored.
    """

    if len(df) < 40:
        return {"status": "skipped", "reason": "Insufficient historical bar depth (need 40+)."}

    # Rolling baselines
    df = df.copy()
    df['spread']     = df['high'] - df['low']
    df['avg_spread'] = df['spread'].rolling(20).mean()
    df['avg_volume'] = df['volume'].rolling(20).mean()

    # ── EVENT 1: Selling Climax (SC) ─────────────────────────────────────────
    # Scan backward from recent bars — most recent valid SC wins
    sc_idx = None

    for i in range(len(df) - 15, 20, -1):
        bar = df.iloc[i]

        is_wide_spread    = bar['spread']  > (bar['avg_spread'] * 1.5)
        is_volume_climax  = bar['volume']  > (bar['avg_volume'] * 2.0)

        bar_range   = bar['high'] - bar['low']
        close_pos   = (bar['close'] - bar['low']) / (bar_range if bar_range > 0 else 1)
        is_low_close = close_pos <= 0.35

        if is_wide_spread and is_volume_climax and is_low_close:
            sc_idx = i
            break

    if sc_idx is None:
        return {"status": "none_found", "reason": "No Selling Climax signature detected."}

    sc_bar  = df.iloc[sc_idx]
    sc_low  = float(sc_bar['low'])
    sc_time = sc_bar['timestamp']

    # ── EVENT 2: Automatic Rally (AR) ────────────────────────────────────────
    # Widened to 15 bars — large-cap ARs can take up to 15 trading days to peak
    ar_search_end = min(sc_idx + 15, len(df))
    ar_df         = df.iloc[sc_idx + 1 : ar_search_end]

    if ar_df.empty:
        return {"status": "none_found", "reason": "SC found but AR search window is empty."}

    ar_max_idx = ar_df['high'].idxmax()
    ar_bar     = df.loc[ar_max_idx]
    ar_high    = float(ar_bar['high'])
    ar_time    = ar_bar['timestamp']
    ar_idx     = df.index.get_loc(ar_max_idx)

    # Minimum 40% recovery of the SC bar's spread
    total_sc_spread = sc_bar['high'] - sc_bar['low']
    rally_recovery  = ar_high - sc_low

    if rally_recovery < (total_sc_spread * 0.40):
        return {"status": "rejected", "reason": "AR recovery too weak — below 40% of SC spread."}

    # ── MARKUP COMPLETION CHECK ───────────────────────────────────────────────
    # If price is already >15% above AR high, this Wyckoff cycle is complete.
    # Writing stale anchors would misclassify normal pullbacks as Springs.
    latest_close = float(df.iloc[-1]['close'])
    if latest_close > ar_high * 1.15:
        return {
            "status": "skipped",
            "reason": (
                f"Wyckoff cycle already complete — price ({latest_close:.2f}) "
                f"is >15% above AR high ({ar_high:.2f}). Asset in markup phase."
            )
        }

    # ── EVENT 3: Secondary Test (ST) ─────────────────────────────────────────
    # Widened to 45 bars — ST can take 20–40 trading days after the AR peak
    st_search_end = min(ar_idx + 45, len(df))
    st_df         = df.iloc[ar_idx + 1 : st_search_end]

    if st_df.empty:
        return {"status": "none_found", "reason": "AR found but ST search window is empty."}

    st_min_idx = st_df['low'].idxmin()
    st_bar     = df.loc[st_min_idx]
    st_low     = float(st_bar['low'])
    st_time    = st_bar['timestamp']

    # ST must retest near the SC floor — not breach it badly, not stay too far above
    # Lower bound: ST can slightly undercut SC (springs do this) but not >4% below
    # Upper bound: ST must come within 8% of SC low to count as a real test
    if st_low < (sc_low * 0.96):
        return {
            "status": "rejected",
            "reason": f"ST ({st_low:.2f}) broke too far below SC floor ({sc_low:.2f}) — markdown, not accumulation."
        }

    if st_low > (sc_low * 1.08):
        return {
            "status": "rejected",
            "reason": f"ST ({st_low:.2f}) too far above SC floor ({sc_low:.2f}) — no meaningful test occurred."
        }

    # ST volume must be lower than SC volume — confirms supply is drying up
    if st_bar['volume'] > sc_bar['volume'] * 0.70:
        return {
            "status": "rejected",
            "reason": "ST volume too high — active supply still present. Not a valid secondary test."
        }

    # ── WRITE TO SUPABASE ─────────────────────────────────────────────────────
    # Deactivate any existing anchors for this ticker first
    if supabase:
        supabase.table("geometric_structures") \
            .update({"is_active": False}) \
            .eq("ticker", ticker) \
            .in_("structure_type", ["Wyckoff_SC_Low", "Wyckoff_AR_High", "Wyckoff_ST_Low"]) \
            .execute()

    # Insert the three validated, immutable anchors
    new_anchors = [
        {
            "ticker"        : ticker,
            "structure_type": "Wyckoff_SC_Low",
            "price_level"   : sc_low,
            "time_anchor"   : str(sc_time),
            "is_active"     : True
        },
        {
            "ticker"        : ticker,
            "structure_type": "Wyckoff_AR_High",
            "price_level"   : ar_high,
            "time_anchor"   : str(ar_time),
            "is_active"     : True
        },
        {
            "ticker"        : ticker,
            "structure_type": "Wyckoff_ST_Low",
            "price_level"   : st_low,
            "time_anchor"   : str(st_time),
            "is_active"     : True
        }
    ]

    if supabase:
        supabase.table("geometric_structures").insert(new_anchors).execute()

    return {
        "status"   : "anchored",
        "ticker"   : ticker,
        "sc_low"   : sc_low,
        "ar_high"  : ar_high,
        "st_low"   : st_low,
        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    }


# ================================================================================
# STEP 3 — SEED THE INTELLIGENCE LAYER (run once manually)
# ================================================================================

def seed_intelligence_universe(symbols: list = INTELLIGENCE_SYMBOLS) -> None:
    """
    One-time seed run for your 14 Intelligence Layer symbols.
    Fetches 180 days of daily bars per symbol and writes validated
    Wyckoff anchors to Supabase geometric_structures.
    """
    print("=" * 64)
    print("  SIGMALYTIC — Wyckoff Anchor Seeding Sequence")
    print("=" * 64)

    for symbol in symbols:
        try:
            df     = fetch_alpaca_daily_bars(symbol, lookback_days=180)

            if df.empty:
                print(f"  {symbol:<6} ⚠️  No daily bars returned from Alpaca.")
                continue

            result = detect_and_store_wyckoff_anchors(symbol, df)
            status = result['status']

            if status == "anchored":
                print(
                    f"  {symbol:<6} ✅  SC={result['sc_low']:.2f}  "
                    f"AR={result['ar_high']:.2f}  ST={result['st_low']:.2f}"
                )
            else:
                reason = result.get('reason', 'Unknown')
                print(f"  {symbol:<6} ⏭️   {status.upper()} — {reason}")

        except Exception as e:
            print(f"  {symbol:<6} ❌  Exception: {str(e)}")

    print("=" * 64)
    print("  Seeding complete. Check Supabase geometric_structures table.")
    print("=" * 64)


# ================================================================================
# STEP 4 — NIGHTLY RECALCULATION (scheduled at 20:00 UTC)
# ================================================================================

def run_nightly_wyckoff_recalculation() -> None:
    """
    Nightly maintenance run. Re-scans all Intelligence Layer symbols
    to detect new Wyckoff cycles that may have formed during the session.
    Wire this into your backend scheduler at 20:00 UTC.
    """
    print(f"[{datetime.now(timezone.utc).isoformat()}] Nightly Wyckoff recalculation starting...")
    seed_intelligence_universe(INTELLIGENCE_SYMBOLS)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Nightly recalculation complete.")


# ================================================================================
# ENTRY POINT — Manual seed run
# ================================================================================

if __name__ == "__main__":
    seed_intelligence_universe()

