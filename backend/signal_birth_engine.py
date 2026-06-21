"""
SAVE AS:
backend/research_engine/signal_birth_engine.py

Sigmalytic V2
Signal Birth Engine

Consumes:
- Master Campaign Index
- Meaningful Resistance
- Behavioral Resolution
- Campaign Survival

Signal Birth is the final institutional campaign birth verdict.
It does not use edge_score, campaign_score, ODS, or any existing composite
as a substitute for campaign evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


try:
    from backend.research_engine.master_campaign_index import MasterCampaignIndexEngine
except Exception:
    MasterCampaignIndexEngine = None


@dataclass
class SignalBirthVerdict:
    symbol: str
    birth_score: float
    birth_state: str
    birth_eligible: bool
    master_campaign_index: float
    master_verdict: str
    campaign_quality: str
    resistance_score: float
    behavioral_resolution_score: float
    survival_score: float
    confirmation_count: int
    agreement_score: float
    explanation: str
    master_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalBirthEngine:
    REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

    def __init__(
        self,
        symbols: Optional[Iterable[str]] = None,
        records: Optional[List[Dict[str, Any]]] = None,
    ):
        self.symbols = list(symbols or [])
        self.records = records or []

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

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Missing required OHLCV column: {col}")
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close", "volume"])

    def compute_resistance_score(self, df: pd.DataFrame, lookback: int = 60) -> Dict[str, Any]:
        """
        Meaningful Resistance Layer.
        Research principle: No meaningful obstacle = no meaningful victory.
        """
        df = self._prepare(df)

        if len(df) < lookback + 1:
            return {
                "resistance_score": 0.0,
                "resistance_level": None,
                "support_level": None,
                "cause_width_pct": None,
            }

        resistance = float(df["high"].rolling(lookback).max().shift(1).iloc[-1])
        support = float(df["low"].rolling(lookback).min().shift(1).iloc[-1])
        current_close = float(df["close"].iloc[-1])

        cause_width = max(0.0, resistance - support)
        cause_width_pct = cause_width / max(current_close, 1.0)
        cause_quality = min(100.0, cause_width_pct * 500.0)

        distance_to_resistance = resistance - current_close
        proximity = 100.0 - min(
            100.0,
            max(0.0, distance_to_resistance / max(current_close, 1.0) * 500.0),
        )

        resistance_score = self._safe_score((cause_quality * 0.60) + (proximity * 0.40))

        return {
            "resistance_score": resistance_score,
            "resistance_level": round(resistance, 4),
            "support_level": round(support, 4),
            "cause_width_pct": round(cause_width_pct, 4),
        }

    def compute_behavioral_resolution_score(self, df: pd.DataFrame, lookback: int = 60) -> Dict[str, Any]:
        """
        Behavioral Resolution Layer.
        Measures whether price is resolving the meaningful obstacle.
        """
        df = self._prepare(df)

        if len(df) < lookback + 5:
            return {
                "behavioral_resolution_score": 0.0,
                "progress_against_resistance": None,
                "five_bar_progress": None,
            }

        resistance = float(df["high"].rolling(lookback).max().shift(1).iloc[-1])
        current_close = float(df["close"].iloc[-1])
        prior_close = float(df["close"].iloc[-5])

        progress_against_resistance = current_close / max(resistance, 1.0)
        five_bar_progress = (current_close - prior_close) / max(prior_close, 1.0)

        score = 0.0
        if progress_against_resistance >= 0.98:
            score += 35.0
        if current_close > resistance:
            score += 40.0
        if five_bar_progress > 0:
            score += 25.0

        return {
            "behavioral_resolution_score": self._safe_score(score),
            "progress_against_resistance": round(float(progress_against_resistance), 4),
            "five_bar_progress": round(float(five_bar_progress), 4),
        }

    def compute_survival_score(self, df: pd.DataFrame, window: int = 30) -> Dict[str, Any]:
        """
        Campaign Survival Layer.
        Measures whether the campaign has enough structural durability to survive.
        """
        df = self._prepare(df)

        if len(df) < 10:
            return {
                "survival_score": 0.0,
                "recent_drawdown": None,
                "higher_lows_count": 0,
                "close_above_mid_count": 0,
            }

        recent = df.tail(window)

        higher_lows = int((recent["low"] > recent["low"].shift(1)).sum())
        close_above_mid = int(
            (
                recent["close"]
                > ((recent["high"] + recent["low"]) / 2)
            ).sum()
        )

        max_close = float(recent["close"].max())
        current_close = float(recent["close"].iloc[-1])
        recent_drawdown = (current_close - max_close) / max(max_close, 1.0)

        survival_score = (
            min(100.0, higher_lows * 5.0) * 0.35
            + min(100.0, close_above_mid * 4.0) * 0.35
            + max(0.0, 100.0 + recent_drawdown * 300.0) * 0.30
        )

        return {
            "survival_score": self._safe_score(survival_score),
            "recent_drawdown": round(float(recent_drawdown), 4),
            "higher_lows_count": higher_lows,
            "close_above_mid_count": close_above_mid,
        }

    def run_master_campaign_index(
        self,
        df: pd.DataFrame,
        symbol: str = "",
        sister_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if MasterCampaignIndexEngine is None:
            return {
                "master_campaign_index": 0.0,
                "verdict": "MASTER_CAMPAIGN_INDEX_UNAVAILABLE",
                "birth_eligible": False,
                "campaign_quality": "F",
                "confirmation_count": 0,
                "agreement_score": 0.0,
            }

        try:
            return MasterCampaignIndexEngine().evaluate_bars(
                df,
                symbol=symbol,
                sister_df=sister_df,
            )
        except Exception as exc:
            return {
                "master_campaign_index": 0.0,
                "verdict": "MASTER_CAMPAIGN_INDEX_ERROR",
                "birth_eligible": False,
                "campaign_quality": "F",
                "confirmation_count": 0,
                "agreement_score": 0.0,
                "error": str(exc),
            }

    def evaluate_bars(
        self,
        df: pd.DataFrame,
        sister_df: Optional[pd.DataFrame] = None,
        symbol: str = "",
    ) -> Dict[str, Any]:
        symbol = str(symbol or "").upper()

        if df is None or len(df) == 0:
            return SignalBirthVerdict(
                symbol=symbol,
                birth_score=0.0,
                birth_state="NO_BARS",
                birth_eligible=False,
                master_campaign_index=0.0,
                master_verdict="NO_BARS",
                campaign_quality="F",
                resistance_score=0.0,
                behavioral_resolution_score=0.0,
                survival_score=0.0,
                confirmation_count=0,
                agreement_score=0.0,
                explanation="No OHLCV bars supplied to Signal Birth Engine.",
                master_details={},
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        df = self._prepare(df)

        master = self.run_master_campaign_index(df, symbol=symbol, sister_df=sister_df)
        resistance = self.compute_resistance_score(df)
        resolution = self.compute_behavioral_resolution_score(df)
        survival = self.compute_survival_score(df)

        master_index = self._safe_score(master.get("master_campaign_index", 0.0))
        resistance_score = self._safe_score(resistance.get("resistance_score", 0.0))
        resolution_score = self._safe_score(resolution.get("behavioral_resolution_score", 0.0))
        survival_score = self._safe_score(survival.get("survival_score", 0.0))

        birth_score = self._safe_score(
            master_index * 0.60
            + resistance_score * 0.15
            + resolution_score * 0.15
            + survival_score * 0.10
        )

        confirmation_count = int(master.get("confirmation_count", 0) or 0)
        agreement_score = self._safe_score(master.get("agreement_score", 0.0))

        birth_eligible = (
            master_index >= 65.0
            and resolution_score >= 60.0
            and survival_score >= 50.0
            and confirmation_count >= 2
        )

        if birth_score >= 85.0 and birth_eligible:
            birth_state = "CAMPAIGN_BIRTH"
        elif birth_score >= 70.0 and birth_eligible:
            birth_state = "EARLY_CAMPAIGN"
        elif birth_score >= 55.0:
            birth_state = "POTENTIAL_BIRTH"
        else:
            birth_state = "NO_BIRTH"

        explanation = (
            f"Signal Birth {birth_state}; birth_score={birth_score}; "
            f"MCI={master_index}, resistance={resistance_score}, "
            f"resolution={resolution_score}, survival={survival_score}, "
            f"confirmations={confirmation_count}/3."
        )

        return SignalBirthVerdict(
            symbol=symbol,
            birth_score=birth_score,
            birth_state=birth_state,
            birth_eligible=birth_eligible,
            master_campaign_index=master_index,
            master_verdict=str(master.get("verdict", "UNKNOWN")),
            campaign_quality=str(master.get("campaign_quality", "F")),
            resistance_score=resistance_score,
            behavioral_resolution_score=resolution_score,
            survival_score=survival_score,
            confirmation_count=confirmation_count,
            agreement_score=agreement_score,
            explanation=explanation,
            master_details={
                "master_campaign_index": master,
                "meaningful_resistance": resistance,
                "behavioral_resolution": resolution,
                "campaign_survival": survival,
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
                "birth_score": 0.0,
                "birth_state": "NO_BARS",
                "birth_eligible": False,
                "explanation": "Record does not contain bars.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }

        df = pd.DataFrame(bars)
        sister_df = pd.DataFrame(sister_bars) if sister_bars else None

        return self.evaluate_bars(df, sister_df=sister_df, symbol=symbol)

    def run(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        symbols: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        active_records = records if records is not None else self.records
        active_symbols = list(symbols or self.symbols)

        evaluated: List[Dict[str, Any]] = []

        if active_records:
            evaluated = [self.evaluate_record(record) for record in active_records]
        elif active_symbols:
            evaluated = [
                {
                    "symbol": str(symbol).upper(),
                    "birth_state": "WATCH",
                    "birth_score": 0.0,
                    "birth_eligible": False,
                    "message": "Symbol supplied without OHLCV bars. Signal Birth requires bars.",
                    "as_of": datetime.now(timezone.utc).isoformat(),
                }
                for symbol in active_symbols
            ]

        born = [row for row in evaluated if row.get("birth_eligible")]

        return {
            "ok": True,
            "engine": "signal_birth_engine",
            "status": "completed",
            "engine_available": True,
            "signals_evaluated": len(evaluated),
            "signals_born": len(born),
            "campaigns_created": 0,
            "results": evaluated[:100],
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def run_cycle(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return self.run(*args, **kwargs)

    def execute(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        return self.run(*args, **kwargs)


def run_signal_birth_engine(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return SignalBirthEngine().run(*args, **kwargs)


def run_signal_birth_cycle(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return SignalBirthEngine().run(*args, **kwargs)


def trigger_signal_birth(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return SignalBirthEngine().run(*args, **kwargs)


def execute_signal_birth(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    return SignalBirthEngine().run(*args, **kwargs)


ResearchSignalBirthEngine = SignalBirthEngine
CampaignSignalBirthEngine = SignalBirthEngine
SignalBirthRunner = SignalBirthEngine


__all__ = [
    "SignalBirthEngine",
    "SignalBirthVerdict",
    "run_signal_birth_engine",
    "run_signal_birth_cycle",
    "trigger_signal_birth",
    "execute_signal_birth",
    "ResearchSignalBirthEngine",
    "CampaignSignalBirthEngine",
    "SignalBirthRunner",
]
