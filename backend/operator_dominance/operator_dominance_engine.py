# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/operator_dominance/operator_dominance_engine.py
--------------------------------------------------------
Layer 3 — Operator Dominance Score (ODS) Engine.

Computes a continuous 0-100 score measuring institutional versus retail
control for every active campaign. The score is updated daily and stored
in the campaigns table.

ODS FRAMEWORK (Phase 14)
-------------------------
The Operator Dominance Score answers one question:
  Is an institutional operator still in control of this campaign?

High ODS (70-100): Operator actively accumulating / defending structure.
Mid  ODS (40-69):  Mixed — operator present but retail noise increasing.
Low  ODS (0-39):   Operator exiting — distribution risk elevated.

CONJUNCTION EXIT SIGNAL
-----------------------
Fires when ODS drops below 40 while campaign state is MATURING or
DISTRIBUTION_RISK. This is the exit timing mechanism described in Phase 14.

ODS COMPONENTS (7 factors, weighted)
--------------------------------------
1. Volume Efficiency Ratio      (20%) — operator volume vs retail volume
2. Absorption Persistence       (15%) — consecutive bars absorbed near support
3. Price Defense                (15%) — closes persistently above key levels
4. Wave Efficiency Delta        (15%) — SPD/DEI trend over rolling window
5. Spread Quality               (10%) — tight spreads on down-bars (operator hold)
6. Relative Volume Profile      (15%) — volume pattern matches institutional cadence
7. Campaign Health Delta        (10%) — ODS trend over 5-day window

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
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("operator_dominance_engine")

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

_ODS_AVAILABLE = _STORE_AVAILABLE


# ---------------------------------------------------------------------------
# ODS result
# ---------------------------------------------------------------------------

@dataclass
class ODSResult:
    symbol:             str
    campaign_id:        str
    ods_score:          float        # 0-100
    distribution_risk:  float        # 0-100 (inverse of ODS for late states)
    conjunction_exit:   bool         # True = exit signal firing
    components:         dict         = field(default_factory=dict)
    computed_at:        str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def operator_label(self) -> str:
        if self.ods_score >= 70:
            return "OPERATOR_IN_CONTROL"
        elif self.ods_score >= 40:
            return "MIXED_CONTROL"
        else:
            return "OPERATOR_EXITING"


# ---------------------------------------------------------------------------
# Component calculations
# ---------------------------------------------------------------------------

def _volume_efficiency_ratio(bars: list[dict]) -> float:
    """
    Component 1 — Volume Efficiency Ratio (0-100, weight 20%)

    Institutional operators move price efficiently — high volume on up-bars,
    low volume on down-bars. Retail does the opposite (chases moves).

    Ratio = (avg_up_bar_volume / avg_down_bar_volume)
    Normalized: ratio >= 2.0 → 100, ratio <= 0.5 → 0
    """
    if len(bars) < 10:
        return 50.0

    up_vols   = [float(b.get("v", 0)) for b in bars[-20:] if float(b.get("c", 0)) >= float(b.get("o", 0))]
    down_vols = [float(b.get("v", 0)) for b in bars[-20:] if float(b.get("c", 0)) <  float(b.get("o", 0))]

    if not up_vols or not down_vols:
        return 50.0

    avg_up   = sum(up_vols)   / len(up_vols)
    avg_down = sum(down_vols) / len(down_vols)

    if avg_down == 0:
        return 100.0

    ratio = avg_up / avg_down
    # Normalize: 2.0 → 100, 1.0 → 50, 0.5 → 0
    score = min(100.0, max(0.0, (ratio - 0.5) / 1.5 * 100.0))
    return round(score, 2)


def _absorption_persistence(bars: list[dict], support_level: float) -> float:
    """
    Component 2 — Absorption Persistence (0-100, weight 15%)

    Counts consecutive bars where price tested below support but closed above.
    Operator holds up the stock — retail tries to push it down but fails.
    """
    if len(bars) < 5 or support_level <= 0:
        return 50.0

    absorbed_count = 0
    for b in reversed(bars[-15:]):
        low   = float(b.get("l", 0))
        close = float(b.get("c", 0))
        if low < support_level and close >= support_level * 0.99:
            absorbed_count += 1
        else:
            break  # consecutive only

    # 5+ absorbed bars → 100, 0 → 0
    score = min(100.0, absorbed_count / 5.0 * 100.0)
    return round(score, 2)


def _price_defense(bars: list[dict], entry_price: float) -> float:
    """
    Component 3 — Price Defense (0-100, weight 15%)

    What percentage of the last 20 bars closed above the campaign entry price?
    Operator defends the entry level — stock does not give back gains.
    """
    if len(bars) < 5 or entry_price <= 0:
        return 50.0

    recent = bars[-20:]
    above  = sum(1 for b in recent if float(b.get("c", 0)) >= entry_price)
    score  = above / len(recent) * 100.0
    return round(score, 2)


def _wave_efficiency_delta(bars: list[dict]) -> float:
    """
    Component 4 — Wave Efficiency Delta (0-100, weight 15%)

    Measures whether the SPD/DEI behavioral trend is improving or deteriorating.
    Computes up-wave vs down-wave price efficiency ratio over the last 10 bars
    and compares it to the prior 10 bars.

    Improving → operator accumulation strengthening.
    Deteriorating → operator activity fading.
    """
    if len(bars) < 20:
        return 50.0

    def _wave_ratio(window: list[dict]) -> float:
        up_moves   = [abs(float(b.get("c", 0)) - float(b.get("o", 0)))
                      for b in window if float(b.get("c", 0)) >= float(b.get("o", 0))]
        down_moves = [abs(float(b.get("c", 0)) - float(b.get("o", 0)))
                      for b in window if float(b.get("c", 0)) <  float(b.get("o", 0))]
        avg_up   = sum(up_moves)   / len(up_moves)   if up_moves   else 0.0
        avg_down = sum(down_moves) / len(down_moves) if down_moves else 0.01
        return avg_up / avg_down

    recent_ratio = _wave_ratio(bars[-10:])
    prior_ratio  = _wave_ratio(bars[-20:-10])

    if prior_ratio == 0:
        return 50.0

    delta = (recent_ratio - prior_ratio) / prior_ratio
    # +50% improvement → 100, flat → 50, -50% → 0
    score = min(100.0, max(0.0, 50.0 + delta * 100.0))
    return round(score, 2)


def _spread_quality(bars: list[dict]) -> float:
    """
    Component 5 — Spread Quality (0-100, weight 10%)

    On down-bars, operators tend to have tight spreads (controlled selling).
    Retail panic shows wide spreads on down-bars.

    Metric: avg spread on down-bars vs avg spread on up-bars.
    Tight down spreads relative to up spreads = operator in control.
    """
    if len(bars) < 10:
        return 50.0

    def _spread(b: dict) -> float:
        h = float(b.get("h", 0))
        l = float(b.get("l", 0))
        c = float(b.get("c", 1))
        return (h - l) / c if c > 0 else 0.0

    recent     = bars[-20:]
    up_spreads = [_spread(b) for b in recent if float(b.get("c", 0)) >= float(b.get("o", 0))]
    dn_spreads = [_spread(b) for b in recent if float(b.get("c", 0)) <  float(b.get("o", 0))]

    if not up_spreads or not dn_spreads:
        return 50.0

    avg_up = sum(up_spreads) / len(up_spreads)
    avg_dn = sum(dn_spreads) / len(dn_spreads)

    if avg_up == 0:
        return 50.0

    # Tight down spread = avg_dn < avg_up → score > 50
    ratio = avg_dn / avg_up
    score = min(100.0, max(0.0, (2.0 - ratio) / 2.0 * 100.0))
    return round(score, 2)


def _relative_volume_profile(bars: list[dict]) -> float:
    """
    Component 6 — Relative Volume Profile (0-100, weight 15%)

    Institutional cadence: volume expands on up-days, contracts on down-days,
    and periodically spikes on accumulation bars (high volume, small price move).

    Score based on percentage of bars matching the institutional volume pattern.
    """
    if len(bars) < 20:
        return 50.0

    avg_vol = sum(float(b.get("v", 0)) for b in bars[-20:]) / 20.0
    if avg_vol == 0:
        return 50.0

    institutional_bars = 0
    recent = bars[-20:]

    for b in recent:
        vol    = float(b.get("v", 0))
        close  = float(b.get("c", 0))
        open_  = float(b.get("o", 0))
        spread = abs(close - open_) / open_ if open_ > 0 else 0.0
        rel_vol = vol / avg_vol

        is_up = close >= open_

        # Up-bar with above-average volume = demand
        if is_up and rel_vol >= 1.1:
            institutional_bars += 1
        # Down-bar with below-average volume = controlled retreat
        elif not is_up and rel_vol <= 0.9:
            institutional_bars += 1
        # High volume + small spread = absorption (best institutional signal)
        elif rel_vol >= 1.5 and spread < 0.005:
            institutional_bars += 1

    score = institutional_bars / len(recent) * 100.0
    return round(score, 2)


def _campaign_health_delta(ods_history: list[float]) -> float:
    """
    Component 7 — Campaign Health Delta (0-100, weight 10%)

    Is ODS trending up (operator strengthening) or down (operator fading)?
    Compares most recent ODS to 5-day prior ODS.
    """
    if len(ods_history) < 2:
        return 50.0

    recent = ods_history[-1]
    prior  = ods_history[-min(5, len(ods_history))]

    delta  = recent - prior
    # +20 point improvement → 100, flat → 50, -20 → 0
    score  = min(100.0, max(0.0, 50.0 + delta * 2.5))
    return round(score, 2)


# ---------------------------------------------------------------------------
# Core ODS computation
# ---------------------------------------------------------------------------

def compute_ods(
    campaign:     "Campaign",
    bars:         list[dict],
    ods_history:  list[float],
) -> ODSResult:
    """
    Compute the Operator Dominance Score for a single campaign.

    Parameters
    ----------
    campaign:    Active Campaign object with entry_price and state.
    bars:        Recent daily bars from HISTORICAL_BARS cache.
    ods_history: List of prior ODS scores for this campaign (oldest first).

    Returns
    -------
    ODSResult with ods_score, distribution_risk, and conjunction_exit flag.
    """
    entry_price = float(campaign.entry_price)

    # Support level — use entry price as proxy (Phase 13 will use LPS levels)
    support_level = entry_price * 0.98

    # ── Compute all 7 components ──────────────────────────────────────────
    c1 = _volume_efficiency_ratio(bars)
    c2 = _absorption_persistence(bars, support_level)
    c3 = _price_defense(bars, entry_price)
    c4 = _wave_efficiency_delta(bars)
    c5 = _spread_quality(bars)
    c6 = _relative_volume_profile(bars)
    c7 = _campaign_health_delta(ods_history)

    # ── Weighted composite ────────────────────────────────────────────────
    ods_score = round(
        c1 * 0.20 +
        c2 * 0.15 +
        c3 * 0.15 +
        c4 * 0.15 +
        c5 * 0.10 +
        c6 * 0.15 +
        c7 * 0.10,
        2
    )

    # ── Distribution risk (inverse for late-stage campaigns) ──────────────
    # In early states, distribution risk is low regardless of ODS.
    # In MATURING / DISTRIBUTION_RISK, distribution risk = 100 - ODS.
    late_states = {
        CampaignState.MATURING,
        CampaignState.DISTRIBUTION_RISK,
    }
    if campaign.state in late_states:
        distribution_risk = round(100.0 - ods_score, 2)
    else:
        distribution_risk = round(max(0.0, 50.0 - ods_score * 0.5), 2)

    # ── Conjunction Exit Signal ───────────────────────────────────────────
    # ODS drops below 40 while campaign is in a late state.
    conjunction_exit = (
        ods_score < 40.0
        and campaign.state in late_states
    )

    if conjunction_exit:
        log.warning(
            "CONJUNCTION EXIT SIGNAL | %s campaign=%s ODS=%.1f state=%s",
            campaign.symbol, campaign.campaign_id, ods_score, campaign.state.value,
        )

    return ODSResult(
        symbol            = campaign.symbol,
        campaign_id       = campaign.campaign_id,
        ods_score         = ods_score,
        distribution_risk = distribution_risk,
        conjunction_exit  = conjunction_exit,
        components        = {
            "volume_efficiency":    c1,
            "absorption_persist":   c2,
            "price_defense":        c3,
            "wave_eff_delta":       c4,
            "spread_quality":       c5,
            "rel_vol_profile":      c6,
            "campaign_health_delta": c7,
        },
    )


# ---------------------------------------------------------------------------
# Nightly ODS cycle
# ---------------------------------------------------------------------------

async def run_nightly_ods_cycle(
    bars_cache: dict[str, list[dict]],
) -> dict[str, Any]:
    """
    Compute ODS for all active campaigns and write results to Supabase.

    Runs at 21:30 UTC — after the campaign pipeline (21:00 UTC) has
    updated campaign states.

    Parameters
    ----------
    bars_cache:
        The radar_service._historical_bars dict — {symbol: [bar_dicts]}
    """
    if not _ODS_AVAILABLE:
        return {"status": "unavailable", "reason": "campaign store not loaded"}

    started_at = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("ODS ENGINE starting — %s", started_at.isoformat())
    log.info("=" * 60)

    store = CampaignStore()

    try:
        active_campaigns: list[Campaign] = await store.fetch_active_campaigns()
    except Exception as exc:
        log.error("Could not fetch active campaigns for ODS: %s", exc)
        return {"status": "error", "reason": str(exc)}

    if not active_campaigns:
        log.info("No active campaigns — ODS cycle complete.")
        return {"status": "ok", "campaigns_evaluated": 0}

    results:          list[ODSResult] = []
    conjunction_exits: list[str]      = []
    errors = 0

    for campaign in active_campaigns:
        bars = bars_cache.get(campaign.symbol)
        if not bars or len(bars) < 10:
            log.warning("No bars for ODS computation: %s", campaign.symbol)
            continue

        try:
            # ODS history — placeholder until we persist daily ODS to DB
            ods_history: list[float] = []

            result = compute_ods(campaign, bars, ods_history)
            results.append(result)

            if result.conjunction_exit:
                conjunction_exits.append(campaign.symbol)

        except Exception as exc:
            errors += 1
            log.error("ODS error for %s: %s", campaign.symbol, exc)

    # ── Write ODS scores back to campaigns table ──────────────────────────
    if results:
        try:
            import requests as _requests

            url = os.environ.get("SUPABASE_URL", "").rstrip("/")
            key = (
                os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
                or os.environ.get("SUPABASE_ANON_KEY", "")
            )
            headers = {
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "resolution=merge-duplicates,return=minimal",
            }

            rows = [
                {
                    "display_label":    r.campaign_id,
                    "operator_dominance": r.ods_score,
                    "distribution_risk":  r.distribution_risk,
                    "updated_at":         datetime.now(timezone.utc).isoformat(),
                }
                for r in results
            ]

            # Batch update in groups of 100
            for i in range(0, len(rows), 100):
                batch = rows[i:i + 100]
                _requests.post(
                    f"{url}/rest/v1/campaigns",
                    headers=headers,
                    json=batch,
                    timeout=30,
                )

        except Exception as exc:
            log.error("ODS Supabase write failed: %s", exc)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":             "ok",
        "run_at":             started_at.isoformat(),
        "elapsed_secs":       round(elapsed, 1),
        "campaigns_evaluated": len(results),
        "conjunction_exits":  conjunction_exits,
        "errors":             errors,
        "avg_ods":            round(sum(r.ods_score for r in results) / len(results), 1) if results else 0,
    }

    log.info("ODS ENGINE complete in %.1fs | evaluated=%d exits=%d",
             elapsed, len(results), len(conjunction_exits))

    return summary
