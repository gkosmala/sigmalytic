#!/usr/bin/env python3
"""
Sigmalytic Qualified Long Signal Audit

Purpose
-------
Tests the directional accuracy of ONLY qualified long signals.

Core long qualification rules from Greg/Sigmalytic:
1) 2-hour Relative Strength score must be >= 50 first.
2) Daily Relative Strength score must be >= 20 and pointing higher.
3) Long-side structure only.
4) Baseline grade must be at least C.
5) Results are measured across multiple holding windows, not only 10 days.

Outputs
-------
backend/audit_outputs/qualified_long_signal_rows.csv
backend/audit_outputs/qualified_long_signal_summary.json
backend/audit_outputs/qualified_long_signal_summary.csv

Environment
-----------
Requires Alpaca market data credentials:
ALPACA_API_KEY
ALPACA_API_SECRET
Optional:
ALPACA_FEED=sip or iex

Example
-------
python backend/qualified_long_signal_audit.py --symbols AAPL,MSFT,NVDA,GOOG,SPY --years 2
python backend/qualified_long_signal_audit.py --symbols-file backend/data/active_universe.csv --limit 1500 --years 2
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import requests
except Exception as exc:  # pragma: no cover
    raise SystemExit("This script requires requests. Install with: pip install requests") from exc


ALPACA_BASE_URL = "https://data.alpaca.markets"
DEFAULT_BENCHMARK = "SPY"
DEFAULT_HORIZONS = [1, 2, 3, 5, 10, 20, 40, 60, 90]
DEFAULT_OUTPUT_DIR = Path("backend/audit_outputs")

LONG_SETUP_TYPES = {
    "Compression Breakout Candidate",
    "Volatility Expansion Candidate",
    "Trend Continuation",
}

EXCLUDED_SETUP_TYPES = {
    "Distribution",
    "Breakdown Risk",
    "Low Edge - Avoid",
    "Monitoring",
    "Avoid",
}

GRADE_ORDER = {
    "A+": 10,
    "A": 9,
    "A-": 8,
    "B+": 7,
    "B": 6,
    "B-": 5,
    "C+": 4,
    "C": 3,
    "C-": 2,
    "D": 1,
    "F": 0,
}


@dataclass
class Bar:
    t: str
    dt: datetime
    date: str
    o: float
    h: float
    l: float
    c: float
    v: float


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _headers() -> Dict[str, str]:
    key = _env("ALPACA_API_KEY") or _env("APCA_API_KEY_ID")
    secret = _env("ALPACA_API_SECRET") or _env("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Missing Alpaca credentials. Set ALPACA_API_KEY and ALPACA_API_SECRET.")
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _clean_symbol(s: str) -> str:
    return str(s or "").strip().upper().replace("/", ".")


def _as_bar(raw: Dict[str, Any]) -> Optional[Bar]:
    try:
        dt = _parse_dt(raw["t"])
        return Bar(
            t=str(raw["t"]),
            dt=dt,
            date=dt.date().isoformat(),
            o=float(raw["o"]),
            h=float(raw["h"]),
            l=float(raw["l"]),
            c=float(raw["c"]),
            v=float(raw.get("v", 0) or 0),
        )
    except Exception:
        return None


def fetch_bars(symbol: str, timeframe: str, start: str, end: str, feed: str, adjustment: str = "raw") -> List[Bar]:
    """Fetch Alpaca bars with pagination."""
    symbol = _clean_symbol(symbol)
    headers = _headers()
    bars: List[Bar] = []
    page_token: Optional[str] = None

    while True:
        params: Dict[str, Any] = {
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "feed": feed,
            "adjustment": adjustment,
            "sort": "asc",
            "limit": 10000,
        }
        if page_token:
            params["page_token"] = page_token

        url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code != 200:
            print(f"WARN {symbol} {timeframe}: HTTP {r.status_code} {r.text[:160]}", file=sys.stderr)
            break

        data = r.json()
        raw_bars = data.get("bars") or []
        for raw in raw_bars:
            b = _as_bar(raw)
            if b:
                bars.append(b)

        page_token = data.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.05)

    return bars


def load_symbols_from_file(path: Path) -> List[str]:
    if not path.exists():
        raise SystemExit(f"Symbols file not found: {path}")
    text = path.read_text(errors="ignore").strip()
    if not text:
        return []

    symbols: List[str] = []
    # CSV with possible symbol column.
    rows = list(csv.DictReader(text.splitlines()))
    if rows and rows[0]:
        for key in ("symbol", "Symbol", "ticker", "Ticker", "SYMBOL"):
            if key in rows[0]:
                symbols = [_clean_symbol(r.get(key, "")) for r in rows]
                break
    if not symbols:
        # Plain text / one symbol per line / comma separated.
        raw = text.replace("\n", ",").split(",")
        symbols = [_clean_symbol(x) for x in raw]
    return sorted({s for s in symbols if s})


def load_symbols_from_csv_import(limit: Optional[int] = None) -> List[str]:
    """Best-effort loader for the existing backend/csv_import.py universe module."""
    root = Path.cwd()
    backend_dir = root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        import csv_import  # type: ignore
    except Exception as exc:
        print(f"WARN: could not import backend/csv_import.py: {exc}", file=sys.stderr)
        return []

    candidates = [
        "get_symbols",
        "load_symbols",
        "get_universe",
        "load_universe",
        "get_active_symbols",
        "ACTIVE_SYMBOLS",
        "SYMBOLS",
        "UNIVERSE",
    ]
    for name in candidates:
        obj = getattr(csv_import, name, None)
        try:
            value = obj() if callable(obj) else obj
            if isinstance(value, dict):
                # Support {"symbols": [...]} style.
                value = value.get("symbols") or value.get("universe") or []
            if isinstance(value, (list, tuple, set)):
                symbols = sorted({_clean_symbol(x) for x in value if _clean_symbol(x)})
                if symbols:
                    return symbols[:limit] if limit else symbols
        except Exception as exc:
            print(f"WARN: csv_import.{name} failed: {exc}", file=sys.stderr)
    return []


def percentile_score(values: List[float], idx: int, lookback: int) -> Optional[float]:
    if idx < 0 or idx >= len(values):
        return None
    start = max(0, idx - lookback + 1)
    window = [x for x in values[start : idx + 1] if x is not None and math.isfinite(x)]
    if len(window) < max(10, min(lookback, 20)):
        return None
    current = values[idx]
    below_or_equal = sum(1 for x in window if x <= current)
    return 100.0 * below_or_equal / len(window)


def sma(values: List[float], end_idx: int, n: int) -> Optional[float]:
    if end_idx - n + 1 < 0:
        return None
    window = values[end_idx - n + 1 : end_idx + 1]
    if len(window) < n:
        return None
    return sum(window) / n


def calc_atr(bars: List[Bar], idx: int, n: int = 14) -> Optional[float]:
    if idx <= 0 or idx - n + 1 < 1:
        return None
    trs: List[float] = []
    for i in range(idx - n + 1, idx + 1):
        prev_close = bars[i - 1].c
        tr = max(
            bars[i].h - bars[i].l,
            abs(bars[i].h - prev_close),
            abs(bars[i].l - prev_close),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else None


def classify_setup(bars: List[Bar], idx: int) -> str:
    closes = [b.c for b in bars]
    volumes = [b.v for b in bars]
    if idx < 50:
        return "Insufficient"
    price = bars[idx].c
    ma20 = sma(closes, idx, 20) or price
    ma50 = sma(closes, idx, 50) or ma20
    atr = calc_atr(bars, idx, 14) or max(bars[idx].h - bars[idx].l, price * 0.02)
    avg_vol20 = sma(volumes, idx, 20) or 0
    rel_vol = bars[idx].v / avg_vol20 if avg_vol20 > 0 else 0
    change_pct = ((bars[idx].c - bars[idx - 1].c) / bars[idx - 1].c) * 100 if idx > 0 and bars[idx - 1].c else 0
    recent_range = max(closes[max(0, idx - 4) : idx + 1]) - min(closes[max(0, idx - 4) : idx + 1])
    compressed = recent_range < (atr * 5 * 0.75)
    high_52 = max(b.h for b in bars[max(0, idx - 251) : idx + 1])
    near_52 = high_52 > 0 and ((high_52 - price) / high_52) < 0.04

    if change_pct < -3 and rel_vol >= 1.2:
        return "Breakdown Risk"
    if change_pct < -1 and price < ma20:
        return "Distribution"
    if price > ma20 and ma20 >= ma50 and change_pct > 1.5 and rel_vol >= 1.1:
        return "Trend Continuation"
    if compressed and near_52:
        return "Compression Breakout Candidate"
    if compressed:
        return "Volatility Expansion Candidate"
    if near_52 and change_pct >= 0:
        return "Compression Breakout Candidate"
    if abs(change_pct) < 0.5 and rel_vol < 0.8:
        return "Low Edge - Avoid"
    return "Monitoring"


def setup_is_long(setup: str) -> bool:
    return setup in LONG_SETUP_TYPES and setup not in EXCLUDED_SETUP_TYPES


def grade_from_signal(
    rs_2h: float,
    rs_daily: float,
    daily_slope_pct: float,
    setup: str,
    rel_vol: float,
    price: float,
    ma20: float,
    ma50: float,
) -> Tuple[str, float]:
    """
    Baseline grading model for audit purposes.
    This is deliberately transparent and can be replaced by the live probability grade later.
    """
    score = 50.0

    # Sequential RS rules already passed; grade quality by strength above threshold.
    score += max(0.0, min(18.0, (rs_2h - 50.0) * 0.45))
    score += max(0.0, min(18.0, (rs_daily - 20.0) * 0.25))
    score += max(0.0, min(12.0, daily_slope_pct * 5.0))

    if setup == "Trend Continuation":
        score += 8
    elif setup == "Compression Breakout Candidate":
        score += 7
    elif setup == "Volatility Expansion Candidate":
        score += 5

    if price > ma20:
        score += 4
    if ma20 >= ma50:
        score += 4
    if rel_vol >= 1.2:
        score += 5
    elif rel_vol >= 0.8:
        score += 2
    elif rel_vol < 0.5:
        score -= 5

    score = max(0.0, min(100.0, score))
    if score >= 92:
        grade = "A+"
    elif score >= 86:
        grade = "A"
    elif score >= 80:
        grade = "A-"
    elif score >= 74:
        grade = "B+"
    elif score >= 68:
        grade = "B"
    elif score >= 62:
        grade = "B-"
    elif score >= 56:
        grade = "C+"
    elif score >= 50:
        grade = "C"
    elif score >= 44:
        grade = "C-"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"
    return grade, round(score, 2)


def grade_at_least(grade: str, minimum: str) -> bool:
    return GRADE_ORDER.get(str(grade).upper(), -1) >= GRADE_ORDER.get(str(minimum).upper(), 999)


def bars_by_date(bars: List[Bar]) -> Dict[str, Bar]:
    return {b.date: b for b in bars}


def last_2h_rs_by_date(symbol_2h: List[Bar], bench_2h: List[Bar], lookback: int) -> Dict[str, float]:
    bench_map_by_time = {b.t: b for b in bench_2h}
    ratios: List[float] = []
    dates: List[str] = []
    for b in symbol_2h:
        bb = bench_map_by_time.get(b.t)
        if not bb or bb.c <= 0:
            continue
        ratios.append(b.c / bb.c)
        dates.append(b.date)

    scores_by_date: Dict[str, float] = {}
    for i in range(len(ratios)):
        score = percentile_score(ratios, i, lookback)
        if score is not None:
            # Keep last 2H bar score per date.
            scores_by_date[dates[i]] = score
    return scores_by_date


def calc_rel_volume(bars: List[Bar], idx: int, n: int = 20) -> float:
    vols = [b.v for b in bars]
    avg = sma(vols, idx, n) or 0
    return bars[idx].v / avg if avg > 0 else 0.0


def forward_metrics(bars: List[Bar], idx: int, horizon: int) -> Optional[Dict[str, float]]:
    if idx + horizon >= len(bars):
        return None
    entry = bars[idx].c
    exit_close = bars[idx + horizon].c
    if entry <= 0:
        return None
    forward_slice = bars[idx + 1 : idx + horizon + 1]
    max_high = max(b.h for b in forward_slice)
    min_low = min(b.l for b in forward_slice)
    ret = ((exit_close - entry) / entry) * 100
    mfe = ((max_high - entry) / entry) * 100
    mae = ((min_low - entry) / entry) * 100
    return {
        "horizon": horizon,
        "direction_correct": 1.0 if ret > 0 else 0.0,
        "return_pct": ret,
        "mfe_pct": mfe,
        "mae_pct": mae,
    }


def summarize(rows: List[Dict[str, Any]], horizons: List[int]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = defaultdict(list)

    for r in rows:
        grade = r["grade"]
        setup = r["setup_type"]
        for bucket in ["C_AND_ABOVE", "B_AND_ABOVE", "A_MINUS_AND_ABOVE", f"GRADE_{grade}", f"SETUP_{setup}"]:
            if bucket == "C_AND_ABOVE" and not grade_at_least(grade, "C"):
                continue
            if bucket == "B_AND_ABOVE" and not grade_at_least(grade, "B"):
                continue
            if bucket == "A_MINUS_AND_ABOVE" and not grade_at_least(grade, "A-"):
                continue
            for h in horizons:
                key = f"h{h}"
                if key in r and isinstance(r[key], dict):
                    groups[(bucket, "ALL", h)].append(r[key])

    summary: List[Dict[str, Any]] = []
    for (bucket, segment, h), vals in sorted(groups.items(), key=lambda x: (x[0][0], x[0][2])):
        if not vals:
            continue
        count = len(vals)
        acc = sum(v["direction_correct"] for v in vals) / count * 100
        avg_ret = sum(v["return_pct"] for v in vals) / count
        avg_mfe = sum(v["mfe_pct"] for v in vals) / count
        avg_mae = sum(v["mae_pct"] for v in vals) / count
        edge_ratio = (avg_mfe / abs(avg_mae)) if avg_mae < 0 else None
        summary.append({
            "bucket": bucket,
            "segment": segment,
            "horizon_days": h,
            "signals": count,
            "direction_accuracy_pct": round(acc, 2),
            "avg_return_pct": round(avg_ret, 3),
            "avg_mfe_pct": round(avg_mfe, 3),
            "avg_mae_pct": round(avg_mae, 3),
            "edge_ratio": round(edge_ratio, 3) if edge_ratio is not None else None,
        })
    return summary


def run_audit(args: argparse.Namespace) -> None:
    feed = args.feed or _env("ALPACA_FEED", "iex")
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int(args.years * 365) + 120)
    start = start_dt.strftime("%Y-%m-%d")
    end = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    horizons = [int(x) for x in args.horizons.split(",") if x.strip()]
    max_horizon = max(horizons)

    if args.symbols:
        symbols = [_clean_symbol(x) for x in args.symbols.split(",") if _clean_symbol(x)]
    elif args.symbols_file:
        symbols = load_symbols_from_file(Path(args.symbols_file))
    else:
        symbols = load_symbols_from_csv_import(limit=args.limit)

    if args.limit:
        symbols = symbols[: args.limit]
    symbols = [s for s in sorted(set(symbols)) if s]
    if not symbols:
        raise SystemExit("No symbols supplied. Use --symbols, --symbols-file, or expose symbols from backend/csv_import.py")

    benchmark = _clean_symbol(args.benchmark or DEFAULT_BENCHMARK)
    if benchmark not in symbols:
        fetch_list = [benchmark] + symbols
    else:
        fetch_list = symbols

    print(f"Audit start: symbols={len(symbols)} benchmark={benchmark} feed={feed} start={start} end={end}")
    print(f"Rules: 2H RS >= {args.rs_2h_min}; Daily RS >= {args.rs_daily_min}; Daily RS rising over {args.daily_slope_bars} bars")
    print(f"Horizons: {horizons}")

    bench_daily = fetch_bars(benchmark, "1Day", start, end, feed)
    bench_2h = fetch_bars(benchmark, "2Hour", start, end, feed)
    if len(bench_daily) < 100 or len(bench_2h) < 100:
        raise SystemExit(f"Benchmark history too thin: daily={len(bench_daily)} 2h={len(bench_2h)}")
    bench_daily_by_date = bars_by_date(bench_daily)

    signal_rows: List[Dict[str, Any]] = []
    processed = 0
    skipped = 0

    for idx_sym, symbol in enumerate(symbols, start=1):
        if symbol == benchmark:
            continue
        try:
            daily = fetch_bars(symbol, "1Day", start, end, feed)
            twoh = fetch_bars(symbol, "2Hour", start, end, feed)
            if len(daily) < max(80, max_horizon + 60) or len(twoh) < 80:
                skipped += 1
                continue

            # Daily RS ratios aligned by date.
            ratios: List[Optional[float]] = []
            for b in daily:
                bb = bench_daily_by_date.get(b.date)
                ratios.append((b.c / bb.c) if bb and bb.c > 0 else None)

            # Convert optional ratios to numeric series for percentile/slope.
            # Missing benchmark dates get skipped by treating as non-signal.
            ratio_values = [float(x) if x is not None else float("nan") for x in ratios]
            rs_2h_by_date = last_2h_rs_by_date(twoh, bench_2h, args.rs_2h_lookback)

            closes = [b.c for b in daily]
            for i in range(60, len(daily) - max_horizon):
                ratio = ratio_values[i]
                if not math.isfinite(ratio):
                    continue
                daily_rs = percentile_score(ratio_values, i, args.rs_daily_lookback)
                if daily_rs is None or daily_rs < args.rs_daily_min:
                    continue

                slope_idx = i - args.daily_slope_bars
                if slope_idx < 0 or not math.isfinite(ratio_values[slope_idx]) or ratio_values[slope_idx] <= 0:
                    continue
                daily_slope_pct = ((ratio - ratio_values[slope_idx]) / ratio_values[slope_idx]) * 100
                if daily_slope_pct <= 0:
                    continue

                rs_2h = rs_2h_by_date.get(daily[i].date)
                if rs_2h is None or rs_2h < args.rs_2h_min:
                    continue

                setup = classify_setup(daily, i)
                if not setup_is_long(setup):
                    continue

                ma20 = sma(closes, i, 20) or daily[i].c
                ma50 = sma(closes, i, 50) or ma20
                rel_vol = calc_rel_volume(daily, i, 20)
                grade, audit_score = grade_from_signal(
                    rs_2h=rs_2h,
                    rs_daily=daily_rs,
                    daily_slope_pct=daily_slope_pct,
                    setup=setup,
                    rel_vol=rel_vol,
                    price=daily[i].c,
                    ma20=ma20,
                    ma50=ma50,
                )
                if not grade_at_least(grade, args.min_grade):
                    continue

                row: Dict[str, Any] = {
                    "symbol": symbol,
                    "signal_date": daily[i].date,
                    "entry_close": round(daily[i].c, 4),
                    "setup_type": setup,
                    "grade": grade,
                    "audit_score": audit_score,
                    "rs_2h": round(rs_2h, 2),
                    "rs_daily": round(daily_rs, 2),
                    "daily_rs_slope_pct": round(daily_slope_pct, 3),
                    "rel_volume": round(rel_vol, 3),
                    "ma20": round(ma20, 4),
                    "ma50": round(ma50, 4),
                }
                for h in horizons:
                    fm = forward_metrics(daily, i, h)
                    if fm:
                        row[f"h{h}"] = fm
                        row[f"h{h}_direction_correct"] = int(fm["direction_correct"])
                        row[f"h{h}_return_pct"] = round(fm["return_pct"], 3)
                        row[f"h{h}_mfe_pct"] = round(fm["mfe_pct"], 3)
                        row[f"h{h}_mae_pct"] = round(fm["mae_pct"], 3)
                signal_rows.append(row)
            processed += 1
            if idx_sym % 25 == 0:
                print(f"Processed {idx_sym}/{len(symbols)} symbols; signals={len(signal_rows)} skipped={skipped}")
            time.sleep(args.symbol_pause)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            skipped += 1
            print(f"WARN {symbol}: {exc}", file=sys.stderr)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_csv = output_dir / "qualified_long_signal_rows.csv"
    summary_json = output_dir / "qualified_long_signal_summary.json"
    summary_csv = output_dir / "qualified_long_signal_summary.csv"

    summary = summarize(signal_rows, horizons)

    # Flatten rows for CSV.
    flat_fields = [
        "symbol", "signal_date", "entry_close", "setup_type", "grade", "audit_score",
        "rs_2h", "rs_daily", "daily_rs_slope_pct", "rel_volume", "ma20", "ma50",
    ]
    for h in horizons:
        flat_fields += [f"h{h}_direction_correct", f"h{h}_return_pct", f"h{h}_mfe_pct", f"h{h}_mae_pct"]

    with rows_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=flat_fields)
        writer.writeheader()
        for r in signal_rows:
            writer.writerow({k: r.get(k, "") for k in flat_fields})

    with summary_csv.open("w", newline="") as f:
        fields = ["bucket", "segment", "horizon_days", "signals", "direction_accuracy_pct", "avg_return_pct", "avg_mfe_pct", "avg_mae_pct", "edge_ratio"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rules": {
            "rs_2h_min": args.rs_2h_min,
            "rs_daily_min": args.rs_daily_min,
            "daily_slope_bars": args.daily_slope_bars,
            "min_grade": args.min_grade,
            "included_setups": sorted(LONG_SETUP_TYPES),
            "excluded_setups": sorted(EXCLUDED_SETUP_TYPES),
            "horizons": horizons,
        },
        "universe": {
            "symbols_requested": len(symbols),
            "symbols_processed": processed,
            "symbols_skipped": skipped,
            "benchmark": benchmark,
            "feed": feed,
            "start": start,
            "end": end,
        },
        "total_signals": len(signal_rows),
        "summary": summary,
        "output_files": {
            "rows_csv": str(rows_csv),
            "summary_csv": str(summary_csv),
        },
    }
    summary_json.write_text(json.dumps(payload, indent=2))

    print("\nAudit complete")
    print(f"Signals: {len(signal_rows):,}")
    print(f"Rows:    {rows_csv}")
    print(f"Summary: {summary_json}")
    print(f"CSV:     {summary_csv}")

    # Console preview: best B+ / A- buckets across horizons.
    preview = [s for s in summary if s["bucket"] in {"B_AND_ABOVE", "A_MINUS_AND_ABOVE", "C_AND_ABOVE"}]
    preview = sorted(preview, key=lambda x: (x["bucket"], x["horizon_days"]))
    print("\nKey summary:")
    for s in preview:
        print(
            f"{s['bucket']:18s} h={s['horizon_days']:>3} "
            f"n={s['signals']:>5} acc={s['direction_accuracy_pct']:>6.2f}% "
            f"avg={s['avg_return_pct']:>7.3f}% edge={s['edge_ratio']}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Qualified Long Direction Accuracy Audit")
    p.add_argument("--symbols", default="", help="Comma-separated symbols, e.g. AAPL,MSFT,NVDA")
    p.add_argument("--symbols-file", default="", help="CSV/plain text symbols file")
    p.add_argument("--limit", type=int, default=0, help="Limit symbols loaded from csv_import/symbols file")
    p.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--feed", default=_env("ALPACA_FEED", "iex"), choices=["iex", "sip"])
    p.add_argument("--horizons", default=",".join(map(str, DEFAULT_HORIZONS)))
    p.add_argument("--rs-2h-min", type=float, default=50.0)
    p.add_argument("--rs-daily-min", type=float, default=20.0)
    p.add_argument("--rs-2h-lookback", type=int, default=80, help="2H RS percentile lookback bars")
    p.add_argument("--rs-daily-lookback", type=int, default=63, help="Daily RS percentile lookback bars")
    p.add_argument("--daily-slope-bars", type=int, default=5, help="Daily RS ratio must rise over this many daily bars")
    p.add_argument("--min-grade", default="C", choices=sorted(GRADE_ORDER.keys(), key=lambda g: GRADE_ORDER[g]))
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument("--symbol-pause", type=float, default=0.03, help="Pause between symbols to avoid rate limits")
    return p


if __name__ == "__main__":
    run_audit(build_arg_parser().parse_args())
