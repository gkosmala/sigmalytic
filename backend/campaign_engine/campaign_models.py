"""
Sigmalytic V2 — Campaign Models
Phase 16A

Purpose
-------
This file defines the core campaign-centric domain model for Sigmalytic V2.

The key architectural rule is:

    A symbol is permanent.
    A campaign is temporary.
    A timeframe is the user's execution lens.

These models are intentionally pure Python. They do not depend on Supabase,
FastAPI, Redis, Alpaca, or any external service. That keeps the domain layer
stable and testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class CampaignDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    AMBIGUOUS = "AMBIGUOUS"


class CampaignState(str, Enum):
    BIRTH = "BIRTH"
    CONFIRMED = "CONFIRMED"
    SURVIVING = "SURVIVING"
    EXPANDING = "EXPANDING"
    MATURING = "MATURING"
    DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class CampaignTier(str, Enum):
    TIER_1_INSTITUTIONAL_ALPHA = "TIER_1_INSTITUTIONAL_ALPHA"
    TIER_2_STABLE_RETENTION = "TIER_2_STABLE_RETENTION"
    TIER_3_LIQUIDATION_VOID = "TIER_3_LIQUIDATION_VOID"
    UNRANKED = "UNRANKED"


class ExecutionAction(str, Enum):
    HOLD_WATCH = "HOLD_WATCH"
    WATCH = "WATCH"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    EXIT = "EXIT"
    LOCKOUT = "LOCKOUT"


class Timeframe(str, Enum):
    TICK = "TICK"
    ONE_MIN = "1MIN"
    FIVE_MIN = "5MIN"
    HOURLY = "HOURLY"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


# ---------------------------------------------------------------------------
# NORMALIZATION HELPERS
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_symbol(symbol: str) -> str:
    if not symbol or not str(symbol).strip():
        raise ValueError("symbol is required")
    return str(symbol).strip().upper()


def normalize_timeframe(timeframe: str) -> str:
    if not timeframe or not str(timeframe).strip():
        raise ValueError("timeframe is required")

    tf = str(timeframe).strip().upper().replace("-", "").replace(" ", "")

    aliases = {
        "T": Timeframe.TICK.value,
        "TICK": Timeframe.TICK.value,
        "1M": Timeframe.ONE_MIN.value,
        "1MIN": Timeframe.ONE_MIN.value,
        "1MINUTE": Timeframe.ONE_MIN.value,
        "5M": Timeframe.FIVE_MIN.value,
        "5MIN": Timeframe.FIVE_MIN.value,
        "5MINUTE": Timeframe.FIVE_MIN.value,
        "H": Timeframe.HOURLY.value,
        "1H": Timeframe.HOURLY.value,
        "HOURLY": Timeframe.HOURLY.value,
        "D": Timeframe.DAILY.value,
        "1D": Timeframe.DAILY.value,
        "DAILY": Timeframe.DAILY.value,
        "W": Timeframe.WEEKLY.value,
        "1W": Timeframe.WEEKLY.value,
        "WEEKLY": Timeframe.WEEKLY.value,
        "M": Timeframe.MONTHLY.value,
        "1MO": Timeframe.MONTHLY.value,
        "MONTHLY": Timeframe.MONTHLY.value,
    }

    if tf not in aliases:
        raise ValueError(f"unsupported timeframe: {timeframe}")

    return aliases[tf]


# ---------------------------------------------------------------------------
# DOMAIN OBJECTS
# ---------------------------------------------------------------------------


@dataclass
class WyckoffAnchors:
    """
    Structural range anchors for a campaign.

    SC = Selling Climax low
    AR = Automatic Rally high
    ST = Secondary Test low

    These are not decorative chart labels. They are the mathematical boundaries
    used for readiness, invalidation, survival, target projection, and decay.
    """

    sc_low: Optional[float] = None
    ar_high: Optional[float] = None
    st_low: Optional[float] = None
    spring_low: Optional[float] = None
    upthrust_high: Optional[float] = None
    last_price: Optional[float] = None
    invalidation_level: Optional[float] = None

    def range_width(self) -> Optional[float]:
        if self.sc_low is None or self.ar_high is None:
            return None
        width = self.ar_high - self.sc_low
        return width if width > 0 else None

    def is_valid_range(self) -> bool:
        return self.range_width() is not None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PointFigureTargets:
    """
    Point & Figure cause/effect target layer.

    Conservative and aggressive targets allow the system to distinguish
    between valid campaign birth and attractive remaining opportunity.
    """

    box_size: Optional[float] = None
    reversal_count: int = 3
    horizontal_count: Optional[int] = None
    conservative_target: Optional[float] = None
    aggressive_target: Optional[float] = None
    remaining_opportunity_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WeisWaveMetrics:
    """
    Weis / Renko effort-versus-result layer.

    WWE = Weis Wave Efficiency.
    SPD = Selling Pressure Diminishing.
    DEI = Demand Efficiency Improving.
    WED = Wave Exhaustion Depth.
    """

    current_up_efficiency: float = 0.0
    prior_up_efficiency: float = 0.0
    current_down_efficiency: float = 0.0
    prior_down_efficiency: float = 0.0
    wwe_ratio: float = 0.0
    spd: bool = False
    dei: bool = False
    wed_depth: int = 0
    sot_alert: bool = False
    classification: str = "AMBIGUOUS"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CampaignScores:
    """
    Master score layer.

    These are the values used by the dashboard, API, ranking engine, and
    commercial subscription outputs.
    """

    mta_score: float = 0.0
    ods_score: float = 0.0
    wwe_ratio: float = 0.0
    csd_score: float = 0.0
    ucr_score: float = 0.0
    tier: CampaignTier = CampaignTier.UNRANKED
    execution_action: ExecutionAction = ExecutionAction.HOLD_WATCH

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["tier"] = self.tier.value
        payload["execution_action"] = self.execution_action.value
        return payload


@dataclass
class CampaignStateEvent:
    """
    Audit trail event.

    Every state transition should be recorded. This is essential for commercial
    trust, debugging, compliance-style reconstruction, and institutional review.
    """

    from_state: Optional[CampaignState]
    to_state: CampaignState
    reason: str
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class OperationalCampaign:
    """
    The central V2 campaign object.

    This object is what the rest of the system should pass around. It is the
    bridge between Wyckoff/Livermore/Weis doctrine and software execution.
    """

    symbol: str
    timeframe: str
    direction: CampaignDirection = CampaignDirection.AMBIGUOUS
    state: CampaignState = CampaignState.BIRTH
    campaign_id: str = field(default_factory=lambda: str(uuid4()))

    anchors: WyckoffAnchors = field(default_factory=WyckoffAnchors)
    pnf: PointFigureTargets = field(default_factory=PointFigureTargets)
    wave: WeisWaveMetrics = field(default_factory=WeisWaveMetrics)
    scores: CampaignScores = field(default_factory=CampaignScores)

    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    closed_at: Optional[datetime] = None
    state_events: list[CampaignStateEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        self.timeframe = normalize_timeframe(self.timeframe)

    def is_active(self) -> bool:
        return self.state not in {CampaignState.CLOSED, CampaignState.FAILED}

    def mark_updated(self) -> None:
        self.updated_at = utc_now()

    def transition_to(self, new_state: CampaignState, reason: str) -> None:
        if not isinstance(new_state, CampaignState):
            new_state = CampaignState(str(new_state))

        old_state = self.state
        if old_state == new_state:
            return

        self.state = new_state
        self.mark_updated()

        if new_state in {CampaignState.CLOSED, CampaignState.FAILED}:
            self.closed_at = utc_now()

        self.state_events.append(
            CampaignStateEvent(
                from_state=old_state,
                to_state=new_state,
                reason=reason,
            )
        )

    def update_scores(
        self,
        mta_score: Optional[float] = None,
        ods_score: Optional[float] = None,
        wwe_ratio: Optional[float] = None,
        csd_score: Optional[float] = None,
        ucr_score: Optional[float] = None,
        tier: Optional[CampaignTier] = None,
        execution_action: Optional[ExecutionAction] = None,
    ) -> None:
        if mta_score is not None:
            self.scores.mta_score = float(mta_score)
        if ods_score is not None:
            self.scores.ods_score = float(ods_score)
        if wwe_ratio is not None:
            self.scores.wwe_ratio = float(wwe_ratio)
        if csd_score is not None:
            self.scores.csd_score = float(csd_score)
        if ucr_score is not None:
            self.scores.ucr_score = float(ucr_score)
        if tier is not None:
            self.scores.tier = tier if isinstance(tier, CampaignTier) else CampaignTier(str(tier))
        if execution_action is not None:
            self.scores.execution_action = (
                execution_action
                if isinstance(execution_action, ExecutionAction)
                else ExecutionAction(str(execution_action))
            )

        self.mark_updated()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction.value,
            "state": self.state.value,
            "anchors": self.anchors.to_dict(),
            "pnf": self.pnf.to_dict(),
            "wave": self.wave.to_dict(),
            "scores": self.scores.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "state_events": [event.to_dict() for event in self.state_events],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OperationalCampaign":
        campaign = cls(
            campaign_id=payload.get("campaign_id") or str(uuid4()),
            symbol=payload["symbol"],
            timeframe=payload["timeframe"],
            direction=CampaignDirection(payload.get("direction", CampaignDirection.AMBIGUOUS.value)),
            state=CampaignState(payload.get("state", CampaignState.BIRTH.value)),
        )

        anchors = payload.get("anchors") or {}
        campaign.anchors = WyckoffAnchors(**anchors)

        pnf = payload.get("pnf") or {}
        campaign.pnf = PointFigureTargets(**pnf)

        wave = payload.get("wave") or {}
        campaign.wave = WeisWaveMetrics(**wave)

        scores = payload.get("scores") or {}
        if scores:
            campaign.scores = CampaignScores(
                mta_score=float(scores.get("mta_score", 0.0)),
                ods_score=float(scores.get("ods_score", 0.0)),
                wwe_ratio=float(scores.get("wwe_ratio", 0.0)),
                csd_score=float(scores.get("csd_score", 0.0)),
                ucr_score=float(scores.get("ucr_score", 0.0)),
                tier=CampaignTier(scores.get("tier", CampaignTier.UNRANKED.value)),
                execution_action=ExecutionAction(
                    scores.get("execution_action", ExecutionAction.HOLD_WATCH.value)
                ),
            )

        return campaign
