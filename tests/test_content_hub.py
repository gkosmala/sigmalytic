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
    assert facts["pattern_signals"][0]["type"] == "Bear Trap"
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
            "news": {"us": {"text": "Treasury yields moved 12 basis points this week.", "urls": ["https://www.reuters.com/x"]},
                     "geopolitical": {"text": "Invented claim.", "urls": ["https://not-searched.com"]},
                     "institutional": None},
            "summary": {}, "private": {"A": {"supported": True, "reasoning": "r"}, "B": {"supported": False},
                                       "C": {"supported": False}, "selected": "A"},
            "_search_results": {"https://www.reuters.com/x": "Source A"}}
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
    assert [x["url"] for x in blog["sources"]] == ["https://www.reuters.com/x"]
    assert blog["private"]["selected"] == "none" and "Dark-Pool" not in blog["title"]   # A needs sourced evidence
    assert "Geopolitical" in blog["note"]


def test_option_b_is_private_idea_and_never_the_headline(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    cand = _ai_cand(facts, private={"A": {"supported": False}, "B": {"supported": True, "reasoning": "r"},
                                    "C": {"supported": False}, "selected": "B"})
    monkeypatch.setattr(ch, "ai_blog", lambda f: cand)
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["title"] == "TEST Holds Its Trend"                # the model's own headline, not the option text
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
         "content": [{"type": "web_search_tool_result", "content": [{"url": "https://www.reuters.com/x", "title": "A"}]}]},
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
    assert out["k"] == 1 and out["_search_results"] == {"https://www.reuters.com/x": "A"}
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
    assert "repaired" in blog["note"] and "Key Levels" not in blog["note"]   # Key Levels is written by code, so it is never missing
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
    out = ch._ai_json("s", "u")
    assert out["ok"] == 1 and len(calls) == 2


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
        "news": {"company": {"text": dirty, "urls": ["https://www.reuters.com/x"]}}, "summary": {}, "private": {}}))
    import requests
    orig = requests.post
    def post(*a, **k):
        r = orig(*a, **k); b = r.json()
        b["content"].insert(0, {"type": "web_search_tool_result", "content": [{"url": "https://www.reuters.com/x", "title": "A"}]})
        r.json = lambda: b
        return r
    monkeypatch.setattr(requests, "post", post)
    blog = ch.generate_blog(facts, use_ai=True)
    assert "cite" not in blog["html"].lower() and "cite" not in blog["markdown"].lower()
    assert "Musk said Tesla and SpaceX would own Terafab." in blog["html"] and "<cite" not in blog["title"]


def test_effort_sent_thinking_recorded_and_400_fallback(monkeypatch):
    import requests
    sent = []

    class R:
        def __init__(self, code, body=None): self.status_code = code; self.headers = {}; self._b = body
        def raise_for_status(self): pass
        def json(self): return self._b

    ok = {"model": "claude-sonnet-5-5", "stop_reason": "end_turn",
          "usage": {"input_tokens": 100, "output_tokens": 900, "output_tokens_details": {"thinking_tokens": 600}},
          "content": [{"type": "text", "text": '{"k": 1}'}]}

    def post(url, headers=None, json=None, timeout=None):
        sent.append(dict(json))
        return R(400) if ("output_config" in json) and len(sent) == 1 else R(200, ok)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    token = ch._USAGE.set([])
    try:
        out = ch._ai_json("s", "u"); u = ch.summarize_usage(ch._USAGE.get())
    finally:
        ch._USAGE.reset(token)
    assert sent[0]["output_config"] == {"effort": "low"} and "output_config" not in sent[1]
    assert out["k"] == 1 and out["_thinking"] == 600 and u["reasoning_tokens"] == 600


def _bars_for(n=252):
    import random
    random.seed(1); p = 300.0; out = []
    for i in range(n):
        p += random.uniform(-5, 5.5); o = p + random.uniform(-2, 2)
        out.append([f"2026-01-{(i % 28) + 1:02d}", o, max(o, p) + 2, min(o, p) - 2, p, 90e6])
    return out


def test_share_image_is_png_of_expected_size(facts):
    import struct
    from backend import content_chart as cc
    bars = _bars_for()
    png = cc.render_share_image(facts, bars)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (1800, 945)
    with pytest.raises(ValueError):
        cc.render_share_image(facts, bars[:10])


def test_package_includes_share_image_and_keeps_bars_out_of_facts(facts):
    f = dict(facts); f["_chart_bars"] = _bars_for()
    pkg = ch.build_package("TEST", use_ai=False, facts=f)
    assert pkg["share_image"]["filename"].endswith("-share-image.png") and len(pkg["share_image"]["png_b64"]) > 1000
    assert "_chart_bars" not in pkg["facts"]


def test_share_image_failure_never_breaks_report(facts, monkeypatch):
    from backend import content_chart as cc
    monkeypatch.setattr(cc, "render_share_image", lambda f, b: (_ for _ in ()).throw(RuntimeError("boom")))
    f = dict(facts); f["_chart_bars"] = _bars_for()
    pkg = ch.build_package("TEST", use_ai=False, facts=f)
    assert pkg["share_image"] is None and any("Share image could not be drawn" in n for n in pkg["notes"])


def test_logo_file_is_found_and_drawn(facts):
    from backend import content_chart as cc
    assert cc._logo_path() and cc._logo_path().endswith("sigmalytic_logo.png")
    assert cc.render_share_image(facts, _bars_for(), title="TEST", view_text="x")[:4] == b"\x89PNG"


def test_image_text_from_ai_is_used_and_number_checked(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    body = f"TEST closed at ${facts['last_close']:,.2f}."
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                        "sections": [{"heading": "h", "body": body}],
                        "image": {"view": "Constructive rebound, but price is still below long-term resistance.",
                                  "volume": "Volume was light and price reached $987.65."}})
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["image_text"]["view"].startswith("Constructive rebound")
    assert "987.65" in blog["note"]                      # an invented number in the image text is flagged too


def test_image_text_falls_back_to_template(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                        "sections": [{"heading": "h", "body": "Plain text."}], "image": {"view": "", "volume": "x" * 400}})
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["image_text"]["view"] and len(blog["image_text"]["volume"]) <= 215


def test_timeframe_volume_uses_previous_complete_bar():
    c = _tf_chart(80)
    for i, b in enumerate(c["bars"]):
        b["volume"] = 1000.0
    c["bars"][-1]["volume"] = 5.0           # the newest bar is still forming
    tf = ch.timeframe_facts(c, "weekly")
    assert tf["prior_bar_volume_vs_20_bar_avg"] == 1.0 and "volume_vs_20_bar_avg" not in tf


def test_renderer_takes_volume_text(facts):
    from backend import content_chart as cc
    png = cc.render_share_image(facts, _bars_for(), title="TEST", view_text="a b c", volume_text="Volume ran lighter than usual.")
    assert png[:4] == b"\x89PNG"


def test_panel_text_never_cut_mid_sentence():
    from backend import content_chart as cc
    long = "First sentence is here. " * 12
    lines = cc._fit_lines(long)
    assert len(lines) <= 5 and lines[-1].endswith(".")
    one = cc._fit_lines("word " * 80)
    assert len(one) == 5 and one[-1].endswith("…")


def test_weaker_sources_never_listed_or_used_alone(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    found = {"https://www.cnbc.com/a": "CNBC", "https://albertodd.substack.com/p/x": "Substack", "https://finbold.com/y": "Finbold"}
    cand = _ai_cand(facts, news={
        "us": {"text": "Yields rose.", "urls": ["https://albertodd.substack.com/p/x", "https://www.cnbc.com/a"]},
        "company": {"text": "A forecast.", "urls": ["https://finbold.com/y"]}, "institutional": None}, _search_results=found)
    monkeypatch.setattr(ch, "ai_blog", lambda f: cand)
    blog = ch.generate_blog(facts, use_ai=True)
    heads = [s["heading"] for s in blog["sections"]]
    assert "U.S. Market and Economic Developments" in heads and not any("Company" in h for h in heads)
    assert [x["url"] for x in blog["sources"]] == ["https://www.cnbc.com/a"]       # weaker URL never listed
    assert "only weaker sources" in blog["note"]
    assert ch.is_trusted_source("https://news.sec.gov/x") and ch.is_trusted_source("https://www.reuters.com/a")
    assert not ch.is_trusted_source("https://evilreuters.com/a") and not ch.is_trusted_source("https://finbold.com/y")


def test_session_state_live_and_closed():
    from datetime import datetime, timezone
    live = ch.session_state("2026-10-12", now=datetime(2026, 10, 12, 15, 5, tzinfo=timezone.utc))      # 11:05 a.m. ET Monday
    assert live["live"] and live["stamp"] == "11:05 a.m. ET" and live["verb"] == "is trading at"
    after = ch.session_state("2026-10-12", now=datetime(2026, 10, 12, 21, 0, tzinfo=timezone.utc))     # 5:00 p.m. ET
    assert not after["live"] and after["verb"] == "closed at"
    fri = ch.session_state("2026-10-09", now=datetime(2026, 10, 12, 15, 5, tzinfo=timezone.utc))       # last bar is Friday
    assert not fri["live"]
    sat = ch.session_state("2026-10-10", now=datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc))
    assert not sat["live"]


def test_live_session_wording_in_template(facts, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    facts["session"] = {"live": True, "stamp": "11:05 a.m. ET", "verb": "is trading at", "day_word": "so far today"}
    blog = ch.generate_blog(facts, use_ai=False)
    assert "is trading at" in blog["html"] and "closed at" not in blog["html"]
    assert "As of 11:05 a.m. ET, this is the current market" in blog["html"]


def test_search_restricted_to_major_domains_with_400_fallback(monkeypatch):
    import requests, copy
    sent = []

    class R:
        def __init__(self, code, body=None): self.status_code = code; self.headers = {}; self._b = body
        def raise_for_status(self): pass
        def json(self): return self._b

    ok = {"model": "m", "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
          "content": [{"type": "text", "text": '{"k": 1}'}]}

    def post(url, headers=None, json=None, timeout=None):
        sent.append(copy.deepcopy(json))
        tools = json.get("tools") or [{}]
        return R(400) if "allowed_domains" in tools[0] else R(200, ok)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    token = ch._USAGE.set([])
    try:
        out = ch._ai_json("s", "u", web_search=True)
    finally:
        ch._USAGE.reset(token)
    first = sent[0]["tools"][0]
    assert "reuters.com" in first["allowed_domains"] and "cnbc.com" in first["allowed_domains"]
    assert "allowed_domains" not in sent[-1]["tools"][0] and out["k"] == 1       # rejected filter: retried without it

def test_headline_limit_65_is_flagged(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    long_title = "TEST " + "x" * 70
    cand = _ai_cand(facts, title=long_title, private={"A": {"supported": False}, "B": {"supported": False},
                                                       "C": {"supported": False}, "selected": "none"})
    monkeypatch.setattr(ch, "ai_blog", lambda f: cand)
    blog = ch.generate_blog(facts, use_ai=True)
    assert "GoDaddy allows 65" in (blog.get("note") or "")
    assert any(c["name"] == "Headline length" and c["level"] == "warn" for c in blog["seo"]["checks"])
    short = _ai_cand(facts, title="TEST Holds Its Trend", private={"A": {"supported": False}, "B": {"supported": False},
                                                                    "C": {"supported": False}, "selected": "none"})
    monkeypatch.setattr(ch, "ai_blog", lambda f: short)
    ok = ch.generate_blog(facts, use_ai=True)
    assert "GoDaddy allows" not in (ok.get("note") or "")
    assert any(c["name"] == "Headline length" and c["level"] == "ok" for c in ok["seo"]["checks"])


def _aapl_like(facts):
    facts.update({"session_high": 342.63, "session_low": 337.60, "last_close": 339.63, "prev_close": 336.64,
                  "session": {"live": True, "stamp": "11:36 a.m. ET", "verb": "is trading at", "day_word": "so far today"}})
    facts["timeframes"] = {"4h": {"label": "4-hour", "recent_pivots": [
        {"kind": "swing_low", "price": 328.7}, {"kind": "swing_low", "price": 325.81}, {"kind": "swing_low", "price": 330.62}]}}
    facts["levels"] = {"above": [{"price": 340.0, "label": "put wall"}, {"price": 345.34, "label": "high"}], "below": []}
    return ch.add_derived(facts)


def test_derived_facts_range_swings_and_traded_through(facts):
    f = _aapl_like(facts)
    assert f["day_range"]["half"] == "lower" and abs(f["day_range"]["position_pct"] - 40.4) < 0.1
    assert f["timeframes"]["4h"]["swing_low_direction"] == "mixed"
    lv = {x["price"]: x["traded_today"] for x in f["levels"]["above"]}
    assert lv[340.0] is True and lv[345.34] is False


def test_consistency_flags_contradictions(facts):
    f = _aapl_like(facts)
    bad = ["The price is in the upper half of today's range of $337.60 to $342.63.",
           "The recent swing lows are 328.7, 325.81 and 330.62, so lows are rising only modestly.",
           "Participation is thin so far today.",
           "Index moves and energy prices have been shaping risk appetite this week."]
    out = " | ".join(ch.consistency_issues(f, bad))
    assert "lower half" in out and "swing lows rising" in out and "light or thin" in out and "backdrop" in out
    good = ["Price is in the lower half of today's range.", "The swing lows are mixed.",
            "Daily volume so far today is 0.26 of the 20-day average; this alone does not establish whether participation is normal."]
    assert ch.consistency_issues(f, good) == []


def test_price_formatting_only_touches_known_prices(facts):
    f = _aapl_like(facts)
    t = ch.format_prices("The 50-day is 323.0 and the swing low 300.0 and 339.3; volume was 0.26 of average, up 0.89%, 1.16x.", f)
    assert "0.26 of" in t and "0.89%" in t and "1.16x" in t
    t2 = ch.format_prices("Support near 328.7 and 340.0 and $339.63.", f)
    assert "$328.70" in t2 and "$340.00" in t2 and "$339.63" in t2


def test_generate_blog_notes_flag_contradictions_and_format_prices(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    f = _aapl_like(facts)
    cand = _ai_cand(f, title="TEST Holds Its Trend", sections=[
        {"heading": "Market Structure", "body": "The latest low is 337.6 and the price is in the upper half of today's range."}],
        news={"institutional": None}, private={"A": {"supported": False}, "B": {"supported": False},
                                               "C": {"supported": False}, "selected": "none"})
    monkeypatch.setattr(ch, "ai_blog", lambda ff: cand)
    blog = ch.generate_blog(f, use_ai=True)
    assert "lower half" in (blog.get("note") or "") and "Review before publishing" in blog["note"]
    assert "$337.60" in blog["html"]

def test_pattern_names_are_traps():
    assert ch.pattern_name("UPTHRUST") == "Bull Trap" and ch.pattern_name("UPTHRUST_BUILDING") == "Bull Trap Forming"
    assert ch.pattern_name("SPRING") == "Bear Trap" and ch.pattern_name("SPRING_BUILDING") == "Bear Trap Forming"
    assert ch.pattern_name("BREAKOUT") == "Breakout"
    f = ch.facts_from_chart_data("TEST", {"ok": True, "bars": _chart()["bars"], "hits": [{"type": "UPTHRUST_BUILDING", "level": 339.3}]})
    assert f["pattern_signals"][0]["type"] == "Bull Trap Forming" and "bull trap" in ch._signal_phrase(f).lower()
    out = " ".join(ch.consistency_issues(f, ["The 2-hour view shows an upthrust signal near the high."]))
    assert "bull trap" in out


def test_teaser_failure_note_gives_the_reason(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    blog = ch.generate_blog(facts, use_ai=False)
    too_long = {"text": "x" * 400}
    monkeypatch.setattr(ch, "ai_teasers", lambda f, b: {"x": too_long})
    out = ch.generate_teasers(facts, blog, use_ai=True)
    note = out["_note"]["note"] if "_note" in out else ""
    assert "X AI draft failed checks (" in note and "limit is" in note


def test_key_levels_use_plain_platform_labels_and_hide_methods(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    f = _aapl_like(facts)
    f["pattern_signals"] = [{"type": "Bear Trap Forming", "level": 330.0}, {"type": "Bull Trap", "level": 345.0}]
    f["levels"] = ch.key_levels(f)
    labels = {x["label"] for s in ("above", "below") for x in f["levels"][s]}
    assert "Support" in labels and "Resistance" in labels
    assert not any("flag level" in l or "pivot" in l or "touch" in l for l in labels)
    body = ch.key_levels_body(f)
    assert "Latest price:" in body and body.index("Latest price:") > 0
    prices = [float(p.split(":")[0].replace("$", "").replace(",", "")) for p in body.split("\n\n")
              if p.startswith("$")]
    assert prices == sorted(prices, reverse=True)
    cand = _ai_cand(f, title="TEST Holds Its Trend", sections=[
        {"heading": "Key Levels", "body": "Support at 330 held on 4 touches near the apex of a channel."}],
        news={"institutional": None}, private={"A": {"supported": False}, "B": {"supported": False},
                                               "C": {"supported": False}, "selected": "none"})
    monkeypatch.setattr(ch, "ai_blog", lambda ff: cand)
    blog = ch.generate_blog(f, use_ai=True)
    assert "apex" not in blog["html"].lower() and "Latest price:" in blog["html"]
    assert ch.method_words_in("held on 4 touches near the apex") == ["touches", "apex"]
    assert ch.method_words_in("Support at $330.00") == []


def test_image_ladder_uses_report_labels(facts):
    import inspect
    from backend import content_chart as cc
    src = inspect.getsource(cc.render_share_image)
    assert 'y["label"]' in src and '"R{i' not in src and "Major Resistance" not in src and "Major Support" not in src
    f = _aapl_like(facts)
    f["levels"]["below"] = [{"price": 330.0, "label": "Support"}]
    assert cc_png_ok(f)


def cc_png_ok(f):
    from backend import content_chart as cc
    return cc.render_share_image(f, _bars_for())[:8] == b"\x89PNG\r\n\x1a\n"


def test_instagram_draft_sits_after_x_and_passes_checks(facts):
    assert ch.PLATFORM_ORDER[:3] == ["linkedin", "x", "instagram"]
    blog = ch.generate_blog(facts, use_ai=False)
    t = ch.generate_teasers(facts, blog, use_ai=False)["instagram"]
    assert t["ok"], t["issues"]
    assert "link in bio" in t["text"] and "http" not in t["text"] and t["limit"] == 2200
    assert "4:5" in t["image_spec"]
    bad = ch.validate_teaser("instagram", {"text": "See https://example.com now"}, facts)
    assert any("Link is in the main text" in x for x in bad)


def test_anthropic_400_shows_the_api_message(monkeypatch):
    import requests
    from backend import content_hub as ch

    class R:
        status_code = 400
        headers = {}
        def raise_for_status(self): raise requests.HTTPError("400 Client Error: Bad Request for url: x", response=self)
        def json(self): return {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_HUB_PROVIDER", raising=False)
    with pytest.raises(requests.HTTPError) as e:
        ch._ai_json("s", "u")
    assert "credit balance is too low" in str(e.value) and str(e.value).startswith("400 from Anthropic")
