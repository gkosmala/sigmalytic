# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_intelligence.py
------------------------------
Broker Behavioural Intelligence: grades a broker/adviser from the statements
in one account vault.

The broker is graded by the SAME engine Import History uses for a subscriber
(`import_history_restore_api._analyze_trades`: execution -> round trips ->
win/loss, streak, re-entry, sizing and time-of-day behaviour). This module
adds the one thing that engine does not produce: a plain A-F grade for the
whole profile and for its four components (Execution, Discipline, Timing,
Risk Management). The scale lives in one place (`letter_from_score`) so the
subscriber profile can use it too.

Pure functions only. No network, no database. Storage lives in
broker_vault_store.py and the HTTP layer in broker_intelligence_api.py.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

MIN_ROUND_TRIPS_FOR_GRADE = 5

GRADE_BANDS = ((90.0, "A"), (80.0, "B"), (70.0, "C"), (60.0, "D"))

COMPONENT_WEIGHTS = {
    "execution": 0.35,
    "discipline": 0.25,
    "timing": 0.20,
    "risk_management": 0.20,
}


def letter_from_score(score: Optional[float]) -> str:
    """A-F for a 0-100 score. None -> 'N/A'."""
    if score is None:
        return "N/A"
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _component(score: float, basis: List[str]) -> Dict[str, Any]:
    score = round(_clamp(score), 1)
    return {"score": score, "grade": letter_from_score(score), "basis": basis}


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def _execution(a: Dict[str, Any]) -> Dict[str, Any]:
    """Did the trades make money? Profit factor, win rate, expectancy."""
    pf = min(_f(a.get("profit_factor")), 3.0)
    win_rate = _f(a.get("win_rate"))
    expectancy = _f(a.get("expectancy_per_trade"))

    pf_c = _clamp(pf / 1.5 * 100.0)
    win_c = _clamp(win_rate / 0.55 * 100.0)
    exp_c = 100.0 if expectancy > 0 else (40.0 if expectancy == 0 else 20.0)
    score = 0.5 * pf_c + 0.3 * win_c + 0.2 * exp_c

    basis = [
        f"Profit factor {_f(a.get('profit_factor')):.2f} (1.50 or better scores full marks)",
        f"Win rate {win_rate * 100:.0f}% (55% or better scores full marks)",
        f"Expectancy ${expectancy:,.2f} per trade",
    ]
    return _component(score, basis)


def _discipline(a: Dict[str, Any]) -> Dict[str, Any]:
    """Behaviour after losses: quick re-entry, bigger size, losing days, streaks."""
    losers = max(1, int(_f(a.get("losing_trades"))))
    quick = int(_f(a.get("quick_reentry_after_loss_count")))
    size_up = int(_f(a.get("size_after_loss_count")))
    losing_day_rate = _f(a.get("losing_day_rate"))
    streak = int(_f(a.get("max_losing_streak")))

    score = 100.0
    basis: List[str] = []

    quick_rate = quick / losers
    score -= 40.0 * quick_rate
    basis.append(f"{quick} quick re-entries within 60 minutes of a loss")

    size_rate = size_up / losers
    score -= 30.0 * size_rate
    basis.append(f"{size_up} trades sized up more than 25% right after a loss")

    if losing_day_rate > 0.5:
        score -= (losing_day_rate - 0.5) * 60.0
    basis.append(f"{losing_day_rate * 100:.0f}% of trading days lost money")

    if streak >= 8:
        score -= 25.0
    elif streak >= 5:
        score -= 15.0
    basis.append(f"Longest losing streak: {streak}")

    return _component(score, basis)


def _timing(a: Dict[str, Any]) -> Dict[str, Any]:
    """Is damage concentrated in particular hours; very short holds that lose."""
    score = 85.0
    basis: List[str] = []

    gross_loss = _f(a.get("gross_loss"))
    worst_hours = a.get("worst_hours") or []
    if worst_hours and gross_loss < 0:
        worst = _f(worst_hours[0].get("pnl"))
        share = worst / gross_loss if worst < 0 else 0.0
        if share > 0.35:
            score -= (share - 0.35) * 80.0
        basis.append(
            f"Worst hour ({worst_hours[0].get('hour')}) holds {share * 100:.0f}% of all losses"
        )
    else:
        basis.append("No hour-of-day data in these statements")

    flags = a.get("behavioral_flags") or []
    if "SHORT_HOLD_NEGATIVE_EXPECTANCY_PATTERN" in flags:
        score -= 20.0
        basis.append("Very short holds are losing money")

    win_rate = _f(a.get("win_rate"))
    score += max(-15.0, min(15.0, (win_rate - 0.45) * 50.0))
    basis.append(f"Win rate {win_rate * 100:.0f}% versus a 45% baseline")

    return _component(score, basis)


def _risk_management(a: Dict[str, Any]) -> Dict[str, Any]:
    """Size of losses versus wins and how concentrated the damage is."""
    avg_win = _f(a.get("average_win"))
    avg_loss = abs(_f(a.get("average_loss")))
    payoff = (avg_win / avg_loss) if avg_loss > 0 else None

    payoff_c = 100.0 if payoff is None else _clamp(payoff / 1.5 * 100.0)
    penalties = 0.0
    basis: List[str] = []

    if payoff is None:
        basis.append("No losing trades to measure payoff against")
    else:
        basis.append(f"Average win is {payoff:.2f}x the average loss (1.50x scores full marks)")

    gross_loss = _f(a.get("gross_loss"))
    worst_symbols = a.get("worst_symbols") or []
    if worst_symbols and gross_loss < 0:
        worst = _f(worst_symbols[0].get("pnl"))
        share = worst / gross_loss if worst < 0 else 0.0
        if share > 0.4:
            penalties += 15.0
        basis.append(
            f"Worst symbol ({worst_symbols[0].get('symbol')}) holds {share * 100:.0f}% of all losses"
        )

    flags = a.get("behavioral_flags") or []
    if "SYMBOL_SPECIFIC_DAMAGE_CONCENTRATION" in flags:
        penalties += 10.0
    if int(_f(a.get("max_losing_streak"))) >= 5:
        penalties += 10.0

    score = 0.6 * payoff_c + 40.0 - penalties
    return _component(score, basis)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def grade_behavior(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn an `_analyze_trades` result into the broker's A-F behavioural grade.

    Returns {"graded": False, "reason": ...} when there are too few round
    trips to say anything fair.
    """
    trips = int(_f(analysis.get("round_trip_trades")))
    if trips < MIN_ROUND_TRIPS_FOR_GRADE:
        return {
            "graded": False,
            "overall_grade": "N/A",
            "round_trips": trips,
            "reason": (
                f"{trips} completed trades found; at least {MIN_ROUND_TRIPS_FOR_GRADE} "
                "are needed for a fair grade. Add more statements."
            ),
        }

    components = {
        "execution": _execution(analysis),
        "discipline": _discipline(analysis),
        "timing": _timing(analysis),
        "risk_management": _risk_management(analysis),
    }
    overall = sum(components[k]["score"] * w for k, w in COMPONENT_WEIGHTS.items())
    overall = round(_clamp(overall), 1)

    return {
        "graded": True,
        "round_trips": trips,
        "overall_score": overall,
        "overall_grade": letter_from_score(overall),
        "components": components,
        "flags": list(analysis.get("behavioral_flags") or []),
        "profile": analysis.get("behavioral_profile"),
        "weights": dict(COMPONENT_WEIGHTS),
    }


def merge_executions(batches: Iterable[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Combine the executions of several statements for one vault.

    Statements often overlap (a monthly and a year-to-date export), so the
    same fill can appear twice. A fill is a duplicate when date, symbol,
    side, quantity and price all match. Genuine repeated identical fills
    inside ONE statement are kept; only repeats across statements are dropped.
    """
    from collections import Counter

    def key(t: Dict[str, Any]):
        return (
            str(t.get("date")),
            str(t.get("symbol")).upper(),
            str(t.get("side")).upper(),
            round(_f(t.get("quantity")), 6),
            round(_f(t.get("price")), 6),
        )

    seen: Counter = Counter()
    merged: List[Dict[str, Any]] = []
    for batch in batches:
        batch_count: Counter = Counter(key(t) for t in batch)
        for k, n in batch_count.items():
            keep = max(0, n - seen[k])
            seen[k] = max(seen[k], n)
            if keep:
                merged_for_key = [t for t in batch if key(t) == k][:keep]
                merged.extend(merged_for_key)
    return merged
