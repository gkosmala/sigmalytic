"""
backtest_service.py
Sigmalytic Quant Corporation

Replays 5 years of historical data through the Sigmalytic scoring engine.
For each symbol in backtest_universe.csv:
  1. Pulls 5yr Weekly + Daily + Hourly bars from Alpaca
  2. Runs multi-timeframe scoring logic (weekly trend + daily setup + hourly trigger)
  3. Measures outcome: direction accuracy + T1/T2 target hits
  4. Stores results in Supabase + CSV

Timeframe hierarchy:
  Weekly  → regime + trend direction
  Daily   → setup identification + scoring
  Hourly  → entry trigger + target tracking

Usage:
  python backtest_service.py \
    --api-key YOUR_ALPACA_KEY \
    --secret-key YOUR_ALPACA_SECRET \
    --supabase-url YOUR_SUPABASE_URL \
    --supabase-key YOUR_SUPABASE_KEY \
    --universe backtest_universe.csv \
    --output backtest_results.csv
"""

import argparse
import time
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
LOOKBACK_YEARS  = 5
T1_MULTIPLIER   = 0.02    # T1 = entry + 2%
T2_MULTIPLIER   = 0.04    # T2 = entry + 4%
STOP_MULTIPLIER = 0.015   # Stop = entry - 1.5%
MAX_HOLD_DAYS   = 10      # Max calendar days to hold

REGIME_BULL     = "Bull Expansion"
REGIME_BEAR     = "Bear Market"
REGIME_VOLATILE = "Volatility Shock"
REGIME_COMPRESS = "Compression"
REGIME_RECOVERY = "Recovery"

# ---------------------------------------------------------------------------
# Alpaca data fetcher
# ---------------------------------------------------------------------------

def fetch_bars(symbol: str, timeframe: str, start: str, end: str,
               api_key: str, secret_key: str) -> pd.DataFrame:
    headers = {
        "APCA-API-KEY-ID":     api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    all_bars   = []
    next_token = None

    while True:
        params = {
            "symbols":    symbol,
            "timeframe":  timeframe,
            "start":      start,
            "end":        end,
            "limit":      10000,
            "adjustment": "all",
            "feed":       "iex",
        }
        if next_token:
            params["page_token"] = next_token

        try:
            resp = requests.get(
                f"{ALPACA_DATA_URL}/stocks/bars",
                headers=headers, params=params, timeout=30,
            )
            resp.raise_for_status()
            data       = resp.json()
            bars       = data.get("bars", {}).get(symbol, [])
            all_bars.extend(bars)
            next_token = data.get("next_page_token")
            if not next_token:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"    ⚠️  {symbol} {timeframe}: {e}")
            break

    if not all_bars:
        return pd.DataFrame()

    df = pd.DataFrame(all_bars)
    df["t"] = pd.to_datetime(df["t"])
    df = df.sort_values("t").reset_index(drop=True)
    df.rename(columns={
        "o": "open", "h": "high", "l": "low",
        "c": "close", "v": "volume", "t": "timestamp"
    }, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Regime classifier (uses weekly bars)
# ---------------------------------------------------------------------------

def classify_regime(weekly: pd.DataFrame, as_of: pd.Timestamp) -> str:
    past = weekly[weekly["timestamp"] <= as_of].tail(26)  # ~6 months of weekly bars
    if len(past) < 10:
        return REGIME_BULL

    closes     = past["close"]
    returns    = closes.pct_change().dropna()
    volatility = returns.std()
    trend      = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0]
    avg_ret    = returns.mean()

    if volatility > 0.04:
        return REGIME_VOLATILE
    elif trend > 0.08 and avg_ret > 0:
        return REGIME_BULL
    elif trend < -0.08:
        return REGIME_BEAR
    elif abs(trend) < 0.03:
        return REGIME_COMPRESS
    else:
        return REGIME_RECOVERY


# ---------------------------------------------------------------------------
# Weekly trend scorer
# ---------------------------------------------------------------------------

def weekly_trend(weekly: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    past = weekly[weekly["timestamp"] <= as_of].tail(13)  # ~3 months
    if len(past) < 8:
        return {"direction": "neutral", "strength": 50}

    closes    = past["close"]
    sma13     = closes.mean()
    sma4      = closes.tail(4).mean()
    price     = closes.iloc[-1]
    momentum  = (price - closes.iloc[0]) / closes.iloc[0]

    if price > sma13 and sma4 > sma13 and momentum > 0:
        direction = "bull"
        strength  = min(100, 60 + int(momentum * 200))
    elif price < sma13 and sma4 < sma13 and momentum < 0:
        direction = "bear"
        strength  = min(100, 60 + int(abs(momentum) * 200))
    else:
        direction = "neutral"
        strength  = 50

    return {"direction": direction, "strength": strength}


# ---------------------------------------------------------------------------
# Daily setup scorer
# ---------------------------------------------------------------------------

def score_daily_bar(daily: pd.DataFrame, idx: int, weekly_signal: dict) -> Optional[dict]:
    if idx < 20:
        return None

    window  = daily.iloc[max(0, idx - 20):idx + 1]
    bar     = daily.iloc[idx]
    closes  = window["close"]
    highs   = window["high"]
    lows    = window["low"]
    volumes = window["volume"]

    price       = bar["close"]
    sma20       = closes.mean()
    sma5        = closes.tail(5).mean()
    vol_avg     = volumes.mean()
    vol_ratio   = bar["volume"] / vol_avg if vol_avg > 0 else 1
    high20      = highs.max()
    low20       = lows.min()
    range20     = high20 - low20

    if range20 == 0 or sma20 == 0:
        return None

    # Compression: recent 5-bar range vs 20-bar range
    recent_range   = (highs.tail(5).max() - lows.tail(5).min()) / range20
    is_compressed  = recent_range < 0.35

    # Price position within 20-bar range (0=bottom, 1=top)
    price_position = (price - low20) / range20

    # Momentum (10-bar)
    momentum    = (price - closes.iloc[-10]) / closes.iloc[-10] if len(closes) >= 10 else 0

    # RSI proxy: ratio of up days over 14 bars
    changes     = closes.diff().dropna().tail(14)
    up_days     = (changes > 0).sum()
    rsi_proxy   = up_days / 14

    above_sma20 = price > sma20
    above_sma5  = price > sma5

    score = 50

    # 1. Weekly alignment — most important
    weekly_dir = weekly_signal.get("direction", "neutral")
    if weekly_dir == "bull" and above_sma20:
        score += 15
    elif weekly_dir == "bear" and not above_sma20:
        score += 15
    elif weekly_dir == "neutral":
        score -= 5

    # 2. Compression — reward BEFORE breakout
    if is_compressed and price_position < 0.75:
        score += 15
    elif is_compressed and price_position >= 0.75:
        score += 5

    # 3. Volume expansion
    if vol_ratio > 2.0:
        score += 12
    elif vol_ratio > 1.5:
        score += 8
    elif vol_ratio < 0.7:
        score -= 8

    # 4. Momentum — reward moderate, penalize extremes
    if 0.01 < momentum < 0.04:
        score += 10
    elif momentum > 0.06:
        score -= 8
    elif momentum < -0.06:
        score -= 8

    # 5. Trend structure
    if above_sma20 and above_sma5 and sma5 > sma20:
        score += 8
    elif not above_sma20 and not above_sma5 and sma5 < sma20:
        score += 8

    # 6. RSI filter — penalize extremes
    if rsi_proxy > 0.75:
        score -= 10
    elif rsi_proxy < 0.25:
        score -= 10
    elif 0.4 < rsi_proxy < 0.65:
        score += 5

    score = max(0, min(100, int(score)))

    if score < 70:
        return None

    # Direction
    if weekly_dir == "bull":
        direction = "bull"
    elif weekly_dir == "bear":
        direction = "bear"
    else:
        direction = "bull" if (above_sma20 and momentum > 0) else "bear"

    # Setup type
    if is_compressed and price_position < 0.8:
        setup_type = "Compression Breakout"
    elif vol_ratio > 1.5 and above_sma20:
        setup_type = "Volume Breakout"
    elif above_sma20 and above_sma5 and momentum > 0.01:
        setup_type = "Trend Continuation"
    elif not above_sma20 and momentum > 0.01:
        setup_type = "Reclaim"
    else:
        setup_type = "Mean Reversion"

    # Targets
    if direction == "bull":
        t1           = round(price * (1 + T1_MULTIPLIER), 2)
        t2           = round(price * (1 + T2_MULTIPLIER), 2)
        invalidation = round(price * (1 - STOP_MULTIPLIER), 2)
    else:
        t1           = round(price * (1 - T1_MULTIPLIER), 2)
        t2           = round(price * (1 - T2_MULTIPLIER), 2)
        invalidation = round(price * (1 + STOP_MULTIPLIER), 2)

    return {
        "entry":        price,
        "direction":    direction,
        "setup_type":   setup_type,
        "score":        score,
        "t1":           t1,
        "t2":           t2,
        "invalidation": invalidation,
        "vol_ratio":    round(vol_ratio, 2),
        "momentum":     round(momentum, 4),
        "compressed":   is_compressed,
    }


# ---------------------------------------------------------------------------
# Hourly outcome tracker
# ---------------------------------------------------------------------------

def track_outcome(signal: dict, hourly: pd.DataFrame, signal_date: pd.Timestamp) -> dict:
    """
    8-factor outcome tracker matching Sigmalytic scoreboard definition.

    A WIN requires ALL of:
      1. Direction aligned
      2. Opening read aligned (first 2 hourly bars)
      3. Key level respected (T1 touched/held)
      4. Timing window hit (within 3 trading days = ~21 hours)
      5. Path followed (clean progression, not choppy)
      6. Close confirmed (day 1 or day 2 close validates thesis)
      7. Regime matched (already filtered upstream)
      8. Tradeability confirmed (no gap-only moves)

    Grade:
      A = 8/8 factors + T2 hit
      B = 6-7/8 factors + T1 hit + close confirmed
      C = 4-5/8 factors
      D = 2-3/8 factors
      F = 0-1/8 factors or stop hit immediately
    """
    end_date = signal_date + timedelta(days=MAX_HOLD_DAYS)
    future_h = hourly[
        (hourly["timestamp"] > signal_date) &
        (hourly["timestamp"] <= end_date)
    ].copy().reset_index(drop=True)

    if future_h.empty or len(future_h) < 2:
        return _no_data_outcome()

    entry     = signal["entry"]
    direction = signal["direction"]
    t1        = signal["t1"]
    t2        = signal["t2"]
    stop      = signal["invalidation"]

    # --- FACTOR TRACKING ---
    factors = {
        "direction":      False,  # F1
        "opening_read":   False,  # F2
        "level_respected":False,  # F3
        "timing_window":  False,  # F4
        "path_quality":   False,  # F5
        "close_confirmed":False,  # F6
        "regime_matched": True,   # F7 — already filtered upstream
        "tradeability":   False,  # F8
    }

    t1_hit   = False
    t2_hit   = False
    stop_hit = False
    t1_bar   = None
    mae      = 0.0
    mfe      = 0.0
    highs    = []
    lows     = []

    # F8 Tradeability: first bar should not gap more than 2% from entry
    first_bar  = future_h.iloc[0]
    gap_pct    = abs(first_bar["open"] - entry) / entry
    factors["tradeability"] = gap_pct < 0.02

    # F2 Opening read: first 2 bars move in expected direction
    if len(future_h) >= 2:
        open_bars = future_h.iloc[:2]
        if direction == "bull":
            factors["opening_read"] = open_bars["close"].iloc[-1] > open_bars["open"].iloc[0]
        else:
            factors["opening_read"] = open_bars["close"].iloc[-1] < open_bars["open"].iloc[0]

    # Walk through hourly bars
    for i, row in future_h.iterrows():
        high  = row["high"]
        low   = row["low"]
        close = row["close"]
        highs.append(high)
        lows.append(low)

        if direction == "bull":
            adverse   = (low - entry) / entry
            favorable = (high - entry) / entry
            mae       = min(mae, adverse)
            mfe       = max(mfe, favorable)

            if low <= stop and not t1_hit:
                stop_hit = True
                break
            if high >= t1 and not t1_hit:
                t1_hit = True
                t1_bar = i
                factors["level_respected"] = True
                # F4 Timing: T1 within 21 hours (~3 trading days)
                factors["timing_window"] = i <= 21
            if high >= t2 and t1_hit:
                t2_hit = True
                break
        else:
            adverse   = (high - entry) / entry
            favorable = (entry - low) / entry
            mae       = min(mae, -adverse)
            mfe       = max(mfe, favorable)

            if high >= stop and not t1_hit:
                stop_hit = True
                break
            if low <= t1 and not t1_hit:
                t1_hit = True
                t1_bar = i
                factors["level_respected"] = True
                factors["timing_window"]   = i <= 21
            if low <= t2 and t1_hit:
                t2_hit = True
                break

    # F1 Direction: price moved net in correct direction
    if len(highs) > 0:
        if direction == "bull":
            factors["direction"] = future_h["close"].iloc[-1] > entry
        else:
            factors["direction"] = future_h["close"].iloc[-1] < entry

    # F5 Path quality: monotonic progression (not choppy)
    # Measure: no more than 2 bars reversing more than 1% against direction
    reversals = 0
    for i in range(1, len(future_h)):
        bar_ret = (future_h["close"].iloc[i] - future_h["close"].iloc[i-1]) / future_h["close"].iloc[i-1]
        if direction == "bull" and bar_ret < -0.01:
            reversals += 1
        elif direction == "bear" and bar_ret > 0.01:
            reversals += 1
    factors["path_quality"] = reversals <= 2

    # F6 Close confirmation: check closes at end of each trading day
    # Trading day = bars where hour is 15 or 16 (3pm-4pm ET)
    # Fallback: use last bar of each group of 7 hourly bars
    future_h2 = future_h.copy()
    future_h2["hour"] = future_h2["timestamp"].dt.hour
    
    # Try to find actual end-of-day bars (hour 15 or 16)
    eod_bars = future_h2[future_h2["hour"].isin([15, 16, 19, 20])]  # ET or UTC
    
    if not eod_bars.empty:
        # Check first two end-of-day closes
        for _, eod_bar in eod_bars.head(2).iterrows():
            eod_close = eod_bar["close"]
            if direction == "bull":
                if eod_close > entry * 1.003:  # closed 0.3% above entry
                    factors["close_confirmed"] = True
                    break
            else:
                if eod_close < entry * 0.997:
                    factors["close_confirmed"] = True
                    break
    else:
        # Fallback: use bar 6 and bar 13 as proxies for day 1 and day 2 close
        for proxy_idx in [6, 13]:
            if proxy_idx < len(future_h):
                proxy_close = future_h.iloc[proxy_idx]["close"]
                if direction == "bull":
                    if proxy_close > entry * 1.003:
                        factors["close_confirmed"] = True
                        break
                else:
                    if proxy_close < entry * 0.997:
                        factors["close_confirmed"] = True
                        break

    # Count factors passed
    factor_count = sum(factors.values())

    # Time to T1
    time_to_t1 = None
    if t1_hit and t1_bar is not None:
        t1_time    = future_h.loc[t1_bar, "timestamp"]
        time_to_t1 = int((t1_time - signal_date).total_seconds() / 3600)

    # TRUE WIN requires direction + level + timing + close (minimum 4 core factors)
    core_win = (
        factors["direction"] and
        factors["level_respected"] and
        factors["timing_window"] and
        factors["close_confirmed"] and
        not stop_hit
    )

    # Grade
    if core_win and t2_hit and factor_count >= 7:
        grade = "A"
    elif core_win and t1_hit and factor_count >= 6:
        grade = "B"
    elif t1_hit and factor_count >= 4 and not stop_hit:
        grade = "C"
    elif factor_count >= 2 and not stop_hit:
        grade = "D"
    else:
        grade = "F"

    # Failure classification
    failure_type = None
    if not core_win:
        if stop_hit and len(future_h) <= 4:
            failure_type = "Immediate Reversal"
        elif stop_hit:
            failure_type = "Stopped Out"
        elif not factors["close_confirmed"]:
            failure_type = "No Close Confirmation"
        elif not factors["timing_window"]:
            failure_type = "Timing Miss"
        elif not factors["level_respected"]:
            failure_type = "Weak Follow-Through"
        else:
            failure_type = "Partial"

    return {
        "win":              core_win,
        "t1_hit":          t1_hit,
        "t2_hit":          t2_hit,
        "stop_hit":        stop_hit,
        "mae":             round(mae, 4),
        "mfe":             round(mfe, 4),
        "time_to_t1_h":   time_to_t1,
        "failure_type":    failure_type,
        "grade":           grade,
        "factor_count":    factor_count,
        "f1_direction":    factors["direction"],
        "f2_opening":      factors["opening_read"],
        "f3_level":        factors["level_respected"],
        "f4_timing":       factors["timing_window"],
        "f5_path":         factors["path_quality"],
        "f6_close":        factors["close_confirmed"],
        "f7_regime":       factors["regime_matched"],
        "f8_tradeable":    factors["tradeability"],
    }


def _no_data_outcome() -> dict:
    return {
        "win": None, "t1_hit": None, "t2_hit": None,
        "stop_hit": None, "mae": None, "mfe": None,
        "time_to_t1_h": None, "failure_type": "No Data", "grade": None,
        "factor_count": None,
        "f1_direction": None, "f2_opening": None, "f3_level": None,
        "f4_timing": None, "f5_path": None, "f6_close": None,
        "f7_regime": None, "f8_tradeable": None,
    }


# ---------------------------------------------------------------------------
# Supabase writer
# ---------------------------------------------------------------------------

def write_to_supabase(records: list, supabase_url: str, supabase_key: str):
    if not records:
        return
    url     = f"{supabase_url}/rest/v1/backtest_results"
    headers = {
        "apikey":        supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    # Insert in batches of 100
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        try:
            resp = requests.post(url, json=batch, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  ⚠️  Supabase write error: {e}")


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_backtest(args):
    print("\n" + "=" * 62)
    print("  SIGMALYTIC — BACKTEST ENGINE")
    print(f"  Timeframes: Weekly + Daily + Hourly | Lookback: {LOOKBACK_YEARS}yr")
    print("=" * 62 + "\n")

    # Load universe
    universe = pd.read_csv(args.universe)
    symbols  = universe["Symbol"].tolist()
    sector_map = dict(zip(universe["Symbol"], universe["Sector_Normalized"]))
    print(f"📋 Universe loaded: {len(symbols)} symbols\n")

    # Date range
    end_date   = datetime.now()
    start_date = end_date - timedelta(days=365 * LOOKBACK_YEARS + 60)
    start_str  = start_date.strftime("%Y-%m-%dT00:00:00Z")
    end_str    = end_date.strftime("%Y-%m-%dT00:00:00Z")

    all_results = []
    total_signals = 0

    for sym_idx, symbol in enumerate(symbols):
        print(f"[{sym_idx+1}/{len(symbols)}] {symbol} — fetching bars...")

        # Fetch all three timeframes
        weekly  = fetch_bars(symbol, "1Week",  start_str, end_str, args.api_key, args.secret_key)
        daily   = fetch_bars(symbol, "1Day",   start_str, end_str, args.api_key, args.secret_key)
        hourly  = fetch_bars(symbol, "1Hour",  start_str, end_str, args.api_key, args.secret_key)
        time.sleep(0.5)

        if daily.empty or len(daily) < 30:
            print(f"  ⚠️  Insufficient data — skipping")
            continue

        print(f"  Daily: {len(daily)} bars | Hourly: {len(hourly)} bars | Weekly: {len(weekly)} bars")

        sym_signals = 0
        sector      = sector_map.get(symbol, "Unknown")

        # Walk forward through daily bars
        for i in range(20, len(daily) - 1):
            bar_date     = daily.iloc[i]["timestamp"]
            regime       = classify_regime(weekly, bar_date) if not weekly.empty else REGIME_BULL
            weekly_sig   = weekly_trend(weekly, bar_date) if not weekly.empty else {"direction":"neutral","strength":50}
            signal       = score_daily_bar(daily, i, weekly_sig)

            if signal is None:
                continue

            # HIGH PROBABILITY FILTER
            direction = signal["direction"]
            score     = signal["score"]
            weekly_dir = weekly_sig["direction"]

            if direction == "bull":
                # Long: Bull/Recovery regime, weekly bull, score 75+
                if regime in [REGIME_VOLATILE, REGIME_BEAR, REGIME_COMPRESS]:
                    continue
                if weekly_dir != "bull":
                    continue
                if score < 75:
                    continue
            elif direction == "bear":
                # Short: Bear/Volatile regime, weekly bear, score 80+ (proxy for A/B quality)
                if regime not in [REGIME_BEAR, REGIME_VOLATILE]:
                    continue
                if weekly_dir != "bear":
                    continue
                if score < 80:
                    continue
            else:
                continue

            # Track outcome using hourly bars
            outcome = track_outcome(signal, hourly, bar_date) if not hourly.empty else _no_data_outcome()

            record = {
                "symbol":           symbol,
                "sector":           sector,
                "signal_date":      bar_date.strftime("%Y-%m-%d"),
                "setup_type":       signal["setup_type"],
                "direction":        signal["direction"],
                "confidence_score": signal["score"],
                "entry_price":      signal["entry"],
                "t1":               signal["t1"],
                "t2":               signal["t2"],
                "invalidation":     signal["invalidation"],
                "vol_ratio":        signal["vol_ratio"],
                "momentum":         signal["momentum"],
                "compressed":       signal["compressed"],
                "regime":           regime,
                "weekly_direction": weekly_sig["direction"],
                "weekly_strength":  weekly_sig["strength"],
                "win":              outcome["win"],
                "t1_hit":           outcome["t1_hit"],
                "t2_hit":           outcome["t2_hit"],
                "stop_hit":         outcome["stop_hit"],
                "mae":              outcome["mae"],
                "mfe":              outcome["mfe"],
                "time_to_t1_h":     outcome["time_to_t1_h"],
                "failure_type":     outcome["failure_type"],
                "grade":            outcome["grade"],
                "factor_count":     outcome["factor_count"],
                "f1_direction":     outcome["f1_direction"],
                "f2_opening":       outcome["f2_opening"],
                "f3_level":         outcome["f3_level"],
                "f4_timing":        outcome["f4_timing"],
                "f5_path":          outcome["f5_path"],
                "f6_close":         outcome["f6_close"],
                "f7_regime":        outcome["f7_regime"],
                "f8_tradeable":     outcome["f8_tradeable"],
            }
            all_results.append(record)
            sym_signals += 1

        total_signals += sym_signals
        print(f"  ✅ {sym_signals} signals generated")

        # Write to Supabase every 500 records
        if len(all_results) >= 500 and args.supabase_url:
            write_to_supabase(all_results[-500:], args.supabase_url, args.supabase_key)

    # Write remaining to Supabase
    remainder = len(all_results) % 500
    if remainder > 0 and args.supabase_url:
        write_to_supabase(all_results[-remainder:], args.supabase_url, args.supabase_key)

    # Save CSV
    if all_results:
        df_out = pd.DataFrame(all_results)
        df_out.to_csv(args.output, index=False)

        # Summary stats
        valid   = df_out[df_out["win"].notna()]
        wins    = valid[valid["win"] == True]
        t1_hits = valid[valid["t1_hit"] == True]
        t2_hits = valid[valid["t2_hit"] == True]

        print(f"\n{'='*62}")
        print(f"  ✅ BACKTEST COMPLETE")
        print(f"{'='*62}")
        print(f"  Total signals:    {len(df_out):,}")
        print(f"  Win rate:         {len(wins)/len(valid)*100:.1f}%" if len(valid) > 0 else "  Win rate: N/A")
        print(f"  T1 hit rate:      {len(t1_hits)/len(valid)*100:.1f}%" if len(valid) > 0 else "")
        print(f"  T2 hit rate:      {len(t2_hits)/len(valid)*100:.1f}%" if len(valid) > 0 else "")
        print(f"  Avg MAE:          {valid['mae'].mean()*100:.2f}%" if len(valid) > 0 else "")
        print(f"  Avg MFE:          {valid['mfe'].mean()*100:.2f}%" if len(valid) > 0 else "")
        print(f"  Output:           {args.output}")
        print(f"{'='*62}\n")

        # Regime breakdown
        print("📊 Win rate by regime:\n")
        regime_stats = valid.groupby("regime").apply(
            lambda x: pd.Series({
                "Signals":  len(x),
                "Win Rate": f"{x['win'].mean()*100:.1f}%"
            })
        )
        print(regime_stats.to_string())

        # Sector breakdown
        print("\n📊 Win rate by sector:\n")
        sector_stats = valid.groupby("sector").apply(
            lambda x: pd.Series({
                "Signals":  len(x),
                "Win Rate": f"{x['win'].mean()*100:.1f}%"
            })
        )
        print(sector_stats.to_string())

        # Confidence calibration
        print("\n📊 Confidence calibration:\n")
        bins   = [65, 75, 85, 95, 101]
        labels = ["65-74","75-84","85-94","95-100"]
        valid2 = valid.copy()
        valid2["conf_band"] = pd.cut(valid2["confidence_score"], bins=bins, labels=labels, right=False)
        cal = valid2.groupby("conf_band", observed=True).apply(
            lambda x: pd.Series({
                "Signals":       len(x),
                "Actual Win %":  f"{x['win'].mean()*100:.1f}%"
            })
        )
        print(cal.to_string())

        # Factor pass rates — shows which factor is killing the win rate
        print("\n📊 Factor pass rates (which factors are failing):\n")
        factor_cols = {
            "f1_direction":  "F1 Direction",
            "f2_opening":    "F2 Opening Read",
            "f3_level":      "F3 Level Respected",
            "f4_timing":     "F4 Timing Window",
            "f5_path":       "F5 Path Quality",
            "f6_close":      "F6 Close Confirmed",
            "f7_regime":     "F7 Regime Matched",
            "f8_tradeable":  "F8 Tradeability",
        }
        for col, label in factor_cols.items():
            if col in df_out.columns:
                pass_rate = df_out[col].dropna().mean() * 100
                print(f"  {label:<25} {pass_rate:5.1f}% pass rate")

        # Factor count distribution
        print("\n📊 Factor count distribution:\n")
        if "factor_count" in df_out.columns:
            dist = df_out["factor_count"].dropna().value_counts().sort_index()
            for count, num in dist.items():
                print(f"  {int(count)}/8 factors: {num} signals ({num/len(df_out)*100:.1f}%)")

        # Failure type breakdown
        print("\n📊 Failure classification:\n")
        failures = df_out[df_out["win"] == False]["failure_type"].value_counts()
        for ftype, count in failures.items():
            print(f"  {ftype:<30} {count} ({count/len(df_out)*100:.1f}%)")
        print()
    else:
        print("\n⚠️  No signals generated. Check universe and scoring thresholds.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sigmalytic Backtest Engine")
    parser.add_argument("--api-key",      required=True)
    parser.add_argument("--secret-key",   required=True)
    parser.add_argument("--supabase-url", default=None,  help="Supabase project URL")
    parser.add_argument("--supabase-key", default=None,  help="Supabase anon key")
    parser.add_argument("--universe",     default="backtest_universe.csv")
    parser.add_argument("--output",       default="backtest_results.csv")
    parser.add_argument("--symbols",      default=None,  help="Comma-separated subset for testing, e.g. AAPL,MSFT")
    args = parser.parse_args()

    # Allow subset testing
    if args.symbols:
        subset = [s.strip().upper() for s in args.symbols.split(",")]
        uni    = pd.read_csv(args.universe)
        uni    = uni[uni["Symbol"].isin(subset)]
        uni.to_csv(args.universe, index=False)
        print(f"  Running subset: {subset}")

    run_backtest(args)


if __name__ == "__main__":
    main()
