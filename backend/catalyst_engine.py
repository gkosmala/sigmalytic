# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
Multi-Catalyst Alignment Engine (Admin only).

For any U.S.-listed symbol, builds a quarter-by-quarter table of:
  * the earnings reaction (earnings dates and before/after-market timing come from SEC EDGAR 8-K Item 2.02 filings),
  * an optional pre-announcement (e.g. "deliveries" for TSLA), found by keyword in Alpaca news on the
    biggest-move days between two earnings reports,
  * the biggest pre-earnings catalyst day in that window, matched to Alpaca news headlines and 8-K filings,
  * the run-up between prints and the 5-day follow-through after the print.

Every move is close-to-close on the first trading day that could react, both raw and market-adjusted (minus SPY).
Nothing here trades or posts; it is research output only.
"""
from __future__ import annotations

import logging
import os
import statistics
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("catalyst_engine")

ET = ZoneInfo("America/New_York")
ALPACA_BASE = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
# SEC asks every automated client to identify itself with a name and a contact email.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT") or "Sigmalytic Quant Corporation research sigmalyticquantcorp.com"
BENCHMARK = "SPY"
CANDIDATE_DAYS = 6          # biggest-move days per window that get a news lookup
SIGMA_LOOKBACK = 60         # trading days used for the "normal day" size
CACHE_TTL = 6 * 3600
OPEN_T, CLOSE_T = dtime(9, 30), dtime(16, 0)

ITEM_LABELS = {
    "1.01": "Material agreement", "1.02": "Agreement terminated", "2.01": "Acquisition or sale completed",
    "2.02": "Earnings results", "2.03": "New financial obligation", "2.05": "Restructuring / exit costs",
    "2.06": "Impairment", "3.02": "Unregistered share sale", "5.02": "Executive or director change",
    "5.07": "Shareholder vote results", "7.01": "Reg FD disclosure", "8.01": "Other material event",
}

_cache: Dict[Tuple[str, int, str], Tuple[float, Dict[str, Any]]] = {}
_cik_map: Dict[str, int] = {}


# ── helpers ──────────────────────────────────────────────────────────────────
def _pct(a: float, b: float) -> Optional[float]:
    return None if not b else (a / b - 1.0) * 100.0


def _sign(v: Optional[float]) -> int:
    return 0 if not v else (1 if v > 0 else -1)


def reaction_index(dates: List[str], when_et: datetime) -> Optional[int]:
    """
    Index of the first trading day whose close can reflect news released at `when_et` (Eastern time).
    After the 4:00 PM close -> next trading day. Before the open or during the session -> that day,
    rolled forward to the next trading day when the date is a weekend or holiday.
    """
    d = when_et.date().isoformat()
    i = bisect_right(dates, d) if when_et.time() >= CLOSE_T else bisect_left(dates, d)
    return i if 0 < i < len(dates) else None


def timing_label(when_et: datetime) -> str:
    t = when_et.time()
    return "after close" if t >= CLOSE_T else ("before open" if t < OPEN_T else "during session")


# ── SEC EDGAR ────────────────────────────────────────────────────────────────
def _sec_get(url: str) -> Any:
    r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}, timeout=25)
    if r.status_code == 403:
        raise ValueError("SEC EDGAR refused the request (HTTP 403). Set the SEC_USER_AGENT environment variable "
                         "on the backend to a name plus a contact email, e.g. \"Sigmalytic Quant Corporation you@example.com\".")
    r.raise_for_status()
    return r.json()


def cik_for(symbol: str) -> int:
    if not _cik_map:
        data = _sec_get("https://www.sec.gov/files/company_tickers.json")
        for row in (data or {}).values():
            _cik_map[str(row.get("ticker", "")).upper()] = int(row.get("cik_str"))
    key = symbol.upper().replace(".", "-")
    if key not in _cik_map:
        raise ValueError(f"{symbol} is not in SEC EDGAR's ticker list. The engine covers U.S. SEC filers only "
                         f"(foreign companies that file 6-K reports and ETFs are not supported).")
    return _cik_map[key]


def _rows_from_block(block: Dict[str, Any], cik: int) -> List[Dict[str, Any]]:
    out = []
    forms = block.get("form") or []
    for i, form in enumerate(forms):
        acc_time = (block.get("acceptanceDateTime") or [""] * len(forms))[i]
        try:
            # EDGAR acceptance times are Eastern time even though the string ends in "Z".
            accepted = datetime.strptime(acc_time[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ET)
        except (TypeError, ValueError):
            continue
        acc = (block.get("accessionNumber") or [""] * len(forms))[i]
        doc = (block.get("primaryDocument") or [""] * len(forms))[i]
        items = [x.strip() for x in str((block.get("items") or [""] * len(forms))[i] or "").split(",") if x.strip()]
        out.append({"form": form, "items": items, "accepted": accepted,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
    return out


def sec_8k_filings(symbol: str, since: datetime) -> List[Dict[str, Any]]:
    """Original 8-K filings (no amendments) accepted on or after `since`, oldest first."""
    cik = cik_for(symbol)
    sub = _sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    rows = _rows_from_block((sub.get("filings") or {}).get("recent") or {}, cik)
    for f in (sub.get("filings") or {}).get("files") or []:
        if str(f.get("filingTo", "")) >= since.date().isoformat():
            rows += _rows_from_block(_sec_get(f"https://data.sec.gov/submissions/{f['name']}"), cik)
    since_et = since.astimezone(ET)
    return sorted((r for r in rows if r["form"] == "8-K" and r["accepted"] >= since_et), key=lambda r: r["accepted"])


def earnings_events(filings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """8-K Item 2.02 filings, one per print (a second 2.02 within 7 days is treated as the same print)."""
    out: List[Dict[str, Any]] = []
    for f in filings:
        if "2.02" not in f["items"]:
            continue
        if out and f["accepted"] - out[-1]["accepted"] < timedelta(days=7):
            continue
        out.append(f)
    return out


# ── Alpaca ───────────────────────────────────────────────────────────────────
def _alpaca_headers() -> Dict[str, str]:
    from backend import broker_market_data as bmd
    return bmd._headers()


def fetch_bars(symbols: List[str], years: int) -> Dict[str, List[dict]]:
    from backend import broker_market_data as bmd
    end = datetime.now(timezone.utc)
    return bmd.fetch_daily_bars(symbols, end - timedelta(days=int(365.25 * years) + 120), end)


def fetch_news(symbol: str, start: datetime, end: datetime, pages: int = 2) -> List[Dict[str, Any]]:
    """Alpaca (Benzinga) headlines tagged with `symbol` between two UTC times. Never raises."""
    out: List[Dict[str, Any]] = []
    token = None
    for _ in range(pages):
        params = {"symbols": symbol, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": "50", "sort": "desc",
                  "include_content": "false"}
        if token:
            params["page_token"] = token
        try:
            r = requests.get(f"{ALPACA_BASE}/v1beta1/news", headers=_alpaca_headers(), params=params, timeout=20)
            if r.status_code != 200:
                log.warning("news %s: %s", r.status_code, r.text[:160])
                break
            body = r.json()
        except Exception as exc:  # network problems must never break the report
            log.warning("news request failed: %s", exc)
            break
        out += body.get("news") or []
        token = body.get("next_page_token")
        if not token:
            break
    return out


def _day_bounds_utc(dates: List[str], i: int) -> Tuple[datetime, datetime]:
    """News that could move day i's close: from the prior session's 4 PM close to day i's 4 PM close."""
    start = datetime.combine(datetime.fromisoformat(dates[i - 1]).date(), CLOSE_T, ET)
    end = datetime.combine(datetime.fromisoformat(dates[i]).date(), CLOSE_T, ET)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _best_headlines(news: List[Dict[str, Any]], n: int = 3) -> List[Dict[str, str]]:
    # Company-specific stories first: fewer tagged symbols means less likely to be a market recap.
    ranked = sorted(news, key=lambda x: (len(x.get("symbols") or []), str(x.get("created_at", ""))))
    return [{"headline": str(x.get("headline", "")).strip(), "url": x.get("url") or "", "source": x.get("source") or "",
             "created_at": str(x.get("created_at", ""))[:16].replace("T", " ")} for x in ranked[:n] if x.get("headline")]


# ── engine ───────────────────────────────────────────────────────────────────
def analyze(symbol: str, bars: List[dict], bench: List[dict], filings: List[Dict[str, Any]],
            news_lookup, keyword: str = "") -> Dict[str, Any]:
    """Pure computation, so it can be tested without the network. `news_lookup(i)` returns headlines for bar i."""
    bars = sorted(bars, key=lambda b: str(b["t"]))
    dates = [str(b["t"])[:10] for b in bars]
    close = [float(b["c"]) for b in bars]
    n = len(dates)
    if n < SIGMA_LOOKBACK + 20:
        raise ValueError(f"Not enough price history for {symbol} ({n} daily bars).")
    bclose = {str(b["t"])[:10]: float(b["c"]) for b in bench}
    bdates = sorted(bclose)

    ret = [None] + [_pct(close[i], close[i - 1]) for i in range(1, n)]
    abn: List[Optional[float]] = [None] * n
    for i in range(1, n):
        prev_b = bdates[bisect_left(bdates, dates[i]) - 1] if bisect_left(bdates, dates[i]) > 0 else None
        if dates[i] in bclose and prev_b:
            abn[i] = ret[i] - _pct(bclose[dates[i]], bclose[prev_b])
        else:
            abn[i] = ret[i]

    events = []
    for f in earnings_events(filings):
        r = reaction_index(dates, f["accepted"])
        if r is not None and (not events or r > events[-1][0]):
            events.append((r, f))

    kw = keyword.strip().lower()
    item_filings = [(reaction_index(dates, f["accepted"]), f) for f in filings if "2.02" not in f["items"]]

    # First pass: windows and candidate days (news is looked up in bulk afterwards).
    plans = []
    for k in range(1, len(events)):
        p, _ = events[k - 1]
        r, f = events[k]
        window = list(range(p + 1, r))
        if len(window) < 3:
            continue
        cands = sorted(window, key=lambda i: abs(abn[i] or 0), reverse=True)[:CANDIDATE_DAYS]
        plans.append((p, r, f, window, cands))

    need = sorted({i for *_, cands in plans for i in cands})
    news = news_lookup(need) if need else {}

    rows = []
    for p, r, f, window, cands in plans:
        sig_slice = [abn[i] for i in range(max(1, r - SIGMA_LOOKBACK), r) if abn[i] is not None]
        sigma = statistics.pstdev(sig_slice) if len(sig_slice) > 10 else None

        pre = None
        if kw:
            hits = [i for i in cands if any(kw in str(x.get("headline", "")).lower() for x in news.get(i, []))]
            if hits:
                i = max(hits, key=lambda j: abs(abn[j] or 0))
                match = [x for x in news.get(i, []) if kw in str(x.get("headline", "")).lower()]
                pre = {"date": dates[i], "move": ret[i], "abn": abn[i], "headlines": _best_headlines(match, 2)}

        cat_i = next((i for i in cands if not pre or dates[i] != pre["date"]), None)
        catalyst = None
        if cat_i is not None:
            heads = _best_headlines(news.get(cat_i, []))
            docs = [{"label": ", ".join(ITEM_LABELS.get(it, f"Item {it}") for it in ff["items"] if it != "9.01")
                     or "8-K filing", "url": ff["url"]} for ri, ff in item_filings if ri == cat_i]
            catalyst = {"date": dates[cat_i], "move": ret[cat_i], "abn": abn[cat_i], "headlines": heads,
                        "filings": docs, "explained": bool(heads or docs)}

        runup = _pct(close[r - 1], close[p])
        lead_src = "pre-announcement" if pre else "run-up"
        lead = pre["move"] if pre else runup
        earn = ret[r]
        status = "Pending" if earn is None else ("Reversal" if _sign(lead) * _sign(earn) == -1 else "Aligned")
        post5 = _pct(close[r + 5], close[r]) if r + 5 < n else None
        rows.append({
            "release": f["accepted"].strftime("%Y-%m-%d %H:%M ET"), "timing": timing_label(f["accepted"]),
            "filing_url": f["url"], "reaction_date": dates[r], "earn_move": earn, "earn_abn": abn[r],
            "sigma_mult": (abs(abn[r]) / sigma) if sigma and abn[r] is not None else None,
            "runup": runup, "window_start": dates[p + 1], "window_end": dates[r - 1],
            "pre": pre, "catalyst": catalyst, "lead_source": lead_src, "lead_move": lead,
            "status": status, "post5": post5,
        })
    rows.reverse()  # newest first

    def avg_abs(vals):
        vals = [abs(v) for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    decided = [x for x in rows if x["status"] != "Pending"]
    follow = [x for x in rows if x["post5"] is not None and x["earn_move"]]
    summary = {
        "quarters": len(rows),
        "avg_abs_earn": avg_abs(x["earn_move"] for x in rows),
        "avg_abs_earn_abn": avg_abs(x["earn_abn"] for x in rows),
        "avg_sigma_mult": avg_abs(x["sigma_mult"] for x in rows),
        "avg_abs_catalyst": avg_abs(x["catalyst"]["move"] for x in rows if x["catalyst"]),
        "catalysts_explained": sum(1 for x in rows if x["catalyst"] and x["catalyst"]["explained"]),
        "avg_abs_pre": avg_abs(x["pre"]["move"] for x in rows if x["pre"]),
        "pre_found": sum(1 for x in rows if x["pre"]),
        "avg_abs_runup": avg_abs(x["runup"] for x in rows),
        "reversal_rate": (100.0 * sum(1 for x in decided if x["status"] == "Reversal") / len(decided)) if decided else None,
        "follow_through_rate": (100.0 * sum(1 for x in follow if _sign(x["post5"]) == _sign(x["earn_move"]))
                                / len(follow)) if follow else None,
    }
    return {"symbol": symbol, "keyword": keyword.strip(), "rows": rows, "summary": summary,
            "price_through": dates[-1], "generated": datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")}


def build(symbol: str, years: int = 4, keyword: str = "") -> Dict[str, Any]:
    symbol = symbol.strip().upper()
    years = max(2, min(int(years or 4), 8))
    key = (symbol, years, keyword.strip().lower())
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return {**hit[1], "cached": True}

    bars_map = fetch_bars([symbol, BENCHMARK], years)
    bars = bars_map.get(symbol) or []
    if not bars:
        raise ValueError(f"Alpaca returned no daily price history for {symbol}.")
    first = datetime.fromisoformat(str(bars[0]["t"])[:10]).replace(tzinfo=timezone.utc)
    filings = sec_8k_filings(symbol, first)
    if not earnings_events(filings):
        raise ValueError(f"No 8-K earnings filings (Item 2.02) found for {symbol} in SEC EDGAR for this period.")

    dates = [str(b["t"])[:10] for b in sorted(bars, key=lambda b: str(b["t"]))]

    def lookup(idxs: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        def one(i):
            s, e = _day_bounds_utc(dates, i)
            return i, fetch_news(symbol, s, e)
        with ThreadPoolExecutor(max_workers=6) as pool:
            return dict(pool.map(one, idxs))

    out = analyze(symbol, bars, bars_map.get(BENCHMARK) or [], filings, lookup, keyword)
    out["years"] = years
    out["notes"] = [
        "Earnings dates and timing come from the SEC acceptance time of each 8-K Item 2.02 filing. Companies that "
        "publish results well before filing the 8-K can show a later reaction day than the market actually traded.",
        "Moves are close-to-close on the first trading day that could react. \"vs SPY\" subtracts SPY's move that day.",
        "σ multiple = market-adjusted earnings move divided by the stock's typical daily move over the prior 60 trading days.",
        "Catalyst = the biggest market-adjusted move between two earnings reactions. Headlines are Alpaca (Benzinga) "
        "stories tagged with the symbol from the prior 4 PM close to that day's close; 8-K filings are listed when "
        "they landed on that day. \"Unexplained\" means neither was found.",
        ("Pre-announcement = the biggest-move day in the window whose headlines contain \"" + keyword.strip() + "\". "
         "Alignment compares it with the earnings move.") if keyword.strip() else
        "No pre-announcement keyword was given, so alignment compares the run-up between prints with the earnings move.",
        "Follow-through = the 5 trading days after the reaction day moved in the same direction as the reaction.",
    ]
    _cache[key] = (time.time(), out)
    return out
