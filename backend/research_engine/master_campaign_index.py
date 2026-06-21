"""
SAVE AS:
backend/research_engine/master_campaign_index.py

Sigmalytic V2
Master Campaign Index Engine

Purpose:
Fuse three independent institutional campaign verdict engines into one
100-point campaign index:

- Wyckoff: structure / accumulation / cause / spring / SOS
- Livermore: operator persistence / advancement / failure frequency / continuity
- Weis: effort vs result / SOT / exhaustion / demand confirmation

Core Principle:
This engine does NOT predict price.
It measures current institutional campaign state.

Default Master Weights:
- Wyckoff   40%
- Livermore 30%
- Weis      30%
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd


try:
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
except Exception:
    WyckoffVerdictEngine = None


try:
    from backend.research_engine.livermore_verdict_engine import LivermoreVerdictEngine
except Exception:
    LivermoreVerdictEngine = None


try:
    from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
except Exception:
    WeisVerdictEngine = None


@dataclass
class MasterCampaignVerdict:
    symbol: str

    master_campaign_index: float
    verdict: str
    birth_eligible: bool
    campaign_quality: str

    wyckoff_score: float
    wyckoff_verdict: str
    livermore_score: float
    livermore_verdict: str
    weis_score: float
    weis_verdict: str

    agreement_score: float
    confirmation_count: int
    conflict_count: int

    explanation: str
    component_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MasterCampaignIndexEngine:
    """
    Combines Wyckoff, Livermore, and Weis verdicts into a unified
    institutional campaign state measurement.
    """

    def __init__(
        self,
        wyckoff_weight: float = 0.40,
        livermore_weight: float = 0.30,
        weis_weight: float = 0.30,
    ):
        total = wyckoff_weight + livermore_weight + weis_weight

        if total <= 0:
            wyckoff_weight = 0.40
            livermore_weight = 0.30
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
    def _extract_score(result: Dict[str, Any], keys: list[str]) -> float:
        for key in keys:
            if key in result:
                return MasterCampaignIndexEngine._safe_score(result.get(key))
        return 0.0

    @staticmethod
    def _extract_verdict(result: Dict[str, Any], default: str = "UNKNOWN") -> str:
        return str(result.get("verdict") or result.get("phase") or default)

    @staticmethod
    def _is_positive_verdict(result: Dict[str, Any]) -> bool:
        if bool(result.get("birth_eligible")):
            return True

        verdict = str(result.get("verdict", "")).upper()

        positive_terms = (
            "STRONG",
            "EMERGING",
            "BIRTH",
            "BUILDING",
            "LAUNCH",
            "ACCUMULATION",
            "ABSORPTION",
        )

        negative_terms = (
            "NO_",
            "FAILURE",
            "DISTRIBUTION",
            "INSUFFICIENT",
            "UNKNOWN",
        )

        if any(term in verdict for term in negative_terms):
            return False

        return any(term in verdict for term in positive_terms)

    def _run_wyckoff(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        if WyckoffVerdictEngine is None:
            return {
                "wyckoff_score": 0.0,
                "verdict": "WYCKOFF_ENGINE_UNAVAILABLE",
                "birth_eligible": False,
            }

        try:
            return WyckoffVerdictEngine().evaluate_bars(df, symbol=symbol)
        except Exception as exc:
            return {
                "wyckoff_score": 0.0,
                "verdict": "WYCKOFF_ERROR",
                "birth_eligible": False,
                "error": str(exc),
            }

    def _run_livermore(
        self,
        df: pd.DataFrame,
        symbol: str,
        sister_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if LivermoreVerdictEngine is None:
            return {
                "livermore_score": 0.0,
                "verdict": "LIVERMORE_ENGINE_UNAVAILABLE",
                "birth_eligible": False,
            }

        try:
            return LivermoreVerdictEngine().evaluate(
                df,
                symbol=symbol,
                sister_df=sister_df,
            )
        except Exception as exc:
            return {
                "livermore_score": 0.0,
                "verdict": "LIVERMORE_ERROR",
                "birth_eligible": False,
                "error": str(exc),
            }

    def _run_weis(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        if WeisVerdictEngine is None:
            return {
                "weis_score": 0.0,
                "verdict": "WEIS_ENGINE_UNAVAILABLE",
                "birth_eligible": False,
            }

        try:
            return WeisVerdictEngine().evaluate(df, symbol=symbol)
        except Exception as exc:
            return {
                "weis_score": 0.0,
                "verdict": "WEIS_ERROR",
                "birth_eligible": False,
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
            return MasterCampaignVerdict(
                symbol=symbol,
                master_campaign_index=0.0,
                verdict="NO_BARS",
                birth_eligible=False,
                campaign_quality="F",
                wyckoff_score=0.0,
                wyckoff_verdict="NO_BARS",
                livermore_score=0.0,
                livermore_verdict="NO_BARS",
                weis_score=0.0,
                weis_verdict="NO_BARS",
                agreement_score=0.0,
                confirmation_count=0,
                conflict_count=3,
                explanation="No OHLCV bars supplied to Master Campaign Index.",
                component_details={},
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        df = df.copy()

        wyckoff = self._run_wyckoff(df, symbol)
        livermore = self._run_livermore(df, symbol, sister_df=sister_df)
        weis = self._run_weis(df, symbol)

        wyckoff_score = self._extract_score(wyckoff, ["wyckoff_score", "score"])
        livermore_score = self._extract_score(livermore, ["livermore_score", "score"])
        weis_score = self._extract_score(weis, ["weis_score", "score"])

        master_index = (
            wyckoff_score * self.wyckoff_weight
            + livermore_score * self.livermore_weight
            + weis_score * self.weis_weight
        )
        master_index = self._safe_score(master_index)

        positive_flags = [
            self._is_positive_verdict(wyckoff),
            self._is_positive_verdict(livermore),
            self._is_positive_verdict(weis),
        ]

        confirmation_count = sum(1 for flag in positive_flags if flag)
        conflict_count = 3 - confirmation_count
        agreement_score = round((confirmation_count / 3.0) * 100.0, 2)

        if master_index >= 80 and confirmation_count >= 2:
            verdict = "ALPHA_CAMPAIGN_ACTIVATION"
            quality = "A"
        elif master_index >= 65 and confirmation_count >= 2:
            verdict = "EMERGING_INSTITUTIONAL_CAMPAIGN"
            quality = "B"
        elif master_index >= 45 and confirmation_count >= 1:
            verdict = "INSTITUTIONAL_BASE_BUILD"
            quality = "C"
        elif master_index >= 35:
            verdict = "WATCH_NOISE_OR_EARLY_BASE"
            quality = "D"
        else:
            verdict = "NO_CAMPAIGN"
            quality = "F"

        birth_eligible = verdict in {
            "ALPHA_CAMPAIGN_ACTIVATION",
            "EMERGING_INSTITUTIONAL_CAMPAIGN",
        }

        explanation = (
            f"MCI={master_index}; verdict={verdict}; "
            f"Wyckoff={wyckoff_score} ({self._extract_verdict(wyckoff)}), "
            f"Livermore={livermore_score} ({self._extract_verdict(livermore)}), "
            f"Weis={weis_score} ({self._extract_verdict(weis)}); "
            f"confirmations={confirmation_count}/3."
        )

        return MasterCampaignVerdict(
            symbol=symbol,
            master_campaign_index=master_index,
            verdict=verdict,
            birth_eligible=birth_eligible,
            campaign_quality=quality,
            wyckoff_score=wyckoff_score,
            wyckoff_verdict=self._extract_verdict(wyckoff),
            livermore_score=livermore_score,
            livermore_verdict=self._extract_verdict(livermore),
            weis_score=weis_score,
            weis_verdict=self._extract_verdict(weis),
            agreement_score=agreement_score,
            confirmation_count=confirmation_count,
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
                "master_campaign_index": 0.0,
                "verdict": "NO_BARS",
                "birth_eligible": False,
                "campaign_quality": "F",
                "explanation": "Record does not contain bars.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }

        df = pd.DataFrame(bars)
        sister_df = pd.DataFrame(sister_bars) if sister_bars else None

        return self.evaluate_bars(df, symbol=symbol, sister_df=sister_df)


def calculate_macro_campaign_master_index(
    df: pd.DataFrame,
    sector_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Compatibility wrapper for dataframe-level use.
    Returns the latest master verdict dictionary.
    """
    return MasterCampaignIndexEngine().evaluate_bars(
        df,
        symbol="",
        sister_df=sector_df,
    )


def run_master_campaign_index(record: Dict[str, Any]) -> Dict[str, Any]:
    return MasterCampaignIndexEngine().evaluate_record(record)


__all__ = [
    "MasterCampaignIndexEngine",
    "MasterCampaignVerdict",
    "calculate_macro_campaign_master_index",
    "run_master_campaign_index",
]
