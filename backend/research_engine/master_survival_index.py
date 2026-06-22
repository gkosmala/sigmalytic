"""
SAVE AS:
backend/research_engine/master_survival_index.py

Sigmalytic V2
Master Survival Index Engine

Purpose:
Combine the three independent campaign survival engines into one
multi-level institutional campaign survival verdict.

Inputs:
- Wyckoff Survival Engine
- Livermore Survival Engine
- Weis Survival Engine

Output:
- master_survival_score
- survival_grade
- survival_state
- survival_confirmed

Core Principle:
Birth is not enough.
A campaign must survive after birth to become a confirmed institutional campaign.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd


try:
    from backend.research_engine.wyckoff_survival_engine import WyckoffSurvivalEngine
except Exception:
    WyckoffSurvivalEngine = None


try:
    from backend.research_engine.livermore_survival_engine import LivermoreSurvivalEngine
except Exception:
    LivermoreSurvivalEngine = None


try:
    from backend.research_engine.weis_survival_engine import WeisSurvivalEngine
except Exception:
    WeisSurvivalEngine = None


@dataclass
class MasterSurvivalVerdict:
    symbol: str

    master_survival_score: float
    survival_grade: str
    survival_state: str
    survival_confirmed: bool

    wyckoff_survival_score: float
    wyckoff_survival_state: str
    livermore_survival_score: float
    livermore_survival_state: str
    weis_survival_score: float
    weis_survival_state: str

    confirmation_count: int
    agreement_score: float
    conflict_count: int

    explanation: str
    component_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MasterSurvivalIndexEngine:
    """
    Multi-method campaign survival aggregation.

    Default weights:
    Wyckoff    35%
    Livermore 35%
    Weis      30%

    Rationale:
    - Wyckoff measures structural survival.
    - Livermore measures campaign behavior survival.
    - Weis measures tape / effort-vs-result survival.
    """

    def __init__(
        self,
        wyckoff_weight: float = 0.35,
        livermore_weight: float = 0.35,
        weis_weight: float = 0.30,
    ):
        total = wyckoff_weight + livermore_weight + weis_weight

        if total <= 0:
            wyckoff_weight = 0.35
            livermore_weight = 0.35
            weis_weight = 0.30
            total = 1.0

        self.wyckoff_weight = wyckoff_weight / total
        self.livermore_weight = livermore_weight / total
        self.weis_weight = weis_weight / total

    @staticmethod
    def _safe_score(value: Any) -> float:
        try:
            value = float(value)
            if value < 0:
                return 0.0
            if value > 100:
                return 100.0
            return round(value, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 60:
            return "C"
        if score >= 50:
            return "D"
        return "F"

    @staticmethod
    def _state(score: float) -> str:
        if score >= 85:
            return "INSTITUTIONAL_SURVIVAL_CONFIRMED"
        if score >= 75:
            return "STRONG_SURVIVAL"
        if score >= 65:
            return "SURVIVING"
        if score >= 55:
            return "MARGINAL_SURVIVAL"
        if score >= 45:
            return "AT_RISK"
        return "FAILURE_RISK"

    @staticmethod
    def _extract_state(result: Dict[str, Any]) -> str:
        return str(
            result.get("survival_state")
            or result.get("state")
            or result.get("verdict")
            or "UNKNOWN"
        )

    @staticmethod
    def _is_confirmed(result: Dict[str, Any], score_key: str) -> bool:
        if bool(result.get("survival_confirmed")):
            return True

        try:
            return float(result.get(score_key, 0.0)) >= 70.0
        except Exception:
            return False

    def _run_wyckoff(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        if WyckoffSurvivalEngine is None:
            return {
                "wyckoff_survival_score": 0.0,
                "survival_state": "WYCKOFF_SURVIVAL_ENGINE_UNAVAILABLE",
                "survival_confirmed": False,
            }

        try:
            return WyckoffSurvivalEngine().evaluate_bars(df, symbol=symbol)
        except Exception as exc:
            return {
                "wyckoff_survival_score": 0.0,
                "survival_state": "WYCKOFF_SURVIVAL_ERROR",
                "survival_confirmed": False,
                "error": str(exc),
            }

    def _run_livermore(
        self,
        df: pd.DataFrame,
        symbol: str,
        sister_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if LivermoreSurvivalEngine is None:
            return {
                "livermore_survival_score": 0.0,
                "survival_state": "LIVERMORE_SURVIVAL_ENGINE_UNAVAILABLE",
                "survival_confirmed": False,
            }

        try:
            return LivermoreSurvivalEngine().evaluate_bars(
                df,
                symbol=symbol,
                sister_df=sister_df,
            )
        except Exception as exc:
            return {
                "livermore_survival_score": 0.0,
                "survival_state": "LIVERMORE_SURVIVAL_ERROR",
                "survival_confirmed": False,
                "error": str(exc),
            }

    def _run_weis(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        if WeisSurvivalEngine is None:
            return {
                "weis_survival_score": 0.0,
                "survival_state": "WEIS_SURVIVAL_ENGINE_UNAVAILABLE",
                "survival_confirmed": False,
            }

        try:
            return WeisSurvivalEngine().evaluate_bars(df, symbol=symbol)
        except Exception as exc:
            return {
                "weis_survival_score": 0.0,
                "survival_state": "WEIS_SURVIVAL_ERROR",
                "survival_confirmed": False,
                "error": str(exc),
            }

    def evaluate_bars(
        self,
        df: pd.DataFrame,
        symbol: str = "",
        sister_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        symbol = str(symbol or "").upper()

        if df is None or len(df) == 0:
            return MasterSurvivalVerdict(
                symbol=symbol,
                master_survival_score=0.0,
                survival_grade="F",
                survival_state="NO_BARS",
                survival_confirmed=False,
                wyckoff_survival_score=0.0,
                wyckoff_survival_state="NO_BARS",
                livermore_survival_score=0.0,
                livermore_survival_state="NO_BARS",
                weis_survival_score=0.0,
                weis_survival_state="NO_BARS",
                confirmation_count=0,
                agreement_score=0.0,
                conflict_count=3,
                explanation="No OHLCV bars supplied to Master Survival Index.",
                component_details={},
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        df = df.copy()

        wyckoff = self._run_wyckoff(df, symbol)
        livermore = self._run_livermore(df, symbol, sister_df=sister_df)
        weis = self._run_weis(df, symbol)

        wyckoff_score = self._safe_score(wyckoff.get("wyckoff_survival_score", 0.0))
        livermore_score = self._safe_score(livermore.get("livermore_survival_score", 0.0))
        weis_score = self._safe_score(weis.get("weis_survival_score", 0.0))

        master_score = self._safe_score(
            wyckoff_score * self.wyckoff_weight
            + livermore_score * self.livermore_weight
            + weis_score * self.weis_weight
        )

        confirmed_flags = [
            self._is_confirmed(wyckoff, "wyckoff_survival_score"),
            self._is_confirmed(livermore, "livermore_survival_score"),
            self._is_confirmed(weis, "weis_survival_score"),
        ]

        confirmation_count = sum(1 for flag in confirmed_flags if flag)
        conflict_count = 3 - confirmation_count
        agreement_score = round((confirmation_count / 3.0) * 100.0, 2)

        survival_confirmed = (
            master_score >= 70.0
            and confirmation_count >= 2
        )

        grade = self._grade(master_score)
        state = self._state(master_score)

        explanation = (
            f"Master Survival {state}; score={master_score}; "
            f"Wyckoff={wyckoff_score} ({self._extract_state(wyckoff)}), "
            f"Livermore={livermore_score} ({self._extract_state(livermore)}), "
            f"Weis={weis_score} ({self._extract_state(weis)}); "
            f"confirmations={confirmation_count}/3."
        )

        return MasterSurvivalVerdict(
            symbol=symbol,
            master_survival_score=master_score,
            survival_grade=grade,
            survival_state=state,
            survival_confirmed=survival_confirmed,
            wyckoff_survival_score=wyckoff_score,
            wyckoff_survival_state=self._extract_state(wyckoff),
            livermore_survival_score=livermore_score,
            livermore_survival_state=self._extract_state(livermore),
            weis_survival_score=weis_score,
            weis_survival_state=self._extract_state(weis),
            confirmation_count=confirmation_count,
            agreement_score=agreement_score,
            conflict_count=conflict_count,
            explanation=explanation,
            component_details={
                "wyckoff": wyckoff,
                "livermore": livermore,
                "weis": weis,
                "weights": {
                    "wyckoff": self.wyckoff_weight,
                    "livermore": self.livermore_weight,
                    "weis": self.weis_weight,
                },
            },
            as_of=datetime.now(timezone.utc).isoformat(),
        ).to_dict()

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper()

        bars = record.get("bars")
        sister_bars = record.get("sister_bars") or record.get("sector_bars")

        if not bars:
            return {
                "symbol": symbol,
                "master_survival_score": 0.0,
                "survival_grade": "F",
                "survival_state": "NO_BARS",
                "survival_confirmed": False,
                "explanation": "Record does not contain bars.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }

        df = pd.DataFrame(bars)
        sister_df = pd.DataFrame(sister_bars) if sister_bars else None

        return self.evaluate_bars(
            df,
            symbol=symbol,
            sister_df=sister_df,
        )


def run_master_survival_index(record: Dict[str, Any]) -> Dict[str, Any]:
    return MasterSurvivalIndexEngine().evaluate_record(record)


__all__ = [
    "MasterSurvivalIndexEngine",
    "MasterSurvivalVerdict",
    "run_master_survival_index",
]
