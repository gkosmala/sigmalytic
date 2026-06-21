from fastapi import APIRouter
from typing import Dict, Any
import pandas as pd

from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
from backend.research_engine.livermore_verdict_engine import LivermoreVerdictEngine
from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
from backend.research_engine.master_campaign_index import MasterCampaignIndexEngine
from backend.research_engine.signal_birth_engine import SignalBirthEngine

router = APIRouter(
    prefix="/api/research",
    tags=["research"],
)


@router.get("/status")
def research_status():
    return {
        "wyckoff": True,
        "livermore": True,
        "weis": True,
        "master_campaign_index": True,
        "signal_birth": True,
    }


@router.post("/wyckoff-verdict")
def wyckoff_verdict(payload: Dict[str, Any]):

    df = pd.DataFrame(payload.get("bars", []))

    engine = WyckoffVerdictEngine()

    if hasattr(engine, "evaluate_bars"):
        return engine.evaluate_bars(
            df,
            symbol=payload.get("symbol", ""),
        )

    return {
        "error": "evaluate_bars not found on WyckoffVerdictEngine"
    }


@router.post("/livermore-verdict")
def livermore_verdict(payload: Dict[str, Any]):

    df = pd.DataFrame(payload.get("bars", []))

    sister_bars = payload.get("sister_bars", [])

    sister_df = (
        pd.DataFrame(sister_bars)
        if sister_bars
        else None
    )

    return LivermoreVerdictEngine().evaluate(
        df,
        symbol=payload.get("symbol", ""),
        sister_df=sister_df,
    )


@router.post("/weis-verdict")
def weis_verdict(payload: Dict[str, Any]):

    df = pd.DataFrame(payload.get("bars", []))

    return WeisVerdictEngine().evaluate(
        df,
        symbol=payload.get("symbol", ""),
    )


@router.post("/master-campaign-index")
def master_campaign_index(payload: Dict[str, Any]):

    df = pd.DataFrame(payload.get("bars", []))

    sister_bars = payload.get("sister_bars", [])

    sister_df = (
        pd.DataFrame(sister_bars)
        if sister_bars
        else None
    )

    return MasterCampaignIndexEngine().evaluate_bars(
        df,
        symbol=payload.get("symbol", ""),
        sister_df=sister_df,
    )


@router.post("/signal-birth")
def signal_birth(payload: Dict[str, Any]):

    df = pd.DataFrame(payload.get("bars", []))

    sister_bars = payload.get("sister_bars", [])

    sister_df = (
        pd.DataFrame(sister_bars)
        if sister_bars
        else None
    )

    return SignalBirthEngine().evaluate_bars(
        df,
        sister_df=sister_df,
        symbol=payload.get("symbol", ""),
    )