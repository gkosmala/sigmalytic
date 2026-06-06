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

    summary = summarize(signal_rows, horizons)
    factor_summary = summarize_factor_attribution(signal_rows)
    setup_breakdown = summarize_setup_breakdown(signal_rows)
    expansion_subtype_summary = summarize_expansion_subtypes(signal_rows)
    volatility_dna_summary = summarize_volatility_dna(signal_rows)
    volatility_interactions = summarize_volatility_interactions(signal_rows)

    # Flatten rows for CSV.
    flat_fields = [
        "symbol", "signal_date", "entry_close", "setup_type", "setup_subtype", "grade", "audit_score",
        "rs_2h", "rs_daily", "daily_rs_slope_pct", "rel_volume", "rel_volume_bucket",
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
        "output_files": {
            "rows_csv": str(rows_csv),
            "summary_csv": str(summary_csv),
            "factor_csv": str(factor_csv),
            "setup_breakdown_csv": str(setup_breakdown_csv),
            "expansion_subtype_csv": str(expansion_subtype_csv),
            "volatility_dna_json": str(volatility_dna_json),
        },
    }
    summary_json.write_text(json.dumps(payload, indent=2))
    volatility_dna_json.write_text(json.dumps(volatility_dna_summary, indent=2))

    print("\nAudit complete")
    print(f"Signals: {len(signal_rows):,}")
    print(f"Rows:    {rows_csv}")
    print(f"Summary: {summary_json}")
    print(f"CSV:     {summary_csv}")
    print(f"Factors: {factor_csv}")
    print(f"Setups:  {setup_breakdown_csv}")
    print(f"Subtypes:{expansion_subtype_csv}")
    print(f"VolDNA:  {volatility_dna_json}")

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
