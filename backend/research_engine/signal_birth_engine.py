# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/signal_birth_engine.py
-----------------------------------------------
Nightly signal birth engine — the live implementation of Phase 12B scoring.

Runs at 20:30 UTC nightly (after geometry at 20:00, before campaign
pipeline at 21:00). Evaluates every symbol in the radar bar cache,
computes TIER classifications using the validated research metrics,
and calls CampaignEngine.birth_campaign() for new TIER_1 / TIER_2 signals.

WHAT IT COMPUTES
----------------
For each symbol with sufficient bar history:

1. Obstacle Score
   = abs(distance from 252-day high) + (days since 252-day high / 5) + range_width
   Measures structural resistance the stock must overcome.

2. Behavioral State (SPD / DEI / WED)
   Derived from swing-wave analysis — the exact logic from
   qualified_long_signal_audit.py._compute_wave_variables():
     SPD = selling pressure diminishing (dn-wave volume dropping, price drop shrinking)
     DEI = demand efficiency improving (up-wave price efficiency rising)
     State 1 (SPD=Y, DEI=N) = optimal entry window — 59%+ mfe90 validated

3. Duration Bucket
   Days below 252-day high:
     DUR_UNDER_20   < 20 days  (suppress)
     DUR_20_60      20-60 days
     DUR_60_120     60-120 days (strongest — 78.85% mfe90)
     DUR_120_180    120-180 days
     DUR_180_PLUS   180+ days

4. Grade (RS-based qualification)
   Mirrors grade_from_signal() from the audit script.
   Minimum grade C required for any TIER assignment.

5. TIER Assignment
   TIER_1: State 1 + OBS_Q3/Q4 + DUR_60_120 + Grade B+
   TIER_2: State 1 + OBS_Q2/Q3 + DUR_60_180 + Grade B
   TIER_3: State 2 + any OBS + Grade C+
   TIER_4: Qualified long, grade C, no strong behavioral signal

CLAUDE.md compliance
--------------------
• Credentials via os.environ only.
• Decimal for all prices in Campaign objects.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("signal_birth_engine")

# ---------------------------------------------------------------------------
# Safe imports
# ---------------------------------------------------------------------------

try:
    from campaign_engine.campaign_state_engine import (
        Campaign,
        CampaignEngine,
        ResearchSignal,
        build_engine,
    )
    from campaign_engine.campaign_store import CampaignStore
    _CAMPAIGN_ENGINE_AVAILABLE = True
except Exception as _e:
    _CAMPAIGN_ENGINE_AVAILABLE = False
    log.warning(f"campaign_state_engine import failed: {_e}")

_SIGNAL_BIRTH_AVAILABLE = _CAMPAIGN_ENGINE_AVAILABLE

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_BARS_REQUIRED:    int   = 60    # minimum daily bars to score a symbol
MIN_GRADE_FOR_TIER:   str   = "C"   # minimum grade for any TIER assignment
TIER1_MIN_GRADE:      str   = "B+"
TIER2_MIN_GRADE:      str   = "B"
TIER3_MIN_GRADE:      str   = "C+"

GRADE_ORDER: dict[str, int] = {
    "A+": 10, "A": 9, "A-": 8,
    "B+": 7,  "B": 6, "B-": 5,
    "C+": 4,  "C": 3, "C-": 2,
    "D": 1,   "F": 0,
}

# Obstacle score quartile thresholds (derived from research; recalibrated nightly)
# These are recomputed each run from the live universe.
OBS_Q3_PERCENTILE: float = 0.75
OBS_Q4_PERCENTILE: float = 0.90


# ---------------------------------------------------------------------------
# Bar data structure (mirrors the audit script's Bar dataclass)
# ---------------------------------------------------------------------------

@dataclass
class DailyBarSimple:
    t:  str
    o:  float
    h:  float
    l:  float
    c:  float
    v:  float


# ---------------------------------------------------------------------------
# Wave analysis (ported directly from qualified_long_signal_audit.py)
# ---------------------------------------------------------------------------

@dataclass
class WaveResult:
    spd:          bool  = False   # Selling Pressure Diminishing
    dei:          bool  = False   # Demand Efficiency Improving
    buoyancy:     bool  = False   # Buoyancy Near Support
    up1_price_eff: float = 0.0   # Most recent up-wave price efficiency
    dn1_vol_eff:   float = 0.0   # Most recent down-wave volume efficiency
    wed_count:    int   = 0       # Wave Exhaustion Depth
    wave_score:   int   = 0       # 0-8 composite


def _identify_swings(
    bars: list[DailyBarSimple],
    n_confirm: int = 2,
) -> list[tuple[int, float, str]]:
    """Identify swing highs and lows. Mirrors _identify_swing_points()."""
    n = len(bars)
    swings: list[tuple[int, float, str]] = []

    for j in range(n_confirm, n - n_confirm):
        is_sh = (
            all(bars[j].h >= bars[j - k].h for k in range(1, n_confirm + 1))
            and all(bars[j].h >= bars[j + k].h for k in range(1, n_confirm + 1))
        )
        if is_sh:
            swings.append((j, bars[j].h, "high"))

        is_sl = (
            all(bars[j].l <= bars[j - k].l for k in range(1, n_confirm + 1))
            and all(bars[j].l <= bars[j + k].l for k in range(1, n_confirm + 1))
        )
        if is_sl:
            swings.append((j, bars[j].l, "low"))

    swings.sort(key=lambda x: x[0])
    return swings


def _build_waves(
    bars:    list[DailyBarSimple],
    swings:  list[tuple[int, float, str]],
    avg_vol: float,
) -> list[dict[str, Any]]:
    """Build directional waves from swing points."""
    if len(swings) < 2:
        return []

    # Deduplicate consecutive same-type swings
    deduped: list[tuple[int, float, str]] = []
    for s in swings:
        if deduped and deduped[-1][2] == s[2]:
            prev = deduped[-1]
            if s[2] == "high" and s[1] > prev[1]:
                deduped[-1] = s
            elif s[2] == "low" and s[1] < prev[1]:
                deduped[-1] = s
        else:
            deduped.append(s)

    waves: list[dict[str, Any]] = []
    for k in range(len(deduped) - 1):
        s1 = deduped[k]
        s2 = deduped[k + 1]
        start_idx, start_price, start_type = s1
        end_idx,   end_price,   end_type   = s2

        direction    = "up" if end_type == "high" else "dn"
        price_change = end_price - start_price
        duration     = max(end_idx - start_idx, 1)
        total_vol    = sum(bars[i].v for i in range(start_idx, min(end_idx + 1, len(bars))))
        vol_ratio    = (total_vol / avg_vol / duration) if avg_vol > 0 else 1.0
        price_eff    = abs(price_change) / duration if duration > 0 else 0.0
        vol_eff      = (total_vol / duration) if duration > 0 else 0.0
        return_pct   = abs(price_change / start_price * 100) if start_price > 0 else 0.0

        waves.append({
            "direction":         direction,
            "price_change":      price_change,
            "price_eff":         price_eff,
            "vol_eff":           vol_eff,
            "wave_return_pct":   return_pct,
            "wave_total_volume": total_vol,
            "wave_vol_ratio":    vol_ratio,
            "duration":          duration,
        })

    return waves


def compute_wave_metrics(bars: list[DailyBarSimple]) -> WaveResult:
    """
    Compute SPD, DEI, WED and wave score from daily bars.
    Mirrors _compute_wave_variables() in qualified_long_signal_audit.py.
    """
    result = WaveResult()

    if len(bars) < 20:
        return result

    avg_vol = sum(b.v for b in bars[-20:]) / 20.0
    if avg_vol == 0:
        return result

    # ATR estimate
    atrs = [abs(bars[i].h - bars[i].l) for i in range(1, len(bars))]
    atr  = sum(atrs[-14:]) / min(14, len(atrs)) if atrs else 0.0

    swings = _identify_swings(bars[-60:])
    waves  = _build_waves(bars[-60:], swings, avg_vol)

    if not waves:
        return result

    up_waves = [w for w in reversed(waves) if w["direction"] == "up"]
    dn_waves = [w for w in reversed(waves) if w["direction"] == "dn"]

    # SPD — selling pressure diminishing
    # Most recent down-wave drops less AND on lower volume than the prior
    if len(dn_waves) >= 2:
        result.spd = (
            dn_waves[0]["wave_return_pct"] <= dn_waves[1]["wave_return_pct"]
            and dn_waves[0]["wave_total_volume"] < dn_waves[1]["wave_total_volume"]
        )
        result.dn1_vol_eff = dn_waves[0]["vol_eff"]

    # DEI — demand efficiency improving
    # Most recent up-wave is more price-efficient than the prior
    if len(up_waves) >= 2:
        result.dei = (
            up_waves[0]["price_eff"] > up_waves[1]["price_eff"] * 0.9
            and up_waves[0]["wave_return_pct"] >= up_waves[1]["wave_return_pct"] * 0.7
        )
        result.up1_price_eff = up_waves[0]["price_eff"]

    # WED — wave exhaustion depth (consecutive deteriorating down-waves)
    wed = 0
    for i in range(1, len(dn_waves)):
        if dn_waves[i]["vol_eff"] < dn_waves[i - 1]["vol_eff"]:
            wed += 1
        else:
            break
    result.wed_count = wed

    # Buoyancy near support
    if len(bars) >= 5 and atr > 0:
        support = min(b.l for b in bars[-20:])
        recent_closes = [b.c for b in bars[-5:]]
        closes_near   = [c for c in recent_closes if abs(c - support) < atr * 1.2]
        if len(closes_near) >= 3:
            std = statistics.stdev(closes_near) if len(closes_near) > 1 else 0.0
            result.buoyancy = std < atr * 0.35

    # Composite wave score (0-8)
    score = 0
    if result.spd:     score += 2
    if result.dei:     score += 2
    if result.buoyancy: score += 1
    result.wave_score = max(0, score)

    return result


# ---------------------------------------------------------------------------
# Obstacle score (from _compute_obstacle_score in audit script)
# ---------------------------------------------------------------------------

def compute_obstacle_score(bars: list[DailyBarSimple]) -> tuple[float, int, float]:
    """
    Compute obstacle score and return (score, days_since_high, dist_pct).

    Obstacle = abs(distance from 252-day high) + (days_since_high / 5) + range_width
    """
    if len(bars) < 20:
        return 0.0, 0, 0.0

    lookback = bars[-min(252, len(bars)):]
    high_252  = max(b.h for b in lookback)
    current   = bars[-1].c

    dist_pct     = ((current - high_252) / high_252 * 100) if high_252 > 0 else 0.0
    dist_abs     = abs(dist_pct)

    # Days since 252-day high
    high_idx = max(range(len(lookback)), key=lambda i: lookback[i].h)
    days_since_high = len(lookback) - 1 - high_idx
    days_norm = days_since_high / 5.0

    # Range width (simplified — distance between 52-week high and 20-bar low)
    recent_low  = min(b.l for b in bars[-20:])
    range_width = ((high_252 - recent_low) / high_252 * 100) if high_252 > 0 else 0.0
    range_width = min(range_width, 30.0)  # cap at 30 to prevent outlier domination

    score = round(dist_abs + days_norm + range_width, 3)
    return score, days_since_high, dist_pct


# ---------------------------------------------------------------------------
# Duration bucket
# ---------------------------------------------------------------------------

def duration_bucket(days_since_high: int) -> str:
    if days_since_high < 20:
        return "DUR_UNDER_20"
    elif days_since_high < 60:
        return "DUR_20_60"
    elif days_since_high < 120:
        return "DUR_60_120"
    elif days_since_high < 180:
        return "DUR_120_180"
    else:
        return "DUR_180_PLUS"


# ---------------------------------------------------------------------------
# Grade (from grade_from_signal in audit script)
# ---------------------------------------------------------------------------

def compute_grade(
    bars:       list[DailyBarSimple],
    rel_volume: float,
) -> tuple[str, float]:
    """
    Compute signal grade from bars.
    Mirrors grade_from_signal() — simplified for daily bar input.
    """
    if len(bars) < 50:
        return "F", 0.0

    closes  = [b.c for b in bars]
    current = closes[-1]

    # MA20 and MA50
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20

    # RS proxies — simplified percentile within own history
    recent_returns  = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    rs_daily        = _percentile_rank(recent_returns, recent_returns[-1]) * 100
    rs_daily_slope  = (closes[-1] - closes[-5]) / closes[-5] * 100 if closes[-5] > 0 else 0.0

    # 2H RS proxy — use 10-bar momentum as surrogate
    rs_2h = _percentile_rank(recent_returns[-20:], recent_returns[-1]) * 100 if len(recent_returns) >= 20 else rs_daily

    score = 50.0
    score += max(0.0, min(18.0, (rs_2h - 50.0) * 0.45))
    score += max(0.0, min(18.0, (rs_daily - 20.0) * 0.25))
    score += max(0.0, min(12.0, rs_daily_slope * 5.0))

    if current > ma20:  score += 4
    if ma20 >= ma50:    score += 4
    if rel_volume >= 1.2: score += 5
    elif rel_volume >= 0.8: score += 2
    elif rel_volume < 0.5:  score -= 5

    score = max(0.0, min(100.0, score))

    if score >= 92:   grade = "A+"
    elif score >= 86: grade = "A"
    elif score >= 80: grade = "A-"
    elif score >= 74: grade = "B+"
    elif score >= 68: grade = "B"
    elif score >= 62: grade = "B-"
    elif score >= 56: grade = "C+"
    elif score >= 50: grade = "C"
    elif score >= 44: grade = "C-"
    elif score >= 35: grade = "D"
    else:             grade = "F"

    return grade, score


def _percentile_rank(values: list[float], value: float) -> float:
    """Return the percentile rank of value within values (0.0-1.0)."""
    if not values:
        return 0.5
    below = sum(1 for v in values if v < value)
    return below / len(values)


# ---------------------------------------------------------------------------
# Behavioral state classifier
# ---------------------------------------------------------------------------

def classify_behavioral_state(waves: WaveResult) -> tuple[str, int]:
    """
    Classify into one of 5 research-validated states.
    Mirrors _classify_behavioral_state() from the audit script.
    """
    if waves.up1_price_eff >= 3.0:
        return "STATE_4_EXPANSION", 4
    if waves.buoyancy:
        return "STATE_3_CONFIRMING", 3
    if waves.spd and waves.dei:
        return "STATE_2_EMERGING", 2
    if waves.spd and not waves.dei:
        return "STATE_1_EXHAUSTION", 1
    return "STATE_0_NEUTRAL", 0


# ---------------------------------------------------------------------------
# TIER assignment
# ---------------------------------------------------------------------------

def assign_tier(
    state_num:      int,
    obs_quartile:   int,   # 1-4
    dur_bucket:     str,
    grade:          str,
    grade_score:    float,
) -> Optional[str]:
    """
    Assign TIER_1 through TIER_4 based on validated research criteria.
    Returns None if signal does not qualify.

    TIER_1: State 1, OBS Q3/Q4, DUR_60_120, Grade B+
    TIER_2: State 1, OBS Q2+,   DUR_60_180, Grade B
    TIER_3: State 2, any OBS,   Grade C+
    TIER_4: Qualified long, Grade C, no strong behavioral signal
    """
    g = GRADE_ORDER.get(grade, 0)

    if g < GRADE_ORDER["C"]:
        return None  # Below minimum grade — no signal

    # TIER_1 — highest conviction
    if (
        state_num == 1
        and obs_quartile >= 3
        and dur_bucket == "DUR_60_120"
        and g >= GRADE_ORDER[TIER1_MIN_GRADE]
    ):
        return "TIER_1"

    # TIER_2 — strong conviction
    if (
        state_num == 1
        and obs_quartile >= 2
        and dur_bucket in {"DUR_60_120", "DUR_120_180"}
        and g >= GRADE_ORDER[TIER2_MIN_GRADE]
    ):
        return "TIER_2"

    # TIER_3 — emerging signal
    if (
        state_num == 2
        and g >= GRADE_ORDER[TIER3_MIN_GRADE]
    ):
        return "TIER_3"

    # TIER_4 — qualified long, watch list
    if g >= GRADE_ORDER["C"] and state_num >= 1:
        return "TIER_4"

    return None


# ---------------------------------------------------------------------------
# mfe90 expectation lookup (from validated research findings)
# ---------------------------------------------------------------------------

_MFE90_BY_TIER: dict[str, float] = {
    "TIER_1": 70.62,
    "TIER_2": 52.30,
    "TIER_3": 38.50,
    "TIER_4": 24.10,
}


# ---------------------------------------------------------------------------
# Main scoring function — one symbol
# ---------------------------------------------------------------------------

@dataclass
class SignalScore:
    symbol:         str
    tier:           Optional[str]
    grade:          str
    grade_score:    float
    obstacle_score: float
    obs_quartile:   int
    state_label:    str
    state_num:      int
    dur_bucket:     str
    days_since_high: int
    dist_pct:       float
    spd:            bool
    dei:            bool
    wed_count:      int
    mfe90_expected: float
    asym_ratio:     float = 1.0
    d_score:        float = 0.0


def score_symbol(
    symbol:        str,
    raw_bars:      list[dict],
    obs_quartiles: tuple[float, float, float],  # Q1, Q2, Q3 thresholds
) -> Optional[SignalScore]:
    """
    Score a single symbol against all TIER criteria.
    Returns None if insufficient data or below minimum grade.
    """
    if len(raw_bars) < MIN_BARS_REQUIRED:
        return None

    # Convert to DailyBarSimple
    bars: list[DailyBarSimple] = []
    for b in raw_bars:
        try:
            bars.append(DailyBarSimple(
                t=str(b.get("t", "")),
                o=float(b.get("o", 0)),
                h=float(b.get("h", 0)),
                l=float(b.get("l", 0)),
                c=float(b.get("c", 0)),
                v=float(b.get("v", 0)),
            ))
        except Exception:
            continue

    if len(bars) < MIN_BARS_REQUIRED:
        return None

    try:
        # Average volume for relative volume
        avg_vol    = sum(b.v for b in bars[-20:]) / 20.0
        cur_vol    = bars[-1].v
        rel_volume = (cur_vol / avg_vol) if avg_vol > 0 else 1.0

        # Core metrics
        obs_score, days_since_high, dist_pct = compute_obstacle_score(bars)
        waves     = compute_wave_metrics(bars)
        state_label, state_num = classify_behavioral_state(waves)
        dur       = duration_bucket(days_since_high)
        grade, grade_score = compute_grade(bars, rel_volume)

        # Obstacle quartile
        q1, q2, q3 = obs_quartiles
        if obs_score >= q3:
            obs_q = 4
        elif obs_score >= q2:
            obs_q = 3
        elif obs_score >= q1:
            obs_q = 2
        else:
            obs_q = 1

        tier = assign_tier(state_num, obs_q, dur, grade, grade_score)

        mfe90 = _MFE90_BY_TIER.get(tier, 0.0) if tier else 0.0

        # D-Score: composite 0-100
        d_score = min(100.0, round(
            grade_score * 0.4
            + obs_score * 0.3
            + waves.wave_score * 5.0
            + (10.0 if waves.spd else 0.0)
            + (5.0  if waves.dei else 0.0),
            2
        ))

        return SignalScore(
            symbol          = symbol,
            tier            = tier,
            grade           = grade,
            grade_score     = round(grade_score, 2),
            obstacle_score  = obs_score,
            obs_quartile    = obs_q,
            state_label     = state_label,
            state_num       = state_num,
            dur_bucket      = dur,
            days_since_high = days_since_high,
            dist_pct        = round(dist_pct, 2),
            spd             = waves.spd,
            dei             = waves.dei,
            wed_count       = waves.wed_count,
            mfe90_expected  = mfe90,
            d_score         = d_score,
        )

    except Exception as exc:
        log.debug("score_symbol error for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Nightly universe scoring
# ---------------------------------------------------------------------------

async def run_signal_birth_cycle(
    bars_cache:       dict[str, list[dict]],
    existing_symbols: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Score all symbols in bars_cache, identify new TIER_1/TIER_2 signals,
    and birth campaigns for symbols not already in an active campaign.

    Parameters
    ----------
    bars_cache:
        The radar_service._historical_bars dict — {symbol: [bar_dicts]}
    existing_symbols:
        Set of symbols that already have an active campaign.
        Avoids birthing duplicate campaigns.

    Returns
    -------
    Summary dict with signal counts and new campaign IDs.
    """
    if not _SIGNAL_BIRTH_AVAILABLE:
        return {"status": "unavailable", "reason": "campaign engine not loaded"}

    existing_symbols = existing_symbols or set()
    started_at = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("SIGNAL BIRTH ENGINE starting — %s", started_at.isoformat())
    log.info("Scoring %d symbols", len(bars_cache))
    log.info("=" * 60)

    # ── Step 1: Compute obstacle scores for quartile thresholds ──────────
    all_obs_scores: list[float] = []
    for symbol, raw_bars in bars_cache.items():
        if len(raw_bars) < MIN_BARS_REQUIRED:
            continue
        try:
            bars = [DailyBarSimple(
                t=str(b.get("t", "")),
                o=float(b.get("o", 0)), h=float(b.get("h", 0)),
                l=float(b.get("l", 0)), c=float(b.get("c", 0)),
                v=float(b.get("v", 0)),
            ) for b in raw_bars]
            obs, _, _ = compute_obstacle_score(bars)
            if obs > 0:
                all_obs_scores.append(obs)
        except Exception:
            continue

    if not all_obs_scores:
        return {"status": "error", "reason": "no obstacle scores computed"}

    sorted_obs  = sorted(all_obs_scores)
    n           = len(sorted_obs)
    q1_thresh   = sorted_obs[n // 4]
    q2_thresh   = sorted_obs[n // 2]
    q3_thresh   = sorted_obs[3 * n // 4]
    obs_quartiles = (q1_thresh, q2_thresh, q3_thresh)
    log.info("Obstacle quartiles: Q1=%.1f Q2=%.1f Q3=%.1f", q1_thresh, q2_thresh, q3_thresh)

    # ── Step 2: Score every symbol ────────────────────────────────────────
    all_scores:   list[SignalScore] = []
    errors = 0

    for symbol, raw_bars in bars_cache.items():
        try:
            score = score_symbol(symbol, raw_bars, obs_quartiles)
            if score and score.tier:
                all_scores.append(score)
        except Exception as exc:
            errors += 1
            if errors <= 5:
                log.warning("Scoring error for %s: %s", symbol, exc)

    # Sort by D-Score descending
    all_scores.sort(key=lambda s: s.d_score, reverse=True)

    tier_counts = {}
    for s in all_scores:
        tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1

    log.info("Signals found: %s | errors: %d", tier_counts, errors)

    # ── Step 3: Birth campaigns for TIER_1 and TIER_2 ────────────────────
    birth_candidates = [
        s for s in all_scores
        if s.tier in {"TIER_1", "TIER_2"}
        and s.symbol not in existing_symbols
    ]

    log.info("New birth candidates: %d", len(birth_candidates))

    if not birth_candidates:
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        return {
            "status":        "ok",
            "scored":        len(all_scores),
            "tier_counts":   tier_counts,
            "new_campaigns": 0,
            "elapsed_secs":  round(elapsed, 1),
        }

    store  = CampaignStore()
    engine = build_engine(store)

    new_campaign_ids: list[str] = []

    for signal in birth_candidates:
        try:
            # Current price from last bar
            last_bar  = bars_cache[signal.symbol][-1]
            entry_price = Decimal(str(last_bar.get("c", 0)))
            if entry_price <= 0:
                continue

            # P&F target — conservative: entry + (dist_pct * 0.5) as proxy
            # Full P&F count requires box-size calculation — placeholder for now
            pnf_multiplier = Decimal("1.15") if signal.tier == "TIER_1" else Decimal("1.10")
            pnf_target     = entry_price * pnf_multiplier

            research_signal = ResearchSignal(
                tier           = signal.tier,
                mfe90_expected = Decimal(str(signal.mfe90_expected)),
                obstacle_score = Decimal(str(signal.obstacle_score)),
                progress_score = Decimal(str(signal.grade_score)),
                d_score        = Decimal(str(signal.d_score)),
                duration_days  = signal.days_since_high,
                asym_ratio     = Decimal(str(signal.asym_ratio)),
                layer          = "A" if signal.tier == "TIER_1" else "B",
            )

            campaign = await engine.birth_campaign(
                symbol          = signal.symbol,
                entry_price     = entry_price,
                research_signal = research_signal,
                pnf_target      = pnf_target,
            )
            new_campaign_ids.append(campaign.campaign_id)
            log.info(
                "Campaign born | %s %s d_score=%.1f obs=%.1f dur=%s",
                signal.symbol, signal.tier, signal.d_score,
                signal.obstacle_score, signal.dur_bucket,
            )

        except Exception as exc:
            log.error("Failed to birth campaign for %s: %s", signal.symbol, exc)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":           "ok",
        "run_at":           started_at.isoformat(),
        "elapsed_secs":     round(elapsed, 1),
        "symbols_scored":   len(bars_cache),
        "signals_found":    len(all_scores),
        "tier_counts":      tier_counts,
        "new_campaigns":    len(new_campaign_ids),
        "campaign_ids":     new_campaign_ids,
    }

    log.info("=" * 60)
    log.info("SIGNAL BIRTH ENGINE complete in %.1fs", elapsed)
    log.info("  Signals found : %d", len(all_scores))
    log.info("  New campaigns : %d", len(new_campaign_ids))
    log.info("=" * 60)

    return summary


# ---------------------------------------------------------------------------
# Sync wrapper for main.py scheduler thread
# ---------------------------------------------------------------------------

def run_signal_birth_cycle_sync(bars_cache: dict) -> dict[str, Any]:
    """Synchronous wrapper for use in main.py daemon thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_signal_birth_cycle(bars_cache))
    finally:
        loop.close()
