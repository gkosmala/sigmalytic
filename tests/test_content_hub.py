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


def test_ai_blog_with_invented_number_is_rejected(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(ch, "ai_blog", lambda f: {"title": "T", "meta_description": "m", "ai": True,
                                                   "sections": [{"heading": "h", "body": "Price hit $9,999.99 today."}]})
    blog = ch.generate_blog(facts, use_ai=True)
    assert blog["ai"] is False and "rejected" in blog["note"]


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
    pkg = ch.build_package("TEST", use_ai=True, facts=facts)
    assert pkg["ai_used"] is False and any("ANTHROPIC_API_KEY" in n for n in pkg["notes"])
