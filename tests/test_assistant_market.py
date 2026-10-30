"""Alpaca lookups for the AI Sigmalytic Assistant. Alpaca is faked; no network."""
import json
import math
import random

import pytest

from backend import assistant as a
from backend import assistant_market as m
from backend.indicators import rsi_series, rsi_wilder


def _bars(n, seed=1, drift=0.0, start=100.0):
    rng = random.Random(seed)
    out, p = [], start
    for i in range(n):
        o = p
        p = max(1.0, p * (1 + rng.gauss(drift, 0.02)))
        out.append({"t": f"2016-01-01T05:00:00Z" if i == 0 else f"20{16 + i // 252}-{(i // 21) % 12 + 1:02d}-"
                                                                  f"{i % 21 + 1:02d}T05:00:00Z",
                    "o": o, "h": max(o, p) * 1.01, "l": min(o, p) * 0.99, "c": p, "v": 1000 + i})
    return out


@pytest.fixture(autouse=True)
def fake_alpaca(monkeypatch):
    store = {"AAPL": _bars(2600, 1), "NVDA": _bars(2600, 2, 0.0008), "TINY": _bars(30, 3)}
    calls = []

    def load(symbols, timeframe, bars):
        calls.append((list(symbols), timeframe, bars))
        return {s: store.get(s, [])[-bars:] for s in symbols}
    monkeypatch.setattr(m, "load_bars", load)
    return calls


def test_price_history_lists_bars_and_summary(fake_alpaca):
    out = m.tool_get_price_history("aapl", bars=60)
    assert out["ok"] and out["bars"] == 60 and len(out["rows"]) == 60 and out["rows"][0][0] == out["first"]
    assert out["rows"][-1][4] == round(_bars(2600, 1)[-1]["c"], 2)
    big = m.tool_get_price_history("AAPL", bars=2000)
    assert big["bars"] == 2000 and len(big["rows"]) == m.MAX_HISTORY_ROWS and big["rows_note"]
    with pytest.raises(ValueError):
        m.tool_get_price_history("AAPL", timeframe="1Min")
    assert m.tool_get_price_history("NOPE")["ok"] is False


def test_indicators_any_rsi_period(fake_alpaca):
    out = m.tool_get_indicators(["AAPL", "NVDA", "TINY", "ZZZZ"], rsi_periods=[7, 14, 21])
    rows = {r["symbol"]: r for r in out["rows"]}
    closes = [b["c"] for b in _bars(2600, 1)][-(fake_alpaca[-1][2]):]
    assert rows["AAPL"]["rsi14"] == rsi_wilder(closes, 14) and "rsi7" in rows["AAPL"] and "sma200" in rows["NVDA"]
    assert set(out["no_data"]) == {"ZZZZ"}       # TINY has 30 bars: enough for RSI(21)
    assert m.tool_get_indicators([f"S{i}" for i in range(21)])["ok"] is False


def test_rsi_exit_test_uses_out_of_sample(fake_alpaca):
    out = m.tool_test_rsi_exit(["AAPL", "NVDA", "TINY"], periods=[5, 14, 28], threshold=40, horizon=20)
    assert out["ok"] and out["no_data"] == ["TINY"] and out["periods"] == [5, 14, 28]
    r = out["results"][0]
    assert r["best_period_in_sample"] in (5, 14, 28) and r["rsi14_out_of_sample"]["events"] >= 1
    best = r["best_period_in_sample"]
    assert r["best_in_sample"] == r["by_period"][str(best)]["in_sample"]
    assert r["best_out_of_sample"] == r["by_period"][str(best)]["out_of_sample"]
    others = [r["by_period"][str(p)]["in_sample"]["avg_fwd_return_pct"] for p in (5, 14, 28)
              if r["by_period"][str(p)]["in_sample"]["events"] >= 5]
    assert r["best_in_sample"]["avg_fwd_return_pct"] == min(others)       # chosen on in-sample only
    assert m.tool_test_rsi_exit([f"S{i}" for i in range(11)])["ok"] is False


def test_period_stats_counts_crossings_and_forward_returns():
    closes = [100, 100, 100, 90, 95, 99]
    rsi = [None, 50, 45, 35, 38, 42]
    st = m._period_stats(closes, rsi, 40, 2, 0, len(closes))
    assert st == {"events": 1, "avg_fwd_return_pct": 10.0, "share_followed_by_decline_pct": 0.0}


def test_rsi_series_matches_single_value():
    c = [b["c"] for b in _bars(400, 9)]
    for p in (2, 7, 14, 28):
        assert rsi_series(c, p)[-1] == rsi_wilder(c, p)


def test_assistant_can_answer_from_alpaca_and_pass_the_number_check(monkeypatch):
    monkeypatch.setattr(a, "_redis", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    a._LOCAL_SPEND.clear()
    ind = m.tool_get_indicators(["AAPL"], rsi_periods=[7])
    rsi7 = ind["rows"][0]["rsi7"]
    turns = [{"text": "", "calls": [{"id": "c1", "name": "get_indicators", "input": {"symbols": ["AAPL"],
                                                                                     "rsi_periods": [7]},
                                     "input_error": None}],
              "in": 100, "out": 10, "reasoning": 0, "assistant_message": {"role": "assistant", "content": []}},
             {"text": f"AAPL's daily RSI(7) from Alpaca bars is {rsi7}.", "calls": [], "in": 100, "out": 10,
              "reasoning": 0, "assistant_message": {}}]
    monkeypatch.setattr(a, "_call_model", lambda p, msgs, mo, force_answer=False: turns.pop(0))
    out = a.ask("What is AAPL's 7-day RSI?")
    assert out["ok"], out
    assert out["lookups"][0].startswith("get_indicators(")


def test_tools_are_registered_and_described():
    names = [t["function"]["name"] for t in a.TOOLS]
    for n in ("get_price_history", "get_indicators", "test_rsi_exit"):
        assert n in names and n in a.TOOL_FUNCS
    assert "never say Alpaca cannot be reached" in a.build_system_prompt()
