# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/publishing_checklist.py
-------------------------------
Sigmalytic's repeatable publishing checklist for every daily market post, blog and white paper, so Google
indexes the analysis quickly and AI answer engines (Gemini, AI Overviews) can lift the data cleanly.

  1. Structure for fast AI extraction (before publishing)
     1a. A specific, level-driven headline: the ticker or index plus a concrete price level and, where it fits, the
         catalyst ("NVDA Stock Analysis: Can Buyers Defend $224.00 Support?").
     1b. A two-sentence "Bottom Line" opening: the exact price, the current bias, and the invalidation level.
     1c. Chart visuals translated into text: 2-3 bullets directly beneath every chart with the exact support,
         resistance, call/put wall and moving-average figures shown in the image.
  2. Authority and internal links (inside the post)
     2a. A natural link to 1-2 earlier Sigmalytic posts on the same ticker or index.
     2b. The standard byline: "By the Sigmalytic Quant Research Team | Methodology & Editorial Standards", linked to
         the website.
  3. Publish and distribute (immediately after publishing)
     3a. Publish in GoDaddy's Research and Intelligence blog.
     3b. Request indexing by hand only for flagship reports (pre-market macro reports, weekly white paper audits);
         routine daily posts are found through sitemap.blog.xml, which avoids crawl throttling.
     3c. Share a 3-bullet summary on LinkedIn and X with a direct link to the article.

Steps 1a-2b are checked by code (check_post works on any post's HTML, generated or pasted). Steps 3a-3c happen outside
the platform, so they are listed as manual steps with the exact URL and text to use.
"""

from __future__ import annotations

import html as _html
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

SITE_URL = os.getenv("CONTENT_HUB_SITE_URL", "https://sigmalyticquantcorp.com").rstrip("/")
BLOG_PATH = os.getenv("CONTENT_HUB_BLOG_PATH", "/research-and-intelligence").rstrip("/")
SITEMAP_URL = os.getenv("CONTENT_HUB_SITEMAP_URL", f"{SITE_URL}/sitemap.blog.xml")
METHODOLOGY_URL = os.getenv("CONTENT_HUB_METHODOLOGY_URL", SITE_URL)
BYLINE_TEAM = "Sigmalytic Quant Research Team"
BYLINE_TEXT = f"By the {BYLINE_TEAM} | Methodology & Editorial Standards"
HEADLINE_MAX = 65  # GoDaddy's headline limit

GROUPS = [("structure", "1. Structure for fast AI extraction (before publishing)"),
          ("authority", "2. Authority and internal links (inside the post)"),
          ("distribute", "3. Publish and distribute (immediately after publishing)")]

# Index tickers are also matched by the words their posts use in URLs.
INDEX_ALIASES = {"SPY": ["s-p-500", "sp-500", "sp500", "s-and-p-500", "spx"], "SPX": ["s-p-500", "sp-500", "sp500", "spy"],
                 "QQQ": ["nasdaq", "ndx"], "NDX": ["nasdaq", "qqq"], "DIA": ["dow", "djia"], "IWM": ["russell", "rut"]}

_PRICE_RE = re.compile(r"\$\d[\d,]*\.\d{2}\b")
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z$\"'(])")


def sentences(text: str) -> List[str]:
    return [s for s in _SENT_RE.split(re.sub(r"\s+", " ", text or "").strip()) if s]


def prices_in(text: str) -> List[float]:
    return [float(p[1:].replace(",", "")) for p in _PRICE_RE.findall(text or "")]


# ───────────────────────────── 1b. bottom line ─────────────────────────────

def bias(f: Dict[str, Any]) -> str:
    """'buyer-led', 'seller-led' or 'balanced', from where price sits against its 20-day average and today's range."""
    above = (f.get("vs_sma20_pct") or 0) > 0
    half = (f.get("day_range") or {}).get("half")
    if above and half != "lower":
        return "buyer-led"
    if not above and half != "upper":
        return "seller-led"
    return "balanced"


def nearest(f: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    lv = f.get("levels") or {}
    below = [x for x in (lv.get("below") or []) if not x.get("traded_today")] or (lv.get("below") or [])
    above = lv.get("above") or []
    return (below[0] if below else None), (above[0] if above else None)


def _usd(v: Optional[float]) -> str:
    return f"${v:,.2f}" if v is not None else "n/a"


def _lab(x: Dict[str, Any]) -> str:
    """Level label for use in a sentence: 'Support'/'Resistance' labels become 'pattern level' so the text never
    reads 'support $105.50 (support)'."""
    lab = str(x.get("label") or "").strip()
    return "pattern level" if lab.lower() in ("support", "resistance") else lab[:1].lower() + lab[1:]


def template_bottom_line(f: Dict[str, Any]) -> str:
    s, px = f["symbol"], _usd(f.get("last_close"))
    sess = f.get("session") or {}
    verb = "is trading at" if sess.get("live") else "closed at"
    b = bias(f)
    sup, res = nearest(f)
    half = (f.get("day_range") or {}).get("half")
    where = f", in the {half} half of the day's range" if half else ""
    first = f"{s} {verb} {px}{where}, and the current bias is {b} with price {'above' if (f.get('vs_sma20_pct') or 0) > 0 else 'below'} its 20-day average of {_usd(f.get('sma20'))}."
    if b == "buyer-led" and sup:
        second = f"A close below {_usd(sup['price'])} ({_lab(sup)}) is the primary invalidation level for that read."
    elif b == "seller-led" and res:
        second = f"A close above {_usd(res['price'])} ({_lab(res)}) is the primary invalidation level for that read."
    elif sup and res:
        second = (f"A close below {_usd(sup['price'])} or above {_usd(res['price'])} is the primary invalidation level "
                  "for the balance.")
    else:
        second = f"A close back through the 20-day average at {_usd(f.get('sma20'))} is the primary invalidation level."
    return f"{first} {second}"


def bottom_line_problems(text: str, symbol: str = "") -> List[str]:
    out = []
    n = len(sentences(text))
    if n != 2:
        out.append(f"has {n} sentences; the rule is exactly 2")
    if len(prices_in(text)) < 2:
        out.append("should state at least two exact prices (the current price and the invalidation level)")
    if "invalidat" not in text.lower():
        out.append("should name the invalidation level")
    if symbol and symbol.upper() not in text.upper():
        out.append(f"should name {symbol}")
    return out


# ───────────────────────────── 1a. headline ─────────────────────────────

def template_headline(f: Dict[str, Any]) -> str:
    s = f["symbol"]
    sup, res = nearest(f)
    b = bias(f)
    opts = []
    if b != "seller-led" and sup:
        opts += [f"{s} Stock Analysis: Can Buyers Defend {_usd(sup['price'])} Support?", f"{s}: Can Buyers Defend {_usd(sup['price'])}?"]
    if res:
        opts += [f"{s} Stock Analysis: Can Buyers Reclaim {_usd(res['price'])}?", f"{s}: Can Buyers Reclaim {_usd(res['price'])}?"]
    opts.append(f"{s} Stock Analysis: Price at {_usd(f.get('last_close'))}")
    return next((o for o in opts if len(o) <= HEADLINE_MAX), opts[-1][:HEADLINE_MAX])


def headline_problems(title: str, symbol: str = "") -> List[str]:
    out = []
    if symbol and not re.search(r"(?<![A-Za-z])" + re.escape(symbol.upper()) + r"(?![A-Za-z])", title.upper()):
        out.append(f"does not name {symbol}")
    if not symbol and not re.search(r"\b[A-Z]{1,5}\b", title):
        out.append("does not name a ticker or index")
    if not _PRICE_RE.search(title):
        out.append("has no concrete price level (for example $224.00)")
    if len(title) > HEADLINE_MAX:
        out.append(f"is {len(title)} characters; GoDaddy allows {HEADLINE_MAX}")
    return out


# ───────────────────────────── 1c. chart bullets ─────────────────────────────

def chart_bullets(f: Dict[str, Any]) -> List[str]:
    """2-3 plain-text bullets that state the levels drawn in the chart image, so crawlers can read them."""
    sup, res = nearest(f)
    out = []
    sr = []
    if sup:
        sr.append(f"Support {_usd(sup['price'])} ({_lab(sup)})")
    if res:
        sr.append(f"{'resistance' if sup else 'Resistance'} {_usd(res['price'])} ({_lab(res)})")
    if sr:
        out.append("; ".join(sr) + ".")
    walls = []
    if f.get("call_wall"):
        walls.append(f"call wall {_usd(f['call_wall'])}")
    if f.get("put_wall"):
        walls.append(f"put wall {_usd(f['put_wall'])}")
    if walls:
        out.append("Options walls: " + "; ".join(walls) + ".")
    mas = [f"{n}-day {_usd(f.get(k))}" for n, k in ((20, "sma20"), (50, "sma50"), (200, "sma200")) if f.get(k)]
    if mas:
        out.append("Moving averages: " + "; ".join(mas) + ".")
    return out[:3]


def short_bullets(f: Dict[str, Any]) -> List[str]:
    """The same levels, compact enough for X."""
    sup, res = nearest(f)
    out = []
    if sup or res:
        out.append(" / ".join(x for x in ((f"Support {_usd(sup['price'])}" if sup else ""),
                                          (f"Resistance {_usd(res['price'])}" if res else "")) if x))
    walls = [x for x in ((f"Call wall {_usd(f['call_wall'])}" if f.get("call_wall") else ""),
                         (f"Put wall {_usd(f['put_wall'])}" if f.get("put_wall") else "")) if x]
    if walls:
        out.append(" / ".join(walls))
    if f.get("sma20"):
        out.append(f"20-day avg {_usd(f['sma20'])}")
    return out[:3]


# ───────────────────────────── 2a. related posts from the live sitemap ─────────────────────────────

_SITEMAP_CACHE: Dict[str, Any] = {"at": 0.0, "urls": []}
SITEMAP_TTL = 3600


def _fetch(url: str) -> str:
    import requests
    r = requests.get(url, timeout=6, headers={"User-Agent": "SigmalyticContentHub/1.0"})
    r.raise_for_status()
    return r.text


def parse_sitemap(xml_text: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Returns (pages, child sitemap URLs). Namespace-agnostic."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    tag = lambda e: e.tag.rsplit("}", 1)[-1]
    pages, children = [], []
    for node in root:
        loc = next((c.text.strip() for c in node if tag(c) == "loc" and c.text), "")
        mod = next((c.text.strip() for c in node if tag(c) == "lastmod" and c.text), "")
        if not loc:
            continue
        (children.append(loc) if tag(node) == "sitemap" else pages.append({"url": loc, "lastmod": mod}))
    return pages, children


def sitemap_pages(fetch=None) -> List[Dict[str, str]]:
    fetch = fetch or _fetch
    if _SITEMAP_CACHE["urls"] and time.time() - _SITEMAP_CACHE["at"] < SITEMAP_TTL:
        return _SITEMAP_CACHE["urls"]
    pages, children = parse_sitemap(fetch(SITEMAP_URL))
    for child in children[:5]:
        try:
            pages += parse_sitemap(fetch(child))[0]
        except Exception:
            pass
    _SITEMAP_CACHE.update(at=time.time(), urls=pages)
    return pages


def _matches(symbol: str, url: str) -> bool:
    slug = url.lower().rstrip("/").rsplit("/", 1)[-1]
    tokens = re.split(r"[^a-z0-9]+", slug)
    if symbol.lower() in tokens:
        return True
    return any(a in slug for a in INDEX_ALIASES.get(symbol.upper(), []))


def _anchor(symbol: str, lastmod: str) -> str:
    try:
        d = datetime.strptime(lastmod[:10], "%Y-%m-%d")
        return f"Sigmalytic's {symbol} report from {d.strftime('%A')}, {d.strftime('%B')} {d.day}"
    except Exception:
        return f"Sigmalytic's earlier {symbol} report"


def related_posts(symbol: str, exclude_url: str = "", limit: int = 2, fetch=None) -> Dict[str, Any]:
    """Up to `limit` of the newest published posts on the same ticker or index, read from sitemap.blog.xml.
    Never raises: a sitemap that cannot be read gives an empty list and a reason."""
    try:
        pages = sitemap_pages(fetch)
    except Exception as e:
        return {"posts": [], "error": f"sitemap could not be read ({type(e).__name__}: {str(e)[:80]})"}
    ex = exclude_url.rstrip("/").lower()
    hits = [p for p in pages if _matches(symbol, p["url"]) and p["url"].rstrip("/").lower() != ex]
    hits.sort(key=lambda p: p.get("lastmod") or "", reverse=True)
    posts = [{"id": i + 1, "url": p["url"], "anchor": _anchor(symbol, p.get("lastmod") or ""), "lastmod": p.get("lastmod", "")}
             for i, p in enumerate(hits[:limit])]
    return {"posts": posts, "error": None if posts else f"no earlier {symbol} post found in the sitemap"}


_MARK_RE = re.compile(r"\[\[(\d)\]\]")


def link_markers(text: str) -> List[int]:
    return [int(m) for m in _MARK_RE.findall(text or "")]


def expand_links(text: str, posts: List[Dict[str, Any]], mode: str) -> str:
    """Turns [[1]] markers into links. `text` must already be HTML-escaped when mode is 'html'."""
    by_id = {p["id"]: p for p in posts}

    def rep(m):
        p = by_id.get(int(m.group(1)))
        if not p:
            return ""
        if mode == "html":
            return f'<a href="{_html.escape(p["url"], quote=True)}">{_html.escape(p["anchor"])}</a>'
        if mode == "md":
            return f'[{p["anchor"]}]({p["url"]})'
        return p["anchor"]
    return re.sub(r"\s+([.,;])", r"\1", _MARK_RE.sub(rep, text))


# ───────────────────────────── 2b. byline ─────────────────────────────

def byline_html() -> str:
    return (f'By the <a href="{_html.escape(SITE_URL)}">{BYLINE_TEAM}</a> | '
            f'<a href="{_html.escape(METHODOLOGY_URL)}">Methodology &amp; Editorial Standards</a>')


# ───────────────────────────── checking any post's HTML ─────────────────────────────

class _Walker(HTMLParser):
    """Flattens HTML into a list of events: ('h1'|'p'|'li'|'img'|'a'|'ul_end'|'h2', text_or_attrs)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events: List[Tuple[str, Any]] = []
        self._stack: List[Tuple[str, List[str], Dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "img":
            self.events.append(("img", a))
            return
        if tag == "a":
            self.events.append(("a", a))
        if tag in ("h1", "h2", "h3", "p", "li"):
            self._stack.append((tag, [], a))

    def handle_endtag(self, tag):
        if tag == "ul":
            self.events.append(("ul_end", None))
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                t, buf, a = self._stack.pop(i)
                self.events.append((t, {"text": re.sub(r"\s+", " ", "".join(buf)).strip(), "class": a.get("class", "")}))
                break

    def handle_data(self, data):
        for _, buf, _ in self._stack:
            buf.append(data)


def _check(name: str, group: str, level: str, detail: str) -> Dict[str, str]:
    return {"name": name, "group": group, "level": level, "detail": detail}


def check_post(title: str, html_text: str, symbol: str = "") -> List[Dict[str, str]]:
    """Steps 1a-2b on any post (generated blog, pasted blog or white paper). level: ok | warn."""
    w = _Walker()
    w.feed(html_text or "")
    ev = w.events
    title = (title or next((e[1]["text"] for e in ev if e[0] == "h1"), "")).strip()
    sym = (symbol or "").upper().strip()
    out = []

    hp = headline_problems(title, sym)
    out.append(_check("Specific, level-driven headline", "structure", "warn" if hp else "ok",
                      f"\"{title}\"" + (": " + "; ".join(hp) if hp else "")))

    paras = [e[1] for e in ev if e[0] == "p"]
    body_paras = [p for p in paras if "byline" not in p["class"] and p["text"] and not p["text"].startswith("Report Date")]
    first = body_paras[0]["text"] if body_paras else ""
    first = re.sub(r"^Bottom Line:\s*", "", first)
    bp = bottom_line_problems(first, sym)
    out.append(_check("Two-sentence Bottom Line opening", "structure", "warn" if bp else "ok",
                      (first[:220] + ("…" if len(first) > 220 else "")) + (" — " + "; ".join(bp) if bp else "") if first
                      else "No opening paragraph found"))

    imgs = [i for i, e in enumerate(ev) if e[0] == "img"]
    marker = "<!-- chart -->" in (html_text or "")
    bad_imgs = []
    for n, i in enumerate(imgs):
        stop = imgs[n + 1] if n + 1 < len(imgs) else len(ev)
        lis, j = [], i + 1
        while j < stop and ev[j][0] not in ("h2",):
            if ev[j][0] == "li":
                lis.append(ev[j][1]["text"])
            if ev[j][0] == "ul_end" and lis:
                break
            j += 1
        priced = [x for x in lis if re.search(r"\$\d|\d\.\d{2}", x)]
        if not (2 <= len(lis) <= 3 and len(priced) >= 2):
            bad_imgs.append(n + 1)
    if imgs:
        out.append(_check("Chart levels written out beneath every chart", "structure", "warn" if bad_imgs else "ok",
                          f"{len(imgs)} image(s); " + (f"image {', '.join(map(str, bad_imgs))} needs 2-3 bullets with exact "
                                                      "levels directly beneath it" if bad_imgs else "each has 2-3 level bullets")))
    elif marker:
        lis = [e[1]["text"] for e in ev if e[0] == "li"]
        ok = 2 <= len([x for x in lis if "$" in x][:3])
        out.append(_check("Chart levels written out beneath every chart", "structure", "ok" if ok else "warn",
                          "Chart-level bullets are in place; upload the chart image where the HTML comment marks it, "
                          "directly above them" if ok else "Chart-level bullets missing"))
    else:
        out.append(_check("Chart levels written out beneath every chart", "structure", "ok", "No chart images in this post"))

    links = [e[1].get("href", "") for e in ev if e[0] == "a"]
    host = re.sub(r"^https?://(www\.)?", "", SITE_URL).lower()
    internal = [h for h in links if host in h.lower() and re.sub(r"^https?://(www\.)?", "", h.lower()).rstrip("/") not in
                (host, re.sub(r"^https?://(www\.)?", "", METHODOLOGY_URL.lower()).rstrip("/"))]
    n_int = len(set(internal))
    out.append(_check("Links to 1-2 earlier posts on the same ticker", "authority", "ok" if 1 <= n_int <= 2 else "warn",
                      f"{n_int} link(s) to other Sigmalytic pages" + ("" if n_int else ": add a natural link to a recent "
                      "post on the same stock or index") + ("; 1-2 is the target" if n_int > 2 else "")))

    text_all = " ".join(e[1]["text"] for e in ev if e[0] in ("p", "li"))
    has_byline = f"By the {BYLINE_TEAM}" in text_all and "Methodology & Editorial Standards" in text_all
    site_link = any(host in h.lower() for h in links)
    out.append(_check("Standard author byline", "authority", "ok" if has_byline and site_link else "warn",
                      BYLINE_TEXT + (" (linked)" if has_byline and site_link else
                                     " — missing or not linked to " + SITE_URL)))
    return out


def distribution_steps(url: str, flagship: bool, linkedin_text: str = "", x_text: str = "") -> List[Dict[str, str]]:
    """Steps 3a-3c: done by hand after publishing; the checklist gives the exact action."""
    return [
        _check("Publish in GoDaddy", "distribute", "manual",
               f"Publish in the Research and Intelligence blog. Expected URL: {url}"),
        _check("Request indexing (flagship only)", "distribute", "manual",
               (f"Flagship report: in Google Search Console, URL Inspection > paste {url} > Request Indexing.")
               if flagship else
               "Routine daily post: do not request indexing. Google picks it up from sitemap.blog.xml; saving manual "
               "requests for flagship reports avoids crawl throttling."),
        _check("Share a 3-bullet summary on LinkedIn and X", "distribute", "manual",
               "Use the LinkedIn and X drafts below: the opening takeaway, three chart levels and a direct link to the article."
               if (linkedin_text or x_text) else "Post the opening takeaway and chart levels with a direct link to the article."),
    ]


def checklist(title: str, html_text: str, url: str = "", symbol: str = "", flagship: bool = False,
              extra: Optional[List[Dict[str, str]]] = None, linkedin_text: str = "", x_text: str = "") -> Dict[str, Any]:
    items = check_post(title, html_text, symbol) + (extra or []) + distribution_steps(url or "(the post's URL)", flagship,
                                                                                     linkedin_text, x_text)
    return {"groups": [{"key": k, "label": lab, "items": [i for i in items if i["group"] == k]} for k, lab in GROUPS],
            "to_fix": sum(1 for i in items if i["level"] == "warn"), "flagship": bool(flagship)}
