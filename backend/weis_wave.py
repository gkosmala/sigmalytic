# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
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

    def _detect_sot(self, bars: List[dict]) -> Optional[dict]:
        """
        Candle-style Shortening of the Thrust (SOT) detection.
        Looks for 3 consecutive same-direction candles with decreasing thrust
        and sustained volume — signals institutional exhaustion.
        """
        if not bars or len(bars) < 3:
            return None

        try:
            for i in range(len(bars) - 1, 1, -1):
                c1 = bars[i - 2]
                c2 = bars[i - 1]
                c3 = bars[i]

                o1,c1p = float(c1.get('o',0)), float(c1.get('c',0))
                o2,c2p = float(c2.get('o',0)), float(c2.get('c',0))
                o3,c3p = float(c3.get('o',0)), float(c3.get('c',0))
                v2     = float(c2.get('v',0))
                v3     = float(c3.get('v',0))
                h3     = float(c3.get('h', c3p))
                l3     = float(c3.get('l', c3p))

                # ── Bearish SOT (uptrend exhausting) ──────────────────────
                if c1p > o1 and c2p > o2 and c3p > o3:
                    thrust1 = c2p - c1p
                    thrust2 = c3p - c2p
                    if thrust1 > 0 and thrust2 > 0 and thrust2 < thrust1 * 0.6 and v3 >= v2 * 0.9:
                        return {
                            "signal"      : "SOT_BEARISH",
                            "score"       : 16,
                            "invalidation": h3,
                            "note"        : f"Bearish SOT: Thrust fracturing on upwave. Invalidation {h3:.2f}.",
                            "options"     : {
                                "signal"          : "SOT_BEARISH",
                                "bias"            : "BEARISH",
                                "invalidation"    : h3,
                                "long_put_strike" : round(c3p * 1.01, 2),
                                "bear_call_short" : round(c3p * 1.05, 2),
                                "bear_call_long"  : round(c3p * 1.06, 2),
                                "stop_note"       : f"Exit if price closes above {h3:.2f}",
                                "execution"       : "PENDING_BROKER_INTEGRATION",
                            }
                        }

                # ── Bullish SOT (downtrend exhausting) ────────────────────
                if c1p < o1 and c2p < o2 and c3p < o3:
                    thrust1 = c1p - c2p
                    thrust2 = c2p - c3p
                    if thrust1 > 0 and thrust2 > 0 and thrust2 < thrust1 * 0.6 and v3 >= v2 * 0.9:
                        return {
                            "signal"      : "SOT_BULLISH",
                            "score"       : 16,
                            "invalidation": l3,
                            "note"        : f"Bullish SOT: Thrust fracturing on downwave. Invalidation {l3:.2f}.",
                            "options"     : {
                                "signal"          : "SOT_BULLISH",
                                "bias"            : "BULLISH",
                                "invalidation"    : l3,
                                "long_call_strike": round(c3p * 0.99, 2),
                                "bull_put_short"  : round(c3p * 0.95, 2),
                                "bull_put_long"   : round(c3p * 0.94, 2),
                                "stop_note"       : f"Exit if price closes below {l3:.2f}",
                                "execution"       : "PENDING_BROKER_INTEGRATION",
                            }
                        }
        except Exception:
            pass
        return None

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

        # ── Shortening of the Thrust (SOT) detection ─────────────────────────
        sot_signal = self._detect_sot(bars_5m)
        if sot_signal and signal == "NONE":
            signal       = sot_signal["signal"]
            signal_score = sot_signal["score"]
            invalidation = sot_signal["invalidation"]
            notes.append(sot_signal["note"])
            if sot_signal["options"]:
                options_setup = sot_signal["options"]

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

# ================================================================================
# THREE-BAR REVERSAL PATTERN DETECTION
# ================================================================================

THREE_BAR_REVERSAL_SCORE = 14

@dataclass
class ThreeBarReversal:
    direction   : str    # "BULLISH" | "BEARISH"
    score       : float
    invalidation: float
    note        : str
    bar_index   : int    # Index of the middle (key) bar


def detect_three_bar_reversal(bars: List[dict]) -> Optional[ThreeBarReversal]:
    """
    Detects classic 3-bar reversal patterns on any timeframe.

    BEARISH 3-Bar Reversal (Topping):
      Bar 1: Strong up bar (close > open, range > avg_range)
      Bar 2: Inside bar or narrow range — indecision
      Bar 3: Strong down bar closing below Bar 1 open — commitment reversal

    BULLISH 3-Bar Reversal (Bottoming):
      Bar 1: Strong down bar (close < open, range > avg_range)
      Bar 2: Inside bar or narrow range — indecision
      Bar 3: Strong up bar closing above Bar 1 open — commitment reversal

    Volume confirmation: Bar 3 volume >= Bar 1 volume * 0.8
    """
    if not bars or len(bars) < 5:
        return None

    try:
        # Use last 5 bars, scan most recent 3-bar windows
        scan_bars = bars[-5:]
        avg_range = sum(
            abs(float(b.get('h', 0)) - float(b.get('l', 0)))
            for b in scan_bars
        ) / len(scan_bars)

        if avg_range <= 0:
            return None

        for i in range(len(scan_bars) - 2, 0, -1):
            b1 = scan_bars[i - 1]
            b2 = scan_bars[i]
            b3 = scan_bars[i + 1]

            o1 = float(b1.get('o', 0)); c1 = float(b1.get('c', 0))
            o2 = float(b2.get('o', 0)); c2 = float(b2.get('c', 0))
            o3 = float(b3.get('o', 0)); c3 = float(b3.get('c', 0))
            h1 = float(b1.get('h', 0)); l1 = float(b1.get('l', 0))
            h2 = float(b2.get('h', 0)); l2 = float(b2.get('l', 0))
            h3 = float(b3.get('h', 0)); l3 = float(b3.get('l', 0))
            v1 = float(b1.get('v', 0)); v3 = float(b3.get('v', 0))

            if any(x <= 0 for x in [o1, c1, o2, c2, o3, c3]):
                continue

            range1 = h1 - l1
            range2 = h2 - l2
            range3 = h3 - l3

            # ── BEARISH 3-Bar Reversal ────────────────────────────────────────
            bar1_strong_up  = c1 > o1 and range1 >= avg_range * 0.8
            bar2_indecision = range2 <= range1 * 0.6  # inside or narrow
            bar3_strong_down = c3 < o3 and c3 < o1    # closes below Bar 1 open
            bar3_volume_ok  = v3 >= v1 * 0.8

            if bar1_strong_up and bar2_indecision and bar3_strong_down and bar3_volume_ok:
                return ThreeBarReversal(
                    direction    = "BEARISH",
                    score        = THREE_BAR_REVERSAL_SCORE,
                    invalidation = h1,  # Stop above Bar 1 high
                    note         = (
                        f"Bearish 3-Bar Reversal: Strong up ({c1:.2f}) → "
                        f"indecision → breakdown below {o1:.2f}. "
                        f"Invalidation: {h1:.2f}."
                    ),
                    bar_index = i,
                )

            # ── BULLISH 3-Bar Reversal ────────────────────────────────────────
            bar1_strong_down = c1 < o1 and range1 >= avg_range * 0.8
            bar2_indecision2 = range2 <= range1 * 0.6
            bar3_strong_up   = c3 > o3 and c3 > o1   # closes above Bar 1 open
            bar3_volume_ok2  = v3 >= v1 * 0.8

            if bar1_strong_down and bar2_indecision2 and bar3_strong_up and bar3_volume_ok2:
                return ThreeBarReversal(
                    direction    = "BULLISH",
                    score        = THREE_BAR_REVERSAL_SCORE,
                    invalidation = l1,  # Stop below Bar 1 low
                    note         = (
                        f"Bullish 3-Bar Reversal: Strong down ({c1:.2f}) → "
                        f"indecision → recovery above {o1:.2f}. "
                        f"Invalidation: {l1:.2f}."
                    ),
                    bar_index = i,
                )

    except Exception:
        pass

    return None


# ================================================================================
# WYCKOFF ANCHOR CROSS-REFERENCE (Spring Validation)
# ================================================================================

def validate_spring_against_anchors(
    symbol: str,
    spring_low: float,
    current_price: float,
    supabase_client=None,
) -> dict:
    """
    Validates a detected Spring against stored Wyckoff SC_Low and ST_Low anchors.

    A true Wyckoff Spring requires:
    1. Spring low is at or below SC_Low (tests the climax floor)
    2. Spring low is within 4% of SC_Low (not a random dip)
    3. Current price has recovered above SC_Low (false breakdown confirmed)
    4. Optionally: ST_Low anchor exists confirming Phase C context

    Returns validation result with confidence level.
    """
    result = {
        "spring_validated"  : False,
        "spring_confidence" : "LOW",
        "sc_low"            : None,
        "st_low"            : None,
        "spring_low"        : spring_low,
        "validation_note"   : "No Wyckoff anchors found — Spring unvalidated.",
    }

    if not supabase_client:
        # Try importing from environment
        try:
            import os
            from supabase import create_client
            url = os.getenv("SUPABASE_URL", "")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            if url and key:
                supabase_client = create_client(url, key)
        except Exception:
            return result

    if not supabase_client:
        return result

    try:
        resp = supabase_client.table("geometric_structures") \
            .select("structure_type,price_level") \
            .eq("ticker", symbol) \
            .eq("is_active", True) \
            .in_("structure_type", ["Wyckoff_SC_Low", "Wyckoff_ST_Low"]) \
            .execute()

        anchors = {row["structure_type"]: row["price_level"]
                   for row in (resp.data or [])}

        sc_low = anchors.get("Wyckoff_SC_Low")
        st_low = anchors.get("Wyckoff_ST_Low")

        result["sc_low"] = sc_low
        result["st_low"] = st_low

        if not sc_low:
            result["validation_note"] = "SC_Low anchor not found — Spring cannot be validated."
            return result

        sc_low = float(sc_low)

        # Check 1: Spring low tested near SC floor (within 4%)
        tested_floor = spring_low <= sc_low * 1.04

        # Check 2: Not a catastrophic breakdown (within 4% below SC)
        not_breakdown = spring_low >= sc_low * 0.96

        # Check 3: Price has recovered above SC floor
        recovered = current_price > sc_low

        if tested_floor and not_breakdown and recovered:
            confidence = "HIGH" if st_low else "MEDIUM"
            note = (
                f"✅ Validated Spring: Low {spring_low:.2f} tested SC floor "
                f"{sc_low:.2f} and recovered to {current_price:.2f}. "
            )
            if st_low:
                note += f"ST_Low anchor {float(st_low):.2f} confirms Phase C context. "
                confidence = "HIGH"
            note += f"Confidence: {confidence}."

            result.update({
                "spring_validated"  : True,
                "spring_confidence" : confidence,
                "validation_note"   : note,
            })
        else:
            reasons = []
            if not tested_floor:
                reasons.append(f"Low {spring_low:.2f} didn't reach SC floor {sc_low:.2f}")
            if not not_breakdown:
                reasons.append(f"Low {spring_low:.2f} broke too far below SC {sc_low:.2f}")
            if not recovered:
                reasons.append(f"Price {current_price:.2f} hasn't recovered above SC {sc_low:.2f}")
            result["validation_note"] = "Spring rejected: " + "; ".join(reasons) + "."

    except Exception as e:
        result["validation_note"] = f"Anchor lookup error: {e}"

    return result


# ================================================================================
# ENHANCED SCORE FUNCTION — includes 3-bar reversal + anchor validation
# ================================================================================

def score_weis_wave_enhanced(
    symbol       : str,
    timeframe    : str,
    bars_5m      : List[dict],
    bars_daily   : List[dict],
    current_price: float,
    user_threshold: Optional[float] = None,
    supabase_client = None,
) -> Dict[str, Any]:
    """
    Enhanced version of score_weis_wave that adds:
    1. 3-bar reversal detection on 5m bars
    2. Spring validation against Wyckoff anchors
    3. Combined signal with confidence level

    Drop-in replacement for score_weis_wave in confluence_bridge.py.
    """
    # Get base Weis Wave result
    base = score_weis_wave(symbol, timeframe, bars_5m, bars_daily,
                           current_price, user_threshold)

    # ── 3-Bar Reversal Detection ──────────────────────────────────────────────
    tbr = detect_three_bar_reversal(bars_5m)
    if tbr:
        base["three_bar_reversal"]       = tbr.direction
        base["three_bar_reversal_score"] = tbr.score
        base["three_bar_invalidation"]   = tbr.invalidation
        base["three_bar_note"]           = tbr.note

        # Upgrade signal if no stronger signal already detected
        if base.get("weis_signal") == "NONE":
            base["weis_signal"] = f"3BAR_{tbr.direction}"
            base["weis_score"]  = tbr.score
            base["weis_notes"]  = base.get("weis_notes", []) + [tbr.note]
            base["weis_invalidation"] = tbr.invalidation
    else:
        base["three_bar_reversal"] = None

    # ── Spring Anchor Validation ──────────────────────────────────────────────
    if base.get("weis_signal") == "SPRING" and bars_5m:
        try:
            spring_low = min(float(b.get('l', current_price)) for b in bars_5m[-10:])
            validation = validate_spring_against_anchors(
                symbol, spring_low, current_price, supabase_client
            )
            base["spring_validated"]   = validation["spring_validated"]
            base["spring_confidence"]  = validation["spring_confidence"]
            base["spring_sc_low"]      = validation["sc_low"]
            base["spring_validation_note"] = validation["validation_note"]
            base["weis_notes"] = base.get("weis_notes", []) + [validation["validation_note"]]

            # Boost score for validated Springs
            if validation["spring_validated"]:
                confidence_boost = {"HIGH": 6, "MEDIUM": 3, "LOW": 0}
                base["weis_score"] = min(
                    20,
                    base.get("weis_score", SPRING_SCORE) +
                    confidence_boost.get(validation["spring_confidence"], 0)
                )
        except Exception as _e:
            base["spring_validated"] = False
            base["spring_confidence"] = "UNVERIFIED"
    else:
        base["spring_validated"]  = False
        base["spring_confidence"] = None

    return base


# ================================================================================
# LIGHTWEIGHT RADAR SIGNAL (daily bars only — no intraday fetch)
# ================================================================================

def score_weis_wave_radar(
    symbol      : str,
    bars_daily  : List[dict],
    current_price: float,
) -> Dict[str, Any]:
    """
    Lightweight Weis Wave scoring for the universe radar scan.
    Uses daily bars only — no intraday API calls.
    Detects: 3-bar reversal, daily Spring/Upthrust, macro bias.
    Fast enough to run on 1,403 symbols without delay.
    """
    empty = {
        "weis_signal"   : "NONE",
        "weis_score"    : 0,
        "weis_macro_bias": 0,
        "three_bar_reversal": None,
    }

    if not bars_daily or len(bars_daily) < 5:
        return empty

    try:
        # Daily macro bias
        engine = WeisWaveEngine(TF_DEFAULTS["1D"])
        waves  = engine.calculate_waves(bars_daily[-60:])

        macro_bias = 0
        if len(waves) >= 4:
            recent   = waves[-6:]
            up_vol   = sum(w.cum_volume for w in recent if w.direction ==  1)
            down_vol = sum(w.cum_volume for w in recent if w.direction == -1)
            if up_vol > down_vol * 1.2:
                macro_bias = 1
            elif down_vol > up_vol * 1.2:
                macro_bias = -1

        # 3-bar reversal on daily bars
        tbr = detect_three_bar_reversal(bars_daily)

        signal = "NONE"
        score  = 0

        if tbr:
            signal = f"3BAR_{tbr.direction}"
            score  = tbr.score

        # Daily Spring / Upthrust from waves
        elif len(waves) >= 3:
            cw  = waves[-1]
            pw  = waves[-2]
            pw2 = waves[-3]

            # Daily Spring
            if (macro_bias >= 0 and cw.direction == 1 and pw.direction == -1 and
                    pw.cum_volume < pw2.cum_volume * 0.7):
                signal = "SPRING"
                score  = SPRING_SCORE

            # Daily Upthrust
            elif (macro_bias <= 0 and cw.direction == -1 and pw.direction == 1 and
                    pw.cum_volume < pw2.cum_volume * 0.7):
                signal = "UPTHRUST"
                score  = UPTHRUST_SCORE

            # Daily Buying Climax
            elif (cw.direction == 1 and len(waves) >= 2 and
                    cw.cum_volume > pw.cum_volume * 2.0 and
                    cw.price_range < pw.price_range * 0.5):
                signal = "CLIMAX_BUY"
                score  = CLIMAX_SCORE

            # Daily Selling Climax
            elif (cw.direction == -1 and len(waves) >= 2 and
                    cw.cum_volume > pw.cum_volume * 2.0 and
                    cw.price_range < pw.price_range * 0.5):
                signal = "CLIMAX_SELL"
                score  = CLIMAX_SCORE

        return {
            "weis_signal"       : signal,
            "weis_score"        : score,
            "weis_macro_bias"   : macro_bias,
            "three_bar_reversal": tbr.direction if tbr else None,
            "three_bar_note"    : tbr.note if tbr else None,
        }

    except Exception:
        return empty

