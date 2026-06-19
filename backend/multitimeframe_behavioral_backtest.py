# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/multitimeframe_behavioral_backtest.py

Multi-Timeframe Behavioral Attribution Builder v1.0

Phase 1:
    Weekly = regime / trend filter
    Daily  = setup discovery + readiness snapshot
    Outcome = 5D / 10D / 20D return, MFE, MAE, favorable, tradeable

Run:
    python backend/multitimeframe_behavioral_backtest.py --symbols-file backend/backtest_symbols_50.txt --years 2

Optional:
    python backend/multitimeframe_behavioral_backtest.py --symbols AAPL,MSFT,NVDA,SPY,QQQ --years 2
"""

from __future__ import annotations

import os
import csv
import json
import time
import argparse
import statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from behavioral_transition_engine import evaluate_behavioral_transition
    BEHAVIORAL_ENGINE_AVAILABLE = True
except Exception:
    BEHAVIORAL_ENGINE_AVAILABLE = False


ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED = os.getenv("ALPACA_FEED", "iex")


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pct(a: float, b: float) -> Optional[float]:
    if b == 0:
        return None
    return (a - b) / b * 100.0


def _parse_dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _sma(values: List[float], length: int) -> Optional[float]:
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def _atr_from_rows(rows: List[dict], period: int = 14) -> float:
    if len(rows) < 2:
        if rows:
            return max(_f(rows[-1].get("h")) - _f(rows[-1].get("l")), 0.01)
        return 1.0

    trs = []
    for i in range(1, len(rows)):
        h = _f(rows[i].get("h"))
        l = _f(rows[i].get("l"))
        pc = _f(rows[i - 1].get("c"))
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)

    if not trs:
        return 1.0
    return max(sum(trs[-period:]) / min(period, len(trs)), 0.01)


def _avg_volume(rows: List[dict], length: int = 20) -> float:
    vols = [_f(r.get("v")) for r in rows[-length:] if _f(r.get("v")) > 0]
    return sum(vols) / len(vols) if vols else 1.0


def fetch_daily_bars(symbol: str, years: int = 2) -> List[dict]:
    start_date = (datetime.now(timezone.utc) - timedelta(days=int(years * 365.25) + 120)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
            headers=_headers(),
            params={
                "timeframe": "1Day",
                "start": start_date,
                "feed": ALPACA_FEED,
                "sort": "asc",
                "adjustment": "raw",
            },
            timeout=20,
        )
        if r.status_code != 200:
            print(f"  fetch failed {symbol}: {r.status_code} {r.text[:120]}")
            return []
        return r.json().get("bars") or []
    except Exception as e:
        print(f"  fetch error {symbol}: {e}")
        return []


def resample_weekly(daily_rows: List[dict]) -> List[dict]:
    buckets: Dict[Tuple[int, int], List[dict]] = {}

    for r in daily_rows:
        try:
            dt = _parse_dt(r.get("t"))
            key = (dt.isocalendar().year, dt.isocalendar().week)
            buckets.setdefault(key, []).append(r)
        except Exception:
            continue

    weekly = []
    for key in sorted(buckets.keys()):
        rows = buckets[key]
        if not rows:
            continue
        first = rows[0]
        last = rows[-1]
        weekly.append({
            "t": last.get("t"),
            "o": _f(first.get("o")),
            "h": max(_f(x.get("h")) for x in rows),
            "l": min(_f(x.get("l")) for x in rows),
            "c": _f(last.get("c")),
            "v": sum(_f(x.get("v")) for x in rows),
        })
    return weekly


def weekly_rows_until(weekly_rows: List[dict], current_date: datetime) -> List[dict]:
    out = []
    for w in weekly_rows:
        try:
            if _parse_dt(w.get("t")) <= current_date:
                out.append(w)
        except Exception:
            continue
    return out


def infer_weekly_regime(weekly_history: List[dict]) -> str:
    if len(weekly_history) < 12:
        return "Insufficient Weekly Data"

    closes = [_f(w.get("c")) for w in weekly_history]
    highs = [_f(w.get("h")) for w in weekly_history]
    lows = [_f(w.get("l")) for w in weekly_history]
    volumes = [_f(w.get("v")) for w in weekly_history]

    close = closes[-1]
    prev = closes[-2]
    ma10 = _sma(closes, 10) or close
    ma20 = _sma(closes, 20) or ma10
    avg_vol = sum(volumes[-10:]) / min(10, len(volumes)) if volumes else 1
    rel_vol = volumes[-1] / avg_vol if avg_vol > 0 else 1
    change = _pct(close, prev) or 0

    recent_high = max(highs[-12:])
    near_high = recent_high > 0 and (recent_high - close) / recent_high < 0.04
    weak_close = close < (lows[-1] + (highs[-1] - lows[-1]) * 0.45)

    if close > ma10 > ma20 and change >= 0:
        if rel_vol >= 1.3 and change > 3:
            return "Weekly FOMO / Expansion"
        return "Weekly Markup"

    if close > ma10 > ma20 and change < 0:
        return "Weekly Pullback Within Markup"

    if close < ma10 < ma20 and change <= 0:
        if rel_vol >= 1.4 and change < -4:
            return "Weekly Capitulation / Markdown"
        return "Weekly Markdown"

    if close < ma10 < ma20 and change > 0:
        return "Weekly Bear Rally / Recovery Attempt"

    if near_high and weak_close and rel_vol >= 1.1:
        return "Weekly Distribution Risk"

    return "Weekly Neutral"


def classify_daily_setup(price: float, ma20: float, ma50: float, atr: float,
                         high: float, low: float, high_52w: float,
                         rel_vol: float, change_pct: float,
                         closes: List[float]) -> str:
    if len(closes) < 5:
        return "Insufficient Data"

    recent_range = max(closes[-5:]) - min(closes[-5:])
    avg_range = atr * 5 if atr > 0 else max(recent_range, 0.01)
    compressed = recent_range < avg_range * 0.6
    near_52w_high = high_52w > 0 and ((high_52w - price) / high_52w) < 0.03

    if compressed and near_52w_high:
        return "Compression Breakout Candidate"
    if compressed:
        return "Volatility Expansion Candidate"
    if change_pct > 2 and rel_vol > 1.5 and price > ma20:
        return "Trend Continuation"
    if change_pct > 1 and price > ma20 > ma50:
        return "Momentum Leader"
    if change_pct < -3 and rel_vol > 1.5:
        return "Breakdown Risk"
    if change_pct < -1 and price < ma20:
        return "Distribution"
    if abs(change_pct) < 0.5 and rel_vol < 0.8:
        return "Low Edge — Avoid"
    return "Monitoring"


def infer_daily_regime(change_pct: float, rel_vol: float, price: float, ma20: float, ma50: float) -> str:
    if price > ma20 > ma50 and change_pct > 1:
        return "Bull Expansion"
    if price > ma20 > ma50 and change_pct < 0:
        return "Bull Pullback"
    if price < ma20 < ma50 and change_pct < -1:
        return "Bear Expansion"
    if price < ma20 < ma50 and change_pct > 0:
        return "Bear Rally"
    if abs(change_pct) < 0.3 and rel_vol < 0.8:
        return "Compression"
    return "Neutral"


def determine_status(composite: float, expansion: float, rel_vol: float,
                     change_pct: float, price: float, trigger: float,
                     invalidation: float, ma20: float) -> str:
    if invalidation > 0 and price <= invalidation and rel_vol >= 1.2 and change_pct < -2:
        return "Short Trigger"
    if change_pct < -1.5 and rel_vol >= 1.1 and invalidation > 0 and price > 0:
        if (price - invalidation) / price <= 0.01 and price < ma20:
            return "Short Armed"
    if trigger > 0 and price >= trigger and rel_vol >= 1.2:
        return "Triggered"
    if composite >= 75 and expansion >= 60:
        return "Armed"
    if composite >= 68:
        return "Building"
    if change_pct < -3 or composite < 45:
        return "Avoid"
    return "Watching"


def score_daily_snapshot(symbol: str, rows_until_today: List[dict], weekly_regime: str) -> Optional[dict]:
    if len(rows_until_today) < 60:
        return None

    today = rows_until_today[-1]
    prev = rows_until_today[-2]

    date = _parse_dt(today.get("t")).date().isoformat()
    price = _f(today.get("c"))
    day_open = _f(today.get("o"))
    day_high = _f(today.get("h"))
    day_low = _f(today.get("l"))
    volume = _f(today.get("v"))
    prev_close = _f(prev.get("c"))

    if price <= 0 or prev_close <= 0:
        return None

    closes = [_f(r.get("c")) for r in rows_until_today]
    highs = [_f(r.get("h")) for r in rows_until_today]
    lows = [_f(r.get("l")) for r in rows_until_today]

    change_pct = _pct(price, prev_close) or 0
    ma20 = _sma(closes, 20) or price
    ma50 = _sma(closes, 50) or price
    avg_vol_20 = _avg_volume(rows_until_today, 20)
    rel_vol = volume / avg_vol_20 if avg_vol_20 > 0 else 1.0
    atr = _atr_from_rows(rows_until_today[-20:], 14)
    high_52w = max(highs[-252:]) if len(highs) >= 60 else max(highs)
    low_52w = min(lows[-252:]) if len(lows) >= 60 else min(lows)
    vwap = price

    confluence = 50.0
    if price > vwap:
        confluence += 8
    if price > ma20:
        confluence += 8
    if price > ma50:
        confluence += 6
    if price > day_open:
        confluence += 5
    if change_pct > 0:
        confluence += 5
    if rel_vol > 1.5:
        confluence += 8
    if rel_vol > 2.0:
        confluence += 4
    if price > prev_close:
        confluence += 3
    confluence = _clamp(confluence)

    expansion = 50.0
    if atr > 0:
        rng_ratio = (day_high - day_low) / atr
        if rng_ratio < 0.6:
            expansion += 20
        elif rng_ratio < 0.8:
            expansion += 10
        elif rng_ratio > 1.5:
            expansion -= 10

    dist_52w = ((high_52w - price) / high_52w) if high_52w > 0 else 1
    if dist_52w < 0.02:
        expansion += 15
    elif dist_52w < 0.05:
        expansion += 8
    elif dist_52w > 0.20:
        expansion -= 10
    if rel_vol > 1.3 and change_pct > 0:
        expansion += 7
    expansion = _clamp(expansion)

    rel_strength = 50.0
    if len(closes) >= 20 and closes[-20] > 0:
        perf_1m = _pct(price, closes[-20]) or 0
        if perf_1m > 5:
            rel_strength += 20
        elif perf_1m > 2:
            rel_strength += 12
        elif perf_1m > 0:
            rel_strength += 5
        elif perf_1m < -5:
            rel_strength -= 15
        elif perf_1m < -2:
            rel_strength -= 8
    if price > ma20 > ma50:
        rel_strength += 10
    if price < ma20 < ma50:
        rel_strength -= 10
    rel_strength = _clamp(rel_strength)

    volume_pressure = 50.0
    if rel_vol > 3.0:
        volume_pressure += 30
    elif rel_vol > 2.0:
        volume_pressure += 20
    elif rel_vol > 1.5:
        volume_pressure += 12
    elif rel_vol > 1.2:
        volume_pressure += 6
    elif rel_vol < 0.7:
        volume_pressure -= 15
    elif rel_vol < 0.5:
        volume_pressure -= 25
    if change_pct > 0 and rel_vol > 1.5:
        volume_pressure += 5
    if change_pct < 0 and rel_vol > 1.5:
        volume_pressure -= 5
    volume_pressure = _clamp(volume_pressure)

    behavioral = 50.0
    if price > day_open:
        behavioral += 10
    if price > vwap:
        behavioral += 8
    if day_low > prev_close * 0.98:
        behavioral += 8
    if change_pct > 2:
        behavioral += 8
    if change_pct > 5:
        behavioral += 7
    if change_pct < -3:
        behavioral -= 15
    if price < day_open:
        behavioral -= 8
    behavioral = _clamp(behavioral)

    weekly_alignment = 0
    if "Markup" in weekly_regime and price > ma20:
        weekly_alignment = 5
    elif "Markdown" in weekly_regime and price < ma20:
        weekly_alignment = 5
    elif "Distribution" in weekly_regime and change_pct < 0:
        weekly_alignment = 4
    elif "Pullback Within Markup" in weekly_regime and price >= ma50:
        weekly_alignment = 3

    composite = _clamp(round(
        confluence * 0.25 +
        expansion * 0.20 +
        rel_strength * 0.20 +
        volume_pressure * 0.20 +
        behavioral * 0.15 +
        weekly_alignment,
        1,
    ))

    setup_type = classify_daily_setup(price, ma20, ma50, atr, day_high, day_low, high_52w, rel_vol, change_pct, closes)
    trigger = round(day_high + atr * 0.1, 2) if atr > 0 else round(price * 1.005, 2)
    invalidation = round(day_low - atr * 0.1, 2) if atr > 0 else round(price * 0.99, 2)
    target1 = round(price + atr * 1.0, 2)
    target2 = round(price + atr * 2.0, 2)
    daily_regime = infer_daily_regime(change_pct, rel_vol, price, ma20, ma50)
    status = determine_status(composite, expansion, rel_vol, change_pct, price, trigger, invalidation, ma20)

    row = {
        "symbol": symbol,
        "date": date,
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "volume": int(volume),
        "rel_volume": round(rel_vol, 2),
        "composite_score": composite,
        "confluence": round(confluence, 1),
        "expansion_node": round(expansion, 1),
        "relative_strength": round(rel_strength, 1),
        "volume_pressure": round(volume_pressure, 1),
        "behavioral": round(behavioral, 1),
        "setup_type": setup_type,
        "status": status,
        "trigger": trigger,
        "invalidation": invalidation,
        "target1": target1,
        "target2": target2,
        "daily_regime": daily_regime,
        "regime": daily_regime,
        "weekly_regime": weekly_regime,
        "ma20": round(ma20, 2),
        "ma50": round(ma50, 2),
        "atr": round(atr, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "trigger_proximity": round((trigger - price) / price * 100, 2) if price > 0 and trigger > 0 else 0,
    }

    if BEHAVIORAL_ENGINE_AVAILABLE:
        try:
            bt = evaluate_behavioral_transition(row)
            row["readiness_score"] = bt.get("readiness_score")
            row["behavioral_state"] = bt.get("behavioral_state")
            row["transition_candidate"] = bt.get("transition_candidate")
            row["opportunity_state"] = bt.get("opportunity_state")
            row["trade_side"] = bt.get("side")
            row["confidence_label"] = bt.get("confidence_label")
            row["alert_type"] = bt.get("alert_type")
            row["why_this_trade"] = bt.get("why_this_trade")
        except Exception:
            row["readiness_score"] = composite
            row["behavioral_state"] = ""
            row["transition_candidate"] = ""
            row["opportunity_state"] = status
            row["trade_side"] = "Long"
    else:
        row["readiness_score"] = composite
        row["behavioral_state"] = ""
        row["transition_candidate"] = ""
        row["opportunity_state"] = status
        row["trade_side"] = "Long"

    return row


def forward_outcomes(rows: List[dict], idx: int, side: str, windows=(5, 10, 20)) -> dict:
    out = {}
    entry = _f(rows[idx].get("c"))
    if entry <= 0:
        return out

    is_short = "short" in (side or "Long").lower()

    for w in windows:
        future = rows[idx + 1: idx + 1 + w]
        if len(future) < w:
            out[f"return_{w}d"] = None
            out[f"mfe_{w}d"] = None
            out[f"mae_{w}d"] = None
            out[f"favorable_{w}d"] = None
            out[f"tradeable_{w}d"] = None
            continue

        close_w = _f(future[-1].get("c"))
        high_w = max(_f(r.get("h")) for r in future)
        low_w = min(_f(r.get("l")) for r in future)

        if is_short:
            ret = (entry - close_w) / entry * 100
            mfe = (entry - low_w) / entry * 100
            mae = (high_w - entry) / entry * 100
        else:
            ret = (close_w - entry) / entry * 100
            mfe = (high_w - entry) / entry * 100
            mae = (entry - low_w) / entry * 100

        out[f"return_{w}d"] = round(ret, 3)
        out[f"mfe_{w}d"] = round(mfe, 3)
        out[f"mae_{w}d"] = round(mae, 3)
        out[f"favorable_{w}d"] = bool(ret > 0)
        out[f"tradeable_{w}d"] = bool(mfe >= 1.5 and mfe > mae)

    return out


def summarize_group(rows: List[dict], key: str, window: int = 10, min_count: int = 5) -> List[dict]:
    groups: Dict[str, List[dict]] = {}

    for r in rows:
        k = str(r.get(key) or "Unknown")
        groups.setdefault(k, []).append(r)

    summary = []
    for group, items in groups.items():
        eval_items = [x for x in items if x.get(f"return_{window}d") is not None]
        n = len(eval_items)
        if n < min_count:
            continue

        fav = sum(1 for x in eval_items if x.get(f"favorable_{window}d") is True)
        trd = sum(1 for x in eval_items if x.get(f"tradeable_{window}d") is True)
        returns = [_f(x.get(f"return_{window}d")) for x in eval_items]
        mfe = [_f(x.get(f"mfe_{window}d")) for x in eval_items]
        mae = [_f(x.get(f"mae_{window}d")) for x in eval_items]

        avg_return = statistics.mean(returns) if returns else 0
        avg_mfe = statistics.mean(mfe) if mfe else 0
        avg_mae = statistics.mean(mae) if mae else 0
        edge_ratio = avg_mfe / max(avg_mae, 0.01)

        summary.append({
            "group": group,
            "count": n,
            "favorable_rate": round(fav / n * 100, 1),
            "tradeable_rate": round(trd / n * 100, 1),
            "avg_return": round(avg_return, 3),
            "avg_mfe": round(avg_mfe, 3),
            "avg_mae": round(avg_mae, 3),
            "edge_ratio": round(edge_ratio, 2),
        })

    summary.sort(key=lambda x: (x["tradeable_rate"], x["edge_ratio"], x["count"]), reverse=True)
    return summary


def summarize_readiness_buckets(rows: List[dict], window: int = 10) -> List[dict]:
    bucketed = []
    for r in rows:
        score = _f(r.get("readiness_score"))
        if score >= 90:
            b = "90+ Elite"
        elif score >= 80:
            b = "80-89 High"
        elif score >= 70:
            b = "70-79 Qualified"
        elif score >= 60:
            b = "60-69 Developing"
        else:
            b = "<60 Low"
        x = dict(r)
        x["readiness_bucket"] = b
        bucketed.append(x)
    return summarize_group(bucketed, "readiness_bucket", window, min_count=5)


def summarize(rows: List[dict]) -> dict:
    return {
        "total_rows": len(rows),
        "by_weekly_regime": summarize_group(rows, "weekly_regime", 10),
        "by_daily_setup": summarize_group(rows, "setup_type", 10),
        "by_transition": summarize_group(rows, "transition_candidate", 10),
        "by_opportunity_state": summarize_group(rows, "opportunity_state", 10),
        "by_readiness_bucket": summarize_readiness_buckets(rows, 10),
    }


def load_symbols(args) -> List[str]:
    if args.symbols:
        return [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if args.symbols_file:
        p = Path(args.symbols_file)
        if not p.exists():
            raise FileNotFoundError(f"Symbols file not found: {p}")
        return [line.strip().upper() for line in p.read_text().splitlines() if line.strip() and not line.strip().startswith("#")]

    return ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]


def write_outputs(rows: List[dict], summary: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "mtf_behavioral_observations.csv"
    json_path = output_dir / "mtf_behavioral_observations.json"
    summary_path = output_dir / "mtf_behavioral_summary.json"

    if rows:
        fieldnames = sorted(set().union(*(r.keys() for r in rows)))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print(f"CSV:     {csv_path}")
    print(f"JSON:    {json_path}")
    print(f"Summary: {summary_path}")


def run(args):
    symbols = load_symbols(args)
    output_dir = Path(args.output_dir or f"backtests/mtf_phase1_{len(symbols)}symbols_{args.years}years_daily_weekly")

    print("Starting Multi-Timeframe Behavioral Attribution Builder")
    print(f"Symbols: {len(symbols)}")
    print(f"Years: {args.years}")
    print(f"Feed: {ALPACA_FEED}")
    print(f"Behavioral engine available: {BEHAVIORAL_ENGINE_AVAILABLE}")
    print(f"Output: {output_dir}")
    print("-" * 80)

    if not ALPACA_API_KEY:
        print("WARNING: ALPACA_API_KEY is missing. Fetches will fail unless env vars are set.")

    all_rows: List[dict] = []

    for n, symbol in enumerate(symbols, start=1):
        print(f"[{n}/{len(symbols)}] {symbol}")
        daily = fetch_daily_bars(symbol, args.years)
        if len(daily) < 90:
            print(f"  skipped: only {len(daily)} daily bars")
            continue

        weekly = resample_weekly(daily)
        symbol_rows = []
        max_window = 20

        for i in range(60, len(daily) - max_window):
            current_dt = _parse_dt(daily[i].get("t"))
            daily_history = daily[: i + 1]
            weekly_history = weekly_rows_until(weekly, current_dt)
            weekly_regime = infer_weekly_regime(weekly_history)

            snap = score_daily_snapshot(symbol, daily_history, weekly_regime)
            if not snap:
                continue

            if _f(snap.get("readiness_score")) < args.min_readiness and _f(snap.get("composite_score")) < args.min_score:
                continue

            snap.update(forward_outcomes(daily, i, snap.get("trade_side", "Long")))
            symbol_rows.append(snap)

        all_rows.extend(symbol_rows)
        print(f"  observations: {len(symbol_rows)}")
        time.sleep(args.sleep)

    print("-" * 80)
    print(f"Total observations: {len(all_rows)}")

    summary = summarize(all_rows)
    print("Summary preview:")
    print(json.dumps(summary, indent=2)[:4000])

    write_outputs(all_rows, summary, output_dir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="", help="Comma-separated symbols")
    parser.add_argument("--symbols-file", default="", help="Path to symbol list")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--min-readiness", type=float, default=60)
    parser.add_argument("--min-score", type=float, default=60)
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

