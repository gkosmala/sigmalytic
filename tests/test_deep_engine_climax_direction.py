"""The deep engine must read climax signals the same way the rest of the app does:
Buying Climax = distribution (bearish), Selling Climax = accumulation (bullish)."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

import pytest

from backend import doctrine_deep_engine as dde
from backend import weis_wave
from backend.weis_direction import BEARISH, BULLISH, signal_direction


def _bars(n=60):
    out, px = [], 100.0
    for i in range(n):
        px *= 1 + (0.004 if i % 2 else -0.004)
        out.append({"o": px, "h": px * 1.005, "l": px * 0.995, "c": px, "v": 1_000_000})
    return out


def _run(monkeypatch, signal):
    monkeypatch.setattr(
        weis_wave, "score_weis_wave_radar",
        lambda symbol, bars, price: {"weis_signal": signal, "weis_score": 12,
                                     "weis_macro_bias": 0},
    )
    return dde.compute_doctrine_deep_score("X", _bars(), 100.0)


def test_buying_climax_is_distribution(monkeypatch):
    r = _run(monkeypatch, "CLIMAX_BUY")
    assert r["new_regime"] == "DISTRIBUTION" and r["new_status"] == "Avoid"


def test_selling_climax_is_accumulation(monkeypatch):
    r = _run(monkeypatch, "CLIMAX_SELL")
    assert r["new_regime"] == "ACCUMULATION" and r["new_status"] == "Building"


def test_spring_and_upthrust_unchanged(monkeypatch):
    assert _run(monkeypatch, "SPRING")["new_regime"] == "ACCUMULATION"
    assert _run(monkeypatch, "UPTHRUST")["new_regime"] == "DISTRIBUTION"


@pytest.mark.parametrize("signal", ["SPRING", "CLIMAX_SELL", "UPTHRUST", "CLIMAX_BUY"])
def test_regime_matches_shared_direction_map(monkeypatch, signal):
    regime = _run(monkeypatch, signal)["new_regime"]
    expected = "ACCUMULATION" if signal_direction(signal) == BULLISH else "DISTRIBUTION"
    assert signal_direction(signal) in (BULLISH, BEARISH)
    assert regime == expected


def test_bullish_climax_scores_higher_than_bearish(monkeypatch):
    sell = _run(monkeypatch, "CLIMAX_SELL")["new_composite_score"]
    buy = _run(monkeypatch, "CLIMAX_BUY")["new_composite_score"]
    assert sell > buy
