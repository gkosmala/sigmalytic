"""Pivot scan (Astro Research, owner only): which Russell 1000 stocks had a pivot high or pivot low 6, 12, 18 ... 60 months ago?

Owner's definitions (2026-10-20):
  - pivots are the Gann Fan's daily-chart pivots (course p.124 bottom: a 3-bar rally with higher lows and higher highs; p.126 top:
    3 bars with lower lows and lower highs), read on Alpaca split-adjusted daily bars;
  - the pivot date must fall within 5 days before or after the date N months ago.
Calendar days are used for the 5 days (my reading of "5 days"; market days would be a different window).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

MONTHS = (6, 12, 18, 24, 30, 36, 42, 48, 54, 60)
TOL_DAYS = 5
BENCHMARKS = ("SPY", "QQQ", "IWM", "GLD", "SMH")   # added by load_russell1000(); they are not Russell 1000 stocks
HISTORY_YEARS = 7                                   # 60 months plus a lead-in so the pivot sequence has settled
BATCH = 40


def scan_bars(symbol: str, bars: List[Dict[str, Any]], today: date) -> List[Dict[str, Any]]:
    """Pivots of one symbol that sit within TOL_DAYS of each N months before `today`."""
    from backend import astro_gann_extra as gx
    rows = gx.chart_bars(bars, "daily", str(today))
    if len(rows) < 60:
        return []
    out = []
    targets = {n: gx._add_months(today, -n) for n in MONTHS}
    for p in gx.gann_pivots(rows, "daily"):
        pd = datetime.strptime(str(p["date"])[:10], "%Y-%m-%d").date()
        for n, tgt in targets.items():
            if abs((pd - tgt).days) <= TOL_DAYS:
                out.append({"symbol": symbol, "months": n, "kind": "pivot high" if p["kind"] == "high" else "pivot low",
                            "date": str(pd), "price": round(float(p["price"]), 2), "target": str(tgt), "confirmed": str(p["confirmed"])[:10]})
    return out


def pivot_scan(symbols: Optional[List[str]] = None, today: Optional[date] = None,
               fetch: Optional[Callable[[List[str], datetime, datetime], Dict[str, List[dict]]]] = None, workers: int = 6) -> Dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor
    if symbols is None:
        from backend.radar_service import load_russell1000
        symbols = [s for s in load_russell1000() if s not in BENCHMARKS]
    if today is None:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/New_York")).date()
    if fetch is None:
        from backend.broker_market_data import fetch_daily_bars as fetch
    start = datetime.combine(today - timedelta(days=int(365.25 * HISTORY_YEARS)), datetime.min.time())
    end = datetime.combine(today, datetime.min.time())
    batches = [symbols[i:i + BATCH] for i in range(0, len(symbols), BATCH)]

    def run(batch: List[str]):
        got = fetch(batch, start, end)
        rows, with_bars = [], 0
        for s in batch:
            b = got.get(s) or []
            if b:
                with_bars += 1
                rows += scan_bars(s, b, today)
        return rows, with_bars

    rows, with_bars = [], 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for r, w in pool.map(run, batches):
            rows += r
            with_bars += w
    rows.sort(key=lambda x: (x["months"], x["kind"], x["symbol"]))
    return {"today": str(today), "months": list(MONTHS), "tolerance_days": TOL_DAYS, "universe": len(symbols), "with_bars": with_bars,
            "rows": rows,
            "note": "Pivots by the Gann Fan's daily rules (course pp.124 and 126) on Alpaca split-adjusted daily bars; the pivot date is within "
                    f"{TOL_DAYS} calendar days of the date N months before {today}. The universe is the platform's Russell 1000 list "
                    "(benchmark ETFs removed); it may not match the index exactly."}
