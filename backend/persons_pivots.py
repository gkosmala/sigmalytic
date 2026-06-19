# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Person's Pivots Engine
================================================================================
File    : persons_pivots.py
Version : 1.0.0
Date    : 2026-05-27

PURPOSE
-------
Calculates John Person's Pivot Points — a conditional pivot system that
plots exactly ONE support and ONE resistance level based on a 3-day
momentum filter. Used in confluence scoring and chart display.

MATH
----
P  = (H + L + C) / 3          — Base pivot
R1 = (P * 2) - L              — Resistance 1
S1 = (P * 2) - H              — Support 1
R2 = P + (H - L)              — Resistance 2
S2 = P - (H - L)              — Support 2

3-day SMA of P = P_avg3

Condition:
  P > P_avg3  → Bullish  → Show R2 + S1
  P < P_avg3  → Bearish  → Show R1 + S2
  P ≈ P_avg3  → Neutral  → Show R1 + S1

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List

NEUTRAL_THRESHOLD_PCT = 0.10   # within 0.10% = neutral


@dataclass
class PersonsPivotResult:
    pivot        : float
    resistance   : float
    support      : float
    condition    : str          # "Bullish" | "Bearish" | "Neutral"
    r1           : float
    r2           : float
    s1           : float
    s2           : float
    p_avg3       : float
    score        : float        # confluence score contribution (0-15)


def calculate_persons_pivots(
    weekly_high : float,
    weekly_low  : float,
    weekly_close: float,
    prior_pivots: Optional[List[float]] = None,
) -> Optional[PersonsPivotResult]:
    """
    Calculate Person's Pivots from the prior week's H/L/C.

    Args:
        weekly_high : Prior week high
        weekly_low  : Prior week low
        weekly_close: Prior week close
        prior_pivots: List of last 2 prior pivot P values for 3-day SMA
                      If None or insufficient, defaults to Neutral condition.

    Returns:
        PersonsPivotResult or None if invalid inputs
    """
    if weekly_high <= 0 or weekly_low <= 0 or weekly_close <= 0:
        return None
    if weekly_high < weekly_low:
        return None

    # Core calculations
    p  = (weekly_high + weekly_low + weekly_close) / 3
    r1 = (p * 2) - weekly_low
    s1 = (p * 2) - weekly_high
    r2 = p + (weekly_high - weekly_low)
    s2 = p - (weekly_high - weekly_low)

    # 3-day SMA of pivot
    if prior_pivots and len(prior_pivots) >= 2:
        p_avg3 = (p + prior_pivots[-1] + prior_pivots[-2]) / 3
    else:
        p_avg3 = p  # fallback — neutral condition

    # Condition filter
    pct_diff = abs(p - p_avg3) / p_avg3 * 100 if p_avg3 > 0 else 0

    if pct_diff <= NEUTRAL_THRESHOLD_PCT:
        condition  = "Neutral"
        resistance = r1
        support    = s1
    elif p > p_avg3:
        condition  = "Bullish"
        resistance = r2
        support    = s1
    else:
        condition  = "Bearish"
        resistance = r1
        support    = s2

    # Confluence score — how close is current pivot to 3-day average?
    # Tight alignment = stronger signal
    score = max(0, 15 - (pct_diff * 10))

    return PersonsPivotResult(
        pivot      = round(p, 2),
        resistance = round(resistance, 2),
        support    = round(support, 2),
        condition  = condition,
        r1         = round(r1, 2),
        r2         = round(r2, 2),
        s1         = round(s1, 2),
        s2         = round(s2, 2),
        p_avg3     = round(p_avg3, 2),
        score      = round(score, 2),
    )


def calculate_from_bars(daily_bars: list) -> Optional[PersonsPivotResult]:
    """
    Calculate Person's Pivots from a list of daily bar dicts.
    Uses the most recent completed week's H/L/C.

    Args:
        daily_bars: List of dicts with keys 'h', 'l', 'c', 't'
                    Sorted oldest to newest.

    Returns:
        PersonsPivotResult or None
    """
    if not daily_bars or len(daily_bars) < 5:
        return None

    # Group into weeks — use last 3 completed weeks
    import pandas as pd
    from datetime import datetime, timezone

    try:
        df = pd.DataFrame(daily_bars)
        df['t'] = pd.to_datetime(df['t'], utc=True, errors='coerce')
        df = df.dropna(subset=['t']).sort_values('t')
        df['week'] = df['t'].dt.tz_localize(None).dt.to_period('W')

        weekly = df.groupby('week').agg(
            high =('h', 'max'),
            low  =('l', 'min'),
            close=('c', 'last'),
        ).reset_index()

        if len(weekly) < 2:
            return None

        # Prior week (most recent completed)
        prior = weekly.iloc[-2]
        wh = float(prior['high'])
        wl = float(prior['low'])
        wc = float(prior['close'])

        # Prior 2 weeks for 3-day SMA approximation
        prior_ps = []
        for i in range(max(0, len(weekly)-4), len(weekly)-2):
            row = weekly.iloc[i]
            pp = (float(row['high']) + float(row['low']) + float(row['close'])) / 3
            prior_ps.append(pp)

        return calculate_persons_pivots(wh, wl, wc, prior_ps)

    except Exception as e:
        return None


def get_pivot_levels_for_chart(result: PersonsPivotResult) -> dict:
    """
    Returns the two levels to display on the chart.
    Matches the Person's system — only ONE support and ONE resistance.
    """
    return {
        "persons_pivot"     : result.pivot,
        "persons_resistance": result.resistance,
        "persons_support"   : result.support,
        "persons_condition" : result.condition,
        "persons_r1"        : result.r1,
        "persons_r2"        : result.r2,
        "persons_s1"        : result.s1,
        "persons_s2"        : result.s2,
        "persons_score"     : result.score,
    }

