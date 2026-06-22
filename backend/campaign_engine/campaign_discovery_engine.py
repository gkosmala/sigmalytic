"""
SAVE AS:
backend/campaign_engine/campaign_discovery_engine.py

Sigmalytic V2
Campaign Discovery Engine

Purpose:
Find and create new institutional campaign records.

This engine is the missing front door before nightly lifecycle transitions.

It does:
1. Accept symbols with OHLCV bars or prebuilt records containing bars.
2. Run Signal Birth.
3. Run Master Survival Index.
4. Create a campaign payload when discovery thresholds are met.
5. Save the campaign through CampaignStore.

Important:
This engine does not fetch bars by itself unless a data_loader callback is supplied.
That prevents fake discovery from symbols with no OHLCV data.

Expected record format:
{
    "symbol": "NVDA",
    "timeframe": "DAILY",
    "bars": [
        {"open":..., "high":..., "low":..., "close":..., "volume":...}
    ],
    "sister_bars": optional list
}
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import pandas as pd


try:
    from backend.research_engine.signal_birth_engine import SignalBirthEngine
except Exception:
    SignalBirthEngine = None


try:
    from backend.research_engine.master_survival_index import MasterSurvivalIndexEngine
except Exception:
    MasterSurvivalIndexEngine = None


try:
    from backend.campaign_engine.campaign_store import CampaignStore
except Exception:
    CampaignStore = None


@dataclass
class CampaignDiscoveryVerdict:
    symbol: str
    timeframe: str
    discovered: bool
    reason: str

    birth_score: float
    birth_state: str
    birth_eligible: bool

    master_campaign_index: float
    master_verdict: str
    campaign_quality: str

    master_survival_score: float
    survival_state: str
    survival_grade: str
    survival_confirmed: bool

    current_state: str
    payload: Dict[str, Any]
    birth_details: Dict[str, Any]
    survival_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CampaignDiscoveryEngine:
    """
    Discovery layer.

    Birth engine:
        SignalBirthEngine.evaluate_bars(df, sister_df, symbol)

    Survival engine:
        MasterSurvivalIndexEngine.evaluate_bars(df, symbol, sister_df)

    Store:
        CampaignStore.save_campaign(payload)

    The existing CampaignStore upserts on:
        symbol,timeframe
    """

    def __init__(
        self,
        store: Optional[Any] = None,
        data_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        sister_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        birth_threshold: float = 55.0,
        survival_threshold: float = 50.0,
        mci_threshold: float = 25.0,
        timeframe: str = "DAILY",
    ):
        self.store = store or (CampaignStore() if CampaignStore is not None else None)
        self.data_loader = data_loader
        self.sister_loader = sister_loader

        self.birth_threshold = birth_threshold
        self.survival_threshold = survival_threshold
        self.mci_threshold = mci_threshold
        self.timeframe = timeframe.upper()

        self.birth_engine = SignalBirthEngine() if SignalBirthEngine is not None else None
        self.survival_engine = (
            MasterSurvivalIndexEngine()
            if MasterSurvivalIndexEngine is not None
            else None
        )

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return round(float(value), 2)
        except Exception:
            return default

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        bars = record.get("bars")
        if not bars:
            return None

        df = pd.DataFrame(bars)

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None

        return df

    def _sister_bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        sister_bars = record.get("sister_bars") or record.get("sector_bars")
        if not sister_bars:
            return None

        df = pd.DataFrame(sister_bars)

        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(set(df.columns)):
            return None

        return df

    def _load_bars(self, symbol: str, timeframe: str, record: Optional[Dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        if record:
            df = self._bars_from_record(record)
            if df is not None:
                return df

        if self.data_loader is None:
            return None

        return self.data_loader(symbol, timeframe)

    def _load_sister_bars(self, symbol: str, timeframe: str, record: Optional[Dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        if record:
            df = self._sister_bars_from_record(record)
            if df is not None:
                return df

        if self.sister_loader is None:
            return None

        return self.sister_loader(symbol, timeframe)

    def _build_campaign_payload(
        self,
        symbol: str,
        timeframe: str,
        birth: Dict[str, Any],
        survival: Dict[str, Any],
        current_close: Optional[float],
    ) -> Dict[str, Any]:
        now = self._now()

        birth_score = self._safe_float(birth.get("birth_score"))
        master_campaign_index = self._safe_float(birth.get("master_campaign_index"))
        master_survival_score = self._safe_float(survival.get("master_survival_score"))

        birth_state = str(birth.get("birth_state", "UNKNOWN"))
        survival_state = str(survival.get("survival_state", "UNKNOWN"))

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),

            "current_state": "BIRTH",
            "state_enum": "BIRTH",

            "birth_score": birth_score,
            "birth_state": birth_state,
            "birth_eligible": bool(birth.get("birth_eligible", False)),

            "master_campaign_index": master_campaign_index,
            "master_verdict": str(birth.get("master_verdict", "UNKNOWN")),
            "campaign_quality": str(birth.get("campaign_quality", "UNKNOWN")),

            "master_survival_score": master_survival_score,
            "survival_state": survival_state,
            "survival_grade": str(survival.get("survival_grade", "F")),
            "survival_confirmed": bool(survival.get("survival_confirmed", False)),

            "confirmation_count": int(birth.get("confirmation_count", 0) or 0),
            "agreement_score": self._safe_float(birth.get("agreement_score")),

            "current_price": current_close,

            "active": True,
            "discovery_source": "campaign_discovery_engine",
            "campaign_created_at": now,
            "last_discovery_run": now,
            "last_pipeline_run": now,
        }

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper().strip()
        timeframe = str(record.get("timeframe") or self.timeframe).upper().strip()

        if not symbol:
            return CampaignDiscoveryVerdict(
                symbol="",
                timeframe=timeframe,
                discovered=False,
                reason="Missing symbol.",
                birth_score=0.0,
                birth_state="NO_SYMBOL",
                birth_eligible=False,
                master_campaign_index=0.0,
                master_verdict="NO_SYMBOL",
                campaign_quality="F",
                master_survival_score=0.0,
                survival_state="NO_SYMBOL",
                survival_grade="F",
                survival_confirmed=False,
                current_state="NO_CAMPAIGN",
                payload={},
                birth_details={},
                survival_details={},
                as_of=self._now(),
            ).to_dict()

        df = self._load_bars(symbol, timeframe, record=record)
        sister_df = self._load_sister_bars(symbol, timeframe, record=record)

        if df is None or len(df) == 0:
            return CampaignDiscoveryVerdict(
                symbol=symbol,
                timeframe=timeframe,
                discovered=False,
                reason="No OHLCV bars supplied or loaded. Discovery requires bars.",
                birth_score=0.0,
                birth_state="NO_BARS",
                birth_eligible=False,
                master_campaign_index=0.0,
                master_verdict="NO_BARS",
                campaign_quality="F",
                master_survival_score=0.0,
                survival_state="NO_BARS",
                survival_grade="F",
                survival_confirmed=False,
                current_state="NO_CAMPAIGN",
                payload={},
                birth_details={},
                survival_details={},
                as_of=self._now(),
            ).to_dict()

        if self.birth_engine is None:
            raise RuntimeError("SignalBirthEngine unavailable.")

        birth = self.birth_engine.evaluate_bars(
            df,
            sister_df=sister_df,
            symbol=symbol,
        )

        if self.survival_engine is not None:
            survival = self.survival_engine.evaluate_bars(
                df,
                symbol=symbol,
                sister_df=sister_df,
            )
        else:
            survival = {
                "master_survival_score": 0.0,
                "survival_state": "MASTER_SURVIVAL_INDEX_UNAVAILABLE",
                "survival_grade": "F",
                "survival_confirmed": False,
            }

        birth_score = self._safe_float(birth.get("birth_score"))
        mci = self._safe_float(birth.get("master_campaign_index"))
        survival_score = self._safe_float(survival.get("master_survival_score"))

        current_close = None
        try:
            current_close = round(float(df["close"].iloc[-1]), 4)
        except Exception:
            current_close = None

        discovered = (
            birth_score >= self.birth_threshold
            and mci >= self.mci_threshold
            and survival_score >= self.survival_threshold
        )

        reason = (
            f"Discovery {'accepted' if discovered else 'rejected'}; "
            f"birth={birth_score}, mci={mci}, survival={survival_score}; "
            f"thresholds birth>={self.birth_threshold}, "
            f"mci>={self.mci_threshold}, survival>={self.survival_threshold}."
        )

        payload = {}
        if discovered:
            payload = self._build_campaign_payload(
                symbol=symbol,
                timeframe=timeframe,
                birth=birth,
                survival=survival,
                current_close=current_close,
            )

            if self.store is not None and getattr(self.store, "configured", lambda: False)():
                self.store.save_campaign(payload)

        return CampaignDiscoveryVerdict(
            symbol=symbol,
            timeframe=timeframe,
            discovered=discovered,
            reason=reason,
            birth_score=birth_score,
            birth_state=str(birth.get("birth_state", "UNKNOWN")),
            birth_eligible=bool(birth.get("birth_eligible", False)),
            master_campaign_index=mci,
            master_verdict=str(birth.get("master_verdict", "UNKNOWN")),
            campaign_quality=str(birth.get("campaign_quality", "F")),
            master_survival_score=survival_score,
            survival_state=str(survival.get("survival_state", "UNKNOWN")),
            survival_grade=str(survival.get("survival_grade", "F")),
            survival_confirmed=bool(survival.get("survival_confirmed", False)),
            current_state="BIRTH" if discovered else "NO_CAMPAIGN",
            payload=payload,
            birth_details=birth,
            survival_details=survival,
            as_of=self._now(),
        ).to_dict()

    def run_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = [self.evaluate_record(record) for record in records]
        discovered = [row for row in results if row.get("discovered")]

        return {
            "ok": True,
            "engine": "campaign_discovery_engine",
            "records_evaluated": len(results),
            "campaigns_discovered": len(discovered),
            "discovered_symbols": [row.get("symbol") for row in discovered],
            "results": results,
            "as_of": self._now(),
        }

    def run_symbols(
        self,
        symbols: Iterable[str],
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        timeframe = str(timeframe or self.timeframe).upper()

        records = [
            {
                "symbol": str(symbol).upper(),
                "timeframe": timeframe,
            }
            for symbol in symbols
        ]

        return self.run_records(records)

    def run(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        symbols: Optional[Iterable[str]] = None,
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        if records:
            return self.run_records(records)

        if symbols:
            return self.run_symbols(symbols, timeframe=timeframe)

        return {
            "ok": True,
            "engine": "campaign_discovery_engine",
            "records_evaluated": 0,
            "campaigns_discovered": 0,
            "discovered_symbols": [],
            "results": [],
            "message": "No records or symbols supplied.",
            "as_of": self._now(),
        }


def run_campaign_discovery(
    records: Optional[List[Dict[str, Any]]] = None,
    symbols: Optional[Iterable[str]] = None,
    timeframe: str = "DAILY",
) -> Dict[str, Any]:
    return CampaignDiscoveryEngine(timeframe=timeframe).run(
        records=records,
        symbols=symbols,
        timeframe=timeframe,
    )


CampaignDiscoveryRunner = CampaignDiscoveryEngine


__all__ = [
    "CampaignDiscoveryEngine",
    "CampaignDiscoveryVerdict",
    "CampaignDiscoveryRunner",
    "run_campaign_discovery",
]
