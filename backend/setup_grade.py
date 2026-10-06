# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/setup_grade.py
----------------------
The per-symbol Setup Grade (A/B/C) built from the Wyckoff and Weis verdicts.

Moved out of radar_service.py unchanged so other features (Broker Behavioural
Intelligence) can use it without importing the whole scanner, which needs the
full production environment to load. radar_service imports it from here under
the original name, so the scanner behaves exactly as before.
"""
from __future__ import annotations


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def compute_setup_grade(wyckoff_verdict: dict, weis_verdict: dict) -> dict:
    """
    Genuine, per-symbol Setup Grade -- replaces the old probability_grade,
    which was pooled across an unrelated, fixed 50-symbol historical
    backtest (confirmed to leave most real symbols "Unrated" and to
    treat unrelated stocks as identical whenever they landed in the
    same coarse bucket).

    Built directly from David Weis's own grading framework (discussed
    and confirmed with the user): a genuine "A" setup requires the full
    sweep -> exhaustion -> reclaim sequence AND a genuinely mature
    prior range (multiple, time-separated touches over weeks) -- the
    same sequence without a mature range is a "B" at best, since
    without real pooled stop-loss liquidity behind the level, the
    sweep doesn't trap anyone and the snap-back lacks the structural
    "Cause" to sustain a real move. No sequence at all is a "C".

    Thresholds: spring_score/upthrust_score >= 65 requires the sweep
    (30) AND reclaim (35) components of that score to both genuinely
    be present (its own confirmed minimum, not an arbitrary round
    number). Weis's exhaustion and reclaim sub-scores are binary (0 or
    100 -- an exact pattern match, not a gradual scale), so >= 100 is
    the only meaningful "confirmed" threshold for those.

    FIX (2026-08-09): extended to evaluate both sides -- long (Spring)
    and short (Upthrust) -- using the newly-built mirror-image Weis
    fields (buying_exhaustion, downwave_confirmation) alongside
    Wyckoff's upthrust_score. A stock can't genuinely sweep both below
    support and above resistance at once, so only one side should
    realistically confirm at a time; whichever side confirms
    determines the grade and reported setup_side.
    """
    spring_score = _f(wyckoff_verdict.get("spring_score")) if wyckoff_verdict else 0
    upthrust_score = _f(wyckoff_verdict.get("upthrust_score")) if wyckoff_verdict else 0
    volume_exhaustion = _f(weis_verdict.get("volume_exhaustion")) if weis_verdict else 0
    upwave_confirmation = _f(weis_verdict.get("upwave_confirmation")) if weis_verdict else 0
    buying_exhaustion = _f(weis_verdict.get("buying_exhaustion")) if weis_verdict else 0
    downwave_confirmation = _f(weis_verdict.get("downwave_confirmation")) if weis_verdict else 0
    range_is_mature = bool(weis_verdict.get("range_is_mature")) if weis_verdict else False

    long_sweep = spring_score >= 65
    long_exhaustion = volume_exhaustion >= 100
    long_reclaim = upwave_confirmation >= 100
    long_confirmed = long_sweep and long_exhaustion and long_reclaim

    short_sweep = upthrust_score >= 65
    short_exhaustion = buying_exhaustion >= 100
    short_reclaim = downwave_confirmation >= 100
    short_confirmed = short_sweep and short_exhaustion and short_reclaim

    if long_confirmed:
        side = "Long"
        sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = long_sweep, long_exhaustion, long_reclaim
    elif short_confirmed:
        side = "Short"
        sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = short_sweep, short_exhaustion, short_reclaim
    else:
        # Neither side confirmed -- report whichever side got closer
        # (more of the three conditions true), defaulting to Long on
        # a tie since it's the more common, primary case.
        long_hits = sum([long_sweep, long_exhaustion, long_reclaim])
        short_hits = sum([short_sweep, short_exhaustion, short_reclaim])
        if short_hits > long_hits:
            side = "Short"
            sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = short_sweep, short_exhaustion, short_reclaim
        else:
            side = "Long"
            sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = long_sweep, long_exhaustion, long_reclaim

    sequence_confirmed = sweep_confirmed and exhaustion_confirmed and reclaim_confirmed

    if sequence_confirmed and range_is_mature:
        grade = "A"
        reason = f"{side} sweep, exhaustion, and reclaim confirmed at a mature range boundary."
    elif sequence_confirmed:
        grade = "B"
        reason = f"{side} sweep, exhaustion, and reclaim confirmed, but the prior range is not yet mature."
    else:
        grade = "C"
        missing = []
        if not sweep_confirmed:
            missing.append("sweep")
        if not exhaustion_confirmed:
            missing.append("exhaustion")
        if not reclaim_confirmed:
            missing.append("reclaim")
        reason = f"{side} sequence not confirmed (missing: {', '.join(missing)})."

    return {
        "setup_grade": grade,
        "setup_grade_reason": reason,
        "setup_side": side,
        "setup_sweep_confirmed": sweep_confirmed,
        "setup_exhaustion_confirmed": exhaustion_confirmed,
        "setup_reclaim_confirmed": reclaim_confirmed,
        "setup_range_mature": range_is_mature,
    }
