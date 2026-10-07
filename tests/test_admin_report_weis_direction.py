"""Admin report: direction-aware Weis signal handling (score strength is the same for Spring and Upthrust)."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from backend.weis_direction import signal_direction, signal_label
from backend.snapshot_service import _detect_anomalies, _slim, _top_by_weis_state


def _row(sym, signal="NONE", score=100, status="Watching", rel_volume=1.0, chg=0.0):
    return {"symbol": sym, "composite_score": score, "status": status, "weis_signal": signal,
            "rel_volume": rel_volume, "change_pct": chg, "price": 10.0}


def _many(extra):
    return [_row(f"S{i}", score=60) for i in range(12)] + extra


def test_direction_map():
    assert signal_direction("SPRING") == "BULL" and signal_direction("spring") == "BULL"
    assert signal_direction("UPTHRUST") == "BEAR"
    assert signal_direction("CLIMAX_BUY") == "BEAR" and signal_direction("CLIMAX_SELL") == "BULL"
    assert signal_direction("NO_DEMAND") == "BEAR" and signal_direction("NO_SUPPLY") == "BULL"
    assert signal_direction("3BAR_BULLISH") == "BULL" and signal_direction("3BAR_BEARISH") == "BEAR"
    assert signal_direction("NONE") is None and signal_direction(None) is None and signal_direction("???") is None


def test_labels():
    assert signal_label("UPTHRUST") == "Upthrust (bearish)"
    assert signal_label("SPRING") == "Spring (bullish)"
    assert signal_label("NONE") == "-" and signal_label(None) == "-"


def test_bearish_signal_marked_avoid_is_not_flagged():
    flags = _detect_anomalies(_many([_row("ABNB", "UPTHRUST", 100, "Avoid")]))
    assert [f for f in flags if f["symbol"] == "ABNB"] == []


def test_bullish_signal_marked_avoid_is_not_flagged():
    # Avoid is a Weis state (failed or flipped setup), not a filter result, so this is no contradiction.
    flags = _detect_anomalies(_many([_row("XYZ", "SPRING", 100, "Avoid")]))
    assert [f for f in flags if f["symbol"] == "XYZ"] == []


def test_unknown_signal_marked_avoid_is_not_flagged():
    assert [f for f in _detect_anomalies(_many([_row("Q", None, 100, "Avoid")])) if f["symbol"] == "Q"] == []


def test_slim_carries_signal_fields():
    d = _slim(_row("A", "UPTHRUST"))
    assert d["signal_label"] == "Upthrust (bearish)" and d["signal_direction"] == "BEAR" and d["weis_signal"] == "UPTHRUST"


def test_top_list_ranks_weis_state_first_then_strength_then_volume():
    rows = [_row("LOW", "SPRING", 100, "No setup", rel_volume=9.0),
            _row("AV", "SPRING", 100, "Avoid", rel_volume=9.0),
            _row("WA", "SPRING", 80, "Watching", rel_volume=1.0),
            _row("SU", "SPRING", 70, "Setting Up", rel_volume=1.0),
            _row("AR1", "SPRING", 60, "Armed", rel_volume=1.0),
            _row("AR2", "SPRING", 90, "Armed", rel_volume=0.5),
            _row("AR3", "SPRING", 90, "Armed", rel_volume=2.0)]
    rows += [_row(f"Z{i}", "NONE", 40, "No setup") for i in range(12)]
    top = [r["symbol"] for r in _top_by_weis_state(rows)]
    assert top[:7] == ["AR3", "AR2", "AR1", "SU", "WA", "AV", "LOW"]
    assert len(top) == 10
    assert _top_by_weis_state([_row("N", score=None, rel_volume=None, status="Watching"), _row("M", score=5, status="Watching")])[0]["symbol"] == "M"


def test_slim_carries_the_weis_direction():
    r = _row("A", "SPRING", 100, "Armed"); r["status_direction"] = "short"
    assert _slim(r)["status_direction"] == "short"
