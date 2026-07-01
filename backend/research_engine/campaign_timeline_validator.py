"""
SAVE AS:
backend/research_engine/campaign_timeline_validator.py

Sigmalytic V2
Campaign Timeline Validator

Purpose:
Scan a full historical window bar-by-bar and let the V2 engines determine
the first campaign birth / early campaign / potential birth date.

This replaces arbitrary campaign windows.

Default timeline:
2022-01-01 through 2026-06-19

Tests:
- Wyckoff Verdict Engine
- Livermore Verdict Engine
- Weis Verdict Engine
- Master Campaign Index
- Signal Birth Engine

Outputs:
backend/research_engine/validation_outputs/campaign_timeline_results.json
backend/research_engine/validation_outputs/campaign_timeline_results.csv
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backend.research_engine.signal_birth_engine import SignalBirthEngine
from backend.research_engine.master_campaign_index import MasterCampaignIndexEngine


DEFAULT_START = "2022-01-01"
DEFAULT_END = "2026-06-19"


@dataclass
class TimelineCase:
    symbol: str
    sister_symbol: str
    start: str
    end: str
    thesis: str


DEFAULT_CASES: List[TimelineCase] = [
    TimelineCase("NVDA", "SMH", DEFAULT_START, DEFAULT_END, "AI/semiconductor campaign"),
    TimelineCase("META", "QQQ", DEFAULT_START, DEFAULT_END, "mega-cap recovery campaign"),
    TimelineCase("TSLA", "QQQ", DEFAULT_START, DEFAULT_END, "EV campaign"),
    TimelineCase("PLTR", "QQQ", DEFAULT_START, DEFAULT_END, "AI/software campaign"),
    TimelineCase("MSTR", "QQQ", DEFAULT_START, DEFAULT_END, "bitcoin proxy campaign"),
    TimelineCase("CMG", "XLY", DEFAULT_START, DEFAULT_END, "consumer leadership campaign"),
    TimelineCase("NFLX", "QQQ", DEFAULT_START, DEFAULT_END, "streaming recovery campaign"),
    TimelineCase("AAPL", "QQQ", DEFAULT_START, DEFAULT_END, "large-cap campaign"),
    TimelineCase("MSFT", "QQQ", DEFAULT_START, DEFAULT_END, "AI/software mega-cap campaign"),
    TimelineCase("SMCI", "SMH", DEFAULT_START, DEFAULT_END, "AI infrastructure campaign"),
    TimelineCase("AMD", "SMH", DEFAULT_START, DEFAULT_END, "semiconductor campaign"),
    TimelineCase("AVGO", "SMH", DEFAULT_START, DEFAULT_END, "semiconductor leadership campaign"),
    TimelineCase("LLY", "XLV", DEFAULT_START, DEFAULT_END, "pharma leadership campaign"),
    TimelineCase("NVO", "XLV", DEFAULT_START, DEFAULT_END, "GLP-1 pharma campaign"),
    TimelineCase("CELH", "XLP", DEFAULT_START, DEFAULT_END, "consumer growth campaign"),
]


def make_json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [make_json_safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    try:
        if pd.isna(obj) and not isinstance(obj, str):
            return None
    except Exception:
        pass
    return obj


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

    request = urllib.request.Request(url, headers=_alpaca_headers())

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = []
    for bar in payload.get("bars", []):
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

    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.set_index("timestamp")
    return df[["open", "high", "low", "close", "volume"]].dropna()


def future_return(df: pd.DataFrame, idx: int, days: int) -> Optional[float]:
    if idx < 0 or idx >= len(df):
        return None

    future_idx = min(len(df) - 1, idx + days)
    start_price = float(df["close"].iloc[idx])
    end_price = float(df["close"].iloc[future_idx])

    if start_price <= 0:
        return None

    return round(((end_price - start_price) / start_price) * 100.0, 2)


def find_first_event(
    timeline: List[Dict[str, Any]],
    predicate,
) -> Optional[Dict[str, Any]]:
    for row in timeline:
        try:
            if predicate(row):
                return row
        except Exception:
            continue
    return None


def evaluate_timeline_case(
    case: TimelineCase,
    min_bars: int = 90,
) -> Dict[str, Any]:
    symbol = case.symbol.upper()
    sister_symbol = case.sister_symbol.upper()

    df = fetch_alpaca_daily_bars(symbol, case.start, case.end)

    if df.empty or len(df) < min_bars:
        return {
            "symbol": symbol,
            "sister_symbol": sister_symbol,
            "status": "FAILED_NO_DATA",
            "error": "Insufficient OHLCV bars returned.",
            "start": case.start,
            "end": case.end,
            "bars": len(df),
            "thesis": case.thesis,
        }

    try:
        sister_df_full = fetch_alpaca_daily_bars(sister_symbol, case.start, case.end)
    except Exception:
        sister_df_full = None

    signal_engine = SignalBirthEngine()
    mci_engine = MasterCampaignIndexEngine()

    timeline: List[Dict[str, Any]] = []

    # Start after enough bars exist for 60-bar resistance and campaign layers.
    for i in range(min_bars, len(df)):
        current_df = df.iloc[: i + 1].copy()

        sister_slice = None
        if sister_df_full is not None and not sister_df_full.empty:
            sister_slice = sister_df_full.loc[
                sister_df_full.index <= current_df.index[-1]
            ].copy()
            if len(sister_slice) < 20:
                sister_slice = None

        signal = signal_engine.evaluate_bars(
            current_df,
            sister_df=sister_slice,
            symbol=symbol,
        )

        mci = mci_engine.evaluate_bars(
            current_df,
            symbol=symbol,
            sister_df=sister_slice,
        )

        row = {
            "date": current_df.index[-1].date().isoformat(),
            "symbol": symbol,
            "close": round(float(current_df["close"].iloc[-1]), 4),
            "birth_score": signal.get("birth_score"),
            "birth_state": signal.get("birth_state"),
            "birth_eligible": signal.get("birth_eligible"),
            "master_campaign_index": signal.get("master_campaign_index"),
            "master_verdict": signal.get("master_verdict"),
            "campaign_quality": signal.get("campaign_quality"),
            "confirmation_count": signal.get("confirmation_count"),
            "agreement_score": signal.get("agreement_score"),
            "wyckoff_score": mci.get("wyckoff_score"),
            "wyckoff_verdict": mci.get("wyckoff_verdict"),
            "livermore_score": mci.get("livermore_score"),
            "livermore_verdict": mci.get("livermore_verdict"),
            "weis_score": mci.get("weis_score"),
            "weis_verdict": mci.get("weis_verdict"),
        }

        timeline.append(row)

    first_potential_birth = find_first_event(
        timeline,
        lambda r: str(r.get("birth_state")) in {
            "POTENTIAL_BIRTH",
            "EARLY_CAMPAIGN",
            "CAMPAIGN_BIRTH",
        },
    )

    first_early_campaign = find_first_event(
        timeline,
        lambda r: str(r.get("birth_state")) in {
            "EARLY_CAMPAIGN",
            "CAMPAIGN_BIRTH",
        },
    )

    first_campaign_birth = find_first_event(
        timeline,
        lambda r: str(r.get("birth_state")) == "CAMPAIGN_BIRTH",
    )

    first_mci_45 = find_first_event(
        timeline,
        lambda r: float(r.get("master_campaign_index") or 0) >= 45,
    )

    first_mci_65 = find_first_event(
        timeline,
        lambda r: float(r.get("master_campaign_index") or 0) >= 65,
    )

    first_two_confirmations = find_first_event(
        timeline,
        lambda r: int(r.get("confirmation_count") or 0) >= 2,
    )

    # Index map for forward returns
    date_to_idx = {
        idx.date().isoformat(): n
        for n, idx in enumerate(df.index)
    }

    def enrich_event(event: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not event:
            return None

        idx = date_to_idx.get(event["date"])
        if idx is None:
            return event

        out = dict(event)
        out["return_30d"] = future_return(df, idx, 30)
        out["return_60d"] = future_return(df, idx, 60)
        out["return_90d"] = future_return(df, idx, 90)
        out["return_180d"] = future_return(df, idx, 180)
        out["return_to_end"] = future_return(df, idx, len(df) - idx - 1)
        return out

    first_potential_birth = enrich_event(first_potential_birth)
    first_early_campaign = enrich_event(first_early_campaign)
    first_campaign_birth = enrich_event(first_campaign_birth)
    first_mci_45 = enrich_event(first_mci_45)
    first_mci_65 = enrich_event(first_mci_65)
    first_two_confirmations = enrich_event(first_two_confirmations)

    start_close = float(df["close"].iloc[0])
    end_close = float(df["close"].iloc[-1])
    total_return = round(((end_close - start_close) / max(start_close, 1.0)) * 100.0, 2)

    last = timeline[-1] if timeline else {}

    return {
        "symbol": symbol,
        "sister_symbol": sister_symbol,
        "status": "OK",
        "start": case.start,
        "end": case.end,
        "bars": len(df),
        "thesis": case.thesis,
        "total_return_pct": total_return,
        "first_potential_birth": first_potential_birth,
        "first_early_campaign": first_early_campaign,
        "first_campaign_birth": first_campaign_birth,
        "first_mci_45": first_mci_45,
        "first_mci_65": first_mci_65,
        "first_two_confirmations": first_two_confirmations,
        "last_score": last,
        "timeline_tail": timeline[-20:],
    }


def write_outputs(results: List[Dict[str, Any]]) -> Dict[str, str]:
    safe_results = make_json_safe(results)

    out_dir = ROOT / "backend" / "research_engine" / "validation_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "campaign_timeline_results.json"
    csv_path = out_dir / "campaign_timeline_results.csv"

    json_path.write_text(json.dumps(safe_results, indent=2), encoding="utf-8")

    fields = [
        "symbol",
        "sister_symbol",
        "status",
        "start",
        "end",
        "bars",
        "total_return_pct",
        "first_potential_birth_date",
        "first_potential_birth_score",
        "first_potential_birth_state",
        "first_potential_birth_30d",
        "first_potential_birth_90d",
        "first_potential_birth_180d",
        "first_early_campaign_date",
        "first_campaign_birth_date",
        "first_mci_45_date",
        "first_mci_65_date",
        "first_two_confirmations_date",
        "last_birth_score",
        "last_birth_state",
        "last_mci",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for row in safe_results:
            fpb = row.get("first_potential_birth") or {}
            fec = row.get("first_early_campaign") or {}
            fcb = row.get("first_campaign_birth") or {}
            fm45 = row.get("first_mci_45") or {}
            fm65 = row.get("first_mci_65") or {}
            ftc = row.get("first_two_confirmations") or {}
            last = row.get("last_score") or {}

            writer.writerow(
                {
                    "symbol": row.get("symbol"),
                    "sister_symbol": row.get("sister_symbol"),
                    "status": row.get("status"),
                    "start": row.get("start"),
                    "end": row.get("end"),
                    "bars": row.get("bars"),
                    "total_return_pct": row.get("total_return_pct"),
                    "first_potential_birth_date": fpb.get("date"),
                    "first_potential_birth_score": fpb.get("birth_score"),
                    "first_potential_birth_state": fpb.get("birth_state"),
                    "first_potential_birth_30d": fpb.get("return_30d"),
                    "first_potential_birth_90d": fpb.get("return_90d"),
                    "first_potential_birth_180d": fpb.get("return_180d"),
                    "first_early_campaign_date": fec.get("date"),
                    "first_campaign_birth_date": fcb.get("date"),
                    "first_mci_45_date": fm45.get("date"),
                    "first_mci_65_date": fm65.get("date"),
                    "first_two_confirmations_date": ftc.get("date"),
                    "last_birth_score": last.get("birth_score"),
                    "last_birth_state": last.get("birth_state"),
                    "last_mci": last.get("master_campaign_index"),
                }
            )

    return {"json": str(json_path), "csv": str(csv_path)}


def run_timeline_validation(
    cases: Optional[List[TimelineCase]] = None,
    sleep_seconds: float = 0.25,
) -> Dict[str, Any]:
    cases = cases or DEFAULT_CASES
    results: List[Dict[str, Any]] = []

    for case in cases:
        print(f"Timeline validating {case.symbol} {case.start} -> {case.end}")
        try:
            result = evaluate_timeline_case(case)
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
    potential_births = [r for r in ok if r.get("first_potential_birth")]
    early_campaigns = [r for r in ok if r.get("first_early_campaign")]
    full_births = [r for r in ok if r.get("first_campaign_birth")]

    return {
        "summary": {
            "ok": True,
            "cases": len(cases),
            "successful_cases": len(ok),
            "potential_births_detected": len(potential_births),
            "early_campaigns_detected": len(early_campaigns),
            "full_births_detected": len(full_births),
            "potential_birth_symbols": [r.get("symbol") for r in potential_births],
            "early_campaign_symbols": [r.get("symbol") for r in early_campaigns],
            "full_birth_symbols": [r.get("symbol") for r in full_births],
            "outputs": paths,
            "as_of": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
    }


if __name__ == "__main__":
    report = run_timeline_validation()
    print(json.dumps(report["summary"], indent=2))
