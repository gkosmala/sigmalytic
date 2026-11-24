"""Wyckoff structure (2026-11-24): when too few swings are confirmed, a climax and its
automatic rally/reaction set the range for every caller (panel, radar, Trade Finder,
backtests). Stocks with confirmed swings are unchanged."""
import pandas as pd
from backend.research_engine.wyckoff_verdict_engine import (
    WyckoffVerdictEngine, run_wyckoff_verdict, calculate_wyckoff_accumulation_score)


def _decline_then_selling_climax():
    bars, price = [], 220.0
    for _ in range(80):
        price -= 1.0
        bars.append({"open": price + 0.5, "high": price + 1.0, "low": price - 1.0, "close": price, "volume": 1_000_000})
    bars.append({"open": price, "high": price, "low": price - 15, "close": price - 14, "volume": 3_000_000})
    low = price - 15
    bars.append({"open": low + 20, "high": low + 45, "low": low + 18, "close": low + 40, "volume": 3_500_000})
    return bars, low, low + 45


def _rally_then_buying_climax():
    bars, price = [], 100.0
    for _ in range(80):
        price += 1.0
        bars.append({"open": price - 0.5, "high": price + 1.0, "low": price - 1.0, "close": price, "volume": 1_000_000})
    top = price + 15
    bars.append({"open": price, "high": top, "low": price, "close": price + 14, "volume": 3_000_000})
    bars.append({"open": top - 20, "high": top - 18, "low": top - 40, "close": top - 35, "volume": 3_500_000})
    return bars, top - 40, top


def test_selling_climax_and_automatic_rally_define_the_range():
    bars, low, high = _decline_then_selling_climax()
    v = run_wyckoff_verdict({"symbol": "SC", "bars": bars})
    assert v["verdict"] != "NO_MEANINGFUL_STRUCTURE"
    assert v["structure_source"] == "selling_climax"
    assert (v["support_level"], v["resistance_level"]) == (low, high)
    assert v["automatic_rally_score"] >= 50
    assert v["trend_context"] != "unknown"


def test_buying_climax_and_automatic_reaction_define_the_range():
    bars, low, high = _rally_then_buying_climax()
    v = run_wyckoff_verdict({"symbol": "BC", "bars": bars})
    assert v["structure_source"] == "buying_climax"
    assert (v["support_level"], v["resistance_level"]) == (low, high)


def test_steady_trend_without_a_climax_still_has_no_range_but_reports_trend():
    bars, price = [], 100.0
    for _ in range(90):
        price += 1.0
        bars.append({"open": price - 0.5, "high": price + 1.0, "low": price - 1.0, "close": price, "volume": 1_000_000})
    v = run_wyckoff_verdict({"symbol": "TR", "bars": bars})
    assert v["verdict"] == "NO_MEANINGFUL_STRUCTURE"
    assert v["structure_source"] == "none"
    assert v["trend_context"] != "unknown"


def test_backtest_scorer_uses_the_same_structure():
    bars, low, high = _decline_then_selling_climax()
    df = pd.DataFrame(bars)
    eng = WyckoffVerdictEngine()
    p = eng._prepare(df)
    assert eng._structure_bounds(p, len(p) - 1)["source"] == "selling_climax"
    assert len(calculate_wyckoff_accumulation_score(df)) == len(p)
