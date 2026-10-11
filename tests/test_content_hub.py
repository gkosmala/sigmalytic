import pytest
from backend import content_hub as ch


def _chart(n=60, drift=0.3):
    bars, p = [], 100.0
    for i in range(n):
        p += drift
        bars.append({"date": f"2026-08-{(i % 28) + 1:02d}", "open": p - 0.2, "high": p + 0.8, "low": p - 0.9,
                     "close": p, "volume": 1_000_000 + (i % 5) * 50_000})
    return {"ok": True, "bars": bars, "hits": [{"type": "SPRING", "date": "2026-09-30", "level": 105.5}],
            "call_wall": 120.0, "put_wall": 100.0, "gamma_flip": 110.0,
            "weis_lines": {"ice_line_level": 108.25}}


@pytest.fixture
def facts():
    return ch.facts_from_chart_data("TEST", _chart())


def test_facts_computed(facts):
    assert facts["symbol"] == "TEST"
    assert facts["last_close"] == round(100 + 0.3 * 60, 2)
    assert facts["high_52w"] >= facts["last_close"]
    assert facts["pattern_signals"][0]["type"] == "Spring"
    assert facts["ice_line"] == 108.25


def test_facts_need_history():
    with pytest.raises(ValueError):
        ch.facts_from_chart_data("TEST", _chart(n=10))


def test_template_package_passes_all_checks(facts):
    pkg = ch.build_package("TEST", use_ai=False, facts=facts)
    assert pkg["blog_issues"] == []
    assert set(pkg["teasers"]) == set(ch.PLATFORM_ORDER)
    for plat, d in pkg["teasers"].items():
        assert d["ok"], (plat, d["issues"])
        assert d["chars"] <= d["limit"]
    assert pkg["blog"]["disclaimer"] in pkg["blog"]["html"]
    assert "utm_source=linkedin" in pkg["teasers"]["linkedin"]["text"]
    assert "utm_source=x" in pkg["teasers"]["x"]["reply"]


def test_x_link_not_in_main_text(facts):
    d = ch.template_teasers(facts, ch.template_blog(facts))["x"]
    assert "http" not in d["text"] and "utm_source=x" in d["reply"]


def test_x_weighted_length_counts_link_as_23():
    text = "a" * 250 + " https://example.com/a/very/long/path/that/would/be/long?utm_source=x&utm_medium=social"
    assert ch.weighted_len("x", text) == 250 + 1 + 23


def test_banned_phrases():
    assert ch.find_banned_phrases("This stock will soar, guaranteed!")
    assert ch.find_banned_phrases("You should buy now")
    assert not ch.find_banned_phrases("Educational research, not investment advice. Price closed above its average.")
    assert not ch.find_banned_phrases("This is not financial advice.")


def test_number_guard(facts):
    ok = f"Closed at ${facts['last_close']:,.2f}, {abs(facts['change_1d_pct']):.2f}% on the day."
    assert ch.numbers_trace_to_facts(ok, facts) == []
    assert ch.numbers_trace_to_facts("Closed at $987.65 today.", facts) == ["987.65"]


def test_validator_flags_problems():
    long_x = {"text": "a" * 300}
    assert any("limit" in i for i in ch.validate_teaser("x", long_x))
    assert any("hashtags" in i for i in ch.validate_teaser("facebook", {"text": "hi #a #b #c"}))
    assert any("Missing title" in i for i in ch.validate_teaser("pinterest", {"text": "hello"}))
    assert any("Advice" in i for i in ch.validate_teaser("linkedin", {"text": "It will rally, guaranteed."}))
    assert any("Link is in the main text" in i for i in ch.validate_teaser("reddit", {"title": "t", "text": "see https://a.co"}))


def test_ai_blog_clean_is_accepted(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    body = f"Closed at ${facts['last_close']:,.2f}."
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                                                   "sections": [{"heading": "h", "body": body}]})
    assert ch.generate_blog(facts, use_ai=True)["ai"] is True


def test_ai_teaser_failing_checks_falls_back(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_teasers", lambda f, b: {"x": {"text": "This will soar, guaranteed!"}})
    t = ch.generate_teasers(facts, ch.template_blog(facts), use_ai=True)
    assert t["x"]["source"] == "template" and t["x"]["ok"]


def test_no_key_uses_template(facts, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pkg = ch.build_package("TEST", use_ai=True, facts=facts)
    assert pkg["ai_used"] is False and any("AI key" in n for n in pkg["notes"])


def test_seo_markup(facts, monkeypatch):
    import json, re
    monkeypatch.setenv("CONTENT_HUB_OG_IMAGE", "https://example.com/og/test.png")
    monkeypatch.setenv("CONTENT_HUB_LOGO_URL", "https://example.com/logo.png")
    blog = ch.generate_blog(facts, use_ai=False)
    seo = blog["seo"]
    assert len(seo["title_tag"]) <= 60 and seo["title_tag"].startswith("TEST Stock Analysis")
    assert len(seo["meta_description"]) <= 155
    head = blog["head_tags"]
    for needle in ('rel="canonical"', 'name="robots"', 'property="og:image"', 'name="twitter:card"',
                   'application/ld+json', 'article:published_time'):
        assert needle in head, needle
    ld = json.loads(re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', head, re.S).group(1))
    types = [n["@type"] for n in ld["@graph"]]
    assert types == ["Article", "BreadcrumbList"]
    assert ld["@graph"][0]["image"] == ["https://example.com/og/test.png"]


def test_seo_checklist_flags_thin_copy_and_missing_image(facts, monkeypatch):
    monkeypatch.delenv("CONTENT_HUB_OG_IMAGE", raising=False)
    seo = ch.generate_blog(facts, use_ai=False)["seo"]
    flagged = {c["name"] for c in seo["checks"] if c["level"] != "ok"}
    assert "Enough original copy" in flagged and "Share image (Open Graph)" in flagged
    assert seo["warnings"] >= 2


def test_provider_selection(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CONTENT_HUB_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert ch.ai_provider() is None and not ch.ai_available()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert ch.ai_provider() == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert ch.ai_provider() == "anthropic"
    monkeypatch.setenv("CONTENT_HUB_PROVIDER", "openai")
    assert ch.ai_provider() == "openai"


def test_openai_request_shape(monkeypatch):
    import requests
    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": 'noise {"a": 1} noise'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json); return R()
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("CONTENT_HUB_OPENAI_MODEL", "gpt-test")
    assert ch._ai_json("sys", "usr") == {"a": 1}
    assert seen["url"].endswith("/v1/chat/completions") and seen["headers"]["Authorization"] == "Bearer sk-x"
    assert seen["body"]["model"] == "gpt-test" and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0]["role"] == "system"


def test_usage_exact_cost_and_unknown_model(monkeypatch, facts):
    import requests
    calls = []

    class R:
        def __init__(self, body): self._b = body
        def raise_for_status(self): pass
        def json(self): return self._b

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(url)
        return R({"model": "claude-sonnet-5-5", "usage": {"input_tokens": 1000, "output_tokens": 500},
                  "content": [{"type": "text", "text": '{"x": 1}'}]})
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    token = ch._USAGE.set([])
    try:
        ch._ai_json("s", "u"); ch._ai_json("s", "u")
        u = ch.summarize_usage(ch._USAGE.get())
    finally:
        ch._USAGE.reset(token)
    assert u["input_tokens"] == 2000 and u["output_tokens"] == 1000 and u["calls"] == 2
    assert u["cost_usd"] == round(2000 / 1e6 * 2 + 1000 / 1e6 * 10, 5)  # Sonnet 5.5: $2 in, $10 out per 1M
    assert ch.summarize_usage([{"model": "mystery", "input_tokens": 5, "output_tokens": 5, "reasoning_tokens": 0,
                                "provider": "x"}])["cost_usd"] is None


def test_openai_reasoning_tokens_counted(monkeypatch):
    import requests

    class R:
        def raise_for_status(self): pass
        def json(self): return {"model": "gpt-5.6-terra", "choices": [{"message": {"content": "{}"}}],
                                "usage": {"prompt_tokens": 100, "completion_tokens": 900,
                                          "completion_tokens_details": {"reasoning_tokens": 700}}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.setenv("OPENAI_API_KEY", "k")
    token = ch._USAGE.set([])
    try:
        ch._ai_json("s", "u"); u = ch.summarize_usage(ch._USAGE.get())
    finally:
        ch._USAGE.reset(token)
    assert u["output_tokens"] == 900 and u["reasoning_tokens"] == 700
    assert u["cost_usd"] == round(100 / 1e6 * 2 + 900 / 1e6 * 12, 5)


# ───────────── website report requirements ─────────────

def _ai_cand(facts, **over):
    body = f"{facts['symbol']} closed at ${facts['last_close']:,.2f}."
    cand = {"title": f"{facts['symbol']} Holds Its Trend", "meta_description": "m", "ai": True,
            "sections": [{"heading": "h", "body": body}],
            "news": {"us": {"text": "Treasury yields moved 12 basis points this week.", "urls": ["https://a.com/x"]},
                     "geopolitical": {"text": "Invented claim.", "urls": ["https://not-searched.com"]},
                     "institutional": None},
            "summary": {}, "private": {"A": {"supported": True, "reasoning": "r"}, "B": {"supported": False},
                                       "C": {"supported": False}, "selected": "A"},
            "_search_results": {"https://a.com/x": "Source A"}}
    cand.update(over)
    return cand


def test_report_structure_and_no_tables(facts, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    blog = ch.generate_blog(facts, use_ai=False)
    h = blog["html"]
    for needle in ("Market Data and Attribution", "Sigmalytic Summary", "Current condition", "Principal risk",
                   "What would strengthen the bullish case", "What would weaken it", "What traders should monitor next",
                   "Better Opportunities. Better Decisions. Better Trading Results.",
                   "Every decision creates information. Every outcome creates evidence.",
                   "www.sigmalyticquantcorp.com", "All rights reserved.", "<h2>Reference Sources</h2>", "Alpaca Markets: market data",
                   "Report Date:", "Market Data Through:", "proprietary analytical framework"):
        assert needle in h, needle
    assert (h.index("Sigmalytic Summary") < h.index("Better Opportunities") < h.index("Market Data and Attribution")
            < h.index("<h2>Reference Sources</h2>") < h.index("All rights") < h.index("research and educational purposes"))
    assert "<table" not in h.lower() and "FINRA" not in h and "footnote" not in h.lower()
    assert "PRIVATE" not in h and "Option A" not in h and "Option A" not in blog["markdown"]


def test_news_needs_real_search_source_and_option_a_needs_institutional(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: _ai_cand(facts))
    blog = ch.generate_blog(facts, use_ai=True)
    heads = [s["heading"] for s in blog["sections"]]
    assert "U.S. Market and Economic Developments" in heads
    assert "Geopolitical Developments" not in heads          # URL never came back from the search
    assert "Institutional and Liquidity Evidence" not in heads
    assert [x["url"] for x in blog["sources"]] == ["https://a.com/x"]
    assert blog["private"]["selected"] == "none" and "Dark-Pool" not in blog["title"]   # A needs sourced evidence
    assert "Geopolitical" in blog["note"]


def test_option_b_headline_used_when_supported(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    cand = _ai_cand(facts, private={"A": {"supported": False}, "B": {"supported": True, "reasoning": "r"},
                                    "C": {"supported": False}, "selected": "B"})
    monkeypatch.setattr(ch, "ai_blog", lambda f: cand)
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["title"] == ch.OPTION_TITLES["B"].format(s="TEST")
    assert blog["private"]["selected"] == "B" and "Option B" not in blog["html"] and "reasoning" not in blog["html"]


def test_web_search_request_pause_and_usage(monkeypatch):
    import requests
    sent = []

    class R:
        def __init__(self, b): self._b = b
        def raise_for_status(self): pass
        def json(self): return self._b

    replies = [
        {"model": "claude-sonnet-5-5", "stop_reason": "pause_turn", "usage": {"input_tokens": 100, "output_tokens": 10,
         "server_tool_use": {"web_search_requests": 2}},
         "content": [{"type": "web_search_tool_result", "content": [{"url": "https://a.com/x", "title": "A"}]}]},
        {"model": "claude-sonnet-5-5", "stop_reason": "end_turn", "usage": {"input_tokens": 50, "output_tokens": 20},
         "content": [{"type": "text", "text": 'pre {"k": 1}'}]},
    ]

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append(json); return R(replies[len(sent) - 1])
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    token = ch._USAGE.set([])
    try:
        out = ch._ai_json("s", "u", web_search=True); u = ch.summarize_usage(ch._USAGE.get())
    finally:
        ch._USAGE.reset(token)
    assert sent[0]["tools"][0]["name"] == "web_search" and sent[1]["messages"][-1]["role"] == "assistant"
    assert out["k"] == 1 and out["_search_results"] == {"https://a.com/x": "A"}
    assert u["searches"] == 2 and u["calls"] == 2
    assert u["cost_usd"] == round(150 / 1e6 * 2 + 30 / 1e6 * 10 + 2 * 0.01, 5)


def _fake_anthropic(monkeypatch, text, stop="end_turn"):
    import requests

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"model": "claude-sonnet-5-5", "stop_reason": stop,
                                "usage": {"input_tokens": 10, "output_tokens": 9000},
                                "content": [{"type": "text", "text": text}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)


def test_truncated_reply_is_repaired_and_kept(facts, monkeypatch):
    cut = ('{"title": "TEST: Can It Hold?", "meta_description": "m", "sections": ['
           '{"heading": "Executive Summary", "body": "TEST closed at $%.2f."}, '
           '{"heading": "Market Structure", "body": "Price is above its average."}, '
           '{"heading": "What Changed?", "body": "The rebound was cut o' % facts["last_close"])
    _fake_anthropic(monkeypatch, cut, stop="max_tokens")
    blog = ch.generate_blog(facts, use_ai=True)
    heads = [s["heading"] for s in blog["sections"]]
    assert blog["ai"] is True and heads[:2] == ["Executive Summary", "Market Structure"]
    assert "repaired" in blog["note"] and "Key Levels" in blog["note"]       # tells the editor what is missing
    assert "raw_ai_text" not in blog


def test_unreadable_reply_is_handed_back_raw(facts, monkeypatch):
    _fake_anthropic(monkeypatch, "Here is the report you asked for, written as prose with no JSON at all.")
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["ai"] is False and "written as prose" in blog["raw_ai_text"]
    assert "not wasted" in blog["note"]


def test_repair_json_cases():
    assert ch._repair_json('{"a": [1, 2, {"b": "x"}, {"c": "cut')["a"][:3] == [1, 2, {"b": "x"}]
    assert ch._repair_json('{"a": 1, "b": ') == {"a": 1}
    assert ch._repair_json("no braces") is None


def test_advice_wording_is_flagged_not_discarded(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                        "sections": [{"heading": "h", "body": "This stock will soar."}]})
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["ai"] is True and "advice or promise wording" in blog["note"]


def test_rate_limit_retried_once(monkeypatch):
    import requests
    calls = []

    class R:
        def __init__(self, code): self.status_code = code; self.headers = {"retry-after": "0"}
        def raise_for_status(self): pass
        def json(self): return {"model": "claude-sonnet-5-5", "usage": {"input_tokens": 1, "output_tokens": 1},
                                "content": [{"type": "text", "text": '{"ok": 1}'}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: (calls.append(1), R(429 if len(calls) == 1 else 200))[1])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    assert ch._ai_json("s", "u") == {"ok": 1} and len(calls) == 2


def _tf_chart(n=80, drift=0.5, with_pivots=True):
    c = _chart(n, drift)
    c["weis_lines"] = {"ice_line_level": 140.5,
                       "pivots": [{"kind": "swing_high", "price": 150.0, "bar_index": 70},
                                  {"kind": "swing_low", "price": 130.0, "bar_index": 60}] if with_pivots else []}
    return c


def test_timeframes_and_levels(facts):
    f = ch.attach_timeframes(dict(facts), {"weekly": _tf_chart(), "4h": _tf_chart(), "2h": {"ok": False, "error": "no bars"}})
    assert set(f["timeframes"]) == {"weekly", "4h"} and any("2-hour" in m for m in f["timeframes_missing"])
    assert f["timeframes"]["weekly"]["recent_pivots"][-1]["price"] in (150.0, 130.0)
    lv = f["levels"]
    assert all(x["price"] > f["last_close"] for x in lv["above"]) and all(x["price"] <= f["last_close"] for x in lv["below"])
    assert [x["price"] for x in lv["above"]] == sorted(x["price"] for x in lv["above"])
    # numbers from the extra timeframes are allowed by the guard
    assert ch.numbers_trace_to_facts("Weekly swing high near $150.00 and ice line near $140.50.", f) == []


def test_numbers_flagged_for_review_but_draft_kept(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                        "sections": [{"heading": "h", "body": "Price recovered $987.65 in a week."}]})
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["ai"] is True and "987.65" in blog["note"]


def test_weekly_is_required(monkeypatch):
    import sys, types
    calls = {"1Week": 0}

    def fake(sym, timeframe="1Day", limit=252, include_options=True):
        if timeframe == "1Week":
            calls["1Week"] += 1
            return {"ok": False, "error": "Insufficient bar history for XYZ."}
        return _tf_chart(260) if timeframe == "1Day" else _tf_chart()
    mod = types.ModuleType("backend.main"); mod.weis_radar_chart_data = fake
    monkeypatch.setitem(sys.modules, "backend.main", mod)
    with pytest.raises(ValueError, match="Weekly data could not be loaded"):
        ch.build_facts("XYZ")
    assert calls["1Week"] == 2  # tried twice


def test_weekly_present_when_available(monkeypatch):
    import sys, types
    mod = types.ModuleType("backend.main")
    mod.weis_radar_chart_data = lambda sym, timeframe="1Day", limit=252, include_options=True: (
        _tf_chart(260) if timeframe == "1Day" else _tf_chart())
    monkeypatch.setitem(sys.modules, "backend.main", mod)
    f = ch.build_facts("XYZ")
    assert {"weekly", "4h", "2h"} <= set(f["timeframes"])


def test_citation_markup_is_stripped(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    dirty = '<cite index="8-10">Musk said Tesla and SpaceX would own Terafab.</cite> (<cite index="2-11">Earnings are October 21.</cite>'
    _fake_anthropic(monkeypatch, __import__("json").dumps({
        "title": "T <cite index='1-1'>x</cite>", "meta_description": "m",
        "sections": [{"heading": "Executive Summary", "body": f"TEST closed at ${facts['last_close']:,.2f}."}],
        "news": {"company": {"text": dirty, "urls": ["https://a.com/x"]}}, "summary": {}, "private": {}}))
    import requests
    orig = requests.post
    def post(*a, **k):
        r = orig(*a, **k); b = r.json()
        b["content"].insert(0, {"type": "web_search_tool_result", "content": [{"url": "https://a.com/x", "title": "A"}]})
        r.json = lambda: b
        return r
    monkeypatch.setattr(requests, "post", post)
    blog = ch.generate_blog(facts, use_ai=True)
    assert "cite" not in blog["html"].lower() and "cite" not in blog["markdown"].lower()
    assert "Musk said Tesla and SpaceX would own Terafab." in blog["html"] and "<cite" not in blog["title"]
