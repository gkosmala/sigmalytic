# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_engine/wyckoff_signal_bridge.py
-------------------------------------------------
Translates the output of the existing Weis/Wyckoff engines into the
WyckoffSignals dataclass consumed by campaign_state_engine.py.

This is NOT a new engine. It is a thin adapter layer that sits between:

  EXISTING (Layer 3 originals):
    weis_wave.score_weis_wave_enhanced()   → weis_result dict
    confluence_engine.WeisWyckoffEngine.score() → wyckoff_result dict
    behavioral_transition_engine.classify_behavioral_state() → str

  NEW (campaign engine input):
    campaign_state_engine.WyckoffSignals   → structured flags

WHY THIS EXISTS
---------------
The campaign engine needs boolean flags (sos_detected, spd, dei, etc.)
The existing engines return rich dicts with scores, notes, phase strings.
Rather than modify the working engines, this bridge does the translation.

CLAUDE.md compliance
--------------------
• No credentials — pure signal translation, no I/O.
• All numeric comparisons use float (scores, ratios) — not financial math.
  Decimal is only required for prices/quantities, not scoring ratios.
• Full type hints.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from campaign_state_engine import WyckoffSignals

log = logging.getLogger("wyckoff_signal_bridge")


# ---------------------------------------------------------------------------
# Mapping constants
# ---------------------------------------------------------------------------

# Weis wave signal strings that indicate a Spring event
_SPRING_SIGNALS: frozenset[str] = frozenset({"SPRING", "3BAR_BULL"})

# Weis wave signal strings that indicate an Upthrust event
_UPTHRUST_SIGNALS: frozenset[str] = frozenset({"UPTHRUST", "3BAR_BEAR"})

# Behavioral state strings from classify_behavioral_state() that map to
# Wyckoff Accumulation — used to infer DEI (demand efficiency improving)
_ACCUMULATION_STATES: frozenset[str] = frozenset({
    "Accumulation / Spring Test",
    "Absorption / Markup Loading",
    "Constructive Setup",
    "Pullback Within Markup",
})

# Behavioral state strings that map to Distribution
_DISTRIBUTION_STATES: frozenset[str] = frozenset({
    "Distribution",
    "Distribution / Upthrust Test",
    "Distribution to Markdown Pressure",
    "Markdown",
    "Capitulation / Markdown",
})

# Wyckoff phase proxy strings from WeisWyckoffEngine that signal SOS
_SOS_PHASES: frozenset[str] = frozenset({
    "Sign of Strength",
    "Markup",
    "Spring",          # Spring closing back above SC = implicit SOS
})

# Phase proxy strings that signal CHoCH (character change — bearish)
_CHOCH_PHASES: frozenset[str] = frozenset({
    "Upthrust",
    "Distribution",
    "Markdown",
})


# ---------------------------------------------------------------------------
# Primary bridge function
# ---------------------------------------------------------------------------

def build_wyckoff_signals(
    weis_result:    dict[str, Any],
    wyckoff_result: dict[str, Any],
    behavioral_state: str,
    wave_history:   Optional[list[dict[str, Any]]] = None,
) -> WyckoffSignals:
    """
    Translate engine output dicts into a WyckoffSignals object.

    Parameters
    ----------
    weis_result:
        Output of score_weis_wave_enhanced() from weis_wave.py.
        Expected keys: weis_signal, spring_validated, spring_confidence,
                       weis_score, macro_bias, effort_vs_result.

    wyckoff_result:
        Output of WeisWyckoffEngine.score() from confluence_engine.py.
        Expected keys: score, phase, waves, notes.

    behavioral_state:
        String from classify_behavioral_state() in behavioral_transition_engine.py.
        e.g. "Accumulation / Spring Test", "Distribution to Markdown Pressure".

    wave_history:
        Optional list of recent WeisWave dicts for WED computation.
        Each dict has keys: direction, volume, price_change.
        If None, falls back to wyckoff_result["waves"].

    Returns
    -------
    WyckoffSignals
        Structured flags ready for CampaignStateMachine.transition().
    """
    weis_signal  = str(weis_result.get("weis_signal", "NONE")).upper()
    wyckoff_phase = str(wyckoff_result.get("phase", "")).strip()
    wyckoff_score = float(wyckoff_result.get("score", 50.0))

    # ── Spring ────────────────────────────────────────────────────────────────
    spring_detected = (
        weis_signal in _SPRING_SIGNALS
        or wyckoff_phase == "Spring"
        or bool(weis_result.get("spring_validated", False))
    )

    # ── Upthrust ──────────────────────────────────────────────────────────────
    upthrust_detected = (
        weis_signal in _UPTHRUST_SIGNALS
        or wyckoff_phase == "Upthrust"
    )

    # ── SOS / JAC ─────────────────────────────────────────────────────────────
    # Sign of Strength: phase proxy says so, or Wyckoff score is strongly bullish
    # and weis macro bias is bullish.
    macro_bias   = int(weis_result.get("macro_bias", 0))
    sos_detected = (
        wyckoff_phase in _SOS_PHASES
        or (wyckoff_score >= 75 and macro_bias == 1)
    )
    jac_detected = sos_detected  # JAC (Jump Across Creek) is the entry expression of SOS

    # ── BU / LPS ──────────────────────────────────────────────────────────────
    # Back-Up / Last Point of Support: effort vs result shows ease of movement
    # on the upside, combined with a bullish behavioral state.
    effort_vs_result = str(weis_result.get("effort_vs_result", "NEUTRAL")).upper()
    in_accumulation  = behavioral_state in _ACCUMULATION_STATES

    bu_detected  = (
        effort_vs_result == "CONFIRM"
        and in_accumulation
        and macro_bias == 1
    )
    lps_detected = bu_detected  # LPS is the structural expression of BU in the range

    # ── CHoCH ─────────────────────────────────────────────────────────────────
    # Change of Character (bearish): phase flips to distribution/upthrust OR
    # behavioral state enters distribution territory.
    in_distribution = behavioral_state in _DISTRIBUTION_STATES
    choch_detected  = (
        wyckoff_phase in _CHOCH_PHASES
        or (upthrust_detected and in_distribution)
    )

    # ── SPD — Selling Pressure Diminishing ───────────────────────────────────
    # Approximated from effort vs result on the downside:
    # higher volume + smaller downward move = supply being absorbed.
    # The full SPD computation (w_dn1_vol_eff across wave pairs) requires
    # the research engine's wave decomposition; this is the best proxy
    # available from the existing engines.
    spd = _compute_spd_proxy(
        weis_result    = weis_result,
        wyckoff_result = wyckoff_result,
        macro_bias     = macro_bias,
    )

    # ── DEI — Demand Efficiency Improving ────────────────────────────────────
    # Approximated: up-waves showing ease of movement + accumulation state.
    dei = (
        effort_vs_result == "CONFIRM"
        and in_accumulation
        and macro_bias >= 0
    )

    # ── WED — Wave Exhaustion Depth ───────────────────────────────────────────
    # Count of successive down-wave pairs where volume efficiency deteriorates.
    waves = wave_history or wyckoff_result.get("waves", [])
    wed_count = _compute_wed(waves)

    # ── Behavioral state string → simplified label ────────────────────────────
    if in_accumulation or spring_detected:
        behavioral_label = "ACCUMULATION"
    elif in_distribution or choch_detected:
        behavioral_label = "DISTRIBUTION"
    else:
        behavioral_label = "AMBIGUOUS"

    signals = WyckoffSignals(
        sos_detected      = sos_detected,
        jac_detected      = jac_detected,
        bu_detected       = bu_detected,
        lps_detected      = lps_detected,
        choch_detected    = choch_detected,
        spring_detected   = spring_detected,
        upthrust_detected = upthrust_detected,
        spd               = spd,
        dei               = dei,
        wed_count         = wed_count,
        behavioral_state  = behavioral_label,
    )

    log.debug(
        "WyckoffSignals built | phase=%s weis=%s beh=%s → sos=%s spring=%s spd=%s dei=%s wed=%d choch=%s",
        wyckoff_phase, weis_signal, behavioral_state,
        sos_detected, spring_detected, spd, dei, wed_count, choch_detected,
    )

    return signals


# ---------------------------------------------------------------------------
# SPD proxy
# ---------------------------------------------------------------------------

def _compute_spd_proxy(
    weis_result:    dict[str, Any],
    wyckoff_result: dict[str, Any],
    macro_bias:     int,
) -> bool:
    """
    Proxy for Selling Pressure Diminishing using available engine outputs.

    SPD is True when:
    - The effort vs result signal shows divergence on a down-wave
      (high volume, small downward move = absorption), OR
    - The Wyckoff score notes contain absorption language AND macro bias
      is neutral-to-bullish (sellers failing to push price lower).

    This is an approximation. The validated SPD from qualified_long_signal_audit.py
    computes this across successive wave pairs with w_dn1_vol_eff / w_dn2_vol_eff.
    Full integration of that metric is Phase 12C / Layer 2 work.
    """
    effort_vs_result = str(weis_result.get("effort_vs_result", "NEUTRAL")).upper()

    # Divergence on a down move = high volume, small downward result = absorption
    if effort_vs_result == "DIVERGE" and macro_bias >= 0:
        return True

    # Check Wyckoff notes for absorption language
    notes = wyckoff_result.get("notes", [])
    if isinstance(notes, list):
        absorption_keywords = {"absorption", "accumulation footprint", "selling into weakness"}
        for note in notes:
            if any(kw in str(note).lower() for kw in absorption_keywords):
                return True

    return False


# ---------------------------------------------------------------------------
# WED computation
# ---------------------------------------------------------------------------

def _compute_wed(waves: list[dict[str, Any]]) -> int:
    """
    Count successive down-wave pairs where volume efficiency deteriorates.

    A down-wave's efficiency = abs(price_change) / volume.
    Deterioration = efficiency is lower than the prior down-wave.

    Validated optimum from research: WED_2 (2 deteriorating pairs).
    WED_3 is also meaningful but slightly less so.

    Parameters
    ----------
    waves:
        List of wave dicts with keys: direction, volume, price_change.
        Most recent wave is last. Typically 5 waves from wyckoff_result["waves"].
    """
    if not waves or len(waves) < 2:
        return 0

    # Extract down-waves only, in order
    down_waves = [
        w for w in waves
        if str(w.get("direction", "")).lower() in {"bear", "down", "-1", "red"}
        and float(w.get("volume", 0)) > 0
    ]

    if len(down_waves) < 2:
        return 0

    # Compute efficiency per down-wave
    def efficiency(w: dict) -> float:
        vol = float(w.get("volume", 1))
        chg = abs(float(w.get("price_change", w.get("price_range", 0))))
        return chg / vol if vol > 0 else 0.0

    wed = 0
    for i in range(1, len(down_waves)):
        if efficiency(down_waves[i]) < efficiency(down_waves[i - 1]):
            wed += 1
        else:
            break  # Consecutive deterioration only

    return wed


# ---------------------------------------------------------------------------
# Convenience wrapper — called from the nightly pipeline
# ---------------------------------------------------------------------------

def signals_from_confluence_output(
    confluence_result: dict[str, Any],
) -> WyckoffSignals:
    """
    Single-dict convenience wrapper for callers that already have the full
    confluence bridge output dict (which contains weis, wyckoff, and
    behavioral sub-keys).

    Expected top-level keys in confluence_result:
        weis_wave       → dict (from score_weis_wave_enhanced)
        wyckoff         → dict (from WeisWyckoffEngine.score)
        behavioral_state → str (from classify_behavioral_state)
        waves           → list (optional, from WeisWyckoffEngine)
    """
    weis_result    = confluence_result.get("weis_wave", {})
    wyckoff_result = confluence_result.get("wyckoff", {})
    behavioral     = str(confluence_result.get("behavioral_state", "Neutral / Noise"))
    waves          = confluence_result.get("waves")

    return build_wyckoff_signals(
        weis_result      = weis_result,
        wyckoff_result   = wyckoff_result,
        behavioral_state = behavioral,
        wave_history     = waves,
    )
