# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/assistant_market.py
---------------------------
Alpaca market-data lookups for the AI Sigmalytic Assistant (admin only, read-only).

The assistant reaches Alpaca through the platform's existing connection (radar_service.fetch_bars_batch: the
account's feed, split-adjusted bars, the same data the scan uses). Every number returned is computed here by code,
so answers built on these lookups pass the assistant's number check.

Limits protect the web backend (one worker, 2 GB): a few symbols per call, at most 10 years of daily bars.
A study of the whole universe belongs on the radar-scanner worker, not here.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from backend.indicators import rsi_series, sma

TIMEFRAMES = {"1Day": 2520, "1Week": 520, "4Hour": 1512, "1Hour": 2000}
MAX_HISTORY_ROWS = 250
MAX_INDICATOR_SYMBOLS = 20
MAX_TEST_SYMBOLS = 10
DEFAULT_TEST_PERIODS = [2, 5, 7, 9, 14, 21, 28]


def _sym(v: Any) -> str:
    s = str(v or "").strip().upper().replace("/", ".")
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s):
        raise ValueError(f"Not a valid stock symbol: {v}")
    return s


def load_bars(symbols: List[str], timeframe: str, bars: int) -> Dict[str, List[dict]]:
    """Completed bars from Alpaca, oldest first, as [{"t", "o", "h", "l", "c", "v"}]. Replaceable in tests."""
    from backend.radar_service import fetch_bars_batch, trim_incomplete_bar
    raw = fetch_bars_batch(list(symbols), timeframe=timeframe, limit=int(bars) + 1, min_bars_floor=10)
    out = {}
    for s in symbols:
        b = trim_incomplete_bar(raw.get(s) or [], timeframe)
        out[s] = [x for x in b if x.get("c") is not None][-int(bars):]
    return out


def _check_tf(timeframe: str) -> str:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Timeframe must be one of {', '.join(TIMEFRAMES)}.")
    return timeframe


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return round((a / b - 1) * 100, 2) if a is not None and b else None


def _date(b: dict, timeframe: str) -> str:
    t = str(b.get("t") or "")
    return t[:10] if timeframe in ("1Day", "1Week") else t[:16].replace("T", " ")


def tool_get_price_history(symbol: str, timeframe: str = "1Day", bars: int = 60) -> Dict[str, Any]:
    sym, tf = _sym(symbol), _check_tf(timeframe)
    n = max(5, min(int(bars or 60), TIMEFRAMES[tf]))
    data = load_bars([sym], tf, n).get(sym) or []
    if not data:
        return {"ok": False, "error": f"Alpaca returned no {tf} bars for {sym}."}
    closes = [float(b["c"]) for b in data]
    rows = [[_date(b, tf), round(float(b["o"]), 2), round(float(b["h"]), 2), round(float(b["l"]), 2),
             round(float(b["c"]), 2), int(b.get("v") or 0)] for b in data[-MAX_HISTORY_ROWS:]]
    return {"ok": True, "source": "Alpaca, split-adjusted", "symbol": sym, "timeframe": tf, "bars": len(data),
            "first": _date(data[0], tf), "last": _date(data[-1], tf),
            "change_pct": _pct(closes[-1], closes[0]), "high": round(max(float(b["h"]) for b in data), 2),
            "low": round(min(float(b["l"]) for b in data), 2),
            "columns": ["date", "open", "high", "low", "close", "volume"], "rows": rows,
            "rows_note": (f"Only the latest {MAX_HISTORY_ROWS} bars are listed; the summary covers all {len(data)}."
                          if len(data) > MAX_HISTORY_ROWS else None)}


def tool_get_indicators(symbols: List[str], timeframe: str = "1Day", rsi_periods: Optional[List[int]] = None,
                        sma_periods: Optional[List[int]] = None) -> Dict[str, Any]:
    tf = _check_tf(timeframe)
    syms = list(dict.fromkeys(_sym(s) for s in (symbols or [])))
    if not syms:
        return {"ok": False, "error": "Give at least one symbol."}
    if len(syms) > MAX_INDICATOR_SYMBOLS:
        return {"ok": False, "error": f"At most {MAX_INDICATOR_SYMBOLS} symbols per call."}
    rp = sorted({max(2, min(int(p), 100)) for p in (rsi_periods or [14])})
    sp = sorted({max(2, min(int(p), 400)) for p in (sma_periods or [20, 50, 200])})
    need = max(max(sp), max(rp) * 6, 253)
    data = load_bars(syms, tf, min(need + 5, TIMEFRAMES[tf]))
    out, missing = [], []
    for s in syms:
        b = data.get(s) or []
        if len(b) < max(rp) + 1:
            missing.append(s)
            continue
        c = [float(x["c"]) for x in b]
        row: Dict[str, Any] = {"symbol": s, "as_of": _date(b[-1], tf), "close": round(c[-1], 2)}
        for p in rp:
            row[f"rsi{p}"] = rsi_series(c, p)[-1]
        for p in sp:
            avg = sma(c, p)
            row[f"sma{p}"] = avg
            row[f"vs_sma{p}_pct"] = _pct(c[-1], avg)
        for n in (20, 60, 252):
            if len(c) > n:
                row[f"return_{n}_bars_pct"] = _pct(c[-1], c[-1 - n])
        out.append(row)
    return {"ok": True, "source": "Alpaca, split-adjusted", "timeframe": tf, "rsi": "Wilder", "rows": out,
            "no_data": missing}


def _period_stats(closes: Sequence[float], rsi: Sequence[Optional[float]], threshold: float, horizon: int,
                  lo: int, hi: int) -> Dict[str, Any]:
    """Events: RSI crosses below `threshold` at bar i (lo <= i < hi, with i + horizon inside the history).
    Forward return = close[i + horizon] / close[i] - 1."""
    fwd = []
    for i in range(max(lo, 1), min(hi, len(closes) - horizon)):
        a, b = rsi[i - 1], rsi[i]
        if a is not None and b is not None and a >= threshold > b:
            fwd.append(closes[i + horizon] / closes[i] - 1)
    if not fwd:
        return {"events": 0, "avg_fwd_return_pct": None, "share_followed_by_decline_pct": None}
    return {"events": len(fwd), "avg_fwd_return_pct": round(sum(fwd) / len(fwd) * 100, 2),
            "share_followed_by_decline_pct": round(sum(1 for x in fwd if x < 0) / len(fwd) * 100, 1)}


def tool_test_rsi_exit(symbols: List[str], periods: Optional[List[int]] = None, threshold: float = 40,
                       horizon: int = 20, years: int = 10, train_share: float = 0.7,
                       min_events: int = 5) -> Dict[str, Any]:
    """For each symbol and RSI period: how the stock did over the next `horizon` days after its daily RSI crossed
    below `threshold`. The best period (lowest average forward return = the best warning of further decline) is
    chosen on the first train_share of the history, then checked on the rest, which the choice never saw, against
    RSI(14)."""
    syms = list(dict.fromkeys(_sym(s) for s in (symbols or [])))
    if not syms:
        return {"ok": False, "error": "Give at least one symbol."}
    if len(syms) > MAX_TEST_SYMBOLS:
        return {"ok": False, "error": f"At most {MAX_TEST_SYMBOLS} symbols per call; a whole-universe study runs "
                                      f"on the scanner worker instead."}
    ps = sorted({max(2, min(int(p), 60)) for p in (periods or DEFAULT_TEST_PERIODS)} | {14})
    h = max(1, min(int(horizon or 20), 120))
    yrs = max(1, min(int(years or 10), 10))
    split_share = max(0.5, min(float(train_share or 0.7), 0.9))
    data = load_bars(syms, "1Day", min(yrs * 252 + 10, TIMEFRAMES["1Day"]))
    results, missing = [], []
    for s in syms:
        b = data.get(s) or []
        if len(b) < 252 + h:
            missing.append(s)
            continue
        c = [float(x["c"]) for x in b]
        split = int(len(c) * split_share)
        per = {}
        for p in ps:
            r = rsi_series(c, p)
            per[p] = {"in_sample": _period_stats(c, r, threshold, h, 0, split),
                      "out_of_sample": _period_stats(c, r, threshold, h, split, len(c))}
        ok = [p for p in ps if per[p]["in_sample"]["events"] >= min_events]
        best = min(ok, key=lambda p: per[p]["in_sample"]["avg_fwd_return_pct"]) if ok else None
        results.append({
            "symbol": s, "history": f"{_date(b[0], '1Day')} to {_date(b[-1], '1Day')}",
            "split_date": _date(b[split], "1Day"),
            "best_period_in_sample": best,
            "best_in_sample": per[best]["in_sample"] if best else None,
            "best_out_of_sample": per[best]["out_of_sample"] if best else None,
            "rsi14_out_of_sample": per[14]["out_of_sample"],
            "by_period": {str(p): per[p] for p in ps}})
    return {"ok": True, "source": "Alpaca daily bars, split-adjusted",
            "rule": f"daily RSI crosses below {threshold}; return over the next {h} trading days",
            "selection": (f"best period = lowest average forward return on the first {int(split_share * 100)}% of "
                          f"history with at least {min_events} events; judge it only on out_of_sample"),
            "periods": ps, "results": results, "no_data": missing,
            "caution": ("Choosing the best of several settings on past data often looks good by chance; only the "
                        "out-of-sample figures show whether a setting held up. A few symbols are not proof.")}
