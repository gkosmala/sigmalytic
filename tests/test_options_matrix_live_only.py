"""The Command Center Options Matrix uses only the live options feed.
No synthetic numbers when the feed is missing or incomplete."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app as fa


def _text(node):
    return json.dumps(node, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))


def _render(monkeypatch, gamma):
    monkeypatch.setattr(fa, "_cc_cached_background_fetch", lambda key, fn, **kw: gamma if key.startswith("cc-gamma") else {})
    live = json.loads(json.dumps(fa._init_live))
    return _text(fa.build_command_tab(live, [], "AAPL", "5m"))


def test_no_feed_shows_dashes_and_no_synthetic(monkeypatch):
    out = _render(monkeypatch, {"status": "NO_DATA", "has_real_data": False, "top_call_walls": [], "top_put_walls": []})
    assert "synthetic" not in out.lower()
    assert "NO LIVE OPTIONS DATA" in out
    assert "Vol Trigger" not in out and "expansion energy" not in out
    assert "dealer sensitivity" not in out
    assert "Net Gamma Exposure" in out and "ATM Implied Vol" in out


def test_live_feed_shows_real_values(monkeypatch):
    out = _render(monkeypatch, {
        "has_real_data": True, "contract_count": 10, "net_gamma_regime": "POSITIVE", "zero_gamma_level": 281.0,
        "top_call_walls": [{"strike": 290, "call_wall_strength": 3}],
        "top_put_walls": [{"strike": 270, "put_wall_strength": 1}],
        "net_gamma_exposure": -2500000.0,
        "touch_probability_inputs": {"available": True, "atm_implied_volatility": 0.2534,
                                     "expiration_date": "2026-10-16", "days_to_expiration": 8},
    })
    assert "$290" in out and "$270" in out and "$281" in out
    assert "75% call-side pressure" in out and "25% put-side pressure" in out
    assert "-2.50M" in out and "25.3%" in out and "2026-10-16" in out


def test_partial_feed_not_filled_in(monkeypatch):
    out = _render(monkeypatch, {"has_real_data": True, "top_call_walls": [], "top_put_walls": [], "contract_count": 4})
    assert "Nothing is estimated" in out
    assert "synthetic" not in out.lower()
