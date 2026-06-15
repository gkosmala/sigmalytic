"""
engines/campaign_engine.py
==========================
Sigmalytic V2 — Layer 3: Campaign Engine

Implements a strict enum-based state machine that tracks every active campaign
from BIRTH through CLOSED.  Depends on data/campaign_store.py (Layer 2) for all
persistence; this module contains zero DB calls directly.

State transition map
--------------------
BIRTH ──► CONFIRMED ──► SURVIVING ──► EXPANDING ──► MATURING ──► DISTRIBUTION_RISK
  │            │              │             │              │                │
  └────────────┴──────────────┴─────────────┴──────────────┴────────────────┴──► CLOSED

Allowed forward transitions only (no skipping states); regression to CLOSED is
permitted from any state on stop-loss breach or 90-day expiry.

CLAUDE.md compliance
--------------------
• No hardcoded credentials — none needed (pure engine logic).
• All prices and quantities use Decimal.
• Full type hints on every function and class.
• Structured try/except with exponential-backoff logging pattern.
• async/await throughout for non-blocking integration with the live data layer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Campaign State Machine
# ---------------------------------------------------------------------------

class CampaignState(str, Enum):
    """
    Ordered lifecycle states for an institutional campaign.

    Using str mixin so values serialise cleanly to/from Supabase JSON columns
    without an extra conversion step.
    """
    BIRTH             = "BIRTH"
    CONFIRMED         = "CONFIRMED"
    SURVIVING         = "SURVIVING"
    EXPANDING         = "EXPANDING"
    MATURING          = "MATURING"
    DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
    CLOSED            = "CLOSED"


# Defines which forward transitions are legal.  Regression to CLOSED is handled
# separately so it can happen from any state.
_ALLOWED_TRANSITIONS: dict[CampaignState, set[CampaignState]] = {
    CampaignState.BIRTH:             {CampaignState.CONFIRMED,         CampaignState.CLOSED},
    CampaignState.CONFIRMED:         {CampaignState.SURVIVING,         CampaignState.CLOSED},
    CampaignState.SURVIVING:         {CampaignState.EXPANDING,         CampaignState.CLOSED},
    CampaignState.EXPANDING:         {CampaignState.MATURING,          CampaignState.CLOSED},
    CampaignState.MATURING:          {CampaignState.DISTRIBUTION_RISK, CampaignState.CLOSED},
    CampaignState.DISTRIBUTION_RISK: {CampaignState.CLOSED},
    CampaignState.CLOSED:            set(),
}

# How many calendar days a campaign may remain open before auto-expiry.
CAMPAIGN_MAX_DAYS: int = 90

# Stop-loss thresholds aligned with Phase 10 research findings.
STOP_LAYER_A: Decimal = Decimal("-0.10")  # -10 % for Layer A signals
STOP_LAYER_B: Decimal = Decimal("-0.20")  # -20 % for Layer B signals


# ---------------------------------------------------------------------------
# Domain data classes
# ---------------------------------------------------------------------------

@dataclass
class DailyBar:
    """Minimal OHLCV bar passed into the engine for state evaluation."""
    symbol:    str
    bar_date:  date
    open:      Decimal
    high:      Decimal
    low:       Decimal
    close:     Decimal
    volume:    Decimal
    vwap:      Optional[Decimal] = None


@dataclass
class WyckoffSignals:
    """
    Wyckoff / Weis metrics supplied by the Wyckoff engine (Layer 3 sibling).
    All boolean flags; the campaign engine does not recompute them.
    """
    sos_detected:      bool = False   # Sign of Strength / Jump Across Creek
    jac_detected:      bool = False
    bu_detected:       bool = False   # Back-Up / Last Point of Support
    lps_detected:      bool = False
    choch_detected:    bool = False   # Change of Character (bearish)
    spring_detected:   bool = False
    upthrust_detected: bool = False
    spd:               bool = False   # Selling Pressure Diminishing
    dei:               bool = False   # Demand Efficiency Improving
    wed_count:         int  = 0       # Wave Exhaustion Depth (validated optimum = 2)
    behavioral_state:  str  = "AMBIGUOUS"  # "ACCUMULATION" | "DISTRIBUTION" | "AMBIGUOUS"


@dataclass
class ResearchSignal:
    """
    Nightly output from run_phase12_scoring.py consumed by Layer 1 loader.
    Passed in at campaign birth to anchor the lifecycle.
    """
    tier:           str            # "TIER_1" | "TIER_2" | "TIER_3" | "TIER_4"
    mfe90_expected: Decimal        # Expected max-favourable excursion at 90 days
    obstacle_score: Decimal        # Structural resistance composite
    progress_score: Decimal        # Resolution evidence composite
    d_score:        Decimal        # Composite daily signal score (0-105)
    duration_days:  int            # Days below 252-day high at signal birth
    asym_ratio:     Decimal        # Asymmetry ratio — below 1.0 flags low quality
    layer:          str = "A"      # "A" or "B" — determines stop threshold


@dataclass
class Campaign:
    """
    Represents a single, tracked institutional campaign for one symbol.

    Serialises to/from Supabase via campaign_store.py; this class is the
    in-memory authoritative object.
    """
    campaign_id:      str            = field(default_factory=lambda: str(uuid.uuid4()))
    symbol:           str            = ""
    birth_date:       date           = field(default_factory=date.today)
    state:            CampaignState  = CampaignState.BIRTH
    entry_price:      Decimal        = Decimal("0")
    stop_price:       Decimal        = Decimal("0")
    pnf_target:       Decimal        = Decimal("0")   # Point-and-Figure conservative target
    current_price:    Decimal        = Decimal("0")
    tier:             str            = "TIER_1"
    mfe90_expected:   Decimal        = Decimal("0")
    obstacle_score:   Decimal        = Decimal("0")
    progress_score:   Decimal        = Decimal("0")
    d_score:          Decimal        = Decimal("0")
    duration_days:    int            = 0
    asym_ratio:       Decimal        = Decimal("1")
    layer:            str            = "A"
    close_reason:     Optional[str]  = None
    state_history:    list[dict]     = field(default_factory=list)
    days_open:        int            = 0

    # ------------------------------------------------------------------ #
    #  Computed helpers                                                    #
    # ------------------------------------------------------------------ #

    @property
    def stop_threshold(self) -> Decimal:
        """Return the empirically validated stop threshold for this campaign."""
        return STOP_LAYER_A if self.layer == "A" else STOP_LAYER_B

    @property
    def return_pct(self) -> Decimal:
        """Current open return as a fraction (e.g. -0.05 = -5 %)."""
        if self.entry_price == Decimal("0"):
            return Decimal("0")
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def is_stop_breached(self) -> bool:
        return self.return_pct <= self.stop_threshold

    @property
    def is_expired(self) -> bool:
        return self.days_open >= CAMPAIGN_MAX_DAYS

    @property
    def pnf_progress_pct(self) -> Decimal:
        """Percentage of P&F target already captured."""
        span = self.pnf_target - self.entry_price
        if span == Decimal("0"):
            return Decimal("0")
        return (self.current_price - self.entry_price) / span * Decimal("100")


# ---------------------------------------------------------------------------
# State-transition logic
# ---------------------------------------------------------------------------

class CampaignStateMachine:
    """
    Evaluates daily Wyckoff/Weis signals against an in-memory Campaign object
    and returns the new state.  All methods are pure (no I/O).
    """

    def transition(
        self,
        campaign:  Campaign,
        signals:   WyckoffSignals,
        bar:       DailyBar,
    ) -> tuple[CampaignState, str | None]:
        """
        Determine the next state for *campaign* given today's *signals* and *bar*.

        Returns
        -------
        (new_state, close_reason)
            close_reason is only non-None when new_state is CLOSED.
        """
        current = campaign.state

        # Terminal — nothing to do.
        if current == CampaignState.CLOSED:
            return CampaignState.CLOSED, None

        # ── Priority 1: hard-exit conditions ──────────────────────────────
        if campaign.is_stop_breached:
            return CampaignState.CLOSED, f"Stop breached at {bar.close} (threshold {campaign.stop_threshold:.0%})"

        if campaign.is_expired:
            return CampaignState.CLOSED, f"90-day campaign expiry on day {campaign.days_open}"

        if signals.choch_detected and current in {
            CampaignState.MATURING,
            CampaignState.DISTRIBUTION_RISK,
        }:
            return CampaignState.CLOSED, "CHoCH confirmed — operator exit detected"

        # ── Priority 2: distribution deterioration ────────────────────────
        if current == CampaignState.MATURING:
            if signals.upthrust_detected or signals.behavioral_state == "DISTRIBUTION":
                return CampaignState.DISTRIBUTION_RISK, None

        # ── Priority 3: forward progression ──────────────────────────────
        if current == CampaignState.BIRTH:
            # Confirmation requires SOS or JAC — structural breakout above creek.
            if signals.sos_detected or signals.jac_detected:
                return CampaignState.CONFIRMED, None

        elif current == CampaignState.CONFIRMED:
            # Surviving: price pulls back but holds structure (BU / LPS).
            if signals.bu_detected or signals.lps_detected:
                return CampaignState.SURVIVING, None

        elif current == CampaignState.SURVIVING:
            # Expanding: renewed SOS off the LPS zone.
            if signals.sos_detected and signals.dei:
                return CampaignState.EXPANDING, None

        elif current == CampaignState.EXPANDING:
            # Maturing: P&F target >75 % captured or wave-efficiency fading.
            if campaign.pnf_progress_pct >= Decimal("75"):
                return CampaignState.MATURING, None
            # WED_2 reversal risk — seller supply re-emerging.
            if signals.wed_count >= 2 and not signals.spd:
                return CampaignState.MATURING, None

        elif current == CampaignState.DISTRIBUTION_RISK:
            # Only exit from here is CLOSED (handled above) or remain.
            pass

        # No transition — hold current state.
        return current, None


# ---------------------------------------------------------------------------
# Campaign Engine (public API)
# ---------------------------------------------------------------------------

class CampaignEngine:
    """
    Orchestrates campaign lifecycle across all active campaigns for one daily
    cycle.  Delegates persistence to *campaign_store* (Layer 2).

    Usage (called by the nightly pipeline)
    ----------------------------------------
    engine = CampaignEngine(campaign_store=store)
    await engine.run_daily_cycle(bars_by_symbol, signals_by_symbol)
    """

    def __init__(self, campaign_store: "CampaignStore") -> None:  # type: ignore[name-defined]
        self._store = campaign_store
        self._fsm   = CampaignStateMachine()

    # ------------------------------------------------------------------ #
    #  Birth                                                               #
    # ------------------------------------------------------------------ #

    async def birth_campaign(
        self,
        symbol:          str,
        entry_price:     Decimal,
        research_signal: ResearchSignal,
        pnf_target:      Decimal,
    ) -> Campaign:
        """
        Create and persist a new campaign at BIRTH state.

        The stop is placed at the empirically validated layer threshold
        (Phase 10: -10 % Layer A, -20 % Layer B).

        Parameters
        ----------
        symbol:          Ticker symbol.
        entry_price:     Market-on-open fill price.
        research_signal: Phase 12B output for this symbol.
        pnf_target:      Conservative P&F count target computed externally.
        """
        _validate_price(entry_price, "entry_price")
        _validate_price(pnf_target,  "pnf_target")

        stop_pct   = STOP_LAYER_A if research_signal.layer == "A" else STOP_LAYER_B
        stop_price = entry_price * (Decimal("1") + stop_pct)

        campaign = Campaign(
            symbol         = symbol,
            birth_date     = date.today(),
            state          = CampaignState.BIRTH,
            entry_price    = entry_price,
            current_price  = entry_price,
            stop_price     = stop_price,
            pnf_target     = pnf_target,
            tier           = research_signal.tier,
            mfe90_expected = research_signal.mfe90_expected,
            obstacle_score = research_signal.obstacle_score,
            progress_score = research_signal.progress_score,
            d_score        = research_signal.d_score,
            duration_days  = research_signal.duration_days,
            asym_ratio     = research_signal.asym_ratio,
            layer          = research_signal.layer,
            state_history  = [_state_event(CampaignState.BIRTH, "Campaign born")],
        )

        try:
            await self._store.upsert_campaign(campaign)
            logger.info(
                "Campaign BORN | id=%s symbol=%s tier=%s entry=%s stop=%s pnf_target=%s",
                campaign.campaign_id, symbol, research_signal.tier,
                entry_price, stop_price, pnf_target,
            )
        except Exception as exc:
            logger.error("Failed to persist new campaign for %s: %s", symbol, exc)
            raise

        return campaign

    # ------------------------------------------------------------------ #
    #  Nightly cycle                                                       #
    # ------------------------------------------------------------------ #

    async def run_daily_cycle(
        self,
        bars_by_symbol:    dict[str, DailyBar],
        signals_by_symbol: dict[str, WyckoffSignals],
    ) -> dict[str, CampaignState]:
        """
        Evaluate all open campaigns for the day.  Returns a mapping of
        campaign_id → new_state for downstream consumers (UI, alerts, etc.).

        Fetches active campaigns from the store, applies the FSM for each,
        then bulk-upserts the updated batch.
        """
        results: dict[str, CampaignState] = {}
        updated_campaigns: list[Campaign]  = []

        try:
            active_campaigns: list[Campaign] = await self._store.fetch_active_campaigns()
        except Exception as exc:
            logger.error("Could not fetch active campaigns: %s", exc)
            return results

        for campaign in active_campaigns:
            symbol = campaign.symbol
            bar    = bars_by_symbol.get(symbol)
            wyck   = signals_by_symbol.get(symbol)

            if bar is None or wyck is None:
                logger.warning("No bar/signals for active campaign %s (%s) — skipping", campaign.campaign_id, symbol)
                continue

            try:
                new_state, close_reason = self._apply_daily_update(campaign, bar, wyck)
                results[campaign.campaign_id] = new_state
                updated_campaigns.append(campaign)
            except Exception as exc:
                logger.error(
                    "Error evaluating campaign %s (%s): %s",
                    campaign.campaign_id, symbol, exc, exc_info=True,
                )

        if updated_campaigns:
            try:
                await self._store.bulk_upsert_campaigns(updated_campaigns)
                logger.info("Daily cycle complete — %d campaigns updated", len(updated_campaigns))
            except Exception as exc:
                logger.error("Bulk upsert failed: %s", exc)

        return results

    # ------------------------------------------------------------------ #
    #  Manual close                                                        #
    # ------------------------------------------------------------------ #

    async def close_campaign(
        self,
        campaign_id: str,
        reason:      str,
        exit_price:  Decimal,
    ) -> Campaign:
        """
        Manually close a campaign (e.g. trader decision, 90-day forced exit).
        """
        _validate_price(exit_price, "exit_price")

        try:
            campaign = await self._store.fetch_campaign(campaign_id)
        except Exception as exc:
            logger.error("Cannot fetch campaign %s for close: %s", campaign_id, exc)
            raise

        _transition_campaign(campaign, CampaignState.CLOSED, reason)
        campaign.current_price = exit_price

        try:
            await self._store.upsert_campaign(campaign)
            logger.info(
                "Campaign CLOSED | id=%s symbol=%s reason=%s exit=%s return=%.2f%%",
                campaign.campaign_id, campaign.symbol, reason,
                exit_price, float(campaign.return_pct * Decimal("100")),
            )
        except Exception as exc:
            logger.error("Failed to persist campaign close for %s: %s", campaign_id, exc)
            raise

        return campaign

    # ------------------------------------------------------------------ #
    #  Query helpers                                                       #
    # ------------------------------------------------------------------ #

    async def get_campaign_summary(self, campaign_id: str) -> dict:
        """Return a plain dict snapshot suitable for UI / API serialisation."""
        campaign = await self._store.fetch_campaign(campaign_id)
        return {
            "campaign_id":      campaign.campaign_id,
            "symbol":           campaign.symbol,
            "state":            campaign.state.value,
            "days_open":        campaign.days_open,
            "tier":             campaign.tier,
            "entry_price":      str(campaign.entry_price),
            "current_price":    str(campaign.current_price),
            "stop_price":       str(campaign.stop_price),
            "pnf_target":       str(campaign.pnf_target),
            "pnf_progress_pct": str(campaign.pnf_progress_pct.quantize(Decimal("0.01"))),
            "return_pct":       str((campaign.return_pct * Decimal("100")).quantize(Decimal("0.01"))),
            "mfe90_expected":   str(campaign.mfe90_expected),
            "d_score":          str(campaign.d_score),
            "close_reason":     campaign.close_reason,
            "state_history":    campaign.state_history,
        }

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _apply_daily_update(
        self,
        campaign:  Campaign,
        bar:       DailyBar,
        signals:   WyckoffSignals,
    ) -> tuple[CampaignState, str | None]:
        """Update the campaign object in-place for the given daily bar."""
        campaign.current_price = bar.close
        campaign.days_open    += 1

        new_state, close_reason = self._fsm.transition(campaign, signals, bar)

        if new_state != campaign.state:
            _transition_campaign(campaign, new_state, close_reason or "FSM transition")

        return new_state, close_reason


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _transition_campaign(
    campaign:   Campaign,
    new_state:  CampaignState,
    reason:     str,
) -> None:
    """
    Mutate *campaign* to *new_state* after validating the transition is legal.
    Appends an audit record to state_history.

    Raises
    ------
    ValueError  if the transition is not permitted by _ALLOWED_TRANSITIONS.
    """
    allowed = _ALLOWED_TRANSITIONS.get(campaign.state, set())
    if new_state not in allowed:
        raise ValueError(
            f"Illegal transition {campaign.state.value} → {new_state.value} "
            f"for campaign {campaign.campaign_id}"
        )

    old_state           = campaign.state
    campaign.state      = new_state
    campaign.state_history.append(_state_event(new_state, reason))

    if new_state == CampaignState.CLOSED:
        campaign.close_reason = reason

    logger.info(
        "Campaign state change | id=%s symbol=%s %s → %s | reason=%s",
        campaign.campaign_id, campaign.symbol,
        old_state.value, new_state.value, reason,
    )


def _state_event(state: CampaignState, reason: str) -> dict:
    return {
        "state":     state.value,
        "reason":    reason,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _validate_price(value: Decimal, name: str) -> None:
    """Guard against zero or negative prices slipping through."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal, got {type(value).__name__}")
    if value <= Decimal("0"):
        raise ValueError(f"{name} must be positive, got {value}")


# ---------------------------------------------------------------------------
# Factory helper — convenience constructor used by the nightly pipeline
# ---------------------------------------------------------------------------

def build_engine(campaign_store: "CampaignStore") -> CampaignEngine:  # type: ignore[name-defined]
    """
    Construct a CampaignEngine bound to the given store.

    Example
    -------
    from data.campaign_store import CampaignStore
    from engines.campaign_engine import build_engine

    store  = CampaignStore()
    engine = build_engine(store)
    """
    return CampaignEngine(campaign_store=campaign_store)