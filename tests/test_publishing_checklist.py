"""Publishing checklist: level-driven headline, two-sentence Bottom Line, chart levels in text, internal links from
sitemap.blog.xml, standard byline, and the LinkedIn / X 3-bullet summary (backend/publishing_checklist.py)."""
import pytest

from backend import content_hub as ch
from backend import publishing_checklist as pc
from tests.test_content_hub import _chart

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
 <url><loc>https://sigmalyticquantcorp.com/research-and-intelligence/f/test-stock-analysis-can-buyers-defend</loc><lastmod>2026-11-10</lastmod></url>
 <url><loc>https://sigmalyticquantcorp.com/research-and-intelligence/f/test-market-structure-2026-11-12</loc><lastmod>2026-11-12T13:00:00Z</lastmod></url>
 <url><loc>https://sigmalyticquantcorp.com/research-and-intelligence/f/test-older-read</loc><lastmod>2026-10-01</lastmod></url>
 <url><loc>https://sigmalyticquantcorp.com/research-and-intelligence/f/attest-latest-notes</loc><lastmod>2026-11-13</lastmod></url>
 <url><loc>https://sigmalyticquantcorp.com/research-and-intelligence/f/s-p-500-structural-macro-report</loc><lastmod>2026-11-11</lastmod></url>
</urlset>"""


@pytest.fixture(autouse=True)
def _sitemap(monkeypatch):
    pc._SITEMAP_CACHE.update(at=0.0, urls=[])
    monkeypatch.setattr(pc, "_fetch", lambda url: SITEMAP)


@pytest.fixture
def facts():
    return ch.facts_from_chart_data("TEST", _chart())


def test_related_posts_newest_two_same_ticker_only():
    r = pc.related_posts("TEST")
    assert [p["url"].rsplit("/", 1)[-1] for p in r["posts"]] == ["test-market-structure-2026-11-12",
                                                                 "test-stock-analysis-can-buyers-defend"]
    assert r["posts"][0]["anchor"] == "Sigmalytic's TEST report from Thursday, November 12"
    assert pc.related_posts("SPY")["posts"][0]["url"].endswith("s-p-500-structural-macro-report")  # index aliases


def test_sitemap_index_is_followed(monkeypatch):
    index = ('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://x.com/a.xml</loc>'
             '</sitemap></sitemapindex>')
    monkeypatch.setattr(pc, "_fetch", lambda url: index if url == pc.SITEMAP_URL else SITEMAP)
    assert len(pc.related_posts("TEST")["posts"]) == 2


def test_unreadable_sitemap_never_breaks_the_post(facts, monkeypatch):
    def boom(url):
        raise ConnectionError("down")
    monkeypatch.setattr(pc, "_fetch", boom)
    pkg = ch.build_package("TEST", use_ai=False, facts=facts)
    item = next(i for g in pkg["publishing"]["groups"] for i in g["items"] if i["name"].startswith("Links to"))
    assert item["level"] == "warn" and "sitemap could not be read" in item["detail"]


def test_template_post_meets_every_structure_rule(facts):
    pkg = ch.build_package("TEST", use_ai=False, facts=facts)
    blog, pub = pkg["blog"], pkg["publishing"]
    auto = [i for g in pub["groups"] for i in g["items"] if i["level"] != "manual"]
    assert all(i["level"] == "ok" for i in auto), [i for i in auto if i["level"] != "ok"]
    assert pub["to_fix"] == 0 and pkg["blog_issues"] == []
    html = blog["html"]
    assert html.index('class="byline"') < html.index('class="bottom-line"') < html.index("<h2>")
    assert "By the <a href=\"https://sigmalyticquantcorp.com\">Sigmalytic Quant Research Team</a>" in html
    assert len(pc.sentences(blog["bottom_line"])) == 2 and "invalidation level" in blog["bottom_line"]
    assert html.index("<!-- chart -->") < html.index("<li>Support $")
    assert 2 <= len(blog["chart_bullets"]) <= 3 and "call wall $120.00" in html
    assert 'href="https://sigmalyticquantcorp.com/research-and-intelligence/f/test-market-structure-2026-11-12"' in html
    assert "[[1]]" not in html and "[[1]]" not in blog["markdown"]
    assert "**Bottom Line:**" in blog["markdown"] and "[Sigmalytic's TEST report from Thursday, November 12](" in blog["markdown"]
    assert blog["title"].startswith("TEST Stock Analysis:") and "$" in blog["title"] and len(blog["title"]) <= 65


def test_flagship_only_gets_request_indexing(facts):
    routine = ch.build_package("TEST", use_ai=False, facts=facts)
    flag = ch.build_package("TEST", use_ai=False, facts=facts, flagship=True)
    get = lambda p: next(i for i in p["publishing"]["groups"][2]["items"] if i["name"].startswith("Request indexing"))
    assert "do not request indexing" in get(routine)["detail"]
    assert "Request Indexing" in get(flag)["detail"] and flag["blog"]["url"] in get(flag)["detail"]


def test_linkedin_and_x_carry_takeaway_three_levels_and_direct_link(facts):
    pkg = ch.build_package("TEST", use_ai=False, facts=facts)
    li, x = pkg["teasers"]["linkedin"], pkg["teasers"]["x"]
    assert li["ok"] and x["ok"] and li["source"] == x["source"] == "checklist"
    assert li["text"].startswith(pkg["blog"]["bottom_line"]) and li["text"].count("\n• ") == 3
    assert x["text"].count("\n• ") == 3 and "utm_source=x" in x["text"] and ch.SHORT_DISCLAIMER in x["text"]
    assert ch.weighted_len("x", x["text"]) <= 280


def _ai_cand(facts, **kw):
    base = {"title": "TEST Stock Analysis: Can Buyers Defend $115.15 Support?", "meta_description": "m" * 120, "ai": True,
            "sections": [{"heading": h, "body": f"TEST note for {h}."} for h in ch.EXPECTED_SECTIONS],
            "summary": {}, "news": {}, "image": {},
            "bottom_line": "TEST closed at $118.00 with a buyer-led bias above the 20-day average. "
                           "A close below $115.15 is the invalidation level."}
    base.update(kw)
    return base


def test_ai_bottom_line_and_link_marker_used(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    secs = [{"heading": h, "body": ("As noted in [[1]], the structure held." if h == "What Changed?" else f"TEST {h}.")}
            for h in ch.EXPECTED_SECTIONS]
    monkeypatch.setattr(ch, "ai_blog", lambda f: _ai_cand(facts, sections=secs))
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["bottom_line"].startswith("TEST closed at $118.00 with a buyer-led bias")
    assert "As noted in <a href=" in blog["html"] and blog["html"].count("For the earlier read") == 0


def test_bad_ai_bottom_line_replaced_and_flagged(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: _ai_cand(facts, bottom_line="TEST looks strong at $118.00."))
    blog = ch.generate_blog(facts, use_ai=True)
    assert "Bottom Line has 1 sentences" in blog["note"] and blog["bottom_line"] == pc.template_bottom_line(facts)


def test_ai_headline_without_level_is_flagged_not_replaced(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: _ai_cand(facts, title="TEST Holds Its Trend"))
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["title"] == "TEST Holds Its Trend" and "Headline rule" in blog["note"] and "Suggested:" in blog["note"]


def test_link_inserted_when_ai_skips_marker(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: _ai_cand(facts))
    blog = ch.generate_blog(facts, use_ai=True)
    wc = next(s for s in blog["sections"] if s["heading"] == "What Changed?")
    assert wc["body"].endswith("For the earlier read, see [[1]].") and "For the earlier read, see <a href=" in blog["html"]


def test_check_pasted_white_paper():
    good = ("<h1>SPY Weekly White Paper: Can the S&P 500 Hold $660.00?</h1>"
            f"<p class='byline'>{pc.byline_html()}</p>"
            "<p>SPY closed at $664.20 with a balanced bias. A close below $660.00 is the invalidation level.</p>"
            "<p>As noted in <a href='https://sigmalyticquantcorp.com/research-and-intelligence/f/s-p-500-macro'>Tuesday's "
            "report</a>, breadth narrowed.</p>"
            "<img src='chart.png'><ul><li>Support $660.00; resistance $671.50.</li><li>Call wall $675.00; put wall "
            "$650.00.</li></ul>"
            "<img src='chart2.png'><ul><li>20-day $662.10; 50-day $655.40.</li><li>200-day $610.00.</li></ul>")
    items = pc.check_post("", good, "SPY")
    assert all(i["level"] == "ok" for i in items), [i for i in items if i["level"] != "ok"]
    bad = good.replace("<ul><li>20-day $662.10; 50-day $655.40.</li><li>200-day $610.00.</li></ul>", "<p>See chart.</p>")
    chart = next(i for i in pc.check_post("", bad, "SPY") if i["name"].startswith("Chart levels"))
    assert chart["level"] == "warn" and "image 2" in chart["detail"]
    plain = pc.check_post("Market thoughts", "<p>Some text. More text. Even more.</p>")
    lv = {i["name"]: i["level"] for i in plain}
    assert lv["Specific, level-driven headline"] == lv["Two-sentence Bottom Line opening"] == "warn"
    assert lv["Standard author byline"] == lv["Links to 1-2 earlier posts on the same ticker"] == "warn"


def test_headline_rules():
    assert pc.headline_problems("NVDA Stock Analysis: Can Buyers Defend $224.00 Support?", "NVDA") == []
    assert any("price level" in x for x in pc.headline_problems("NVDA rallies again", "NVDA"))
    assert any("65" in x for x in pc.headline_problems(
        "NVDA Stock Analysis: Can Buyers Defend $224.00 Support Ahead of Volume Rotation?", "NVDA"))


def test_check_endpoint_and_flagship_passthrough(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    main.app.dependency_overrides[main.require_admin] = lambda: "admin"
    try:
        c = TestClient(main.app)
        r = c.post("/api/admin/content-hub/check", json={"title": "NVDA Stock Analysis: Can Buyers Defend $224.00?",
                                                          "html": "<p>Only text.</p>", "symbol": "nvda", "flagship": True}).json()
        assert r["ok"] and r["flagship"] and [g["key"] for g in r["groups"]] == ["structure", "authority", "distribute"]
        assert c.post("/api/admin/content-hub/check", json={"html": " "}).json()["ok"] is False
        seen = {}
        monkeypatch.setattr(ch, "build_package", lambda s, use_ai=True, **kw: seen.update(kw) or {"symbol": s})
        main._CONTENT_HUB_REUSE.clear()
        c.post("/api/admin/content-hub/generate", json={"symbol": "NVDA", "flagship": True})
        assert seen == {"flagship": True}
    finally:
        main.app.dependency_overrides.clear()
