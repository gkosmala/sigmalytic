# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Hurst / askSlim Cycle Engine
================================================================================
File    : hurst_cycle.py
Version : 1.0.0
Date    : 2026-05-27

PURPOSE
-------
Implements J.M. Hurst / Steve Miller (askSlim) cycle analysis.
Detects the dominant cycle rhythm from trough-to-trough measurements,
projects the next Cycle Low Timing Zone, and scores confluence when
price enters a timing window.

TIMEFRAME PROFILES
------------------
SHORT  : 90-day lookback  | 5-bar min trough distance  | fast EMA (3)
MEDIUM : 365-day lookback | 15-bar min trough distance | balanced EMA (5)
LONG   : 1095-day lookback| 45-bar min trough distance | macro EMA (13)

INTEGRATION
-----------
Called by confluence_bridge.py on every symbol scan.
Feeds into TimeCycleEngine's cycle_hits score.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import numpy as np

# ── Timeframe profiles ────────────────────────────────────────────────────────
TIMEFRAME_PROFILES: Dict[str, Dict] = {
    "SHORT": {
        "lookback_days"    : 90,
        "min_peak_distance": 5,
        "gann_window"      : 20,
        "scout_ema_span"   : 3,
        "label"            : "Short-Term (90d)",
    },
    "MEDIUM": {
        "lookback_days"    : 365,
        "min_peak_distance": 15,
        "gann_window"      : 60,
        "scout_ema_span"   : 5,
        "label"            : "Medium-Term (1Y)",
    },
    "LONG": {
        "lookback_days"    : 1095,
        "min_peak_distance": 45,
        "gann_window"      : 180,
        "scout_ema_span"   : 13,
        "label"            : "Long-Term (3Y)",
    },
}

# Minimum average daily dollar volume for liquidity check
MIN_DAILY_DOLLAR_VOLUME = 5_000_000


@dataclass
class HurstCycleResult:
    symbol              : str
    profile             : str                    # SHORT | MEDIUM | LONG
    dominant_cycle_days : int                    # Average trough-to-trough
    last_trough_date    : Optional[datetime]
    ideal_low_date      : Optional[datetime]
    window_start        : Optional[datetime]
    window_end          : Optional[datetime]
    is_inside_zone      : bool                   # Price inside timing window now
    days_to_window      : int                    # Days until window opens (0 if inside)
    translation         : str                    # "RIGHT" | "LEFT" | "NEUTRAL"
    reversal_scout      : str                    # "GREEN" | "PURPLE"
    liquidity_ok        : bool                   # Passed volume profile check
    score               : float                  # Confluence score (0-20)
    notes               : List[str]


class HurstCycleEngine:
    """
    Hurst / Steve Miller cycle engine.
    Uses trough-to-trough rhythm to project the next Cycle Low Timing Zone.
    """

    def __init__(self, profile: str = "MEDIUM"):
        self.profile = profile.upper()
        self.config  = TIMEFRAME_PROFILES.get(self.profile, TIMEFRAME_PROFILES["MEDIUM"])

    def _find_troughs(self, prices: np.ndarray) -> np.ndarray:
        """
        Finds cyclical lows using scipy if available,
        falls back to a pure numpy implementation.
        """
        try:
            from scipy.signal import find_peaks
            inverted = -prices
            prominence = prices.mean() * 0.02
            troughs, _ = find_peaks(
                inverted,
                distance=self.config["min_peak_distance"],
                prominence=prominence
            )
            return troughs
        except ImportError:
            # Pure numpy fallback — sliding window local minima
            dist = self.config["min_peak_distance"]
            troughs = []
            for i in range(dist, len(prices) - dist):
                window = prices[i - dist: i + dist + 1]
                if prices[i] == window.min() and prices[i] < prices[i-1] and prices[i] < prices[i+1]:
                    troughs.append(i)
            return np.array(troughs)

    def _reversal_scout(self, closes: np.ndarray) -> str:
        """
        Double-smoothed EMA proxy for the askSlim Reversal Scout.
        GREEN = bullish momentum, PURPLE = bearish momentum.
        """
        if len(closes) < 10:
            return "NEUTRAL"
        span = self.config["scout_ema_span"]
        import pandas as _pd
        s = _pd.Series(closes)
        short_ema    = s.ewm(span=span, adjust=False).mean()
        smoothed     = short_ema.ewm(span=span, adjust=False).mean()
        return "GREEN" if smoothed.iloc[-1] > smoothed.iloc[-2] else "PURPLE"

    def _check_translation(self, troughs: np.ndarray,
                           closes: np.ndarray) -> str:
        """
        Determines cycle translation — where does the peak sit within the cycle?
        RIGHT = bullish (peak late), LEFT = bearish (peak early).
        """
        if len(troughs) < 2:
            return "NEUTRAL"
        last_trough = troughs[-1]
        prev_trough = troughs[-2]
        cycle_len   = last_trough - prev_trough
        if cycle_len <= 0:
            return "NEUTRAL"

        # Find peak between the two troughs
        segment = closes[prev_trough:last_trough]
        if len(segment) == 0:
            return "NEUTRAL"
        peak_idx = int(np.argmax(segment))
        peak_pct = peak_idx / len(segment)

        if peak_pct > 0.55:
            return "RIGHT"    # Peak after midpoint = bullish
        elif peak_pct < 0.45:
            return "LEFT"     # Peak before midpoint = bearish
        else:
            return "NEUTRAL"

    def _liquidity_check(self, bars: List[dict]) -> bool:
        """Checks if average daily dollar volume meets minimum threshold."""
        if not bars:
            return False
        try:
            dollar_vols = [
                float(b.get('c', 0)) * float(b.get('v', 0))
                for b in bars[-20:]
                if b.get('c') and b.get('v')
            ]
            if not dollar_vols:
                return True  # Can't check, assume OK
            return (sum(dollar_vols) / len(dollar_vols)) >= MIN_DAILY_DOLLAR_VOLUME
        except Exception:
            return True

    def analyze(self, symbol: str, bars: List[dict],
                current_price: float) -> HurstCycleResult:
        """
        Main analysis function.
        bars: list of daily bar dicts with 'c' (close), 'v' (volume), 't' (timestamp)
        """
        notes: List[str] = []
        cfg = self.config

        # Liquidity check
        liquidity_ok = self._liquidity_check(bars)
        if not liquidity_ok:
            notes.append(f"Low liquidity — below ${MIN_DAILY_DOLLAR_VOLUME:,.0f}/day avg.")

        if len(bars) < 30:
            return HurstCycleResult(
                symbol=symbol, profile=self.profile,
                dominant_cycle_days=20, last_trough_date=None,
                ideal_low_date=None, window_start=None, window_end=None,
                is_inside_zone=False, days_to_window=99,
                translation="NEUTRAL", reversal_scout="NEUTRAL",
                liquidity_ok=liquidity_ok, score=0, notes=["Insufficient bars."]
            )

        closes    = np.array([float(b.get('c', 0)) for b in bars])
        troughs   = self._find_troughs(closes)

        # Dominant cycle length
        if len(troughs) >= 2:
            diffs = np.diff(troughs)
            dominant_cycle = int(np.mean(diffs))
            notes.append(f"Dominant cycle: {dominant_cycle} bars (from {len(troughs)} troughs).")
        else:
            dominant_cycle = cfg["min_peak_distance"] * 2
            notes.append(f"Sparse troughs — using fallback cycle of {dominant_cycle} bars.")

        # Last trough date
        last_trough_date = None
        if len(troughs) > 0:
            last_bar = bars[troughs[-1]]
            t = last_bar.get('t', '')
            try:
                last_trough_date = datetime.fromisoformat(
                    str(t).replace('Z', '+00:00')
                ).replace(tzinfo=None)
            except Exception:
                last_trough_date = datetime.utcnow() - timedelta(days=dominant_cycle)

        if last_trough_date is None:
            last_trough_date = datetime.utcnow() - timedelta(days=dominant_cycle)

        # Project next ideal low
        ideal_low_date = last_trough_date + timedelta(days=dominant_cycle)
        variance       = max(2, int(dominant_cycle * 0.15))
        window_start   = ideal_low_date - timedelta(days=variance)
        window_end     = ideal_low_date + timedelta(days=variance)
        now            = datetime.utcnow()
        is_inside_zone = (window_start <= now <= window_end)

        # Days to window
        if is_inside_zone:
            days_to_window = 0
        elif now < window_start:
            days_to_window = (window_start - now).days
        else:
            days_to_window = 0  # Window passed

        # Translation
        translation = self._check_translation(troughs, closes)

        # Reversal scout
        reversal_scout = self._reversal_scout(closes)

        # Score calculation
        score = 0.0
        if is_inside_zone:
            score += 12
            notes.append(f"Inside Hurst Timing Zone ({window_start.strftime('%m/%d')} — {window_end.strftime('%m/%d')}).")
            if reversal_scout == "GREEN":
                score += 6
                notes.append("Reversal Scout GREEN — momentum confirms timing zone.")
            if translation == "RIGHT":
                score += 2
                notes.append("Right-hand translation — bullish cycle structure.")
            elif translation == "LEFT":
                score -= 2
                notes.append("Left-hand translation — bearish cycle structure.")
        elif days_to_window <= 3:
            score += 5
            notes.append(f"Approaching timing zone in {days_to_window} days.")
        else:
            notes.append(f"Next timing zone: {window_start.strftime('%Y-%m-%d')} ({days_to_window} days away).")

        score = max(0.0, min(20.0, score))

        return HurstCycleResult(
            symbol=symbol, profile=self.profile,
            dominant_cycle_days=dominant_cycle,
            last_trough_date=last_trough_date,
            ideal_low_date=ideal_low_date,
            window_start=window_start,
            window_end=window_end,
            is_inside_zone=is_inside_zone,
            days_to_window=days_to_window,
            translation=translation,
            reversal_scout=reversal_scout,
            liquidity_ok=liquidity_ok,
            score=score,
            notes=notes,
        )


def score_hurst_cycle(symbol: str, bars: List[dict],
                      current_price: float,
                      profile: str = "MEDIUM") -> Dict[str, Any]:
    """
    Public interface for confluence_bridge.py
    Returns dict compatible with existing scoring pipeline.
    """
    try:
        engine = HurstCycleEngine(profile=profile)
        result = engine.analyze(symbol, bars, current_price)
        return {
            "hurst_profile"      : result.profile,
            "hurst_cycle_days"   : result.dominant_cycle_days,
            "hurst_inside_zone"  : result.is_inside_zone,
            "hurst_days_to_zone" : result.days_to_window,
            "hurst_translation"  : result.translation,
            "hurst_scout"        : result.reversal_scout,
            "hurst_score"        : result.score,
            "hurst_window_start" : result.window_start.strftime("%Y-%m-%d") if result.window_start else None,
            "hurst_window_end"   : result.window_end.strftime("%Y-%m-%d") if result.window_end else None,
            "hurst_notes"        : result.notes,
            "hurst_liquidity_ok" : result.liquidity_ok,
        }
    except Exception as e:
        return {
            "hurst_profile"    : profile,
            "hurst_cycle_days" : 0,
            "hurst_inside_zone": False,
            "hurst_days_to_zone": 99,
            "hurst_translation": "NEUTRAL",
            "hurst_scout"      : "NEUTRAL",
            "hurst_score"      : 0,
            "hurst_window_start": None,
            "hurst_window_end"  : None,
            "hurst_notes"      : [f"Hurst error: {e}"],
            "hurst_liquidity_ok": True,
        }


