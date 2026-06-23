"""
SAVE AS:
backend/campaign_engine/campaign_state_engine.py

Sigmalytic V2
Survival-Aware Campaign State Engine

Purpose:
Advance campaign lifecycle states only when BOTH birth evidence and survival
evidence justify advancement.

Core rule:
Birth alone does not confirm a campaign.
A campaign moves from BIRTH to CONFIRMED only after survival is confirmed.

Consumes:
- Signal Birth Engine
- Master Survival Index
- Existing campaign record fields when bars are unavailable

States:
- NO_CAMPAIGN
- BIRTH
- CONFIRMED
- SURVIVING
- EXPANDING
- MATURING
- DISTRIBUTION_RISK
- CLOSED
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import pandas as pd


try:
    from backend.research_engine.signal_birth_engine import SignalBirthEngine
except Exception:
    SignalBirthEngine = None


try:
    from backend.research_engine.master_survival_index import MasterSurvivalIndexEngine
except Exception:
    MasterSurvivalIndexEngine = None


class WyckoffSignals:
    """
    Backward-compatible signal container.

    Existing pipeline passes legacy keyword names such as:
    sos_detected, spring_detected, absorption_detected.

    This class accepts any keyword argument and exposes it as an attribute.
    """

    def __init__(self, **kwargs):
        self.sos_detected = kwargs.get("sos_detected", False)
        self.spring_detected = kwargs.get("spring_detected", False)
        self.absorption_detected = kwargs.get("absorption_detected", False)
        self.stopping_climax_detected = kwargs.get("stopping_climax_detected", False)
        self.supply_absorption_detected = kwargs.get("supply_absorption_detected", False)
        self.sign_of_strength_detected = kwargs.get("sign_of_strength_detected", False)

        self.stopping_climax = kwargs.get("stopping_climax", 0.0)
        self.supply_absorption = kwargs.get("supply_absorption", 0.0)
        self.spring = kwargs.get("spring", 0.0)
        self.sign_of_strength = kwargs.get("sign_of_strength", 0.0)
        self.meaningful_resistance = kwargs.get("meaningful_resistance", 0.0)
        self.behavioral_resolution = kwargs.get("behavioral_resolution", 0.0)
        self.survival_score = kwargs.get("survival_score", 0.0)
        self.wyckoff_score = kwargs.get("wyckoff_score", 0.0)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)




class CampaignTransition:
    """
    Backward-compatible transition object for nightly_campaign_pipeline.py.

    The existing pipeline expects attribute access:
        transition.old_state.value
        transition.new_state.value
        transition.changed
        transition.reason
        transition.confidence
    """

    def __init__(self, **kwargs):
        raw_old = kwargs.get(
            "old_state",
            kwargs.get("previous_state", kwargs.get("from_state", "NO_CAMPAIGN")),
        )
        raw_new = kwargs.get(
            "new_state",
            kwargs.get("state", kwargs.get("to_state", "NO_CAMPAIGN")),
        )

        self.symbol = kwargs.get("symbol", "")
        self.old_state = CampaignStateEngine._normalize_state(raw_old)
        self.previous_state = self.old_state
        self.new_state = CampaignStateEngine._normalize_state(raw_new)

        self.transition = kwargs.get("transition", "UNCHANGED")
        self.transition_score = kwargs.get("transition_score", 0.0)
        self.advance_allowed = kwargs.get("advance_allowed", False)
        self.failure_risk = kwargs.get("failure_risk", False)

        self.reason = kwargs.get(
            "reason",
            kwargs.get("explanation", kwargs.get("transition_reason", "")),
        )
        self.explanation = kwargs.get("explanation", self.reason)

        try:
            self.confidence = float(kwargs.get("confidence", kwargs.get("transition_score", 0.0)))
        except Exception:
            self.confidence = 0.0

        self.changed = kwargs.get(
            "changed",
            self.old_state != self.new_state,
        )

        self.as_of = kwargs.get("as_of", datetime.now(timezone.utc).isoformat())

        for key, value in kwargs.items():
            if key in {
                "old_state",
                "previous_state",
                "from_state",
                "new_state",
                "state",
                "to_state",
                "changed",
                "reason",
                "confidence",
            }:
                continue
            setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        for key in ("old_state", "previous_state", "new_state"):
            value = data.get(key)
            if hasattr(value, "value"):
                data[key] = value.value
        return data

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)




class CampaignState(str, Enum):
    NO_CAMPAIGN = "NO_CAMPAIGN"
    BIRTH = "BIRTH"
    CONFIRMED = "CONFIRMED"
    SURVIVING = "SURVIVING"
    EXPANDING = "EXPANDING"
    MATURING = "MATURING"
    DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
    CLOSED = "CLOSED"


_STATE_RANK = {
    CampaignState.NO_CAMPAIGN: 0,
    CampaignState.BIRTH: 1,
    CampaignState.CONFIRMED: 2,
    CampaignState.SURVIVING: 3,
    CampaignState.EXPANDING: 4,
    CampaignState.MATURING: 5,
    CampaignState.DISTRIBUTION_RISK: 6,
    CampaignState.CLOSED: 7,
}


@dataclass
class CampaignStateVerdict:
    symbol: str
    previous_state: str
    new_state: str
    transition: str

    birth_score: float
    birth_state: str
    birth_eligible: bool

    master_survival_score: float
    survival_state: str
    survival_grade: str
    survival_confirmed: bool

    transition_score: float
    advance_allowed: bool
    failure_risk: bool

    explanation: str
    birth_details: Dict[str, Any]
    survival_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CampaignStateEngine:
    """
    Survival-aware lifecycle engine.

    Decision rules:
    - BIRTH can occur from strong birth evidence.
    - CONFIRMED requires birth evidence plus survival confirmation.
    - SURVIVING requires survival score >= 70.
    - EXPANDING requires survival score >= 75 and birth/campaign evidence intact.
    - MATURING is reserved for strong survival but weakening birth/new-campaign edge.
    - DISTRIBUTION_RISK appears when survival fails after a prior confirmed state.
    - CLOSED is reserved for explicit closure/failure records.
    """

    def __init__(self):
        pass

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _normalize_state(value: Any) -> CampaignState:
        if value is None:
            return CampaignState.NO_CAMPAIGN

        text = str(value).upper().strip()

        for state in CampaignState:
            if text == state.value:
                return state

        return CampaignState.NO_CAMPAIGN

    def _run_birth(
        self,
        df: Optional[pd.DataFrame],
        symbol: str,
        sister_df: Optional[pd.DataFrame] = None,
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = record or {}

        if df is not None and SignalBirthEngine is not None:
            try:
                return SignalBirthEngine().evaluate_bars(
                    df,
                    sister_df=sister_df,
                    symbol=symbol,
                )
            except Exception as exc:
                return {
                    "birth_score": 0.0,
                    "birth_state": "BIRTH_ENGINE_ERROR",
                    "birth_eligible": False,
                    "error": str(exc),
                }

        return {
            "birth_score": self._safe_float(record.get("birth_score")),
            "birth_state": str(record.get("birth_state", "UNKNOWN")),
            "birth_eligible": bool(record.get("birth_eligible", False)),
        }

    def _run_survival(
        self,
        df: Optional[pd.DataFrame],
        symbol: str,
        sister_df: Optional[pd.DataFrame] = None,
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = record or {}

        if df is not None and MasterSurvivalIndexEngine is not None:
            try:
                return MasterSurvivalIndexEngine().evaluate_bars(
                    df,
                    symbol=symbol,
                    sister_df=sister_df,
                )
            except Exception as exc:
                return {
                    "master_survival_score": 0.0,
                    "survival_state": "SURVIVAL_ENGINE_ERROR",
                    "survival_grade": "F",
                    "survival_confirmed": False,
                    "error": str(exc),
                }

        return {
            "master_survival_score": self._safe_float(
                record.get("master_survival_score")
                or record.get("survival_score")
            ),
            "survival_state": str(record.get("survival_state", "UNKNOWN")),
            "survival_grade": str(record.get("survival_grade", "F")),
            "survival_confirmed": bool(record.get("survival_confirmed", False)),
        }

    def determine_state(
        self,
        previous_state: CampaignState,
        birth: Dict[str, Any],
        survival: Dict[str, Any],
        record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = record or {}

        birth_score = self._safe_float(birth.get("birth_score"))
        birth_state = str(birth.get("birth_state", "UNKNOWN"))

        survival_score = self._safe_float(survival.get("master_survival_score"))
        survival_state = str(survival.get("survival_state", "UNKNOWN"))

        # Do not let stale/missing boolean flags veto valid numeric evidence.
        # Discovery may store schema-safe numeric evidence without persisting
        # birth_eligible or survival_confirmed as physical DB columns.
        birth_eligible = bool(birth.get("birth_eligible", False)) or birth_score >= 55.0
        survival_confirmed = bool(survival.get("survival_confirmed", False)) or survival_score >= 50.0

        explicit_closed = bool(record.get("closed", False) or record.get("is_closed", False))
        explicit_distribution = bool(
            record.get("distribution_risk", False)
            or record.get("decay_state") in {"EXIT_CANDIDATE", "WEAKENING"}
        )

        transition_score = round((birth_score * 0.45) + (survival_score * 0.55), 2)

        failure_risk = False
        advance_allowed = False

        if explicit_closed:
            return {
                "state": CampaignState.CLOSED,
                "transition_score": transition_score,
                "advance_allowed": False,
                "failure_risk": True,
                "reason": "Explicit closure flag present.",
            }

        if explicit_distribution:
            return {
                "state": CampaignState.DISTRIBUTION_RISK,
                "transition_score": transition_score,
                "advance_allowed": False,
                "failure_risk": True,
                "reason": "Distribution/decay risk flag present.",
            }

        # No birth evidence.
        if birth_score < 55 and not birth_eligible:
            if _STATE_RANK.get(previous_state, 0) >= _STATE_RANK[CampaignState.CONFIRMED]:
                failure_risk = survival_score < 55
                if failure_risk:
                    return {
                        "state": CampaignState.DISTRIBUTION_RISK,
                        "transition_score": transition_score,
                        "advance_allowed": False,
                        "failure_risk": True,
                        "reason": "Prior campaign lost birth edge and survival weakened.",
                    }

            return {
                "state": CampaignState.NO_CAMPAIGN if previous_state == CampaignState.NO_CAMPAIGN else previous_state,
                "transition_score": transition_score,
                "advance_allowed": False,
                "failure_risk": False,
                "reason": "No current birth evidence.",
            }

        # Birth exists but survival not confirmed.
        if birth_score >= 55 and not survival_confirmed:
            if survival_score < 50 and previous_state in {
                CampaignState.CONFIRMED,
                CampaignState.SURVIVING,
                CampaignState.EXPANDING,
                CampaignState.MATURING,
            }:
                return {
                    "state": CampaignState.DISTRIBUTION_RISK,
                    "transition_score": transition_score,
                    "advance_allowed": False,
                    "failure_risk": True,
                    "reason": "Birth evidence exists but survival failed after prior confirmation.",
                }

            return {
                "state": CampaignState.BIRTH,
                "transition_score": transition_score,
                "advance_allowed": previous_state == CampaignState.NO_CAMPAIGN,
                "failure_risk": survival_score < 50,
                "reason": "Birth evidence present; survival not yet confirmed.",
            }

        # Survival confirmed.
        if birth_score >= 85 and survival_score >= 80:
            return {
                "state": CampaignState.EXPANDING,
                "transition_score": transition_score,
                "advance_allowed": True,
                "failure_risk": False,
                "reason": "Strong birth evidence and strong survival.",
            }

        if birth_score >= 70 and survival_score >= 75:
            return {
                "state": CampaignState.SURVIVING,
                "transition_score": transition_score,
                "advance_allowed": True,
                "failure_risk": False,
                "reason": "Early campaign with strong survival confirmation.",
            }

        if birth_score >= 55 and survival_score >= 70:
            return {
                "state": CampaignState.CONFIRMED,
                "transition_score": transition_score,
                "advance_allowed": True,
                "failure_risk": False,
                "reason": "Birth evidence survived confirmation threshold.",
            }

        if survival_score >= 80 and birth_score < 55:
            return {
                "state": CampaignState.MATURING,
                "transition_score": transition_score,
                "advance_allowed": True,
                "failure_risk": False,
                "reason": "Strong survival remains but new birth edge has faded.",
            }

        return {
            "state": CampaignState.BIRTH,
            "transition_score": transition_score,
            "advance_allowed": False,
            "failure_risk": survival_score < 50,
            "reason": "Default holding at birth pending cleaner survival confirmation.",
        }

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper()
        previous_state = self._normalize_state(
            record.get("state")
            or record.get("campaign_state")
            or record.get("previous_state")
        )

        bars = record.get("bars")
        sister_bars = record.get("sister_bars") or record.get("sector_bars")

        df = pd.DataFrame(bars) if bars else None
        sister_df = pd.DataFrame(sister_bars) if sister_bars else None

        birth = self._run_birth(
            df,
            symbol=symbol,
            sister_df=sister_df,
            record=record,
        )

        survival = self._run_survival(
            df,
            symbol=symbol,
            sister_df=sister_df,
            record=record,
        )

        decision = self.determine_state(
            previous_state,
            birth,
            survival,
            record=record,
        )

        new_state = decision["state"]
        previous_rank = _STATE_RANK.get(previous_state, 0)
        new_rank = _STATE_RANK.get(new_state, 0)

        if new_state == previous_state:
            transition = "UNCHANGED"
        elif new_state == CampaignState.DISTRIBUTION_RISK:
            transition = "RISK_DOWNGRADE"
        elif new_state == CampaignState.CLOSED:
            transition = "CLOSED"
        elif new_rank > previous_rank:
            transition = "ADVANCED"
        elif new_rank < previous_rank:
            transition = "DOWNGRADED"
        else:
            transition = "CHANGED"

        explanation = (
            f"Campaign state {transition}: {previous_state.value} -> {new_state.value}. "
            f"Birth={birth.get('birth_score')} ({birth.get('birth_state')}), "
            f"Survival={survival.get('master_survival_score')} ({survival.get('survival_state')}). "
            f"Reason: {decision.get('reason')}"
        )

        return CampaignStateVerdict(
            symbol=symbol,
            previous_state=previous_state.value,
            new_state=new_state.value,
            transition=transition,
            birth_score=self._safe_float(birth.get("birth_score")),
            birth_state=str(birth.get("birth_state", "UNKNOWN")),
            birth_eligible=bool(birth.get("birth_eligible", False)),
            master_survival_score=self._safe_float(survival.get("master_survival_score")),
            survival_state=str(survival.get("survival_state", "UNKNOWN")),
            survival_grade=str(survival.get("survival_grade", "F")),
            survival_confirmed=bool(survival.get("survival_confirmed", False)),
            transition_score=self._safe_float(decision.get("transition_score")),
            advance_allowed=bool(decision.get("advance_allowed", False)),
            failure_risk=bool(decision.get("failure_risk", False)),
            explanation=explanation,
            birth_details=birth,
            survival_details=survival,
            as_of=datetime.now(timezone.utc).isoformat(),
        ).to_dict()

    def evaluate_transition(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self.evaluate_record(record)

    def transition(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self.evaluate_record(record)

    def run(self, records: Optional[list[Dict[str, Any]]] = None) -> Dict[str, Any]:
        records = records or []
        results = [self.evaluate_record(record) for record in records]

        return {
            "ok": True,
            "engine": "campaign_state_engine",
            "records_evaluated": len(results),
            "results": results,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }


StateTransitionEngine = CampaignStateEngine
CampaignLifecycleEngine = CampaignStateEngine


def evaluate_campaign_state(record: Dict[str, Any]) -> Dict[str, Any]:
    return CampaignStateEngine().evaluate_record(record)


def run_campaign_state_engine(records: Optional[list[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return CampaignStateEngine().run(records or [])


__all__ = [
    "CampaignState",
    "CampaignStateEngine",
    "CampaignStateVerdict",
    "WyckoffSignals",
    "CampaignTransition",
    "StateTransitionEngine",
    "CampaignLifecycleEngine",
    "evaluate_campaign_state",
    "run_campaign_state_engine",
    "transition_campaign_state",
    "evaluate_transition",
    "run_state_transition",
]


def _dict_to_campaign_transition(result: Dict[str, Any]) -> CampaignTransition:
    """
    Convert survival-aware dict verdict to legacy CampaignTransition object.
    """
    if isinstance(result, CampaignTransition):
        return result

    old_state = result.get("old_state", result.get("previous_state", "NO_CAMPAIGN"))
    new_state = result.get("new_state", result.get("state", "NO_CAMPAIGN"))
    transition_score = result.get("transition_score", 0.0)

    return CampaignTransition(
        symbol=result.get("symbol", ""),
        old_state=old_state,
        previous_state=old_state,
        new_state=new_state,
        transition=result.get("transition", "UNCHANGED"),
        transition_score=transition_score,
        advance_allowed=result.get("advance_allowed", False),
        failure_risk=result.get("failure_risk", False),
        changed=str(old_state) != str(new_state),
        reason=result.get("reason", result.get("explanation", "")),
        explanation=result.get("explanation", result.get("reason", "")),
        confidence=result.get("confidence", transition_score),
        as_of=result.get("as_of", datetime.now(timezone.utc).isoformat()),
        birth_score=result.get("birth_score", 0.0),
        birth_state=result.get("birth_state", "UNKNOWN"),
        master_survival_score=result.get("master_survival_score", 0.0),
        survival_state=result.get("survival_state", "UNKNOWN"),
        survival_confirmed=result.get("survival_confirmed", False),
    )


def transition_campaign_state(*args, **kwargs):
    """
    Backward-compatible pipeline function.

    Existing nightly pipeline expects:
        transition.old_state.value
        transition.new_state.value
        transition.changed
        transition.reason
        transition.confidence
    """
    engine = CampaignStateEngine()

    if args and isinstance(args[0], dict):
        record = dict(args[0])
        record.update(kwargs)
        result = engine.evaluate_record(record)
        return _dict_to_campaign_transition(result)

    record = dict(kwargs)

    if args:
        record["symbol"] = str(args[0])

    result = engine.evaluate_record(record)
    return _dict_to_campaign_transition(result)


def evaluate_transition(record):
    return _dict_to_campaign_transition(CampaignStateEngine().evaluate_record(record))


def run_state_transition(record):
    return _dict_to_campaign_transition(CampaignStateEngine().evaluate_record(record))