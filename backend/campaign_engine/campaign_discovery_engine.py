"""
SAVE AS:
backend/campaign_engine/campaign_discovery_engine.py

Sigmalytic V2
Campaign Discovery Engine with automatic universe + bar loading.

Uses existing radar_service infrastructure:
- load_russell1000()
- fetch_bars_batch(symbols, timeframe="1Day", limit=252)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import os
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

try:
    from backend.radar_service import load_russell1000, fetch_bars_batch
except Exception:
    load_russell1000 = None
    fetch_bars_batch = None


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
    def __init__(
        self,
        store: Optional[Any] = None,
        data_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        sister_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        birth_threshold: Optional[float] = None,
        survival_threshold: Optional[float] = None,
        mci_threshold: Optional[float] = None,
        timeframe: str = "DAILY",
        max_symbols: Optional[int] = None,
        bar_limit: Optional[int] = None,
    ):
        self.store = store or (CampaignStore() if CampaignStore is not None else None)
        self.data_loader = data_loader
        self.sister_loader = sister_loader
        self.birth_threshold = float(birth_threshold if birth_threshold is not None else os.getenv("CAMPAIGN_DISCOVERY_BIRTH_THRESHOLD", "55"))
        self.survival_threshold = float(survival_threshold if survival_threshold is not None else os.getenv("CAMPAIGN_DISCOVERY_SURVIVAL_THRESHOLD", "50"))
        self.mci_threshold = float(mci_threshold if mci_threshold is not None else os.getenv("CAMPAIGN_DISCOVERY_MCI_THRESHOLD", "25"))
        self.timeframe = timeframe.upper()
        self.max_symbols = int(max_symbols or os.getenv("CAMPAIGN_DISCOVERY_MAX_SYMBOLS", "1500"))
        self.bar_limit = int(bar_limit or os.getenv("CAMPAIGN_DISCOVERY_BAR_LIMIT", "252"))
        self.birth_engine = SignalBirthEngine() if SignalBirthEngine is not None else None
        self.survival_engine = MasterSurvivalIndexEngine() if MasterSurvivalIndexEngine is not None else None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return round(float(value), 2)
        except Exception:
            return default

    @staticmethod
    def _normalize_bar_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "open": row.get("open", row.get("o")),
            "high": row.get("high", row.get("h")),
            "low": row.get("low", row.get("l")),
            "close": row.get("close", row.get("c")),
            "volume": row.get("volume", row.get("v")),
        }

    @classmethod
    def _normalize_bars(cls, raw_bars: Any) -> Optional[List[Dict[str, Any]]]:
        if raw_bars is None:
            return None

        if isinstance(raw_bars, pd.DataFrame):
            if raw_bars.empty:
                return None
            rows = raw_bars.reset_index(drop=True).to_dict("records")
            return [cls._normalize_bar_row(r) for r in rows]

        if isinstance(raw_bars, dict):
            if "bars" in raw_bars:
                return cls._normalize_bars(raw_bars.get("bars"))
            return None

        if isinstance(raw_bars, list):
            rows = [cls._normalize_bar_row(r) for r in raw_bars if isinstance(r, dict)]
            rows = [
                r for r in rows
                if all(r.get(k) is not None for k in ("open", "high", "low", "close", "volume"))
            ]
            return rows or None

        return None

    def load_universe_symbols(self, symbols: Optional[Iterable[str]] = None) -> List[str]:
        if symbols:
            return [str(s).upper().strip() for s in symbols if str(s).strip()][: self.max_symbols]

        env_symbols = os.getenv("SIGMALYTIC_DISCOVERY_SYMBOLS", "")
        if env_symbols:
            return [s.strip().upper() for s in env_symbols.split(",") if s.strip()][: self.max_symbols]

        if load_russell1000 is None:
            return []

        try:
            loaded = load_russell1000()
            return [str(s).upper().strip() for s in loaded if str(s).strip()][: self.max_symbols]
        except Exception:
            return []

    def build_records_from_universe(self, symbols: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        universe = self.load_universe_symbols(symbols=symbols)
        if not universe or fetch_bars_batch is None:
            return []

        try:
            bars_cache = fetch_bars_batch(universe, timeframe="1Day", limit=self.bar_limit)
        except Exception:
            return []

        records: List[Dict[str, Any]] = []
        for symbol in universe:
            raw = bars_cache.get(symbol) or bars_cache.get(symbol.upper()) if isinstance(bars_cache, dict) else None
            bars = self._normalize_bars(raw)
            if not bars:
                continue
            records.append({"symbol": symbol.upper(), "timeframe": self.timeframe, "bars": bars})
        return records

    def _bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        bars = self._normalize_bars(record.get("bars"))
        if not bars:
            return None
        df = pd.DataFrame(bars)
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            return None
        return df

    def _sister_bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        bars = self._normalize_bars(record.get("sister_bars") or record.get("sector_bars"))
        if not bars:
            return None
        return pd.DataFrame(bars)

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

    def _build_campaign_payload(self, symbol: str, timeframe: str, birth: Dict[str, Any], survival: Dict[str, Any], current_close: Optional[float]) -> Dict[str, Any]:
        now = self._now()
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "current_state": "BIRTH",
            "state_enum": "BIRTH",
            "birth_score": self._safe_float(birth.get("birth_score")),
            "birth_state": str(birth.get("birth_state", "UNKNOWN")),
            "birth_eligible": bool(birth.get("birth_eligible", False)),
            "master_campaign_index": self._safe_float(birth.get("master_campaign_index")),
            "master_verdict": str(birth.get("master_verdict", "UNKNOWN")),
            "campaign_quality": str(birth.get("campaign_quality", "UNKNOWN")),
            "master_survival_score": self._safe_float(survival.get("master_survival_score")),
            "survival_state": str(survival.get("survival_state", "UNKNOWN")),
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

    def _empty_verdict(self, symbol: str, timeframe: str, reason: str, state: str = "NO_BARS") -> Dict[str, Any]:
        return CampaignDiscoveryVerdict(
            symbol=symbol,
            timeframe=timeframe,
            discovered=False,
            reason=reason,
            birth_score=0.0,
            birth_state=state,
            birth_eligible=False,
            master_campaign_index=0.0,
            master_verdict=state,
            campaign_quality="F",
            master_survival_score=0.0,
            survival_state=state,
            survival_grade="F",
            survival_confirmed=False,
            current_state="NO_CAMPAIGN",
            payload={},
            birth_details={},
            survival_details={},
            as_of=self._now(),
        ).to_dict()

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper().strip()
        timeframe = str(record.get("timeframe") or self.timeframe).upper().strip()

        if not symbol:
            return self._empty_verdict("", timeframe, "Missing symbol.", "NO_SYMBOL")

        df = self._load_bars(symbol, timeframe, record=record)
        sister_df = self._load_sister_bars(symbol, timeframe, record=record)

        if df is None or len(df) == 0:
            return self._empty_verdict(symbol, timeframe, "No OHLCV bars supplied or loaded.", "NO_BARS")

        if self.birth_engine is None:
            raise RuntimeError("SignalBirthEngine unavailable.")

        birth = self.birth_engine.evaluate_bars(df, sister_df=sister_df, symbol=symbol)

        if self.survival_engine is not None:
            survival = self.survival_engine.evaluate_bars(df, symbol=symbol, sister_df=sister_df)
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

        try:
            current_close = round(float(df["close"].iloc[-1]), 4)
        except Exception:
            current_close = None

        discovered = birth_score >= self.birth_threshold and mci >= self.mci_threshold and survival_score >= self.survival_threshold

        reason = (
            f"Discovery {'accepted' if discovered else 'rejected'}; "
            f"birth={birth_score}, mci={mci}, survival={survival_score}; "
            f"thresholds birth>={self.birth_threshold}, mci>={self.mci_threshold}, survival>={self.survival_threshold}."
        )

        payload: Dict[str, Any] = {}
        if discovered:
            payload = self._build_campaign_payload(symbol, timeframe, birth, survival, current_close)
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
            "results": results[:100],
            "as_of": self._now(),
        }

    def run_symbols(self, symbols: Iterable[str], timeframe: Optional[str] = None) -> Dict[str, Any]:
        records = self.build_records_from_universe(symbols=symbols)
        return self.run_records(records)

    def run(self, records: Optional[List[Dict[str, Any]]] = None, symbols: Optional[Iterable[str]] = None, timeframe: Optional[str] = None) -> Dict[str, Any]:
        if records:
            return self.run_records(records)
        records = self.build_records_from_universe(symbols=symbols)
        if records:
            return self.run_records(records)
        return {
            "ok": True,
            "engine": "campaign_discovery_engine",
            "records_evaluated": 0,
            "campaigns_discovered": 0,
            "discovered_symbols": [],
            "results": [],
            "message": "No universe symbols or OHLCV bars available.",
            "as_of": self._now(),
        }


def run_campaign_discovery(records: Optional[List[Dict[str, Any]]] = None, symbols: Optional[Iterable[str]] = None, timeframe: str = "DAILY") -> Dict[str, Any]:
    return CampaignDiscoveryEngine(timeframe=timeframe).run(records=records, symbols=symbols, timeframe=timeframe)


CampaignDiscoveryRunner = CampaignDiscoveryEngine


__all__ = [
    "CampaignDiscoveryEngine",
    "CampaignDiscoveryVerdict",
    "CampaignDiscoveryRunner",
    "run_campaign_discovery",
]
