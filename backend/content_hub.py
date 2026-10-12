# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/content_hub.py
----------------------
Content Hub: turns one symbol's platform data into (1) a blog post for the
Research & Intelligence page and (2) one teaser draft per social platform.

Nothing here posts anywhere. Everything is a DRAFT for a human to review and
paste. Design rules:

* Facts come from the platform's own data (build_facts). Prose is either a
  deterministic template (no API key needed) or written by Claude, and in the
  AI case every number the model writes must trace back to the facts
  (numbers_trace_to_facts) or the draft is discarded for the template.
* Platform limits and a banned-phrase list are enforced in CODE (validate_teaser,
  find_banned_phrases), never left to a prompt.
* The disclaimer is added by code, never by the model.

Platform limits below were checked in October 2026 and DO change; keep them in
PLATFORM_RULES only so there is one place to update.
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

SITE_URL = os.getenv("CONTENT_HUB_SITE_URL", "https://sigmalyticquantcorp.com").rstrip("/")
BLOG_PATH = os.getenv("CONTENT_HUB_BLOG_PATH", "/research-and-intelligence").rstrip("/")
AI_MODEL = os.getenv("CONTENT_HUB_MODEL", "claude-sonnet-5-5")

DISCLAIMER = (
    "This material is provided solely for research and educational purposes. It does not constitute personalized "
    "investment advice, a recommendation, or an offer or solicitation to buy or sell any security. Market conditions "
    "can change rapidly, and historical or modeled observations do not guarantee future results."
)
SHORT_DISCLAIMER = "Educational research, not investment advice."

# Phrases that turn analysis into advice or a promise. Matched case-insensitively on word boundaries.
BANNED_PATTERNS = [
    r"guarantee[ds]?", r"risk[- ]free", r"can'?t lose", r"sure thing", r"no[- ]brainer",
    r"will (?:rise|fall|go up|go down|soar|crash|moon|rally|drop|surge|explode)",
    r"going to (?:rise|fall|go up|go down|soar|crash|moon|rally|drop|surge|explode)",
    r"you (?:should|must|need to) (?:buy|sell|short)", r"\bbuy now\b", r"\bsell now\b",
    r"\bmust[- ]buy\b", r"\bto the moon\b", r"\bfree money\b", r"\bpick of the (?:day|week)\b",
    r"\bI recommend\b", r"\bwe recommend\b", r"\bprice target\b",
]
_BANNED_RE = re.compile("|".join(f"(?:{p})" for p in BANNED_PATTERNS), re.IGNORECASE)

# Per-platform rules. "max_chars" is the limit the draft must meet (the safe working limit, which can be
# stricter than the platform's absolute maximum). Verify against each platform's docs before relying on it.
PLATFORM_RULES: Dict[str, Dict[str, Any]] = {
    "linkedin": {"label": "LinkedIn", "max_chars": 1300, "max_hashtags": 3, "link": "end of post or first comment",
                 "image": "1200x627 chart image (or 1080x1080)"},
    "x": {"label": "X", "max_chars": 280, "max_hashtags": 2, "link": "in a reply (link posts cost far more via the API)",
          "image": "1600x900 chart image", "link_weight": 23},
    "reddit": {"label": "Reddit", "max_chars": 3000, "title_max": 300, "max_hashtags": 0,
               "link": "in a comment, only where the subreddit allows it; read its rules first",
               "image": "optional chart image"},
    "pinterest": {"label": "Pinterest", "max_chars": 500, "title_max": 100, "max_hashtags": 3,
                  "link": "the pin's destination link", "image": "1000x1500 (2:3) vertical chart graphic"},
    "facebook": {"label": "Facebook", "max_chars": 500, "max_hashtags": 2,
                 "link": "test link in post vs first comment", "image": "1200x630 chart image"},
    "tiktok": {"label": "TikTok", "max_chars": 2200, "max_hashtags": 5,
               "link": "link in bio (captions are not clickable)", "image": "1080x1920 (9:16) video or photo carousel"},
}
PLATFORM_ORDER = ["linkedin", "x", "reddit", "pinterest", "facebook", "tiktok"]


# ───────────────────────────── facts ─────────────────────────────

def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if x != x or x in (float("inf"), float("-inf")) else x
    except Exception:
        return None


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or not b:
        return None
    return round((a - b) / b * 100, 2)


def facts_from_chart_data(symbol: str, chart: Dict[str, Any]) -> Dict[str, Any]:
    """Pure function: turns the /api/weis-radar/chart payload into the facts the content is allowed to use."""
    bars = chart.get("bars") or []
    closes = [_f(b.get("close")) for b in bars]
    highs = [_f(b.get("high")) for b in bars]
    lows = [_f(b.get("low")) for b in bars]
    vols = [_f(b.get("volume")) for b in bars]
    if len(bars) < 21 or closes[-1] is None:
        raise ValueError(f"Not enough price history for {symbol}.")
    last = closes[-1]

    def back(n: int) -> Optional[float]:
        return closes[-1 - n] if len(closes) > n else None

    window_h = [h for h in highs[-252:] if h is not None]
    window_l = [l for l in lows[-252:] if l is not None]
    hi, lo = (max(window_h) if window_h else None), (min(window_l) if window_l else None)
    sma20 = sum(c for c in closes[-20:] if c is not None) / max(1, len([c for c in closes[-20:] if c is not None]))
    v20 = [v for v in vols[-21:-1] if v is not None]
    avg_v20 = sum(v20) / len(v20) if v20 else None
    vol_ratio = round(vols[-1] / avg_v20, 2) if (vols[-1] is not None and avg_v20) else None

    hits = []
    for h in (chart.get("hits") or [])[:6]:
        hits.append({"type": str(h.get("type") or "").replace("_", " ").title(),
                     "date": str(h.get("date") or "")[:10], "level": _f(h.get("level") or h.get("price"))})

    wl = chart.get("weis_lines") or {}

    def sma(n: int) -> Optional[float]:
        w = [c for c in closes[-n:] if c is not None]
        return round(sum(w) / len(w), 2) if len(closes) >= n and w else None

    def span(n: int):
        h = [x for x in highs[-n:] if x is not None]
        l = [x for x in lows[-n:] if x is not None]
        return (round(max(h), 2) if h else None), (round(min(l), 2) if l else None)

    sma50, sma200 = sma(50), sma(200)
    hi20, lo20 = span(20)
    hi60, lo60 = span(60)
    facts = {
        "symbol": symbol.upper(),
        "as_of": str(bars[-1].get("date") or "")[:10],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "last_close": round(last, 2),
        "change_1d_pct": _pct(last, back(1)),
        "change_5d_pct": _pct(last, back(5)),
        "change_20d_pct": _pct(last, back(20)),
        "high_52w": round(hi, 2) if hi else None,
        "low_52w": round(lo, 2) if lo else None,
        "from_high_pct": _pct(last, hi),
        "from_low_pct": _pct(last, lo),
        "sma20": round(sma20, 2),
        "vs_sma20_pct": _pct(last, sma20),
        "sma50": sma50, "vs_sma50_pct": _pct(last, sma50),
        "sma200": sma200, "vs_sma200_pct": _pct(last, sma200),
        "change_60d_pct": _pct(last, back(60)),
        "high_20d": hi20, "low_20d": lo20, "high_60d": hi60, "low_60d": lo60,
        "volume_vs_20d_avg": vol_ratio,
        "pattern_signals": hits,
        "call_wall": _f(chart.get("call_wall")),
        "put_wall": _f(chart.get("put_wall")),
        "gamma_flip": _f(chart.get("gamma_flip")),
        "ice_line": _f(wl.get("ice_line_level")) if isinstance(wl, dict) else None,
        "bars_used": len(bars),
        "session_high": round(highs[-1], 2) if highs[-1] is not None else None,
        "session_low": round(lows[-1], 2) if lows[-1] is not None else None,
        "prev_close": round(back(1), 2) if back(1) is not None else None,
        "timeframes": {},
    }
    facts["levels"] = key_levels(facts)
    return facts


# Extra timeframes read alongside the daily bars: (key, platform timeframe, bars requested).
EXTRA_TIMEFRAMES = [("weekly", "1Week", 104), ("4h", "4Hour", 160), ("2h", "2Hour", 200)]
TF_LABELS = {"weekly": "weekly", "4h": "4-hour", "2h": "2-hour"}


def timeframe_facts(chart: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Pure: reduces one extra timeframe's chart payload to the few facts the report may use."""
    bars = chart.get("bars") or []
    closes = [_f(b.get("close")) for b in bars]
    highs = [_f(b.get("high")) for b in bars]
    lows = [_f(b.get("low")) for b in bars]
    vols = [_f(b.get("volume")) for b in bars]
    if len(bars) < 21 or closes[-1] is None:
        raise ValueError(f"Not enough {label} bars.")
    last = closes[-1]

    def sma(n: int) -> Optional[float]:
        w = [c for c in closes[-n:] if c is not None]
        return round(sum(w) / len(w), 2) if len(closes) >= n and w else None

    def span(n: int):
        h = [x for x in highs[-n:] if x is not None]
        l = [x for x in lows[-n:] if x is not None]
        return (round(max(h), 2) if h else None), (round(min(l), 2) if l else None)

    def back(n: int) -> Optional[float]:
        return closes[-1 - n] if len(closes) > n else None

    # The newest weekly / 4-hour / 2-hour bar is often still forming, which makes its volume look tiny. The ratio is
    # therefore taken on the previous bar, which is complete, against the 20 bars before it.
    v20 = [v for v in vols[-22:-2] if v is not None]
    vol_ratio = round(vols[-2] / (sum(v20) / len(v20)), 2) if (len(vols) >= 23 and v20 and vols[-2] is not None and sum(v20)) else None
    wl = chart.get("weis_lines") if isinstance(chart.get("weis_lines"), dict) else {}
    pivots = sorted((wl.get("pivots") or []), key=lambda p: p.get("bar_index", 0))[-6:]
    sma20, sma50 = sma(20), sma(50)
    h20, l20 = span(20)
    h60, l60 = span(60)
    return {
        "label": label, "bars_used": len(bars), "last_bar": str(bars[-1].get("date") or "")[:16],
        "last_close": round(last, 2), "change_5_bars_pct": _pct(last, back(5)), "change_20_bars_pct": _pct(last, back(20)),
        "sma20": sma20, "vs_sma20_pct": _pct(last, sma20), "sma50": sma50, "vs_sma50_pct": _pct(last, sma50),
        "high_20_bars": h20, "low_20_bars": l20, "high_60_bars": h60, "low_60_bars": l60,
        "prior_bar_volume_vs_20_bar_avg": vol_ratio, "ice_line": _f(wl.get("ice_line_level")),
        "recent_pivots": [{"kind": str(p.get("kind")), "price": _f(p.get("price"))} for p in pivots if _f(p.get("price"))],
        "pattern_signals": [{"type": str(h.get("type") or "").replace("_", " ").title(), "level": _f(h.get("level") or h.get("price"))}
                            for h in (chart.get("hits") or [])[:3]],
    }


def key_levels(f: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Nearest reference levels above and below the last close, gathered from every timeframe in the facts."""
    px = f.get("last_close")
    cands: List[Any] = []

    def add(price: Any, label: str) -> None:
        v = _f(price)
        if v:
            cands.append((round(v, 2), label))

    for k, lab in (("sma20", "20-day average"), ("sma50", "50-day average"), ("sma200", "200-day average"),
                   ("high_20d", "20-day high"), ("low_20d", "20-day low"), ("high_60d", "60-day high"),
                   ("low_60d", "60-day low"), ("high_52w", "52-week high"), ("low_52w", "52-week low"),
                   ("call_wall", "largest call-open-interest strike"), ("put_wall", "largest put-open-interest strike"),
                   ("gamma_flip", "estimated gamma flip level"), ("ice_line", "daily ice line")):
        add(f.get(k), lab)
    for x in (f.get("pattern_signals") or []):
        add(x.get("level"), f"daily {x.get('type', 'pattern')} flag level")
    for key, tf in (f.get("timeframes") or {}).items():
        name = TF_LABELS.get(key, key)
        for k, lab in (("sma20", "20-bar average"), ("high_20_bars", "20-bar high"), ("low_20_bars", "20-bar low"),
                       ("ice_line", "ice line")):
            add(tf.get(k), f"{name} {lab}")
        for pv in tf.get("recent_pivots") or []:
            add(pv.get("price"), f"{name} {str(pv.get('kind')).replace('_', ' ')}")
    if not px:
        return {"above": [], "below": []}
    seen: List[float] = []
    uniq = []
    for price, lab in cands:
        if any(abs(price - s) <= max(0.01, s * 0.001) for s in seen):
            continue
        seen.append(price)
        uniq.append({"price": price, "label": lab})
    above = sorted([c for c in uniq if c["price"] > px], key=lambda c: c["price"])[:5]
    below = sorted([c for c in uniq if c["price"] <= px], key=lambda c: -c["price"])[:5]
    return {"above": above, "below": below}


def attach_timeframes(f: Dict[str, Any], charts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    tfs, missing = {}, []
    for key, chart in charts.items():
        try:
            if not chart.get("ok"):
                raise ValueError(chart.get("error") or "no data")
            tfs[key] = timeframe_facts(chart, TF_LABELS.get(key, key))
        except Exception as e:
            missing.append(f"{TF_LABELS.get(key, key)} ({str(e)[:60]})")
    f["timeframes"] = tfs
    f["timeframes_missing"] = missing
    f["levels"] = key_levels(f)
    return f


def build_facts(symbol: str) -> Dict[str, Any]:
    """Fetches live data through the existing chart endpoint function and reduces it to facts."""
    from backend.main import weis_radar_chart_data  # lazy: avoids a circular import at module load
    sym = symbol.upper().strip()
    chart = weis_radar_chart_data(sym, timeframe="1Day", limit=400)  # 400 so the 200-day line spans the whole chart image
    if not chart.get("ok"):
        raise ValueError(chart.get("error") or f"No data for {symbol}.")
    f = facts_from_chart_data(symbol, chart)
    f["_chart_bars"] = [[str(b.get("date"))[:10], b.get("open"), b.get("high"), b.get("low"), b.get("close"), b.get("volume")]
                        for b in (chart.get("bars") or [])]
    extra: Dict[str, Dict[str, Any]] = {}
    for key, tf, limit in EXTRA_TIMEFRAMES:
        for attempt in range(2):  # one retry per timeframe
            try:
                extra[key] = weis_radar_chart_data(sym, timeframe=tf, limit=limit, include_options=False)
            except Exception as e:
                extra[key] = {"ok": False, "error": str(e)}
            if extra[key].get("ok"):
                break
    f = attach_timeframes(f, extra)
    if "weekly" not in f["timeframes"]:  # the weekly view is required; stop before any AI cost is incurred
        why = next((m for m in f["timeframes_missing"] if m.startswith("weekly")), "weekly (no data)")
        raise ValueError(f"Weekly data could not be loaded for {sym}: {why}. No report was generated and nothing was charged.")
    return f


# ───────────────────────────── formatting helpers ─────────────────────────────

def _usd(v: Optional[float]) -> str:
    return f"${v:,.2f}" if v is not None else "n/a"


def _sgn(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:+.2f}%"


def _slug(symbol: str, as_of: str) -> str:
    return f"{symbol.lower()}-market-structure-{as_of or datetime.now(timezone.utc).strftime('%Y-%m-%d')}"


def blog_url(symbol: str, as_of: str) -> str:
    return f"{SITE_URL}{BLOG_PATH}/{_slug(symbol, as_of)}"


def tracked_url(platform: str, symbol: str, as_of: str) -> str:
    q = urlencode({"utm_source": platform, "utm_medium": "social", "utm_campaign": f"{symbol.lower()}-{as_of}",
                   "utm_content": "teaser"})
    return f"{blog_url(symbol, as_of)}?{q}"


def _trend_word(f: Dict[str, Any]) -> str:
    v = f.get("vs_sma20_pct")
    if v is None:
        return "mixed"
    return "above" if v > 0 else "below"


def _signal_phrase(f: Dict[str, Any]) -> str:
    sig = f.get("pattern_signals") or []
    if not sig:
        return "no recent Wyckoff/Weis pattern flags"
    s = sig[0]
    where = f" near {_usd(s['level'])}" if s.get("level") else ""
    when = f" on {s['date']}" if s.get("date") else ""
    return f"a {s['type']} flag{where}{when}"


# ───────────────────────────── numbers guard / compliance ─────────────────────────────

_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


def _num_tokens(text: str) -> List[float]:
    out = []
    for m in _NUM_RE.findall(text or ""):
        try:
            out.append(float(m.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def _allowed_numbers(facts: Dict[str, Any]) -> List[float]:
    nums: List[float] = []

    def walk(x: Any):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            nums.append(abs(float(x)))
        elif isinstance(x, str):
            nums.extend(_num_tokens(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(facts)
    nums.extend([20, 50, 52, 60, 200, 252])  # window lengths named in the copy ("20-day average", "52-week range")
    return nums


def numbers_trace_to_facts(text: str, facts: Dict[str, Any]) -> List[str]:
    """Returns the numbers in `text` that do not appear in the facts. Small counts (<=10) and years are allowed."""
    allowed = _allowed_numbers(facts)
    bad = []
    for n in _num_tokens(text):
        if n <= 10 or 1990 <= n <= 2100:
            continue
        if not any(abs(n - a) <= max(0.011, abs(a) * 0.0005) for a in allowed):
            bad.append(f"{n:g}")
    return bad


def find_banned_phrases(text: str) -> List[str]:
    return sorted({m.group(0) for m in _BANNED_RE.finditer(text or "")})


def _hashtags(text: str) -> List[str]:
    return re.findall(r"(?<!\w)#\w+", text or "")


def weighted_len(platform: str, text: str) -> int:
    """X counts every URL as a fixed 23 characters."""
    if platform != "x":
        return len(text)
    w = PLATFORM_RULES["x"]["link_weight"]
    return len(re.sub(r"https?://\S+", "x" * w, text))


def validate_teaser(platform: str, draft: Dict[str, Any], facts: Optional[Dict[str, Any]] = None) -> List[str]:
    rules = PLATFORM_RULES[platform]
    issues: List[str] = []
    text = draft.get("text") or ""
    n = weighted_len(platform, text)
    if n > rules["max_chars"]:
        issues.append(f"{n} characters; limit is {rules['max_chars']}.")
    if not text.strip():
        issues.append("Empty text.")
    tags = _hashtags(text)
    if len(tags) > rules["max_hashtags"]:
        issues.append(f"{len(tags)} hashtags; limit is {rules['max_hashtags']}.")
    title = draft.get("title")
    if "title_max" in rules and title is not None and len(title) > rules["title_max"]:
        issues.append(f"Title is {len(title)} characters; limit is {rules['title_max']}.")
    if "title_max" in rules and not title:
        issues.append("Missing title.")
    banned = find_banned_phrases(" ".join([text, title or "", draft.get("reply") or ""]))
    if banned:
        issues.append("Advice/promise wording: " + ", ".join(banned))
    if platform in ("x", "reddit", "tiktok") and re.search(r"https?://", text):
        issues.append("Link is in the main text; this platform wants it elsewhere (see link placement).")
    if facts is not None:
        bad = numbers_trace_to_facts(" ".join([text, title or ""]), facts)
        if bad:
            issues.append("Numbers not found in the data: " + ", ".join(bad))
    return issues


# ───────────────────────────── blog ─────────────────────────────

SITE_LINK_TEXT = "www.sigmalyticquantcorp.com"
SITE_LINK_HREF = "https://www.sigmalyticquantcorp.com"
TAGLINES = ["Better Opportunities. Better Decisions. Better Trading Results.",
            "Every decision creates information. Every outcome creates evidence."]
DATA_SOURCE = os.getenv("CONTENT_HUB_DATA_SOURCE", "Alpaca Markets")

# The three headline options. Used verbatim by code, only when the assessment (and, for A, a sourced
# institutional finding) supports them. Otherwise the model's more accurate alternative headline is used.
OPTION_TITLES = {
    "A": "{s} Order Flow Divergence: Institutional Dark-Pool Accumulation Defends Critical Macro Trend",
    "B": "{s} Trend Geometry Facing Immediate Strain as Short-Duration Selling Overwhelms Order Book",
    "C": "{s} Liquidity Mapping Signals Imminent Volatility Squeeze at Key Volume-Weighted Pivot",
}
DATA_LIMITS = ("Evidence available to this tool: daily price and volume bars, pattern flags, and option-level references. "
               "There is no order-book, tape, block-trade or dark-pool feed, so Options A, B and C can only be "
               "supported by sourced online findings or by what the daily bars alone show.")
NEWS_HEADINGS = {"us": "U.S. Market and Economic Developments", "international": "International Developments",
                 "geopolitical": "Geopolitical Developments", "company": "{s} Company and Industry News",
                 "institutional": "Institutional and Liquidity Evidence"}
SUMMARY_LABELS = [("condition", "Current condition"), ("risk", "Principal risk"),
                  ("strengthen", "What would strengthen the bullish case"),
                  ("weaken", "What would weaken it"), ("monitor", "What traders should monitor next")]


def attribution_text() -> str:
    return (f"Underlying market data used in this report were obtained through {DATA_SOURCE}. {DATA_SOURCE} distributes "
            "market data from multiple securities exchanges and market-data providers.\n\n"
            "Sigmalytic Quant Corporation's proprietary analytical framework was used to interpret the supplied market "
            "information. Proprietary formulas, calibration procedures, internal thresholds, scoring methodology, "
            "computational logic, and analytical calculations are intentionally excluded from this public report.")


def _long_date(d: str) -> str:
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%B %-d, %Y")
    except Exception:
        return d


def _template_summary(f: Dict[str, Any]) -> Dict[str, str]:
    s, trend = f["symbol"], _trend_word(f)
    return {
        "condition": (f"{s} closed at {_usd(f['last_close'])} on {f['as_of']}, {trend} its 20-day average of "
                      f"{_usd(f['sma20'])}, with a {_sgn(f['change_20d_pct'])} move over twenty sessions."),
        "risk": (f"The principal risk is a failure to hold the 20-day average at {_usd(f['sma20'])}, which would bring the "
                 f"recent low near {_usd(f.get('low_20d'))} back into view."),
        "strengthen": (f"A sustained close above the 20-day high near {_usd(f.get('high_20d'))}, supported by volume above "
                       "its 20-day average, would strengthen the bullish case."),
        "weaken": (f"A close below the 20-day low near {_usd(f.get('low_20d'))}, particularly on heavier volume, would "
                   "weaken it."),
        "monitor": (f"Traders should monitor the 20-day average at {_usd(f['sma20'])}, the 60-day range from "
                    f"{_usd(f.get('low_60d'))} to {_usd(f.get('high_60d'))}, and volume against its 20-day average."),
    }


def _template_image_text(f: Dict[str, Any]) -> Dict[str, str]:
    wk = (f.get("timeframes") or {}).get("weekly") or {}
    vol = []
    if f.get("volume_vs_20d_avg") is not None:
        vol.append(f"Daily volume ran {f['volume_vs_20d_avg']:.2f} times its 20-day average.")
    if wk.get("prior_bar_volume_vs_20_bar_avg") is not None:
        vol.append(f"The previous weekly bar ran {wk['prior_bar_volume_vs_20_bar_avg']:.2f} times its 20-week average.")
    return {"view": _template_summary(f)["condition"], "volume": " ".join(vol)}


def _norm_private(p: Any) -> Dict[str, Any]:
    p = p if isinstance(p, dict) else {}
    out: Dict[str, Any] = {}
    for k in "ABC":
        v = p.get(k) if isinstance(p.get(k), dict) else {}
        out[k] = {"supported": bool(v.get("supported")), "reasoning": str(v.get("reasoning") or "")[:700]}
    sel = str(p.get("selected") or "none").strip().upper()
    out["selected"] = sel if sel in ("A", "B", "C") and out[sel]["supported"] else "none"
    out["data_limits"] = DATA_LIMITS
    return out


def template_blog(f: Dict[str, Any]) -> Dict[str, Any]:
    s, name = f["symbol"], f["symbol"]
    trend = _trend_word(f)
    title = f"{s} Market Structure: Price {trend} its 20-day average at {_usd(f['last_close'])}"
    meta = (f"{s} closed at {_usd(f['last_close'])} ({_sgn(f['change_1d_pct'])} on the day), "
            f"{_sgn(f['from_high_pct'])} from its 52-week high. Wyckoff/Weis pattern read, key levels and volume from Sigmalytic.")[:158]
    sections: List[Dict[str, str]] = []

    p = [f"{s} closed at {_usd(f['last_close'])} on {f['as_of']}, "
         f"{_sgn(f['change_1d_pct'])} on the day, {_sgn(f['change_5d_pct'])} over five sessions and "
         f"{_sgn(f['change_20d_pct'])} over twenty."]
    if f.get("vs_sma20_pct") is not None:
        p.append(f"Price sits {abs(f['vs_sma20_pct']):.2f}% {trend} its 20-day average of {_usd(f['sma20'])}.")
    sections.append({"heading": "Where price stands", "body": " ".join(p)})

    r = []
    if f.get("high_52w") and f.get("low_52w"):
        r.append(f"Over the last year the stock has traded between {_usd(f['low_52w'])} and {_usd(f['high_52w'])}, "
                 f"so it is {_sgn(f['from_high_pct'])} from the high and {_sgn(f['from_low_pct'])} from the low.")
    if f.get("volume_vs_20d_avg") is not None:
        r.append(f"The latest session's volume was {f['volume_vs_20d_avg']:.2f} times its 20-day average.")
    sections.append({"heading": "Range and participation", "body": " ".join(r) or "Range data was not available."})

    sig = f.get("pattern_signals") or []
    if sig:
        items = "; ".join(
            f"{x['type']}" + (f" near {_usd(x['level'])}" if x.get("level") else "") + (f" ({x['date']})" if x.get("date") else "")
            for x in sig[:4])
        body = (f"Sigmalytic's Wyckoff/Weis scan flagged: {items}. These describe how price and volume behaved around "
                "a prior level; they are observations of past behavior, not forecasts.")
    else:
        body = "Sigmalytic's Wyckoff/Weis scan found no recent Spring, Upthrust, Breakout or Breakdown flags."
    sections.append({"heading": "Wyckoff/Weis pattern read", "body": body})

    lv = []
    if f.get("call_wall"):
        lv.append(f"The largest call-open-interest strike (call wall) is {_usd(f['call_wall'])}.")
    if f.get("put_wall"):
        lv.append(f"The largest put-open-interest strike (put wall) is {_usd(f['put_wall'])}.")
    if f.get("gamma_flip"):
        lv.append(f"The estimated gamma flip level is {_usd(f['gamma_flip'])}.")
    if f.get("ice_line"):
        lv.append(f"The platform's ice line (a Weis horizontal reference level) is {_usd(f['ice_line'])}.")
    if lv:
        sections.append({"heading": "Levels the platform is tracking", "body": " ".join(lv)})

    lvls = f.get("levels") or {}
    if lvls.get("above") or lvls.get("below"):
        parts = []
        if lvls.get("above"):
            parts.append("Nearest reference levels above the last close: " + "; ".join(
                f"{_usd(x['price'])} ({x['label']})" for x in lvls["above"][:3]) + ".")
        if lvls.get("below"):
            parts.append("Nearest reference levels below: " + "; ".join(
                f"{_usd(x['price'])} ({x['label']})" for x in lvls["below"][:3]) + ".")
        sections.append({"heading": "Key Levels", "body": " ".join(parts)})

    private = _norm_private({"selected": "none"})
    for k in "ABC":
        private[k]["reasoning"] = "Not assessed. Template mode makes no determination; run the draft with an AI key."
    return {"title": title, "meta_description": meta, "sections": sections, "summary": _template_summary(f),
            "news": {}, "sources": [], "private": private, "image_text": _template_image_text(f), "ai": False}


def _paras(text: str) -> List[str]:
    return [x.strip() for x in str(text).split("\n\n") if x.strip()]


def _render_blog(f: Dict[str, Any], blog: Dict[str, Any]) -> Dict[str, Any]:
    url = blog_url(f["symbol"], f["as_of"])
    esc = _html.escape
    year = (f.get("as_of") or f.get("generated_at") or "")[:4] or str(datetime.now(timezone.utc).year)
    summary = blog.get("summary") or _template_summary(f)
    news = blog.get("news") or {}
    analysis = list(blog["sections"])
    news_secs = [{"heading": NEWS_HEADINGS[k].format(s=f["symbol"]), "body": news[k]["text"]}
                 for k in ("us", "international", "geopolitical", "company", "institutional") if news.get(k)]
    # News sits just before the closing "what to watch" section, as in the house format.
    if analysis and analysis[-1]["heading"].lower().startswith("what traders"):
        sections = analysis[:-1] + news_secs + analysis[-1:]
    else:
        sections = analysis + news_secs
    sections.append({"heading": "Sigmalytic Summary", "body": "\n\n".join(
        f"{label}: {summary[k]}" for k, label in SUMMARY_LABELS if summary.get(k))})
    sources = [{"title": x["title"], "url": x["url"]} for x in (blog.get("sources") or [])]
    copyright_line = f"© {year} Sigmalytic Quant Corporation. All rights reserved."
    dates = f"Report Date: {_long_date(f.get('generated_at') or f['as_of'])}  ·  Market Data Through: {_long_date(f['as_of'])}"
    level_line = re.compile(r"^[A-Za-z0-9 \-–/'’,]{3,60}: ~?\$[\d,.\-–$ ]+$")

    def para_html(sec: Dict[str, str]) -> str:
        out = []
        for t in _paras(sec["body"]):
            if sec["heading"] == "Sigmalytic Summary" and ": " in t:
                lab, rest = t.split(": ", 1)
                out.append(f"<p><strong>{esc(lab)}:</strong> {esc(rest)}</p>")
            elif "\n" not in t and level_line.match(t):
                out.append(f"<p><strong>{esc(t)}</strong></p>")
            else:
                out.append(f"<p>{esc(t)}</p>")
        return "\n".join(out)

    body_html = "".join(f"<h2>{esc(s['heading'])}</h2>\n{para_html(s)}\n" for s in sections)
    attr = attribution_text().split("\n\n")
    src_html = f"<li>{esc(DATA_SOURCE)}: market data used for this report.</li>" + "".join(
        f"<li><a href=\"{esc(x['url'])}\" rel=\"nofollow noopener\">{esc(x['title'])}</a></li>" for x in sources)
    html_doc = (
        f"<!-- Paste into the Research & Intelligence page. Canonical: {url} -->\n"
        f"<article class=\"sigmalytic-research\">\n<h1>{esc(blog['title'])}</h1>\n"
        f"<p class=\"byline\">Sigmalytic Quant Corporation Market Structure Report<br>{esc(dates)}</p>\n{body_html}"
        f"<p><strong>{esc(TAGLINES[0])}</strong><br>{esc(TAGLINES[1])}</p>\n"
        f"<p><a href=\"{SITE_LINK_HREF}\">{SITE_LINK_TEXT}</a></p>\n"
        f"<h2>Market Data and Attribution</h2>\n" + "".join(f"<p>{esc(x)}</p>\n" for x in attr) +
        f"<h2>Reference Sources</h2>\n<ul>{src_html}</ul>\n<p class=\"copyright\">{esc(copyright_line)}</p>\n"
        f"<p class=\"disclaimer\"><em>{esc(DISCLAIMER)}</em></p>\n</article>"
    )
    md_parts = []
    for sec in sections:
        if sec["heading"] == "Sigmalytic Summary":
            ps = [("**" + t.split(": ", 1)[0] + ":** " + t.split(": ", 1)[1]) if ": " in t else t for t in _paras(sec["body"])]
            md_parts.append(f"## {sec['heading']}\n\n" + "\n\n".join(ps))
        else:
            md_parts.append(f"## {sec['heading']}\n\n{sec['body']}")
    md = (f"# {blog['title']}\n\nSigmalytic Quant Corporation Market Structure Report  \n{dates}\n\n" + "\n\n".join(md_parts) +
          f"\n\n**{TAGLINES[0]}**  \n{TAGLINES[1]}\n\n[{SITE_LINK_TEXT}]({SITE_LINK_HREF})\n\n"
          "## Market Data and Attribution\n\n" + "\n\n".join(attr) +
          f"\n\n## Reference Sources\n\n- {DATA_SOURCE}: market data used for this report.\n"
          + "".join(f"- [{x['title']}]({x['url']})\n" for x in sources) + f"\n{copyright_line}\n\n*{DISCLAIMER}*\n")
    from backend.content_seo import build_seo
    # Word and section counts for SEO cover the analysis and news only, not the summary or boilerplate.
    seo = build_seo(f, {**blog, "sections": [x for x in sections if x["heading"] != "Sigmalytic Summary"]}, url, SITE_URL, BLOG_PATH)
    return {**blog, "sections": sections, "slug": _slug(f["symbol"], f["as_of"]), "url": url, "html": html_doc,
            "markdown": md, "head_tags": seo["head_tags"], "seo": seo, "disclaimer": DISCLAIMER,
            "copyright": copyright_line, "sources": sources}


# ───────────────────────────── AI (optional) ─────────────────────────────

# USD per 1,000,000 tokens (input, output), from the providers' own pricing pages, checked 2026-10-11.
# A model missing from this table is reported with its exact token counts and "price not in table".
MODEL_PRICES: Dict[str, Any] = {
    "claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0),
    "claude-fable-5-1": (10.0, 50.0),
    "gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.0, 12.0), "gpt-5.6-sol": (5.0, 30.0),
}

_USAGE: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("content_hub_usage", default=None)


WEB_SEARCH_PRICE = 0.01  # USD per search ($10 per 1,000), from Anthropic's web search tool documentation
WEB_SEARCH_ON = os.getenv("CONTENT_HUB_WEB_SEARCH", "1").strip() != "0"
AI_EFFORT = (os.getenv("CONTENT_HUB_EFFORT", "low") or "low").strip().lower()  # Claude thinking effort; thinking is billed as output
WEB_SEARCH_MAX = int(os.getenv("CONTENT_HUB_MAX_SEARCHES", "4") or 4)


def _record_usage(provider: str, model: str, tokens_in: int, tokens_out: int, reasoning: int = 0, searches: int = 0) -> None:
    log = _USAGE.get()
    if log is not None:
        log.append({"provider": provider, "model": model, "input_tokens": int(tokens_in or 0),
                    "output_tokens": int(tokens_out or 0), "reasoning_tokens": int(reasoning or 0),
                    "searches": int(searches or 0)})


def summarize_usage(log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Exact token and search counts as reported by the API, and the dollar cost when the model's price is known."""
    tin = sum(c["input_tokens"] for c in log)
    tout = sum(c["output_tokens"] for c in log)
    searches = sum(c.get("searches", 0) for c in log)
    cost: Optional[float] = searches * WEB_SEARCH_PRICE
    for c in log:
        price = MODEL_PRICES.get(c["model"])
        if price is None:
            cost = None
            break
        cost += c["input_tokens"] / 1e6 * price[0] + c["output_tokens"] / 1e6 * price[1]
    return {"calls": len(log), "models": sorted({c["model"] for c in log}), "input_tokens": tin,
            "output_tokens": tout, "reasoning_tokens": sum(c["reasoning_tokens"] for c in log),
            "searches": searches, "cost_usd": None if cost is None else round(cost, 5)}


def ai_provider() -> Optional[str]:
    """'anthropic' or 'openai', whichever has a key. CONTENT_HUB_PROVIDER picks one when both are set."""
    want = (os.getenv("CONTENT_HUB_PROVIDER") or "").strip().lower()
    has = {"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")), "openai": bool(os.getenv("OPENAI_API_KEY"))}
    if want in has and has[want]:
        return want
    return "anthropic" if has["anthropic"] else ("openai" if has["openai"] else None)


def ai_available() -> bool:
    return ai_provider() is not None


class AIParseError(ValueError):
    """The model replied (and was billed) but the reply could not be read. Carries the raw text so it is never wasted."""

    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


def _repair_json(t: str) -> Optional[Dict[str, Any]]:
    """Closes a JSON object that was cut off mid-way, keeping everything that is complete."""
    start = t.find("{")
    if start < 0:
        return None
    t = t[start:]
    stack: List[str] = []
    in_str = esc = False
    cuts: List[Any] = []  # (position, closers) at every comma outside a string
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
        elif ch == ",":
            cuts.append((i, "".join(reversed(stack))))
    tries = [t + ('"' if in_str else "") + "".join(reversed(stack))]
    tries += [t[:pos] + closers for pos, closers in reversed(cuts)]
    for cand in tries:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _extract_json(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    fixed = _repair_json(text)
    if fixed is None:
        raise AIParseError("AI reply had no readable JSON object.", text)
    fixed["_recovered"] = True
    return fixed


def _ai_json(system: str, user: str, max_tokens: int = 2500, web_search: bool = False) -> Dict[str, Any]:
    import requests
    if ai_provider() == "openai":
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"},
            json={"model": os.getenv("CONTENT_HUB_OPENAI_MODEL", "gpt-5.5"),
                  "max_completion_tokens": max_tokens * 4,  # headroom for reasoning tokens on GPT-5 family models
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=120,
        )
        r.raise_for_status()
        body = r.json()
        u = body.get("usage") or {}
        _record_usage("openai", body.get("model") or os.getenv("CONTENT_HUB_OPENAI_MODEL", "gpt-5.5"),
                      u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                      (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
        return _extract_json(body["choices"][0]["message"]["content"] or "")
    messages: List[Dict[str, Any]] = [{"role": "user", "content": user}]
    seen: Dict[str, str] = {}
    text = ""
    truncated = False
    thinking_total = 0
    stop = None
    for _turn in range(3):  # a paused web-search turn is continued by sending it back, at most twice
        payload: Dict[str, Any] = {"model": AI_MODEL, "max_tokens": max_tokens, "system": system, "messages": messages}
        if AI_EFFORT in ("low", "medium", "high", "xhigh", "max"):
            payload["output_config"] = {"effort": AI_EFFORT}
        if web_search:
            payload["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_SEARCH_MAX}]
        for attempt in range(2):  # a 429 (rate limit) is not billed; wait as told, once
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json=payload, timeout=240 if web_search else 90)
            if getattr(r, "status_code", 200) == 400 and "output_config" in payload and attempt == 0:
                payload.pop("output_config", None)  # this model/account rejects the effort setting; a 400 is not billed
                continue
            if getattr(r, "status_code", 200) == 429 and attempt == 0:
                try:
                    wait = min(float(r.headers.get("retry-after", "20")), 45.0)
                except ValueError:
                    wait = 20.0
                time.sleep(wait)
                continue
            break
        r.raise_for_status()
        body = r.json()
        u = body.get("usage") or {}
        think = int((u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0)
        thinking_total += think
        _record_usage("anthropic", body.get("model") or AI_MODEL, u.get("input_tokens", 0), u.get("output_tokens", 0),
                      reasoning=think, searches=(u.get("server_tool_use") or {}).get("web_search_requests", 0))
        content = body.get("content", [])
        for b in content:
            if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                for x in b["content"]:
                    if isinstance(x, dict) and x.get("url"):
                        seen[x["url"]] = str(x.get("title") or x["url"])
        if body.get("stop_reason") == "pause_turn":
            messages = messages + [{"role": "assistant", "content": content}]
            continue
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        stop = body.get("stop_reason")
        truncated = stop == "max_tokens"
        break
    if "{" not in text:
        raise AIParseError("AI reply had no JSON object (stop reason: %s)." % body.get("stop_reason"), text)
    out = _extract_json(text)
    out["_stop"], out["_thinking"] = stop, thinking_total
    if truncated:
        out["_recovered"] = True
    if web_search:
        out["_search_results"] = seen
    return out


_AI_STYLE = (
    "You write for Sigmalytic Quant Corporation, a market-structure research firm (Wyckoff/Weis analysis). "
    "Voice: plain, precise, analytical, no hype. Observations only. Never advise, recommend, predict, or promise. "
    "Use ONLY the numbers in the FACTS JSON; do not compute new ones or add any other numbers. "
    "Do not write a disclaimer; it is added separately. Reply with one JSON object and nothing else."
)

_BLOG_STYLE = (
    "You write website research reports for Sigmalytic Quant Corporation, a market-structure research firm. "
    "Voice: professional, plain, precise, no hype. Observations only; never advise, recommend, predict, or promise. "
    "Spelling, grammar, punctuation, capitalization and commas must be correct. "
    "In the analysis sections and the summary, use ONLY numbers that appear in the FACTS JSON; never compute or add others. "
    "The proprietary platform data must not be disclosed: do not reveal or describe formulas, thresholds, calibration, "
    "scoring logic, internal calculations or methodology; state levels and observations only. "
    "Single vertical column: no tables, no side-by-side layout, no footnotes, no numbered notes, no markdown. "
    "Never repeat the same level, fact or conclusion in more than one section. "
    "Do not write a disclaimer, attribution, sources list or copyright line; they are added separately. "
    "Reply with one JSON object and nothing else. If you search the web, write no text before or between searches; "
    "your only text output is the final JSON. Never include citation tags, XML or HTML in any text value; plain sentences only."
)


def ai_blog(f: Dict[str, Any], web_search: Optional[bool] = None) -> Dict[str, Any]:
    use_search = (WEB_SEARCH_ON and ai_provider() == "anthropic") if web_search is None else web_search
    s = f["symbol"]
    news_rule = (
        f"Use web search first. Find developments from the last few days that bear on {s}: US domestic market or economic, "
        "international, geopolitical, and company- or industry-specific. Write one or two sentences for each category you "
        "can support, and list the exact URLs from your search results that support it. If you find nothing relevant for a "
        "category, set it to null. Do not write from memory."
        if use_search else
        "Web search is not available in this run, so set all five news items to null. Do not write news from memory.")
    user = (
        f"Create today's website report for {s} from the FACTS. {news_rule}\n"
        "FACTS holds the daily view at the top level plus weekly, 4-hour and 2-hour views under 'timeframes' (a view that "
        "is missing is listed in 'timeframes_missing'; never describe a view that is not supplied), and a ranked list of "
        "nearby reference levels under 'levels'. Review all supplied timeframes together. Say where they agree and where "
        "they conflict, and identify market structure, momentum, participation, important support and resistance, "
        "developing risk, and any meaningful change from the recent structure.\n"
        "WRITE THESE SECTIONS, with exactly these headings, in this order, as short paragraphs separated by blank lines: "
        "'Executive Summary' (2 to 3 short paragraphs and the central question), 'Market Structure' (where the closes "
        "sit and how each timeframe reads), 'What Changed?' (the most important change over the recent sessions), "
        "'Current Momentum', 'Key Levels', 'Participation and Volume', 'What Traders Should Watch Next'. "
        "In 'Key Levels', write each level as a one-line label and price (for example 'Immediate Resistance: $123.45') "
        "followed by one sentence on why it matters, using levels from FACTS.levels. Never repeat a level, fact or "
        "conclusion in more than one section except the Executive Summary. The newest weekly, 4-hour and 2-hour bar may "
        "still be forming, so their volume figure (prior_bar_volume_vs_20_bar_avg) is for the previous complete bar; "
        "describe it that way. The title should be a specific, accurate "
        "hook, ideally a question that names the symbol and the key level.\n"
        "INSTITUTIONAL: set news.institutional only if a search result explicitly reports block orders, dark-pool prints, "
        "institutional accumulation or distribution, or unusual liquidity for this symbol. Never infer institutional "
        "activity from price and volume. If nothing is found, set it to null.\n"
        "HEADLINE ASSESSMENT (private, never published). Decide whether each option is supported:\n"
        f'A: "{OPTION_TITLES["A"].format(s=s)}" (needs sourced evidence of institutional or dark-pool accumulation)\n'
        f'B: "{OPTION_TITLES["B"].format(s=s)}" (needs evidence of distribution or exhaustion risk, and of short-duration selling)\n'
        f'C: "{OPTION_TITLES["C"].format(s=s)}" (needs evidence of a high-volatility squeeze setup)\n'
        'Be strict. If none is sufficiently supported, selected is "none" and "title" must be your accurate headline '
        "of at most 90 characters that contains the symbol.\n"
        "Return JSON: {\"title\": str, \"meta_description\": str (110-155 chars, contains the symbol), "
        "\"sections\": [{\"heading\": str, \"body\": str}] (the seven sections above, 700-1000 words in total, "
        "the first paragraph must name the symbol), "
        "\"news\": {\"us\": {\"text\": str, \"urls\": [str]} | null, \"international\": ..., \"geopolitical\": ..., "
        "\"company\": ..., \"institutional\": ...}, "
        "\"summary\": {\"condition\": str, \"risk\": str, \"strengthen\": str, \"weaken\": str, \"monitor\": str}, "
        "\"image\": {\"view\": str (1-2 sentences, at most 200 characters, the day's overall read), \"volume\": str "
        "(1-2 sentences, at most 200 characters, what volume says about confirmation)}, "
        "\"private\": {\"A\": {\"supported\": bool, \"reasoning\": str}, \"B\": {...}, \"C\": {...}, "
        "\"selected\": \"A\"|\"B\"|\"C\"|\"none\"}}\n\nFACTS:\n" + json.dumps(f, indent=1))
    try:
        out = _ai_json(_BLOG_STYLE, user, max_tokens=16000, web_search=use_search)
    except Exception as e:
        resp = getattr(e, "response", None)
        if use_search and getattr(resp, "status_code", None) == 400:  # search not enabled for this account: no charge
            out = _ai_json(_BLOG_STYLE, user.replace(news_rule, "Web search is not available in this run, so set all five "
                                                     "news items to null."), max_tokens=16000)
            out["_search_unavailable"] = True
        else:
            raise
    for k in ("title", "meta_description", "sections", "news", "summary", "private", "image"):
        if k in out:
            out[k] = _clean_obj(out[k])
    secs = [{"heading": str(x["heading"]), "body": str(x["body"])} for x in (out.get("sections") or [])
            if isinstance(x, dict) and x.get("heading") and x.get("body")]
    if not secs:
        raise AIParseError("AI reply had no complete sections.", json.dumps(out, indent=1)[:60000])
    return {"title": str(out.get("title") or f"{s} Market Structure Report")[:90],
            "meta_description": str(out.get("meta_description") or "")[:158], "sections": secs,
            "news": out.get("news") or {}, "summary": out.get("summary") or {}, "private": out.get("private") or {},
            "image": out.get("image") or {},
            "_search_results": out.get("_search_results") or {}, "_search_unavailable": bool(out.get("_search_unavailable")),
            "_recovered": bool(out.get("_recovered")), "_stop": out.get("_stop"), "_thinking": out.get("_thinking") or 0,
            "ai": True}


_TAG_RE = re.compile(r"[<(]\s*/?\s*cite\b[^<>]*>|</?\s*[A-Za-z][^<>]*>")


def clean_ai_text(x: Any) -> str:
    """Removes markup the web-search tool can leave in text (for example <cite index="8-10">...</cite>)."""
    return re.sub(r"[ \t]{2,}", " ", _TAG_RE.sub("", str(x))).strip()


def _clean_obj(o: Any) -> Any:
    if isinstance(o, str):
        return clean_ai_text(o)
    if isinstance(o, list):
        return [_clean_obj(v) for v in o]
    if isinstance(o, dict):
        return {k: (v if k == "urls" else _clean_obj(v)) for k, v in o.items()}
    return o


def _guarded_text(title: str, meta: str, sections: List[Dict[str, str]], summary: Dict[str, str]) -> str:
    return " ".join([title, meta] + [x["heading"] + " " + x["body"] for x in sections] + [str(v) for v in summary.values()])


def _blog_text(blog: Dict[str, Any]) -> str:
    """The part of the post that must trace to the platform data. News (sourced online) and fixed text are excluded."""
    return blog.get("guarded_text") or " ".join(
        [blog["title"], blog["meta_description"]] + [s["heading"] + " " + s["body"] for s in blog["sections"]])


def _vet_news(raw: Any, found: Dict[str, str]):
    """Keeps a news item only if it has text and at least one URL that really came back from the search."""
    news: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, str] = {}
    dropped: List[str] = []
    if not isinstance(raw, dict):
        return news, [], dropped
    for key in NEWS_HEADINGS:
        item = raw.get(key)
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        urls = [u for u in (item.get("urls") or []) if isinstance(u, str) and u in found]
        text = str(item["text"]).strip()
        if not urls:
            dropped.append(f"{NEWS_HEADINGS[key].format(s='')} (no verifiable source)")
        elif find_banned_phrases(text):
            dropped.append(f"{NEWS_HEADINGS[key].format(s='')} (advice wording)")
        else:
            news[key] = {"text": text, "urls": urls}
            for u in urls:
                sources[u] = found[u]
    return news, [{"title": t, "url": u} for u, t in sources.items()], dropped


EXPECTED_SECTIONS = ["Executive Summary", "Market Structure", "What Changed?", "Current Momentum", "Key Levels",
                     "Participation and Volume", "What Traders Should Watch Next"]


def generate_blog(f: Dict[str, Any], use_ai: bool = True) -> Dict[str, Any]:
    """Paid AI output is never thrown away: problems are flagged for the editor, damaged replies are repaired,
    and a reply that cannot be read at all is handed back as raw text."""
    note = None
    blog = None
    raw_ai_text = None
    if use_ai and ai_available():
        try:
            cand = ai_blog(f)
            if not cand.get("meta_description"):
                cand["meta_description"] = template_blog(f)["meta_description"]
            summary = {k: str((cand.get("summary") or {}).get(k) or "").strip() for k, _ in SUMMARY_LABELS}
            missing_summary = not all(summary.values())
            if missing_summary:
                summary = _template_summary(f)
            cand["summary"] = summary
            tpl_img = _template_image_text(f)
            img = {k: str((cand.get("image") or {}).get(k) or "").strip() for k in ("view", "volume")}
            for k in img:
                if not img[k] or len(img[k]) > 215:
                    img[k] = tpl_img[k]
            cand["image_text"] = img
            guarded = _guarded_text(cand["title"], cand["meta_description"], cand["sections"], {**summary, **{"i" + k: v for k, v in img.items()}})
            bad, banned = numbers_trace_to_facts(guarded, f), find_banned_phrases(guarded)
            news, sources, dropped = _vet_news(cand.get("news"), cand.get("_search_results") or {})
            private = _norm_private(cand.get("private"))
            sel = private["selected"]
            if sel == "A" and "institutional" not in news:
                sel = private["selected"] = "none"
                private["A"]["reasoning"] += " (Marked not supported by the tool: no sourced institutional finding was returned.)"
            title = OPTION_TITLES[sel].format(s=f["symbol"]) if sel in OPTION_TITLES else cand["title"]
            cand.update({"title": title, "news": news, "sources": sources, "private": private, "guarded_text": guarded})
            cand.pop("_search_results", None)
            extra = []
            stop, thinking = cand.pop("_stop", None), cand.pop("_thinking", 0)
            if cand.pop("_recovered", False):
                have = {x["heading"].strip().lower() for x in cand["sections"]}
                gone = [h for h in EXPECTED_SECTIONS if h.lower() not in have]
                extra.append(f"The AI reply was cut off or damaged and was repaired (stop reason: {stop}; thinking tokens: {thinking:,}); "
                             "everything complete was kept."
                             + (" Missing sections: " + ", ".join(gone) + "." if gone else "")
                             + (" The summary was filled in from the data." if missing_summary else ""))
            if cand.pop("_search_unavailable", False):
                extra.append("Web search is not enabled for this Anthropic account, so no news sections were written.")
            if banned:
                extra.append("Review before publishing: advice or promise wording found: " + ", ".join(banned) + ".")
            if bad:
                extra.append("Review before publishing: these numbers are not in the platform data (derived or "
                             "invented): " + ", ".join(bad) + ".")
            if dropped:
                extra.append("News left out: " + "; ".join(dropped) + ".")
            if ai_provider() == "openai":
                extra.append("Web search is only wired for Anthropic; no news sections were written in this run.")
            note = " ".join(extra) or None
            blog = cand
        except Exception as e:
            note = f"AI reply could not be used ({str(e)[:140]}); template used."
            raw_ai_text = getattr(e, "raw", None) or None
            if raw_ai_text:
                note += " The AI's unprocessed text is shown below so the cost is not wasted."
    elif use_ai:
        note = "No AI key set (ANTHROPIC_API_KEY or OPENAI_API_KEY); template draft used."
    if blog is None:
        blog = template_blog(f)
        blog["guarded_text"] = _guarded_text(blog["title"], blog["meta_description"], blog["sections"], blog["summary"])
    out = _render_blog(f, blog)
    out["note"] = note
    if raw_ai_text:
        out["raw_ai_text"] = raw_ai_text[:60000]
    return out


# ───────────────────────────── teasers ─────────────────────────────

def _tags(f: Dict[str, Any], n: int) -> str:
    base = [f"#{f['symbol']}", "#Stocks", "#MarketStructure", "#Wyckoff", "#TechnicalAnalysis"]
    return " ".join(base[:n])


def template_teasers(f: Dict[str, Any], blog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    s, asof = f["symbol"], f["as_of"]
    px, d1 = _usd(f["last_close"]), _sgn(f["change_1d_pct"])
    trend = _trend_word(f)
    sig = _signal_phrase(f)
    head = blog["title"]
    link = {p: tracked_url(p, s, asof) for p in PLATFORM_ORDER}

    out: Dict[str, Dict[str, Any]] = {}
    out["linkedin"] = {"text": (
        f"{s} market structure, {asof}\n\n"
        f"Price closed at {px} ({d1}), {trend} its 20-day average. Sigmalytic's Wyckoff/Weis scan shows {sig}.\n\n"
        f"The full read covers the 52-week range, volume against its 20-day average, and the levels we are tracking.\n\n"
        f"{SHORT_DISCLAIMER}\n\nRead the analysis: {link['linkedin']}\n\n{_tags(f, 3)}")}
    out["x"] = {"text": f"${s} {px} ({d1}), {trend} its 20-day average. Scan shows {sig}. {_tags(f, 1)}",
                "reply": f"Full market-structure read: {link['x']}\n{SHORT_DISCLAIMER}"}
    out["reddit"] = {"title": f"{s}: price {trend} its 20-day average at {px}; Wyckoff/Weis scan shows {sig}"[:300],
                     "text": (f"Notes from our nightly scan on {s} (data as of {asof}).\n\n"
                              f"- Close: {px} ({d1}); 5-day {_sgn(f['change_5d_pct'])}; 20-day {_sgn(f['change_20d_pct'])}\n"
                              f"- 52-week range: {_usd(f['low_52w'])} to {_usd(f['high_52w'])}\n"
                              f"- Pattern read: {sig}\n\n"
                              f"Happy to answer questions on how we read these. {SHORT_DISCLAIMER}"),
                     "reply": f"Longer write-up with the levels (only if the subreddit allows links): {link['reddit']}"}
    out["pinterest"] = {"title": f"{s} Stock Analysis: Wyckoff & Weis Market Structure"[:100],
                        "text": (f"{s} closed at {px} ({d1}), {trend} its 20-day average. See the 52-week range, volume "
                                 f"and the pattern read behind it. {SHORT_DISCLAIMER} {_tags(f, 3)}"),
                        "destination_link": link["pinterest"]}
    out["facebook"] = {"text": (f"{s} update: closed at {px} ({d1}), {trend} its 20-day average, with {sig}. "
                                f"Full read: {link['facebook']}\n{SHORT_DISCLAIMER}")}
    out["tiktok"] = {"text": (f"{s} in 20 seconds: {px}, {d1}, {trend} the 20-day average. "
                              f"Pattern read: {sig}. Full analysis, link in bio. {SHORT_DISCLAIMER} {_tags(f, 4)}"),
                     "video_script": [
                         f"Hook (0-3s): {s}, here is what the chart is showing.",
                         f"Beat 1 (3-10s): Closed at {px}, {d1}, {trend} the 20-day average.",
                         f"Beat 2 (10-17s): Scan result: {sig}.",
                         "CTA (17-20s): Full breakdown is linked in our bio."]}
    return out


def ai_teasers(f: Dict[str, Any], blog: Dict[str, Any]) -> Dict[str, Any]:
    rules = {p: {k: PLATFORM_RULES[p][k] for k in ("max_chars", "max_hashtags", "link") if k in PLATFORM_RULES[p]}
             for p in PLATFORM_ORDER}
    user = (
        "Write one social teaser per platform for this blog post. Each teaser must make the reader curious about the "
        "full post, state one concrete data point, and stay inside the platform's limits (characters include everything). "
        f"End every text with: {SHORT_DISCLAIMER}\n"
        "Do NOT put URLs in any text; links are added separately. Use at most the allowed hashtags.\n"
        'Return JSON: {"linkedin": {"text"}, "x": {"text", "reply"}, "reddit": {"title", "text", "reply"}, '
        '"pinterest": {"title", "text"}, "facebook": {"text"}, "tiktok": {"text", "video_script": [str]}}\n\n'
        f"PLATFORM RULES:\n{json.dumps(rules, indent=1)}\n\nBLOG TITLE: {blog['title']}\n\nFACTS:\n"
        f"{json.dumps({k: v for k, v in f.items() if k != 'timeframes'}, indent=1)}")
    return _ai_json(_AI_STYLE, user, max_tokens=3000)


def _attach_links(f: Dict[str, Any], plat: str, d: Dict[str, Any]) -> Dict[str, Any]:
    url = tracked_url(plat, f["symbol"], f["as_of"])
    d = dict(d)
    if plat == "linkedin":
        d["text"] = d["text"].rstrip() + f"\n\nRead the analysis: {url}"
    elif plat == "x":
        d["reply"] = (d.get("reply") or "Full market-structure read:").rstrip() + f" {url}"
    elif plat == "reddit":
        d["reply"] = (d.get("reply") or "Longer write-up:").rstrip() + f" {url}"
    elif plat == "pinterest":
        d["destination_link"] = url
    elif plat == "facebook":
        d["text"] = d["text"].rstrip() + f"\n{url}"
    return d


def generate_teasers(f: Dict[str, Any], blog: Dict[str, Any], use_ai: bool = True) -> Dict[str, Dict[str, Any]]:
    base = template_teasers(f, blog)
    ai: Dict[str, Any] = {}
    note = None
    if use_ai and ai_available():
        try:
            ai = ai_teasers(f, blog)
        except Exception as e:
            note = f"AI unavailable ({str(e)[:100]}); templates used."
    result: Dict[str, Dict[str, Any]] = {}
    for p in PLATFORM_ORDER:
        draft, source = base[p], "template"
        cand = ai.get(p) if isinstance(ai, dict) else None
        if isinstance(cand, dict) and cand.get("text"):
            merged = _attach_links(f, p, {k: cand[k] for k in cand if isinstance(cand[k], (str, list))})
            if not validate_teaser(p, merged, f):
                draft, source = merged, "ai"
            else:
                note = (note or "") + f" {PLATFORM_RULES[p]['label']} AI draft failed checks; template used."
        issues = validate_teaser(p, draft, f)
        result[p] = {**draft, "platform": p, "label": PLATFORM_RULES[p]["label"], "source": source,
                     "chars": weighted_len(p, draft.get("text", "")), "limit": PLATFORM_RULES[p]["max_chars"],
                     "link_placement": PLATFORM_RULES[p]["link"], "image_spec": PLATFORM_RULES[p]["image"],
                     "issues": issues, "ok": not issues}
    if note:
        result["_note"] = {"note": note.strip()}
    return result


# ───────────────────────────── entry point ─────────────────────────────

def build_package(symbol: str, use_ai: bool = True, facts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    log: List[Dict[str, Any]] = []
    token = _USAGE.set(log)
    try:
        return _build_package(symbol, use_ai, facts, log)
    finally:
        _USAGE.reset(token)


def _build_package(symbol: str, use_ai: bool, facts: Optional[Dict[str, Any]], log: List[Dict[str, Any]]) -> Dict[str, Any]:
    f = facts or build_facts(symbol)
    chart_bars = f.pop("_chart_bars", None)
    blog = generate_blog(f, use_ai=use_ai)
    teasers = generate_teasers(f, blog, use_ai=use_ai)
    notes = [n for n in (blog.get("note"), (teasers.pop("_note", {}) or {}).get("note")) if n]
    blog_issues = (["Numbers not in the data: " + ", ".join(numbers_trace_to_facts(_blog_text(blog), f))]
                   if numbers_trace_to_facts(_blog_text(blog), f) else []) + \
                  (["Advice wording: " + ", ".join(find_banned_phrases(_blog_text(blog)))]
                   if find_banned_phrases(_blog_text(blog)) else [])
    share_image = None
    if chart_bars:
        try:
            import base64
            from backend.content_chart import render_share_image, W as IMG_W, H as IMG_H
            share_image = {"png_b64": base64.b64encode(render_share_image(
                f, chart_bars, title=blog.get("title", ""), view_text=(blog.get("image_text") or {}).get("view", ""),
                volume_text=(blog.get("image_text") or {}).get("volume", ""))).decode("ascii"),
                           "filename": f"{f['symbol'].lower()}-{f['as_of']}-share-image.png", "width": IMG_W, "height": IMG_H}
        except Exception as e:  # the image is a convenience; it must never break the report
            notes.append(f"Share image could not be drawn: {str(e)[:120]}.")
    return {"symbol": f["symbol"], "as_of": f["as_of"], "facts": f, "share_image": share_image, "blog": blog,
            "blog_issues": blog_issues,
            "teasers": teasers, "ai_used": bool(blog.get("ai")), "ai_configured": ai_available(), "ai_provider": ai_provider(), "usage": summarize_usage(log), "notes": notes}
