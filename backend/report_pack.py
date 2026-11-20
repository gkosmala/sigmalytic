# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/report_pack.py
----------------------
Top 25 Report Pack (Admin): one public market-structure report for each of the largest U.S. companies by market
capitalization (a sample of 3, or all 25), combined into one PDF with a cover page, contents and each symbol's chart.

How the companies are chosen
    Estimated market cap = shares outstanding (latest SEC filing, dei:EntityCommonStockSharesOutstanding, all share
    classes added together) x latest Alpaca price, for a candidate list of large U.S. companies (REPORT_PACK_CANDIDATES
    overrides it), refreshed once a day. Foreign companies that do not file 10-K/10-Q reports (for example TSM, ASML) are
    not covered. Market-cap figures are shown only in the Admin tab, never in the PDF.

What each report contains, and what it costs
    * Analysis: the Content Hub's template report from the platform's own data (no AI, no cost).
    * News, scanned for free:
        company       SEC 8-K filings (public records) + Alpaca/Benzinga headlines tagged with the symbol
        U.S. economy  FRED (Federal Reserve Bank of St. Louis): CPI, unemployment, fed funds rate, 10-year yield
        international / geopolitical   the open GDELT news index, headlines that name the company (GDELT attribution)
    * News paragraphs: Claude Haiku (REPORT_PACK_NEWS_MODEL) writes 1-3 sentences per category ONLY from the scanned
      items, about a cent or less per report. A paragraph with a number not in its items is replaced by the headline list.
      No AI key, an AI error, or "use_ai" off -> the headlines are listed instead.
    * Public version: levels and facts are relabeled ("ice line" -> "reference line"), every text is scrubbed, and a
      report that still contains "Wyckoff" or "Weis" is blocked from the PDF; method wording is removed from the analysis.
    If the Anthropic account runs out of credit, the pack stops (state "stopped") instead of failing every report;
    finished reports are kept and Generate resumes it.

Running
    A background thread builds the reports (about a minute each) and saves each one to disk (REPORT_PACK_DIR, default
    /tmp/sigmalytic_report_pack/<date>/). If the server restarts its worker mid-run, the next status check resumes from
    the reports already saved.
"""

from __future__ import annotations

import base64
import html as _html
import io
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PACK_DIR = os.getenv("REPORT_PACK_DIR", "/tmp/sigmalytic_report_pack")
PACK_SIZE = 25
WORKERS = max(1, min(4, int(os.getenv("REPORT_PACK_WORKERS", "2") or 2)))
STALE_SECONDS = 300            # a running job with no heartbeat for this long is treated as interrupted and resumed
TOP_TTL = 24 * 3600            # the top-25 list is recomputed at most once a day unless refreshed by hand
SHARES_TTL = 7 * 24 * 3600     # SEC share counts change quarterly; refetched weekly

# Large U.S. SEC filers that could rank in the top 25. Only one share class per company (BRK.B, GOOGL).
DEFAULT_CANDIDATES = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK.B", "LLY", "JPM", "V", "WMT", "ORCL", "MA",
    "XOM", "NFLX", "COST", "JNJ", "PLTR", "HD", "ABBV", "BAC", "PG", "AMD", "UNH", "KO", "GE", "CVX", "CSCO", "IBM",
    "WFC", "MS", "TMUS", "PM", "CRM", "GS", "ABT", "MCD", "LIN", "AXP", "MU", "INTU", "CAT", "NOW", "ISRG", "RTX",
    "PEP", "T", "VZ", "BX", "UBER", "SCHW", "BKNG", "ANET", "QCOM", "TXN", "DIS", "AMAT", "LRCX", "C", "APP",
]

PUBLIC_RULES = (
    " PUBLIC REPORT RULES: never write the words Wyckoff, Weis, ice line, spring or upthrust, and never name or describe "
    "any analysis method, school or indicator system. Do not mention scores, rankings, scans, signal engines, "
    "algorithms, thresholds or how any level is found; call levels by their plain labels (for example 'reference line', "
    "'20-day average', 'support'). The report must not reveal anything proprietary about Sigmalytic's platform."
)

# Hard-blocked words: a report that still contains one after scrubbing is not put in the PDF.
_BLOCKED = re.compile(r"\b(?:wyckoff\w*|weis)\b", re.IGNORECASE)
_REPLACEMENTS = [
    (r"Wyckoff\s*/\s*Weis pattern read", "Price and volume pattern read"),
    (r"Sigmalytic's Wyckoff\s*/\s*Weis scan", "Sigmalytic's pattern review"),
    (r"Wyckoff\s*/\s*Weis scan", "pattern review"),
    (r"Wyckoff\s*(?:/|&|and)\s*Weis", "market structure"),
    (r"\s*\(a Weis horizontal reference level\)", ""),
    (r"(?i)Weis wave volume", "wave volume"), (r"(?i)Weis wave(s?)", r"price wave\1"),
    (r"\bIce lines\b", "Reference lines"), (r"\bice lines\b", "reference lines"),
    (r"\bIce line\b", "Reference line"), (r"\bice line\b", "reference line"),
    (r"\bupthrusts?\b", "bull trap"), (r"\bsprings?\b(?= (?:below|at|near|signal|pattern|level))", "bear trap"),
]
# Method wording removed from the analysis sections (news sections keep their wording).
_METHOD = re.compile(r"\b(?:algorithm\w*|scor(?:e|es|ed|ing)\b|touch count|lookback|tolerance|confluence|"
                     r"calibrat\w*|threshold\w*|signal engine|proprietary (?:model|formula|score))", re.IGNORECASE)

WEBSITE = "https://sigmalyticquantcorp.com/"
EMAIL = "teams@sigmalyticquantcorp.com"
_TM = re.compile(r"Sigmalytic Quant (?:Corporation|AI)(?!™)", re.IGNORECASE)   # also the all-capitals form

_lock = threading.RLock()
_thread: Optional[threading.Thread] = None


# ───────────────────────────── small helpers ─────────────────────────────

def _today() -> str:
    return datetime.now(ET).date().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dir(*parts: str) -> str:
    p = os.path.join(PACK_DIR, *parts)
    os.makedirs(p, exist_ok=True)
    return p


def _read(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _write(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, default=str)
    os.replace(tmp, path)


def _safe(sym: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", sym.upper())


def candidates() -> List[str]:
    raw = os.getenv("REPORT_PACK_CANDIDATES", "")
    syms = [s.strip().upper() for s in raw.split(",") if s.strip()] if raw.strip() else DEFAULT_CANDIDATES
    return list(dict.fromkeys(syms))


# ───────────────────────────── top 25 by market cap ─────────────────────────────

def _latest_quarter(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The most recent figure; for period figures, the shortest (quarterly) one ending on the latest date."""
    rows = [r for r in rows if r.get("val") and r.get("end")]
    if not rows:
        return None
    end = max(r["end"] for r in rows)
    cur = [r for r in rows if r["end"] == end]
    return max(cur, key=lambda r: (str(r.get("start") or ""), str(r.get("filed") or "")))


def _shares_outstanding(symbol: str) -> Dict[str, Any]:
    """Total shares for the market-cap estimate, from SEC EDGAR.
    1) dei:EntityCommonStockSharesOutstanding (cover page, all classes in the latest filing added together);
    2) companies with several share classes (Alphabet, Meta, Palantir, AppLovin ...) report that figure per class, which the
       SEC's API leaves out, so the fallback is us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding, the total for all
       classes for the latest quarter (within a few percent of shares outstanding, which is enough to rank by size)."""
    from backend import catalyst_engine as ce
    cik = ce.cik_for(symbol)
    name = ce._names.get(symbol.upper().replace(".", "-"), "")
    base = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}"
    rows: List[Dict[str, Any]] = []
    try:
        data = ce._sec_get(f"{base}/dei/EntityCommonStockSharesOutstanding.json")
        rows = [r for r in ((data or {}).get("units") or {}).get("shares") or [] if r.get("val") and r.get("end")]
    except Exception:
        rows = []
    if rows:
        end = max(r["end"] for r in rows)
        cur = [r for r in rows if r["end"] == end]
        filed = max(str(r.get("filed") or "") for r in cur)
        vals = sorted({float(r["val"]) for r in cur if str(r.get("filed") or "") == filed}, reverse=True)
        if symbol.upper().startswith("BRK"):
            # Berkshire reports Class A and Class B separately; one Class A share converts into 1,500 Class B shares.
            total = sum(v * 1500 if v < vals[0] / 100 else v for v in vals)
        else:
            total = sum(vals)
        return {"shares": total, "as_of": end, "classes": len(vals), "name": name, "basis": "shares outstanding"}
    data = ce._sec_get(f"{base}/us-gaap/WeightedAverageNumberOfDilutedSharesOutstanding.json")
    best = _latest_quarter(((data or {}).get("units") or {}).get("shares") or [])
    if not best:
        raise ValueError("no share count in SEC filings")
    return {"shares": float(best["val"]), "as_of": best["end"], "classes": 0, "name": name,
            "basis": "diluted weighted average, all classes"}


def _prices(symbols: List[str]) -> Dict[str, float]:
    from backend.radar_service import fetch_snapshots
    out: Dict[str, float] = {}
    for sym, snap in (fetch_snapshots(symbols) or {}).items():
        snap = snap or {}
        p = ((snap.get("latestTrade") or {}).get("p") or (snap.get("dailyBar") or {}).get("c")
             or (snap.get("prevDailyBar") or {}).get("c"))
        if p:
            out[sym.upper()] = float(p)
    return out


def top_list(refresh: bool = False) -> Dict[str, Any]:
    """The 25 largest candidates by estimated market cap, cached for a day."""
    path = os.path.join(_dir(), "top_market_cap.json")
    cached = _read(path)
    if cached and not refresh and time.time() - cached.get("ts", 0) < TOP_TTL:
        return cached
    syms = candidates()
    shares_path = os.path.join(_dir(), "sec_shares.json")
    shares_cache = _read(shares_path) or {}
    shares: Dict[str, Dict[str, Any]] = {}
    skipped: List[Dict[str, str]] = []

    def fetch(sym: str):
        c = shares_cache.get(sym)
        if c and time.time() - c.get("ts", 0) < SHARES_TTL:
            return sym, c, None
        try:
            return sym, {**_shares_outstanding(sym), "ts": time.time()}, None
        except Exception as e:
            return sym, None, str(e)[:160]

    with ThreadPoolExecutor(max_workers=4) as pool:      # SEC allows 10 requests a second; 4 at a time stays well under
        for sym, rec, err in pool.map(fetch, syms):
            if rec:
                shares[sym] = rec
                shares_cache[sym] = rec
            else:
                skipped.append({"symbol": sym, "reason": f"SEC shares: {err}"})
    _write(shares_path, shares_cache)
    prices = _prices(list(shares))
    rows = []
    for sym, rec in shares.items():
        px = prices.get(sym)
        if not px:
            skipped.append({"symbol": sym, "reason": "no Alpaca price"})
            continue
        rows.append({"symbol": sym, "name": rec.get("name") or sym, "price": round(px, 2), "shares": rec["shares"],
                     "shares_as_of": rec["as_of"], "market_cap": rec["shares"] * px})
    rows.sort(key=lambda r: -r["market_cap"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    out = {"ok": True, "ts": time.time(), "computed_at": _now_iso(), "top": rows[:PACK_SIZE], "next": rows[PACK_SIZE:PACK_SIZE + 5],
           "candidates": len(syms), "skipped": skipped,
           "method": "Estimated market cap = shares outstanding from the latest SEC filing (all classes) x latest Alpaca price."}
    _write(path, out)
    return out


# ───────────────────────────── public version of one report ─────────────────────────────

def _rename_keys(x: Any) -> Any:
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            nk = str(k).replace("ice_line", "reference_line").replace("weis", "wave").replace("wyckoff", "structure")
            out[nk] = _rename_keys(v)
        return out
    if isinstance(x, list):
        return [_rename_keys(v) for v in x]
    return x


def scrub(text: Any) -> str:
    t = str(text or "")
    for pat, rep in _REPLACEMENTS:
        t = re.sub(pat, rep, t)
    return t


def _drop_sentences(text: str, pattern: "re.Pattern") -> str:
    paras = []
    for para in str(text).split("\n\n"):
        keep = [s for s in re.split(r"(?<=[.!?])\s+", para) if not pattern.search(s)]
        if keep:
            paras.append(" ".join(keep))
    return "\n\n".join(paras)


def public_facts(f: Dict[str, Any]) -> Dict[str, Any]:
    """Facts the public report may be written from: method-named keys and level labels are renamed."""
    bars = f.pop("_chart_bars", None)
    g = _rename_keys({k: v for k, v in f.items()})
    lv = g.get("levels") or {}
    g["levels"] = {side: [{**x, "label": scrub(x.get("label"))} for x in (lv.get(side) or [])] for side in ("above", "below")}
    if bars is not None:
        g["_chart_bars"] = bars
    return g


# ───────────────────────────── free news scan ─────────────────────────────

NEWS_MODEL = os.getenv("REPORT_PACK_NEWS_MODEL", "claude-haiku-5-5")
NEWS_DAYS = int(os.getenv("REPORT_PACK_NEWS_DAYS", "7") or 7)
FILING_DAYS = int(os.getenv("REPORT_PACK_FILING_DAYS", "21") or 21)
_GDELT_LOCK = threading.Lock()
_GDELT_LAST = [0.0]
_FRED_CACHE: Dict[str, Any] = {}
_GEO_WORDS = re.compile(r"\b(tariff\w*|sanction\w*|war|military|conflict|export (?:ban|control\w*)|geopolit\w*|"
                        r"embargo|invasion|taiwan|ukraine|russia|iran|middle east|national security)\b", re.IGNORECASE)


def _shutting_down(exc: Optional[BaseException] = None) -> bool:
    """True while the server is replacing this worker process (gunicorn restarts it after a set number of requests)."""
    import sys
    return sys.is_finalizing() or (exc is not None and "interpreter shutdown" in str(exc))


class CreditError(RuntimeError):
    """The Anthropic account has no credit left; the pack stops instead of failing every remaining report."""


def _fred_series(series_id: str, limit: int = 14) -> List[Dict[str, Any]]:
    import requests
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        return []
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                     params={"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": limit},
                     timeout=15)
    if not r.ok:
        return []
    return [o for o in (r.json() or {}).get("observations") or [] if o.get("value") not in (None, "", ".")]


def us_economy_items() -> List[Dict[str, Any]]:
    """Latest U.S. economic readings from FRED (Federal Reserve Bank of St. Louis), shared by every report in a run."""
    day = _today()
    if _FRED_CACHE.get("day") == day:
        return _FRED_CACHE["items"]
    items: List[Dict[str, Any]] = []
    try:
        cpi = _fred_series("CPIAUCSL", 14)
        if len(cpi) >= 13:
            yoy = (float(cpi[0]["value"]) / float(cpi[12]["value"]) - 1) * 100
            items.append({"text": f"Consumer prices (CPI) were up {yoy:.1f}% from a year earlier in the "
                                  f"{datetime.strptime(cpi[0]['date'], '%Y-%m-%d').strftime('%B %Y')} reading.",
                          "source": "FRED, U.S. Bureau of Labor Statistics", "date": cpi[0]["date"],
                          "url": "https://fred.stlouisfed.org/series/CPIAUCSL"})
        for sid, label, src in (("UNRATE", "The unemployment rate was {v:.1f}% in {m}.", "FRED, U.S. Bureau of Labor Statistics"),
                                ("FEDFUNDS", "The effective federal funds rate averaged {v:.2f}% in {m}.", "FRED, Federal Reserve"),
                                ("DGS10", "The 10-year Treasury yield was {v:.2f}% on {d}.", "FRED, Federal Reserve")):
            obs = _fred_series(sid, 3)
            if obs:
                dte = datetime.strptime(obs[0]["date"], "%Y-%m-%d")
                items.append({"text": label.format(v=float(obs[0]["value"]), m=dte.strftime("%B %Y"),
                                                   d=dte.strftime("%B %-d, %Y")),
                              "source": src, "date": obs[0]["date"], "url": f"https://fred.stlouisfed.org/series/{sid}"})
    except Exception:
        pass
    _FRED_CACHE.update({"day": day, "items": items})
    return items


def company_items(symbol: str) -> List[Dict[str, Any]]:
    """SEC 8-K filings (public records) and Alpaca/Benzinga headlines tagged with the symbol."""
    from datetime import timedelta
    from backend import catalyst_engine as ce
    out: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    try:
        for fl in reversed(ce.sec_8k_filings(symbol, now - timedelta(days=FILING_DAYS))[-4:]):
            labels = [ce.ITEM_LABELS.get(i, f"Item {i}") for i in fl.get("items") or [] if i not in ("9.01",)]
            out.append({"text": f"SEC Form 8-K filed: {', '.join(labels) or 'current report'}.", "source": "SEC EDGAR",
                        "date": fl["accepted"].strftime("%Y-%m-%d"), "url": fl["url"]})
    except Exception:
        pass
    try:
        news = ce.fetch_news(symbol, now - timedelta(days=NEWS_DAYS), now, pages=1)
        news.sort(key=lambda n: (len(n.get("symbols") or []), -(datetime.fromisoformat(
            str(n.get("created_at", "1970-01-01T00:00:00Z")).replace("Z", "+00:00")).timestamp())))
        for n in news[:8]:
            if n.get("headline") and n.get("url"):
                out.append({"text": str(n["headline"]).strip(), "source": n.get("source", "benzinga").title(),
                            "date": str(n.get("created_at", ""))[:10], "url": n["url"]})
    except Exception:
        pass
    return out


def world_items(symbol: str, name: str) -> Dict[str, List[Dict[str, Any]]]:
    """International and geopolitical coverage that names the company, from the open GDELT index (attribution: GDELT Project)."""
    import requests
    from backend import catalyst_engine as ce
    word = ce.short_name(symbol) or (name.split()[0].strip(",.") if name else symbol)
    q = (f'"{word}" (tariff OR tariffs OR sanctions OR export OR China OR Europe OR regulators OR antitrust OR war) '
         "sourcelang:english")
    with _GDELT_LOCK:                                  # GDELT asks for no more than one request every 5 seconds
        wait = 5.5 - (time.time() - _GDELT_LAST[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
                             params={"query": q, "mode": "ArtList", "format": "json", "maxrecords": "25",
                                     "timespan": f"{NEWS_DAYS}d", "sort": "DateDesc"}, timeout=25)
            arts = (r.json() or {}).get("articles") or [] if r.ok and r.text.strip().startswith("{") else []
            print(f"[report_pack] GDELT {symbol} ({word}): HTTP {r.status_code}, {len(arts)} articles"
                  + ("" if r.ok and r.text.strip().startswith("{") else f", reply: {r.text[:120]!r}"), flush=True)
        except Exception as e:
            print(f"[report_pack] GDELT {symbol} ({word}) failed: {str(e)[:160]}", flush=True)
            arts = []
        _GDELT_LAST[0] = time.time()
    out: Dict[str, List[Dict[str, Any]]] = {"international": [], "geopolitical": []}
    seen = set()
    for a in arts:
        title = str(a.get("title") or "").strip()
        if not title or not a.get("url") or word.lower() not in title.lower() or title.lower() in seen:
            continue
        seen.add(title.lower())
        key = "geopolitical" if _GEO_WORDS.search(title) else "international"
        if len(out[key]) < 6:
            sd = str(a.get("seendate") or "")
            out[key].append({"text": title, "source": str(a.get("domain") or "GDELT"),
                             "date": f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else "", "url": a["url"]})
    return out


def scan_news(symbol: str, name: str) -> Dict[str, List[Dict[str, Any]]]:
    news = {"company": company_items(symbol), "us": us_economy_items()}
    news.update(world_items(symbol, name))
    return news


def _haiku(system: str, user: str, max_tokens: int = 2500) -> Dict[str, Any]:
    import requests
    from backend import content_hub as ch
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": NEWS_MODEL, "max_tokens": max_tokens, "system": system,
                            "messages": [{"role": "user", "content": user}]}, timeout=90)
    if r.status_code >= 400:
        try:
            msg = str((r.json().get("error") or {}).get("message") or r.text[:200])
        except Exception:
            msg = r.text[:200]
        if "credit" in msg.lower() and "balance" in msg.lower():
            raise CreditError("Your Anthropic credit balance is too low. Add credits in the Claude Console "
                              "(Billing page), then press Generate again; finished reports are kept.")
        raise RuntimeError(f"{r.status_code} from Anthropic: {msg}")
    body = r.json()
    u = body.get("usage") or {}
    ch._record_usage("anthropic", body.get("model") or NEWS_MODEL, u.get("input_tokens", 0), u.get("output_tokens", 0))
    text = "".join(b.get("text", "") for b in body.get("content") or [] if b.get("type") == "text")
    return ch._extract_json(text)


def _nums(t: str) -> set:
    return {x.replace(",", "") for x in re.findall(r"\d[\d,]*\.?\d*", t)}


def write_news(symbol: str, news: Dict[str, List[Dict[str, Any]]], use_ai: bool) -> Dict[str, Dict[str, Any]]:
    """One short paragraph per category, written only from the scanned items; falls back to a plain headline list."""
    numbered: Dict[str, Dict[str, Any]] = {}
    lines = []
    for cat in ("company", "us", "international", "geopolitical"):
        for it in news.get(cat) or []:
            iid = f"{cat[0]}{sum(1 for k in numbered if k[0] == cat[0]) + 1}"
            numbered[iid] = {**it, "cat": cat}
            lines.append(f"[{iid}] ({cat}) {it['date']} | {it['source']} | {it['text']}")

    def fallback(cat: str) -> Optional[Dict[str, Any]]:
        its = [(k, v) for k, v in numbered.items() if v["cat"] == cat][:4]
        if not its:
            return None
        return {"text": "\n\n".join(f"{v['text']} ({v['source']}, {v['date']})" for _, v in its),
                "urls": [v["url"] for _, v in its], "written": False}

    out: Dict[str, Dict[str, Any]] = {}
    if not numbered:
        return out
    if use_ai and os.getenv("ANTHROPIC_API_KEY"):
        system = ("You write the news part of a public stock research report. Use ONLY the numbered items supplied; "
                  "never add facts, numbers, opinions or anything from memory. Observations only: never advise, recommend, "
                  "predict or promise. Plain, neutral sentences." + PUBLIC_RULES +
                  " Reply with one JSON object and nothing else.")
        user = (f"Symbol: {symbol}. For each category that has items, write 1-3 sentences (at most 90 words) that say what "
                "the items report and why it may matter to the company or its share price, in neutral terms. Skip items "
                "that are not about this company or its business. Set a category to null if no item supports it. "
                "Return JSON: {\"company\": {\"text\": str, \"ids\": [str]} | null, \"us\": ..., \"international\": ..., "
                "\"geopolitical\": ...} where ids lists the item ids each paragraph is based on.\n\nITEMS:\n" + "\n".join(lines))
        reply = None
        for attempt in range(2):                # an unreadable reply is retried once (costs about a tenth of a cent)
            try:
                reply = _haiku(system, user if attempt == 0 else
                               user + "\n\nYour previous reply could not be read. Reply with the JSON object only.")
                break
            except CreditError:
                raise
            except Exception as e:
                reply = {"_error": str(e)[:160]}
                if "JSON" not in str(e):
                    break
        for cat in ("company", "us", "international", "geopolitical"):
            v = reply.get(cat) if isinstance(reply, dict) else None
            ids = [i for i in (v or {}).get("ids") or [] if i in numbered] if isinstance(v, dict) else []
            text = scrub(str((v or {}).get("text") or "")).strip() if isinstance(v, dict) else ""
            allowed = set().union(*[_nums(numbered[i]["text"] + " " + numbered[i]["date"]) for i in ids]) if ids else set()
            bad = [n for n in _nums(text) if n not in allowed and n != symbol]
            if text and ids and not bad and not _BLOCKED.search(text):
                out[cat] = {"text": text, "urls": list(dict.fromkeys(numbered[i]["url"] for i in ids)), "written": True}
            elif fallback(cat):
                out[cat] = fallback(cat)
        if isinstance(reply, dict) and reply.get("_error"):
            out["_note"] = {"text": "News paragraphs could not be written (" + reply["_error"] + "); headlines listed instead."}
        return out
    for cat in ("company", "us", "international", "geopolitical"):
        if fallback(cat):
            out[cat] = fallback(cat)
    return out


def build_public_report(symbol: str, use_ai: bool = True, name: str = "") -> Dict[str, Any]:
    """Analysis from the template (no AI cost), news from the free scan, news paragraphs by Haiku (a few cents)."""
    from backend import content_hub as ch
    log: List[Dict[str, Any]] = []
    t_usage = ch._USAGE.set(log)
    try:
        f = public_facts(ch.build_facts(symbol))
        bars = f.pop("_chart_bars", None)
        blog = ch.generate_blog(f, use_ai=False)
        news_raw = scan_news(symbol, name)
        print(f"[report_pack] {symbol} news items: " + ", ".join(f"{k}={len(v)}" for k, v in news_raw.items()), flush=True)
        news = write_news(symbol, news_raw, use_ai)
    finally:
        ch._USAGE.reset(t_usage)

    sections = []
    for s in blog.get("sections") or []:
        head, body = scrub(s.get("heading")), _drop_sentences(_drop_sentences(scrub(s.get("body")), _METHOD), _BLOCKED)
        if body.strip():
            sections.append({"heading": head, "body": body, "news": False})
    news_secs, sources = [], []
    for cat in ("company", "us", "international", "geopolitical"):
        v = news.get(cat)
        if not v:
            continue
        body = _drop_sentences(scrub(v["text"]), _BLOCKED)
        if body.strip():
            news_secs.append({"heading": ch.NEWS_HEADINGS[cat].format(s=symbol), "body": body, "news": True})
            for u in v["urls"]:
                it = next((x for x in news_raw.get(cat) or [] if x["url"] == u), None)
                sources.append({"title": f"{it['source']}: {it['text'][:110]}" if it else u, "url": u})
    at = next((i for i, x in enumerate(sections) if x["heading"] == "Sigmalytic Summary"), len(sections))
    sections = sections[:at] + news_secs + sections[at:]
    if news_raw.get("international") or news_raw.get("geopolitical"):
        sources.append({"title": "International coverage located through the GDELT Project", "url": "https://www.gdeltproject.org/"})

    title = scrub(blog.get("title"))
    if not title or _BLOCKED.search(title):
        title = f"{symbol} Stock Analysis: Price Structure and Key Levels"
    bottom = _drop_sentences(scrub(blog.get("bottom_line")), _BLOCKED)
    bullets = [scrub(b) for b in blog.get("chart_bullets") or [] if not _BLOCKED.search(scrub(b))]
    img = {k: _drop_sentences(scrub(v), _BLOCKED) for k, v in (blog.get("image_text") or {}).items()}

    png_b64 = None
    notes: List[str] = []
    if bars:
        try:
            from backend.content_chart import render_share_image
            png_b64 = base64.b64encode(render_share_image(f, bars, title=title, view_text=img.get("view", ""),
                                                          volume_text=img.get("volume", ""))).decode("ascii")
        except Exception as e:
            notes.append(f"Chart could not be drawn: {str(e)[:120]}")
    else:
        notes.append("No price bars for the chart.")
    if news.get("_note"):
        notes.append(news["_note"]["text"])
    written = sum(1 for c in ("company", "us", "international", "geopolitical") if (news.get(c) or {}).get("written"))
    listed = sum(1 for c in ("company", "us", "international", "geopolitical") if news.get(c) and not news[c].get("written"))

    everything = " ".join([title, bottom] + bullets + [x["heading"] + " " + x["body"] for x in sections])
    blocked = sorted({m.group(0) for m in _BLOCKED.finditer(everything)})
    session = f.get("session") or {}
    dates = f"Report date: {ch._long_date(f.get('generated_at') or f['as_of'])}  ·  Market data through: {ch._long_date(f['as_of'])}"
    if session.get("live"):
        dates += f"  ·  As of {session.get('stamp')}; the trading session was still in progress"
    return {
        "symbol": f["symbol"], "name": name, "as_of": f["as_of"], "dates": dates, "title": title, "bottom_line": bottom,
        "sections": sections, "chart_bullets": bullets, "png_b64": png_b64, "sources": sources,
        "related": blog.get("related") or [], "ai_used": written > 0,
        "news_count": len(news_secs), "news_written": written, "news_listed": listed,
        "news_items": {k: len(v) for k, v in news_raw.items()}, "notes": notes,
        "usage": ch.summarize_usage(log), "blocked_words": blocked, "built_at": _now_iso(),
    }


# ───────────────────────────── the background job ─────────────────────────────

def _job_path(day: str) -> str:
    return os.path.join(_dir(day), "job.json")


def _sym_path(day: str, sym: str) -> str:
    return os.path.join(_dir(day), f"{_safe(sym)}.json")


def _pdf_path(day: str) -> str:
    return os.path.join(_dir(day), "pack.pdf")


def _update(day: str, fn) -> Dict[str, Any]:
    with _lock:
        job = _read(_job_path(day)) or {}
        fn(job)
        job["heartbeat"] = time.time()
        _write(_job_path(day), job)
        return job


def _alive() -> bool:
    return bool(_thread and _thread.is_alive())


def _launch(day: str) -> None:
    global _thread
    with _lock:
        if _alive():
            return
        _thread = threading.Thread(target=_run, args=(day,), name="report-pack", daemon=True)
        _thread.start()


def _run(day: str) -> None:
    stop = threading.Event()

    def beat():
        while not stop.wait(30):
            _update(day, lambda j: None)

    threading.Thread(target=beat, daemon=True).start()
    try:
        job = _read(_job_path(day)) or {}
        pending = [s for s in job.get("symbols") or []
                   if (job.get("items") or {}).get(s, {}).get("state") in ("queued", "building")]

        def one(sym: str):
            _update(day, lambda j: j["items"][sym].update({"state": "building", "started": _now_iso()}))
            rep = build_public_report(sym, use_ai=job.get("use_ai", True), name=(job.get("names") or {}).get(sym, ""))
            _write(_sym_path(day, sym), rep)
            return rep

        credit_msg = None
        interrupted = False
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futs = {pool.submit(one, s): s for s in pending}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    rep = fut.result()
                    state = "blocked" if rep["blocked_words"] else "done"
                    info = {"state": state, "cost_usd": (rep.get("usage") or {}).get("cost_usd"),
                            "news": rep.get("news_count", 0), "news_written": rep.get("news_written", 0),
                            "news_listed": rep.get("news_listed", 0), "ai": rep.get("ai_used"),
                            "note": ("Blocked: still contains " + ", ".join(rep["blocked_words"])) if rep["blocked_words"]
                            else "; ".join(rep.get("notes") or [])[:300]}
                except CreditError as e:            # out of credit: stop, keep this symbol queued, cancel the rest
                    credit_msg = str(e)
                    info = {"state": "queued", "note": "Waiting: Anthropic credit ran out."}
                    for other in futs:
                        other.cancel()
                except Exception as e:
                    if _shutting_down(e):           # the worker is being replaced: leave it queued, resume later
                        interrupted = True
                        for other in futs:
                            other.cancel()
                        break
                    info = {"state": "failed", "note": str(e)[:300]}
                if fut.cancelled():
                    continue
                _update(day, lambda j, s=sym, i=info: j["items"][s].update({**i, "finished": _now_iso()}))
        if interrupted or _shutting_down():
            # No status change: the heartbeat stops, and the next status check (in the new worker) sees a stale job and
            # resumes it; reports already saved are reused, items left "building" are queued again by start().
            return
        if credit_msg:
            def _requeue(j):
                for it in (j.get("items") or {}).values():
                    if it.get("state") == "building":
                        it["state"] = "queued"
                j.update({"state": "stopped", "error": credit_msg})
            _update(day, _requeue)
            return
        _update(day, lambda j: j.update({"state": "assembling"}))
        job = _read(_job_path(day)) or {}
        pdf, engine = assemble_pdf(day, job)
        with open(_pdf_path(day), "wb") as fh:
            fh.write(pdf)
        _update(day, lambda j: j.update({"state": "done", "pdf_ready": True, "pdf_engine": engine, "finished_at": _now_iso(),
                                         "pdf_bytes": len(pdf)}))
    except Exception as e:
        if not _shutting_down(e):
            _update(day, lambda j: j.update({"state": "failed", "error": str(e)[:400]}))
    finally:
        stop.set()


def start(use_ai: bool = True, restart: bool = False, retry_failed: bool = False, size: int = PACK_SIZE) -> Dict[str, Any]:
    """Starts today's pack, or resumes it. size = how many of the top companies (3 for a sample, up to 25).
    restart=True builds a new list and new reports; retry_failed re-queues failures. Finished reports are reused."""
    day = _today()
    size = max(1, min(PACK_SIZE, int(size or PACK_SIZE)))
    with _lock:
        job = _read(_job_path(day))
        if job and job.get("state") in ("running", "assembling") and (_alive() or time.time() - job.get("heartbeat", 0) < STALE_SECONDS):
            return status()
        if restart or not job or job.get("size", PACK_SIZE) != size:
            top = top_list(refresh=restart)
            rows = (top.get("top") or [])[:size]
            if not rows:
                return {"ok": False, "error": "Could not build the top-25 list. " + "; ".join(
                    f"{x['symbol']}: {x['reason']}" for x in (top.get("skipped") or [])[:5])}
            if restart:                            # restart means fresh reports, so today's old files are removed
                for r in rows:
                    if os.path.exists(_sym_path(day, r["symbol"])):
                        os.remove(_sym_path(day, r["symbol"]))
                if os.path.exists(_pdf_path(day)):
                    os.remove(_pdf_path(day))
            old_items = (job or {}).get("items") or {} if not restart else {}
            if os.path.exists(_pdf_path(day)):         # the list changed, so the old PDF no longer matches
                os.remove(_pdf_path(day))
            job = {"day": day, "use_ai": use_ai, "size": size, "created_at": _now_iso(), "symbols": [r["symbol"] for r in rows],
                   "names": {r["symbol"]: r["name"] for r in rows}, "list_computed_at": top.get("computed_at"),
                   "items": {r["symbol"]: (old_items.get(r["symbol"]) if (old_items.get(r["symbol"]) or {}).get("state") == "done"
                                           else {"state": "queued"}) for r in rows}}
        job["use_ai"] = use_ai
        for s, it in job["items"].items():
            if it.get("state") == "building" or (retry_failed and it.get("state") in ("failed", "blocked")):
                it["state"] = "queued"
            if it.get("state") == "queued" and os.path.exists(_sym_path(day, s)) and not retry_failed:
                it["state"] = "done"           # finished before an interruption: reuse it, no new cost
        if any(it.get("state") == "queued" for it in job["items"].values()) or not os.path.exists(_pdf_path(day)):
            job.update({"state": "running", "pdf_ready": False, "error": None})
        job["heartbeat"] = time.time()
        _write(_job_path(day), job)
        if job["state"] == "running":
            _launch(day)
    return status()


def status() -> Dict[str, Any]:
    day = _today()
    job = _read(_job_path(day))
    if not job:
        return {"ok": True, "state": "none", "day": day}
    if job.get("state") in ("running", "assembling") and not _alive() and time.time() - job.get("heartbeat", 0) > 45:
        _launch(day)                            # the worker restarted mid-run: carry on from the saved reports
        job["resumed"] = True
    items = job.get("items") or {}
    counts: Dict[str, int] = {}
    cost = 0.0
    for it in items.values():
        counts[it.get("state", "queued")] = counts.get(it.get("state", "queued"), 0) + 1
        cost += float(it.get("cost_usd") or 0)
    return {"ok": True, **job, "counts": counts, "cost_usd": round(cost, 4), "total": len(items)}


def pdf_bytes() -> Optional[bytes]:
    p = _pdf_path(_today())
    if os.path.exists(p):
        with open(p, "rb") as fh:
            return fh.read()
    return None


# ───────────────────────────── PDF ─────────────────────────────

def brand_tm(text: str) -> str:
    """Every 'Sigmalytic Quant Corporation' and 'Sigmalytic Quant AI' carries the trademark symbol."""
    return _TM.sub(lambda m: m.group(0) + "™", text)


_LOGO_URI: List[str] = []


def _logo_uri() -> str:
    """The same logo the charts use (bright lettering, trademark symbol), as an embedded PNG."""
    if _LOGO_URI:
        return _LOGO_URI[0]
    uri = ""
    try:
        from backend.content_chart import logo_png_bytes
        data = logo_png_bytes()
        if data:
            uri = "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        uri = ""
    _LOGO_URI.append(uri)
    return uri

_CSS = """
@page { size: Letter; margin: 0.6in 0.6in 0.7in 0.6in;
        @bottom-left { content: "Sigmalytic Quant Corporation  ·  sigmalyticquantcorp.com  ·  Educational research, not investment advice"; font-size: 7.5pt; color: #64748b; }
        @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 7.5pt; color: #64748b; } }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9.6pt; line-height: 1.5; color: #0f172a; }
h1 { font-size: 17pt; margin: 0 0 4px 0; color: #0b1a33; }
h2 { font-size: 11.5pt; margin: 14px 0 4px 0; color: #12305f; border-bottom: 1px solid #dbe4f3; padding-bottom: 2px; }
p { margin: 0 0 7px 0; }
@page welcome { margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }
.welcome { page: welcome; page-break-after: always; font-family: 'DejaVu Serif', Georgia, serif; color: #0f172a; }
.welcome .band { background: #111c33; padding: 0.42in 0.6in 0.34in 0.6in; border-bottom: 4px solid #c9a227; }
.welcome .band table { width: 100%; border-collapse: collapse; }
.welcome .band img { height: 0.95in; }
.welcome .band .meta { text-align: right; vertical-align: bottom; color: #e2e8f0; font-family: 'DejaVu Sans', Arial, sans-serif;
                       font-size: 8.5pt; letter-spacing: 1.5px; line-height: 1.7; }
.welcome .band .meta b { color: #c9a227; font-size: 9.5pt; }
.welcome .body { padding: 0.32in 0.6in 0 0.6in; }
.welcome .eyebrow { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 8.5pt; letter-spacing: 2.5px; color: #8a6d12;
                    font-weight: bold; }
.welcome h1 { font-size: 25pt; margin: 4px 0 10px 0; color: #0d1b3a; font-weight: bold; }
.welcome .lead { font-size: 10.6pt; line-height: 1.62; margin: 0 0 8px 0; }
.welcome .facts { width: 100%; border-collapse: collapse; margin: 14px 0 16px 0; border-top: 1px solid #0d1b3a;
                  border-bottom: 1px solid #0d1b3a; font-family: 'DejaVu Sans', Arial, sans-serif; }
.welcome .facts td { padding: 7px 8px; vertical-align: top; width: 25%; border-right: 1px solid #cbd5e1; }
.welcome .facts td:last-child { border-right: none; }
.welcome .facts .k { font-size: 7pt; letter-spacing: 1.4px; color: #64748b; text-transform: uppercase; }
.welcome .facts .v { font-size: 10.5pt; font-weight: bold; color: #0d1b3a; margin-top: 2px; }
.welcome .cols { width: 100%; border-collapse: separate; border-spacing: 12px 0; margin: 0 -12px; }
.welcome .cols td { vertical-align: top; width: 33.3%; border-top: 3px solid #c9a227; padding-top: 7px; }
.welcome .cols h3 { font-size: 11.5pt; margin: 0 0 5px 0; color: #0d1b3a; }
.welcome .cols p { font-size: 9.2pt; line-height: 1.55; margin: 0; }
.welcome .contact { margin-top: 16px; font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9pt; color: #0d1b3a; }
.welcome .legal { margin-top: 18px; padding-top: 8px; border-top: 1px solid #cbd5e1; font-family: 'DejaVu Sans', Arial, sans-serif;
                  font-size: 7.4pt; line-height: 1.5; color: #475569; }
.welcome .legal p { margin: 0 0 5px 0; }
.cover { page-break-after: always; }
.cover .logo { width: 100%; border-radius: 6px; margin-top: 0.5in; }
.cover h1 { margin-top: 4px; }
.cover .brand { font-size: 10pt; letter-spacing: 1px; color: #2a5bd7; font-weight: bold; margin-top: 18px; }
.rlogo { height: 0.42in; border-radius: 4px; margin-bottom: 6px; }
.site { font-size: 8.5pt; }
.cover h1 { font-size: 26pt; margin-top: 10px; }
.cover .sub { font-size: 11pt; color: #334155; margin-top: 6px; }
.toc { margin-top: 26px; }
.toc table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
.toc td { padding: 3px 4px; border-bottom: 1px solid #e2e8f0; }
.toc a { color: #0f172a; text-decoration: none; }
.toc a.pg::after { content: target-counter(attr(href), page); }
.report { page-break-before: always; }
.byline { font-size: 8.5pt; color: #475569; margin-bottom: 8px; }
.bottom { background: #eef4ff; border-left: 3px solid #2a5bd7; padding: 6px 9px; margin: 8px 0 10px 0; }
.chart { width: 100%; margin: 6px 0 4px 0; }
.levels { font-size: 8.8pt; margin: 2px 0 8px 0; }
.small { font-size: 8pt; color: #475569; }
.disclaimer { font-size: 7.8pt; color: #475569; font-style: italic; margin-top: 8px; }
a { color: #1d4ed8; }
"""


def _paras_html(sec: Dict[str, Any], posts: List[Dict[str, Any]]) -> str:
    from backend import publishing_checklist as pc
    esc = _html.escape
    out = []
    for t in [x.strip() for x in str(sec["body"]).split("\n\n") if x.strip()]:
        if sec["heading"] == "Sigmalytic Summary" and ": " in t:
            lab, rest = t.split(": ", 1)
            out.append(f"<p><strong>{esc(lab)}:</strong> {esc(rest)}</p>")
        else:
            try:
                out.append(f"<p>{pc.expand_links(esc(t), posts, 'html')}</p>")
            except Exception:
                plain = re.sub(r"\[\[\d+\]\]", "", t)
                out.append(f"<p>{esc(plain)}</p>")
    return "\n".join(out)


def _report_html(rep: Dict[str, Any], idx: int) -> str:
    from backend import content_hub as ch
    from backend import publishing_checklist as pc
    esc = _html.escape
    logo = _logo_uri()
    head = (f"<section class='report' id='r{idx}'>"
            + (f"<img class='rlogo' src='{logo}' alt='Sigmalytic Quant Corporation'>" if logo else "")
            + f"<h1>{esc(rep['title'])}</h1>"
            f"<div class='byline'>{esc(rep['symbol'])}{(' · ' + esc(rep['name'])) if rep.get('name') else ''}<br>"
            f"Market Structure Report by Sigmalytic Quant AI · Sigmalytic Quant Corporation<br>{esc(rep['dates'])}<br>"
            f"<a class='site' href='{WEBSITE}'>{WEBSITE}</a></div>")
    if rep.get("bottom_line"):
        head += f"<div class='bottom'><strong>Bottom Line:</strong> {esc(rep['bottom_line'])}</div>"
    body = []
    for i, sec in enumerate(rep["sections"]):
        body.append(f"<h2>{esc(sec['heading'])}</h2>{_paras_html(sec, rep.get('related') or [])}")
        if i == 0 and rep.get("png_b64"):
            body.append(f"<img class='chart' src='data:image/png;base64,{rep['png_b64']}' alt='{esc(rep['symbol'])} daily chart'>")
            if rep.get("chart_bullets"):
                body.append("<div class='levels'><strong>Levels shown in the chart:</strong><ul>"
                            + "".join(f"<li>{esc(b)}</li>" for b in rep["chart_bullets"]) + "</ul></div>")
    src = [f"<li>{esc(ch.DATA_SOURCE)}: market data used for this report.</li>"] + [
        f"<li><a href='{esc(x['url'] or '')}'>{esc(x['title'] or x['url'] or '')}</a></li>" for x in rep.get("sources") or []]
    attr = "".join(f"<p class='small'>{esc(x)}</p>" for x in ch.attribution_text().split("\n\n"))
    year = (rep.get("as_of") or "")[:4] or str(datetime.now(ET).year)
    tail = (f"<h2>Market Data and Attribution</h2>{attr}<h2>Reference Sources</h2><ul class='small'>{''.join(src)}</ul>"
            f"<p class='small'>More market structure research from Sigmalytic Quant AI: <a href='{WEBSITE}'>{WEBSITE}</a></p>"
            f"<p class='small'>© {esc(year)} Sigmalytic Quant Corporation. All rights reserved.</p>"
            f"<p class='disclaimer'>{esc(ch.DISCLAIMER)}</p></section>")
    return head + "".join(body) + tail


def _welcome_html(day: str, reps: List[Dict[str, Any]], heading: str) -> str:
    """Page 1: the welcome letter, laid out like the opening page of a financial report."""
    from backend import content_hub as ch
    esc = _html.escape
    logo = _logo_uri()
    year = day[:4]
    data_through = max((r.get("as_of") or "") for r in reps)
    logo_html = (f"<img src='{logo}' alt='Sigmalytic Quant Corporation'>" if logo
                 else "<span style='color:#c9a227;font-size:18pt;font-weight:bold'>SIGMALYTIC QUANT CORPORATION</span>")
    mail = f"<a href='mailto:{EMAIL}'>{EMAIL}</a>"
    return (
        "<section class='welcome'>"
        f"<div class='band'><table><tr><td>{logo_html}</td>"
        f"<td class='meta'><b>MARKET STRUCTURE REPORT PACK</b><br>{esc(heading.upper())}<br>{esc(ch._long_date(day).upper())}</td>"
        "</tr></table></div>"
        "<div class='body'>"
        "<div class='eyebrow'>SIGMALYTIC QUANT CORPORATION</div>"
        "<h1>Welcome to Sigmalytic</h1>"
        "<p class='lead'>We built Sigmalytic because we believe a tool is only as good as the outcomes it helps create for "
        "the people using it. Your success is the whole point — we don't measure ours any other way.</p>"
        "<p class='lead'>Markets generate thousands of signals every day. Sigmalytic helps you sort through the noise, save "
        "time, and focus on potential Trades About to Happen — so you can explore opportunities with a clearer view of what "
        "the market is doing, and make more informed decisions with confidence.</p>"
        "<table class='facts'><tr>"
        f"<td><div class='k'>Companies covered</div><div class='v'>{len(reps)}</div></td>"
        f"<td><div class='k'>Market data through</div><div class='v'>{esc(ch._long_date(data_through) if data_through else '')}</div></td>"
        "<td><div class='k'>Prepared by</div><div class='v'>Sigmalytic Quant AI</div></td>"
        "<td><div class='k'>Data sources</div><div class='v' style='font-size:8.5pt'>Alpaca Markets · SEC EDGAR · FRED · GDELT</div></td>"
        "</tr></table>"
        "<table class='cols'><tr>"
        "<td><h3>Learn from every decision</h3><p>Behavioral Intelligence helps you see the patterns behind your own "
        "decisions and outcomes. Use that feedback to recognize avoidable mistakes, build better habits, and strengthen your "
        "process — trade by trade, day by day.</p></td>"
        "<td><h3>Stay informed</h3><p>Start your day with the morning audio report, follow your alerts as they come in, and "
        "enable the nightly report in Preferences for email delivery. Wherever your day takes you, Sigmalytic keeps you "
        "connected to the market.</p></td>"
        "<td><h3>We're listening</h3><p>Your feedback shapes what we build next. If something's working well, or if you see "
        f"a way we can do better, we want to hear it. Email us at {mail} — we read every message and reply within 24–48 "
        "hours.</p></td>"
        "</tr></table>"
        f"<div class='contact'><b>Contact:</b> {mail} &nbsp;·&nbsp; <b>Web:</b> <a href='{WEBSITE}'>{WEBSITE}</a></div>"
        "<div class='legal'>"
        f"<p>© {esc(year)} Sigmalytic Quant Corporation. All rights reserved.</p>"
        "<p>Sigmalytic's original application design, software and source code, analyses, reports, text, charts, and graphics "
        "are protected by copyright. Copying, modifying, distributing, or reusing these materials requires prior written "
        "permission, except as permitted by law or an applicable license. Third-party market data and licensed materials "
        "remain the property of their respective rights holders.</p>"
        "<p>Sigmalytic Quant Corporation and Sigmalytic Quant AI are trademarks of Sigmalytic Quant Corporation. All other "
        "names and marks are the property of their respective owners.</p>"
        f"<p>{esc(ch.DISCLAIMER)}</p>"
        "</div></div></section>")


def assemble_pdf(day: str, job: Dict[str, Any]):
    from backend import content_hub as ch
    esc = _html.escape
    reps, missing = [], []
    for s in job.get("symbols") or []:
        it = (job.get("items") or {}).get(s, {})
        rep = _read(_sym_path(day, s)) if it.get("state") == "done" else None
        if rep and not rep.get("blocked_words"):
            reps.append(rep)
        else:
            missing.append(s)
    if not reps:
        raise ValueError("No report was completed, so there is nothing to put in the PDF.")
    long_day = ch._long_date(day)
    n = len(job.get("symbols") or [])
    heading = (f"Top {n} U.S. Companies by Market Capitalization" if n >= PACK_SIZE
               else f"Sample: Top {n} U.S. Companies by Market Capitalization")
    rows = "".join(f"<tr><td>{i}</td><td><a href='#r{i}'>{esc(r['symbol'])}</a></td><td>{esc(r.get('name') or '')}</td>"
                   f"<td style='text-align:right'><a class='pg' href='#r{i}'></a></td></tr>" for i, r in enumerate(reps, 1))
    miss = (f"<p class='small'>Not included today: {esc(', '.join(missing))} (the report could not be completed).</p>"
            if missing else "")
    logo = _logo_uri()
    cover = (f"<section class='cover'>"
             + (f"<img class='rlogo' src='{logo}' alt='Sigmalytic Quant Corporation'>" if logo
                else "<div class='brand'>SIGMALYTIC QUANT CORPORATION</div>")
             + "<div class='brand'>CONTENTS</div>"
             + f"<h1>{esc(heading)}</h1>"
             f"<div class='sub'>Market Structure Reports by Sigmalytic Quant AI · {esc(long_day)}</div>"
             f"<div class='sub'><a href='{WEBSITE}'>{WEBSITE}</a></div>"
             f"<p class='small' style='margin-top:14px'>One report for each of the largest U.S.-listed companies by approximate "
             f"market capitalization, listed largest first. Each report covers price structure, momentum, key levels, "
             f"participation and recent news from SEC filings, news wires and economic data.</p>"
             f"<div class='toc'><table>{rows}</table></div>{miss}"
             f"<p class='disclaimer'>{esc(ch.DISCLAIMER)}</p></section>")
    doc = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Sigmalytic Top 25 Report Pack {esc(day)}</title>"
           f"<style>{_CSS}</style></head><body>{_welcome_html(day, reps, heading)}{cover}" + "".join(_report_html(r, i) for i, r in enumerate(reps, 1))
           + "</body></html>")
    doc = brand_tm(doc)
    if _BLOCKED.search(re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "", doc)):
        raise ValueError("A blocked word reached the assembled PDF; the PDF was not created.")
    try:
        from weasyprint import HTML
        return HTML(string=doc).write_pdf(), "weasyprint"
    except Exception as exc:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        if pisa.CreatePDF(doc, dest=buf).err:
            raise ValueError(f"PDF conversion failed ({str(exc)[:120]})")
        return buf.getvalue(), "xhtml2pdf"
