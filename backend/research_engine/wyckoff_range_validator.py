# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/wyckoff_range_validator.py
---------------------------------------------------
Range-maturity validator, built to fill a genuine, confirmed gap: no
existing engine measured whether a trading range was actually mature
(multiple, time-separated touches of the same support/resistance
level over weeks) before treating a sweep/exhaustion/reclaim sequence
as a real, tradeable setup.

Per David Weis's own framework (Trades About to Happen), a Spring or
Upthrust only qualifies as a genuine "A" setup when it occurs at the
edge of an already-mature range -- the same sequence occurring without
a real prior range is closer to a generic local reversal than an
institutional trap.

This module is deliberately built directly against this codebase's
real, verified structure -- taking a plain DataFrame (open/high/low/
close/volume) and an already-computed ATR series (reusing
WeisVerdictEngine._compute_atr_series(), not a duplicate calculation)
-- rather than assuming a schema (weis_wave_id, zigzag_trend, a
pre-existing 'atr' column) that does not actually exist anywhere in
this codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class RangeMaturity:
    is_mature: bool
    support: Optional[float]
    resistance: Optional[float]
    support_touches: int
    resistance_touches: int


class WyckoffRangeValidator:
    """
    Sequential, state-persisted range-maturity tracker. Processes a
    full OHLC DataFrame bar by bar, tracking a support/resistance
    level in memory that survives indefinitely (not a fixed rolling
    window), so a genuinely multi-month range is still recognized
    correctly.

    Touch and breakout tolerances are scaled by each bar's own real
    ATR (not a fixed percentage), matching the same per-symbol
    volatility-scaling principle already empirically validated for
    Weis wave detection in this same codebase.
    """

    # FIX (2026-08-09): the original 0.15x touch tolerance was
    # adopted directly from an externally-sourced proposal without
    # independent validation -- unlike the Weis wave threshold,
    # which was empirically tested against real, labeled reference
    # data before shipping. Confirmed the bug directly: tested
    # across 100 realistic synthetic symbols, 0.15x produced a
    # mature range for exactly 0 of them (touch tolerance worked
    # out to ~15% of a typical day's own trading range -- far too
    # tight for ordinary daily noise to ever register as "the same
    # level" twice). This made Grade A structurally impossible,
    # since it requires a mature range.
    #
    # Unlike the wave threshold, there's no equivalent ground-truth
    # label available for "is this a genuinely mature range" (the
    # real reference CSV's Swing/SumVol columns gave a direct,
    # objective answer for wave transitions; nothing comparable
    # exists for range maturity), so this couldn't be empirically
    # tuned the same rigorous way. Swept the touch multiplier from
    # 0.15 to 3.0 across 100 realistic synthetic symbols instead:
    # 0.15x -> 0/100 mature (confirmed broken), 3.0x -> 94/100
    # mature (too loose -- defeats the purpose of a selective
    # filter, since even pure random noise would mostly "qualify").
    # Chose 1.0x as a reasoned, defensible middle value: the touch
    # tolerance roughly equals one typical day's own trading range,
    # a meaningful, intuitive standard ("within about a day's worth
    # of normal noise counts as the same level") that sits clearly
    # away from both extremes.
    def __init__(
        self,
        atr_multiplier_touch: float = 1.0,
        atr_multiplier_break: float = 1.5,
        separation_bars: int = 5,
        min_touches: int = 2,
    ):
        self.atr_mult_touch = atr_multiplier_touch
        self.atr_mult_break = atr_multiplier_break
        self.separation = separation_bars
        self.min_touches = min_touches

    def evaluate(self, df: pd.DataFrame, atr_series: pd.Series) -> RangeMaturity:
        """
        Runs the full sequential pass over df and returns the range
        maturity state as of the final (most recent) bar -- this is
        the only state callers need, since it already reflects the
        full history processed up to that point.
        """
        n = len(df)
        if n == 0:
            return RangeMaturity(False, None, None, 0, 0)

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        atr_values = atr_series.values

        macro_support: Optional[float] = None
        macro_resistance: Optional[float] = None
        support_touch_count = 0
        resistance_touch_count = 0
        last_support_touch_bar = -999
        last_resistance_touch_bar = -999

        for i in range(n):
            high, low, close = float(highs[i]), float(lows[i]), float(closes[i])
            atr = float(atr_values[i]) if pd.notna(atr_values[i]) else None

            # Without a real ATR yet (early bars, before the rolling
            # window fills), fall back to a small fraction of price so
            # early bars don't get an artificially huge tolerance.
            touch_buffer = (atr * self.atr_mult_touch) if atr else close * 0.002
            breakout_buffer = (atr * self.atr_mult_break) if atr else close * 0.02

            if macro_support is None:
                macro_support = low
                support_touch_count = 1
                last_support_touch_bar = i
            if macro_resistance is None:
                macro_resistance = high
                resistance_touch_count = 1
                last_resistance_touch_bar = i

            # True breakout: a real close beyond the ATR-scaled
            # breakout buffer wipes the old range and starts fresh --
            # this is what lets the tracker distinguish a genuine
            # trend expansion from ordinary noise within the range.
            if close < (macro_support - breakout_buffer):
                macro_support = low
                support_touch_count = 1
                last_support_touch_bar = i
            if close > (macro_resistance + breakout_buffer):
                macro_resistance = high
                resistance_touch_count = 1
                last_resistance_touch_bar = i

            # Support: creep vs. genuine touch.
            if low < macro_support:
                creep_distance = macro_support - low
                if creep_distance > touch_buffer:
                    # The line has drifted too far to still count as
                    # the same horizontal level -- prior touches were
                    # against a level that no longer applies, so the
                    # count resets rather than silently carrying over.
                    support_touch_count = 1
                macro_support = low
                last_support_touch_bar = i
            elif low <= (macro_support + touch_buffer):
                if (i - last_support_touch_bar) >= self.separation:
                    support_touch_count += 1
                    last_support_touch_bar = i

            # Resistance: creep vs. genuine touch (mirrored).
            if high > macro_resistance:
                creep_distance = high - macro_resistance
                if creep_distance > touch_buffer:
                    resistance_touch_count = 1
                macro_resistance = high
                last_resistance_touch_bar = i
            elif high >= (macro_resistance - touch_buffer):
                if (i - last_resistance_touch_bar) >= self.separation:
                    resistance_touch_count += 1
                    last_resistance_touch_bar = i

        is_mature = (
            support_touch_count >= self.min_touches
            and resistance_touch_count >= self.min_touches
        )

        return RangeMaturity(
            is_mature=is_mature,
            support=macro_support,
            resistance=macro_resistance,
            support_touches=support_touch_count,
            resistance_touches=resistance_touch_count,
        )
