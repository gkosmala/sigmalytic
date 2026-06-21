"""
SAVE AS:
backend/research_engine/campaign_validation_runner.py

Sigmalytic V2
Historical Campaign Validation Runner

Purpose:
Validate the full V2 campaign-birth chain against known historical campaign winners.

It tests:
- Wyckoff Verdict Engine
- Livermore Verdict Engine
- Weis Verdict Engine
- Master Campaign Index
- Signal Birth Engine

Default validation set:
NVDA, META, TSLA, PLTR, MSTR, CMG, NFLX, AAPL, MSFT, SMCI, AMD, AVGO, LLY, NVO, CELH

Data source:
- Alpaca historical bars using environment variables:
    ALPACA_API_KEY
    ALPACA_SECRET_KEY
    ALPACA_DATA_FEED optional, default "iex"

Run:
    py -3 backend/research_engine/campaign_validation_runner.py

Outputs:
    backend/research_engine/validation_outputs/campaign_validation_results.json
    backend/research_engine/validation_outputs/campaign_validation_results.csv
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np


# Allow running this file directly from project root or from backend folder.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
from backend.research_engine.livermore_verdict_engine import LivermoreVerdictEngine
from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
from backend.research_engine.master_campaign_index import MasterCampaignIndexEngine
from backend.research_engine.signal_birth_engine import SignalBirthEngine


@dataclass
class ValidationCase:
    symbol: str
    sister_symbol: str
    start: str
    end: str
    thesis: str


DEFAULT_CASES: List[ValidationCase] = [
    ValidationCase("NVDA", "SMH", "2022-10-01", "2023-06-30", "AI/semiconductor institutional campaign emergence"),
    ValidationCase("META", "QQQ", "2022-10-01", "2023-06-30", "post-capitulation mega-cap recovery campaign"),
    ValidationCase("TSLA", "QQQ", "2019-06-01", "2020-02-29", "pre-2020 momentum campaign birth"),
    ValidationCase("PLTR", "QQQ", "2023-04-01", "2024-03-31", "AI/software institutional campaign"),
    ValidationCase("MSTR", "BTCUSD", "2023-01-01", "2024-03-31", "bitcoin proxy institutional campaign"),
    ValidationCase("CMG", "XLY", "2022-10-01", "2023-08-31", "consumer discretionary leadership campaign"),
    ValidationCase("NFLX", "QQQ", "2022-06-01", "2023-06-30", "streaming recovery campaign"),
    ValidationCase("AAPL", "QQQ", "2019-01-01", "2020-02-29", "large-cap leadership campaign"),
    ValidationCase("MSFT", "QQQ", "2022-10-01", "2023-07-31", "AI/software mega-cap campaign"),
    ValidationCase("SMCI", "SMH", "2023-01-01", "2024-03-31", "AI server infrastructure campaign"),
    ValidationCase("AMD", "SMH", "2023-01-01", "2024-03-31", "semiconductor campaign"),
    ValidationCase("AVGO", "SMH", "2023-01-01", "2024-03-31", "semiconductor leadership campaign"),
    ValidationCase("LLY", "XLV", "2022-06-01", "2023-12-31", "pharma leadership campaign"),
    ValidationCase("NVO", "XLV", "2022-06-01", "2023-12-31", "GLP-1 pharma campaign"),
    ValidationCase("CELH", "XLP", "2022-01-01", "2023-09-30", "consumer growth campaign"),
]


def _alpaca_headers() -> Dict[str, str]:
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")

    if not key or not secret:
        raise RuntimeError(
            "Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY."
        )

    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def fetch_alpaca_daily_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily bars from Alpaca Market Data API.
    Uses stock bars endpoint. Crypto proxy symbols may fail unless supported by account/feed.
    """
    feed = os.getenv("ALPACA_DATA_FEED", "iex")

    params = {
        "timeframe": "1Day",
        "start": f"{start}T00:00:00Z",
        "end": f"{end}T23:59:59Z",
        "adjustment": "split",
        "feed": feed,
        "limit": 10000,
    }

    query = urllib.parse.urlencode(params)
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars?{query}"

    req = urllib.request.Request(url, headers=_alpaca_headers())

    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    bars = payload.get("bars", [])

    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    rows = []
    for bar in bars:
        rows.append(
            {
                "timestamp": bar.get("t"),
                "open": bar.get("o"),
                "high": bar.get("h"),
                "low": bar.get("l"),
                "close": bar.get("c"),
                "volume": bar.get("v"),
            }
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.set_index("timestamp")
    return df[["open", "high", "low", "close", "volume"]].dropna()


def evaluate_case(case: ValidationCase) -> Dict[str, Any]:
    symbol = case.symbol.upper()
    sister_symbol = case.sister_symbol.upper()

    df = fetch_alpaca_daily_bars(symbol, case.start, case.end)

    sister_df = None
    try:
        sister_df = fetch_alpaca_daily_bars(sister_symbol, case.start, case.end)
    except Exception:
        sister_df = None

    if df.empty or len(df) < 80:
        return {
            "symbol": symbol,
            "sister_symbol": sister_symbol,
            "status": "FAILED_NO_DATA",
            "start": case.start,
            "end": case.end,
            "thesis": case.thesis,
            "error": "Insufficient OHLCV bars returned.",
        }

    wyckoff = WyckoffVerdictEngine().evaluate_bars(df, symbol=symbol)
    livermore = LivermoreVerdictEngine().evaluate(df, symbol=symbol, sister_df=sister_df)
    weis = WeisVerdictEngine().evaluate(df, symbol=symbol)
    master = MasterCampaignIndexEngine().evaluate_bars(df, symbol=symbol, sister_df=sister_df)
    birth = SignalBirthEngine().evaluate_bars(df, symbol=symbol, sister_df=sister_df)

    start_close = float(df["close"].iloc[0])
    end_close = float(df["close"].iloc[-1])
    forward_return_pct = ((end_close - start_close) / max(start_close, 1.0)) * 100.0

    return {
        "symbol": symbol,
        "sister_symbol": sister_symbol,
        "status": "OK",
        "start": case.start,
        "end": case.end,
        "bars": len(df),
        "thesis": case.thesis,
        "forward_return_pct": round(forward_return_pct, 2),
        "wyckoff_score": wyckoff.get("wyckoff_score"),
        "wyckoff_verdict": wyckoff.get("verdict"),
        "wyckoff_phase": wyckoff.get("phase"),
        "livermore_score": livermore.get("livermore_score"),
        "livermore_verdict": livermore.get("verdict"),
        "weis_score": weis.get("weis_score"),
        "weis_verdict": weis.get("verdict"),
        "master_campaign_index": master.get("master_campaign_index"),
        "master_verdict": master.get("verdict"),
        "campaign_quality": master.get("campaign_quality"),
        "confirmation_count": master.get("confirmation_count"),
        "agreement_score": master.get("agreement_score"),
        "birth_score": birth.get("birth_score"),
        "birth_state": birth.get("birth_state"),
        "birth_eligible": birth.get("birth_eligible"),
        "birth_explanation": birth.get("explanation"),
        "details": {
            "wyckoff": wyckoff,
            "livermore": livermore,
            "weis": weis,
            "master": master,
            "signal_birth": birth,
        },
    }



def make_json_safe(obj):
    """
    Convert pandas/numpy objects into plain Python objects so json.dumps works.
    """
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_json_safe(v) for v in obj]

    if isinstance(obj, tuple):
        return [make_json_safe(v) for v in obj]

    if isinstance(obj, (np.integer,)):
        return int(obj)

    if isinstance(obj, (np.floating,)):
        return float(obj)

    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()

    if pd.isna(obj) if not isinstance(obj, (dict, list, tuple, str)) else False:
        return None

    return obj


def write_outputs(results: List[Dict[str, Any]]) -> Dict[str, str]:
    out_dir = ROOT / "backend" / "research_engine" / "validation_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "campaign_validation_results.json"
    csv_path = out_dir / "campaign_validation_results.csv"

    safe_results = make_json_safe(results)
    json_path.write_text(json.dumps(safe_results, indent=2), encoding="utf-8")

    flat_fields = [
        "symbol",
        "sister_symbol",
        "status",
        "start",
        "end",
        "bars",
        "forward_return_pct",
        "wyckoff_score",
        "wyckoff_verdict",
        "wyckoff_phase",
        "livermore_score",
        "livermore_verdict",
        "weis_score",
        "weis_verdict",
        "master_campaign_index",
        "master_verdict",
        "campaign_quality",
        "confirmation_count",
        "agreement_score",
        "birth_score",
        "birth_state",
        "birth_eligible",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=flat_fields)
        writer.writeheader()
        for row in safe_results:
            writer.writerow({field: row.get(field) for field in flat_fields})

    return {
        "json": str(json_path),
        "csv": str(csv_path),
    }


def run_validation(cases: Optional[List[ValidationCase]] = None, sleep_seconds: float = 0.25) -> Dict[str, Any]:
    cases = cases or DEFAULT_CASES
    results = []

    for case in cases:
        print(f"Validating {case.symbol} vs {case.sister_symbol} {case.start} -> {case.end}")
        try:
            result = evaluate_case(case)
        except Exception as exc:
            result = {
                "symbol": case.symbol,
                "sister_symbol": case.sister_symbol,
                "status": "ERROR",
                "start": case.start,
                "end": case.end,
                "thesis": case.thesis,
                "error": str(exc),
            }

        results.append(result)
        time.sleep(sleep_seconds)

    paths = write_outputs(results)

    ok = [r for r in results if r.get("status") == "OK"]
    births = [r for r in ok if r.get("birth_eligible") is True]

    summary = {
        "ok": True,
        "cases": len(cases),
        "successful_cases": len(ok),
        "births_detected": len(births),
        "birth_symbols": [r.get("symbol") for r in births],
        "outputs": paths,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "summary": summary,
        "results": results,
    }


if __name__ == "__main__":
    report = run_validation()
    print(json.dumps(report["summary"], indent=2))
