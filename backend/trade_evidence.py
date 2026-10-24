# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
Measured evidence for Content Hub's three private trading ideas, from Alpaca data instead of web search.

  A  Institutional accumulation   <- the last complete session's tape (Alpaca SIP trades): large prints, which side
                                     they traded on (tick rule), and the off-exchange share of volume.
  B  Distribution / selling       <- 15-minute bars for the last two complete sessions (volume on down bars) and the
                                     last five daily bars (volume-weighted close location).
  C  Volatility squeeze           <- daily bars (Bollinger Bands inside Keltner Channels, band-width percentile,
                                     ATR contraction) plus the platform's gamma flip and option walls.

Every verdict is computed by fixed rules below, so it is the same with or without an AI key, and nothing here is
published. Every function that touches the network fails soft: a missing input becomes "not assessed", never an error.
"""
from __future__ import annotations

import logging
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("trade_evidence")
ET = ZoneInfo("America/New_York")

# Large print: at least this many shares, or this much money, in one trade.
LARGE_SHARES = int(os.getenv("EVIDENCE_LARGE_SHARES", "10000") or 10000)
LARGE_NOTIONAL = float(os.getenv("EVIDENCE_LARGE_NOTIONAL", "1000000") or 1_000_000)
# Tape pages (10,000 trades each) per run. Keeps one run from using up the shared Alpaca rate limit.
MAX_PAGES = int(os.getenv("EVIDENCE_MAX_TRADE_PAGES", "80") or 80)
TAPE_WINDOWS = 13          # the regular session split into 30-minute slices, fetched in parallel
TAPE_THREADS = 4
OFF_EXCHANGE = "D"         # FINRA ADF/TRF: trades reported off-exchange (dark pools and wholesalers)
# Trades whose price is not a current market price (average-price, derivatively priced, out of sequence, extended
# hours, contingent); they count toward volume and size but are not given a buy or sell side.
NO_SIDE = {"W", "4", "7", "Z", "U", "T", "9", "V"}

RULES = {
    "A": "Supported when large prints are at least 3% of session volume, at least half of their volume could be given "
         "a side, net large-print buying is at least +25% of that, and price is above its 50-day average.",
    "B": "Supported when at least 60% of the last two sessions' 15-minute volume traded on down bars and the last five "
         "sessions' volume-weighted close location is -0.20 or lower (closes near the lows on volume).",
    "C": "Supported when the daily Bollinger Bands (20, 2) sit inside the Keltner Channels (20, 1.5 ATR), or the band "
         "width is in the narrowest 10% of the last 120 sessions. Price below the gamma flip is noted as amplifying.",
}
SOURCE_NOTE = ("Measured from Alpaca data by fixed rules: the full SIP tape of the last complete session (idea A), "
               "15-minute and daily bars (B), daily bars plus the platform's option levels (C). Off-exchange prints "
               "include wholesaler retail fills as well as dark pools, and the tick rule estimates the trade side, so "
               "idea A is evidence, not proof, of institutional intent.")


# ───────────────────────────── pure calculations ─────────────────────────────
def _sma(xs: List[float], n: int) -> Optional[float]:
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _true_ranges(h: List[float], l: List[float], c: List[float]) -> List[float]:
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def squeeze_evidence(bars: List[List[Any]], f: Dict[str, Any]) -> Dict[str, Any]:
    """bars: [[date, open, high, low, close, volume], ...] oldest first (Content Hub's chart bars)."""
    rows = [b for b in bars if all(isinstance(x, (int, float)) for x in b[2:5])]
    if len(rows) < 140:
        return {"assessed": False, "reason": f"needs 140 daily bars, have {len(rows)}"}
    h, l, c = [float(b[2]) for b in rows], [float(b[3]) for b in rows], [float(b[4]) for b in rows]
    tr = _true_ranges(h, l, c)

    def width_at(end: int) -> float:
        w = c[end - 20:end]
        m = sum(w) / 20
        return 4 * statistics.pstdev(w) / m        # (upper - lower) / middle

    widths = [width_at(e) for e in range(len(c) - 119, len(c) + 1)]
    pct_rank = 100.0 * sum(1 for w in widths if w <= widths[-1]) / len(widths)
    mid, sd = sum(c[-20:]) / 20, statistics.pstdev(c[-20:])
    atr20 = sum(tr[-20:]) / 20
    inside = (mid + 2 * sd) < (mid + 1.5 * atr20) and (mid - 2 * sd) > (mid - 1.5 * atr20)
    atr14, atr60 = sum(tr[-14:]) / 14, sum(tr[-60:]) / 60
    last, flip = c[-1], f.get("gamma_flip")
    out = {
        "assessed": True,
        "bands_inside_keltner": inside,
        "band_width_pct": round(100 * widths[-1], 2),
        "band_width_percentile_120d": round(pct_rank, 1),
        "atr14_vs_atr60": round(atr14 / atr60, 2) if atr60 else None,
        "below_gamma_flip": (last < flip) if isinstance(flip, (int, float)) else None,
        "call_wall": f.get("call_wall"), "put_wall": f.get("put_wall"), "gamma_flip": flip,
    }
    out["supported"] = bool(inside or pct_rank <= 10)
    return out


def selling_evidence(intraday: List[Dict[str, Any]], bars: List[List[Any]]) -> Dict[str, Any]:
    """intraday: Alpaca 15-minute bars (regular session only) for the last two complete sessions."""
    out: Dict[str, Any] = {"assessed": False}
    if intraday:
        down = sum(float(b["v"]) for b in intraday if float(b["c"]) < float(b["o"]))
        up = sum(float(b["v"]) for b in intraday if float(b["c"]) > float(b["o"]))
        if down + up > 0:
            out["down_volume_share"] = round(down / (down + up), 3)
    rows = [b for b in bars[-5:] if all(isinstance(x, (int, float)) for x in b[2:6])]
    if len(rows) == 5:
        num = sum(((2 * b[4] - b[2] - b[3]) / (b[2] - b[3])) * b[5] for b in rows if b[2] > b[3])
        den = sum(b[5] for b in rows if b[2] > b[3])
        if den:
            out["close_location_5d"] = round(num / den, 3)
    if "down_volume_share" in out and "close_location_5d" in out:
        out["assessed"] = True
        out["supported"] = out["down_volume_share"] >= 0.60 and out["close_location_5d"] <= -0.20
    else:
        out["reason"] = "intraday or daily bars unavailable"
    return out


class TapeStats:
    """Running totals over a session's trades, so a million-trade tape never sits in memory."""

    def __init__(self) -> None:
        self.trades = self.volume = self.off_volume = 0
        self.large_trades = self.large_volume = self.large_buy = self.large_sell = 0
        self.large_off_volume = 0

    def add(self, trades: Iterable[Dict[str, Any]], last_price: Optional[float]) -> Optional[float]:
        """Adds trades (oldest first) and returns the last priced trade, for the next page's tick rule."""
        for t in trades:
            p, s = float(t.get("p") or 0), int(t.get("s") or 0)
            if p <= 0 or s <= 0:
                continue
            conds = set(t.get("c") or [])
            off = t.get("x") == OFF_EXCHANGE
            self.trades += 1
            self.volume += s
            self.off_volume += s if off else 0
            priced = not (conds & NO_SIDE)
            side = 0
            if priced and last_price is not None:
                side = 1 if p > last_price else (-1 if p < last_price else 0)
            if s >= LARGE_SHARES or p * s >= LARGE_NOTIONAL:
                self.large_trades += 1
                self.large_volume += s
                self.large_off_volume += s if off else 0
                if side > 0:
                    self.large_buy += s
                elif side < 0:
                    self.large_sell += s
            if priced:
                last_price = p
        return last_price

    def merge(self, other: "TapeStats") -> None:
        for k, v in vars(other).items():
            setattr(self, k, getattr(self, k) + v)


def institutional_evidence(stats: Optional[TapeStats], f: Dict[str, Any], session: str, complete: bool) -> Dict[str, Any]:
    if not stats or not stats.volume:
        return {"assessed": False, "reason": "tape unavailable"}
    classified = stats.large_buy + stats.large_sell
    net = (stats.large_buy - stats.large_sell) / classified if classified else None
    above50 = (f.get("vs_sma50_pct") or 0) > 0 if f.get("vs_sma50_pct") is not None else None
    out = {
        "assessed": True, "session": session, "tape_complete": complete,
        "trades": stats.trades, "volume": stats.volume,
        "off_exchange_share": round(stats.off_volume / stats.volume, 3),
        "large_prints": stats.large_trades,
        "large_print_volume_share": round(stats.large_volume / stats.volume, 4),
        "large_print_off_exchange_share": round(stats.large_off_volume / stats.large_volume, 3) if stats.large_volume else None,
        "large_print_side_classified": round(classified / stats.large_volume, 3) if stats.large_volume else None,
        "large_print_net_buying": round(net, 3) if net is not None else None,
        "above_50d_average": above50,
    }
    out["supported"] = bool(out["large_print_volume_share"] >= 0.03 and (out["large_print_side_classified"] or 0) >= 0.5
                            and net is not None and net >= 0.25 and above50)
    return out


# ───────────────────────────── Alpaca fetches ─────────────────────────────
def last_complete_sessions(bars: List[List[Any]], f: Dict[str, Any], n: int) -> List[str]:
    """The newest n daily-bar dates whose session is over (drops today's bar while the market is open)."""
    dates = [str(b[0])[:10] for b in bars]
    if (f.get("session") or {}).get("live") and dates:
        dates = dates[:-1]
    return dates[-n:]


def _session_bounds(day: str) -> Tuple[datetime, datetime]:
    d = date.fromisoformat(day)
    return datetime.combine(d, dtime(9, 30), ET), datetime.combine(d, dtime(16, 0), ET)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_tape(symbol: str, day: str, max_pages: int = MAX_PAGES) -> Tuple[Optional[TapeStats], bool]:
    """Aggregates the regular-session SIP tape for one day. Returns (stats, complete)."""
    from backend import broker_market_data as bmd
    start, end = _session_bounds(day)
    step = (end - start) / TAPE_WINDOWS
    per_window = max(1, max_pages // TAPE_WINDOWS)

    def window(k: int) -> Tuple[TapeStats, bool, bool]:
        st, last, token, pages = TapeStats(), None, None, 0
        w0, w1 = start + step * k, start + step * (k + 1)
        while pages < per_window:
            params = {"start": _utc(w0), "end": _utc(w1), "limit": "10000", "feed": bmd.FEED, "sort": "asc"}
            if token:
                params["page_token"] = token
            try:
                r = requests.get(f"{bmd.BASE}/v2/stocks/{symbol}/trades", headers=bmd._headers(), params=params, timeout=25)
                if r.status_code == 429:
                    time.sleep(float(r.headers.get("Retry-After", 2) or 2))
                    continue
                if r.status_code != 200:
                    log.warning("trades %s %s: %s", symbol, r.status_code, r.text[:160])
                    return st, False, False
                body = r.json()
            except Exception as exc:
                log.warning("trades request failed: %s", exc)
                return st, False, False
            last = st.add(body.get("trades") or [], last)
            pages += 1
            token = body.get("next_page_token")
            if not token:
                return st, True, True
        return st, True, False

    total, complete, any_ok = TapeStats(), True, False
    with ThreadPoolExecutor(max_workers=TAPE_THREADS) as pool:
        for st, ok, done in pool.map(window, range(TAPE_WINDOWS)):
            total.merge(st)
            any_ok = any_ok or ok
            complete = complete and done
    return (total if any_ok and total.volume else None), complete


def fetch_intraday(symbol: str, days: List[str]) -> List[Dict[str, Any]]:
    from backend import broker_market_data as bmd
    if not days:
        return []
    s, _ = _session_bounds(days[0])
    _, e = _session_bounds(days[-1])
    rows = bmd.fetch_daily_bars([symbol], s.astimezone(timezone.utc), e.astimezone(timezone.utc), "15Min").get(symbol) or []
    keep = []
    for b in rows:
        t = datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00")).astimezone(ET)
        if t.date().isoformat() in days and dtime(9, 30) <= t.time() < dtime(16, 0):
            keep.append(b)
    return keep


# ───────────────────────────── verdicts ─────────────────────────────
def _pct(v: Optional[float], d: int = 1) -> str:
    return "n/a" if v is None else f"{100 * v:.{d}f}%"


def private_from_evidence(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Content Hub's private A/B/C block, with plain-language reasoning built from the measurements."""
    a, b, c = ev.get("institutional") or {}, ev.get("selling") or {}, ev.get("squeeze") or {}
    out: Dict[str, Any] = {}
    if a.get("assessed"):
        net = a.get("large_print_net_buying")
        txt = (f"Session {a['session']}{'' if a.get('tape_complete') else ' (partial tape)'}: {a['large_prints']:,} large "
               f"prints were {_pct(a['large_print_volume_share'], 2)} of volume, net buying {_pct(net)} of the "
               f"{_pct(a.get('large_print_side_classified'))} given a side; off-exchange share {_pct(a['off_exchange_share'])}; "
               f"price {'above' if a.get('above_50d_average') else 'not above'} its 50-day average.")
    else:
        txt = f"Not assessed: {a.get('reason', 'tape unavailable')}."
    out["A"] = {"supported": bool(a.get("supported")), "reasoning": txt}
    if b.get("assessed"):
        txt = (f"{_pct(b['down_volume_share'])} of the last two sessions' 15-minute volume traded on down bars; five-day "
               f"volume-weighted close location {b['close_location_5d']:+.2f} (-1 = closes at the lows).")
    else:
        txt = f"Not assessed: {b.get('reason', 'bars unavailable')}."
    out["B"] = {"supported": bool(b.get("supported")), "reasoning": txt}
    if c.get("assessed"):
        flip = c.get("below_gamma_flip")
        txt = (f"Bollinger Bands {'inside' if c['bands_inside_keltner'] else 'outside'} the Keltner Channels; band width "
               f"{c['band_width_pct']:.2f}% ({c['band_width_percentile_120d']:.0f}th percentile of 120 sessions); 14-day ATR "
               f"{c['atr14_vs_atr60']}x the 60-day ATR"
               + ("" if flip is None else f"; price {'below' if flip else 'above'} the gamma flip"
                  + (" (dealer hedging tends to amplify moves)" if flip else "")) + ".")
    else:
        txt = f"Not assessed: {c.get('reason', 'bars unavailable')}."
    out["C"] = {"supported": bool(c.get("supported")), "reasoning": txt}
    supported = [k for k in "ABC" if out[k]["supported"]]
    out["selected"] = supported[0] if len(supported) == 1 else ("none" if not supported else "multiple: " + ", ".join(supported))
    out["data_limits"] = SOURCE_NOTE + " Rules: " + " ".join(f"{k}: {v}" for k, v in RULES.items())
    return out


def build(symbol: str, bars: List[List[Any]], f: Dict[str, Any]) -> Dict[str, Any]:
    """All three measurements. Never raises; each part reports its own reason when it cannot be assessed."""
    t0 = time.time()
    ev: Dict[str, Any] = {}
    try:
        ev["squeeze"] = squeeze_evidence(bars, f)
    except Exception as exc:
        ev["squeeze"] = {"assessed": False, "reason": f"{type(exc).__name__}: {str(exc)[:80]}"}
    days = last_complete_sessions(bars, f, 2)
    try:
        ev["selling"] = selling_evidence(fetch_intraday(symbol, days), [b for b in bars if str(b[0])[:10] <= (days[-1] if days else "")])
    except Exception as exc:
        ev["selling"] = {"assessed": False, "reason": f"{type(exc).__name__}: {str(exc)[:80]}"}
    try:
        stats, complete = fetch_tape(symbol, days[-1]) if days else (None, False)
        ev["institutional"] = institutional_evidence(stats, f, days[-1] if days else "", complete)
    except Exception as exc:
        ev["institutional"] = {"assessed": False, "reason": f"{type(exc).__name__}: {str(exc)[:80]}"}
    ev["seconds"] = round(time.time() - t0, 1)
    return ev
