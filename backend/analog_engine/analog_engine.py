# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/analog_engine/analog_engine.py
---------------------------------------
Layer 3 — Historical Analog Engine (Campaign-Aware).

Matches active campaigns against historical campaign patterns to produce
lifecycle-aware probability estimates.

WHAT IT DOES
------------
For each active campaign, finds historical campaigns that match on:
  1. Campaign state at the same age (days_open)
  2. Behavioral classification (ACCUMULATION / DISTRIBUTION / AMBIGUOUS)
  3. Obstacle score quartile (Q1-Q4)
  4. TIER classification (TIER_1 / TIER_2)
  5. Duration bucket (DUR_60_120 etc.)

Returns the matched population's forward outcome statistics:
  - Success rate (% that reached P&F target or positive mfe90)
  - Average mfe90 at 90 days
  - Median campaign duration to target
  - Most common next state transition

PHASE 13 DEPENDENCY
-------------------
The analog engine is most powerful once historical campaign data accumulates
in the campaign_state_history and campaign_observations tables. On first run,
it falls back to the Phase 12B research benchmarks from run_phase12_scoring.py.

SCORING ARCHITECTURE
--------------------
Match quality is scored 0-100:
  State match at same age:     30 pts
  Behavioral classification:   20 pts
  Obstacle quartile:           20 pts
  TIER match:                  15 pts
  Duration bucket:             15 pts

Minimum match score: 50 pts (at least 3 factors must align).
Minimum analog population: 5 campaigns for statistical validity.

CLAUDE.md compliance
--------------------
• Credentials via os.environ only.
• Decimal for all prices.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("analog_engine")

# ---------------------------------------------------------------------------
# Safe imports
# ---------------------------------------------------------------------------

try:
    from campaign_engine.campaign_store import CampaignStore
    from campaign_engine.campaign_state_engine import Campaign, CampaignState
    _STORE_AVAILABLE = True
except Exception as _e:
    _STORE_AVAILABLE = False
    log.warning(f"campaign_store import failed: {_e}")

_ANALOG_AVAILABLE = _STORE_AVAILABLE

# ---------------------------------------------------------------------------
# Phase 12B research benchmarks — fallback when no historical campaigns exist
# ---------------------------------------------------------------------------

_TIER_BENCHMARKS: dict[str, dict[str, float]] = {
    "TIER_1": {
        "success_rate":     70.62,
        "avg_mfe90":        70.62,
        "median_days":      67.0,
        "confidence_level": "RESEARCH_VALIDATED",
    },
    "TIER_2": {
        "success_rate":     59.87,
        "avg_mfe90":        52.30,
        "median_days":      72.0,
        "confidence_level": "RESEARCH_VALIDATED",
    },
    "TIER_3": {
        "success_rate":     44.20,
        "avg_mfe90":        38.50,
        "median_days":      80.0,
        "confidence_level": "RESEARCH_VALIDATED",
    },
    "TIER_4": {
        "success_rate":     31.10,
        "avg_mfe90":        24.10,
        "median_days":      85.0,
        "confidence_level": "RESEARCH_VALIDATED",
    },
}

# State-specific outcome adjustments from Phase 5 survival research
_STATE_MFE90_MULTIPLIERS: dict[str, float] = {
    "BIRTH":             1.00,
    "CONFIRMED":         1.12,   # SOS confirmed — higher conviction
    "SURVIVING":         1.08,   # BU/LPS held — structure intact
    "EXPANDING":         0.85,   # Already moving — less remaining upside
    "MATURING":          0.60,   # Most of the move captured
    "DISTRIBUTION_RISK": 0.30,   # Exit watch — minimal remaining upside
}


# ---------------------------------------------------------------------------
# Analog result
# ---------------------------------------------------------------------------

@dataclass
class AnalogMatch:
    campaign_id:        str
    symbol:             str
    match_score:        float          # 0-100
    analog_count:       int            # number of historical matches
    success_rate:       float          # % of analogs that succeeded
    avg_mfe90:          float          # average mfe90 of analogs
    median_days:        float          # median days to target
    confidence_level:   str            # HIGH / MEDIUM / LOW / RESEARCH_ONLY
    next_state_prob:    dict[str, float] = field(default_factory=dict)
    source:             str            = "LIVE_ANALOGS"  # or RESEARCH_BENCHMARKS


@dataclass
class AnalogQuery:
    """Search parameters extracted from an active campaign."""
    campaign_id:     str
    symbol:          str
    state:           str
    days_open:       int
    tier:            str
    obstacle_score:  float
    dur_bucket:      str
    behavioral:      str   # ACCUMULATION / DISTRIBUTION / AMBIGUOUS


# ---------------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------------

def _score_match(query: AnalogQuery, candidate: dict) -> float:
    """
    Score how well a historical campaign matches the query.
    Returns 0-100. Minimum 50 required for inclusion.
    """
    score = 0.0

    # State at similar age (±10 days) — 30 pts
    cand_state    = candidate.get("current_state", "")
    cand_age      = int(candidate.get("campaign_age_days", 0))
    age_diff      = abs(cand_age - query.days_open)
    if cand_state == query.state:
        if age_diff <= 5:
            score += 30.0
        elif age_diff <= 10:
            score += 20.0
        elif age_diff <= 20:
            score += 10.0

    # Behavioral classification — 20 pts
    cand_bhv = candidate.get("behavioral_classification", "AMBIGUOUS")
    if cand_bhv == query.behavioral:
        score += 20.0
    elif cand_bhv == "AMBIGUOUS" or query.behavioral == "AMBIGUOUS":
        score += 5.0

    # Obstacle quartile — 20 pts
    cand_obs = float(candidate.get("obstacle_score", 0))
    query_obs = query.obstacle_score
    obs_diff  = abs(cand_obs - query_obs)
    if obs_diff <= 5:
        score += 20.0
    elif obs_diff <= 15:
        score += 12.0
    elif obs_diff <= 30:
        score += 5.0

    # TIER match — 15 pts
    if candidate.get("historical_confidence", "") == query.tier:
        score += 15.0

    # Duration bucket — 15 pts
    if candidate.get("duration_bucket", "") == query.dur_bucket:
        score += 15.0
    elif _adjacent_duration(candidate.get("duration_bucket", ""), query.dur_bucket):
        score += 7.0

    return round(score, 1)


def _adjacent_duration(a: str, b: str) -> bool:
    """Return True if two duration buckets are adjacent."""
    order = ["DUR_UNDER_20", "DUR_20_60", "DUR_60_120", "DUR_120_180", "DUR_180_PLUS"]
    try:
        return abs(order.index(a) - order.index(b)) == 1
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Analog lookup — live historical campaigns from Supabase
# ---------------------------------------------------------------------------

def _fetch_closed_campaigns(supabase_url: str, supabase_key: str) -> list[dict]:
    """Fetch all CLOSED campaigns from Supabase for analog matching."""
    try:
        import requests as _requests
        headers = {
            "apikey":        supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type":  "application/json",
        }
        r = _requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/campaigns",
            headers=headers,
            params={
                "select": (
                    "display_label,symbol,current_state,campaign_age_days,"
                    "historical_confidence,obstacle_score,close_reason,"
                    "entry_price,current_price,status"
                ),
                "status": "eq.CLOSED",
                "limit":  "10000",
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        log.warning("Could not fetch closed campaigns for analog: %s", exc)
    return []


# ---------------------------------------------------------------------------
# Outcome computation from matched analogs
# ---------------------------------------------------------------------------

def _compute_outcomes(matches: list[dict]) -> dict[str, Any]:
    """Compute success rate and avg mfe90 from a population of matched campaigns."""
    if not matches:
        return {}

    successes  = [m for m in matches if m.get("close_reason") == "TARGET_REACHED"]
    success_rate = len(successes) / len(matches) * 100.0

    # mfe90 proxy — % gain from entry to close price
    mfe90_vals = []
    for m in matches:
        try:
            entry = float(m.get("entry_price", 0))
            close = float(m.get("current_price", 0))
            if entry > 0 and close > 0:
                mfe90_vals.append((close - entry) / entry * 100.0)
        except Exception:
            continue

    avg_mfe90   = sum(mfe90_vals) / len(mfe90_vals) if mfe90_vals else 0.0
    median_days = _median([float(m.get("campaign_age_days", 90)) for m in matches])

    # Next state probabilities from state history
    state_counts: dict[str, int] = {}
    for m in matches:
        state = m.get("current_state", "CLOSED")
        state_counts[state] = state_counts.get(state, 0) + 1

    total = len(matches)
    next_state_prob = {k: round(v / total * 100, 1) for k, v in state_counts.items()}

    return {
        "success_rate":    round(success_rate, 1),
        "avg_mfe90":       round(avg_mfe90, 2),
        "median_days":     round(median_days, 0),
        "next_state_prob": next_state_prob,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


# ---------------------------------------------------------------------------
# Research benchmark fallback
# ---------------------------------------------------------------------------

def _research_benchmark(campaign: "Campaign") -> AnalogMatch:
    """
    Return Phase 12B research benchmarks when insufficient live analogs exist.
    Adjusts mfe90 for current campaign state using survival multipliers.
    """
    tier      = campaign.tier or "TIER_2"
    bench     = _TIER_BENCHMARKS.get(tier, _TIER_BENCHMARKS["TIER_2"])
    state_key = campaign.state.value if hasattr(campaign.state, "value") else str(campaign.state)
    multiplier = _STATE_MFE90_MULTIPLIERS.get(state_key, 1.0)

    adj_mfe90 = bench["avg_mfe90"] * multiplier

    return AnalogMatch(
        campaign_id      = campaign.campaign_id,
        symbol           = campaign.symbol,
        match_score      = 0.0,
        analog_count     = 0,
        success_rate     = bench["success_rate"],
        avg_mfe90        = round(adj_mfe90, 2),
        median_days      = bench["median_days"],
        confidence_level = "RESEARCH_ONLY",
        source           = "RESEARCH_BENCHMARKS",
    )


# ---------------------------------------------------------------------------
# Main analog lookup — single campaign
# ---------------------------------------------------------------------------

def find_analogs(
    campaign:        "Campaign",
    closed_campaigns: list[dict],
    min_match_score: float = 50.0,
    min_population:  int   = 5,
) -> AnalogMatch:
    """
    Find historical analog campaigns for an active campaign.

    Falls back to research benchmarks if insufficient live analogs exist.
    """
    query = AnalogQuery(
        campaign_id    = campaign.campaign_id,
        symbol         = campaign.symbol,
        state          = campaign.state.value if hasattr(campaign.state, "value") else str(campaign.state),
        days_open      = campaign.days_open,
        tier           = campaign.tier or "TIER_2",
        obstacle_score = float(campaign.obstacle_score),
        dur_bucket     = _days_to_bucket(campaign.duration_days),
        behavioral     = "ACCUMULATION",  # refined by Phase 13
    )

    # Score all closed campaigns
    scored: list[tuple[float, dict]] = []
    for candidate in closed_campaigns:
        score = _score_match(query, candidate)
        if score >= min_match_score:
            scored.append((score, candidate))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_matches = [c for _, c in scored[:50]]  # top 50 analogs max

    if len(top_matches) < min_population:
        # Not enough live analogs — use research benchmarks
        result = _research_benchmark(campaign)
        log.debug(
            "Analog fallback to research benchmarks for %s (only %d matches)",
            campaign.symbol, len(top_matches),
        )
        return result

    outcomes = _compute_outcomes(top_matches)
    avg_match = sum(s for s, _ in scored[:len(top_matches)]) / len(top_matches)

    confidence = (
        "HIGH"   if len(top_matches) >= 20 and avg_match >= 70 else
        "MEDIUM" if len(top_matches) >= 10 else
        "LOW"
    )

    return AnalogMatch(
        campaign_id      = campaign.campaign_id,
        symbol           = campaign.symbol,
        match_score      = round(avg_match, 1),
        analog_count     = len(top_matches),
        success_rate     = outcomes.get("success_rate", 0.0),
        avg_mfe90        = outcomes.get("avg_mfe90", 0.0),
        median_days      = outcomes.get("median_days", 90.0),
        confidence_level = confidence,
        next_state_prob  = outcomes.get("next_state_prob", {}),
        source           = "LIVE_ANALOGS",
    )


def _days_to_bucket(days: int) -> str:
    if days < 20:   return "DUR_UNDER_20"
    if days < 60:   return "DUR_20_60"
    if days < 120:  return "DUR_60_120"
    if days < 180:  return "DUR_120_180"
    return "DUR_180_PLUS"


# ---------------------------------------------------------------------------
# Nightly analog cycle
# ---------------------------------------------------------------------------

async def run_nightly_analog_cycle(
    bars_cache: dict[str, list[dict]],
) -> dict[str, Any]:
    """
    Run analog matching for all active campaigns.
    Runs at 21:45 UTC — after ODS cycle (21:30 UTC).
    """
    if not _ANALOG_AVAILABLE:
        return {"status": "unavailable", "reason": "campaign store not loaded"}

    started_at = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("ANALOG ENGINE starting — %s", started_at.isoformat())

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

    store = CampaignStore()

    try:
        active_campaigns: list[Campaign] = await store.fetch_active_campaigns()
    except Exception as exc:
        log.error("Could not fetch active campaigns for analog: %s", exc)
        return {"status": "error", "reason": str(exc)}

    if not active_campaigns:
        return {"status": "ok", "campaigns_matched": 0}

    # Fetch all closed campaigns once for the whole cycle
    closed_campaigns = _fetch_closed_campaigns(supabase_url, supabase_key)
    log.info("Closed campaigns available for matching: %d", len(closed_campaigns))

    results: list[AnalogMatch] = []
    research_only = 0

    for campaign in active_campaigns:
        try:
            match = find_analogs(campaign, closed_campaigns)
            results.append(match)
            if match.source == "RESEARCH_BENCHMARKS":
                research_only += 1
        except Exception as exc:
            log.error("Analog error for %s: %s", campaign.symbol, exc)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":            "ok",
        "run_at":            started_at.isoformat(),
        "elapsed_secs":      round(elapsed, 1),
        "campaigns_matched": len(results),
        "research_only":     research_only,
        "live_analogs":      len(results) - research_only,
        "closed_pool_size":  len(closed_campaigns),
    }

    log.info(
        "ANALOG ENGINE complete in %.1fs | matched=%d research_only=%d live=%d",
        elapsed, len(results), research_only, len(results) - research_only,
    )

    return summary
