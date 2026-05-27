"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Weis Wave Engine
================================================================================
File    : weis_wave.py
Version : 1.0.0
Date    : 2026-05-27

PURPOSE
-------
Modernizes Wyckoff tape reading using David Weis's algorithmic wave approach.
Identifies cumulative volume waves based on price reversals, detects Springs
and Upthrusts, and measures Effort vs Result for confluence scoring.

TIMEFRAME DEFAULTS
------------------
1m  → 0.20% reversal threshold
5m  → 0.50% reversal threshold
15m → 0.75% reversal threshold
1H  → 1.00% reversal threshold
1D  → 1.50% reversal threshold
1W  → 2.50% reversal threshold

User can override threshold via Preferences page.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np

# ── Timeframe default thresholds ──────────────────────────────────────────────
TF_DEFAULTS: Dict[str, float] = {
    "1m" : 0.0020,
    "5m" : 0.0050,
    "15m": 0.0075,
    "1H" : 0.0100,
    "1D" : 0.0150,
    "1W" : 0.0250,
}

# ── Signal scoring weights ────────────────────────────────────────────────────
SPRING_SCORE    = 18   # Spring = highest signal (institutional accumulation)
UPTHRUST_SCORE  = 18   # Upthrust = highest signal (institutional distribution)
CLIMAX_SCORE    = 12   # Buying/Selling climax
NO_DEMAND_SCORE = 8    # No demand / no supply
EFFORT_FAIL_SCORE = 6  # Effort vs result failure


@dataclass
class WeisWave:
    direction  : int          # 1 = Up (Green), -1 = Down (Red)
    cum_volume : float        # Cumulative volume for this wave
    start_price: float        # Price at wave start
    end_price  : float        # Current/end price
    price_range: float        # Absolute price distance
    bar_count  : int          # Number of bars in wave
    effort_ratio: float       # price_range / cum_volume (normalized)


@dataclass
class WeisWaveResult:
    symbol          : str
    timeframe       : str
    threshold_pct   : float
    waves           : List[WeisWave]
    current_wave    : Optional[WeisWave]
    signal          : str           # "SPRING" | "UPTHRUST" | "CLIMAX_BUY" | "CLIMAX_SELL" | "NO_DEMAND" | "NO_SUPPLY" | "NONE"
    signal_score    : float         # Confluence score contribution (0-20)
    macro_bias      : int           # 1 = Bullish, -1 = Bearish, 0 = Neutral
    effort_vs_result: str           # "CONFIRM" | "DIVERGE" | "NEUTRAL"
    notes           : List[str]
    invalidation    : Optional[float]  # Stop level for options

    # ── Options placeholders (wired when Alpaca options access available) ──────
    options_setup   : Optional[Dict[str, Any]] = field(default=None)


class WeisWaveEngine:
    """
    Core Weis Wave calculation engine.
    Processes OHLCV bars into directional volume waves.
    """

    def __init__(self, reversal_threshold_pct: float = 0.005):
        self.threshold = reversal_threshold_pct

    @classmethod
    def for_timeframe(cls, timeframe: str,
                      user_override: Optional[float] = None) -> "WeisWaveEngine":
        """
        Factory method — creates engine calibrated to timeframe.
        User override (from Preferences) takes precedence.
        """
        threshold = user_override if user_override else TF_DEFAULTS.get(timeframe, 0.005)
        return cls(reversal_threshold_pct=threshold)

    def calculate_waves(self, bars: List[dict]) -> List[WeisWave]:
        """
        Core ZigZag + cumulative volume algorithm.
        Bars: list of dicts with keys 'c' (close), 'v' (volume), 'h' (high), 'l' (low)
        """
        if not bars or len(bars) < 5:
            return []

        waves: List[WeisWave] = []
        last_anchor = float(bars[0].get('c', 0))
        current_dir = 0
        cum_vol = 0.0
        wave_start = last_anchor
        bar_count = 0

        for bar in bars:
            price = float(bar.get('c', 0))
            vol   = float(bar.get('v', 0))
            if price <= 0:
                continue

            pct_chg = (price - last_anchor) / last_anchor if last_anchor > 0 else 0
            bar_count += 1
            cum_vol += vol

            if current_dir == 0:
                if pct_chg >= self.threshold:
                    current_dir = 1
                    last_anchor = price
                elif pct_chg <= -self.threshold:
                    current_dir = -1
                    last_anchor = price

            elif current_dir == 1:
                if price > last_anchor:
                    last_anchor = price
                elif pct_chg <= -self.threshold:
                    # Wave complete — record
                    price_range = abs(last_anchor - wave_start)
                    effort = price_range / (cum_vol / 1_000_000) if cum_vol > 0 else 0
                    waves.append(WeisWave(
                        direction=1, cum_volume=cum_vol,
                        start_price=wave_start, end_price=last_anchor,
                        price_range=price_range, bar_count=bar_count,
                        effort_ratio=round(effort, 4)
                    ))
                    current_dir = -1
                    wave_start = price
                    last_anchor = price
                    cum_vol = vol
                    bar_count = 1

            elif current_dir == -1:
                if price < last_anchor:
                    last_anchor = price
                elif pct_chg >= self.threshold:
                    price_range = abs(last_anchor - wave_start)
                    effort = price_range / (cum_vol / 1_000_000) if cum_vol > 0 else 0
                    waves.append(WeisWave(
                        direction=-1, cum_volume=cum_vol,
                        start_price=wave_start, end_price=last_anchor,
                        price_range=price_range, bar_count=bar_count,
                        effort_ratio=round(effort, 4)
                    ))
                    current_dir = 1
                    wave_start = price
                    last_anchor = price
                    cum_vol = vol
                    bar_count = 1

        # Add current forming wave
        if current_dir != 0 and cum_vol > 0:
            price_range = abs(last_anchor - wave_start)
            effort = price_range / (cum_vol / 1_000_000) if cum_vol > 0 else 0
            waves.append(WeisWave(
                direction=current_dir, cum_volume=cum_vol,
                start_price=wave_start, end_price=last_anchor,
                price_range=price_range, bar_count=bar_count,
                effort_ratio=round(effort, 4)
            ))

        return waves

    def analyze(self, symbol: str, timeframe: str,
                bars_5m: List[dict], bars_daily: List[dict],
                current_price: float,
                user_threshold: Optional[float] = None) -> WeisWaveResult:
        """
        Full multi-timeframe Weis Wave analysis.
        Returns scored result ready for confluence engine.
        """
        threshold = user_threshold or TF_DEFAULTS.get(timeframe, 0.005)
        notes: List[str] = []
        signal = "NONE"
        signal_score = 0.0
        invalidation = None
        options_setup = None

        # ── Macro bias from daily waves ────────────────────────────────────────
        daily_engine = WeisWaveEngine(TF_DEFAULTS.get("1D", 0.015))
        daily_waves = daily_engine.calculate_waves(bars_daily[-60:] if bars_daily else [])

        macro_bias = 0
        if daily_waves:
            # Count recent wave volumes to determine bias
            recent = daily_waves[-6:] if len(daily_waves) >= 6 else daily_waves
            up_vol   = sum(w.cum_volume for w in recent if w.direction == 1)
            down_vol = sum(w.cum_volume for w in recent if w.direction == -1)
            if up_vol > down_vol * 1.2:
                macro_bias = 1
                notes.append("Daily Weis Wave: Bullish bias — up waves dominate.")
            elif down_vol > up_vol * 1.2:
                macro_bias = -1
                notes.append("Daily Weis Wave: Bearish bias — down waves dominate.")
            else:
                notes.append("Daily Weis Wave: Neutral — balanced wave volume.")

        # ── Intraday waves ─────────────────────────────────────────────────────
        intra_engine = WeisWaveEngine(threshold)
        intra_waves = intra_engine.calculate_waves(bars_5m[-100:] if bars_5m else [])

        if len(intra_waves) < 3:
            return WeisWaveResult(
                symbol=symbol, timeframe=timeframe, threshold_pct=threshold,
                waves=intra_waves, current_wave=None, signal="NONE",
                signal_score=0, macro_bias=macro_bias,
                effort_vs_result="NEUTRAL", notes=notes, invalidation=None
            )

        current_wave = intra_waves[-1]
        prev_wave    = intra_waves[-2]
        prev2_wave   = intra_waves[-3] if len(intra_waves) >= 3 else None

        # ── Effort vs Result ───────────────────────────────────────────────────
        # Compare volume effort to price result vs prior wave
        effort_vs_result = "NEUTRAL"
        if prev_wave.cum_volume > 0 and current_wave.cum_volume > 0:
            vol_ratio   = current_wave.cum_volume / prev_wave.cum_volume
            range_ratio = current_wave.price_range / prev_wave.price_range if prev_wave.price_range > 0 else 1

            if vol_ratio > 1.5 and range_ratio < 0.5:
                effort_vs_result = "DIVERGE"
                notes.append(f"Effort vs Result FAIL: High volume ({vol_ratio:.1f}x) but small price move ({range_ratio:.1f}x).")
            elif vol_ratio < 0.5 and range_ratio > 1.2:
                effort_vs_result = "DIVERGE"
                notes.append(f"Effort vs Result FAIL: Low volume ({vol_ratio:.1f}x) but large price move — potential trap.")
            elif vol_ratio > 0.8 and range_ratio > 0.8:
                effort_vs_result = "CONFIRM"
                notes.append("Effort confirms result — institutional backing present.")

        # ── Spring Detection ───────────────────────────────────────────────────
        # Bullish daily + hourly support broken + low volume down wave + reversal up
        if (macro_bias >= 0 and
            current_wave.direction == 1 and
            prev_wave.direction == -1 and
            prev_wave.cum_volume < (prev2_wave.cum_volume * 0.7 if prev2_wave else float('inf'))):

            signal = "SPRING"
            signal_score = SPRING_SCORE
            invalidation = prev_wave.end_price  # Low of the false breakdown
            notes.append(f"SPRING detected: Low-volume breakdown ({prev_wave.cum_volume:,.0f}) reversed. Institutional accumulation likely.")

            # ── OPTIONS PLACEHOLDER ───────────────────────────────────────────
            options_setup = {
                "signal"          : "SPRING",
                "bias"            : "BULLISH",
                "invalidation"    : invalidation,
                # PLACEHOLDER: Replace with live Alpaca options data
                "long_call_strike": round(current_price * 0.99, 2),
                "bull_put_short"  : round(current_price * 0.95, 2),
                "bull_put_long"   : round(current_price * 0.94, 2),
                "intraday_dte"    : "0-3 DTE",
                "swing_dte"       : "30-45 DTE",
                "delta_target"    : 0.60,
                "stop_level"      : invalidation,
                "stop_note"       : "Exit if price closes below Spring low — institutional context failed.",
                # PLACEHOLDER: IV crush filter — wire to Alpaca options chain
                "iv_filter"       : "PENDING_OPTIONS_ACCESS",
                # PLACEHOLDER: Broker execution — wire to Alpaca orders API
                "execution"       : "PENDING_BROKER_INTEGRATION",
            }

        # ── Upthrust Detection ────────────────────────────────────────────────
        elif (macro_bias <= 0 and
              current_wave.direction == -1 and
              prev_wave.direction == 1 and
              prev_wave.cum_volume < (prev2_wave.cum_volume * 0.7 if prev2_wave else float('inf'))):

            signal = "UPTHRUST"
            signal_score = UPTHRUST_SCORE
            invalidation = prev_wave.end_price  # High of the false breakout
            notes.append(f"UPTHRUST detected: Low-volume rally ({prev_wave.cum_volume:,.0f}) rejected. Institutional distribution likely.")

            # ── OPTIONS PLACEHOLDER ───────────────────────────────────────────
            options_setup = {
                "signal"           : "UPTHRUST",
                "bias"             : "BEARISH",
                "invalidation"     : invalidation,
                # PLACEHOLDER: Replace with live Alpaca options data
                "long_put_strike"  : round(current_price * 1.01, 2),
                "bear_call_short"  : round(current_price * 1.05, 2),
                "bear_call_long"   : round(current_price * 1.06, 2),
                "intraday_dte"     : "0-3 DTE",
                "swing_dte"        : "30-45 DTE",
                "delta_target"     : 0.60,
                "stop_level"       : invalidation,
                "stop_note"        : "Exit if price closes above Upthrust high — institutional context failed.",
                # PLACEHOLDER: IV crush filter
                "iv_filter"        : "PENDING_OPTIONS_ACCESS",
                # PLACEHOLDER: Broker execution
                "execution"        : "PENDING_BROKER_INTEGRATION",
            }

        # ── Buying Climax Detection ────────────────────────────────────────────
        elif (current_wave.direction == 1 and prev_wave.direction == 1 and
              current_wave.cum_volume > prev_wave.cum_volume * 2.0 and
              effort_vs_result == "DIVERGE"):
            signal = "CLIMAX_BUY"
            signal_score = CLIMAX_SCORE
            notes.append("Buying Climax: Extreme up volume with stalling price — distribution phase likely.")

        # ── Selling Climax Detection ───────────────────────────────────────────
        elif (current_wave.direction == -1 and prev_wave.direction == -1 and
              current_wave.cum_volume > prev_wave.cum_volume * 2.0 and
              effort_vs_result == "DIVERGE"):
            signal = "CLIMAX_SELL"
            signal_score = CLIMAX_SCORE
            notes.append("Selling Climax: Extreme down volume with stabilizing price — accumulation phase likely.")

        # ── No Demand / No Supply ──────────────────────────────────────────────
        elif (current_wave.direction == 1 and
              current_wave.cum_volume < prev_wave.cum_volume * 0.4):
            signal = "NO_DEMAND"
            signal_score = NO_DEMAND_SCORE
            notes.append("No Demand: Weak up wave volume — rally lacks institutional backing.")

        elif (current_wave.direction == -1 and
              current_wave.cum_volume < prev_wave.cum_volume * 0.4):
            signal = "NO_SUPPLY"
            signal_score = NO_DEMAND_SCORE
            notes.append("No Supply: Weak down wave volume — selloff lacks conviction.")

        return WeisWaveResult(
            symbol=symbol, timeframe=timeframe, threshold_pct=threshold,
            waves=intra_waves, current_wave=current_wave,
            signal=signal, signal_score=signal_score,
            macro_bias=macro_bias, effort_vs_result=effort_vs_result,
            notes=notes, invalidation=invalidation,
            options_setup=options_setup,
        )


def score_weis_wave(symbol: str, timeframe: str,
                    bars_5m: List[dict], bars_daily: List[dict],
                    current_price: float,
                    user_threshold: Optional[float] = None) -> Dict[str, Any]:
    """
    Public interface for confluence_bridge.py
    Returns dict compatible with existing scoring pipeline.
    """
    try:
        engine = WeisWaveEngine.for_timeframe(timeframe, user_threshold)
        result = engine.analyze(symbol, timeframe, bars_5m, bars_daily,
                                current_price, user_threshold)
        return {
            "weis_signal"      : result.signal,
            "weis_score"       : result.signal_score,
            "weis_macro_bias"  : result.macro_bias,
            "weis_effort"      : result.effort_vs_result,
            "weis_notes"       : result.notes,
            "weis_invalidation": result.invalidation,
            "weis_options"     : result.options_setup,
            "weis_wave_count"  : len(result.waves),
        }
    except Exception as e:
        return {
            "weis_signal": "NONE", "weis_score": 0,
            "weis_macro_bias": 0, "weis_effort": "NEUTRAL",
            "weis_notes": [f"Weis Wave error: {e}"],
            "weis_invalidation": None, "weis_options": None,
            "weis_wave_count": 0,
        }
