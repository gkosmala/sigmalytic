"""Admin report: direction-aware Weis signal handling (score strength is the same for Spring and Upthrust)."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from backend.weis_direction import signal_direction, signal_label
from backend.snapshot_service import _detect_anomalies, _slim, _top_by_score


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


def test_bullish_signal_marked_avoid_is_flagged():
    flags = _detect_anomalies(_many([_row("XYZ", "SPRING", 100, "Avoid")]))
    hit = [f for f in flags if f["symbol"] == "XYZ"]
    assert len(hit) == 1 and hit[0]["type"] == "SCORE_STATUS_MISMATCH" and "Spring (bullish)" in hit[0]["message"]


def test_unknown_signal_marked_avoid_is_not_flagged():
    assert [f for f in _detect_anomalies(_many([_row("Q", None, 100, "Avoid")])) if f["symbol"] == "Q"] == []


def test_slim_carries_signal_fields():
    d = _slim(_row("A", "UPTHRUST"))
    assert d["signal_label"] == "Upthrust (bearish)" and d["signal_direction"] == "BEAR" and d["weis_signal"] == "UPTHRUST"


def test_top_scores_break_ties_by_relative_volume_not_alphabet():
    rows = [_row(c, "SPRING", 100, rel_volume=rv) for c, rv in (("AAA", 0.5), ("BBB", 3.0), ("CCC", 1.5), ("DDD", 2.0))]
    rows += [_row(f"Z{i}", "NONE", 40) for i in range(12)]
    assert [r["symbol"] for r in _top_by_score(rows)[:4]] == ["BBB", "DDD", "CCC", "AAA"]
    assert len(_top_by_score(rows)) == 10
    assert _top_by_score([_row("N", score=None, rel_volume=None), _row("M", score=5)])[0]["symbol"] == "M"
