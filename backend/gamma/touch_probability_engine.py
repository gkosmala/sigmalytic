# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/gamma/touch_probability_engine.py
----------------------------------------------------
Computes a genuine, market-derived probability that price touches a
given level before a chosen expiration, replacing the Probability
Ladder's prior heuristic (fixed base score + ad-hoc bonuses) with a
real statistical model driven by real, live implied volatility from
the actual options chain (AlpacaOptionChainAdapter).

Uses the standard "one-touch" probability formula for a driftless
lognormal (geometric Brownian motion) price process, via the
reflection principle:

    P(touch) = 2 * N(-|ln(level/spot)| / (sigma * sqrt(T)))

This is the same core lognormal assumption options pricing itself is
built on, and the same method real options platforms use for
"probability of touching" figures -- genuinely real and market-
derived, but still a model of price behavior (constant volatility,
zero drift), not a certainty or a guarantee.

Time horizon: the nearest MONTHLY expiration (the traditional 3rd-
Friday-of-the-month convention), not the nearest expiration overall
or a fixed day count -- deliberately chosen (2026-08-12) as the
standard, most liquid, most reliable-IV middle ground between an
overly short-dated nearest expiration (probabilities compress toward
0%/100% too fast to be useful) and an arbitrary fixed day count.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def _norm_cdf(x: float) -> float:
    """Standard normal CDF, no external dependency needed."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _is_third_friday(d: date) -> bool:
    if d.weekday() != 4:  # Friday
        return False
    return 15 <= d.day <= 21


class TouchProbabilityEngine:

    @classmethod
    def find_nearest_monthly_expiration(cls, options_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Finds the nearest, still-future monthly expiration (3rd Friday
        of its month) present in the real options chain, and returns
        its expiration_date and dte alongside the contracts belonging
        to it.
        """
        by_expiration: Dict[str, List[Dict[str, Any]]] = {}
        for row in options_data:
            exp = row.get("expiration_date")
            if not exp:
                continue
            by_expiration.setdefault(exp, []).append(row)

        monthly_candidates = []
        for exp_str, rows in by_expiration.items():
            try:
                exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            if not _is_third_friday(exp_date):
                continue
            dte = rows[0].get("dte")
            if dte is None or dte <= 0:
                continue
            monthly_candidates.append((dte, exp_str, rows))

        if not monthly_candidates:
            return None

        monthly_candidates.sort(key=lambda t: t[0])
        dte, exp_str, rows = monthly_candidates[0]
        return {"expiration_date": exp_str, "dte": dte, "contracts": rows}

    @classmethod
    def atm_implied_volatility(cls, contracts: List[Dict[str, Any]], spot_price: float) -> Optional[float]:
        """
        The single strike (across both calls and puts) whose own
        strike is closest to spot_price, using that contract's real
        implied_volatility -- the standard "ATM IV" convention.
        """
        candidates = [
            c for c in contracts
            if c.get("implied_volatility") is not None and c.get("implied_volatility") > 0
            and c.get("strike") is not None
        ]
        if not candidates:
            return None
        closest = min(candidates, key=lambda c: abs(c["strike"] - spot_price))
        return float(closest["implied_volatility"])

    @classmethod
    def touch_probability(cls, spot_price: float, level: float, sigma: float, days_to_expiration: float) -> Optional[float]:
        """
        The core formula. Returns None (rather than a fabricated
        number) for any input that would make the model meaningless --
        e.g. zero/negative volatility, zero/negative time, or the
        level being on the wrong side to even ask the question.
        """
        if spot_price <= 0 or level <= 0 or sigma <= 0 or days_to_expiration <= 0:
            return None

        t_years = days_to_expiration / 365.0
        if level == spot_price:
            return 1.0  # already there

        ratio = level / spot_price
        d = abs(math.log(ratio)) / (sigma * math.sqrt(t_years))
        prob = 2.0 * _norm_cdf(-d)
        return max(0.0, min(1.0, prob))

    @classmethod
    def build_ladder_probabilities(cls, options_data: List[Dict[str, Any]], spot_price: float,
                                     levels: Dict[str, float]) -> Dict[str, Any]:
        """
        Top-level entry point: finds the nearest monthly expiration,
        its ATM IV, and computes a real touch probability for each
        named level in `levels` (e.g. {"breakout": 406.19, ...}).
        """
        monthly = cls.find_nearest_monthly_expiration(options_data)
        if not monthly:
            return {"available": False, "reason": "No monthly expiration found in the current options chain."}

        sigma = cls.atm_implied_volatility(monthly["contracts"], spot_price)
        if sigma is None:
            return {"available": False, "reason": "No usable implied volatility in the nearest monthly expiration's chain."}

        probabilities = {}
        for name, level in levels.items():
            p = cls.touch_probability(spot_price, level, sigma, monthly["dte"])
            probabilities[name] = round(p * 100.0, 1) if p is not None else None

        return {
            "available": True,
            "expiration_date": monthly["expiration_date"],
            "days_to_expiration": monthly["dte"],
            "atm_implied_volatility": round(sigma, 4),
            "probabilities": probabilities,
        }
