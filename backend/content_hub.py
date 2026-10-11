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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

SITE_URL = os.getenv("CONTENT_HUB_SITE_URL", "https://sigmalyticquantcorp.com").rstrip("/")
BLOG_PATH = os.getenv("CONTENT_HUB_BLOG_PATH", "/research-and-intelligence").rstrip("/")
AI_MODEL = os.getenv("CONTENT_HUB_MODEL", "claude-sonnet-5-5")

DISCLAIMER = (
    "This is educational market research from Sigmalytic Quant Corporation. It is not investment "
    "advice, a recommendation, or an offer to buy or sell any security. Patterns describe past price "
    "and volume behavior and do not predict future results. Trading involves risk of loss."
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
        "volume_vs_20d_avg": vol_ratio,
        "pattern_signals": hits,
        "call_wall": _f(chart.get("call_wall")),
        "put_wall": _f(chart.get("put_wall")),
        "gamma_flip": _f(chart.get("gamma_flip")),
        "ice_line": _f(wl.get("ice_line_level")) if isinstance(wl, dict) else None,
        "bars_used": len(bars),
    }
    return facts


def build_facts(symbol: str) -> Dict[str, Any]:
    """Fetches live data through the existing chart endpoint function and reduces it to facts."""
    from backend.main import weis_radar_chart_data  # lazy: avoids a circular import at module load
    chart = weis_radar_chart_data(symbol.upper().strip(), timeframe="1Day", limit=252)
    if not chart.get("ok"):
        raise ValueError(chart.get("error") or f"No data for {symbol}.")
    return facts_from_chart_data(symbol, chart)


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
    nums.extend([20, 52, 252])  # window lengths named in the copy ("20-day average", "52-week range")
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

def template_blog(f: Dict[str, Any]) -> Dict[str, Any]:
    s, name = f["symbol"], f["symbol"]
    trend = _trend_word(f)
    title = f"{s} Market Structure: Price {trend} its 20-day average at {_usd(f['last_close'])}"
    meta = (f"{s} closed at {_usd(f['last_close'])} ({_sgn(f['change_1d_pct'])} on the day), "
            f"{_sgn(f['from_high_pct'])} from its 52-week high. Wyckoff/Weis read from Sigmalytic.")[:158]
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

    sections.append({"heading": "What to watch", "body":
                     f"Traders following {name} will want to see whether price holds above or below its 20-day average "
                     f"({_usd(f['sma20'])}) and how volume behaves near the levels above. Sigmalytic updates these "
                     "readings as new bars arrive."})
    return {"title": title, "meta_description": meta, "sections": sections, "ai": False}


def _render_blog(f: Dict[str, Any], blog: Dict[str, Any]) -> Dict[str, Any]:
    url = blog_url(f["symbol"], f["as_of"])
    esc = _html.escape
    body_html = "".join(f"<h2>{esc(s['heading'])}</h2>\n<p>{esc(s['body'])}</p>\n" for s in blog["sections"])
    html_doc = (
        f"<!-- Paste into the Research & Intelligence page. Canonical: {url} -->\n"
        f"<article class=\"sigmalytic-research\">\n<h1>{esc(blog['title'])}</h1>\n"
        f"<p class=\"byline\">Sigmalytic Quant Corporation · Data as of {esc(f['as_of'])}</p>\n{body_html}"
        f"<p class=\"disclaimer\"><em>{esc(DISCLAIMER)}</em></p>\n</article>"
    )
    md = f"# {blog['title']}\n\n" + "\n\n".join(f"## {s['heading']}\n\n{s['body']}" for s in blog["sections"]) + f"\n\n*{DISCLAIMER}*\n"
    head = (
        f"<title>{esc(blog['title'])}</title>\n<meta name=\"description\" content=\"{esc(blog['meta_description'])}\">\n"
        f"<link rel=\"canonical\" href=\"{url}\">\n<meta property=\"og:type\" content=\"article\">\n"
        f"<meta property=\"og:title\" content=\"{esc(blog['title'])}\">\n"
        f"<meta property=\"og:description\" content=\"{esc(blog['meta_description'])}\">\n"
        f"<meta property=\"og:url\" content=\"{url}\">\n<meta name=\"twitter:card\" content=\"summary_large_image\">"
    )
    return {**blog, "slug": _slug(f["symbol"], f["as_of"]), "url": url, "html": html_doc, "markdown": md,
            "head_tags": head, "disclaimer": DISCLAIMER}


# ───────────────────────────── AI (optional) ─────────────────────────────

def ai_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _ai_json(system: str, user: str, max_tokens: int = 2500) -> Dict[str, Any]:
    import requests
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": AI_MODEL, "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": user}]},
        timeout=90,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("AI reply had no JSON object.")
    return json.loads(m.group(0))


_AI_STYLE = (
    "You write for Sigmalytic Quant Corporation, a market-structure research firm (Wyckoff/Weis analysis). "
    "Voice: plain, precise, analytical, no hype. Observations only. Never advise, recommend, predict, or promise. "
    "Use ONLY the numbers in the FACTS JSON; do not compute new ones or add any other numbers. "
    "Do not write a disclaimer; it is added separately. Reply with one JSON object and nothing else."
)


def ai_blog(f: Dict[str, Any]) -> Dict[str, Any]:
    out = _ai_json(
        _AI_STYLE,
        "Write a blog post (350-550 words) from these FACTS.\nReturn JSON: "
        '{"title": str (<=70 chars), "meta_description": str (<=155 chars), '
        '"sections": [{"heading": str, "body": str}] (4-6 sections)}\n\nFACTS:\n' + json.dumps(f, indent=1))
    secs = [{"heading": str(s["heading"]), "body": str(s["body"])} for s in out["sections"]]
    return {"title": str(out["title"])[:90], "meta_description": str(out["meta_description"])[:158],
            "sections": secs, "ai": True}


def _blog_text(blog: Dict[str, Any]) -> str:
    return " ".join([blog["title"], blog["meta_description"]] + [s["heading"] + " " + s["body"] for s in blog["sections"]])


def generate_blog(f: Dict[str, Any], use_ai: bool = True) -> Dict[str, Any]:
    note = None
    blog = None
    if use_ai and ai_available():
        try:
            cand = ai_blog(f)
            bad, banned = numbers_trace_to_facts(_blog_text(cand), f), find_banned_phrases(_blog_text(cand))
            if bad or banned:
                note = "AI draft rejected (" + ("numbers not in data: " + ", ".join(bad) + "; " if bad else "") + \
                       ("advice wording: " + ", ".join(banned) if banned else "") + "); template used."
            else:
                blog = cand
        except Exception as e:
            note = f"AI unavailable ({str(e)[:120]}); template used."
    elif use_ai:
        note = "No ANTHROPIC_API_KEY set; template draft used."
    blog = blog or template_blog(f)
    out = _render_blog(f, blog)
    out["note"] = note
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
        f"PLATFORM RULES:\n{json.dumps(rules, indent=1)}\n\nBLOG TITLE: {blog['title']}\n\nFACTS:\n{json.dumps(f, indent=1)}")
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
    f = facts or build_facts(symbol)
    blog = generate_blog(f, use_ai=use_ai)
    teasers = generate_teasers(f, blog, use_ai=use_ai)
    notes = [n for n in (blog.get("note"), (teasers.pop("_note", {}) or {}).get("note")) if n]
    blog_issues = (["Numbers not in the data: " + ", ".join(numbers_trace_to_facts(_blog_text(blog), f))]
                   if numbers_trace_to_facts(_blog_text(blog), f) else []) + \
                  (["Advice wording: " + ", ".join(find_banned_phrases(_blog_text(blog)))]
                   if find_banned_phrases(_blog_text(blog)) else [])
    return {"symbol": f["symbol"], "as_of": f["as_of"], "facts": f, "blog": blog, "blog_issues": blog_issues,
            "teasers": teasers, "ai_used": bool(blog.get("ai")), "ai_configured": ai_available(), "notes": notes}
