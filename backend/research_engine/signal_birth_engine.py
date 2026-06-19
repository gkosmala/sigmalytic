# signal_birth_engine.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class SignalBirthResult:
    ok: bool
    status: str
    signals_evaluated: int = 0
    signals_born: int = 0
    campaigns_created: int = 0
    as_of: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "signals_evaluated": self.signals_evaluated,
            "signals_born": self.signals_born,
            "campaigns_created": self.campaigns_created,
            "as_of": self.as_of or datetime.now(timezone.utc).isoformat(),
        }


class SignalBirthEngine:
    def __init__(
        self,
        symbols: Optional[Iterable[str]] = None,
        records: Optional[List[Dict[str, Any]]] = None,
    ):
        self.symbols = list(symbols or [])
        self.records = records or []

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper()
        score = float(
            record.get("edge_score")
            or record.get("score")
            or record.get("campaign_score")
            or record.get("operator_dominance")
            or 0
        )

        state = "NO_BIRTH"
        if score >= 70:
            state = "BIRTH_CANDIDATE"
        elif score >= 55:
            state = "WATCH"

        return {
            "symbol": symbol,
            "birth_state": state,
            "birth_score": round(score, 2),
            "eligible": state == "BIRTH_CANDIDATE",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def run(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        symbols: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        active_records = records if records is not None else self.records
        active_symbols = list(symbols or self.symbols)

        evaluated = []
        if active_records:
            evaluated = [self.evaluate_record(r) for r in active_records]
        elif active_symbols:
            evaluated = [
                {
                    "symbol": str(s).upper(),
                    "birth_state": "WATCH",
                    "birth_score": 0,
                    "eligible": False,
                    "as_of": datetime.now(timezone.utc).isoformat(),
                }
                for s in active_symbols
            ]

        born = [r for r in evaluated if r.get("eligible")]

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
