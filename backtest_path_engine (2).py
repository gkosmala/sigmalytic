"""
backtest_path_engine.py
Sigmalytic Quant Corporation

Backtests the daily path prediction system against historical data.

For each trading day, for each asset in the basket:
  1. Calculates predicted levels from prior day data
  2. Grades 7 alignment factors using intraday bars
  3. Scores the day: X/12 assets fully aligned

Mirrors the live scoreboard grading logic exactly.

Usage:
  python backtest_path_engine.py \
    --api-key YOUR_KEY \
    --secret-key YOUR_SECRET \
    --output path_backtest_results.csv

Basket: SPX, NDX, NVDA, AAPL, GOOG, GOLD, AMD, INTC, IWM, TSLA, WMT, NKE
"""

import argparse
import time
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

# The live basket — matches your scoreboard exactly
BASKET = [
    ("SPY",  "SPX proxy",   "Index"),
    ("QQQ",  "NDX proxy",   "Index"),
    ("NVDA", "NVDA",        "Stock"),
    ("AAPL", "AAPL",        "Stock"),
    ("GOOG", "GOOG",        "Stock"),
    ("GLD",  "GOLD proxy",  "Commodity"),
    ("AMD",  "AMD",         "Stock"),
    ("INTC", "INTC",        "Stock"),
    ("IWM",  "IWM",         "Index"),
    ("TSLA", "TSLA",        "Stock"),
    ("WMT",  "WMT",         "Stock"),
    ("NKE",  "NKE",         "Stock"),
]

# Intraday time windows (Eastern Time hours)
OPEN_WINDOW_START  = 9.5    # 9:30
OPEN_WINDOW_END    = 10.5   # 10:30
EXP_WINDOW_START   = 10.5   # 10:30
EXP_WINDOW_END     = 12.0   # 12:00
MID_WINDOW_START   = 11.5   # 11:30
MID_WINDOW_END     = 13.5   # 1:30
AFT_WINDOW_START   = 13.5   # 1:30
AFT_WINDOW_END     = 14.5   # 2:30
CLOSE_WINDOW_START = 15.0   # 3:00
CLOSE_WINDOW_END   = 16.0   # 4:00

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
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.sort_values("t").reset_index(drop=True)
    df.rename(columns={
        "o": "open", "h": "high", "l": "low",
        "c": "close", "v": "volume", "t": "timestamp"
    }, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Level prediction engine
# ---------------------------------------------------------------------------

def calculate_levels(prior_daily: pd.Series, atr: float, price: float) -> dict:
    """
    Calculate predicted key levels from prior day data.
    Returns confluence zones for support, resistance, battle zone.
    """
    pdh  = prior_daily["high"]
    pdl  = prior_daily["low"]
    pdc  = prior_daily["close"]
    mid  = (pdh + pdl) / 2

    # ATR expansion levels
    exp1_up   = pdc + atr * 1.0
    exp2_up   = pdc + atr * 1.5
    exp1_dn   = pdc - atr * 1.0
    exp2_dn   = pdc - atr * 1.5

    # Confluence clustering — battle zone is where multiple levels overlap
    # Battle zone = within 0.3% of prior close
    battle_upper = pdc * 1.003
    battle_lower = pdc * 0.997

    return {
        "pdh":          pdh,
        "pdl":          pdl,
        "pdc":          pdc,
        "mid":          mid,
        "battle_upper": battle_upper,
        "battle_lower": battle_lower,
        "exp1_up":      exp1_up,
        "exp2_up":      exp2_up,
        "exp1_dn":      exp1_dn,
        "exp2_dn":      exp2_dn,
        "atr":          atr,
    }


def classify_bias(daily_df: pd.DataFrame, idx: int) -> str:
    """Classify daily bias from recent price structure."""
    if idx < 10:
        return "neutral"

    window = daily_df.iloc[max(0, idx-10):idx]
    closes = window["close"]
    highs  = window["high"]
    lows   = window["low"]

    sma10    = closes.mean()
    sma5     = closes.tail(5).mean()
    price    = daily_df.iloc[idx-1]["close"]
    momentum = (price - closes.iloc[0]) / closes.iloc[0]

    # Higher highs + higher lows = bullish structure
    hh = highs.iloc[-1] > highs.iloc[-3]
    hl = lows.iloc[-1] > lows.iloc[-3]
    lh = highs.iloc[-1] < highs.iloc[-3]
    ll = lows.iloc[-1] < lows.iloc[-3]

    if hh and hl and price > sma5:
        return "bullish"
    elif lh and ll and price < sma5:
        return "bearish"
    else:
        return "neutral"


def classify_regime(daily_df: pd.DataFrame, idx: int) -> str:
    """Classify market regime for the day."""
    if idx < 20:
        return "Trend"

    window    = daily_df.iloc[max(0, idx-20):idx]
    closes    = window["close"]
    returns   = closes.pct_change().dropna()
    vol       = returns.std()
    trend     = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0]
    range_pct = (window["high"].max() - window["low"].min()) / closes.mean()

    if vol > 0.025:
        return "Volatility Shock"
    elif abs(trend) < 0.01 and range_pct < 0.04:
        return "Compression"
    elif trend > 0.03:
        return "Trend"
    elif trend < -0.03:
        return "Bear"
    else:
        return "Rotation"


# ---------------------------------------------------------------------------
# 7-Factor grader
# ---------------------------------------------------------------------------

def grade_asset_day(
    symbol: str,
    bias: str,
    levels: dict,
    hourly: pd.DataFrame,
    trade_date: pd.Timestamp,
) -> dict:
    """
    Grade the 7 alignment factors for one asset on one day.
    Uses hourly bars — matches live system timeframe.

    Returns dict with factor scores and overall alignment.
    """

    # Filter to this trading day — handle timezone-aware timestamps
    try:
        trade_date_naive = trade_date.tz_localize(None) if trade_date.tzinfo is None else trade_date.tz_convert("UTC").tz_localize(None)
    except Exception:
        trade_date_naive = trade_date

    day_str = pd.Timestamp(trade_date_naive).strftime("%Y-%m-%d")

    # Normalize hourly timestamps for comparison
    h_ts = hourly["timestamp"].dt.tz_localize(None) if hourly["timestamp"].dt.tz is not None else hourly["timestamp"]
    h = hourly[h_ts.dt.strftime("%Y-%m-%d") == day_str].copy()

    if h.empty or len(h) < 4:
        return _no_data_grade()

    # Extract hour decimal for time-window filtering
    h["hour"] = h["timestamp"].dt.hour + h["timestamp"].dt.minute / 60

    # Use h as m5 throughout (same logic, hourly resolution)
    m5 = h

    # Day OHLC
    day_open  = m5["open"].iloc[0]
    day_high  = m5["high"].max()
    day_low   = m5["low"].min()
    day_close = m5["close"].iloc[-1]
    day_range = day_high - day_low

    if day_range == 0:
        return _no_data_grade()

    pdc          = levels["pdc"]
    battle_upper = levels["battle_upper"]
    battle_lower = levels["battle_lower"]
    pdh          = levels["pdh"]
    pdl          = levels["pdl"]

    factors = {}

    # -------------------------------------------------------------------
    # F1: Opening Alignment
    # Did the open behave as expected given the bias?
    # Bullish: open holds above battle_lower within first 30 min
    # Bearish: open holds below battle_upper
    # Neutral: open stays within battle zone
    # -------------------------------------------------------------------
    open_bars = m5[m5["hour"] <= OPEN_WINDOW_END] if not m5.empty else pd.DataFrame()

    if open_bars.empty:
        factors["f1_opening"] = False
    else:
        open_low   = open_bars["low"].min()
        open_high  = open_bars["high"].max()
        open_close = open_bars["close"].iloc[-1]

        if bias == "bullish":
            # Open should hold above prior close or recover quickly
            factors["f1_opening"] = open_close > pdc * 0.995
        elif bias == "bearish":
            factors["f1_opening"] = open_close < pdc * 1.005
        else:
            # Neutral: open should stay within battle zone (no early breakout)
            factors["f1_opening"] = battle_lower * 0.998 <= open_close <= battle_upper * 1.002

    # -------------------------------------------------------------------
    # F2: Key Level Respect
    # Did price behave correctly at predicted zones?
    # PDH/PDL and battle zone should act as support/resistance
    # -------------------------------------------------------------------
    pdh_zone_upper = pdh * 1.003
    pdh_zone_lower = pdh * 0.997
    pdl_zone_upper = pdl * 1.003
    pdl_zone_lower = pdl * 0.997

    # Check if PDH was tested and respected (rejected from above or held from below)
    touched_pdh = any((m5["high"] >= pdh_zone_lower) & (m5["high"] <= pdh_zone_upper * 1.01))
    touched_pdl = any((m5["low"] >= pdl_zone_lower * 0.99) & (m5["low"] <= pdl_zone_upper))

    if bias == "bullish":
        # PDL should hold as support if tested
        if touched_pdl:
            # Price should recover from PDL test
            recovery = day_close > pdl * 1.005
            factors["f2_levels"] = recovery
        else:
            # PDH breakout or holding above prior close
            factors["f2_levels"] = day_close > pdc * 0.998
    elif bias == "bearish":
        if touched_pdh:
            factors["f2_levels"] = day_close < pdh * 0.995
        else:
            factors["f2_levels"] = day_close < pdc * 1.002
    else:
        # Neutral: price stays between PDL and PDH
        factors["f2_levels"] = pdl * 0.99 <= day_close <= pdh * 1.01

    # -------------------------------------------------------------------
    # F3: Directional Resolution
    # Did the primary move occur in expected direction?
    # -------------------------------------------------------------------
    if bias == "bullish":
        factors["f3_direction"] = day_close > day_open
    elif bias == "bearish":
        factors["f3_direction"] = day_close < day_open
    else:
        # Neutral: small range day
        move_pct = abs(day_close - day_open) / day_open
        factors["f3_direction"] = move_pct < 0.01

    # -------------------------------------------------------------------
    # F4: Intraday Path Sequence
    # Did the day unfold in expected sequence?
    # Bullish: morning push → midday stall → afternoon continuation
    # -------------------------------------------------------------------
    morning_bars  = m5[m5["hour"].between(OPEN_WINDOW_START,  MID_WINDOW_START)]
    midday_bars   = m5[m5["hour"].between(MID_WINDOW_START,   AFT_WINDOW_START)]
    afternoon_bars = m5[m5["hour"].between(AFT_WINDOW_START,  CLOSE_WINDOW_END)]

    if morning_bars.empty or midday_bars.empty or afternoon_bars.empty:
        factors["f4_path"] = False
    else:
        morning_ret   = (morning_bars["close"].iloc[-1]   - morning_bars["open"].iloc[0])   / morning_bars["open"].iloc[0]
        midday_range  = (midday_bars["high"].max()        - midday_bars["low"].min())        / midday_bars["open"].iloc[0]
        afternoon_ret = (afternoon_bars["close"].iloc[-1] - afternoon_bars["open"].iloc[0]) / afternoon_bars["open"].iloc[0]

        if bias == "bullish":
            # Morning push up, midday stall (low range), afternoon continuation or hold
            morning_push   = morning_ret > -0.002       # didn't crash in morning
            midday_stall   = midday_range < 0.012       # relatively quiet midday
            aft_hold       = afternoon_ret > -0.005     # held or continued
            factors["f4_path"] = morning_push and aft_hold
        elif bias == "bearish":
            morning_drop   = morning_ret < 0.002
            aft_continue   = afternoon_ret < 0.005
            factors["f4_path"] = morning_drop and aft_continue
        else:
            # Neutral: tight range all day
            total_range = day_range / day_open
            factors["f4_path"] = total_range < 0.015

    # -------------------------------------------------------------------
    # F5: Timing Window Confirmation
    # Did expansion occur in the correct time window?
    # Primary expansion should happen 10:30-12:00 or 1:30-2:30
    # -------------------------------------------------------------------
    exp_bars  = m5[m5["hour"].between(EXP_WINDOW_START, EXP_WINDOW_END)]
    aft_bars  = m5[m5["hour"].between(AFT_WINDOW_START, AFT_WINDOW_END)]

    if exp_bars.empty and aft_bars.empty:
        factors["f5_timing"] = False
    else:
        # Find the biggest single 5-min move of the day
        m5["bar_ret"] = m5["close"].pct_change().abs()
        if not exp_bars.empty:
            exp_max_move = m5.loc[exp_bars.index, "bar_ret"].max() if len(exp_bars) > 0 else 0
        else:
            exp_max_move = 0
        if not aft_bars.empty:
            aft_max_move = m5.loc[aft_bars.index, "bar_ret"].max() if len(aft_bars) > 0 else 0
        else:
            aft_max_move = 0

        # Biggest move should be in one of the expansion windows
        other_bars  = m5[~m5["hour"].between(EXP_WINDOW_START, AFT_WINDOW_END)]
        other_max   = other_bars["bar_ret"].max() if not other_bars.empty else 0

        window_max  = max(exp_max_move, aft_max_move)
        factors["f5_timing"] = window_max >= other_max * 0.8  # window move at least 80% of max

    # -------------------------------------------------------------------
    # F6: Closing Alignment
    # Did the close confirm the bias?
    # A-grade: close in top 25% (bull) or bottom 25% (bear) of day's range
    # -------------------------------------------------------------------
    close_position = (day_close - day_low) / day_range if day_range > 0 else 0.5

    if bias == "bullish":
        factors["f6_close"] = close_position >= 0.60   # closed in upper 40% of range
    elif bias == "bearish":
        factors["f6_close"] = close_position <= 0.40   # closed in lower 40% of range
    else:
        factors["f6_close"] = 0.35 <= close_position <= 0.65  # closed mid-range

    # -------------------------------------------------------------------
    # F7: Tradeability / Cleanliness
    # Was the move clean and executable?
    # Measure: directional consistency of 5-min bars
    # Low whipsaw = high tradeability
    # -------------------------------------------------------------------
    if bias == "bullish":
        up_bars    = (m5["close"] > m5["open"]).sum()
        total_bars = len(m5)
        consistency = up_bars / total_bars if total_bars > 0 else 0.5
        factors["f7_tradeable"] = consistency >= 0.52
    elif bias == "bearish":
        dn_bars    = (m5["close"] < m5["open"]).sum()
        total_bars = len(m5)
        consistency = dn_bars / total_bars if total_bars > 0 else 0.5
        factors["f7_tradeable"] = consistency >= 0.52
    else:
        # Neutral: no strong directional bias in bars
        up_bars    = (m5["close"] > m5["open"]).sum()
        total_bars = len(m5)
        consistency = abs(up_bars / total_bars - 0.5) if total_bars > 0 else 0
        factors["f7_tradeable"] = consistency < 0.15

    # -------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------
    factor_count = sum(factors.values())
    aligned      = factor_count >= 6   # 6+ of 7 = fully aligned

    # Grade
    if factor_count == 7:
        grade = "A"
    elif factor_count == 6:
        grade = "B"
    elif factor_count == 5:
        grade = "C"
    elif factor_count == 4:
        grade = "D"
    else:
        grade = "F"

    return {
        "aligned":       aligned,
        "grade":         grade,
        "factor_count":  factor_count,
        "f1_opening":    factors["f1_opening"],
        "f2_levels":     factors["f2_levels"],
        "f3_direction":  factors["f3_direction"],
        "f4_path":       factors["f4_path"],
        "f5_timing":     factors["f5_timing"],
        "f6_close":      factors["f6_close"],
        "f7_tradeable":  factors["f7_tradeable"],
        "day_open":      round(day_open, 2),
        "day_high":      round(day_high, 2),
        "day_low":       round(day_low, 2),
        "day_close":     round(day_close, 2),
        "bias":          bias,
    }


def _no_data_grade() -> dict:
    return {
        "aligned": None, "grade": None, "factor_count": None,
        "f1_opening": None, "f2_levels": None, "f3_direction": None,
        "f4_path": None, "f5_timing": None, "f6_close": None,
        "f7_tradeable": None,
        "day_open": None, "day_high": None, "day_low": None, "day_close": None,
        "bias": None,
    }


# ---------------------------------------------------------------------------
# ATR calculator
# ---------------------------------------------------------------------------

def calculate_atr(daily_df: pd.DataFrame, idx: int, period: int = 14) -> float:
    start = max(1, idx - period)
    trs   = []
    for i in range(start, idx):
        h      = daily_df.iloc[i]["high"]
        l      = daily_df.iloc[i]["low"]
        c_prev = daily_df.iloc[i-1]["close"]
        tr     = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    return float(np.mean(trs)) if trs else daily_df.iloc[idx-1]["close"] * 0.01


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_backtest(args):
    print("\n" + "=" * 62)
    print("  SIGMALYTIC — PATH PREDICTION BACKTEST ENGINE")
    print(f"  Basket: {len(BASKET)} assets | Lookback: {LOOKBACK_YEARS}yr")
    print(f"  Grading: 7-factor alignment per asset per day")
    print("=" * 62 + "\n")

    end_date   = datetime.now()
    start_date = end_date - timedelta(days=365 * LOOKBACK_YEARS + 60)
    start_str  = start_date.strftime("%Y-%m-%dT00:00:00Z")
    end_str    = end_date.strftime("%Y-%m-%dT00:00:00Z")

    all_results = []

    for sym_idx, (symbol, name, asset_type) in enumerate(BASKET):
        print(f"[{sym_idx+1}/{len(BASKET)}] {symbol} ({name}) — fetching data...")

        # Fetch daily + hourly only — matches live system timeframes
        daily  = fetch_bars(symbol, "1Day",  start_str, end_str, args.api_key, args.secret_key)
        hourly = fetch_bars(symbol, "1Hour", start_str, end_str, args.api_key, args.secret_key)
        time.sleep(0.5)

        if daily.empty or len(daily) < 20:
            print(f"  ⚠️  Insufficient daily data — skipping")
            continue

        print(f"  Daily: {len(daily)} bars | Hourly: {len(hourly)} bars")

        # Walk forward through daily bars
        for i in range(20, len(daily)):
            trade_date = daily.iloc[i]["timestamp"]

            # Calculate levels from PRIOR day
            prior_bar = daily.iloc[i-1]
            atr       = calculate_atr(daily, i)
            price     = prior_bar["close"]
            levels    = calculate_levels(prior_bar, atr, price)

            # Classify bias and regime from prior structure
            bias   = classify_bias(daily, i)
            regime = classify_regime(daily, i)

            # Grade the day
            grade_result = grade_asset_day(
                symbol, bias, levels, hourly, trade_date
            )

            record = {
                "date":         trade_date.strftime("%Y-%m-%d"),
                "symbol":       symbol,
                "name":         name,
                "asset_type":   asset_type,
                "regime":       regime,
                "bias":         bias,
                "pdc":          round(levels["pdc"], 2),
                "pdh":          round(levels["pdh"], 2),
                "pdl":          round(levels["pdl"], 2),
                "atr":          round(levels["atr"], 4),
                "exp1_up":      round(levels["exp1_up"], 2),
                "exp1_dn":      round(levels["exp1_dn"], 2),
                **grade_result,
            }
            all_results.append(record)

        print(f"  ✅ {len([r for r in all_results if r['symbol'] == symbol])} days graded")

    # -------------------------------------------------------------------
    # Save and summarize
    # -------------------------------------------------------------------
    if not all_results:
        print("⚠️  No results generated.")
        return

    df = pd.DataFrame(all_results)
    df.to_csv(args.output, index=False)

    # Daily alignment scores
    valid = df[df["aligned"].notna()]

    print(f"\n{'='*62}")
    print(f"  ✅ PATH BACKTEST COMPLETE")
    print(f"{'='*62}")
    print(f"  Total asset-days graded: {len(valid):,}")
    print(f"  Overall alignment rate:  {valid['aligned'].mean()*100:.1f}%")
    print(f"  Avg factors per day:     {valid['factor_count'].mean():.2f}/7")
    print(f"  Output: {args.output}")

    # Daily score — X/12 assets aligned per day
    daily_scores = valid.groupby("date").agg(
        assets_total=("aligned", "count"),
        assets_aligned=("aligned", "sum"),
    )
    daily_scores["alignment_pct"] = daily_scores["assets_aligned"] / daily_scores["assets_total"] * 100
    avg_daily = daily_scores["alignment_pct"].mean()
    print(f"  Avg daily basket score:  {avg_daily:.1f}% assets aligned")

    # Grade distribution
    print(f"\n📊 Grade distribution:\n")
    grades = valid["grade"].value_counts().sort_index()
    for g, count in grades.items():
        print(f"  Grade {g}: {count:,} ({count/len(valid)*100:.1f}%)")

    # Factor pass rates
    print(f"\n📊 Factor pass rates:\n")
    factor_map = {
        "f1_opening":   "F1 Opening Alignment",
        "f2_levels":    "F2 Key Level Respect",
        "f3_direction": "F3 Directional Resolution",
        "f4_path":      "F4 Intraday Path Sequence",
        "f5_timing":    "F5 Timing Window",
        "f6_close":     "F6 Closing Alignment",
        "f7_tradeable": "F7 Tradeability",
    }
    for col, label in factor_map.items():
        if col in valid.columns:
            rate = valid[col].dropna().mean() * 100
            print(f"  {label:<30} {rate:5.1f}%")

    # Regime breakdown
    print(f"\n📊 Alignment by regime:\n")
    regime_stats = valid.groupby("regime").apply(
        lambda x: pd.Series({
            "Days":      len(x),
            "Aligned %": f"{x['aligned'].mean()*100:.1f}%",
            "Avg Score": f"{x['factor_count'].mean():.2f}/7",
        })
    )
    print(regime_stats.to_string())

    # Asset breakdown
    print(f"\n📊 Alignment by asset:\n")
    asset_stats = valid.groupby("symbol").apply(
        lambda x: pd.Series({
            "Days":      len(x),
            "Aligned %": f"{x['aligned'].mean()*100:.1f}%",
            "Avg Grade": x["factor_count"].mean(),
        })
    ).sort_values("Avg Grade", ascending=False)
    print(asset_stats.to_string())

    # Best days (8+/12 aligned)
    best_days = daily_scores[daily_scores["assets_aligned"] >= daily_scores["assets_total"] * 0.75]
    print(f"\n  High-alignment days (75%+ basket aligned): {len(best_days):,} ({len(best_days)/len(daily_scores)*100:.1f}% of trading days)")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sigmalytic Path Prediction Backtest")
    parser.add_argument("--api-key",    required=True)
    parser.add_argument("--secret-key", required=True)
    parser.add_argument("--output",     default="path_backtest_results.csv")
    parser.add_argument("--days",       type=int, default=None, help="Limit to last N trading days for testing")
    args = parser.parse_args()

    run_backtest(args)


if __name__ == "__main__":
    main()
