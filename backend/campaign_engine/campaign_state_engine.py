# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_engine/campaign_state_engine.py

Campaign State Progression Engine
---------------------------------
This file supplies the WyckoffSignals dataclass consumed by
wyckoff_signal_bridge.py and a deterministic state machine used by the
nightly campaign pipeline.

States:
    BIRTH
    CONFIRMED
    SURVIVING
    EXPANDING
    MATURING
    DISTRIBUTION_RISK
    CLOSED

Design rule:
    The state machine may advance a campaign when evidence improves.
    It does not downgrade a normal campaign except into DISTRIBUTION_RISK.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional


class CampaignState(str, Enum):
    BIRTH = "BIRTH"
    CONFIRMED = "CONFIRMED"
    SURVIVING = "SURVIVING"
    EXPANDING = "EXPANDING"
    MATURING = "MATURING"
    DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
    CLOSED = "CLOSED"


_STATE_RANK: dict[str, int] = {
    CampaignState.BIRTH.value: 0,
    CampaignState.CONFIRMED.value: 1,
    CampaignState.SURVIVING.value: 2,
    CampaignState.EXPANDING.value: 3,
    CampaignState.MATURING.value: 4,
    CampaignState.DISTRIBUTION_RISK.value: 5,
    CampaignState.CLOSED.value: 6,
}


@dataclass(frozen=True)
class WyckoffSignals:
    sos_detected: bool = False
    jac_detected: bool = False
    bu_detected: bool = False
    lps_detected: bool = False
    choch_detected: bool = False
    spring_detected: bool = False
    upthrust_detected: bool = False
    spd: bool = False
    dei: bool = False
    wed_count: int = 0
    behavioral_state: str = "AMBIGUOUS"


@dataclass(frozen=True)
class CampaignTransition:
    old_state: CampaignState
    new_state: CampaignState
    changed: bool
    reason: str
    confidence: float


def _coerce_state(value: Any) -> CampaignState:
    raw = str(value or "BIRTH").upper().strip()
    for state in CampaignState:
        if raw == state.value:
            return state
    return CampaignState.BIRTH


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _days_since(value: Any) -> int:
    if not value:
        return 0
    try:
        if isinstance(value, date) and not isinstance(value, datetime):
            birth = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        else:
            birth = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if birth.tzinfo is None:
                birth = birth.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - birth.astimezone(timezone.utc)).days)
    except Exception:
        return 0


def target_proximity_pct(current_price: Optional[float], pnf_target: Optional[float]) -> Optional[float]:
    """
    Percent distance from current price to P&F target.
    Returns None if target/current price are unavailable.
    """
    if not current_price or not pnf_target or current_price <= 0 or pnf_target <= 0:
        return None
    return round(((pnf_target - current_price) / current_price) * 100.0, 2)


def default_pnf_target(entry_or_current_price: Optional[float], tier: str | None = None) -> Optional[float]:
    """
    Conservative placeholder target until the full P&F cause engine is wired.
    TIER_1 campaigns receive a larger default target than TIER_2 campaigns.
    """
    if not entry_or_current_price or entry_or_current_price <= 0:
        return None
    tier = str(tier or "").upper()
    multiplier = 1.30 if "TIER_1" in tier else 1.20
    return round(entry_or_current_price * multiplier, 4)


def transition_campaign_state(
    campaign: dict[str, Any],
    signals: WyckoffSignals,
    current_price: Optional[float] = None,
) -> CampaignTransition:
    """
    Decide the next campaign lifecycle state.

    Required campaign keys are flexible because Supabase rows may use:
        current_state or state_enum
        birth_date or created_at
        pnf_target
        entry_price

    Transition rules:
        BIRTH -> CONFIRMED:
            SOS/JAC or Spring + SPD/DEI
        CONFIRMED -> SURVIVING:
            BU/LPS or SPD + DEI persistence
        SURVIVING -> EXPANDING:
            positive campaign progress or strong demand efficiency
        EXPANDING -> MATURING:
            campaign approaches target zone
        any active state -> DISTRIBUTION_RISK:
            CHoCH, upthrust/distribution, or bearish WED pressure near target
    """
    old_state = _coerce_state(campaign.get("current_state") or campaign.get("state_enum"))
    if old_state == CampaignState.CLOSED or str(campaign.get("status", "")).upper() == "CLOSED":
        return CampaignTransition(old_state, CampaignState.CLOSED, False, "Campaign already closed", 1.0)

    entry = _float_or_none(campaign.get("entry_price")) or _float_or_none(campaign.get("current_price"))
    price = _float_or_none(current_price) or _float_or_none(campaign.get("current_price")) or entry
    target = _float_or_none(campaign.get("pnf_target"))
    prox = target_proximity_pct(price, target)
    age_days = int(campaign.get("campaign_age_days") or _days_since(campaign.get("birth_date") or campaign.get("created_at")))

    # Distribution overrides normal forward progression.
    if signals.choch_detected or signals.upthrust_detected or signals.behavioral_state == "DISTRIBUTION":
        return CampaignTransition(
            old_state,
            CampaignState.DISTRIBUTION_RISK,
            old_state != CampaignState.DISTRIBUTION_RISK,
            "Distribution risk: CHoCH/upthrust/distribution behavior detected",
            0.90,
        )

    if prox is not None and prox <= 15 and old_state in {
        CampaignState.EXPANDING,
        CampaignState.SURVIVING,
        CampaignState.CONFIRMED,
        CampaignState.MATURING,
    }:
        return CampaignTransition(
            old_state,
            CampaignState.MATURING,
            old_state != CampaignState.MATURING,
            f"Maturing: within {prox:.1f}% of P&F target",
            0.82,
        )

    # Confirmation.
    if old_state == CampaignState.BIRTH:
        if signals.sos_detected or signals.jac_detected or (signals.spring_detected and (signals.spd or signals.dei)):
            return CampaignTransition(
                old_state,
                CampaignState.CONFIRMED,
                True,
                "Confirmed: SOS/JAC or Spring with absorption/demand evidence",
                0.78,
            )
        return CampaignTransition(old_state, old_state, False, "Still in Birth: waiting for confirmation", 0.55)

    # Survival.
    if old_state == CampaignState.CONFIRMED:
        if signals.bu_detected or signals.lps_detected or (signals.spd and signals.dei):
            return CampaignTransition(
                old_state,
                CampaignState.SURVIVING,
                True,
                "Surviving: BU/LPS or persistent SPD + DEI",
                0.76,
            )
        if age_days >= 5 and signals.spd:
            return CampaignTransition(
                old_state,
                CampaignState.SURVIVING,
                True,
                "Surviving: confirmed campaign holding with selling pressure diminishing",
                0.68,
            )
        return CampaignTransition(old_state, old_state, False, "Confirmed: monitoring for BU/LPS survival evidence", 0.58)

    # Expansion.
    if old_state == CampaignState.SURVIVING:
        progress = 0.0
        if entry and price:
            progress = ((price - entry) / entry) * 100.0
        if progress >= 8.0 or (signals.dei and signals.sos_detected):
            return CampaignTransition(
                old_state,
                CampaignState.EXPANDING,
                True,
                f"Expanding: markup progress {progress:.1f}% with demand evidence",
                0.74,
            )
        return CampaignTransition(old_state, old_state, False, "Surviving: waiting for markup expansion", 0.60)

    if old_state == CampaignState.EXPANDING:
        if signals.dei or signals.spd:
            return CampaignTransition(old_state, old_state, False, "Expanding: campaign remains healthy", 0.70)
        if signals.wed_count >= 2:
            return CampaignTransition(
                old_state,
                CampaignState.DISTRIBUTION_RISK,
                True,
                "Distribution risk: wave exhaustion depth reached WED_2",
                0.72,
            )
        return CampaignTransition(old_state, old_state, False, "Expanding: monitoring campaign health", 0.60)

    if old_state == CampaignState.MATURING:
        if signals.wed_count >= 2:
            return CampaignTransition(
                old_state,
                CampaignState.DISTRIBUTION_RISK,
                True,
                "Distribution risk: maturing campaign with WED_2 exhaustion",
                0.80,
            )
        return CampaignTransition(old_state, old_state, False, "Maturing: target zone active, scanning for distribution", 0.68)

    if old_state == CampaignState.DISTRIBUTION_RISK:
        return CampaignTransition(old_state, old_state, False, "Distribution risk remains active", 0.78)

    return CampaignTransition(old_state, old_state, False, "No state change", 0.50)

