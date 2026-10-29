# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/assistant.py
--------------------
Sigmalytic Assistant (admin only, Level 1): plain-English questions answered by Claude (Anthropic) or ChatGPT
(OpenAI) using ONLY Sigmalytic's own data. Claude is the default.

How an answer is made
  1. The question (plus the last few turns of the conversation) goes to the model with five read-only lookups it
     may call: search_scan, get_symbol_facts, get_setup_state, lookup_companies, list_daily_reports /
     get_daily_report. Each lookup only calls code the platform already has (the Sigma Radar scan in Redis,
     content_hub.build_facts, radar_service.get_symbol_weis_state, reports_engine).
  2. The model may call lookups several times, then writes its answer.
  3. Code checks the answer before anyone sees it: every number must appear in what the lookups returned (the same
     rule the Content Hub uses), no advice or promise phrasing, no method words, and never "Wyckoff" or "Weis".
     A failing answer gets one rewrite; if it still fails it is withheld, never shown.
  4. The short disclaimer is added by code, never by the model.

Nothing here places orders, writes platform data, or posts anywhere. Every question and answer is logged to Redis
(assistant:log) so answers can be reviewed later.

Settings (Render environment variables on the backend service)
  ANTHROPIC_API_KEY            for Claude (already set: the Content Hub uses it)
  OPENAI_API_KEY               for ChatGPT
  ASSISTANT_PROVIDER           optional: "anthropic" or "openai". Unset: read from ASSISTANT_MODEL, else Claude when
                               ANTHROPIC_API_KEY is set
  ASSISTANT_MODEL              default "claude-sonnet-5-5" for Claude, "gpt-5.6-luna" for ChatGPT
  ASSISTANT_EFFORT             optional thinking effort, e.g. "low" (Claude output_config.effort / OpenAI reasoning_effort)
  ASSISTANT_DAILY_LIMIT_USD    default 5     spending cap per calendar day, Eastern time
  ASSISTANT_DAILY_QUESTIONS    default 100   question cap per day (also the cap when a model's price is unknown)
"""

from __future__ import annotations

import csv
import html as _html
import json
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend import content_hub as ch

ET = ZoneInfo("America/New_York")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-5.6-luna"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
LOG_KEY = "assistant:log"
LOG_KEEP = 500
SPEND_KEY = "assistant:spend:{day}"
COUNT_KEY = "assistant:count:{day}"
MAX_ROUNDS = 6              # model turns per question (each turn may call several lookups)
DEADLINE_SECONDS = 135      # the admin tab waits 150 seconds for a reply
MAX_HISTORY_MESSAGES = 8
MAX_QUESTION_CHARS = 2000
MAX_TOOL_RESULT_CHARS = 24000
SECTOR_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "russell1000_sector_industry.csv")

DISCLAIMER = ch.SHORT_DISCLAIMER
EXTRA_BLOCKED = re.compile(r"\b(?:wyckoff|weis)\b", re.IGNORECASE)


def provider_name() -> Optional[str]:
    """'anthropic' (Claude) or 'openai' (ChatGPT). ASSISTANT_PROVIDER decides; otherwise the provider is read from
    ASSISTANT_MODEL's name; otherwise Claude when its key is set, then ChatGPT."""
    want = (os.getenv("ASSISTANT_PROVIDER") or "").strip().lower()
    if want in ("anthropic", "claude"):
        return "anthropic"
    if want in ("openai", "chatgpt"):
        return "openai"
    model = (os.getenv("ASSISTANT_MODEL") or "").strip().lower()
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai" if os.getenv("OPENAI_API_KEY") else None


def model_name(provider: Optional[str] = None) -> str:
    provider = provider or provider_name() or "anthropic"
    return (os.getenv("ASSISTANT_MODEL") or DEFAULT_MODELS[provider]).strip()


def _redis():
    try:
        from backend.radar_service import _redis_client
        return _redis_client
    except Exception:
        return None


# ───────────────────────────── signal names ─────────────────────────────

# Raw scan signal -> (key the model filters by, published label). Labels follow the platform's own naming.
SIGNALS: Dict[str, Tuple[str, str]] = {
    "BREAKOUT": ("breakout", "Breakout"),
    "BREAKDOWN": ("breakdown", "Breakdown"),
    "UPTHRUST": ("bull_trap", "Bull Trap"),
    "SPRING": ("bear_trap", "Bear Trap"),
    "UPTHRUST_BUILDING": ("bull_trap_forming", "Bull Trap Forming"),
    "SPRING_BUILDING": ("bear_trap_forming", "Bear Trap Forming"),
    "CLIMAX_BUY": ("buying_climax", "Buying Climax"),
    "CLIMAX_SELL": ("selling_climax", "Selling Climax"),
    "3BAR_BULLISH": ("3bar_bullish", "Bullish 3-Bar Reversal"),
    "3BAR_BEARISH": ("3bar_bearish", "Bearish 3-Bar Reversal"),
    "SIGN_OF_STRENGTH": ("sign_of_strength", "Sign of Strength"),
    "SIGN_OF_WEAKNESS": ("sign_of_weakness", "Sign of Weakness"),
    "NO_SUPPLY (absorption)": ("absorption", "Absorption / No Supply"),
    "NO_DEMAND (distribution)": ("distribution", "Distribution / No Demand"),
}
SIGNAL_KEYS = sorted({k for k, _ in SIGNALS.values()})


def signal_info(raw: Any) -> Tuple[str, str]:
    raw = str(raw or "")
    if raw in SIGNALS:
        return SIGNALS[raw]
    key = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_") or "other"
    return key, ch.pattern_name(raw)


# ───────────────────────────── company / sector data ─────────────────────────────

_COMPANIES: Optional[Dict[str, Dict[str, str]]] = None


def companies() -> Dict[str, Dict[str, str]]:
    global _COMPANIES
    if _COMPANIES is None:
        out: Dict[str, Dict[str, str]] = {}
        try:
            with open(SECTOR_FILE, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    t = (row.get("ticker") or "").strip().upper()
                    if t:
                        out[t] = {"company": (row.get("name") or "").strip().title(),
                                  "sector": (row.get("sector") or "").strip(),
                                  "industry": (row.get("industry") or "").strip()}
        except OSError:
            pass
        _COMPANIES = out
    return _COMPANIES


# ───────────────────────────── data sources (replaceable in tests) ─────────────────────────────

def _load_scan() -> Dict[str, Any]:
    from backend.weis_radar_scan import get_weis_radar_results
    return get_weis_radar_results()


def _load_facts(symbol: str) -> Dict[str, Any]:
    return ch.build_facts(symbol)


def _load_setup_state(symbol: str) -> Dict[str, Any]:
    from backend.radar_service import get_symbol_weis_state
    return get_symbol_weis_state(symbol)


def _load_report_dates() -> Dict[str, Any]:
    from backend.reports_engine import report_catalog
    return report_catalog()


def _load_report_html(date: str) -> Optional[str]:
    from backend.reports_engine import get_report_html
    return get_report_html(date)


# ───────────────────────────── lookups ─────────────────────────────

def _sym(v: Any) -> str:
    s = str(v or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s):
        raise ValueError("Not a valid stock symbol.")
    return s


def tool_search_scan(signals: Optional[List[str]] = None, symbols: Optional[List[str]] = None,
                     sector: Optional[str] = None, max_sessions_held: Optional[int] = None,
                     new_only: bool = False, sort_by: str = "newest", limit: int = 25) -> Dict[str, Any]:
    scan = _load_scan()
    if scan.get("ok") is False:
        return {"ok": False, "error": f"Scan results unavailable: {scan.get('error')}"}
    want = {str(s).lower() for s in (signals or []) if s}
    syms = {str(s).strip().upper() for s in (symbols or []) if s}
    sec = (sector or "").strip().lower()
    co = companies()
    rows: List[Dict[str, Any]] = []
    for r in scan.get("results") or []:
        sym = str(r.get("symbol") or "").upper()
        if syms and sym not in syms:
            continue
        info = co.get(sym, {})
        if sec and sec not in info.get("sector", "").lower() and sec not in info.get("industry", "").lower():
            continue
        for h in r.get("hits") or []:
            key, label = signal_info(h.get("type"))
            if want and key not in want:
                continue
            held = h.get("days_back")
            if new_only and held not in (0, None):
                continue
            if max_sessions_held is not None and held is not None and int(held) > int(max_sessions_held):
                continue
            row = {"symbol": sym, "company": info.get("company"), "sector": info.get("sector"),
                   "industry": info.get("industry"), "signal": label, "close": h.get("price"),
                   "level": h.get("level") if h.get("level") is not None else h.get("structure_level"),
                   "first_crossed": str(h.get("date") or "")[:10] or None, "sessions_held": held,
                   "pct_beyond_level": h.get("pct_beyond"), "setup_state": r.get("weis_state"),
                   "last_bar_date": str(r.get("last_bar_time") or "")[:10] or None}
            for k in ("entry_trigger", "invalidation"):
                if h.get(k) is not None:
                    row[k] = h[k]
            rows.append({k: v for k, v in row.items() if v not in (None, "")})
    if sort_by == "pct_beyond":
        rows.sort(key=lambda x: -(x.get("pct_beyond_level") or 0))
    elif sort_by == "symbol":
        rows.sort(key=lambda x: x["symbol"])
    else:
        rows.sort(key=lambda x: (x.get("sessions_held", 99), -(x.get("pct_beyond_level") or 0), x["symbol"]))
    counts: Dict[str, int] = {}
    for x in rows:
        counts[x["signal"]] = counts.get(x["signal"], 0) + 1
    bar_dates = [x.get("last_bar_date") for x in rows if x.get("last_bar_date")]
    limit = max(1, min(int(limit or 25), 60))
    return {"ok": True, "scan_generated_at": scan.get("generated_at"), "symbols_scanned": scan.get("scanned"),
            "latest_bar_date": max(bar_dates) if bar_dates else None, "total_matched": len(rows),
            "returned": min(limit, len(rows)), "counts_by_signal": counts, "rows": rows[:limit],
            "note": "Only the latest scan is stored; earlier days are only in stored daily reports."}


_FACTS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
FACTS_TTL = 600


def tool_get_symbol_facts(symbol: str) -> Dict[str, Any]:
    sym = _sym(symbol)
    hit = _FACTS_CACHE.get(sym)
    if hit and time.time() - hit[0] < FACTS_TTL:
        return hit[1]
    f = _load_facts(sym)
    f = {k: v for k, v in f.items() if not str(k).startswith("_")}
    f["company"] = companies().get(sym, {})
    f["field_notes"] = {"call_wall": "strike with the largest call open interest (current, not historical)",
                        "put_wall": "strike with the largest put open interest (current, not historical)",
                        "ice_line": "a Sigmalytic horizontal reference level"}
    if len(_FACTS_CACHE) > 200:
        _FACTS_CACHE.clear()
    _FACTS_CACHE[sym] = (time.time(), f)
    return f


def tool_get_setup_state(symbol: str) -> Dict[str, Any]:
    return _load_setup_state(_sym(symbol))


def tool_lookup_companies(query: str, limit: int = 25) -> Dict[str, Any]:
    q = str(query or "").strip().lower()
    if not q:
        return {"ok": False, "error": "Give a ticker, company name, sector or industry."}
    out = []
    for t, info in companies().items():
        if q == t.lower() or q in info["company"].lower() or q in info["sector"].lower() or q in info["industry"].lower():
            out.append({"symbol": t, **info})
    out.sort(key=lambda x: (x["symbol"].lower() != q, x["symbol"]))
    limit = max(1, min(int(limit or 25), 100))
    return {"ok": True, "total_matched": len(out), "returned": min(limit, len(out)), "companies": out[:limit]}


def tool_list_daily_reports() -> Dict[str, Any]:
    cat = _load_report_dates()
    dates = list(cat.get("dates") or [])
    return {"ok": bool(cat.get("ok", True)), "dates": dates[:30], "total": len(dates),
            **({"warning": cat["warning"]} if cat.get("warning") else {})}


class _Text(HTMLParser):
    BLOCK = {"p", "div", "tr", "li", "br", "h1", "h2", "h3", "h4", "section", "table"}

    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(doc: str) -> str:
    p = _Text()
    p.feed(doc or "")
    text = _html.unescape("".join(p.parts))
    lines = [re.sub(r"[ \t|]+\|", " |", re.sub(r"[ \t]+", " ", ln)).strip(" |") for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def tool_get_daily_report(date: str, symbol: Optional[str] = None) -> Dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date or "")):
        return {"ok": False, "error": "Date must look like 2026-10-26."}
    doc = _load_report_html(date)
    if not doc:
        return {"ok": False, "error": f"No stored daily report for {date}."}
    text = html_to_text(doc)
    if symbol:
        sym = _sym(symbol)
        lines = text.splitlines()
        keep = sorted({j for i, ln in enumerate(lines) if re.search(rf"\b{re.escape(sym)}\b", ln)
                       for j in range(max(0, i - 1), min(len(lines), i + 2))})
        body = "\n".join(lines[i] for i in keep) or f"{sym} does not appear in the {date} report."
        return {"ok": True, "date": date, "symbol": sym, "excerpt": body[:MAX_TOOL_RESULT_CHARS]}
    return {"ok": True, "date": date, "text": text[:MAX_TOOL_RESULT_CHARS],
            "truncated": len(text) > MAX_TOOL_RESULT_CHARS}


TOOL_FUNCS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "search_scan": tool_search_scan,
    "get_symbol_facts": tool_get_symbol_facts,
    "get_setup_state": tool_get_setup_state,
    "lookup_companies": tool_lookup_companies,
    "list_daily_reports": tool_list_daily_reports,
    "get_daily_report": tool_get_daily_report,
}

TOOLS = [
    {"type": "function", "function": {
        "name": "search_scan",
        "description": "Search the latest Sigma Radar scan of the Russell 1000 (one row per flagged signal). Use for "
                       "questions about which stocks broke out, broke down, or showed a pattern. Filter by signal, "
                       "symbols, sector or industry, and how many sessions ago the level was first crossed. Rows "
                       "without sessions_held (traps, climaxes, reversals) are events on the latest bar.",
        "parameters": {"type": "object", "properties": {
            "signals": {"type": "array", "items": {"type": "string", "enum": SIGNAL_KEYS},
                        "description": "Signal types to include; omit for all."},
            "symbols": {"type": "array", "items": {"type": "string"}, "description": "Only these tickers."},
            "sector": {"type": "string", "description": "Text matched against sector or industry, e.g. "
                                                        "'semiconductor', 'Financials', 'utilities'."},
            "max_sessions_held": {"type": "integer", "description": "Only levels first crossed within this many "
                                                                   "sessions (0 = crossed in the latest session)."},
            "new_only": {"type": "boolean", "description": "Only levels first crossed in the latest session."},
            "sort_by": {"type": "string", "enum": ["newest", "pct_beyond", "symbol"]},
            "limit": {"type": "integer", "description": "Rows to return, 1-60 (default 25). total_matched always "
                                                       "gives the full count."}},
            "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_symbol_facts",
        "description": "Current facts for one stock from live data: last close and changes, 20/50/200-day averages, "
                       "20-day, 60-day and 52-week highs and lows, call wall, put wall, gamma flip level, ice line, "
                       "recent pattern signals, nearest reference levels above and below, and weekly, 4-hour and "
                       "2-hour levels. Takes a few seconds.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}},
                       "required": ["symbol"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_setup_state",
        "description": "The platform's current setup state for one stock: state, direction, reason, and the stop and "
                       "target levels the state defines.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}},
                       "required": ["symbol"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "lookup_companies",
        "description": "Find Russell 1000 companies by ticker, company name, sector or industry.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"},
                                                        "limit": {"type": "integer"}},
                       "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "list_daily_reports",
        "description": "Dates that have a stored Nightly Intelligence Report, newest first.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_daily_report",
        "description": "Text of a stored Nightly Intelligence Report for one date. Give a symbol to get only the lines "
                       "that mention it.",
        "parameters": {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"},
                                                        "symbol": {"type": "string"}},
                       "required": ["date"], "additionalProperties": False}}},
]

SYSTEM_PROMPT = (
    "You are the Sigmalytic Assistant for Sigmalytic Quant Corporation's administrator. You answer questions about "
    "the market using ONLY Sigmalytic's data, which you get by calling the lookups. Never answer from memory, and "
    "never use outside knowledge about prices, news or companies beyond what a lookup returns.\n"
    "Rules:\n"
    "1. Call lookups before answering any question about stocks, levels, signals or reports. If the data does not "
    "answer the question, say exactly what is missing (for example, only the latest scan is stored).\n"
    "2. Copy every number exactly as a lookup returned it. Do not round, add, subtract, average or compute new "
    "numbers; counts must come from total_matched or counts_by_signal. Dates may be written out in words.\n"
    "3. Describe; never advise. No buy, sell, hold or short suggestions, no predictions, no price targets, no "
    "promises.\n"
    "4. Call the platform's analysis \"Sigmalytic's scan\" or \"Sigmalytic's framework\". Never write the words "
    "Wyckoff or Weis. Never describe formulas, thresholds, scores, calibration or how levels are calculated.\n"
    "5. Be brief and clear for a busy reader: a one-line answer first, then a short list or small table when it helps. "
    "Plain markdown only. Do not add a disclaimer; one is added separately.\n"
    "6. Say which scan or report date the data comes from."
)


# ───────────────────────────── checks ─────────────────────────────

def check_answer(answer: str, evidence: Any) -> List[str]:
    """Problems that stop an answer from being shown. Empty list = the answer passes."""
    problems: List[str] = []
    bad_nums = ch.numbers_trace_to_facts(answer, evidence)
    if bad_nums:
        problems.append("numbers not found in the lookup results: " + ", ".join(sorted(set(bad_nums))[:12]))
    banned = ch.find_banned_phrases(answer)
    if banned:
        problems.append("advice or promise wording: " + ", ".join(banned))
    method = ch.method_words_in(answer)
    if method:
        problems.append("method words: " + ", ".join(method))
    if EXTRA_BLOCKED.search(answer):
        problems.append("the words Wyckoff or Weis")
    return problems


# ───────────────────────────── spending cap ─────────────────────────────

_LOCAL_SPEND: Dict[str, float] = {}


def _day() -> str:
    return datetime.now(timezone.utc).astimezone(ET).date().isoformat()


def _limits() -> Tuple[float, int]:
    try:
        usd = float(os.getenv("ASSISTANT_DAILY_LIMIT_USD", "5") or 5)
    except ValueError:
        usd = 5.0
    try:
        qs = int(os.getenv("ASSISTANT_DAILY_QUESTIONS", "100") or 100)
    except ValueError:
        qs = 100
    return usd, qs


def spent_today() -> Tuple[float, int]:
    day = _day()
    r = _redis()
    if r is not None:
        try:
            return float(r.get(SPEND_KEY.format(day=day)) or 0), int(r.get(COUNT_KEY.format(day=day)) or 0)
        except Exception:
            pass
    return _LOCAL_SPEND.get("usd:" + day, 0.0), int(_LOCAL_SPEND.get("n:" + day, 0))


def _record_spend(usd: Optional[float]) -> None:
    day = _day()
    r = _redis()
    if r is not None:
        try:
            if usd:
                r.incrbyfloat(SPEND_KEY.format(day=day), round(usd, 6))
            r.incr(COUNT_KEY.format(day=day))
            for k in (SPEND_KEY, COUNT_KEY):
                r.expire(k.format(day=day), 3 * 86400)
            return
        except Exception:
            pass
    _LOCAL_SPEND["usd:" + day] = _LOCAL_SPEND.get("usd:" + day, 0.0) + (usd or 0.0)
    _LOCAL_SPEND["n:" + day] = _LOCAL_SPEND.get("n:" + day, 0) + 1


def price_for(model: str) -> Optional[Tuple[float, float]]:
    """USD per million tokens (input, output) from content_hub.MODEL_PRICES; dated model ids match their base name."""
    best = None
    for name, price in ch.MODEL_PRICES.items():
        if model == name or model.startswith(name + "-"):
            if best is None or len(name) > len(best[0]):
                best = (name, price)
    return best[1] if best else None


# ───────────────────────────── the model call ─────────────────────────────

# ───────────────────────────── the model call (Claude or ChatGPT) ─────────────────────────────

def _post(url: str, payload: Dict[str, Any], headers: Dict[str, str], optional_key: Optional[str]) -> Any:
    """POST with the retries both providers need: wait on 429/529, and drop an optional setting a model rejects
    with 400 (a 400 is not billed)."""
    import requests
    for attempt in range(3):
        r = requests.post(url, json=payload, headers=headers, timeout=90)
        status = getattr(r, "status_code", 200)
        if status == 400 and optional_key and optional_key in payload and attempt < 2:
            payload.pop(optional_key, None)
            continue
        if status in (429, 529) and attempt < 2:
            try:
                wait = min(float(r.headers.get("retry-after", "10")), 30.0)
            except (TypeError, ValueError):
                wait = 10.0
            time.sleep(wait)
            continue
        break
    return r


def _raise_for(r: Any, who: str) -> None:
    status = getattr(r, "status_code", 200)
    if status >= 400:
        try:
            detail = str((r.json().get("error") or {}).get("message") or "")
        except Exception:
            detail = ""
        raise RuntimeError(f"{who} returned {status}" + (f": {detail}" if detail else "."))


def anthropic_tools() -> List[Dict[str, Any]]:
    return [{"name": t["function"]["name"], "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]} for t in TOOLS]


def parse_anthropic(body: Dict[str, Any]) -> Dict[str, Any]:
    """Claude Messages API reply -> one provider-neutral turn."""
    content = body.get("content") or []
    u = body.get("usage") or {}
    tokens_in = sum(int(u.get(k, 0) or 0) for k in ("input_tokens", "cache_read_input_tokens",
                                                    "cache_creation_input_tokens"))
    calls = [{"id": b.get("id"), "name": b.get("name", ""), "input": b.get("input"), "input_error": None}
             for b in content if b.get("type") == "tool_use"]
    return {"text": "".join(b.get("text", "") for b in content if b.get("type") == "text").strip(),
            "calls": calls, "in": tokens_in, "out": int(u.get("output_tokens", 0) or 0),
            "reasoning": int((u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0),
            "assistant_message": {"role": "assistant", "content": content}}


def parse_openai(body: Dict[str, Any]) -> Dict[str, Any]:
    """ChatGPT Chat Completions reply -> one provider-neutral turn."""
    msg = (body.get("choices") or [{}])[0].get("message") or {}
    u = body.get("usage") or {}
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        try:
            args, err = json.loads(fn.get("arguments") or "{}"), None
        except ValueError as exc:
            args, err = None, f"arguments were not valid JSON: {exc}"
        calls.append({"id": c.get("id"), "name": fn.get("name", ""), "input": args, "input_error": err})
    return {"text": (msg.get("content") or "").strip(), "calls": calls,
            "in": int(u.get("prompt_tokens", 0) or 0), "out": int(u.get("completion_tokens", 0) or 0),
            "reasoning": int((u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0),
            "assistant_message": {"role": "assistant", "content": msg.get("content") or "",
                                  **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})}}


def _call_model(provider: str, messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    """One model turn. `messages` holds the conversation in the provider's own format (no system message)."""
    if provider == "anthropic":
        payload: Dict[str, Any] = {"model": model, "max_tokens": 4000, "system": SYSTEM_PROMPT,
                                   "messages": messages, "tools": anthropic_tools()}
        effort = (os.getenv("ASSISTANT_EFFORT") or "").strip().lower()
        if effort:
            payload["output_config"] = {"effort": effort}
        r = _post("https://api.anthropic.com/v1/messages", payload,
                  {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}, "output_config")
        _raise_for(r, "Anthropic")
        return parse_anthropic(r.json())
    payload = {"model": model, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
               "tools": TOOLS, "tool_choice": "auto", "max_completion_tokens": 6000}
    effort = (os.getenv("ASSISTANT_EFFORT") or os.getenv("ASSISTANT_REASONING_EFFORT") or "").strip().lower()
    if effort:
        payload["reasoning_effort"] = effort
    r = _post(OPENAI_URL, payload, {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                                    "Content-Type": "application/json"}, "reasoning_effort")
    _raise_for(r, "OpenAI")
    return parse_openai(r.json())


def tool_results_messages(provider: str, results: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Lookup results, in the provider's format: Claude takes one user turn of tool_result blocks, ChatGPT one
    tool message per call."""
    if provider == "anthropic":
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": cid, "content": text}
                                             for cid, text in results]}]
    return [{"role": "tool", "tool_call_id": cid, "content": text} for cid, text in results]


def _clean_history(history: Any) -> List[Dict[str, str]]:
    """Keeps plain user/assistant text turns only, starting with a user turn, with back-to-back turns of the same
    role merged (Claude requires the roles to alternate)."""
    out: List[Dict[str, str]] = []
    for m in history if isinstance(history, list) else []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][:4000]})
    out = out[-MAX_HISTORY_MESSAGES:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    merged: List[Dict[str, str]] = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1] = {"role": m["role"], "content": merged[-1]["content"] + "\n\n" + m["content"]}
        else:
            merged.append(m)
    if merged and merged[-1]["role"] == "user":   # the new question follows; never two user turns in a row
        merged.pop()
    return merged


def _summary(name: str, args: Dict[str, Any], result: Dict[str, Any]) -> str:
    bits = [f"{k}={v}" for k, v in args.items() if v not in (None, "", [], False)]
    tail = ""
    if "total_matched" in result:
        tail = f" → {result['total_matched']} matched"
    elif result.get("ok") is False:
        tail = " → " + str(result.get("error") or result.get("reason") or "no data")[:80]
    return f"{name}({', '.join(bits)}){tail}"


def _run_lookup(call: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    args: Dict[str, Any] = {}
    try:
        if call.get("input_error"):
            raise ValueError(call["input_error"])
        if not isinstance(call.get("input"), dict):
            raise ValueError("arguments must be an object")
        args = call["input"]
        func = TOOL_FUNCS.get(call.get("name", ""))
        if func is None:
            raise ValueError(f"unknown lookup {call.get('name')}")
        return args, func(**args)
    except Exception as exc:
        return args, {"ok": False, "error": str(exc)[:200]}


def ask(question: str, history: Any = None, admin: str = "") -> Dict[str, Any]:
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "error": "Type a question first."}
    if len(q) > MAX_QUESTION_CHARS:
        return {"ok": False, "error": f"Keep questions under {MAX_QUESTION_CHARS} characters."}
    provider = provider_name()
    if provider is None:
        return {"ok": False, "error": "No AI key is set on the backend service in Render (ANTHROPIC_API_KEY for "
                                      "Claude, or OPENAI_API_KEY for ChatGPT)."}
    key = KEY_ENV[provider]
    if not os.getenv(key):
        return {"ok": False, "error": f"{key} is not set on the backend service in Render."}
    cap_usd, cap_n = _limits()
    usd_today, n_today = spent_today()
    if n_today >= cap_n or usd_today >= cap_usd:
        return {"ok": False, "error": f"Today's assistant limit is reached (${usd_today:.2f} of ${cap_usd:.2f}, "
                                      f"{n_today} of {cap_n} questions). It resets at midnight Eastern."}

    model = model_name(provider)
    hist = _clean_history(history)
    messages: List[Dict[str, Any]] = [*hist, {"role": "user", "content": q}]
    evidence: Dict[str, Any] = {"question": q, "conversation": [m["content"] for m in hist], "lookups": []}
    lookups: List[str] = []
    tokens_in = tokens_out = reasoning = 0
    started = time.time()
    answer, problems, rewrote = "", [], False
    error = None

    try:
        rounds = 0
        while rounds < MAX_ROUNDS + 1:
            if time.time() - started > DEADLINE_SECONDS:
                error = "The question took too long to answer. Try a narrower question."
                break
            rounds += 1
            turn = _call_model(provider, messages, model)
            tokens_in += turn["in"]
            tokens_out += turn["out"]
            reasoning += turn["reasoning"]
            if turn["calls"] and rounds <= MAX_ROUNDS:
                messages.append(turn["assistant_message"])
                results: List[Tuple[str, str]] = []
                for c in turn["calls"]:
                    args, result = _run_lookup(c)
                    evidence["lookups"].append(result)
                    lookups.append(_summary(c.get("name", ""), args, result))
                    text = json.dumps(result, default=str)
                    if len(text) > MAX_TOOL_RESULT_CHARS:
                        text = text[:MAX_TOOL_RESULT_CHARS] + '... [cut: ask for fewer rows]'
                    results.append((c.get("id"), text))
                messages.extend(tool_results_messages(provider, results))
                continue
            answer = turn["text"]
            if not answer:
                error = "The model returned an empty answer."
                break
            problems = check_answer(answer, evidence)
            if problems and not rewrote:
                rewrote = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content":
                                 "Your answer failed Sigmalytic's checks: " + "; ".join(problems) + ". Rewrite it. "
                                 "Use only numbers exactly as the lookups returned them, or leave them out, and "
                                 "follow every rule. Reply with the corrected answer only."})
                continue
            break
    except Exception as exc:
        error = str(exc)[:300]

    price = price_for(model)
    cost = None if price is None else round(tokens_in / 1e6 * price[0] + tokens_out / 1e6 * price[1], 5)
    _record_spend(cost)
    usage = {"provider": provider, "model": model, "input_tokens": tokens_in, "output_tokens": tokens_out,
             "reasoning_tokens": reasoning, "cost_usd": cost, "seconds": round(time.time() - started, 1)}

    if error:
        result = {"ok": False, "error": error, "lookups": lookups, "usage": usage}
    elif problems:
        result = {"ok": False, "withheld": True, "lookups": lookups, "usage": usage,
                  "error": "The answer was withheld because it failed Sigmalytic's checks (" + "; ".join(problems) +
                           "). Try rephrasing the question."}
    else:
        result = {"ok": True, "answer": answer, "disclaimer": DISCLAIMER, "lookups": lookups, "usage": usage,
                  "rewritten": rewrote}
    _log({"at": datetime.now(timezone.utc).isoformat(), "admin": admin, "question": q,
          "answer": answer, "shown": result["ok"], "problems": problems, "error": error,
          "lookups": lookups, "usage": usage})
    return result


def _log(entry: Dict[str, Any]) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.lpush(LOG_KEY, json.dumps(entry, default=str))
        r.ltrim(LOG_KEY, 0, LOG_KEEP - 1)
    except Exception:
        pass


def recent_log(limit: int = 50) -> Dict[str, Any]:
    r = _redis()
    if r is None:
        return {"ok": False, "error": "Redis not configured", "entries": []}
    try:
        raw = r.lrange(LOG_KEY, 0, max(0, min(int(limit), LOG_KEEP)) - 1)
        usd, n = spent_today()
        return {"ok": True, "entries": [json.loads(x) for x in raw],
                "today": {"cost_usd": round(usd, 4), "questions": n}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "entries": []}
