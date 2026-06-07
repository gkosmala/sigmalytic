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


def classify_expansion_subtype(
    setup: str,
    daily_slope_pct: float,
    rel_vol: float,
    price: float,
    high_252: float,
) -> str:
    """
    Splits Volatility Expansion Candidate into practical alpha subtypes.

    This does not change the original setup classification or grading math.
    It only gives the audit a more granular label so we can see which
    version of volatility expansion is actually producing forward returns.
    """
    if setup != "Volatility Expansion Candidate":
        return setup

    if daily_slope_pct < 1.0:
        phase = "EARLY"
    elif daily_slope_pct < 3.0:
        phase = "MID"
    else:
        phase = "LATE"

    if rel_vol >= 1.5:
        vol = "HIGHVOL"
    elif rel_vol >= 1.0:
        vol = "NORMALVOL"
    else:
        vol = "LOWVOL"

    near_high = high_252 > 0 and price >= high_252 * 0.95
    location = "NEARHIGH" if near_high else "OFFHIGH"

    return f"VOL_EXP_{phase}_{vol}_{location}"




def classify_volatility_dna_score(
    setup: str,
    setup_subtype: str,
    rs_daily: float,
    rs_2h: float,
    rel_vol: float,
    distance_from_252_high_pct: Optional[float],
    expansion_phase_bucket: str,
) -> Tuple[int, str]:
    """
    Scores the Volatility Expansion DNA cluster without changing the original audit math.

    The scoring weights are based on the 250-symbol discovery audit:
      - late expansion performed best
      - 2.0x-3.0x relative volume performed best
      - 20%+ off the 252-day high performed best
      - RS Daily 30-40 outperformed very high daily RS
      - 2H RS 60-70 and 90-100 were both constructive

    Output tiers are intentionally broad so we can verify whether returns stair-step upward.
    """
    if setup != "Volatility Expansion Candidate":
        return 0, "DNA_NON_VOL_EXP"

    score = 0

    # Phase: prior audit showed LATE > EARLY > MID.
    if expansion_phase_bucket == "EXP_PHASE_LATE":
        score += 3
    elif expansion_phase_bucket == "EXP_PHASE_EARLY":
        score += 1

    # Volume: prior audit showed 2.0x-3.0x strongest, then 1.5x-2.0x.
    if 2.0 <= rel_vol < 3.0:
        score += 3
    elif 1.5 <= rel_vol < 2.0:
        score += 2
    elif rel_vol >= 3.0:
        score += 1
    elif 1.0 <= rel_vol < 1.5:
        score += 1

    # Distance from 252-day high: prior audit showed 20%+ off highs strongest.
    if distance_from_252_high_pct is not None and math.isfinite(float(distance_from_252_high_pct)):
        d = float(distance_from_252_high_pct)
        if d <= -20.0:
            score += 3
        elif -5.0 <= d <= 0.0:
            score += 1

    # Daily RS: prior audit showed RS 30-40 strongest, then 70-80 / 20-30 / 90-100.
    if 30.0 <= rs_daily < 40.0:
        score += 2
    elif 20.0 <= rs_daily < 30.0:
        score += 1
    elif 70.0 <= rs_daily < 80.0:
        score += 1
    elif 90.0 <= rs_daily <= 100.0:
        score += 1

    # 2H RS: prior audit showed 60-70 strongest, then high 2H RS buckets.
    if 60.0 <= rs_2h < 70.0:
        score += 2
    elif 50.0 <= rs_2h < 60.0:
        score += 1
    elif 80.0 <= rs_2h < 90.0:
        score += 1
    elif 90.0 <= rs_2h <= 100.0:
        score += 1

    if score >= 10:
        tier = "DNA_10_PLUS"
    elif score >= 7:
        tier = "DNA_7_9"
    elif score >= 4:
        tier = "DNA_4_6"
    else:
        tier = "DNA_0_3"

    return score, tier

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

    exact_grade_buckets = {
        "A_PLUS_ONLY": {"A+"},
        "A_ONLY": {"A"},
        "A_MINUS_ONLY": {"A-"},
        "B_PLUS_ONLY": {"B+"},
        "B_ONLY": {"B"},
        "B_MINUS_ONLY": {"B-"},
        "C_PLUS_ONLY": {"C+"},
        "C_ONLY": {"C"},
        "C_MINUS_ONLY": {"C-"},
    }

    for r in rows:
        grade = str(r["grade"]).upper()
        setup = r["setup_type"]

        buckets: List[str] = [
            "ALL_QUALIFIED_LONGS",
            f"GRADE_{grade}",
            f"SETUP_{setup}",
        ]

        # Keep the original cumulative buckets for comparison.
        if grade_at_least(grade, "C"):
            buckets.append("C_AND_ABOVE")
        if grade_at_least(grade, "B"):
            buckets.append("B_AND_ABOVE")
        if grade_at_least(grade, "A-"):
            buckets.append("A_MINUS_AND_ABOVE")

        # Add pure, non-overlapping grade buckets so we can test whether
        # A trades actually outperform B trades without cumulative-bucket distortion.
        for bucket_name, allowed_grades in exact_grade_buckets.items():
            if grade in allowed_grades:
                buckets.append(bucket_name)

        for bucket in buckets:
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



def _bucket_for_factor_attribution(grade: str) -> str:
    grade = str(grade).upper()
    return {
        "A+": "A_PLUS_ONLY",
        "A": "A_ONLY",
        "A-": "A_MINUS_ONLY",
        "B+": "B_PLUS_ONLY",
        "B": "B_ONLY",
        "B-": "B_MINUS_ONLY",
        "C+": "C_PLUS_ONLY",
        "C": "C_ONLY",
        "C-": "C_MINUS_ONLY",
    }.get(grade, f"GRADE_{grade}")


def _avg_num(rows: List[Dict[str, Any]], field: str) -> Optional[float]:
    vals: List[float] = []
    for r in rows:
        try:
            v = r.get(field)
            if v is None or v == "":
                continue
            fv = float(v)
            if math.isfinite(fv):
                vals.append(fv)
        except Exception:
            continue
    return round(sum(vals) / len(vals), 4) if vals else None


def summarize_factor_attribution(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Explains the factor composition of each pure grade bucket.

    This does not change the audit math. It only answers:
      - What does A+ actually contain?
      - What does B+ actually contain?
      - Why might B+ be outperforming A+?
    """
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        bucket = _bucket_for_factor_attribution(str(r.get("grade", "")))
        grouped[bucket].append(r)
        grouped["ALL_QUALIFIED_LONGS"].append(r)

    bucket_order = {
        "A_PLUS_ONLY": 0,
        "A_ONLY": 1,
        "A_MINUS_ONLY": 2,
        "B_PLUS_ONLY": 3,
        "B_ONLY": 4,
        "B_MINUS_ONLY": 5,
        "C_PLUS_ONLY": 6,
        "C_ONLY": 7,
        "C_MINUS_ONLY": 8,
        "ALL_QUALIFIED_LONGS": 99,
    }

    out: List[Dict[str, Any]] = []
    for bucket, vals in sorted(grouped.items(), key=lambda kv: bucket_order.get(kv[0], 50)):
        if not vals:
            continue

        # Useful derived measures from fields already produced by the audit.
        above_ma20 = 0
        above_ma50 = 0
        ma20_ge_ma50 = 0
        ma_spread_vals: List[float] = []
        for r in vals:
            try:
                price = float(r.get("entry_close") or 0)
                ma20 = float(r.get("ma20") or 0)
                ma50 = float(r.get("ma50") or 0)
                if price > ma20:
                    above_ma20 += 1
                if price > ma50:
                    above_ma50 += 1
                if ma20 >= ma50:
                    ma20_ge_ma50 += 1
                if price > 0 and ma50 > 0:
                    ma_spread_vals.append(((ma20 - ma50) / price) * 100)
            except Exception:
                continue

        n = len(vals)
        setup_counts: Dict[str, int] = defaultdict(int)
        for r in vals:
            setup_counts[str(r.get("setup_type", "UNKNOWN"))] += 1
        top_setup = max(setup_counts.items(), key=lambda kv: kv[1])[0] if setup_counts else ""

        out.append({
            "bucket": bucket,
            "signals": n,
            "avg_audit_score": _avg_num(vals, "audit_score"),
            "avg_rs_2h": _avg_num(vals, "rs_2h"),
            "avg_rs_daily": _avg_num(vals, "rs_daily"),
            "avg_daily_rs_slope_pct": _avg_num(vals, "daily_rs_slope_pct"),
            "avg_rel_volume": _avg_num(vals, "rel_volume"),
            "pct_price_above_ma20": round((above_ma20 / n) * 100, 2) if n else None,
            "pct_price_above_ma50": round((above_ma50 / n) * 100, 2) if n else None,
            "pct_ma20_above_ma50": round((ma20_ge_ma50 / n) * 100, 2) if n else None,
            "avg_ma20_minus_ma50_pct_of_price": round(sum(ma_spread_vals) / len(ma_spread_vals), 4) if ma_spread_vals else None,
            "top_setup_type": top_setup,
            "top_setup_count": setup_counts.get(top_setup, 0) if top_setup else 0,
        })
    return out


def summarize_setup_breakdown(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Counts setup types inside each pure grade bucket.
    This helps determine whether B+ is dominated by expansion/breakout/trend setups.
    """
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    bucket_totals: Dict[str, int] = defaultdict(int)

    for r in rows:
        bucket = _bucket_for_factor_attribution(str(r.get("grade", "")))
        setup = str(r.get("setup_type", "UNKNOWN"))
        counts[(bucket, setup)] += 1
        bucket_totals[bucket] += 1

        counts[("ALL_QUALIFIED_LONGS", setup)] += 1
        bucket_totals["ALL_QUALIFIED_LONGS"] += 1

    bucket_order = {
        "A_PLUS_ONLY": 0,
        "A_ONLY": 1,
        "A_MINUS_ONLY": 2,
        "B_PLUS_ONLY": 3,
        "B_ONLY": 4,
        "B_MINUS_ONLY": 5,
        "C_PLUS_ONLY": 6,
        "C_ONLY": 7,
        "C_MINUS_ONLY": 8,
        "ALL_QUALIFIED_LONGS": 99,
    }

    out: List[Dict[str, Any]] = []
    for (bucket, setup), count in sorted(counts.items(), key=lambda kv: (bucket_order.get(kv[0][0], 50), kv[0][1])):
        total = bucket_totals.get(bucket, 0)
        out.append({
            "bucket": bucket,
            "setup_type": setup,
            "signals": count,
            "bucket_pct": round((count / total) * 100, 2) if total else None,
        })
    return out


def summarize_expansion_subtypes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ranks setup_subtype labels by 90-day forward performance.

    Main purpose:
      - identify which Volatility Expansion subtype is producing alpha
      - compare early/mid/late expansion
      - compare low/normal/high volume expansion
      - compare near-high vs off-high expansion
    """
    grouped: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    for r in rows:
        subtype = str(r.get("setup_subtype") or r.get("setup_type") or "UNKNOWN")
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            continue
        try:
            grouped[subtype].append({
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            })
        except Exception:
            continue

    out: List[Dict[str, Any]] = []
    for subtype, vals in grouped.items():
        if not vals:
            continue
        count = len(vals)
        acc = sum(v["direction_correct"] for v in vals) / count * 100
        avg_ret = sum(v["return_pct"] for v in vals) / count
        avg_mfe = sum(v["mfe_pct"] for v in vals) / count
        avg_mae = sum(v["mae_pct"] for v in vals) / count
        edge_ratio = (avg_mfe / abs(avg_mae)) if avg_mae < 0 else None
        out.append({
            "setup_subtype": subtype,
            "signals": count,
            "direction_accuracy_90d_pct": round(acc, 2),
            "avg_return_90d_pct": round(avg_ret, 3),
            "avg_mfe_90d_pct": round(avg_mfe, 3),
            "avg_mae_90d_pct": round(avg_mae, 3),
            "edge_ratio_90d": round(edge_ratio, 3) if edge_ratio is not None else None,
        })

    out.sort(key=lambda x: (x["avg_return_90d_pct"], x["signals"]), reverse=True)
    return out



def _bucket_numeric(value: Any, buckets: List[Tuple[float, float, str]]) -> str:
    try:
        x = float(value)
    except Exception:
        return "UNKNOWN"
    if not math.isfinite(x):
        return "UNKNOWN"
    for low, high, label in buckets:
        if x >= low and x < high:
            return label
    return buckets[-1][2] if buckets else "UNKNOWN"


def _summarize_group_perf(grouped: Dict[str, List[Dict[str, Any]]], min_signals: int = 25) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for bucket, vals in grouped.items():
        if len(vals) < min_signals:
            continue
        n = len(vals)
        acc = sum(float(v.get("direction_correct", 0.0)) for v in vals) / n * 100
        avg_ret = sum(float(v.get("return_pct", 0.0)) for v in vals) / n
        avg_mfe = sum(float(v.get("mfe_pct", 0.0)) for v in vals) / n
        avg_mae = sum(float(v.get("mae_pct", 0.0)) for v in vals) / n
        edge_ratio = (avg_mfe / abs(avg_mae)) if avg_mae < 0 else None
        out.append({
            "bucket": bucket,
            "signals": n,
            "direction_accuracy_90d_pct": round(acc, 2),
            "avg_return_90d_pct": round(avg_ret, 3),
            "avg_mfe_90d_pct": round(avg_mfe, 3),
            "avg_mae_90d_pct": round(avg_mae, 3),
            "edge_ratio_90d": round(edge_ratio, 3) if edge_ratio is not None else None,
        })
    out.sort(key=lambda x: (x["avg_return_90d_pct"], x["signals"]), reverse=True)
    return out


def summarize_volatility_dna(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Breaks Volatility Expansion Candidate into the DNA dimensions we need before
    moving on to other methodologies: RS, volume, distance from high, phase,
    subtype, and top symbols.
    """
    vol_rows = [r for r in rows if str(r.get("setup_type")) == "Volatility Expansion Candidate"]

    def h90_payload(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    rs_daily_buckets = [(0, 30, "RS_DAILY_20_30"), (30, 40, "RS_DAILY_30_40"), (40, 50, "RS_DAILY_40_50"), (50, 60, "RS_DAILY_50_60"), (60, 70, "RS_DAILY_60_70"), (70, 80, "RS_DAILY_70_80"), (80, 90, "RS_DAILY_80_90"), (90, 101, "RS_DAILY_90_100")]
    rs_2h_buckets = [(0, 60, "RS2H_50_60"), (60, 70, "RS2H_60_70"), (70, 80, "RS2H_70_80"), (80, 90, "RS2H_80_90"), (90, 101, "RS2H_90_100")]
    vol_buckets = [(0, 0.8, "RELVOL_UNDER_0_8X"), (0.8, 1.0, "RELVOL_0_8_1_0X"), (1.0, 1.5, "RELVOL_1_0_1_5X"), (1.5, 2.0, "RELVOL_1_5_2_0X"), (2.0, 3.0, "RELVOL_2_0_3_0X"), (3.0, 9999, "RELVOL_3X_PLUS")]
    dist_buckets = [(-999, -20, "HIGH_DISTANCE_20PCT_PLUS_OFF"), (-20, -10, "HIGH_DISTANCE_10_20PCT_OFF"), (-10, -5, "HIGH_DISTANCE_5_10PCT_OFF"), (-5, 0.0001, "HIGH_DISTANCE_0_5PCT_OFF")]

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        "vol_exp_rs_daily_buckets": defaultdict(list),
        "vol_exp_rs_2h_buckets": defaultdict(list),
        "vol_exp_rel_volume_buckets": defaultdict(list),
        "vol_exp_distance_from_high_buckets": defaultdict(list),
        "vol_exp_phase_buckets": defaultdict(list),
        "vol_exp_subtype_buckets": defaultdict(list),
        "vol_exp_dna_score_tiers": defaultdict(list),
        "vol_exp_dna_score_exact": defaultdict(list),
    }

    symbol_grouped: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    top_subtype = "VOL_EXP_LATE_HIGHVOL_OFFHIGH"
    top_subtype_symbol_grouped: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    for r in vol_rows:
        payload = h90_payload(r)
        if not payload:
            continue
        grouped["vol_exp_rs_daily_buckets"][_bucket_numeric(r.get("rs_daily"), rs_daily_buckets)].append(payload)
        grouped["vol_exp_rs_2h_buckets"][_bucket_numeric(r.get("rs_2h"), rs_2h_buckets)].append(payload)
        grouped["vol_exp_rel_volume_buckets"][_bucket_numeric(r.get("rel_volume"), vol_buckets)].append(payload)
        grouped["vol_exp_distance_from_high_buckets"][_bucket_numeric(r.get("distance_from_252_high_pct"), dist_buckets)].append(payload)
        grouped["vol_exp_phase_buckets"][str(r.get("expansion_phase_bucket", "UNKNOWN"))].append(payload)
        grouped["vol_exp_subtype_buckets"][str(r.get("setup_subtype", "UNKNOWN"))].append(payload)
        grouped["vol_exp_dna_score_tiers"][str(r.get("volatility_dna_tier", "UNKNOWN"))].append(payload)
        grouped["vol_exp_dna_score_exact"][f"DNA_SCORE_{r.get('volatility_dna_score', 'UNKNOWN')}"] .append(payload)
        symbol_grouped[str(r.get("symbol", "UNKNOWN"))].append(payload)
        if str(r.get("setup_subtype")) == top_subtype:
            top_subtype_symbol_grouped[str(r.get("symbol", "UNKNOWN"))].append(payload)

    results: Dict[str, List[Dict[str, Any]]] = {}
    for name, buckets in grouped.items():
        results[name] = _summarize_group_perf(buckets, min_signals=25)

    # Symbol tables use a higher threshold so one-off winners don't dominate.
    results["vol_exp_top_symbols"] = _summarize_group_perf(symbol_grouped, min_signals=20)[:50]
    results["vol_exp_late_highvol_offhigh_top_symbols"] = _summarize_group_perf(top_subtype_symbol_grouped, min_signals=5)[:50]
    return results


def summarize_volatility_interactions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tests interaction effects inside Volatility Expansion Candidate.

    This is the key Phase 2 volatility audit:
      phase x relative-volume bucket x distance-from-high bucket x DNA tier

    The goal is to find whether combinations such as:
      LATE + 2.0-3.0x volume + 20%+ off highs
    outperform the individual ingredients.
    """
    grouped: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    for r in rows:
        if str(r.get("setup_type")) != "Volatility Expansion Candidate":
            continue

        h90 = r.get("h90")
        if not isinstance(h90, dict):
            continue

        try:
            payload = {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            continue

        phase = str(r.get("expansion_phase_bucket", "UNKNOWN"))
        relvol_bucket = str(r.get("rel_volume_bucket", "UNKNOWN"))
        dna_tier = str(r.get("volatility_dna_tier", "UNKNOWN"))

        try:
            d = float(r.get("distance_from_252_high_pct"))
        except Exception:
            d = float("nan")

        if not math.isfinite(d):
            high_bucket = "HIGH_DISTANCE_UNKNOWN"
        elif d <= -20.0:
            high_bucket = "HIGH_DISTANCE_20PCT_PLUS_OFF"
        elif d <= -10.0:
            high_bucket = "HIGH_DISTANCE_10_20PCT_OFF"
        elif d <= -5.0:
            high_bucket = "HIGH_DISTANCE_5_10PCT_OFF"
        else:
            high_bucket = "HIGH_DISTANCE_0_5PCT_OFF"

        grouped[f"{phase}|{relvol_bucket}|{high_bucket}"].append(payload)
        grouped[f"{phase}|{relvol_bucket}|{high_bucket}|{dna_tier}"].append(payload)

    return _summarize_group_perf(grouped, min_signals=25)



def summarize_volatility_rs_matrix(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Volatility + Relative Strength study.

    Research question:
      WHERE does volatility alpha occur relative to RS?

    This does not add Wyckoff/VSA/Gann/Elliott/etc. It only cross-tests:
      - volatility DNA tier x daily RS bucket
      - volatility DNA tier x 2H RS bucket
      - strongest volatility environment x daily RS bucket
      - strongest volatility environment x 2H RS bucket
    """
    rs_daily_buckets = [
        (0, 20, "RS_DAILY_0_20"),
        (20, 30, "RS_DAILY_20_30"),
        (30, 40, "RS_DAILY_30_40"),
        (40, 50, "RS_DAILY_40_50"),
        (50, 60, "RS_DAILY_50_60"),
        (60, 70, "RS_DAILY_60_70"),
        (70, 80, "RS_DAILY_70_80"),
        (80, 90, "RS_DAILY_80_90"),
        (90, 101, "RS_DAILY_90_100"),
    ]
    rs_2h_buckets = [
        (0, 20, "RS2H_0_20"),
        (20, 30, "RS2H_20_30"),
        (30, 40, "RS2H_30_40"),
        (40, 50, "RS2H_40_50"),
        (50, 60, "RS2H_50_60"),
        (60, 70, "RS2H_60_70"),
        (70, 80, "RS2H_70_80"),
        (80, 90, "RS2H_80_90"),
        (90, 101, "RS2H_90_100"),
    ]

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        "dna_tier_x_daily_rs": defaultdict(list),
        "dna_tier_x_2h_rs": defaultdict(list),
        "late_2to3x_20off_x_daily_rs": defaultdict(list),
        "late_2to3x_20off_x_2h_rs": defaultdict(list),
        "late_highvol_offhigh_x_daily_rs": defaultdict(list),
        "late_highvol_offhigh_x_2h_rs": defaultdict(list),
    }

    def payload_from_h90(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    for r in rows:
        if str(r.get("setup_type")) != "Volatility Expansion Candidate":
            continue

        payload = payload_from_h90(r)
        if not payload:
            continue

        daily_rs_bucket = _bucket_numeric(r.get("rs_daily"), rs_daily_buckets)
        rs2h_bucket = _bucket_numeric(r.get("rs_2h"), rs_2h_buckets)
        dna_tier = str(r.get("volatility_dna_tier", "UNKNOWN"))
        phase = str(r.get("expansion_phase_bucket", "UNKNOWN"))
        relvol_bucket = str(r.get("rel_volume_bucket", "UNKNOWN"))
        subtype = str(r.get("setup_subtype", "UNKNOWN"))

        try:
            dist = float(r.get("distance_from_252_high_pct"))
        except Exception:
            dist = float("nan")
        far_off_high = math.isfinite(dist) and dist <= -20.0

        grouped["dna_tier_x_daily_rs"][f"{dna_tier}|{daily_rs_bucket}"].append(payload)
        grouped["dna_tier_x_2h_rs"][f"{dna_tier}|{rs2h_bucket}"].append(payload)

        # This was the strongest clean interaction from the prior audit:
        # Late expansion + 2.0-3.0x relative volume + 20%+ off 252-day high.
        if phase == "EXP_PHASE_LATE" and relvol_bucket == "RELVOL_2_0_3_0X" and far_off_high:
            grouped["late_2to3x_20off_x_daily_rs"][daily_rs_bucket].append(payload)
            grouped["late_2to3x_20off_x_2h_rs"][rs2h_bucket].append(payload)

        # This was the strongest named subtype from the subtype audit.
        if subtype == "VOL_EXP_LATE_HIGHVOL_OFFHIGH":
            grouped["late_highvol_offhigh_x_daily_rs"][daily_rs_bucket].append(payload)
            grouped["late_highvol_offhigh_x_2h_rs"][rs2h_bucket].append(payload)

    return {
        name: _summarize_group_perf(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }


# -----------------------------------------------------------------------------
# Wyckoff / Weis Phase 2: Persistent Absorption
# -----------------------------------------------------------------------------

def _is_high_effort_low_result(effort_bucket: str, result_bucket: str) -> bool:
    """
    Atomic Wyckoff/Weis absorption candidate.

    This is intentionally context-neutral.  We are NOT saying this is bullish
    absorption or bearish distribution yet.  We are only detecting the behavioral
    footprint: unusually high effort with little price progress.
    """
    return (
        effort_bucket in {"EFFORT_HIGH_1_5_2_0X", "EFFORT_VERY_HIGH_2_0_3_0X", "EFFORT_CLIMAX_3X_PLUS"}
        and result_bucket == "RESULT_LOW_PROGRESS"
    )


def _absorption_persistence_tier(count: int) -> str:
    if count <= 0:
        return "ABS_PERSISTENCE_0_EVENTS"
    if count == 1:
        return "ABS_PERSISTENCE_1_EVENT"
    if count == 2:
        return "ABS_PERSISTENCE_2_EVENTS"
    if count == 3:
        return "ABS_PERSISTENCE_3_EVENTS"
    return "ABS_PERSISTENCE_4_PLUS_EVENTS"


def _count_absorption_candidates_in_window(
    bars: List[Bar],
    idx: int,
    window: int,
    mode: str = "single",
) -> int:
    """
    Count atomic absorption candidates in a rolling window ending at idx.

    mode="single": one-bar effort/result.
    mode="five": five-bar effort/result.

    This function deliberately avoids RS, volatility regime, distance from high,
    setup type, or grade.  It tests the pure Wyckoff/Weis proposition that
    repeated high-effort / low-result behavior may represent cause building.
    """
    if idx <= 0:
        return 0
    start = max(1, idx - window + 1)
    count = 0
    for j in range(start, idx + 1):
        atr_pct = _atr_pct(bars, j, 20) or 0.0
        if atr_pct <= 0:
            continue

        if mode == "five":
            if j < 5:
                continue
            start_close = bars[j - 5].c
            return_pct = ((bars[j].c - start_close) / start_close * 100.0) if start_close > 0 else 0.0
            recent_vol = sum(b.v for b in bars[j - 4:j + 1])
            prior_start = max(0, j - 24)
            prior_vols = [b.v for b in bars[prior_start:j - 4]]
            avg_prior_vol = (sum(prior_vols) / len(prior_vols)) if prior_vols else max(bars[j].v, 1.0)
            rel_effort = recent_vol / max(avg_prior_vol * 5.0, 1.0)
            norm_result = (return_pct / (atr_pct * math.sqrt(5))) if atr_pct > 0 else 0.0
        else:
            prev_close = bars[j - 1].c if j > 0 else bars[j].o
            return_pct = ((bars[j].c - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
            rel_effort = calc_rel_volume(bars, j, 20)
            norm_result = (return_pct / atr_pct) if atr_pct > 0 else 0.0

        effort_bucket = _effort_bucket(rel_effort)
        result_bucket = _result_bucket(norm_result)
        if _is_high_effort_low_result(effort_bucket, result_bucket):
            count += 1
    return count





# =============================================================================
# Wyckoff / Weis Phase 4: Juncture Detection
# =============================================================================
#
# Research question:
#   Can we algorithmically identify the moments Weis calls junctures —
#   specifically springs, upthrusts, and absorption at critical levels —
#   and demonstrate that those moments produce asymmetric forward returns
#   compared to absorption detected outside of structural context?
#
# Three juncture types are tested:
#   1. Spring   — failed penetration of support that reverses upward
#   2. Upthrust — failed penetration of resistance that reverses downward
#   3. Absorption at structural level (support or resistance)
#
# Classification:
#   Each signal is scored for accumulation or distribution character
#   using location, volume asymmetry, and juncture type.
# =============================================================================


def _swing_lows(bars: List[Bar], idx: int, lookback: int, n: int = 3) -> List[float]:
    """Return the n most recent swing lows in the lookback window ending at idx."""
    start = max(2, idx - lookback + 1)
    lows: List[float] = []
    for j in range(start, idx - 1):
        if bars[j].l < bars[j - 1].l and bars[j].l < bars[j + 1].l:
            lows.append(bars[j].l)
    return lows[-n:] if lows else []


def _swing_highs(bars: List[Bar], idx: int, lookback: int, n: int = 3) -> List[float]:
    """Return the n most recent swing highs in the lookback window ending at idx."""
    start = max(2, idx - lookback + 1)
    highs: List[float] = []
    for j in range(start, idx - 1):
        if bars[j].h > bars[j - 1].h and bars[j].h > bars[j + 1].h:
            highs.append(bars[j].h)
    return highs[-n:] if highs else []


def _detect_trading_range(
    bars: List[Bar],
    idx: int,
    lookback: int = 60,
    min_width_pct: float = 5.0,
    max_width_pct: float = 45.0,
    min_touches: int = 2,
    min_bars: int = 20,
) -> Dict[str, Any]:
    """
    Detect whether price has been oscillating inside a trading range.

    Returns a dict with:
        detected       bool
        range_high     float
        range_low      float
        range_width_pct float
        support_level  float
        resistance_level float
        support_touches  int
        resistance_touches int
        bars_in_range  int
        price_location_in_range  float   0=bottom  1=top
    """
    result: Dict[str, Any] = {
        "detected": False,
        "range_high": 0.0,
        "range_low": 0.0,
        "range_width_pct": 0.0,
        "support_level": 0.0,
        "resistance_level": 0.0,
        "support_touches": 0,
        "resistance_touches": 0,
        "bars_in_range": 0,
        "price_location_in_range": 0.5,
    }

    if idx < lookback:
        return result

    window = bars[idx - lookback: idx + 1]
    if len(window) < min_bars:
        return result

    highs = [b.h for b in window]
    lows  = [b.l for b in window]
    closes = [b.c for b in window]

    range_high = max(highs)
    range_low  = min(lows)
    if range_low <= 0:
        return result

    range_width_pct = (range_high - range_low) / range_low * 100.0
    if not (min_width_pct <= range_width_pct <= max_width_pct):
        return result

    atr = calc_atr(bars, idx, 14) or (range_high - range_low) * 0.05
    tolerance = atr * 1.0

    # Support = average of swing lows; resistance = average of swing highs
    s_lows  = _swing_lows(bars, idx, lookback, n=5)
    s_highs = _swing_highs(bars, idx, lookback, n=5)

    if not s_lows or not s_highs:
        return result

    support_level    = sum(s_lows)  / len(s_lows)
    resistance_level = sum(s_highs) / len(s_highs)

    if resistance_level <= support_level:
        return result

    # Count bars that touch each level within tolerance
    support_touches    = sum(1 for b in window if abs(b.l - support_level)    <= tolerance)
    resistance_touches = sum(1 for b in window if abs(b.h - resistance_level) <= tolerance)

    if support_touches < min_touches or resistance_touches < min_touches:
        return result

    # Count bars inside the range
    bars_in_range = sum(
        1 for b in window
        if support_level - tolerance <= b.l and b.h <= resistance_level + tolerance
    )

    if bars_in_range < min_bars:
        return result

    price = bars[idx].c
    rng = resistance_level - support_level
    price_location = (price - support_level) / rng if rng > 0 else 0.5

    result.update({
        "detected": True,
        "range_high": round(range_high, 4),
        "range_low": round(range_low, 4),
        "range_width_pct": round(range_width_pct, 3),
        "support_level": round(support_level, 4),
        "resistance_level": round(resistance_level, 4),
        "support_touches": support_touches,
        "resistance_touches": resistance_touches,
        "bars_in_range": bars_in_range,
        "price_location_in_range": round(max(0.0, min(1.0, price_location)), 3),
    })
    return result


def _detect_apex(bars: List[Bar], idx: int, lookback: int = 40) -> Dict[str, Any]:
    """
    Detect whether price is coiling toward an apex (converging trend lines).

    Measures range compression over the lookback window.
    When apex_proximity approaches 0, price is tightly coiled.
    """
    result = {"apex_detected": False, "apex_proximity": 1.0, "range_contraction_pct": 0.0}

    if idx < lookback:
        return result

    # Compare recent range to earlier range
    half = lookback // 2
    early_window = bars[idx - lookback: idx - half]
    recent_window = bars[idx - half: idx + 1]

    if not early_window or not recent_window:
        return result

    early_range  = max(b.h for b in early_window)  - min(b.l for b in early_window)
    recent_range = max(b.h for b in recent_window) - min(b.l for b in recent_window)

    if early_range <= 0:
        return result

    contraction = (early_range - recent_range) / early_range
    proximity   = recent_range / early_range   # 0 = fully coiled, 1 = no contraction

    apex_detected = contraction >= 0.30 and proximity <= 0.70

    result.update({
        "apex_detected": apex_detected,
        "apex_proximity": round(max(0.0, min(1.0, proximity)), 3),
        "range_contraction_pct": round(contraction * 100.0, 2),
    })
    return result


def _volume_asymmetry(bars: List[Bar], idx: int, lookback: int = 20) -> Dict[str, Any]:
    """
    Measure whether volume is heavier on up days vs down days within the window.

    up_vol_ratio > 1.0 → demand dominant (accumulation signature)
    up_vol_ratio < 1.0 → supply dominant (distribution signature)
    """
    start = max(1, idx - lookback + 1)
    up_vol   = 0.0
    down_vol = 0.0
    up_days  = 0
    down_days = 0

    for j in range(start, idx + 1):
        if bars[j].c >= bars[j - 1].c:
            up_vol  += bars[j].v
            up_days += 1
        else:
            down_vol  += bars[j].v
            down_days += 1

    avg_up   = up_vol   / up_days   if up_days   > 0 else 0.0
    avg_down = down_vol / down_days if down_days > 0 else 0.0

    ratio = avg_up / avg_down if avg_down > 0 else 1.0

    return {
        "up_vol_avg":   round(avg_up,   2),
        "down_vol_avg": round(avg_down, 2),
        "vol_asymmetry_ratio": round(ratio, 3),
        "demand_dominant": ratio >= 1.10,
    }


def _detect_spring(
    bars: List[Bar],
    idx: int,
    support_level: float,
    atr: float,
    lookforward: int = 3,
) -> Dict[str, Any]:
    """
    Spring detection.

    A spring occurs when:
    1. Price penetrates below support (low < support)
    2. The penetration is shallow (< 2 ATR below support)
    3. Price closes back above support within lookforward bars
    4. Volume on penetration bar is at or above average
    5. The bar closes in the upper half of its range (rejection)

    Returns detection flag and quality score (0-5).
    """
    result = {
        "spring_detected": False,
        "spring_quality": 0,
        "spring_penetration_pct": 0.0,
        "spring_recovery_bars": 0,
    }

    if support_level <= 0 or atr <= 0:
        return result

    bar = bars[idx]

    # Condition 1: low penetrates support
    if bar.l >= support_level:
        return result

    penetration = support_level - bar.l
    penetration_pct = penetration / support_level * 100.0

    # Condition 2: shallow — within 2 ATR
    if penetration > atr * 2.0:
        return result

    # Condition 3: closes back above support (or within 0.5 ATR of it)
    close_near_support = bar.c >= support_level - atr * 0.5

    # Look forward for recovery above support
    recovery_bar = 0
    for j in range(1, lookforward + 1):
        if idx + j < len(bars) and bars[idx + j].c > support_level:
            recovery_bar = j
            break

    if not close_near_support and recovery_bar == 0:
        return result

    # Quality scoring
    score = 0

    # Volume on penetration bar vs 20-day average
    avg_vol = sma([b.v for b in bars], idx, 20) or bars[idx].v
    if avg_vol and avg_vol > 0:
        vol_ratio = bar.v / avg_vol
        if vol_ratio >= 1.5:
            score += 2   # climactic volume on test — classic spring
        elif vol_ratio >= 1.0:
            score += 1

    # Bar closes in upper half of its range (rejection of lows)
    bar_range = bar.h - bar.l
    if bar_range > 0 and (bar.c - bar.l) / bar_range >= 0.5:
        score += 1

    # Shallow penetration is better
    if penetration_pct < 1.0:
        score += 1

    # Quick recovery
    if recovery_bar == 1:
        score += 1

    detected = score >= 2

    result.update({
        "spring_detected": detected,
        "spring_quality": score,
        "spring_penetration_pct": round(penetration_pct, 3),
        "spring_recovery_bars": recovery_bar,
    })
    return result


def _detect_upthrust(
    bars: List[Bar],
    idx: int,
    resistance_level: float,
    atr: float,
    lookforward: int = 3,
) -> Dict[str, Any]:
    """
    Upthrust detection.

    An upthrust occurs when:
    1. Price penetrates above resistance (high > resistance)
    2. The penetration is shallow (< 2 ATR above resistance)
    3. Price closes back below resistance within lookforward bars
    4. Volume climaxes on the breakout bar (elevated)
    5. The bar closes in the lower half of its range (rejection)

    Returns detection flag and quality score (0-5).
    """
    result = {
        "upthrust_detected": False,
        "upthrust_quality": 0,
        "upthrust_penetration_pct": 0.0,
        "upthrust_return_bars": 0,
    }

    if resistance_level <= 0 or atr <= 0:
        return result

    bar = bars[idx]

    # Condition 1: high penetrates resistance
    if bar.h <= resistance_level:
        return result

    penetration = bar.h - resistance_level
    penetration_pct = penetration / resistance_level * 100.0

    # Condition 2: shallow — within 2 ATR
    if penetration > atr * 2.0:
        return result

    # Condition 3: closes back below resistance (or within 0.5 ATR)
    close_near_resistance = bar.c <= resistance_level + atr * 0.5

    # Look forward for return below resistance
    return_bar = 0
    for j in range(1, lookforward + 1):
        if idx + j < len(bars) and bars[idx + j].c < resistance_level:
            return_bar = j
            break

    if not close_near_resistance and return_bar == 0:
        return result

    # Quality scoring
    score = 0

    avg_vol = sma([b.v for b in bars], idx, 20) or bars[idx].v
    if avg_vol and avg_vol > 0:
        vol_ratio = bar.v / avg_vol
        if vol_ratio >= 1.5:
            score += 2   # volume climax on the upthrust — supply overwhelming demand
        elif vol_ratio >= 1.0:
            score += 1

    # Bar closes in lower half (rejection of highs)
    bar_range = bar.h - bar.l
    if bar_range > 0 and (bar.h - bar.c) / bar_range >= 0.5:
        score += 1

    # Shallow penetration
    if penetration_pct < 1.0:
        score += 1

    # Quick return
    if return_bar == 1:
        score += 1

    detected = score >= 2

    result.update({
        "upthrust_detected": detected,
        "upthrust_quality": score,
        "upthrust_penetration_pct": round(penetration_pct, 3),
        "upthrust_return_bars": return_bar,
    })
    return result


def _absorption_at_juncture(
    bars: List[Bar],
    idx: int,
    support_level: float,
    resistance_level: float,
    atr: float,
) -> Dict[str, Any]:
    """
    Determine whether five-bar absorption is occurring AT a structural level.

    Absorption in open price space = noise (Phase 3 result).
    Absorption at support or resistance = potential signal.

    Returns:
        at_support     bool
        at_resistance  bool
        at_juncture    bool
        juncture_type  str
    """
    price = bars[idx].c
    tolerance = atr * 1.0

    at_support    = support_level > 0    and abs(price - support_level)    <= tolerance
    at_resistance = resistance_level > 0 and abs(price - resistance_level) <= tolerance

    if at_support:
        juncture_type = "AT_SUPPORT"
    elif at_resistance:
        juncture_type = "AT_RESISTANCE"
    else:
        juncture_type = "OPEN_SPACE"

    return {
        "at_support":    at_support,
        "at_resistance": at_resistance,
        "at_juncture":   at_support or at_resistance,
        "juncture_type": juncture_type,
    }


def _classify_behavior(
    distance_from_high_pct: Optional[float],
    spring_detected: bool,
    upthrust_detected: bool,
    demand_dominant: bool,
    price_location_in_range: float,
    at_support: bool,
    at_resistance: bool,
    apex_detected: bool,
) -> Dict[str, Any]:
    """
    Score the behavioral character of the signal.

    Accumulation evidence:
      - Deep off highs (supply has been distributed, markdown complete)
      - Spring detected (final supply test)
      - Demand dominant volume (buyers absorbing sellers)
      - Price in lower portion of range (building cause at base)
      - Absorption occurring at support

    Distribution evidence:
      - Near highs (markup complete, institutions offloading)
      - Upthrust detected (final demand test rejected)
      - Supply dominant volume (sellers absorbing buyers)
      - Price in upper portion of range (distributing at top)
      - Absorption occurring at resistance

    Apex adds urgency to whichever side dominates.
    """
    acc_score = 0
    dist_score = 0

    try:
        dist = float(distance_from_high_pct) if distance_from_high_pct not in (None, "") else 0.0
    except Exception:
        dist = 0.0

    # Location relative to 252-day high
    if dist <= -20.0:
        acc_score  += 3
    elif dist <= -10.0:
        acc_score  += 1
    elif dist >= -5.0:
        dist_score += 3

    # Juncture type
    if spring_detected:
        acc_score  += 3
    if upthrust_detected:
        dist_score += 3

    # Volume character
    if demand_dominant:
        acc_score  += 2
    else:
        dist_score += 2

    # Price location in range
    if price_location_in_range <= 0.35:
        acc_score  += 2
    elif price_location_in_range >= 0.65:
        dist_score += 2

    # Absorption level
    if at_support:
        acc_score  += 1
    if at_resistance:
        dist_score += 1

    # Apex adds urgency
    if apex_detected:
        acc_score  += 1
        dist_score += 1

    total = acc_score + dist_score
    if total == 0:
        behavior = "NEUTRAL"
    elif acc_score >= dist_score * 1.5:
        behavior = "ACCUMULATION"
    elif dist_score >= acc_score * 1.5:
        behavior = "DISTRIBUTION"
    else:
        behavior = "AMBIGUOUS"

    return {
        "accumulation_score": acc_score,
        "distribution_score": dist_score,
        "behavior_classification": behavior,
    }



# =============================================================================
# Wyckoff / Weis Phase 5: Dissection of the Strongest Bucket
# =============================================================================
#
# Research question:
#   Inside the strongest performing bucket identified in prior phases
#   (Late Expansion + 20%+ Off High + RelVol 2-3X),
#   what behavioral and trajectory variables distinguish the top-quartile
#   performers from the bottom-quartile performers?
#
#   The goal is to find the resident's address inside the profitable neighborhood.
#
# The dissection runs on two populations:
#   A. The full universe — to establish what each variable means at baseline.
#   B. The target bucket — Late + 20% Off + 2-3x RelVol — to see what differs
#      inside the best-performing context.
#
# Variables dissected:
#   1. Price trajectory (10-day) leading into the signal
#   2. Volume trend leading into the signal
#   3. RS daily trajectory (10-day) leading into the signal
#   4. Days since the 252-day high was set
#   5. DNA tier
#   6. Five-bar absorption presence (ABS5)
#   7. Behavioral classification (Phase 4)
#   8. Accumulation score tier (Phase 4)
#   9. RS daily range at signal
#  10. Interaction: price trajectory x RS trajectory (the dual momentum test)
# =============================================================================



# =============================================================================
# Weis Wave / Behavioral Efficiency Engine
# =============================================================================
#
# Weis's central insight: price does not unfold in equal time slices.
# It unfolds in directional waves.  Each wave has three measurable properties:
#   length   — how far price traveled (price efficiency)
#   duration — how many bars the wave lasted
#   volume   — cumulative volume during the wave (volume efficiency)
#
# By comparing successive waves on these dimensions, we can detect:
#   - Shortening of upward thrust  (demand tiring)
#   - Diminishing selling pressure (supply exhausted)
#   - Springboard formation        (tiny low-volume down-wave before markup)
#   - Buoyancy near support        (close clustering; resolution imminent)
#   - Failure to follow through    (threatening bar absorbed by demand)
#
# Research question:
#   Do improving wave characteristics near structural levels
#   predict asymmetric forward returns?
# =============================================================================


def _identify_swing_points(
    bars: List[Bar],
    idx: int,
    lookback: int = 60,
    n_confirm: int = 2,
) -> Tuple[List[Tuple[int, float, str]], List[Tuple[int, float]]]:
    """
    Identify swing highs and swing lows in the lookback window.

    A swing high is a bar whose high exceeds the n_confirm bars on each side.
    A swing low  is a bar whose low  is below  the n_confirm bars on each side.

    Returns two lists:
        swing_points: [(idx, price, "high"/"low"), ...]  — all swings, sorted ascending
        waves:        not returned directly; caller builds waves from swing_points
    """
    start = max(n_confirm, idx - lookback + 1)
    end   = max(0, idx - n_confirm)   # need n_confirm bars after for confirmation

    swing_highs: List[Tuple[int, float]] = []
    swing_lows:  List[Tuple[int, float]] = []

    for j in range(start, end + 1):
        # Swing high: higher than n_confirm bars on both sides
        is_sh = all(bars[j].h >= bars[j - k].h for k in range(1, n_confirm + 1)) and                 all(bars[j].h >= bars[j + k].h for k in range(1, n_confirm + 1))
        if is_sh:
            swing_highs.append((j, bars[j].h))

        # Swing low: lower than n_confirm bars on both sides
        is_sl = all(bars[j].l <= bars[j - k].l for k in range(1, n_confirm + 1)) and                 all(bars[j].l <= bars[j + k].l for k in range(1, n_confirm + 1))
        if is_sl:
            swing_lows.append((j, bars[j].l))

    # Merge and sort
    swings: List[Tuple[int, float, str]] = (
        [(idx_, price, "high") for idx_, price in swing_highs] +
        [(idx_, price, "low")  for idx_, price in swing_lows]
    )
    swings.sort(key=lambda x: x[0])

    return swings


def _build_waves_from_swings(
    bars: List[Bar],
    swings: List[Tuple[int, float, str]],
    avg_volume_20: float,
) -> List[Dict[str, Any]]:
    """
    Convert swing points into waves with length, duration, volume, and efficiency.

    A wave is defined as the move from one swing point to the next in the
    alternating sequence high→low→high or low→high→low.

    Returns a list of wave dicts sorted oldest to newest.
    """
    if len(swings) < 2:
        return []

    waves: List[Dict[str, Any]] = []

    # Deduplicate consecutive same-type swings, keeping the more extreme one
    deduped: List[Tuple[int, float, str]] = []
    for s in swings:
        if deduped and deduped[-1][2] == s[2]:
            # Same type: keep the more extreme
            prev = deduped[-1]
            if s[2] == "high" and s[1] > prev[1]:
                deduped[-1] = s
            elif s[2] == "low" and s[1] < prev[1]:
                deduped[-1] = s
        else:
            deduped.append(s)

    for k in range(len(deduped) - 1):
        s1 = deduped[k]
        s2 = deduped[k + 1]

        start_idx, start_price, start_type = s1
        end_idx,   end_price,   end_type   = s2

        if start_type == end_type:
            continue  # malformed pair, skip

        direction = "up" if end_type == "high" else "down"
        duration  = max(1, end_idx - start_idx)

        # Cumulative volume across the wave bars
        wave_vol = sum(bars[j].v for j in range(start_idx, end_idx + 1))

        wave_return_pct = abs((end_price - start_price) / start_price * 100.0)                           if start_price > 0 else 0.0

        # Expected volume for the same duration at 20-bar average
        expected_vol = max(avg_volume_20 * duration, 1.0)
        wave_vol_ratio = wave_vol / expected_vol

        # Price efficiency: return per bar (speed through time)
        wave_price_eff = round(wave_return_pct / duration, 4)

        # Volume efficiency: return per unit of relative volume effort
        # Floor at 0.1 to prevent extreme readings on ultra-quiet waves
        wave_vol_eff = round(wave_return_pct / max(wave_vol_ratio, 0.1), 4)

        waves.append({
            "direction":          direction,
            "start_idx":          start_idx,
            "end_idx":            end_idx,
            "start_price":        round(start_price, 4),
            "end_price":          round(end_price, 4),
            "wave_return_pct":    round(wave_return_pct, 3),
            "wave_duration_bars": duration,
            "wave_total_volume":  round(wave_vol, 0),
            "wave_vol_ratio":     round(wave_vol_ratio, 3),
            "wave_price_eff":     wave_price_eff,
            "wave_vol_eff":       wave_vol_eff,
        })

    return waves


def _compute_wave_variables(
    bars: List[Bar],
    idx: int,
    support_level: float,
    avg_vol_20: float,
    atr: float,
    lookback: int = 60,
) -> Dict[str, Any]:
    """
    Compute all Weis Wave / Behavioral Efficiency variables for a signal at idx.

    Returns a flat dict of wave metrics ready to store in the signal row.
    """
    empty = {
        # Last 3 up-waves
        "w_up1_return_pct": 0.0, "w_up1_duration": 0,
        "w_up1_vol_ratio": 0.0,  "w_up1_price_eff": 0.0, "w_up1_vol_eff": 0.0,
        "w_up2_return_pct": 0.0, "w_up2_duration": 0,
        "w_up2_vol_ratio": 0.0,  "w_up2_price_eff": 0.0, "w_up2_vol_eff": 0.0,
        "w_up3_return_pct": 0.0, "w_up3_duration": 0,
        "w_up3_vol_ratio": 0.0,  "w_up3_price_eff": 0.0, "w_up3_vol_eff": 0.0,
        # Last 3 down-waves
        "w_dn1_return_pct": 0.0, "w_dn1_duration": 0,
        "w_dn1_vol_ratio": 0.0,  "w_dn1_price_eff": 0.0, "w_dn1_vol_eff": 0.0,
        "w_dn2_return_pct": 0.0, "w_dn2_duration": 0,
        "w_dn2_vol_ratio": 0.0,  "w_dn2_price_eff": 0.0, "w_dn2_vol_eff": 0.0,
        "w_dn3_return_pct": 0.0, "w_dn3_duration": 0,
        "w_dn3_vol_ratio": 0.0,  "w_dn3_price_eff": 0.0, "w_dn3_vol_eff": 0.0,
        # Derived behavioral flags
        "w_thrust_shortening":          False,
        "w_thrust_shortening_ratio":    1.0,
        "w_selling_pressure_diminishing": False,
        "w_demand_efficiency_improving": False,
        "w_springboard_present":        False,
        "w_buoyancy_near_support":      False,
        "w_failure_to_follow_through":  False,
        "w_wave_efficiency_score":      0,
        "w_wave_efficiency_bucket":     "WAVE_INSUFFICIENT_DATA",
    }

    if idx < 10 or avg_vol_20 <= 0:
        return empty

    swings = _identify_swing_points(bars, idx, lookback=lookback, n_confirm=2)
    if len(swings) < 4:
        return empty

    waves = _build_waves_from_swings(bars, swings, avg_vol_20)
    if not waves:
        return empty

    # Separate into up and down waves, most recent first
    up_waves  = [w for w in reversed(waves) if w["direction"] == "up"]
    dn_waves  = [w for w in reversed(waves) if w["direction"] == "down"]

    result: Dict[str, Any] = dict(empty)

    # Store last 3 of each direction
    for k, prefix in enumerate(["w_up1", "w_up2", "w_up3"]):
        if k < len(up_waves):
            w = up_waves[k]
            result[f"{prefix}_return_pct"] = w["wave_return_pct"]
            result[f"{prefix}_duration"]   = w["wave_duration_bars"]
            result[f"{prefix}_vol_ratio"]  = w["wave_vol_ratio"]
            result[f"{prefix}_price_eff"]  = w["wave_price_eff"]
            result[f"{prefix}_vol_eff"]    = w["wave_vol_eff"]

    for k, prefix in enumerate(["w_dn1", "w_dn2", "w_dn3"]):
        if k < len(dn_waves):
            w = dn_waves[k]
            result[f"{prefix}_return_pct"] = w["wave_return_pct"]
            result[f"{prefix}_duration"]   = w["wave_duration_bars"]
            result[f"{prefix}_vol_ratio"]  = w["wave_vol_ratio"]
            result[f"{prefix}_price_eff"]  = w["wave_price_eff"]
            result[f"{prefix}_vol_eff"]    = w["wave_vol_eff"]

    # ── Shortening of Upward Thrust ──────────────────────────────────────────
    # Three successive up-waves where each is shorter than the prior.
    # Ratio < 1.0 means most recent wave is smaller than two waves ago.
    if len(up_waves) >= 3:
        sot = (
            up_waves[0]["wave_return_pct"] < up_waves[1]["wave_return_pct"]
            and up_waves[1]["wave_return_pct"] < up_waves[2]["wave_return_pct"]
        )
        result["w_thrust_shortening"] = sot
        if up_waves[2]["wave_return_pct"] > 0:
            result["w_thrust_shortening_ratio"] = round(
                up_waves[0]["wave_return_pct"] / up_waves[2]["wave_return_pct"], 3
            )
    elif len(up_waves) >= 2:
        sot = up_waves[0]["wave_return_pct"] < up_waves[1]["wave_return_pct"]
        result["w_thrust_shortening"] = sot

    # ── Diminishing Selling Pressure ─────────────────────────────────────────
    # Most recent down-wave is smaller AND has lower volume than the prior one.
    # Sellers working less and achieving less = accumulation signature.
    if len(dn_waves) >= 2:
        result["w_selling_pressure_diminishing"] = (
            dn_waves[0]["wave_return_pct"] <= dn_waves[1]["wave_return_pct"]
            and dn_waves[0]["wave_total_volume"] < dn_waves[1]["wave_total_volume"]
        )

    # ── Demand Efficiency Improving ──────────────────────────────────────────
    # Most recent up-wave is more price-efficient than the prior.
    # Buyers achieving more progress per bar without proportionally more volume.
    if len(up_waves) >= 2:
        result["w_demand_efficiency_improving"] = (
            up_waves[0]["wave_price_eff"] > up_waves[1]["wave_price_eff"] * 0.9
            and up_waves[0]["wave_return_pct"] >= up_waves[1]["wave_return_pct"] * 0.7
        )

    # ── Springboard ──────────────────────────────────────────────────────────
    # Most recent down-wave is tiny and quiet — Weis's pre-markup signal.
    # The market is at rest before the next directional move.
    if len(dn_waves) >= 1:
        dn1 = dn_waves[0]
        avg_dn_return = (
            sum(w["wave_return_pct"] for w in dn_waves[:3]) / min(len(dn_waves), 3)
        )
        result["w_springboard_present"] = (
            dn1["wave_return_pct"] < atr / bars[idx].c * 100.0 * 0.8
            and dn1["wave_vol_ratio"] < 0.6
            and dn1["wave_return_pct"] < avg_dn_return * 0.5
        )

    # ── Buoyancy Near Support ────────────────────────────────────────────────
    # Closes clustering near support over prior 5 bars.
    # Tight clustering = stock being held up; resolution imminent.
    if support_level > 0 and atr > 0 and idx >= 4:
        recent_closes = [bars[idx - k].c for k in range(5)]
        closes_near = [c for c in recent_closes
                       if abs(c - support_level) < atr * 1.2]
        if len(closes_near) >= 3:
            close_std = statistics.stdev(closes_near) if len(closes_near) > 1 else 0.0
            result["w_buoyancy_near_support"] = close_std < atr * 0.35
        else:
            result["w_buoyancy_near_support"] = False

    # ── Failure to Follow Through ────────────────────────────────────────────
    # A bar with a threatening low (penetrating support or wide range)
    # that does NOT produce a lower close in the next 1-2 bars.
    if support_level > 0 and idx >= 2:
        bar = bars[idx]
        threatening = (
            bar.l < support_level
            or (bar.h - bar.l) > atr * 1.5
        )
        if threatening and idx + 2 < len(bars):
            no_follow = all(bars[idx + j].c >= bar.l * 0.995 for j in range(1, 3))
            result["w_failure_to_follow_through"] = threatening and no_follow
        else:
            result["w_failure_to_follow_through"] = threatening and True  # end of data, assume held

    # ── Wave Efficiency Composite Score ──────────────────────────────────────
    # 0-8 score combining all behavioral signals.
    # Higher = more Weis-favorable conditions for a Trade About to Happen.
    score = 0
    if result["w_selling_pressure_diminishing"]:   score += 2
    if result["w_demand_efficiency_improving"]:    score += 2
    if result["w_springboard_present"]:            score += 2
    if result["w_buoyancy_near_support"]:          score += 1
    if result["w_failure_to_follow_through"]:      score += 1
    # Deduct for thrust shortening (selling context, not buying setup)
    if result["w_thrust_shortening"]:              score -= 1
    score = max(0, score)

    result["w_wave_efficiency_score"] = score
    if score >= 6:
        result["w_wave_efficiency_bucket"] = "WAVE_EFF_HIGH_6_PLUS"
    elif score >= 4:
        result["w_wave_efficiency_bucket"] = "WAVE_EFF_MID_4_5"
    elif score >= 2:
        result["w_wave_efficiency_bucket"] = "WAVE_EFF_LOW_2_3"
    else:
        result["w_wave_efficiency_bucket"] = "WAVE_EFF_NONE_0_1"

    return result



# =============================================================================
# Wyckoff / Weis Phase 6: Behavioral Efficiency Study
# =============================================================================
#
# Research question:
#   Do improving wave characteristics near structural levels
#   predict asymmetric forward returns?
#
# This phase tests the Weis Wave variables computed above against the same
# target bucket used in Phase 5 (Late + 20%+ Off High + RelVol 2-3x).
#
# Studies:
#   A — Wave efficiency bucket vs forward MFE and asymmetry
#   B — Selling pressure diminishing vs forward MFE
#   C — Demand efficiency improving vs forward MFE
#   D — Springboard present vs forward MFE
#   E — Buoyancy near support vs forward MFE
#   F — Failure to follow through vs forward MFE
#   G — Combined: diminishing selling + improving demand (the dual confirmation)
#   H — Combined: springboard + buoyancy (the imminent resolution signal)
#   I — Full confluence: all favorable conditions together
#   J — Wave efficiency score tier vs forward MFE (monotonic test)
# =============================================================================


def summarize_wyckoff_phase6_wave_efficiency(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Phase 6: Weis Wave / Behavioral Efficiency.

    For each variable, runs two parallel studies:
      1. Full universe — establishes baseline for each bucket
      2. Target bucket — Late + 20%+ Off High + RelVol 2-3x

    The asymmetry ratio (MFE/MAE at 20 days) is the primary validation metric.
    Target: asymmetry > 2.0 for favorable conditions vs base rate.
    """

    def _safe_float(val: Any) -> Optional[float]:
        try:
            v = float(val)
            return v if math.isfinite(v) else None
        except Exception:
            return None

    def _payload(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h20 = r.get("h20")
        h90 = r.get("h90")
        if not isinstance(h20, dict) or not isinstance(h90, dict):
            return None
        mfe20 = _safe_float(r.get("markup_20d_pct"))
        mfe90 = _safe_float(r.get("markup_90d_pct"))
        if mfe90 is None:
            return None
        mae20 = float(h20.get("mae_pct", 0.0))
        asym  = (mfe20 / abs(mae20)) if (mfe20 and mfe20 > 0 and mae20 < 0) else 0.0
        return {
            "acc_20d":  float(h20.get("direction_correct", 0.0)),
            "ret_20d":  float(h20.get("return_pct", 0.0)),
            "mfe_20d":  mfe20 if mfe20 is not None else 0.0,
            "mae_20d":  mae20,
            "asym_20d": asym,
            "acc_90d":  float(h90.get("direction_correct", 0.0)),
            "ret_90d":  float(h90.get("return_pct", 0.0)),
            "mfe_90d":  mfe90,
            "mae_90d":  float(h90.get("mae_pct", 0.0)),
        }

    def _summ(bucket_map: Dict[str, List], min_n: int = 15) -> List[Dict[str, Any]]:
        out = []
        for bucket, vals in sorted(bucket_map.items()):
            if len(vals) < min_n:
                continue
            n = len(vals)
            avg = lambda f: round(sum(v[f] for v in vals) / n, 3)
            asym_vals = [v["asym_20d"] for v in vals if v["asym_20d"] > 0]
            out.append({
                "bucket":          bucket,
                "signals":         n,
                "acc_20d_pct":     round(avg("acc_20d") * 100, 2),
                "avg_mfe_20d_pct": avg("mfe_20d"),
                "avg_mae_20d_pct": avg("mae_20d"),
                "avg_asym_20d":    round(sum(asym_vals)/len(asym_vals), 3) if asym_vals else None,
                "acc_90d_pct":     round(avg("acc_90d") * 100, 2),
                "avg_ret_90d_pct": avg("ret_90d"),
                "avg_mfe_90d_pct": avg("mfe_90d"),
                "avg_mae_90d_pct": avg("mae_90d"),
            })
        out.sort(key=lambda x: x["avg_mfe_90d_pct"], reverse=True)
        return out

    universe_rows = []
    target_rows   = []
    for r in rows:
        p = _payload(r)
        if p is None:
            continue
        universe_rows.append((r, p))
        if _is_target_bucket(r):
            target_rows.append((r, p))

    def _populate(population: List[tuple]) -> Dict[str, Dict[str, List]]:
        g: Dict[str, Dict[str, List]] = {
            # Study A
            "wave_efficiency_bucket":   defaultdict(list),
            # Study J — score tier (monotonic test)
            "wave_efficiency_score_tier": defaultdict(list),
            # Studies B-F — individual behavioral flags
            "selling_pressure_dim":     defaultdict(list),
            "demand_eff_improving":     defaultdict(list),
            "springboard":              defaultdict(list),
            "buoyancy":                 defaultdict(list),
            "failure_follow_through":   defaultdict(list),
            "thrust_shortening":        defaultdict(list),
            # Study G — dual demand confirmation
            "dual_demand_confirm":      defaultdict(list),
            # Study H — imminent resolution
            "imminent_resolution":      defaultdict(list),
            # Study I — full confluence
            "full_confluence":          defaultdict(list),
            # Interactions
            "buoyancy_x_springboard":   defaultdict(list),
            "dim_sell_x_impr_demand":   defaultdict(list),
            "wave_score_x_behavior":    defaultdict(list),
            # Up-wave efficiency tiers
            "up1_price_eff_tier":       defaultdict(list),
            "dn1_vol_eff_tier":         defaultdict(list),
        }

        for r, p in population:
            wbkt  = str(r.get("w_wave_efficiency_bucket",       "WAVE_INSUFFICIENT_DATA"))
            score = int(r.get("w_wave_efficiency_score",         0) or 0)
            spd   = bool(r.get("w_selling_pressure_diminishing", False))
            dei   = bool(r.get("w_demand_efficiency_improving",  False))
            spb   = bool(r.get("w_springboard_present",          False))
            buy   = bool(r.get("w_buoyancy_near_support",        False))
            ftf   = bool(r.get("w_failure_to_follow_through",    False))
            tsh   = bool(r.get("w_thrust_shortening",            False))
            bhv   = str(r.get("behavior_classification",         "NEUTRAL"))

            # Score tier
            if score >= 6:
                stier = "SCORE_6_PLUS"
            elif score >= 4:
                stier = "SCORE_4_5"
            elif score >= 2:
                stier = "SCORE_2_3"
            else:
                stier = "SCORE_0_1"

            # Up-wave price efficiency tier
            up1_pe = _safe_float(r.get("w_up1_price_eff")) or 0.0
            if up1_pe >= 2.0:
                up1_tier = "UP1_PRICE_EFF_HIGH_2_PLUS"
            elif up1_pe >= 1.0:
                up1_tier = "UP1_PRICE_EFF_MID_1_2"
            elif up1_pe >= 0.3:
                up1_tier = "UP1_PRICE_EFF_LOW_0_3_1"
            else:
                up1_tier = "UP1_PRICE_EFF_VERY_LOW_UNDER_0_3"

            # Down-wave volume efficiency tier
            dn1_ve = _safe_float(r.get("w_dn1_vol_eff")) or 0.0
            if dn1_ve >= 5.0:
                dn1_tier = "DN1_VOL_EFF_HIGH_5_PLUS"
            elif dn1_ve >= 2.0:
                dn1_tier = "DN1_VOL_EFF_MID_2_5"
            elif dn1_ve >= 0.5:
                dn1_tier = "DN1_VOL_EFF_LOW_0_5_2"
            else:
                dn1_tier = "DN1_VOL_EFF_VERY_LOW_UNDER_0_5"

            g["wave_efficiency_bucket"][wbkt].append(p)
            g["wave_efficiency_score_tier"][stier].append(p)

            g["selling_pressure_dim"]["SPD_YES" if spd else "SPD_NO"].append(p)
            g["demand_eff_improving"]["DEI_YES"  if dei else "DEI_NO"].append(p)
            g["springboard"]["SPB_YES"           if spb else "SPB_NO"].append(p)
            g["buoyancy"]["BUY_YES"              if buy else "BUY_NO"].append(p)
            g["failure_follow_through"]["FTF_YES" if ftf else "FTF_NO"].append(p)
            g["thrust_shortening"]["TSH_YES"     if tsh else "TSH_NO"].append(p)

            # Study G: diminishing selling + improving demand
            dual = spd and dei
            g["dual_demand_confirm"]["DUAL_CONFIRM_YES" if dual else "DUAL_CONFIRM_NO"].append(p)

            # Study H: springboard + buoyancy = imminent resolution
            imm = spb or buy
            g["imminent_resolution"]["IMMINENT_YES" if imm else "IMMINENT_NO"].append(p)

            # Study I: full confluence (both H conditions + diminishing selling)
            full = spd and (spb or buy)
            g["full_confluence"]["FULL_CONFLUENCE_YES" if full else "FULL_CONFLUENCE_NO"].append(p)

            # Interactions
            g["buoyancy_x_springboard"][f"BUY={'Y' if buy else 'N'}|SPB={'Y' if spb else 'N'}"].append(p)
            g["dim_sell_x_impr_demand"][f"SPD={'Y' if spd else 'N'}|DEI={'Y' if dei else 'N'}"].append(p)
            g["wave_score_x_behavior"][f"{stier}|{bhv}"].append(p)
            g["up1_price_eff_tier"][up1_tier].append(p)
            g["dn1_vol_eff_tier"][dn1_tier].append(p)

        return g

    universe_groups = _populate(universe_rows)
    target_groups   = _populate(target_rows)

    result: Dict[str, Any] = {
        "target_bucket_n": len(target_rows),
        "universe_n":      len(universe_rows),
        "target_bucket_definition": {
            "setup_type":        "Volatility Expansion Candidate",
            "expansion_phase":   "EXP_PHASE_LATE",
            "rel_volume_bucket": "RELVOL_2_0_3_0X",
            "distance_from_high": "20PCT_PLUS_OFF",
        },
    }

    study_names = [
        "wave_efficiency_bucket",
        "wave_efficiency_score_tier",
        "selling_pressure_dim",
        "demand_eff_improving",
        "springboard",
        "buoyancy",
        "failure_follow_through",
        "thrust_shortening",
        "dual_demand_confirm",
        "imminent_resolution",
        "full_confluence",
        "buoyancy_x_springboard",
        "dim_sell_x_impr_demand",
        "wave_score_x_behavior",
        "up1_price_eff_tier",
        "dn1_vol_eff_tier",
    ]

    for name in study_names:
        result[f"universe_{name}"] = _summ(universe_groups[name], min_n=20)
        result[f"target_{name}"]   = _summ(target_groups[name],   min_n=5)

    return result


def _is_target_bucket(r: Dict[str, Any]) -> bool:
    """
    Filter for the strongest bucket from prior phases:
      Late Expansion + 20%+ Off High + RelVol 2.0-3.0x.

    This is the neighborhood identified in Phase 0 through Phase 4.
    Phase 5 zooms inside it.
    """
    setup    = str(r.get("setup_type", ""))
    phase    = str(r.get("expansion_phase_bucket", ""))
    relvol   = str(r.get("rel_volume_bucket", ""))

    try:
        dist = float(r.get("distance_from_252_high_pct", 0) or 0)
    except Exception:
        dist = 0.0

    return (
        setup == "Volatility Expansion Candidate"
        and phase == "EXP_PHASE_LATE"
        and relvol == "RELVOL_2_0_3_0X"
        and dist <= -20.0
    )


def summarize_wyckoff_phase5_dissection(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Phase 5: Dissect the strongest bucket to find the winning variables.

    For each variable of interest, produce two tables side by side:
      - full_universe: performance across ALL qualified long signals
      - target_bucket: performance across LATE + 20%OFF + 2-3x only

    The comparison reveals whether each variable adds information
    beyond what the bucket membership already provides.

    Outcome quartiles are assigned based on 90-day MFE within
    each population independently, so quartile boundaries are
    population-specific rather than universe-wide.
    """

    def _safe_float(val: Any) -> Optional[float]:
        try:
            v = float(val)
            return v if math.isfinite(v) else None
        except Exception:
            return None

    def _p5_payload(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h20 = r.get("h20")
        h90 = r.get("h90")
        if not isinstance(h20, dict) or not isinstance(h90, dict):
            return None
        mfe90 = _safe_float(r.get("markup_90d_pct"))
        mfe20 = _safe_float(r.get("markup_20d_pct"))
        if mfe90 is None:
            return None
        try:
            mae20 = float(h20.get("mae_pct", 0.0))
            asym  = (mfe20 / abs(mae20)) if (mfe20 and mae20 < 0) else 0.0
            return {
                "acc_20d":  float(h20.get("direction_correct", 0.0)),
                "ret_20d":  float(h20.get("return_pct", 0.0)),
                "mfe_20d":  mfe20 if mfe20 is not None else 0.0,
                "mae_20d":  mae20,
                "asym_20d": asym,
                "acc_90d":  float(h90.get("direction_correct", 0.0)),
                "ret_90d":  float(h90.get("return_pct", 0.0)),
                "mfe_90d":  mfe90,
                "mae_90d":  float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    def _summarize_bucket(
        bucket_map: Dict[str, List[Dict[str, float]]],
        min_signals: int = 15,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for bucket, vals in sorted(bucket_map.items()):
            if len(vals) < min_signals:
                continue
            n = len(vals)
            avg = lambda f: round(sum(v[f] for v in vals) / n, 3)
            asym_vals = [v["asym_20d"] for v in vals if v["asym_20d"] > 0]
            out.append({
                "bucket":          bucket,
                "signals":         n,
                "acc_20d_pct":     round(avg("acc_20d") * 100, 2),
                "avg_mfe_20d_pct": avg("mfe_20d"),
                "avg_mae_20d_pct": avg("mae_20d"),
                "avg_asym_20d":    round(sum(asym_vals)/len(asym_vals), 3) if asym_vals else None,
                "acc_90d_pct":     round(avg("acc_90d") * 100, 2),
                "avg_ret_90d_pct": avg("ret_90d"),
                "avg_mfe_90d_pct": avg("mfe_90d"),
                "avg_mae_90d_pct": avg("mae_90d"),
            })
        out.sort(key=lambda x: x["avg_mfe_90d_pct"], reverse=True)
        return out

    # Separate the two populations
    universe_rows = []
    target_rows   = []
    for r in rows:
        p = _p5_payload(r)
        if p is None:
            continue
        universe_rows.append((r, p))
        if _is_target_bucket(r):
            target_rows.append((r, p))

    def _build_groups(population: List[tuple]) -> Dict[str, Dict[str, List]]:
        """Build all variable bucket maps for one population."""
        g: Dict[str, Dict[str, List]] = {
            "price_trajectory":      defaultdict(list),
            "volume_trend":          defaultdict(list),
            "rs_trajectory":         defaultdict(list),
            "days_since_high":       defaultdict(list),
            "dna_tier":              defaultdict(list),
            "abs5_presence":         defaultdict(list),
            "behavior_class":        defaultdict(list),
            "accumulation_tier":     defaultdict(list),
            "rs_daily_range":        defaultdict(list),
            "price_x_rs_trajectory": defaultdict(list),
            "vol_trend_x_price_traj": defaultdict(list),
            "days_since_high_x_price_traj": defaultdict(list),
        }

        rs_daily_buckets = [
            (0, 20,  "RS_DAILY_0_20"),
            (20, 30, "RS_DAILY_20_30"),
            (30, 40, "RS_DAILY_30_40"),
            (40, 50, "RS_DAILY_40_50"),
            (50, 60, "RS_DAILY_50_60"),
            (60, 70, "RS_DAILY_60_70"),
            (70, 80, "RS_DAILY_70_80"),
            (80, 90, "RS_DAILY_80_90"),
            (90, 101,"RS_DAILY_90_100"),
        ]

        for r, p in population:
            ptraj  = str(r.get("p5_price_traj_bucket",    "UNKNOWN"))
            vtrend = str(r.get("p5_vol_trend_bucket",     "UNKNOWN"))
            rstraj = str(r.get("p5_rs_traj_bucket",       "UNKNOWN"))
            dhigh  = str(r.get("p5_days_since_high_bucket","UNKNOWN"))
            dna    = str(r.get("volatility_dna_tier",     "UNKNOWN"))
            bhv    = str(r.get("behavior_classification", "UNKNOWN"))

            abs5_60 = int(r.get("abs5_count_60", 0) or 0)
            abs5_label = "ABS5_PRESENT_1_PLUS" if abs5_60 >= 1 else "ABS5_ABSENT"

            acc_score = int(r.get("accumulation_score", 0) or 0)
            if acc_score >= 7:
                acc_tier = "ACC_7_PLUS"
            elif acc_score >= 5:
                acc_tier = "ACC_5_6"
            elif acc_score >= 3:
                acc_tier = "ACC_3_4"
            else:
                acc_tier = "ACC_0_2"

            rs_daily_val = _safe_float(r.get("rs_daily"))
            rs_d_bucket = "RS_DAILY_UNKNOWN"
            if rs_daily_val is not None:
                for lo, hi, label in rs_daily_buckets:
                    if lo <= rs_daily_val < hi:
                        rs_d_bucket = label
                        break

            g["price_trajectory"][ptraj].append(p)
            g["volume_trend"][vtrend].append(p)
            g["rs_trajectory"][rstraj].append(p)
            g["days_since_high"][dhigh].append(p)
            g["dna_tier"][dna].append(p)
            g["abs5_presence"][abs5_label].append(p)
            g["behavior_class"][bhv].append(p)
            g["accumulation_tier"][acc_tier].append(p)
            g["rs_daily_range"][rs_d_bucket].append(p)

            # Interaction: price trajectory x RS trajectory
            g["price_x_rs_trajectory"][f"{ptraj}|{rstraj}"].append(p)

            # Interaction: volume trend x price trajectory
            g["vol_trend_x_price_traj"][f"{vtrend}|{ptraj}"].append(p)

            # Interaction: days since high x price trajectory
            g["days_since_high_x_price_traj"][f"{dhigh}|{ptraj}"].append(p)

        return g

    universe_groups = _build_groups(universe_rows)
    target_groups   = _build_groups(target_rows)

    # Outcome quartile analysis within target bucket
    # Split target rows into top / bottom quartile by mfe90
    target_mfe90_vals = sorted(
        [p["mfe_90d"] for _, p in target_rows],
        reverse=True
    )
    if len(target_mfe90_vals) >= 4:
        q1_threshold = target_mfe90_vals[len(target_mfe90_vals) // 4]      # top 25%
        q4_threshold = target_mfe90_vals[(len(target_mfe90_vals) * 3) // 4] # bottom 25%
    else:
        q1_threshold = float("inf")
        q4_threshold = float("-inf")

    top_quartile_groups    = defaultdict(lambda: defaultdict(list))
    bottom_quartile_groups = defaultdict(lambda: defaultdict(list))

    for r, p in target_rows:
        mfe90 = p["mfe_90d"]
        for var_name in [
            "price_trajectory", "volume_trend", "rs_trajectory",
            "days_since_high", "dna_tier", "abs5_presence",
            "behavior_class", "rs_daily_range",
        ]:
            bucket_key = {
                "price_trajectory": str(r.get("p5_price_traj_bucket",    "UNKNOWN")),
                "volume_trend":     str(r.get("p5_vol_trend_bucket",     "UNKNOWN")),
                "rs_trajectory":    str(r.get("p5_rs_traj_bucket",       "UNKNOWN")),
                "days_since_high":  str(r.get("p5_days_since_high_bucket","UNKNOWN")),
                "dna_tier":         str(r.get("volatility_dna_tier",     "UNKNOWN")),
                "behavior_class":   str(r.get("behavior_classification", "UNKNOWN")),
                "abs5_presence":    "ABS5_PRESENT_1_PLUS" if int(r.get("abs5_count_60",0) or 0) >= 1 else "ABS5_ABSENT",
                "rs_daily_range":   "RS_DAILY_UNKNOWN",
            }[var_name]

            if var_name == "rs_daily_range":
                rs_val = _safe_float(r.get("rs_daily"))
                if rs_val is not None:
                    for lo, hi, lbl in [
                        (0,20,"RS_DAILY_0_20"),(20,30,"RS_DAILY_20_30"),
                        (30,40,"RS_DAILY_30_40"),(40,50,"RS_DAILY_40_50"),
                        (50,60,"RS_DAILY_50_60"),(60,70,"RS_DAILY_60_70"),
                        (70,80,"RS_DAILY_70_80"),(80,90,"RS_DAILY_80_90"),
                        (90,101,"RS_DAILY_90_100"),
                    ]:
                        if lo <= rs_val < hi:
                            bucket_key = lbl
                            break

            if mfe90 >= q1_threshold:
                top_quartile_groups[var_name][bucket_key].append(p)
            if mfe90 <= q4_threshold:
                bottom_quartile_groups[var_name][bucket_key].append(p)

    # Build final output structure
    result: Dict[str, Any] = {
        "target_bucket_definition": {
            "setup_type":            "Volatility Expansion Candidate",
            "expansion_phase":       "EXP_PHASE_LATE",
            "rel_volume_bucket":     "RELVOL_2_0_3_0X",
            "distance_from_high":    "20PCT_PLUS_OFF",
        },
        "target_bucket_n":   len(target_rows),
        "universe_n":        len(universe_rows),
        "quartile_thresholds": {
            "top_25pct_mfe90_threshold":    round(q1_threshold, 2) if math.isfinite(q1_threshold) else None,
            "bottom_25pct_mfe90_threshold": round(q4_threshold, 2) if math.isfinite(q4_threshold) else None,
        },
    }

    # Add universe and target summaries for each variable
    var_names = [
        "price_trajectory", "volume_trend", "rs_trajectory",
        "days_since_high", "dna_tier", "abs5_presence",
        "behavior_class", "accumulation_tier", "rs_daily_range",
        "price_x_rs_trajectory", "vol_trend_x_price_traj",
        "days_since_high_x_price_traj",
    ]
    for var in var_names:
        result[f"universe_{var}"] = _summarize_bucket(universe_groups[var], min_signals=20)
        result[f"target_{var}"]   = _summarize_bucket(target_groups[var],   min_signals=5)

    # Add quartile comparison tables
    for var in [
        "price_trajectory", "volume_trend", "rs_trajectory",
        "days_since_high", "dna_tier", "abs5_presence",
        "behavior_class", "rs_daily_range",
    ]:
        result[f"top_quartile_{var}"]    = _summarize_bucket(
            top_quartile_groups[var],    min_signals=3
        )
        result[f"bottom_quartile_{var}"] = _summarize_bucket(
            bottom_quartile_groups[var], min_signals=3
        )

    return result


def summarize_wyckoff_phase4_junctures(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Wyckoff / Weis Phase 4 study: Juncture Detection.

    Research question:
      Can we algorithmically detect springs, upthrusts, and absorption at
      structural levels, and do those junctures produce asymmetric forward
      returns compared to the base rate and to non-juncture absorption?

    Study A — Spring Detection
      Do detected springs produce forward rallies above the base rate?
      Is the MFE/MAE asymmetry > 2.0?

    Study B — Upthrust Detection
      Do detected upthrusts occur in signals that underperform?
      (Upthrusts are bearish; their presence in long signals warns of risk.)

    Study C — Absorption at Juncture vs Open Space
      Does absorption at support/resistance outperform absorption in open space?
      This directly resolves the Phase 3 null result.

    Study D — Behavioral Classification
      Does the accumulation label correctly predict positive outcomes?
      Does the distribution label correctly predict negative outcomes?

    Study E — Apex + Juncture Confluence
      Does coiling toward an apex combined with a juncture produce
      the highest asymmetric outcomes?

    Study F — Base Rate Validation
      What is the forward return of ALL qualified long signals?
      All juncture studies are compared against this baseline.
    """

    def _safe_float(val: Any) -> Optional[float]:
        try:
            v = float(val)
            return v if math.isfinite(v) else None
        except Exception:
            return None

    def _juncture_payload(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h20 = r.get("h20")
        h90 = r.get("h90")
        if not isinstance(h20, dict) or not isinstance(h90, dict):
            return None
        try:
            mfe20 = _safe_float(r.get("markup_20d_pct"))
            mfe90 = _safe_float(r.get("markup_90d_pct"))
            mae20 = float(h20.get("mae_pct", 0.0))
            asymmetry_20d = (mfe20 / abs(mae20)) if (mfe20 is not None and mae20 < 0) else None
            return {
                "direction_correct_20d": float(h20.get("direction_correct", 0.0)),
                "return_20d":            float(h20.get("return_pct", 0.0)),
                "mfe_20d":               mfe20 if mfe20 is not None else 0.0,
                "mae_20d":               mae20,
                "asymmetry_20d":         asymmetry_20d if asymmetry_20d is not None else 0.0,
                "direction_correct_90d": float(h90.get("direction_correct", 0.0)),
                "return_90d":            float(h90.get("return_pct", 0.0)),
                "mfe_90d":               mfe90 if mfe90 is not None else 0.0,
                "mae_90d":               float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    def _summarize_juncture(
        bucket_map: Dict[str, List[Dict[str, float]]],
        min_signals: int = 20,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for bucket, vals in sorted(bucket_map.items()):
            if len(vals) < min_signals:
                continue
            n = len(vals)
            avg = lambda field: round(sum(v[field] for v in vals) / n, 3)
            asym_vals = [v["asymmetry_20d"] for v in vals if v["asymmetry_20d"] > 0]
            avg_asym  = round(sum(asym_vals) / len(asym_vals), 3) if asym_vals else None
            out.append({
                "bucket":                  bucket,
                "signals":                 n,
                "acc_20d_pct":             round(avg("direction_correct_20d") * 100, 2),
                "avg_return_20d_pct":      avg("return_20d"),
                "avg_mfe_20d_pct":         avg("mfe_20d"),
                "avg_mae_20d_pct":         avg("mae_20d"),
                "avg_asymmetry_20d":       avg_asym,
                "acc_90d_pct":             round(avg("direction_correct_90d") * 100, 2),
                "avg_return_90d_pct":      avg("return_90d"),
                "avg_mfe_90d_pct":         avg("mfe_90d"),
                "avg_mae_90d_pct":         avg("mae_90d"),
            })
        out.sort(key=lambda x: x["avg_mfe_20d_pct"], reverse=True)
        return out

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        # Study A: Spring quality vs forward rally
        "study_a_spring_detection":        defaultdict(list),
        "study_a_spring_quality_vs_rally": defaultdict(list),

        # Study B: Upthrust presence in long signals
        "study_b_upthrust_detection":      defaultdict(list),

        # Study C: Absorption location — juncture vs open space
        "study_c_absorption_location":     defaultdict(list),
        "study_c_juncture_type_detail":    defaultdict(list),

        # Study D: Behavioral classification
        "study_d_behavior_classification": defaultdict(list),
        "study_d_accumulation_score_tier": defaultdict(list),

        # Study E: Apex confluence
        "study_e_apex_x_juncture":         defaultdict(list),
        "study_e_apex_x_behavior":         defaultdict(list),

        # Study F: Base rate — all signals
        "study_f_base_rate":               defaultdict(list),

        # Combined: Spring + Accumulation (the ideal signal)
        "combined_spring_x_behavior":      defaultdict(list),
        "combined_juncture_x_behavior_x_apex": defaultdict(list),
    }

    for r in rows:
        payload = _juncture_payload(r)
        if payload is None:
            continue

        spring      = bool(r.get("spring_detected",    False))
        upthrust    = bool(r.get("upthrust_detected",  False))
        at_juncture = bool(r.get("at_juncture",        False))
        apex        = bool(r.get("apex_detected",       False))
        behavior    = str(r.get("behavior_classification", "NEUTRAL"))
        jtype       = str(r.get("juncture_type",        "OPEN_SPACE"))
        spring_q    = int(r.get("spring_quality",       0) or 0)
        acc_score   = int(r.get("accumulation_score",   0) or 0)
        trading_range = bool(r.get("trading_range_detected", False))

        # Study A
        spring_label = f"SPRING_Q{spring_q}" if spring else "NO_SPRING"
        grouped["study_a_spring_detection"]["SPRING_DETECTED" if spring else "NO_SPRING"].append(payload)
        if spring:
            grouped["study_a_spring_quality_vs_rally"][spring_label].append(payload)

        # Study B
        grouped["study_b_upthrust_detection"]["UPTHRUST_DETECTED" if upthrust else "NO_UPTHRUST"].append(payload)

        # Study C
        grouped["study_c_absorption_location"][jtype].append(payload)
        if at_juncture:
            grouped["study_c_juncture_type_detail"]["JUNCTURE_" + jtype].append(payload)
        else:
            grouped["study_c_juncture_type_detail"]["NON_JUNCTURE_OPEN_SPACE"].append(payload)

        # Study D
        grouped["study_d_behavior_classification"][behavior].append(payload)
        if acc_score >= 7:
            acc_tier = "ACC_SCORE_7_PLUS"
        elif acc_score >= 5:
            acc_tier = "ACC_SCORE_5_6"
        elif acc_score >= 3:
            acc_tier = "ACC_SCORE_3_4"
        else:
            acc_tier = "ACC_SCORE_0_2"
        grouped["study_d_accumulation_score_tier"][acc_tier].append(payload)

        # Study E
        apex_label    = "APEX" if apex else "NO_APEX"
        juncture_label = "AT_JUNCTURE" if at_juncture else "OPEN_SPACE"
        grouped["study_e_apex_x_juncture"][f"{apex_label}|{juncture_label}"].append(payload)
        grouped["study_e_apex_x_behavior"][f"{apex_label}|{behavior}"].append(payload)

        # Study F — base rate
        grouped["study_f_base_rate"]["ALL_QUALIFIED_LONGS"].append(payload)
        if trading_range:
            grouped["study_f_base_rate"]["IN_TRADING_RANGE"].append(payload)
        else:
            grouped["study_f_base_rate"]["NOT_IN_TRADING_RANGE"].append(payload)

        # Combined
        spring_bhv = f"{'SPRING' if spring else 'NO_SPRING'}|{behavior}"
        grouped["combined_spring_x_behavior"][spring_bhv].append(payload)

        apex_juncture_bhv = f"{apex_label}|{juncture_label}|{behavior}"
        grouped["combined_juncture_x_behavior_x_apex"][apex_juncture_bhv].append(payload)

    return {
        name: _summarize_juncture(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }


def summarize_wyckoff_phase3_cause_effect(rows):
    """
    Wyckoff / Weis Phase 3 study: Cause -> Effect.

    Research questions:
      Study A -- Does absorption persistence exhibit monotonic alpha generation?
                 Bucket signals by abs1/abs5 count and compare markup MFE at 20/40/60/90 days.
      Study B -- Single-bar vs Multi-bar: does abs5 outperform abs1?
      Study C -- Dual Confirmation: does abs1 AND abs5 together outperform either alone?
      Study D -- Time Compression: does absorption clustered in 20 days beat absorption
                 spread over 60 days with the same total count?

    Markup is measured using Maximum Favorable Excursion (MFE) so intraperiod
    highs are captured rather than closing-price-only returns.
    """
    import math
    from collections import defaultdict

    def _safe_float(val):
        try:
            v = float(val)
            return v if math.isfinite(v) else None
        except Exception:
            return None

    def _markup_payload(r):
        m20 = _safe_float(r.get("markup_20d_pct"))
        m40 = _safe_float(r.get("markup_40d_pct"))
        m60 = _safe_float(r.get("markup_60d_pct"))
        m90 = _safe_float(r.get("markup_90d_pct"))
        if m90 is None:
            return None
        return {
            "markup_20d": m20 if m20 is not None else 0.0,
            "markup_40d": m40 if m40 is not None else 0.0,
            "markup_60d": m60 if m60 is not None else 0.0,
            "markup_90d": m90,
        }

    def _summarize_markup(bucket_map, min_signals=20):
        out = []
        for bucket, vals in sorted(bucket_map.items()):
            if len(vals) < min_signals:
                continue
            n = len(vals)
            out.append({
                "bucket": bucket,
                "signals": n,
                "avg_markup_20d_mfe_pct": round(sum(v["markup_20d"] for v in vals) / n, 3),
                "avg_markup_40d_mfe_pct": round(sum(v["markup_40d"] for v in vals) / n, 3),
                "avg_markup_60d_mfe_pct": round(sum(v["markup_60d"] for v in vals) / n, 3),
                "avg_markup_90d_mfe_pct": round(sum(v["markup_90d"] for v in vals) / n, 3),
            })
        out.sort(key=lambda x: x["avg_markup_90d_mfe_pct"], reverse=True)
        return out

    grouped = {
        # Study A: persistence tiers.
        "study_a_abs1_count_20_vs_markup": defaultdict(list),
        "study_a_abs1_count_40_vs_markup": defaultdict(list),
        "study_a_abs1_count_60_vs_markup": defaultdict(list),
        "study_a_abs5_count_20_vs_markup": defaultdict(list),
        "study_a_abs5_count_40_vs_markup": defaultdict(list),
        "study_a_abs5_count_60_vs_markup": defaultdict(list),
        # Study A: cause_score tier -> Markup.
        "study_a_cause_score_tier_vs_markup": defaultdict(list),
        # Study B: Single vs Multi-bar head-to-head.
        "study_b_abs1_vs_abs5": defaultdict(list),
        # Study C: Dual confirmation.
        "study_c_dual_confirmation": defaultdict(list),
        # Study D: Time compression.
        "study_d_time_compression": defaultdict(list),
        # Markup bucket distribution by cause score tier.
        "markup_bucket_by_cause_score_tier": defaultdict(list),
    }

    for r in rows:
        payload = _markup_payload(r)
        if payload is None:
            continue

        s20 = int(r.get("abs1_count_20", 0) or 0)
        s40 = int(r.get("abs1_count_40", 0) or 0)
        s60 = int(r.get("abs1_count_60", 0) or 0)
        f20 = int(r.get("abs5_count_20", 0) or 0)
        f40 = int(r.get("abs5_count_40", 0) or 0)
        f60 = int(r.get("abs5_count_60", 0) or 0)
        cause = _safe_float(r.get("cause_score")) or 0.0

        # Study A: persistence tiers.
        grouped["study_a_abs1_count_20_vs_markup"][_absorption_persistence_tier(s20)].append(payload)
        grouped["study_a_abs1_count_40_vs_markup"][_absorption_persistence_tier(s40)].append(payload)
        grouped["study_a_abs1_count_60_vs_markup"][_absorption_persistence_tier(s60)].append(payload)
        grouped["study_a_abs5_count_20_vs_markup"][_absorption_persistence_tier(f20)].append(payload)
        grouped["study_a_abs5_count_40_vs_markup"][_absorption_persistence_tier(f40)].append(payload)
        grouped["study_a_abs5_count_60_vs_markup"][_absorption_persistence_tier(f60)].append(payload)

        # Study A: cause score tier.
        if cause >= 20.0:
            cs_tier = "CAUSE_SCORE_20_PLUS"
        elif cause >= 12.0:
            cs_tier = "CAUSE_SCORE_12_20"
        elif cause >= 6.0:
            cs_tier = "CAUSE_SCORE_6_12"
        elif cause >= 2.0:
            cs_tier = "CAUSE_SCORE_2_6"
        else:
            cs_tier = "CAUSE_SCORE_0_2"
        grouped["study_a_cause_score_tier_vs_markup"][cs_tier].append(payload)

        # Study B: Single-bar vs Five-bar head-to-head (use 60-bar windows for breadth).
        abs1_only = s60 > 0 and f60 == 0
        abs5_only = f60 > 0 and s60 == 0
        both_present = s60 > 0 and f60 > 0
        if abs1_only:
            grouped["study_b_abs1_vs_abs5"]["ABS1_ONLY"].append(payload)
        elif abs5_only:
            grouped["study_b_abs1_vs_abs5"]["ABS5_ONLY"].append(payload)
        elif both_present:
            grouped["study_b_abs1_vs_abs5"]["BOTH_ABS1_AND_ABS5"].append(payload)
        else:
            grouped["study_b_abs1_vs_abs5"]["NEITHER"].append(payload)

        # Study C: Dual confirmation (both single AND five-bar in the 20-bar window).
        if s20 > 0 and f20 > 0:
            dual_label = "DUAL_CONFIRMED_BOTH_IN_20"
        elif s20 > 0:
            dual_label = "SINGLE_BAR_ONLY_IN_20"
        elif f20 > 0:
            dual_label = "FIVE_BAR_ONLY_IN_20"
        else:
            dual_label = "NO_ABSORPTION_IN_20"
        grouped["study_c_dual_confirmation"][dual_label].append(payload)

        # Study D: Time compression.
        # Clustered = same count packed into fewer days = stronger cause per Wyckoff.
        if s20 >= 3:
            compression = "CLUSTERED_3_PLUS_IN_20DAYS"
        elif s20 >= 2 and s40 <= s20 + 1:
            compression = "CLUSTERED_RECENT_TIGHT"
        elif s60 >= 4 and s20 <= 1:
            compression = "DISTRIBUTED_4_PLUS_IN_60DAYS"
        elif s60 >= 2:
            compression = "LIGHT_DISTRIBUTED"
        else:
            compression = "SPARSE_OR_NONE"
        grouped["study_d_time_compression"][compression].append(payload)

        # Markup bucket distribution.
        mb = str(r.get("markup_bucket", "MARKUP_INSUFFICIENT_DATA"))
        grouped["markup_bucket_by_cause_score_tier"][f"{cs_tier}|{mb}"].append(payload)

    return {
        name: _summarize_markup(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }


def summarize_wyckoff_persistent_absorption(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Wyckoff / Weis Phase 2 study: Persistent Absorption.

    Research question:
      Does repeated high-effort / low-result behavior produce better forward
      outcomes than isolated high-effort / low-result behavior?

    This is a pure Wyckoff/Weis persistence test.  It intentionally does NOT
    filter by RS, volatility, distance from high, expansion phase, or setup type.
    """
    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        "single_bar_absorption_count_20": defaultdict(list),
        "single_bar_absorption_count_40": defaultdict(list),
        "single_bar_absorption_count_60": defaultdict(list),
        "five_bar_absorption_count_20": defaultdict(list),
        "five_bar_absorption_count_40": defaultdict(list),
        "five_bar_absorption_count_60": defaultdict(list),
        "single_bar_absorption_cluster_shape": defaultdict(list),
        "five_bar_absorption_cluster_shape": defaultdict(list),
        "single_vs_five_bar_absorption_overlap": defaultdict(list),
    }

    def payload_from_h90(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    for r in rows:
        payload = payload_from_h90(r)
        if not payload:
            continue

        s20 = int(r.get("abs1_count_20", 0) or 0)
        s40 = int(r.get("abs1_count_40", 0) or 0)
        s60 = int(r.get("abs1_count_60", 0) or 0)
        f20 = int(r.get("abs5_count_20", 0) or 0)
        f40 = int(r.get("abs5_count_40", 0) or 0)
        f60 = int(r.get("abs5_count_60", 0) or 0)

        grouped["single_bar_absorption_count_20"][_absorption_persistence_tier(s20)].append(payload)
        grouped["single_bar_absorption_count_40"][_absorption_persistence_tier(s40)].append(payload)
        grouped["single_bar_absorption_count_60"][_absorption_persistence_tier(s60)].append(payload)
        grouped["five_bar_absorption_count_20"][_absorption_persistence_tier(f20)].append(payload)
        grouped["five_bar_absorption_count_40"][_absorption_persistence_tier(f40)].append(payload)
        grouped["five_bar_absorption_count_60"][_absorption_persistence_tier(f60)].append(payload)

        # Cluster shape: recent 20-bar persistence versus broader 60-bar persistence.
        if s20 >= 3:
            single_shape = "SINGLE_BAR_CLUSTERED_RECENT_3_PLUS_IN_20"
        elif s60 >= 4:
            single_shape = "SINGLE_BAR_DISTRIBUTED_PERSISTENT_4_PLUS_IN_60"
        elif s20 >= 1:
            single_shape = "SINGLE_BAR_ISOLATED_OR_LIGHT_CLUSTER"
        else:
            single_shape = "SINGLE_BAR_NO_ABSORPTION_CLUSTER"
        grouped["single_bar_absorption_cluster_shape"][single_shape].append(payload)

        if f20 >= 3:
            five_shape = "FIVE_BAR_CLUSTERED_RECENT_3_PLUS_IN_20"
        elif f60 >= 4:
            five_shape = "FIVE_BAR_DISTRIBUTED_PERSISTENT_4_PLUS_IN_60"
        elif f20 >= 1:
            five_shape = "FIVE_BAR_ISOLATED_OR_LIGHT_CLUSTER"
        else:
            five_shape = "FIVE_BAR_NO_ABSORPTION_CLUSTER"
        grouped["five_bar_absorption_cluster_shape"][five_shape].append(payload)

        if s20 >= 2 and f20 >= 2:
            overlap = "BOTH_SINGLE_AND_FIVE_BAR_PERSISTENT_2_PLUS_IN_20"
        elif s20 >= 2:
            overlap = "SINGLE_BAR_ONLY_PERSISTENT_2_PLUS_IN_20"
        elif f20 >= 2:
            overlap = "FIVE_BAR_ONLY_PERSISTENT_2_PLUS_IN_20"
        else:
            overlap = "NO_DUAL_PERSISTENCE"
        grouped["single_vs_five_bar_absorption_overlap"][overlap].append(payload)

    return {
        name: _summarize_group_perf(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }


def summarize_volatility_rs_distance_matrix(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Volatility + Relative Strength + Distance From High study.

    Research question:
      WHERE does volatility alpha appear when RS is cross-tested with
      distance from the 252-day high?

    This stays inside the volatility research bucket. It does not add
    Wyckoff/VSA/Gann/Elliott/etc.
    """
    rs_daily_buckets = [
        (0, 20, "RS_DAILY_0_20"),
        (20, 30, "RS_DAILY_20_30"),
        (30, 40, "RS_DAILY_30_40"),
        (40, 50, "RS_DAILY_40_50"),
        (50, 60, "RS_DAILY_50_60"),
        (60, 70, "RS_DAILY_60_70"),
        (70, 80, "RS_DAILY_70_80"),
        (80, 90, "RS_DAILY_80_90"),
        (90, 101, "RS_DAILY_90_100"),
    ]
    rs_2h_buckets = [
        (0, 20, "RS2H_0_20"),
        (20, 30, "RS2H_20_30"),
        (30, 40, "RS2H_30_40"),
        (40, 50, "RS2H_40_50"),
        (50, 60, "RS2H_50_60"),
        (60, 70, "RS2H_60_70"),
        (70, 80, "RS2H_70_80"),
        (80, 90, "RS2H_80_90"),
        (90, 101, "RS2H_90_100"),
    ]

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        "distance_x_daily_rs": defaultdict(list),
        "distance_x_2h_rs": defaultdict(list),
        "dna_tier_x_distance_x_daily_rs": defaultdict(list),
        "dna_tier_x_distance_x_2h_rs": defaultdict(list),
        "late_phase_x_distance_x_daily_rs": defaultdict(list),
        "late_phase_x_distance_x_2h_rs": defaultdict(list),
        "relvol_2to3x_x_distance_x_daily_rs": defaultdict(list),
        "relvol_2to3x_x_distance_x_2h_rs": defaultdict(list),
    }

    def payload_from_h90(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    def distance_bucket(r: Dict[str, Any]) -> str:
        try:
            d = float(r.get("distance_from_252_high_pct"))
        except Exception:
            d = float("nan")

        if not math.isfinite(d):
            return "HIGH_DISTANCE_UNKNOWN"
        if d <= -20.0:
            return "HIGH_DISTANCE_20PCT_PLUS_OFF"
        if d <= -10.0:
            return "HIGH_DISTANCE_10_20PCT_OFF"
        if d <= -5.0:
            return "HIGH_DISTANCE_5_10PCT_OFF"
        return "HIGH_DISTANCE_0_5PCT_OFF"

    for r in rows:
        if str(r.get("setup_type")) != "Volatility Expansion Candidate":
            continue

        payload = payload_from_h90(r)
        if not payload:
            continue

        daily_rs_bucket = _bucket_numeric(r.get("rs_daily"), rs_daily_buckets)
        rs2h_bucket = _bucket_numeric(r.get("rs_2h"), rs_2h_buckets)
        dist_bucket = distance_bucket(r)
        dna_tier = str(r.get("volatility_dna_tier", "UNKNOWN"))
        phase = str(r.get("expansion_phase_bucket", "UNKNOWN"))
        relvol_bucket = str(r.get("rel_volume_bucket", "UNKNOWN"))

        grouped["distance_x_daily_rs"][f"{dist_bucket}|{daily_rs_bucket}"].append(payload)
        grouped["distance_x_2h_rs"][f"{dist_bucket}|{rs2h_bucket}"].append(payload)
        grouped["dna_tier_x_distance_x_daily_rs"][f"{dna_tier}|{dist_bucket}|{daily_rs_bucket}"].append(payload)
        grouped["dna_tier_x_distance_x_2h_rs"][f"{dna_tier}|{dist_bucket}|{rs2h_bucket}"].append(payload)

        if phase == "EXP_PHASE_LATE":
            grouped["late_phase_x_distance_x_daily_rs"][f"{dist_bucket}|{daily_rs_bucket}"].append(payload)
            grouped["late_phase_x_distance_x_2h_rs"][f"{dist_bucket}|{rs2h_bucket}"].append(payload)

        if relvol_bucket == "RELVOL_2_0_3_0X":
            grouped["relvol_2to3x_x_distance_x_daily_rs"][f"{dist_bucket}|{daily_rs_bucket}"].append(payload)
            grouped["relvol_2to3x_x_distance_x_2h_rs"][f"{dist_bucket}|{rs2h_bucket}"].append(payload)

    return {
        name: _summarize_group_perf(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }



def summarize_volatility_rs_distance_relvol_matrix(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Final volatility study:
      Volatility + Relative Strength + Distance From High + Relative Volume.

    Research question:
      Does relative volume confirm, weaken, or change the alpha discovered in
      volatility expansion + RS + distance-from-high buckets?

    This intentionally shows BOTH low-volume and high-volume states.
    """
    rs_daily_buckets = [
        (0, 20, "RS_DAILY_0_20"),
        (20, 30, "RS_DAILY_20_30"),
        (30, 40, "RS_DAILY_30_40"),
        (40, 50, "RS_DAILY_40_50"),
        (50, 60, "RS_DAILY_50_60"),
        (60, 70, "RS_DAILY_60_70"),
        (70, 80, "RS_DAILY_70_80"),
        (80, 90, "RS_DAILY_80_90"),
        (90, 101, "RS_DAILY_90_100"),
    ]
    rs_2h_buckets = [
        (0, 20, "RS2H_0_20"),
        (20, 30, "RS2H_20_30"),
        (30, 40, "RS2H_30_40"),
        (40, 50, "RS2H_40_50"),
        (50, 60, "RS2H_50_60"),
        (60, 70, "RS2H_60_70"),
        (70, 80, "RS2H_70_80"),
        (80, 90, "RS2H_80_90"),
        (90, 101, "RS2H_90_100"),
    ]

    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        # Broad maps: show whether volume itself changes the distance/RS finding.
        "relvol_x_distance_x_daily_rs": defaultdict(list),
        "relvol_x_distance_x_2h_rs": defaultdict(list),

        # Phase-aware maps: show whether low/high volume means different things early/mid/late.
        "phase_x_relvol_x_distance": defaultdict(list),
        "phase_x_relvol_x_distance_x_daily_rs": defaultdict(list),
        "phase_x_relvol_x_distance_x_2h_rs": defaultdict(list),

        # Production-candidate maps: restrict to the strongest prior volatility DNA tier.
        "dna_tier_x_relvol_x_distance_x_daily_rs": defaultdict(list),
        "dna_tier_x_relvol_x_distance_x_2h_rs": defaultdict(list),

        # Clean answer to Greg's question: high volume confirmation vs low volume lack-of-conviction/quiet accumulation.
        "late_phase_relvol_x_distance": defaultdict(list),
        "twenty_off_relvol_x_rs2h": defaultdict(list),
    }

    def payload_from_h90(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    def distance_bucket(r: Dict[str, Any]) -> str:
        try:
            d = float(r.get("distance_from_252_high_pct"))
        except Exception:
            d = float("nan")
        if not math.isfinite(d):
            return "HIGH_DISTANCE_UNKNOWN"
        if d <= -20.0:
            return "HIGH_DISTANCE_20PCT_PLUS_OFF"
        if d <= -10.0:
            return "HIGH_DISTANCE_10_20PCT_OFF"
        if d <= -5.0:
            return "HIGH_DISTANCE_5_10PCT_OFF"
        return "HIGH_DISTANCE_0_5PCT_OFF"

    for r in rows:
        if str(r.get("setup_type")) != "Volatility Expansion Candidate":
            continue

        payload = payload_from_h90(r)
        if not payload:
            continue

        daily_rs_bucket = _bucket_numeric(r.get("rs_daily"), rs_daily_buckets)
        rs2h_bucket = _bucket_numeric(r.get("rs_2h"), rs_2h_buckets)
        dist_bucket = distance_bucket(r)
        dna_tier = str(r.get("volatility_dna_tier", "UNKNOWN"))
        phase = str(r.get("expansion_phase_bucket", "UNKNOWN"))
        relvol_bucket = str(r.get("rel_volume_bucket", "UNKNOWN"))

        grouped["relvol_x_distance_x_daily_rs"][f"{relvol_bucket}|{dist_bucket}|{daily_rs_bucket}"].append(payload)
        grouped["relvol_x_distance_x_2h_rs"][f"{relvol_bucket}|{dist_bucket}|{rs2h_bucket}"].append(payload)

        grouped["phase_x_relvol_x_distance"][f"{phase}|{relvol_bucket}|{dist_bucket}"].append(payload)
        grouped["phase_x_relvol_x_distance_x_daily_rs"][f"{phase}|{relvol_bucket}|{dist_bucket}|{daily_rs_bucket}"].append(payload)
        grouped["phase_x_relvol_x_distance_x_2h_rs"][f"{phase}|{relvol_bucket}|{dist_bucket}|{rs2h_bucket}"].append(payload)

        grouped["dna_tier_x_relvol_x_distance_x_daily_rs"][f"{dna_tier}|{relvol_bucket}|{dist_bucket}|{daily_rs_bucket}"].append(payload)
        grouped["dna_tier_x_relvol_x_distance_x_2h_rs"][f"{dna_tier}|{relvol_bucket}|{dist_bucket}|{rs2h_bucket}"].append(payload)

        if phase == "EXP_PHASE_LATE":
            grouped["late_phase_relvol_x_distance"][f"{relvol_bucket}|{dist_bucket}"].append(payload)

        if dist_bucket == "HIGH_DISTANCE_20PCT_PLUS_OFF":
            grouped["twenty_off_relvol_x_rs2h"][f"{relvol_bucket}|{rs2h_bucket}"].append(payload)

    return {
        name: _summarize_group_perf(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }


# -----------------------------------------------------------------------------
# Wyckoff / Weis Phase 1: Effort vs Result
# -----------------------------------------------------------------------------

def _true_range(bars: List[Bar], idx: int) -> float:
    if idx <= 0:
        return max(0.0, bars[idx].h - bars[idx].l)
    prev_close = bars[idx - 1].c
    return max(
        bars[idx].h - bars[idx].l,
        abs(bars[idx].h - prev_close),
        abs(bars[idx].l - prev_close),
    )


def _atr_pct(bars: List[Bar], idx: int, length: int = 20) -> Optional[float]:
    if idx <= 0:
        return None
    start = max(1, idx - length + 1)
    vals = [_true_range(bars, j) for j in range(start, idx + 1)]
    if not vals or bars[idx].c <= 0:
        return None
    return (sum(vals) / len(vals)) / bars[idx].c * 100.0


def _effort_bucket(rel_vol: float) -> str:
    if rel_vol < 0.8:
        return "EFFORT_LOW_UNDER_0_8X"
    if rel_vol < 1.0:
        return "EFFORT_QUIET_0_8_1_0X"
    if rel_vol < 1.5:
        return "EFFORT_NORMAL_1_0_1_5X"
    if rel_vol < 2.0:
        return "EFFORT_HIGH_1_5_2_0X"
    if rel_vol < 3.0:
        return "EFFORT_VERY_HIGH_2_0_3_0X"
    return "EFFORT_CLIMAX_3X_PLUS"


def _result_bucket(norm_result: float) -> str:
    # norm_result = close-to-close return divided by ATR%.
    # Positive means progress up; negative means progress down.
    if norm_result >= 0.75:
        return "RESULT_STRONG_UP"
    if norm_result >= 0.25:
        return "RESULT_MODEST_UP"
    if norm_result > -0.25:
        return "RESULT_LOW_PROGRESS"
    if norm_result > -0.75:
        return "RESULT_MODEST_DOWN"
    return "RESULT_STRONG_DOWN"


def _er_interpretation(effort_bucket: str, result_bucket: str, dist_from_high_pct: Optional[float]) -> str:
    high_effort = effort_bucket in {"EFFORT_HIGH_1_5_2_0X", "EFFORT_VERY_HIGH_2_0_3_0X", "EFFORT_CLIMAX_3X_PLUS"}
    low_effort = effort_bucket in {"EFFORT_LOW_UNDER_0_8X", "EFFORT_QUIET_0_8_1_0X"}
    low_result = result_bucket == "RESULT_LOW_PROGRESS"
    up_result = result_bucket in {"RESULT_MODEST_UP", "RESULT_STRONG_UP"}
    down_result = result_bucket in {"RESULT_MODEST_DOWN", "RESULT_STRONG_DOWN"}
    far_off = False
    near_high = False
    try:
        if dist_from_high_pct is not None and math.isfinite(float(dist_from_high_pct)):
            far_off = float(dist_from_high_pct) <= -20.0
            near_high = float(dist_from_high_pct) > -5.0
    except Exception:
        pass

    if high_effort and low_result and far_off:
        return "ABSORPTION_CANDIDATE_HIGH_EFFORT_LOW_RESULT_FAR_OFF_HIGH"
    if high_effort and low_result and near_high:
        return "DISTRIBUTION_RISK_HIGH_EFFORT_LOW_RESULT_NEAR_HIGH"
    if high_effort and low_result:
        return "EFFORT_RESULT_DIVERGENCE_HIGH_EFFORT_LOW_RESULT"
    if high_effort and up_result:
        return "DEMAND_CONFIRMATION_HIGH_EFFORT_UP_RESULT"
    if high_effort and down_result:
        return "SUPPLY_CONFIRMATION_HIGH_EFFORT_DOWN_RESULT"
    if low_effort and up_result:
        return "NO_SUPPLY_UPDRIFT_LOW_EFFORT_UP_RESULT"
    if low_effort and down_result:
        return "NO_DEMAND_DECLINE_LOW_EFFORT_DOWN_RESULT"
    if low_effort and low_result:
        return "LOW_INTEREST_EQUILIBRIUM_LOW_EFFORT_LOW_RESULT"
    if up_result:
        return "NORMAL_EFFORT_UP_RESULT"
    if down_result:
        return "NORMAL_EFFORT_DOWN_RESULT"
    return "NORMAL_EFFORT_LOW_RESULT"


def _distance_bucket_from_value(value: Any) -> str:
    try:
        d = float(value)
    except Exception:
        return "HIGH_DISTANCE_UNKNOWN"
    if not math.isfinite(d):
        return "HIGH_DISTANCE_UNKNOWN"
    if d <= -20.0:
        return "HIGH_DISTANCE_20PCT_PLUS_OFF"
    if d <= -10.0:
        return "HIGH_DISTANCE_10_20PCT_OFF"
    if d <= -5.0:
        return "HIGH_DISTANCE_5_10PCT_OFF"
    return "HIGH_DISTANCE_0_5PCT_OFF"


def summarize_wyckoff_effort_result(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Wyckoff / Weis Phase 1 study: Effort vs Result.

    Purpose:
      Test whether price progress relative to volume adds forward-return
      information on top of the completed volatility study.

    Definitions:
      Effort = relative volume bucket.
      Result = close-to-close price progress normalized by ATR.
      Divergence = high effort with low progress.
      Harmony = high effort with strong directional progress.

    This is intentionally not a pattern detector. It is the behavioral bridge
    between the volatility alpha map and later Wyckoff structures.
    """
    grouped: Dict[str, Dict[str, List[Dict[str, float]]]] = {
        "single_bar_effort_x_result": defaultdict(list),
        "single_bar_interpretation": defaultdict(list),
        "five_bar_effort_x_result": defaultdict(list),
        "five_bar_interpretation": defaultdict(list),
        "vol_exp_single_bar_interpretation": defaultdict(list),
        "vol_exp_five_bar_interpretation": defaultdict(list),
        "vol_exp_20off_single_bar_interpretation": defaultdict(list),
        "vol_exp_20off_five_bar_interpretation": defaultdict(list),
        "vol_exp_late_single_bar_interpretation": defaultdict(list),
        "vol_exp_late_five_bar_interpretation": defaultdict(list),
        "top_vol_state_single_bar_interpretation": defaultdict(list),
        "top_vol_state_five_bar_interpretation": defaultdict(list),
        "effort_result_x_distance": defaultdict(list),
        "effort_result_x_rs2h": defaultdict(list),
    }

    def payload_from_h90(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
        h90 = r.get("h90")
        if not isinstance(h90, dict):
            return None
        try:
            return {
                "direction_correct": float(h90.get("direction_correct", 0.0)),
                "return_pct": float(h90.get("return_pct", 0.0)),
                "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                "mae_pct": float(h90.get("mae_pct", 0.0)),
            }
        except Exception:
            return None

    rs_2h_buckets = [
        (0, 60, "RS2H_50_60"),
        (60, 70, "RS2H_60_70"),
        (70, 80, "RS2H_70_80"),
        (80, 90, "RS2H_80_90"),
        (90, 101, "RS2H_90_100"),
    ]

    for r in rows:
        payload = payload_from_h90(r)
        if not payload:
            continue

        er_effort = str(r.get("er1_effort_bucket", "UNKNOWN"))
        er_result = str(r.get("er1_result_bucket", "UNKNOWN"))
        er_interp = str(r.get("er1_interpretation", "UNKNOWN"))
        er5_effort = str(r.get("er5_effort_bucket", "UNKNOWN"))
        er5_result = str(r.get("er5_result_bucket", "UNKNOWN"))
        er5_interp = str(r.get("er5_interpretation", "UNKNOWN"))
        setup = str(r.get("setup_type", ""))
        phase = str(r.get("expansion_phase_bucket", ""))
        dist = _distance_bucket_from_value(r.get("distance_from_252_high_pct"))
        rs2h = _bucket_numeric(r.get("rs_2h"), rs_2h_buckets)

        grouped["single_bar_effort_x_result"][f"{er_effort}|{er_result}"].append(payload)
        grouped["single_bar_interpretation"][er_interp].append(payload)
        grouped["five_bar_effort_x_result"][f"{er5_effort}|{er5_result}"].append(payload)
        grouped["five_bar_interpretation"][er5_interp].append(payload)
        grouped["effort_result_x_distance"][f"{er_interp}|{dist}"].append(payload)
        grouped["effort_result_x_rs2h"][f"{er_interp}|{rs2h}"].append(payload)

        if setup == "Volatility Expansion Candidate":
            grouped["vol_exp_single_bar_interpretation"][er_interp].append(payload)
            grouped["vol_exp_five_bar_interpretation"][er5_interp].append(payload)
            if dist == "HIGH_DISTANCE_20PCT_PLUS_OFF":
                grouped["vol_exp_20off_single_bar_interpretation"][er_interp].append(payload)
                grouped["vol_exp_20off_five_bar_interpretation"][er5_interp].append(payload)
            if phase == "EXP_PHASE_LATE":
                grouped["vol_exp_late_single_bar_interpretation"][er_interp].append(payload)
                grouped["vol_exp_late_five_bar_interpretation"][er5_interp].append(payload)

            # Top prior volatility profile from completed research: far off high + strong 2H RS.
            if dist == "HIGH_DISTANCE_20PCT_PLUS_OFF" and rs2h == "RS2H_90_100":
                grouped["top_vol_state_single_bar_interpretation"][er_interp].append(payload)
                grouped["top_vol_state_five_bar_interpretation"][er5_interp].append(payload)

    return {
        name: _summarize_group_perf(bucket_map, min_signals=20)
        for name, bucket_map in grouped.items()
    }

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
                high_252 = max(b.h for b in daily[max(0, i - 251): i + 1])
                setup_subtype = classify_expansion_subtype(
                    setup=setup,
                    daily_slope_pct=daily_slope_pct,
                    rel_vol=rel_vol,
                    price=daily[i].c,
                    high_252=high_252,
                )
                distance_from_252_high_pct = ((daily[i].c - high_252) / high_252 * 100) if high_252 > 0 else None
                if daily_slope_pct < 1.0:
                    expansion_phase_bucket = "EXP_PHASE_EARLY"
                elif daily_slope_pct < 3.0:
                    expansion_phase_bucket = "EXP_PHASE_MID"
                else:
                    expansion_phase_bucket = "EXP_PHASE_LATE"

                if rel_vol < 0.8:
                    rel_volume_bucket = "RELVOL_UNDER_0_8X"
                elif rel_vol < 1.0:
                    rel_volume_bucket = "RELVOL_0_8_1_0X"
                elif rel_vol < 1.5:
                    rel_volume_bucket = "RELVOL_1_0_1_5X"
                elif rel_vol < 2.0:
                    rel_volume_bucket = "RELVOL_1_5_2_0X"
                elif rel_vol < 3.0:
                    rel_volume_bucket = "RELVOL_2_0_3_0X"
                else:
                    rel_volume_bucket = "RELVOL_3X_PLUS"

                # Wyckoff / Weis Phase 1: Effort vs Result.
                # Effort = relative volume. Result = price progress normalized by ATR.
                atr20_pct = _atr_pct(daily, i, 20) or 0.0
                prev_close = daily[i - 1].c if i > 0 else daily[i].o
                er1_return_pct = ((daily[i].c - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
                er1_norm_result = (er1_return_pct / atr20_pct) if atr20_pct > 0 else 0.0
                er1_effort_bucket = _effort_bucket(rel_vol)
                er1_result_bucket = _result_bucket(er1_norm_result)
                er1_interpretation = _er_interpretation(
                    er1_effort_bucket,
                    er1_result_bucket,
                    distance_from_252_high_pct,
                )

                if i >= 5:
                    five_start_close = daily[i - 5].c
                    er5_return_pct = ((daily[i].c - five_start_close) / five_start_close * 100.0) if five_start_close > 0 else 0.0
                    recent_vol = sum(b.v for b in daily[i - 4:i + 1])
                    prior_start = max(0, i - 24)
                    prior_vols = [b.v for b in daily[prior_start:i - 4]]
                    avg_prior_vol = (sum(prior_vols) / len(prior_vols)) if prior_vols else max(daily[i].v, 1.0)
                    er5_rel_effort = recent_vol / max(avg_prior_vol * 5.0, 1.0)
                    er5_norm_result = (er5_return_pct / (atr20_pct * math.sqrt(5))) if atr20_pct > 0 else 0.0
                else:
                    er5_return_pct = er1_return_pct
                    er5_rel_effort = rel_vol
                    er5_norm_result = er1_norm_result
                er5_effort_bucket = _effort_bucket(er5_rel_effort)
                er5_result_bucket = _result_bucket(er5_norm_result)
                er5_interpretation = _er_interpretation(
                    er5_effort_bucket,
                    er5_result_bucket,
                    distance_from_252_high_pct,
                )

                # Wyckoff / Weis Phase 2: Persistent Absorption.
                # Count repeated high-effort / low-result bars in rolling windows.
                # This is intentionally context-neutral: no RS, no volatility filter,
                # no distance-from-high filter, no Spring/UTAD assumption.
                abs1_count_20 = _count_absorption_candidates_in_window(daily, i, 20, mode="single")
                abs1_count_40 = _count_absorption_candidates_in_window(daily, i, 40, mode="single")
                abs1_count_60 = _count_absorption_candidates_in_window(daily, i, 60, mode="single")
                abs5_count_20 = _count_absorption_candidates_in_window(daily, i, 20, mode="five")
                abs5_count_40 = _count_absorption_candidates_in_window(daily, i, 40, mode="five")
                abs5_count_60 = _count_absorption_candidates_in_window(daily, i, 60, mode="five")

                # Wyckoff / Weis Phase 3: Cause Score.
                # Composite weighted score across all six absorption count windows.
                # Longer windows and five-bar counts are weighted more heavily because
                # they represent broader and more deliberate cause building.
                cause_score = round(
                    abs1_count_20 * 1.0
                    + abs1_count_40 * 1.25
                    + abs1_count_60 * 1.5
                    + abs5_count_20 * 2.0
                    + abs5_count_40 * 2.5
                    + abs5_count_60 * 3.0,
                    3,
                )

                # Phase 3: Markup fields using Maximum Favorable Excursion (MFE).
                # MFE captures intraperiod highs and therefore better reflects
                # actual Wyckoff markup than highest closing price alone.
                def _markup_mfe(bars: List[Bar], idx: int, horizon: int) -> Optional[float]:
                    if idx + horizon >= len(bars):
                        return None
                    entry = bars[idx].c
                    if entry <= 0:
                        return None
                    forward_slice = bars[idx + 1 : idx + horizon + 1]
                    if not forward_slice:
                        return None
                    max_high = max(b.h for b in forward_slice)
                    return round(((max_high - entry) / entry) * 100, 3)

                markup_20d_pct  = _markup_mfe(daily, i, 20)
                markup_40d_pct  = _markup_mfe(daily, i, 40)
                markup_60d_pct  = _markup_mfe(daily, i, 60)
                markup_90d_pct  = _markup_mfe(daily, i, 90)

                # Markup bucket: classify the best observed markup (90-day MFE).
                def _markup_bucket(mfe: Optional[float]) -> str:
                    if mfe is None:
                        return "MARKUP_INSUFFICIENT_DATA"
                    if mfe >= 20.0:
                        return "MAJOR_MARKUP_20_PLUS"
                    if mfe >= 10.0:
                        return "STRONG_MARKUP_10_20"
                    if mfe >= 5.0:
                        return "MODERATE_MARKUP_5_10"
                    if mfe >= 0.0:
                        return "MINIMAL_MARKUP_0_5"
                    return "NO_MARKUP_NEGATIVE"

                markup_bucket = _markup_bucket(markup_90d_pct)


                # Phase 4: Juncture Detection.
                # Structure → Juncture → Classification.
                # These fields answer: is price at a critical decision point,
                # and if so, does the behavioral evidence favor accumulation
                # or distribution?

                _p4_atr = calc_atr(daily, i, 14) or max(daily[i].h - daily[i].l, daily[i].c * 0.01)

                _p4_range = _detect_trading_range(daily, i, lookback=60)
                trading_range_detected      = _p4_range["detected"]
                p4_range_width_pct          = _p4_range["range_width_pct"]
                p4_support_level            = _p4_range["support_level"]
                p4_resistance_level         = _p4_range["resistance_level"]
                p4_support_touches          = _p4_range["support_touches"]
                p4_resistance_touches       = _p4_range["resistance_touches"]
                p4_bars_in_range            = _p4_range["bars_in_range"]
                p4_price_location_in_range  = _p4_range["price_location_in_range"]

                _p4_apex = _detect_apex(daily, i, lookback=40)
                p4_apex_detected            = _p4_apex["apex_detected"]
                p4_apex_proximity           = _p4_apex["apex_proximity"]
                p4_range_contraction_pct    = _p4_apex["range_contraction_pct"]

                _p4_vol = _volume_asymmetry(daily, i, lookback=20)
                p4_vol_asymmetry_ratio      = _p4_vol["vol_asymmetry_ratio"]
                p4_demand_dominant          = _p4_vol["demand_dominant"]

                if trading_range_detected and p4_support_level > 0:
                    _p4_spring = _detect_spring(daily, i, p4_support_level, _p4_atr)
                else:
                    _p4_spring = {"spring_detected": False, "spring_quality": 0,
                                  "spring_penetration_pct": 0.0, "spring_recovery_bars": 0}
                p4_spring_detected          = _p4_spring["spring_detected"]
                p4_spring_quality           = _p4_spring["spring_quality"]
                p4_spring_penetration_pct   = _p4_spring["spring_penetration_pct"]
                p4_spring_recovery_bars     = _p4_spring["spring_recovery_bars"]

                if trading_range_detected and p4_resistance_level > 0:
                    _p4_upthrust = _detect_upthrust(daily, i, p4_resistance_level, _p4_atr)
                else:
                    _p4_upthrust = {"upthrust_detected": False, "upthrust_quality": 0,
                                    "upthrust_penetration_pct": 0.0, "upthrust_return_bars": 0}
                p4_upthrust_detected        = _p4_upthrust["upthrust_detected"]
                p4_upthrust_quality         = _p4_upthrust["upthrust_quality"]

                if trading_range_detected:
                    _p4_juncture = _absorption_at_juncture(
                        daily, i, p4_support_level, p4_resistance_level, _p4_atr
                    )
                else:
                    _p4_juncture = {"at_support": False, "at_resistance": False,
                                    "at_juncture": False, "juncture_type": "OPEN_SPACE"}
                p4_at_support               = _p4_juncture["at_support"]
                p4_at_resistance            = _p4_juncture["at_resistance"]
                p4_at_juncture              = _p4_juncture["at_juncture"]
                p4_juncture_type            = _p4_juncture["juncture_type"]

                _p4_behavior = _classify_behavior(
                    distance_from_high_pct=distance_from_252_high_pct,
                    spring_detected=p4_spring_detected,
                    upthrust_detected=p4_upthrust_detected,
                    demand_dominant=p4_demand_dominant,
                    price_location_in_range=p4_price_location_in_range,
                    at_support=p4_at_support,
                    at_resistance=p4_at_resistance,
                    apex_detected=p4_apex_detected,
                )
                p4_accumulation_score       = _p4_behavior["accumulation_score"]
                p4_distribution_score       = _p4_behavior["distribution_score"]
                p4_behavior_classification  = _p4_behavior["behavior_classification"]


                # Phase 5: Trajectory Variables.
                # What was happening in the 10 days BEFORE the signal?
                # The current engine measures state on the signal date.
                # Phase 5 measures direction of travel leading into the signal.
                # Inside the best-performing bucket (LATE + 20% OFF HIGH + 2-3X RELVOL)
                # trajectory likely separates the 23% winners from the 4% winners.

                # 1. Price trajectory over prior 10 bars
                #    Positive = price was rising into the signal (momentum)
                #    Negative = price was still declining into the signal
                _p5_lookback = 10
                if i >= _p5_lookback:
                    _p5_price_10d_ago = daily[i - _p5_lookback].c
                    p5_price_traj_10d_pct = round(
                        ((daily[i].c - _p5_price_10d_ago) / _p5_price_10d_ago * 100.0)
                        if _p5_price_10d_ago > 0 else 0.0, 3
                    )
                    if p5_price_traj_10d_pct >= 3.0:
                        p5_price_traj_bucket = "TRAJ_RISING_STRONG_3PCT_PLUS"
                    elif p5_price_traj_10d_pct >= 1.0:
                        p5_price_traj_bucket = "TRAJ_RISING_MILD_1_3PCT"
                    elif p5_price_traj_10d_pct >= -1.0:
                        p5_price_traj_bucket = "TRAJ_FLAT_NEG1_TO_POS1PCT"
                    elif p5_price_traj_10d_pct >= -3.0:
                        p5_price_traj_bucket = "TRAJ_DECLINING_MILD_NEG3_NEG1PCT"
                    else:
                        p5_price_traj_bucket = "TRAJ_DECLINING_STRONG_NEG3PCT_PLUS"
                else:
                    p5_price_traj_10d_pct = 0.0
                    p5_price_traj_bucket = "TRAJ_INSUFFICIENT_DATA"

                # 2. Volume trend over prior 10 bars vs prior 20 bars
                #    Are buyers increasing participation into the signal?
                _p5_vol_recent = sma([b.v for b in daily], i, 5) or 0.0
                _p5_vol_base   = sma([b.v for b in daily], i, 20) or 0.0
                p5_vol_trend_ratio = round(
                    (_p5_vol_recent / _p5_vol_base) if _p5_vol_base > 0 else 1.0, 3
                )
                if p5_vol_trend_ratio >= 1.5:
                    p5_vol_trend_bucket = "VOL_TREND_EXPANDING_STRONG_1_5X_PLUS"
                elif p5_vol_trend_ratio >= 1.1:
                    p5_vol_trend_bucket = "VOL_TREND_EXPANDING_MILD_1_1_1_5X"
                elif p5_vol_trend_ratio >= 0.9:
                    p5_vol_trend_bucket = "VOL_TREND_FLAT_0_9_1_1X"
                elif p5_vol_trend_ratio >= 0.7:
                    p5_vol_trend_bucket = "VOL_TREND_CONTRACTING_MILD_0_7_0_9X"
                else:
                    p5_vol_trend_bucket = "VOL_TREND_CONTRACTING_STRONG_UNDER_0_7X"

                # 3. RS Daily trajectory over prior 10 bars
                #    Is relative strength rising or falling into the signal?
                #    Uses the slope of the daily RS ratio over 10 bars.
                _p5_closes = [b.c for b in daily]
                _p5_rs_now = percentile_score(_p5_closes, i, 63)
                _p5_rs_10d = percentile_score(_p5_closes, i - _p5_lookback, 63) if i >= _p5_lookback else None
                if _p5_rs_now is not None and _p5_rs_10d is not None:
                    p5_rs_traj_10d = round(_p5_rs_now - _p5_rs_10d, 2)
                    if p5_rs_traj_10d >= 10.0:
                        p5_rs_traj_bucket = "RS_TRAJ_RISING_STRONG_10PT_PLUS"
                    elif p5_rs_traj_10d >= 3.0:
                        p5_rs_traj_bucket = "RS_TRAJ_RISING_MILD_3_10PT"
                    elif p5_rs_traj_10d >= -3.0:
                        p5_rs_traj_bucket = "RS_TRAJ_FLAT_NEG3_TO_POS3PT"
                    elif p5_rs_traj_10d >= -10.0:
                        p5_rs_traj_bucket = "RS_TRAJ_DECLINING_MILD_NEG10_NEG3PT"
                    else:
                        p5_rs_traj_bucket = "RS_TRAJ_DECLINING_STRONG_NEG10PT_PLUS"
                else:
                    p5_rs_traj_10d = 0.0
                    p5_rs_traj_bucket = "RS_TRAJ_INSUFFICIENT_DATA"

                # 4. Days since the 252-day high was set
                #    Early in the recovery = recently marked down
                #    Later in recovery = more time for cause to build
                _p5_high_idx = None
                _p5_start = max(0, i - 251)
                _p5_best_high = -1.0
                for _p5_j in range(_p5_start, i + 1):
                    if daily[_p5_j].h > _p5_best_high:
                        _p5_best_high = daily[_p5_j].h
                        _p5_high_idx = _p5_j
                p5_days_since_252_high = (i - _p5_high_idx) if _p5_high_idx is not None else 0
                if p5_days_since_252_high >= 180:
                    p5_days_since_high_bucket = "DAYS_SINCE_HIGH_180_PLUS"
                elif p5_days_since_252_high >= 120:
                    p5_days_since_high_bucket = "DAYS_SINCE_HIGH_120_180"
                elif p5_days_since_252_high >= 60:
                    p5_days_since_high_bucket = "DAYS_SINCE_HIGH_60_120"
                elif p5_days_since_252_high >= 20:
                    p5_days_since_high_bucket = "DAYS_SINCE_HIGH_20_60"
                else:
                    p5_days_since_high_bucket = "DAYS_SINCE_HIGH_UNDER_20"

                # 5. Outcome quartile classification (for the dissection output).
                #    Computed using 90-day MFE.  This lets us split the best
                #    performing bucket into top / bottom performers and ask
                #    what is different between them.
                #    Value is stored raw; quartile assignment happens in the
                #    summarize function after all rows are collected.
                p5_mfe90_raw = markup_90d_pct  # already computed above


                # Weis Wave / Behavioral Efficiency Engine.
                # Computes wave structure variables from swing highs and lows
                # over the prior 60-bar lookback.  These variables answer:
                #   "How is the market moving into the signal?"
                # rather than "What state is the market in today?"
                # The trajectory of wave efficiency separates stocks that
                # are about to move from those that merely look like they should.

                _ww_avg_vol = sma([b.v for b in daily], i, 20) or 1.0
                _ww_atr     = calc_atr(daily, i, 14) or max(
                    daily[i].h - daily[i].l, daily[i].c * 0.01
                )
                _ww_support = p4_support_level if trading_range_detected else 0.0

                _ww = _compute_wave_variables(
                    bars=daily,
                    idx=i,
                    support_level=_ww_support,
                    avg_vol_20=_ww_avg_vol,
                    atr=_ww_atr,
                    lookback=60,
                )

                # Unpack all wave variables for the row dict
                w_up1_return_pct  = _ww["w_up1_return_pct"]
                w_up1_duration    = _ww["w_up1_duration"]
                w_up1_vol_ratio   = _ww["w_up1_vol_ratio"]
                w_up1_price_eff   = _ww["w_up1_price_eff"]
                w_up1_vol_eff     = _ww["w_up1_vol_eff"]

                w_up2_return_pct  = _ww["w_up2_return_pct"]
                w_up2_duration    = _ww["w_up2_duration"]
                w_up2_vol_ratio   = _ww["w_up2_vol_ratio"]
                w_up2_price_eff   = _ww["w_up2_price_eff"]
                w_up2_vol_eff     = _ww["w_up2_vol_eff"]

                w_up3_return_pct  = _ww["w_up3_return_pct"]
                w_up3_duration    = _ww["w_up3_duration"]
                w_up3_vol_ratio   = _ww["w_up3_vol_ratio"]
                w_up3_price_eff   = _ww["w_up3_price_eff"]
                w_up3_vol_eff     = _ww["w_up3_vol_eff"]

                w_dn1_return_pct  = _ww["w_dn1_return_pct"]
                w_dn1_duration    = _ww["w_dn1_duration"]
                w_dn1_vol_ratio   = _ww["w_dn1_vol_ratio"]
                w_dn1_price_eff   = _ww["w_dn1_price_eff"]
                w_dn1_vol_eff     = _ww["w_dn1_vol_eff"]

                w_dn2_return_pct  = _ww["w_dn2_return_pct"]
                w_dn2_duration    = _ww["w_dn2_duration"]
                w_dn2_vol_ratio   = _ww["w_dn2_vol_ratio"]
                w_dn2_price_eff   = _ww["w_dn2_price_eff"]
                w_dn2_vol_eff     = _ww["w_dn2_vol_eff"]

                w_dn3_return_pct  = _ww["w_dn3_return_pct"]
                w_dn3_duration    = _ww["w_dn3_duration"]
                w_dn3_vol_ratio   = _ww["w_dn3_vol_ratio"]
                w_dn3_price_eff   = _ww["w_dn3_price_eff"]
                w_dn3_vol_eff     = _ww["w_dn3_vol_eff"]

                w_thrust_shortening           = _ww["w_thrust_shortening"]
                w_thrust_shortening_ratio     = _ww["w_thrust_shortening_ratio"]
                w_selling_pressure_diminishing = _ww["w_selling_pressure_diminishing"]
                w_demand_efficiency_improving  = _ww["w_demand_efficiency_improving"]
                w_springboard_present         = _ww["w_springboard_present"]
                w_buoyancy_near_support       = _ww["w_buoyancy_near_support"]
                w_failure_to_follow_through   = _ww["w_failure_to_follow_through"]
                w_wave_efficiency_score       = _ww["w_wave_efficiency_score"]
                w_wave_efficiency_bucket      = _ww["w_wave_efficiency_bucket"]

                volatility_dna_score, volatility_dna_tier = classify_volatility_dna_score(
                    setup=setup,
                    setup_subtype=setup_subtype,
                    rs_daily=daily_rs,
                    rs_2h=rs_2h,
                    rel_vol=rel_vol,
                    distance_from_252_high_pct=distance_from_252_high_pct,
                    expansion_phase_bucket=expansion_phase_bucket,
                )
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
                    "setup_subtype": setup_subtype,
                    "grade": grade,
                    "audit_score": audit_score,
                    "rs_2h": round(rs_2h, 2),
                    "rs_daily": round(daily_rs, 2),
                    "daily_rs_slope_pct": round(daily_slope_pct, 3),
                    "rel_volume": round(rel_vol, 3),
                    "rel_volume_bucket": rel_volume_bucket,
                    "er_atr20_pct": round(atr20_pct, 3),
                    "er1_return_pct": round(er1_return_pct, 3),
                    "er1_norm_result": round(er1_norm_result, 3),
                    "er1_effort_bucket": er1_effort_bucket,
                    "er1_result_bucket": er1_result_bucket,
                    "er1_interpretation": er1_interpretation,
                    "er5_return_pct": round(er5_return_pct, 3),
                    "er5_rel_effort": round(er5_rel_effort, 3),
                    "er5_norm_result": round(er5_norm_result, 3),
                    "er5_effort_bucket": er5_effort_bucket,
                    "er5_result_bucket": er5_result_bucket,
                    "er5_interpretation": er5_interpretation,
                    "abs1_count_20": abs1_count_20,
                    "abs1_count_40": abs1_count_40,
                    "abs1_count_60": abs1_count_60,
                    "abs1_tier_20": _absorption_persistence_tier(abs1_count_20),
                    "abs1_tier_40": _absorption_persistence_tier(abs1_count_40),
                    "abs1_tier_60": _absorption_persistence_tier(abs1_count_60),
                    "abs5_count_20": abs5_count_20,
                    "abs5_count_40": abs5_count_40,
                    "abs5_count_60": abs5_count_60,
                    "abs5_tier_20": _absorption_persistence_tier(abs5_count_20),
                    "abs5_tier_40": _absorption_persistence_tier(abs5_count_40),
                    "abs5_tier_60": _absorption_persistence_tier(abs5_count_60),
                    # Phase 3: Cause → Effect fields.
                    "cause_score": cause_score,
                    "markup_20d_pct": markup_20d_pct if markup_20d_pct is not None else "",
                    "markup_40d_pct": markup_40d_pct if markup_40d_pct is not None else "",
                    "markup_60d_pct": markup_60d_pct if markup_60d_pct is not None else "",
                    "markup_90d_pct": markup_90d_pct if markup_90d_pct is not None else "",
                    "markup_bucket": markup_bucket,

                    # Phase 4: Juncture Detection fields.
                    "trading_range_detected":     trading_range_detected,
                    "range_width_pct":            p4_range_width_pct,
                    "support_level":              p4_support_level,
                    "resistance_level":           p4_resistance_level,
                    "support_touches":            p4_support_touches,
                    "resistance_touches":         p4_resistance_touches,
                    "bars_in_range":              p4_bars_in_range,
                    "price_location_in_range":    p4_price_location_in_range,
                    "apex_detected":              p4_apex_detected,
                    "apex_proximity":             p4_apex_proximity,
                    "range_contraction_pct":      p4_range_contraction_pct,
                    "vol_asymmetry_ratio":        p4_vol_asymmetry_ratio,
                    "demand_dominant":            p4_demand_dominant,
                    "spring_detected":            p4_spring_detected,
                    "spring_quality":             p4_spring_quality,
                    "spring_penetration_pct":     p4_spring_penetration_pct,
                    "spring_recovery_bars":       p4_spring_recovery_bars,
                    "upthrust_detected":          p4_upthrust_detected,
                    "upthrust_quality":           p4_upthrust_quality,
                    "at_support":                 p4_at_support,
                    "at_resistance":              p4_at_resistance,
                    "at_juncture":                p4_at_juncture,
                    "juncture_type":              p4_juncture_type,
                    "accumulation_score":         p4_accumulation_score,
                    "distribution_score":         p4_distribution_score,
                    "behavior_classification":    p4_behavior_classification,

                    # Phase 5: Trajectory and Dissection fields.
                    "p5_price_traj_10d_pct":   p5_price_traj_10d_pct,
                    "p5_price_traj_bucket":    p5_price_traj_bucket,
                    "p5_vol_trend_ratio":      p5_vol_trend_ratio,
                    "p5_vol_trend_bucket":     p5_vol_trend_bucket,
                    "p5_rs_traj_10d":          p5_rs_traj_10d,
                    "p5_rs_traj_bucket":       p5_rs_traj_bucket,
                    "p5_days_since_252_high":  p5_days_since_252_high,
                    "p5_days_since_high_bucket": p5_days_since_high_bucket,

                    # Weis Wave / Behavioral Efficiency fields.
                    "w_up1_return_pct": w_up1_return_pct,
                    "w_up1_duration":   w_up1_duration,
                    "w_up1_vol_ratio":  w_up1_vol_ratio,
                    "w_up1_price_eff":  w_up1_price_eff,
                    "w_up1_vol_eff":    w_up1_vol_eff,
                    "w_up2_return_pct": w_up2_return_pct,
                    "w_up2_duration":   w_up2_duration,
                    "w_up2_vol_ratio":  w_up2_vol_ratio,
                    "w_up2_price_eff":  w_up2_price_eff,
                    "w_up2_vol_eff":    w_up2_vol_eff,
                    "w_up3_return_pct": w_up3_return_pct,
                    "w_up3_duration":   w_up3_duration,
                    "w_up3_vol_ratio":  w_up3_vol_ratio,
                    "w_up3_price_eff":  w_up3_price_eff,
                    "w_up3_vol_eff":    w_up3_vol_eff,
                    "w_dn1_return_pct": w_dn1_return_pct,
                    "w_dn1_duration":   w_dn1_duration,
                    "w_dn1_vol_ratio":  w_dn1_vol_ratio,
                    "w_dn1_price_eff":  w_dn1_price_eff,
                    "w_dn1_vol_eff":    w_dn1_vol_eff,
                    "w_dn2_return_pct": w_dn2_return_pct,
                    "w_dn2_duration":   w_dn2_duration,
                    "w_dn2_vol_ratio":  w_dn2_vol_ratio,
                    "w_dn2_price_eff":  w_dn2_price_eff,
                    "w_dn2_vol_eff":    w_dn2_vol_eff,
                    "w_dn3_return_pct": w_dn3_return_pct,
                    "w_dn3_duration":   w_dn3_duration,
                    "w_dn3_vol_ratio":  w_dn3_vol_ratio,
                    "w_dn3_price_eff":  w_dn3_price_eff,
                    "w_dn3_vol_eff":    w_dn3_vol_eff,
                    "w_thrust_shortening":            w_thrust_shortening,
                    "w_thrust_shortening_ratio":      w_thrust_shortening_ratio,
                    "w_selling_pressure_diminishing": w_selling_pressure_diminishing,
                    "w_demand_efficiency_improving":  w_demand_efficiency_improving,
                    "w_springboard_present":          w_springboard_present,
                    "w_buoyancy_near_support":        w_buoyancy_near_support,
                    "w_failure_to_follow_through":    w_failure_to_follow_through,
                    "w_wave_efficiency_score":        w_wave_efficiency_score,
                    "w_wave_efficiency_bucket":       w_wave_efficiency_bucket,
                    "high_252": round(high_252, 4),
                    "distance_from_252_high_pct": round(distance_from_252_high_pct, 3) if distance_from_252_high_pct is not None else "",
                    "expansion_phase_bucket": expansion_phase_bucket,
                    "volatility_dna_score": volatility_dna_score,
                    "volatility_dna_tier": volatility_dna_tier,
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
    factor_csv = output_dir / "qualified_long_signal_factor_attribution.csv"
    setup_breakdown_csv = output_dir / "qualified_long_signal_setup_breakdown.csv"
    expansion_subtype_csv = output_dir / "qualified_long_signal_expansion_subtype_alpha.csv"
    volatility_dna_json = output_dir / "qualified_long_signal_volatility_dna.json"
    volatility_rs_json = output_dir / "qualified_long_signal_volatility_rs_matrix.json"
    volatility_rs_distance_json = output_dir / "qualified_long_signal_volatility_rs_distance_matrix.json"
    volatility_rs_distance_relvol_json = output_dir / "qualified_long_signal_volatility_rs_distance_relvol_matrix.json"
    wyckoff_er_json = output_dir / "qualified_long_signal_wyckoff_effort_result_phase1.json"
    wyckoff_absorption_json = output_dir / "qualified_long_signal_wyckoff_persistent_absorption_phase2.json"
    wyckoff_phase3_json = output_dir / "qualified_long_signal_wyckoff_cause_effect_phase3.json"
    wyckoff_phase4_json = output_dir / "qualified_long_signal_wyckoff_juncture_phase4.json"
    wyckoff_phase5_json = output_dir / "qualified_long_signal_wyckoff_dissection_phase5.json"
    wyckoff_phase6_json = output_dir / "qualified_long_signal_wyckoff_wave_efficiency_phase6.json"

    summary = summarize(signal_rows, horizons)
    factor_summary = summarize_factor_attribution(signal_rows)
    setup_breakdown = summarize_setup_breakdown(signal_rows)
    expansion_subtype_summary = summarize_expansion_subtypes(signal_rows)
    volatility_dna_summary = summarize_volatility_dna(signal_rows)
    volatility_interactions = summarize_volatility_interactions(signal_rows)
    volatility_rs_matrix = summarize_volatility_rs_matrix(signal_rows)
    volatility_rs_distance_matrix = summarize_volatility_rs_distance_matrix(signal_rows)
    volatility_rs_distance_relvol_matrix = summarize_volatility_rs_distance_relvol_matrix(signal_rows)
    wyckoff_er_summary = summarize_wyckoff_effort_result(signal_rows)
    wyckoff_absorption_summary = summarize_wyckoff_persistent_absorption(signal_rows)
    wyckoff_phase3_summary = summarize_wyckoff_phase3_cause_effect(signal_rows)
    wyckoff_phase4_summary = summarize_wyckoff_phase4_junctures(signal_rows)
    wyckoff_phase5_summary = summarize_wyckoff_phase5_dissection(signal_rows)
    wyckoff_phase6_summary = summarize_wyckoff_phase6_wave_efficiency(signal_rows)

    # Flatten rows for CSV.
    flat_fields = [
        "symbol", "signal_date", "entry_close", "setup_type", "setup_subtype", "grade", "audit_score",
        "rs_2h", "rs_daily", "daily_rs_slope_pct", "rel_volume", "rel_volume_bucket",
        "er_atr20_pct", "er1_return_pct", "er1_norm_result", "er1_effort_bucket", "er1_result_bucket", "er1_interpretation",
        "er5_return_pct", "er5_rel_effort", "er5_norm_result", "er5_effort_bucket", "er5_result_bucket", "er5_interpretation",
        "abs1_count_20", "abs1_count_40", "abs1_count_60", "abs1_tier_20", "abs1_tier_40", "abs1_tier_60",
        "abs5_count_20", "abs5_count_40", "abs5_count_60", "abs5_tier_20", "abs5_tier_40", "abs5_tier_60",
        "cause_score",
        "markup_20d_pct", "markup_40d_pct", "markup_60d_pct", "markup_90d_pct", "markup_bucket",
        "trading_range_detected", "range_width_pct", "support_level", "resistance_level",
        "support_touches", "resistance_touches", "bars_in_range", "price_location_in_range",
        "apex_detected", "apex_proximity", "range_contraction_pct",
        "vol_asymmetry_ratio", "demand_dominant",
        "spring_detected", "spring_quality", "spring_penetration_pct", "spring_recovery_bars",
        "upthrust_detected", "upthrust_quality",
        "at_support", "at_resistance", "at_juncture", "juncture_type",
        "accumulation_score", "distribution_score", "behavior_classification",
        "p5_price_traj_10d_pct", "p5_price_traj_bucket",
        "p5_vol_trend_ratio", "p5_vol_trend_bucket",
        "p5_rs_traj_10d", "p5_rs_traj_bucket",
        "p5_days_since_252_high", "p5_days_since_high_bucket",
        "w_up1_return_pct", "w_up1_duration", "w_up1_vol_ratio", "w_up1_price_eff", "w_up1_vol_eff",
        "w_up2_return_pct", "w_up2_duration", "w_up2_vol_ratio", "w_up2_price_eff", "w_up2_vol_eff",
        "w_up3_return_pct", "w_up3_duration", "w_up3_vol_ratio", "w_up3_price_eff", "w_up3_vol_eff",
        "w_dn1_return_pct", "w_dn1_duration", "w_dn1_vol_ratio", "w_dn1_price_eff", "w_dn1_vol_eff",
        "w_dn2_return_pct", "w_dn2_duration", "w_dn2_vol_ratio", "w_dn2_price_eff", "w_dn2_vol_eff",
        "w_dn3_return_pct", "w_dn3_duration", "w_dn3_vol_ratio", "w_dn3_price_eff", "w_dn3_vol_eff",
        "w_thrust_shortening", "w_thrust_shortening_ratio",
        "w_selling_pressure_diminishing", "w_demand_efficiency_improving",
        "w_springboard_present", "w_buoyancy_near_support", "w_failure_to_follow_through",
        "w_wave_efficiency_score", "w_wave_efficiency_bucket",
        "high_252", "distance_from_252_high_pct", "expansion_phase_bucket",
        "volatility_dna_score", "volatility_dna_tier", "ma20", "ma50",
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

    with factor_csv.open("w", newline="") as f:
        fields = [
            "bucket", "signals", "avg_audit_score", "avg_rs_2h", "avg_rs_daily",
            "avg_daily_rs_slope_pct", "avg_rel_volume",
            "pct_price_above_ma20", "pct_price_above_ma50", "pct_ma20_above_ma50",
            "avg_ma20_minus_ma50_pct_of_price", "top_setup_type", "top_setup_count",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(factor_summary)

    with setup_breakdown_csv.open("w", newline="") as f:
        fields = ["bucket", "setup_type", "signals", "bucket_pct"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(setup_breakdown)

    with expansion_subtype_csv.open("w", newline="") as f:
        fields = [
            "setup_subtype", "signals", "direction_accuracy_90d_pct",
            "avg_return_90d_pct", "avg_mfe_90d_pct", "avg_mae_90d_pct",
            "edge_ratio_90d",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(expansion_subtype_summary)

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
        "factor_attribution": factor_summary,
        "setup_breakdown": setup_breakdown,
        "expansion_subtype_summary": expansion_subtype_summary,
        "volatility_dna_summary": volatility_dna_summary,
        "volatility_interactions": volatility_interactions,
        "volatility_rs_matrix": volatility_rs_matrix,
        "volatility_rs_distance_matrix": volatility_rs_distance_matrix,
        "volatility_rs_distance_relvol_matrix": volatility_rs_distance_relvol_matrix,
        "wyckoff_effort_result_phase1": wyckoff_er_summary,
        "wyckoff_persistent_absorption_phase2": wyckoff_absorption_summary,
        "wyckoff_cause_effect_phase3": wyckoff_phase3_summary,
        "wyckoff_juncture_phase4": wyckoff_phase4_summary,
        "wyckoff_dissection_phase5": wyckoff_phase5_summary,
        "wyckoff_wave_efficiency_phase6": wyckoff_phase6_summary,
        "output_files": {
            "rows_csv": str(rows_csv),
            "summary_csv": str(summary_csv),
            "factor_csv": str(factor_csv),
            "setup_breakdown_csv": str(setup_breakdown_csv),
            "expansion_subtype_csv": str(expansion_subtype_csv),
            "volatility_dna_json": str(volatility_dna_json),
            "volatility_rs_json": str(volatility_rs_json),
            "volatility_rs_distance_json": str(volatility_rs_distance_json),
            "volatility_rs_distance_relvol_json": str(volatility_rs_distance_relvol_json),
            "wyckoff_effort_result_json": str(wyckoff_er_json),
            "wyckoff_persistent_absorption_json": str(wyckoff_absorption_json),
            "wyckoff_cause_effect_phase3_json": str(wyckoff_phase3_json),
            "wyckoff_juncture_phase4_json": str(wyckoff_phase4_json),
            "wyckoff_dissection_phase5_json": str(wyckoff_phase5_json),
            "wyckoff_wave_efficiency_phase6_json": str(wyckoff_phase6_json),
        },
    }
    summary_json.write_text(json.dumps(payload, indent=2))
    volatility_dna_json.write_text(json.dumps(volatility_dna_summary, indent=2))
    volatility_rs_json.write_text(json.dumps(volatility_rs_matrix, indent=2))
    volatility_rs_distance_json.write_text(json.dumps(volatility_rs_distance_matrix, indent=2))
    volatility_rs_distance_relvol_json.write_text(json.dumps(volatility_rs_distance_relvol_matrix, indent=2))
    wyckoff_er_json.write_text(json.dumps(wyckoff_er_summary, indent=2))
    wyckoff_absorption_json.write_text(json.dumps(wyckoff_absorption_summary, indent=2))
    wyckoff_phase3_json.write_text(json.dumps(wyckoff_phase3_summary, indent=2))
    wyckoff_phase4_json.write_text(json.dumps(wyckoff_phase4_summary, indent=2))
    wyckoff_phase5_json.write_text(json.dumps(wyckoff_phase5_summary, indent=2))
    wyckoff_phase6_json.write_text(json.dumps(wyckoff_phase6_summary, indent=2))

    print("\nAudit complete")
    print(f"Signals: {len(signal_rows):,}")
    print(f"Rows:    {rows_csv}")
    print(f"Summary: {summary_json}")
    print(f"CSV:     {summary_csv}")
    print(f"Factors: {factor_csv}")
    print(f"Setups:  {setup_breakdown_csv}")
    print(f"Subtypes:{expansion_subtype_csv}")
    print(f"VolDNA:  {volatility_dna_json}")
    print(f"VolRS:   {volatility_rs_json}")
    print(f"VolRSD:  {volatility_rs_distance_json}")
    print(f"VolRSDV: {volatility_rs_distance_relvol_json}")
    print(f"WyckoffER: {wyckoff_er_json}")
    print(f"WyckoffAbsorption: {wyckoff_absorption_json}")
    print(f"WyckoffPhase3: {wyckoff_phase3_json}")
    print(f"WyckoffPhase4: {wyckoff_phase4_json}")
    print(f"WyckoffPhase5: {wyckoff_phase5_json}")
    print(f"WyckoffPhase6: {wyckoff_phase6_json}")

    factor_preview_buckets = {"A_PLUS_ONLY", "A_ONLY", "A_MINUS_ONLY", "B_PLUS_ONLY", "B_ONLY", "ALL_QUALIFIED_LONGS"}
    print("\nFactor attribution:")
    for s in factor_summary:
        if s["bucket"] in factor_preview_buckets:
            print(
                f"{s['bucket']:22s} n={s['signals']:>5} "
                f"score={s['avg_audit_score']} rs2h={s['avg_rs_2h']} "
                f"rsD={s['avg_rs_daily']} slope={s['avg_daily_rs_slope_pct']} "
                f"relVol={s['avg_rel_volume']} topSetup={s['top_setup_type']}({s['top_setup_count']})"
            )

    # ---------------------------------------------------------
    # SETUP ALPHA ANALYSIS
    # ---------------------------------------------------------
    # This section does NOT change the audit math. It simply ranks
    # the long setup types by their 90-day forward return so we can
    # identify where the actual alpha is coming from.
    setup_alpha: Dict[str, List[float]] = defaultdict(list)
    setup_accuracy: Dict[str, List[float]] = defaultdict(list)
    setup_edge_vals: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    for r in signal_rows:
        setup = str(r.get("setup_type", "UNKNOWN"))
        h90 = r.get("h90")
        if isinstance(h90, dict):
            try:
                setup_alpha[setup].append(float(h90.get("return_pct", 0.0)))
                setup_accuracy[setup].append(float(h90.get("direction_correct", 0.0)))
                setup_edge_vals[setup].append({
                    "mfe_pct": float(h90.get("mfe_pct", 0.0)),
                    "mae_pct": float(h90.get("mae_pct", 0.0)),
                })
            except Exception:
                continue

    print("\nSetup Alpha Summary:")
    print("-" * 96)

    setup_rank: List[Tuple[str, int, float, float, Optional[float]]] = []
    for setup, returns in setup_alpha.items():
        if len(returns) < 25:
            continue

        count = len(returns)
        avg_return = sum(returns) / count
        acc = (sum(setup_accuracy.get(setup, [])) / count) * 100 if count else 0.0

        edge_items = setup_edge_vals.get(setup, [])
        avg_mfe = sum(x["mfe_pct"] for x in edge_items) / len(edge_items) if edge_items else 0.0
        avg_mae = sum(x["mae_pct"] for x in edge_items) / len(edge_items) if edge_items else 0.0
        edge_ratio = (avg_mfe / abs(avg_mae)) if avg_mae < 0 else None

        setup_rank.append((setup, count, avg_return, acc, edge_ratio))

    setup_rank.sort(key=lambda x: x[2], reverse=True)

    for setup, count, avg_return, acc, edge_ratio in setup_rank:
        print(
            f"{setup:<38} "
            f"n={count:>6} "
            f"acc90={acc:>6.2f}% "
            f"avg90={avg_return:>8.3f}% "
            f"edge90={round(edge_ratio, 3) if edge_ratio is not None else None}"
        )

    print("\nVolatility Expansion Subtype Alpha:")
    print("-" * 96)
    for s in expansion_subtype_summary[:30]:
        if s["signals"] < 25:
            continue
        print(
            f"{s['setup_subtype']:<45} "
            f"n={s['signals']:>6} "
            f"acc90={s['direction_accuracy_90d_pct']:>6.2f}% "
            f"avg90={s['avg_return_90d_pct']:>8.3f}% "
            f"edge90={s['edge_ratio_90d']}"
        )


    print("\nVolatility DNA: RS Daily Buckets")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_rs_daily_buckets", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: 2H RS Buckets")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_rs_2h_buckets", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Relative Volume Buckets")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_rel_volume_buckets", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Distance From 252-Day High Buckets")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_distance_from_high_buckets", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Expansion Phase Buckets")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_phase_buckets", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Top Volatility Expansion Symbols")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_top_symbols", [])[:30]:
        print(f"{s['bucket']:<10} n={s['signals']:>5} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Top VOL_EXP_LATE_HIGHVOL_OFFHIGH Symbols")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_late_highvol_offhigh_top_symbols", [])[:30]:
        print(f"{s['bucket']:<10} n={s['signals']:>5} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: DNA Score Tiers")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_dna_score_tiers", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility DNA: Exact DNA Scores")
    print("-" * 96)
    for s in volatility_dna_summary.get("vol_exp_dna_score_exact", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility Interaction Matrix")
    print("-" * 96)
    for s in volatility_interactions[:40]:
        print(f"{s['bucket']:<78} n={s['signals']:>5} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")



    print("\nVolatility + RS: DNA Tier x Daily RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("dna_tier_x_daily_rs", [])[:40]:
        print(f"{s['bucket']:<55} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS: DNA Tier x 2H RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("dna_tier_x_2h_rs", [])[:40]:
        print(f"{s['bucket']:<55} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS: Late 2-3x Volume + 20% Off High x Daily RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("late_2to3x_20off_x_daily_rs", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS: Late 2-3x Volume + 20% Off High x 2H RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("late_2to3x_20off_x_2h_rs", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS: VOL_EXP_LATE_HIGHVOL_OFFHIGH x Daily RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("late_highvol_offhigh_x_daily_rs", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS: VOL_EXP_LATE_HIGHVOL_OFFHIGH x 2H RS")
    print("-" * 96)
    for s in volatility_rs_matrix.get("late_highvol_offhigh_x_2h_rs", [])[:30]:
        print(f"{s['bucket']:<35} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")



    print("\nVolatility + RS + Distance: Distance x Daily RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("distance_x_daily_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: Distance x 2H RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("distance_x_2h_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: DNA Tier x Distance x Daily RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("dna_tier_x_distance_x_daily_rs", [])[:50]:
        print(f"{s['bucket']:<75} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: DNA Tier x Distance x 2H RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("dna_tier_x_distance_x_2h_rs", [])[:50]:
        print(f"{s['bucket']:<75} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: Late Phase x Distance x Daily RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("late_phase_x_distance_x_daily_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: Late Phase x Distance x 2H RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("late_phase_x_distance_x_2h_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: RelVol 2-3x x Distance x Daily RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("relvol_2to3x_x_distance_x_daily_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance: RelVol 2-3x x Distance x 2H RS")
    print("-" * 96)
    for s in volatility_rs_distance_matrix.get("relvol_2to3x_x_distance_x_2h_rs", [])[:50]:
        print(f"{s['bucket']:<65} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")


    print("\nVolatility + RS + Distance + RelVol: RelVol x Distance x Daily RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("relvol_x_distance_x_daily_rs", [])[:60]:
        print(f"{s['bucket']:<85} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: RelVol x Distance x 2H RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("relvol_x_distance_x_2h_rs", [])[:60]:
        print(f"{s['bucket']:<85} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: Phase x RelVol x Distance")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("phase_x_relvol_x_distance", [])[:60]:
        print(f"{s['bucket']:<85} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: Phase x RelVol x Distance x Daily RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("phase_x_relvol_x_distance_x_daily_rs", [])[:60]:
        print(f"{s['bucket']:<95} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: Phase x RelVol x Distance x 2H RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("phase_x_relvol_x_distance_x_2h_rs", [])[:60]:
        print(f"{s['bucket']:<95} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: DNA Tier x RelVol x Distance x Daily RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("dna_tier_x_relvol_x_distance_x_daily_rs", [])[:60]:
        print(f"{s['bucket']:<95} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: DNA Tier x RelVol x Distance x 2H RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("dna_tier_x_relvol_x_distance_x_2h_rs", [])[:60]:
        print(f"{s['bucket']:<95} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: Late Phase RelVol x Distance")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("late_phase_relvol_x_distance", [])[:60]:
        print(f"{s['bucket']:<85} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nVolatility + RS + Distance + RelVol: 20%+ Off High RelVol x 2H RS")
    print("-" * 112)
    for s in volatility_rs_distance_relvol_matrix.get("twenty_off_relvol_x_rs2h", [])[:60]:
        print(f"{s['bucket']:<85} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")


    print("\nWyckoff / Weis Phase 1: Single-Bar Effort x Result")
    print("-" * 112)
    for s in wyckoff_er_summary.get("single_bar_effort_x_result", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1: Single-Bar Interpretation")
    print("-" * 112)
    for s in wyckoff_er_summary.get("single_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1: Five-Bar Effort x Result")
    print("-" * 112)
    for s in wyckoff_er_summary.get("five_bar_effort_x_result", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1: Five-Bar Interpretation")
    print("-" * 112)
    for s in wyckoff_er_summary.get("five_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Volatility Expansion: Single-Bar Interpretation")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_single_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Volatility Expansion: Five-Bar Interpretation")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_five_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Volatility Expansion + 20% Off High: Single-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_20off_single_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Volatility Expansion + 20% Off High: Five-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_20off_five_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Late Volatility Expansion: Single-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_late_single_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Late Volatility Expansion: Five-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("vol_exp_late_five_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Prior Top Vol State: Single-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("top_vol_state_single_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 1 + Prior Top Vol State: Five-Bar")
    print("-" * 112)
    for s in wyckoff_er_summary.get("top_vol_state_five_bar_interpretation", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")


    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Single-Bar Count 20")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("single_bar_absorption_count_20", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Single-Bar Count 40")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("single_bar_absorption_count_40", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Single-Bar Count 60")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("single_bar_absorption_count_60", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Five-Bar Count 20")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("five_bar_absorption_count_20", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Five-Bar Count 40")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("five_bar_absorption_count_40", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Five-Bar Count 60")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("five_bar_absorption_count_60", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Cluster Shape")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("single_bar_absorption_cluster_shape", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 2: Persistent Absorption - Single/Five-Bar Overlap")
    print("-" * 112)
    for s in wyckoff_absorption_summary.get("single_vs_five_bar_absorption_overlap", [])[:60]:
        print(f"{s['bucket']:<82} n={s['signals']:>6} acc90={s['direction_accuracy_90d_pct']:>6.2f}% avg90={s['avg_return_90d_pct']:>8.3f}% edge90={s['edge_ratio_90d']}")

    print("\nWyckoff / Weis Phase 3 (Study A): Cause Score Tier vs Markup MFE")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_a_cause_score_tier_vs_markup", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")

    print("\nWyckoff / Weis Phase 3 (Study A): Single-Bar Persistence Count 60 vs Markup MFE")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_a_abs1_count_60_vs_markup", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")

    print("\nWyckoff / Weis Phase 3 (Study A): Five-Bar Persistence Count 60 vs Markup MFE")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_a_abs5_count_60_vs_markup", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")

    print("\nWyckoff / Weis Phase 3 (Study B): Single-Bar vs Five-Bar vs Both vs Neither")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_b_abs1_vs_abs5", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")

    print("\nWyckoff / Weis Phase 3 (Study C): Dual Confirmation (abs1 AND abs5 in 20-bar window)")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_c_dual_confirmation", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")

    print("\nWyckoff / Weis Phase 3 (Study D): Time Compression - Clustered vs Distributed Absorption")
    print("-" * 112)
    for s in wyckoff_phase3_summary.get("study_d_time_compression", []):
        print(f"{s['bucket']:<40} n={s['signals']:>6} mfe20={s['avg_markup_20d_mfe_pct']:>7.3f}% mfe40={s['avg_markup_40d_mfe_pct']:>7.3f}% mfe60={s['avg_markup_60d_mfe_pct']:>7.3f}% mfe90={s['avg_markup_90d_mfe_pct']:>7.3f}%")


    print("\nWyckoff / Weis Phase 4 (Study F): Base Rate - All Signals vs In Trading Range")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_f_base_rate", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study A): Spring Detection vs No Spring")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_a_spring_detection", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study A): Spring Quality Score vs Forward Rally")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_a_spring_quality_vs_rally", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study B): Upthrust Detection in Long Signals")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_b_upthrust_detection", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study C): Absorption at Juncture vs Open Space")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_c_absorption_location", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study C): Juncture Type Detail")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_c_juncture_type_detail", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study D): Behavioral Classification")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_d_behavior_classification", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study D): Accumulation Score Tier")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_d_accumulation_score_tier", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study E): Apex x Juncture Confluence")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_e_apex_x_juncture", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 (Study E): Apex x Behavior")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("study_e_apex_x_behavior", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 Combined: Spring x Behavior Classification")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("combined_spring_x_behavior", []):
        print(f"{s['bucket']:<45} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")

    print("\nWyckoff / Weis Phase 4 Combined: Apex x Juncture x Behavior")
    print("-" * 112)
    for s in wyckoff_phase4_summary.get("combined_juncture_x_behavior_x_apex", []):
        print(f"{s['bucket']:<55} n={s['signals']:>6} acc20={s['acc_20d_pct']:>6.2f}% mfe20={s['avg_mfe_20d_pct']:>7.3f}% mfe90={s['avg_mfe_90d_pct']:>7.3f}% asym={str(s['avg_asymmetry_20d']):>6}")




    # ── Phase 6: Weis Wave / Behavioral Efficiency ────────────────────────────
    p6 = wyckoff_phase6_summary
    p6_n  = p6.get("target_bucket_n", 0)
    p6_un = p6.get("universe_n", 0)

    print(f"\n{'='*112}")
    print(f"Wyckoff / Weis Phase 6: Behavioral Efficiency Engine (Weis Wave)")
    print(f"  Target: Late Expansion + 20%+ Off High + RelVol 2-3x")
    print(f"  Target n={p6_n}   Universe n={p6_un}")
    print(f"  Validation threshold: avg_asym_20d > 2.0 for favorable conditions")
    print(f"{'='*112}")

    def _p6_print(title: str, universe_rows: list, target_rows: list) -> None:
        fmt = "{:<52} {:>6}  mfe20={:>7.3f}%  mfe90={:>7.3f}%  acc90={:>6.2f}%  asym={}"
        print(f"\n{title}")
        print(f"  --- Universe ---")
        print("-" * 112)
        for s in universe_rows[:10]:
            print(fmt.format(
                s["bucket"], s["signals"],
                s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                s["acc_90d_pct"], str(s["avg_asym_20d"])
            ))
        print(f"  --- Target Bucket (Late + 20%Off + 2-3x RelVol) ---")
        print("-" * 112)
        for s in target_rows:
            print(fmt.format(
                s["bucket"], s["signals"],
                s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                s["acc_90d_pct"], str(s["avg_asym_20d"])
            ))

    _p6_print(
        "Phase 6 | Study A: Wave Efficiency Bucket",
        p6.get("universe_wave_efficiency_bucket", []),
        p6.get("target_wave_efficiency_bucket",   []),
    )
    _p6_print(
        "Phase 6 | Study J: Wave Efficiency Score Tier (Monotonic Test)",
        p6.get("universe_wave_efficiency_score_tier", []),
        p6.get("target_wave_efficiency_score_tier",   []),
    )
    _p6_print(
        "Phase 6 | Study B: Selling Pressure Diminishing",
        p6.get("universe_selling_pressure_dim", []),
        p6.get("target_selling_pressure_dim",   []),
    )
    _p6_print(
        "Phase 6 | Study C: Demand Efficiency Improving",
        p6.get("universe_demand_eff_improving", []),
        p6.get("target_demand_eff_improving",   []),
    )
    _p6_print(
        "Phase 6 | Study D: Springboard Present",
        p6.get("universe_springboard", []),
        p6.get("target_springboard",   []),
    )
    _p6_print(
        "Phase 6 | Study E: Buoyancy Near Support",
        p6.get("universe_buoyancy", []),
        p6.get("target_buoyancy",   []),
    )
    _p6_print(
        "Phase 6 | Study F: Failure to Follow Through",
        p6.get("universe_failure_follow_through", []),
        p6.get("target_failure_follow_through",   []),
    )
    _p6_print(
        "Phase 6 | Study G: Dual Demand Confirmation (Diminishing Sell + Improving Demand)",
        p6.get("universe_dual_demand_confirm", []),
        p6.get("target_dual_demand_confirm",   []),
    )
    _p6_print(
        "Phase 6 | Study H: Imminent Resolution (Springboard OR Buoyancy)",
        p6.get("universe_imminent_resolution", []),
        p6.get("target_imminent_resolution",   []),
    )
    _p6_print(
        "Phase 6 | Study I: Full Confluence (Diminishing Sell + Imminent Resolution)",
        p6.get("universe_full_confluence", []),
        p6.get("target_full_confluence",   []),
    )
    _p6_print(
        "Phase 6 | Interaction: Buoyancy x Springboard",
        p6.get("universe_buoyancy_x_springboard", []),
        p6.get("target_buoyancy_x_springboard",   []),
    )
    _p6_print(
        "Phase 6 | Interaction: Diminishing Selling x Improving Demand",
        p6.get("universe_dim_sell_x_impr_demand", []),
        p6.get("target_dim_sell_x_impr_demand",   []),
    )
    _p6_print(
        "Phase 6 | Interaction: Wave Score x Behavioral Classification",
        p6.get("universe_wave_score_x_behavior", []),
        p6.get("target_wave_score_x_behavior",   []),
    )
    _p6_print(
        "Phase 6 | Up-Wave 1 Price Efficiency Tier",
        p6.get("universe_up1_price_eff_tier", []),
        p6.get("target_up1_price_eff_tier",   []),
    )
    _p6_print(
        "Phase 6 | Down-Wave 1 Volume Efficiency Tier",
        p6.get("universe_dn1_vol_eff_tier", []),
        p6.get("target_dn1_vol_eff_tier",   []),
    )


    # ── Phase 5: Dissection of the Strongest Bucket ──────────────────────────
    p5 = wyckoff_phase5_summary
    p5_n  = p5.get("target_bucket_n", 0)
    p5_un = p5.get("universe_n", 0)
    p5_qt = p5.get("quartile_thresholds", {})

    print(f"\n{'='*112}")
    print(f"Wyckoff / Weis Phase 5: Dissection of Strongest Bucket")
    print(f"  Target: Late Expansion + 20%+ Off High + RelVol 2-3x")
    print(f"  Target n={p5_n}   Universe n={p5_un}")
    print(f"  Top quartile mfe90 >= {p5_qt.get('top_25pct_mfe90_threshold')}%")
    print(f"  Bottom quartile mfe90 <= {p5_qt.get('bottom_25pct_mfe90_threshold')}%")
    print(f"{'='*112}")

    def _p5_print(title: str, universe_rows: list, target_rows: list,
                  top_rows: list = None, bot_rows: list = None) -> None:
        """Print a Phase 5 comparison table."""
        fmt = "{:<48} {:>6}  mfe20={:>7.3f}%  mfe90={:>7.3f}%  acc90={:>6.2f}%  asym={}"
        print(f"\n{title}")
        print(f"  {'--- Universe ---'}")
        print("-" * 112)
        for s in universe_rows[:12]:
            print(fmt.format(
                s["bucket"], s["signals"],
                s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                s["acc_90d_pct"], str(s["avg_asym_20d"])
            ))
        print(f"  {'--- Target Bucket ---'}")
        print("-" * 112)
        for s in target_rows:
            print(fmt.format(
                s["bucket"], s["signals"],
                s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                s["acc_90d_pct"], str(s["avg_asym_20d"])
            ))
        if top_rows is not None and bot_rows is not None:
            print(f"  {'--- Top Quartile (within target) ---'}")
            print("-" * 112)
            for s in top_rows:
                print(fmt.format(
                    s["bucket"], s["signals"],
                    s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                    s["acc_90d_pct"], str(s["avg_asym_20d"])
                ))
            print(f"  {'--- Bottom Quartile (within target) ---'}")
            print("-" * 112)
            for s in bot_rows:
                print(fmt.format(
                    s["bucket"], s["signals"],
                    s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                    s["acc_90d_pct"], str(s["avg_asym_20d"])
                ))

    _p5_print(
        "Phase 5 | Variable 1: Price Trajectory (10-day) into Signal",
        p5.get("universe_price_trajectory", []),
        p5.get("target_price_trajectory",   []),
        p5.get("top_quartile_price_trajectory",    []),
        p5.get("bottom_quartile_price_trajectory", []),
    )
    _p5_print(
        "Phase 5 | Variable 2: Volume Trend (5-day vs 20-day avg)",
        p5.get("universe_volume_trend", []),
        p5.get("target_volume_trend",   []),
        p5.get("top_quartile_volume_trend",    []),
        p5.get("bottom_quartile_volume_trend", []),
    )
    _p5_print(
        "Phase 5 | Variable 3: RS Daily Trajectory (10-day change)",
        p5.get("universe_rs_trajectory", []),
        p5.get("target_rs_trajectory",   []),
        p5.get("top_quartile_rs_trajectory",    []),
        p5.get("bottom_quartile_rs_trajectory", []),
    )
    _p5_print(
        "Phase 5 | Variable 4: Days Since 252-Day High Was Set",
        p5.get("universe_days_since_high", []),
        p5.get("target_days_since_high",   []),
        p5.get("top_quartile_days_since_high",    []),
        p5.get("bottom_quartile_days_since_high", []),
    )
    _p5_print(
        "Phase 5 | Variable 5: Volatility DNA Tier",
        p5.get("universe_dna_tier", []),
        p5.get("target_dna_tier",   []),
        p5.get("top_quartile_dna_tier",    []),
        p5.get("bottom_quartile_dna_tier", []),
    )
    _p5_print(
        "Phase 5 | Variable 6: Five-Bar Absorption Presence (60-day window)",
        p5.get("universe_abs5_presence", []),
        p5.get("target_abs5_presence",   []),
        p5.get("top_quartile_abs5_presence",    []),
        p5.get("bottom_quartile_abs5_presence", []),
    )
    _p5_print(
        "Phase 5 | Variable 7: Behavioral Classification (Phase 4)",
        p5.get("universe_behavior_class", []),
        p5.get("target_behavior_class",   []),
        p5.get("top_quartile_behavior_class",    []),
        p5.get("bottom_quartile_behavior_class", []),
    )
    _p5_print(
        "Phase 5 | Variable 8: Accumulation Score Tier (Phase 4)",
        p5.get("universe_accumulation_tier", []),
        p5.get("target_accumulation_tier",   []),
    )
    _p5_print(
        "Phase 5 | Variable 9: RS Daily Range at Signal",
        p5.get("universe_rs_daily_range", []),
        p5.get("target_rs_daily_range",   []),
        p5.get("top_quartile_rs_daily_range",    []),
        p5.get("bottom_quartile_rs_daily_range", []),
    )
    _p5_print(
        "Phase 5 | Interaction: Price Trajectory x RS Trajectory",
        p5.get("universe_price_x_rs_trajectory", []),
        p5.get("target_price_x_rs_trajectory",   []),
    )
    _p5_print(
        "Phase 5 | Interaction: Volume Trend x Price Trajectory",
        p5.get("universe_vol_trend_x_price_traj", []),
        p5.get("target_vol_trend_x_price_traj",   []),
    )
    _p5_print(
        "Phase 5 | Interaction: Days Since High x Price Trajectory",
        p5.get("universe_days_since_high_x_price_traj", []),
        p5.get("target_days_since_high_x_price_traj",   []),
    )


    # Console preview: pure grade buckets first, then cumulative buckets for comparison.
    preview_buckets = {
        "A_PLUS_ONLY",
        "A_ONLY",
        "A_MINUS_ONLY",
        "B_PLUS_ONLY",
        "B_ONLY",
        "C_ONLY",
        "ALL_QUALIFIED_LONGS",
        "A_MINUS_AND_ABOVE",
        "B_AND_ABOVE",
        "C_AND_ABOVE",
    }
    preview = [s for s in summary if s["bucket"] in preview_buckets]
    preview_order = {
        "A_PLUS_ONLY": 0,
        "A_ONLY": 1,
        "A_MINUS_ONLY": 2,
        "B_PLUS_ONLY": 3,
        "B_ONLY": 4,
        "C_ONLY": 5,
        "ALL_QUALIFIED_LONGS": 6,
        "A_MINUS_AND_ABOVE": 7,
        "B_AND_ABOVE": 8,
        "C_AND_ABOVE": 9,
    }
    preview = sorted(preview, key=lambda x: (preview_order.get(x["bucket"], 99), x["horizon_days"]))
    print("\nKey summary:")
    for s in preview:
        print(
            f"{s['bucket']:22s} h={s['horizon_days']:>3} "
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
