# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/doctrine_deep_engine.py
--------------------------------
Doctrine-aligned "deep" evaluation engine for the Intelligence Change
Detector (Layer 2 of the two-layer radar architecture documented in
radar_service.py).

WHY THIS EXISTS (2026-07-30): a full read-only audit (confirmed via
direct file/line citations) found that the previous Layer 2 engine
(ConfluenceEngine.evaluate(), confluence_engine.py) computed its "deep
score" from twelve weighted internal families, only two of which
(wyckoff_weis at 10%, vsa at 10%) relate to this product's stated
doctrine -- Wyckoff / Weis / Livermore behavioral campaign intelligence.
The remaining ~65% of the weight came from Gann geometry, time cycles,
astrology, numerology/biblical, Fibonacci, and Elliott waves -- methods
unrelated to the product's core, several with no legitimate predictive
basis. Product decision made explicitly after this audit: Layer 2 must
be rebuilt around the same doctrine as the rest of the product, not
merely reweighted.

This engine's composite score is built entirely from genuine Wyckoff /
Weis / Livermore-aligned evidence, computed directly from real daily
price/volume bars -- no Gann, astrology, numerology, Elliott, or
Fibonacci anywhere in this file.

SEVEN PILLARS (as specified in the product decision):
  1. Wyckoff structure / Weis effort-vs-result
     -> backend.weis_wave.score_weis_wave_radar() -- an existing, real
        Wyckoff/Weis engine already used elsewhere in this codebase
        (Spring/Upthrust/Climax detection via cumulative volume-wave
        comparison, i.e. genuine effort-vs-result analysis), reused
        here rather than reinvented.
  2. Livermore line-of-least-resistance
     -> trend structure (price vs MA20/MA50) + recent performance,
        the classic Livermore "path of least resistance" read.
  3. Campaign survival / failure evidence
     -> how far price has drifted from its recent (20-bar) high without
        a clean reversal -- holding near highs = surviving; a deep,
        un-recovered pullback = failing.
  4. Volume-quality confirmation
     -> ratio of volume on advancing days vs declining days over the
        last 20 bars -- real accumulation shows heavier volume on
        strength, not weakness.
  5. Structural location
     -> where price sits within its 52-week range -- near the top
        (strength/markup context) vs near the bottom (weakness/basing
        or markdown context).
  6. Contrary supply / distribution risk
     -> an explicit penalty when the Weis engine detects a genuine
        Upthrust or Selling Climax (distribution signals), and a bonus
        for Spring/Buying Climax (accumulation signals).
  7. Effort-vs-result itself is pillar 1's numeric weis_score, folded
     directly into the composite rather than treated as a separate line.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def compute_doctrine_deep_score(
    symbol: str,
    bars: List[dict],
    price: float,
) -> Dict[str, Any]:
    """
    Returns a dict shaped compatibly with what run_eod_audit() expects
    from the engine it compares against the radar's composite_score:
      - new_composite_score (the deep score, 0-100)
      - new_status / new_regime (for the Intelligence Change Detector's
        display columns)
      - new_engine_error (None on success, a plain-English reason on
        failure -- this engine fails closed, same posture as before)
    Plus the individual pillar sub-scores, for transparency/audit trail.
    """
    from backend.weis_wave import score_weis_wave_radar

    if not bars or len(bars) < 20 or price <= 0:
        return {
            "new_composite_score": None,
            "new_status": None,
            "new_regime": None,
            "new_engine_error": f"INSUFFICIENT_DATA: bars_len={len(bars) if bars else 0} price={price}",
        }

    closes  = [float(b.get("c", 0)) for b in bars if b.get("c")]
    volumes = [float(b.get("v", 0)) for b in bars if b.get("v")]
    highs   = [float(b.get("h", 0)) for b in bars if b.get("h")]
    lows    = [float(b.get("l", 0)) for b in bars if b.get("l")]

    if len(closes) < 20:
        return {
            "new_composite_score": None,
            "new_status": None,
            "new_regime": None,
            "new_engine_error": f"INSUFFICIENT_CLOSES: closes_len={len(closes)}",
        }

    # ── Pillar 1: Wyckoff structure / Weis effort-vs-result ──────────────────
    weis = score_weis_wave_radar(symbol, bars, price)
    weis_score  = float(weis.get("weis_score") or 0)
    weis_signal = weis.get("weis_signal") or "NONE"
    macro_bias  = weis.get("weis_macro_bias") or 0
    weis_component = _clamp(50.0 + weis_score)

    # ── Pillar 2: Livermore line-of-least-resistance ─────────────────────────
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else ma20
    lor_score = 50.0
    if price > ma20 > ma50:
        lor_score += 20.0
    elif price < ma20 < ma50:
        lor_score -= 20.0
    perf_20 = ((price - closes[-20]) / closes[-20] * 100) if closes[-20] > 0 else 0.0
    if perf_20 > 5:
        lor_score += 15.0
    elif perf_20 < -5:
        lor_score -= 15.0
    lor_score = _clamp(lor_score)

    # ── Pillar 3: campaign survival / failure evidence ───────────────────────
    high_20 = max(highs[-20:]) if len(highs) >= 20 else price
    drawdown_from_high = ((high_20 - price) / high_20 * 100) if high_20 > 0 else 0.0
    survival_score = 50.0
    if drawdown_from_high < 3:
        survival_score += 15.0
    elif drawdown_from_high > 15:
        survival_score -= 20.0
    elif drawdown_from_high > 8:
        survival_score -= 8.0
    survival_score = _clamp(survival_score)

    # ── Pillar 4: volume-quality confirmation ────────────────────────────────
    up_vol, down_vol = 0.0, 0.0
    window = min(20, len(closes) - 1)
    for i in range(1, window + 1):
        if len(volumes) < i + 1:
            break
        if closes[-i] > closes[-i - 1]:
            up_vol += volumes[-i]
        else:
            down_vol += volumes[-i]
    vol_quality = 50.0
    if up_vol > down_vol * 1.3:
        vol_quality += 20.0
    elif down_vol > up_vol * 1.3:
        vol_quality -= 20.0
    vol_quality = _clamp(vol_quality)

    # ── Pillar 5: structural location (52-week range position) ──────────────
    high_52w = max(highs[-252:]) if len(highs) >= 52 else (max(highs) if highs else price)
    low_52w  = min(lows[-252:])  if len(lows)  >= 52 else (min(lows)  if lows  else price)
    struct_score = 50.0
    range_52w = high_52w - low_52w
    if range_52w > 0:
        position_in_range = (price - low_52w) / range_52w
        if position_in_range > 0.8:
            struct_score += 10.0
        elif position_in_range < 0.2:
            struct_score -= 10.0
    struct_score = _clamp(struct_score)

    # ── Pillar 6: contrary supply / distribution risk ────────────────────────
    distribution_component = 50.0
    if weis_signal in ("UPTHRUST", "CLIMAX_SELL"):
        distribution_component = 35.0
    elif weis_signal in ("SPRING", "CLIMAX_BUY"):
        distribution_component = 62.0

    composite = _clamp(round(
        weis_component          * 0.30 +
        lor_score               * 0.20 +
        survival_score          * 0.15 +
        vol_quality             * 0.15 +
        struct_score            * 0.10 +
        distribution_component  * 0.10,
        2,
    ))

    if weis_signal in ("SPRING", "CLIMAX_BUY"):
        regime = "ACCUMULATION"
    elif weis_signal in ("UPTHRUST", "CLIMAX_SELL"):
        regime = "DISTRIBUTION"
    elif macro_bias > 0:
        regime = "MARKUP"
    elif macro_bias < 0:
        regime = "MARKDOWN"
    else:
        regime = "NEUTRAL"

    status = "Watching"
    if regime == "ACCUMULATION":
        status = "Building"
    elif regime == "DISTRIBUTION":
        status = "Avoid"

    return {
        "new_composite_score": composite,
        "new_status": status,
        "new_regime": regime,
        "new_engine_error": None,
        # Individual pillars, kept for transparency / audit trail --
        # not required by the caller, but useful for verifying this
        # engine's behavior against real data going forward.
        "pillar_wyckoff_weis":     round(weis_component, 1),
        "pillar_line_of_least_resistance": round(lor_score, 1),
        "pillar_survival":         round(survival_score, 1),
        "pillar_volume_quality":   round(vol_quality, 1),
        "pillar_structural_location": round(struct_score, 1),
        "pillar_distribution_risk": round(distribution_component, 1),
        "weis_signal": weis_signal,
        "weis_macro_bias": macro_bias,
    }
