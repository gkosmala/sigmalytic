# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/historical_attribution_backtest.py
------------------------------------------
Sigmalytic Historical Attribution Backtest — Phase 1

Purpose:
  Run a controlled 50-symbol / 2-year historical attribution test.

What it measures:
  - Direction Accuracy
  - Edge Accuracy: MFE > MAE
  - Tradeable Opportunity Rate: MFE >= 1.5%
  - Strong Opportunity Rate: MFE >= 3.0%
  - Avg MFE
  - Avg MAE
  - Edge Ratio
  - Avg Outcome

Important:
  This is an attribution/research backtest, not an order execution simulator.
  It evaluates whether Sigmalytic-style signals historically created favorable
  path opportunity.

Run from project root:
  python backend/historical_attribution_backtest.py

Optional:
  python backend/historical_attribution_backtest.py --symbols AAPL,MSFT,NVDA,SPY,QQQ --years 2
  python backend/historical_attribution_backtest.py --symbols-file backend/backtest_symbols_50.txt --years 2
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Path setup
# ─────────────────────────────────────────────────────────────────────────────

THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parent
PROJECT_ROOT = BACKEND_DIR.parent

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED = os.getenv("ALPACA_FEED", "sip")

DEFAULT_SYMBOLS_50 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META",
    "GOOGL", "GOOG", "TSLA", "AMD", "NFLX",
    "AVGO", "ORCL", "CRM", "ADBE", "NOW",
    "INTC", "QCOM", "TXN", "MU", "AMAT",
    "JPM", "BAC", "GS", "MS", "C",
    "XLF", "XLK", "XLY", "XLI", "XLE",
    "SPY", "QQQ", "IWM", "DIA", "SMH",
    "GLD", "SLV", "TLT", "HYG", "LQD",
    "WMT", "COST", "HD", "LOW", "MCD",
    "UNH", "LLY", "XOM", "CVX", "CAT",
]

SIGNAL_SCORE_MIN = 55.0
LOOKAHEAD_DAYS = 5
TRADEABLE_MFE_PCT = 1.5
STRONG_MFE_PCT = 3.0


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: int


@dataclass
class SignalResult:
    symbol: str
    signal_date: str
    price: float
    score: float
    status: str
    direction: str
    regime: str
    setup: str
    signal_type: str
    score_bucket: str
    outcome_pct: float
    mfe_pct: float
    mae_pct: float
    direction_correct: bool
    edge_win: bool
    tradeable_opportunity: bool
    strong_opportunity: bool


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _score_bucket(score: float) -> str:
    if score >= 90:
        return "90-100 Elite"
    if score >= 80:
        return "80-89 A"
    if score >= 70:
        return "70-79 B"
    if score >= 60:
        return "60-69 C"
    if score >= 55:
        return "55-59 W"
    return "<55 Ignore"


def _signal_type_from_status(status: str, direction: str) -> str:
    s = (status or "").strip()
    d = (direction or "").strip().upper()

    if "Short" in s:
        return s

    if d == "BEARISH":
        if "Trigger" in s:
            return "Short Trigger"
        return "Short Armed"

    if s:
        return s

    return "Armed"


def _is_bullish_signal(signal_type: str, direction: str) -> bool:
    if "Short" in (signal_type or ""):
        return False
    if (direction or "").upper() == "BEARISH":
        return False
    return True


def _extract_result_field(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def _make_market_data(symbol: str, bars: list[Bar], idx: int):
    """
    Build ConfluenceEngine MarketData using only information available
    through the current historical day.
    """
    from confluence_engine import MarketData

    current = bars[idx]
    prev = bars[idx - 1] if idx > 0 else current

    lookback = bars[max(0, idx - 20):idx + 1]
    volumes = [b.v for b in lookback if b.v is not None]
    avg_volume = int(sum(volumes) / max(len(volumes), 1)) or 1

    highs = [b.h for b in lookback]
    lows = [b.l for b in lookback]
    atr = None
    if len(lookback) >= 2:
        true_ranges = []
        for j in range(1, len(lookback)):
            b = lookback[j]
            p = lookback[j - 1]
            true_ranges.append(max(
                b.h - b.l,
                abs(b.h - p.c),
                abs(b.l - p.c),
            ))
        atr = sum(true_ranges) / max(len(true_ranges), 1)

    # Approx daily VWAP using typical price. Better than close-only,
    # still fully historical and non-lookahead.
    vwap = (current.h + current.l + current.c) / 3.0

    return MarketData(
        symbol=symbol,
        price=current.c,
        previous_close=prev.c,
        day_open=current.o,
        day_high=current.h,
        day_low=current.l,
        volume=int(current.v or 0),
        avg_volume=avg_volume,
        vwap=vwap,
        atr=atr,
        benchmark_change_pct=None,
    )


def _empty_options_data():
    from confluence_engine import OptionsData
    return OptionsData()


def fetch_daily_bars(symbol: str, years: int, extra_days: int = 30) -> list[Bar]:
    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_API_SECRET are not configured.")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years + extra_days)

    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
    params = {
        "timeframe": "1Day",
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
        "limit": 10000,
        "adjustment": "raw",
        "feed": ALPACA_FEED,
        "sort": "asc",
    }

    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{symbol} Alpaca error {r.status_code}: {r.text[:300]}")

    raw = r.json()
    rows = raw.get("bars", []) if isinstance(raw, dict) else []

    bars: list[Bar] = []
    for b in rows:
        try:
            bars.append(Bar(
                t=str(b.get("t", "")),
                o=float(b["o"]),
                h=float(b["h"]),
                l=float(b["l"]),
                c=float(b["c"]),
                v=int(b.get("v", 0) or 0),
            ))
        except Exception:
            continue

    return bars


def compute_path_outcome(
    signal_type: str,
    direction: str,
    entry: float,
    future_bars: list[Bar],
) -> tuple[float, float, float, bool, bool, bool, bool]:
    """
    Returns:
      outcome_pct, mfe_pct, mae_pct, direction_correct,
      edge_win, tradeable_opportunity, strong_opportunity
    """
    if not future_bars or entry <= 0:
        return 0.0, 0.0, 0.0, False, False, False, False

    bullish = _is_bullish_signal(signal_type, direction)

    final_close = future_bars[-1].c
    max_high = max(b.h for b in future_bars)
    min_low = min(b.l for b in future_bars)

    if bullish:
        outcome_pct = (final_close - entry) / entry * 100.0
        mfe_pct = max(0.0, (max_high - entry) / entry * 100.0)
        mae_pct = max(0.0, (entry - min_low) / entry * 100.0)
        direction_correct = final_close > entry
    else:
        outcome_pct = (entry - final_close) / entry * 100.0
        mfe_pct = max(0.0, (entry - min_low) / entry * 100.0)
        mae_pct = max(0.0, (max_high - entry) / entry * 100.0)
        direction_correct = final_close < entry

    edge_win = mfe_pct > mae_pct
    tradeable = mfe_pct >= TRADEABLE_MFE_PCT
    strong = mfe_pct >= STRONG_MFE_PCT

    return (
        round(outcome_pct, 2),
        round(mfe_pct, 2),
        round(mae_pct, 2),
        bool(direction_correct),
        bool(edge_win),
        bool(tradeable),
        bool(strong),
    )


def summarize_group(rows: list[SignalResult]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {}

    direction_correct = sum(1 for r in rows if r.direction_correct)
    edge_wins = sum(1 for r in rows if r.edge_win)
    tradeable = sum(1 for r in rows if r.tradeable_opportunity)
    strong = sum(1 for r in rows if r.strong_opportunity)

    avg_mfe = sum(r.mfe_pct for r in rows) / n
    avg_mae = sum(r.mae_pct for r in rows) / n
    avg_outcome = sum(r.outcome_pct for r in rows) / n
    edge_ratio = avg_mfe / max(avg_mae, 0.01)

    return {
        "signals": n,
        "direction_accuracy": round(direction_correct / n * 100.0, 1),
        "edge_accuracy": round(edge_wins / n * 100.0, 1),
        "tradeable_opportunity_rate": round(tradeable / n * 100.0, 1),
        "strong_opportunity_rate": round(strong / n * 100.0, 1),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "edge_ratio": round(edge_ratio, 2),
        "avg_outcome_pct": round(avg_outcome, 2),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def group_summary(results: list[SignalResult], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[SignalResult]] = {}
    for r in results:
        key = str(getattr(r, field) or "Unknown")
        buckets.setdefault(key, []).append(r)

    rows = []
    for key, group in buckets.items():
        s = summarize_group(group)
        rows.append({"group": key, **s})

    rows.sort(key=lambda x: (x.get("signals", 0), x.get("edge_ratio", 0)), reverse=True)
    return rows


def run_backtest(symbols: list[str], years: int, lookahead_days: int, output_dir: Path) -> None:
    from confluence_engine import ConfluenceEngine

    engine = ConfluenceEngine()
    all_results: list[SignalResult] = []

    print(f"Starting historical attribution backtest")
    print(f"Symbols: {len(symbols)}")
    print(f"Years: {years}")
    print(f"Lookahead days: {lookahead_days}")
    print(f"Output: {output_dir}")
    print("-" * 72)

    for idx_sym, symbol in enumerate(symbols, start=1):
        try:
            print(f"[{idx_sym}/{len(symbols)}] Fetching {symbol}...")
            bars = fetch_daily_bars(symbol, years=years, extra_days=60)
            if len(bars) < 80:
                print(f"  skipped {symbol}: only {len(bars)} bars")
                continue

            symbol_results = 0

            # Start after 30 bars so ATR/avg-volume are meaningful.
            # Stop before lookahead window so no forward data leaks into signal calc.
            for i in range(30, len(bars) - lookahead_days):
                market = _make_market_data(symbol, bars, i)
                result = engine.evaluate(market, _empty_options_data())

                score = _safe_float(_extract_result_field(result, "score", 0))
                if score < SIGNAL_SCORE_MIN:
                    continue

                status = str(_extract_result_field(result, "status", "Armed") or "Armed")
                direction = str(_extract_result_field(result, "direction", "BULLISH") or "BULLISH")
                regime = str(_extract_result_field(result, "regime", "Unknown") or "Unknown")
                setup = str(_extract_result_field(result, "setup", "") or _extract_result_field(result, "setup_type", "") or "Unknown")

                signal_type = _signal_type_from_status(status, direction)
                entry = bars[i].c
                future = bars[i + 1:i + 1 + lookahead_days]

                (
                    outcome_pct,
                    mfe_pct,
                    mae_pct,
                    direction_correct,
                    edge_win,
                    tradeable,
                    strong,
                ) = compute_path_outcome(signal_type, direction, entry, future)

                all_results.append(SignalResult(
                    symbol=symbol,
                    signal_date=bars[i].t,
                    price=entry,
                    score=round(score, 2),
                    status=status,
                    direction=direction,
                    regime=regime,
                    setup=setup,
                    signal_type=signal_type,
                    score_bucket=_score_bucket(score),
                    outcome_pct=outcome_pct,
                    mfe_pct=mfe_pct,
                    mae_pct=mae_pct,
                    direction_correct=direction_correct,
                    edge_win=edge_win,
                    tradeable_opportunity=tradeable,
                    strong_opportunity=strong,
                ))
                symbol_results += 1

            print(f"  signals: {symbol_results}")
            time.sleep(0.25)

        except Exception as e:
            print(f"  ERROR {symbol}: {e}")

    output_dir.mkdir(parents=True, exist_ok=True)

    detail_rows = [r.__dict__ for r in all_results]
    write_csv(output_dir / "historical_signals_detail.csv", detail_rows)

    overall = summarize_group(all_results)
    write_csv(output_dir / "summary_overall.csv", [{"group": "ALL", **overall}] if overall else [])

    for field, filename in [
        ("symbol", "summary_by_symbol.csv"),
        ("score_bucket", "summary_by_score_bucket.csv"),
        ("regime", "summary_by_regime.csv"),
        ("setup", "summary_by_setup.csv"),
        ("signal_type", "summary_by_signal_type.csv"),
        ("direction", "summary_by_direction.csv"),
    ]:
        write_csv(output_dir / filename, group_summary(all_results, field))

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "years": years,
        "lookahead_days": lookahead_days,
        "signal_score_min": SIGNAL_SCORE_MIN,
        "tradeable_mfe_pct": TRADEABLE_MFE_PCT,
        "strong_mfe_pct": STRONG_MFE_PCT,
        "overall": overall,
        "signal_count": len(all_results),
        "output_files": [
            "historical_signals_detail.csv",
            "summary_overall.csv",
            "summary_by_symbol.csv",
            "summary_by_score_bucket.csv",
            "summary_by_regime.csv",
            "summary_by_setup.csv",
            "summary_by_signal_type.csv",
            "summary_by_direction.csv",
        ],
    }

    (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("-" * 72)
    print("Backtest complete")
    print(json.dumps(overall, indent=2))
    print(f"Files written to: {output_dir}")


def parse_symbols(args: argparse.Namespace) -> list[str]:
    if args.symbols:
        return [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.symbols_file:
        path = Path(args.symbols_file)
        raw = path.read_text(encoding="utf-8", errors="replace")
        syms = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for part in line.replace(",", " ").split():
                if part.strip():
                    syms.append(part.strip().upper())
        return syms[:args.max_symbols]

    return DEFAULT_SYMBOLS_50[:args.max_symbols]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--symbols-file", default="", help="Path to file containing symbols")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--lookahead-days", type=int, default=LOOKAHEAD_DAYS)
    parser.add_argument("--max-symbols", type=int, default=50)
    parser.add_argument("--output-dir", default="backtests/phase1_50_symbols_2_years")
    args = parser.parse_args()

    symbols = parse_symbols(args)
    if not symbols:
        raise RuntimeError("No symbols supplied.")

    output_dir = PROJECT_ROOT / args.output_dir

    run_backtest(
        symbols=symbols,
        years=args.years,
        lookahead_days=args.lookahead_days,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    main()

