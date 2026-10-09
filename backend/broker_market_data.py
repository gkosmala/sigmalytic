# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_market_data.py
-----------------------------
Market data for Broker Behavioural Intelligence: daily bars over a date
range, the Russell 1000 proxy (IWB) return for a statement period, and a
point-in-time Sigmalytic reading for a symbol on a past trade date.

Network failures never raise: callers get None / empty and the review shows
"not enough data" for that section.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

log = logging.getLogger("broker_market_data")

BASE = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
FEED = os.getenv("ALPACA_FEED", "sip")
MIN_BARS_FOR_READING = 60
WARMUP_DAYS = 330


def _headers() -> Dict[str, str]:
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_KEY_ID") or ""
    sec = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or ""
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}


# Broker exports use many date styles. US-style dates often carry a time
# ("08/10/2026 09:35:00" or "8/10/2026 9:35 AM"); those must parse too, or the
# whole statement ends up undated and nothing can be read as of a trade date.
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%Y",
    "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M", "%m/%d/%y %I:%M:%S %p", "%m/%d/%y %I:%M %p", "%m/%d/%y",
)


def parse_date(text: Any) -> Optional[datetime]:
    s = str(text or "").strip()
    if not s:
        return None
    # Try the whole text first (needed for "AM/PM" forms), then the first 19
    # characters (trims fractional seconds and timezone suffixes).
    candidates = [s] if len(s) <= 19 else [s, s[:19]]
    for cand in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cand, fmt)
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# Why a trade could not be read, from the most recent point_in_time_readings()
# call. The review shows this next to "not read" so a missing reading is never
# a mystery. (The review builds synchronously, so one call's reasons are read
# before any other call can replace them.)
_last_reasons: Dict[Tuple[str, str], str] = {}
_last_fetch_error: Optional[str] = None


def last_reading_reasons() -> Dict[Tuple[str, str], str]:
    """{(symbol, date): plain-language reason} for trades the last call could not read."""
    return dict(_last_reasons)


def fetch_daily_bars(symbols: List[str], start: datetime, end: datetime) -> Dict[str, List[dict]]:
    """Daily bars (split-adjusted) for each symbol between start and end."""
    global _last_fetch_error
    out: Dict[str, List[dict]] = {s: [] for s in symbols}
    for i in range(0, len(symbols), 40):
        batch = symbols[i:i + 40]
        token = None
        for _ in range(20):  # page guard
            params = {
                "symbols": ",".join(batch), "timeframe": "1Day", "adjustment": "split",
                "start": start.strftime("%Y-%m-%dT00:00:00Z"), "end": end.strftime("%Y-%m-%dT23:59:59Z"),
                "feed": FEED, "limit": "10000", "sort": "asc",
            }
            if token:
                params["page_token"] = token
            try:
                r = requests.get(f"{BASE}/v2/stocks/bars", headers=_headers(), params=params, timeout=25)
                if r.status_code != 200:
                    log.warning("bars %s: %s", r.status_code, r.text[:160])
                    _last_fetch_error = f"Alpaca price history request failed (HTTP {r.status_code}): {r.text[:120]}"
                    break
                body = r.json()
            except Exception as exc:  # network: never fatal
                log.warning("bars request failed: %s", exc)
                _last_fetch_error = f"Alpaca price history request failed: {type(exc).__name__}"
                break
            for sym, rows in (body.get("bars") or {}).items():
                if isinstance(rows, list) and sym in out:
                    out[sym].extend(rows)
            token = body.get("next_page_token")
            if not token:
                break
    return out


def benchmark_stats(start: datetime, end: datetime, symbol: str = "IWB") -> Optional[Dict[str, float]]:
    """Return {'return_pct', 'max_drawdown_pct'} for symbol over the period, or None."""
    bars = fetch_daily_bars([symbol], start - timedelta(days=5), end).get(symbol) or []
    closes = [float(b["c"]) for b in bars if b.get("c")]
    if len(closes) < 2:
        return None
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        worst = min(worst, (c - peak) / peak * 100)
    return {"return_pct": round((closes[-1] / closes[0] - 1) * 100, 2), "max_drawdown_pct": round(worst, 2)}


def alignment(side: str, reading: Optional[Dict[str, Any]]) -> str:
    """
    Did the trade go with Sigmalytic's confirmed setup on that date?
    BUY goes with a confirmed Long setup, SELL with a confirmed Short setup.
    """
    if not reading or not reading.get("sequence_confirmed"):
        return "no confirmed setup"
    long_side = reading.get("setup_side") == "Long"
    if side == "BUY":
        return "with the setup" if long_side else "against the setup"
    return "with the setup" if not long_side else "against the setup"


def point_in_time_readings(trades: List[Dict[str, Any]], limit: int = 60) -> Dict[Tuple[str, str], Optional[Dict[str, Any]]]:
    """
    Sigmalytic reading of each (symbol, trade date) using only bars up to that
    date, so there is no hindsight. Works on the most recent `limit` trades.
    """
    import pandas as pd
    global _last_reasons, _last_fetch_error
    reasons: Dict[Tuple[str, str], str] = {}
    _last_reasons, _last_fetch_error = reasons, None

    def _key(t: Dict[str, Any]) -> Tuple[str, str]:
        return (str(t.get("symbol", "")).upper(), str(t.get("date")))

    try:
        try:
            from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
            from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
            from backend.setup_grade import compute_setup_grade as _compute_setup_grade
        except ImportError:
            from research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
            from research_engine.weis_verdict_engine import WeisVerdictEngine
            from setup_grade import compute_setup_grade as _compute_setup_grade
    except Exception as exc:  # engines unavailable: the review just shows "not read"
        log.warning("point-in-time engines unavailable: %s", exc)
        msg = f"Sigmalytic's analysis engines could not be loaded on the server ({type(exc).__name__}: {str(exc)[:80]})."
        for t in trades:
            reasons[_key(t)] = msg
        print(f"[BROKER_READ] 0 of {len(trades)} trades read: {msg}", flush=True)
        return {}

    dated = []
    for t in trades:
        d = parse_date(t.get("date"))
        if d:
            dated.append((d, t))
        else:
            reasons[_key(t)] = f"The date '{str(t.get('date'))[:30]}' was not recognized."
    dated.sort(key=lambda x: x[0])
    dated = dated[-limit:]
    if not dated:
        print(f"[BROKER_READ] 0 of {len(trades)} trades read: no trade had a recognizable date.", flush=True)
        return {}

    symbols = sorted({str(t["symbol"]).upper() for _, t in dated})
    start = dated[0][0] - timedelta(days=WARMUP_DAYS)
    end = min(dated[-1][0] + timedelta(days=1), datetime.now(timezone.utc).replace(tzinfo=None))
    bars = fetch_daily_bars(symbols, start, end)
    fetch_error = _last_fetch_error

    wy, we = WyckoffVerdictEngine(), WeisVerdictEngine()
    out: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}
    for when, t in dated:
        sym = str(t["symbol"]).upper()
        key = (sym, str(t.get("date")))
        if key in out:
            continue
        cutoff = when.strftime("%Y-%m-%d")
        rows = [b for b in bars.get(sym, []) if str(b.get("t", ""))[:10] <= cutoff]
        if len(rows) < MIN_BARS_FOR_READING:
            if not bars.get(sym):
                reasons[key] = fetch_error or f"No daily price history was returned for {sym}."
            else:
                reasons[key] = (f"Only {len(rows)} daily bars of {sym} exist up to this date; "
                                f"{MIN_BARS_FOR_READING} are needed.")
            out[key] = None
            continue
        try:
            df = pd.DataFrame(rows).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
            wv = wy.evaluate_bars(df, symbol=sym)
            wsv = we.evaluate(df, symbol=sym)
            grade = _compute_setup_grade(wv, wsv)
            out[key] = {
                "as_of": cutoff,
                "wyckoff_verdict": wv.get("verdict"),
                "wyckoff_phase": wv.get("phase"),
                "setup_grade": grade["setup_grade"],
                "setup_side": grade["setup_side"],
                "sequence_confirmed": bool(grade["setup_sweep_confirmed"] and grade["setup_exhaustion_confirmed"]
                                           and grade["setup_reclaim_confirmed"]),
                "reason": grade["setup_grade_reason"],
            }
        except Exception as exc:
            log.warning("reading failed %s %s: %s", sym, cutoff, exc)
            reasons[key] = f"The analysis failed for {sym} on this date ({type(exc).__name__})."
            out[key] = None
    read = sum(1 for v in out.values() if v)
    top = Counter(reasons.values()).most_common(1)
    print(f"[BROKER_READ] {read} of {len(out)} trades read" + (f"; most common reason: {top[0][0]}" if top else ""),
          flush=True)
    return out
