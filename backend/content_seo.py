# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/content_seo.py
----------------------
Search-engine markup for Content Hub blog drafts: title tag, meta description, canonical, robots,
Open Graph, Twitter card, Article + BreadcrumbList JSON-LD, and a checklist that tells the editor what
is still weak before publishing.

Honest scope: markup helps Google understand and present a page, it does not make a page rank. Ranking
depends mostly on content quality, site authority, links and page experience. This module covers what
can be controlled in the page itself and flags the rest (thin copy, missing share image, no internal links).
"""

from __future__ import annotations

import html as _html
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

TITLE_MAX, TITLE_MIN = 60, 30
HEADLINE_MAX = 65   # GoDaddy headline limit
DESC_MAX, DESC_MIN = 155, 110
MIN_WORDS = 300

BRAND = "Sigmalytic"
ORG_NAME = os.getenv("CONTENT_HUB_AUTHOR_NAME", "Sigmalytic Quant Corporation")


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def pick_title_tag(symbol: str, headline: str, date_label: str) -> str:
    """Longest candidate that fits in 60 characters; the search term (symbol + 'stock analysis') comes first."""
    candidates = [
        f"{symbol} Stock Analysis: Wyckoff & Weis Read, {date_label} | {BRAND}",
        f"{symbol} Stock Analysis: Wyckoff & Weis Read | {BRAND}",
        f"{symbol} Stock Analysis: Market Structure | {BRAND}",
        f"{symbol} Stock Analysis | {BRAND}",
    ]
    for c in candidates:
        if len(c) <= TITLE_MAX:
            return c
    return candidates[-1][:TITLE_MAX]


def fit_description(text: str, symbol: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= DESC_MAX:
        return text
    cut = text[: DESC_MAX - 1].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…"


def _word_count(blog: Dict[str, Any]) -> int:
    return len(" ".join(s["body"] for s in blog["sections"]).split())


def _iso(date_str: str) -> str:
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(hour=21, tzinfo=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def build_jsonld(symbol: str, headline: str, description: str, url: str, as_of: str, site_url: str,
                 blog_path: str, image: str, keywords: List[str]) -> Dict[str, Any]:
    published = _iso(as_of)
    publisher: Dict[str, Any] = {"@type": "Organization", "name": ORG_NAME, "url": site_url}
    if _env("CONTENT_HUB_LOGO_URL"):
        publisher["logo"] = {"@type": "ImageObject", "url": _env("CONTENT_HUB_LOGO_URL")}
    author: Dict[str, Any] = {"@type": "Organization", "name": ORG_NAME, "url": site_url}
    if _env("CONTENT_HUB_AUTHOR_URL"):
        author = {"@type": "Person", "name": _env("CONTENT_HUB_AUTHOR_NAME") or ORG_NAME, "url": _env("CONTENT_HUB_AUTHOR_URL")}
    article: Dict[str, Any] = {
        "@type": "Article",
        "headline": headline[:110],
        "description": description,
        "datePublished": published,
        "dateModified": datetime.now(timezone.utc).isoformat(),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "author": author,
        "publisher": publisher,
        "articleSection": "Market Analysis",
        "keywords": ", ".join(keywords),
        "inLanguage": "en-US",
    }
    if image:
        article["image"] = [image]
    crumbs = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url + "/"},
            {"@type": "ListItem", "position": 2, "name": "Research & Intelligence", "item": site_url + blog_path},
            {"@type": "ListItem", "position": 3, "name": headline[:110], "item": url},
        ],
    }
    return {"@context": "https://schema.org", "@graph": [article, crumbs]}


def build_seo(facts: Dict[str, Any], blog: Dict[str, Any], url: str, site_url: str, blog_path: str,
              disclaimer_present: bool = True) -> Dict[str, Any]:
    esc = lambda s: _html.escape(str(s), quote=True)
    symbol, as_of = facts["symbol"], facts["as_of"]
    try:
        date_label = datetime.strptime(as_of[:10], "%Y-%m-%d").strftime("%b %-d, %Y")
    except Exception:
        date_label = as_of
    title_tag = pick_title_tag(symbol, blog["title"], date_label)
    description = fit_description(blog["meta_description"], symbol)
    image = _env("CONTENT_HUB_OG_IMAGE")
    image_alt = f"{symbol} price chart with Wyckoff and Weis pattern markers, data as of {as_of}"
    keywords = [f"{symbol} stock analysis", f"{symbol} technical analysis", f"{symbol} Wyckoff",
                f"{symbol} market structure", "Weis wave"]
    jsonld = build_jsonld(symbol, blog["title"], description, url, as_of, site_url, blog_path, image, keywords)
    published = _iso(as_of)

    tags = [
        f"<title>{esc(title_tag)}</title>",
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{esc(url)}">',
        '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:site_name" content="{esc(ORG_NAME)}">',
        '<meta property="og:locale" content="en_US">',
        f'<meta property="og:title" content="{esc(blog["title"])}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(url)}">',
        f'<meta property="article:published_time" content="{published}">',
        '<meta property="article:section" content="Market Analysis">',
        f'<meta property="article:tag" content="{esc(symbol)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(blog["title"])}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
    ]
    if image:
        tags += [f'<meta property="og:image" content="{esc(image)}">', '<meta property="og:image:width" content="1200">',
                 '<meta property="og:image:height" content="630">', f'<meta property="og:image:alt" content="{esc(image_alt)}">',
                 f'<meta name="twitter:image" content="{esc(image)}">', f'<meta name="twitter:image:alt" content="{esc(image_alt)}">']
    if _env("CONTENT_HUB_TWITTER_HANDLE"):
        tags.append(f'<meta name="twitter:site" content="{esc(_env("CONTENT_HUB_TWITTER_HANDLE"))}">')
    tags.append('<script type="application/ld+json">\n' + json.dumps(jsonld, indent=2) + "\n</script>")

    words = _word_count(blog)
    h2 = len(blog["sections"])
    first_para = blog["sections"][0]["body"].lower() if blog["sections"] else ""
    checks: List[Dict[str, Any]] = [
        {"name": "Headline length", "level": "ok" if len(blog["title"]) <= HEADLINE_MAX else "warn",
         "detail": f"{len(blog['title'])} characters (GoDaddy allows {HEADLINE_MAX})"},
        {"name": "Title tag length", "level": "ok" if TITLE_MIN <= len(title_tag) <= TITLE_MAX else "warn",
         "detail": f"{len(title_tag)} characters (target {TITLE_MIN}-{TITLE_MAX})"},
        {"name": "Meta description length", "level": "ok" if DESC_MIN <= len(description) <= DESC_MAX else "warn",
         "detail": f"{len(description)} characters (target {DESC_MIN}-{DESC_MAX})"},
        {"name": "Symbol in title, headline, description and opening paragraph",
         "level": "ok" if all(symbol.lower() in x.lower() for x in (title_tag, blog["title"], description, first_para)) else "warn",
         "detail": symbol},
        {"name": "One H1 and several H2 sections", "level": "ok" if h2 >= 3 else "warn", "detail": f"{h2} sections"},
        {"name": "Enough original copy", "level": "ok" if words >= MIN_WORDS else "warn",
         "detail": f"{words} words; under {MIN_WORDS} reads as thin content. Use Claude mode or add your own commentary."
         if words < MIN_WORDS else f"{words} words"},
        {"name": "Canonical URL", "level": "ok", "detail": url},
        {"name": "Article and breadcrumb structured data", "level": "ok", "detail": "JSON-LD included"},
        {"name": "Share image (Open Graph)", "level": "ok" if image else "warn",
         "detail": image or "Not set. Set CONTENT_HUB_OG_IMAGE (1200x630) so link previews and Google Discover can show a chart."},
        {"name": "Publisher logo in structured data", "level": "ok" if _env("CONTENT_HUB_LOGO_URL") else "warn",
         "detail": "set" if _env("CONTENT_HUB_LOGO_URL") else "Not set. Set CONTENT_HUB_LOGO_URL."},
        {"name": "Named author", "level": "ok" if _env("CONTENT_HUB_AUTHOR_URL") else "warn",
         "detail": "Person author set" if _env("CONTENT_HUB_AUTHOR_URL") else
         "Using the company as author. For finance content Google weighs a named, credentialed author; "
         "set CONTENT_HUB_AUTHOR_NAME and CONTENT_HUB_AUTHOR_URL (a bio page)."},
        {"name": "Disclaimer on the page", "level": "ok" if disclaimer_present else "warn", "detail": "included"},
        {"name": "Internal links to related research", "level": "warn",
         "detail": "Add links from this post to related research pages, and from your Research & Intelligence index "
                   "and homepage to this post."},
    ]
    return {"title_tag": title_tag, "meta_description": description, "head_tags": "\n".join(tags), "jsonld": jsonld,
            "checks": checks, "warnings": sum(1 for c in checks if c["level"] != "ok"), "word_count": words,
            "image_alt": image_alt}
