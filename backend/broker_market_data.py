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


def parse_date(text: Any) -> Optional[datetime]:
    s = str(text or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def fetch_daily_bars(symbols: List[str], start: datetime, end: datetime) -> Dict[str, List[dict]]:
    """Daily bars (split-adjusted) for each symbol between start and end."""
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
                    break
                body = r.json()
            except Exception as exc:  # network: never fatal
                log.warning("bars request failed: %s", exc)
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
        return {}

    dated = []
    for t in trades:
        d = parse_date(t.get("date"))
        if d:
            dated.append((d, t))
    dated.sort(key=lambda x: x[0])
    dated = dated[-limit:]
    if not dated:
        return {}

    symbols = sorted({str(t["symbol"]).upper() for _, t in dated})
    start = dated[0][0] - timedelta(days=WARMUP_DAYS)
    end = min(dated[-1][0] + timedelta(days=1), datetime.now(timezone.utc).replace(tzinfo=None))
    bars = fetch_daily_bars(symbols, start, end)

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
            out[key] = None
    return out
