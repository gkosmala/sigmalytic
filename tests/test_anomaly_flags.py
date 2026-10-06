"""Anomaly flags must only use fields the radar still saves."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from backend.snapshot_service import _detect_anomalies


def _row(**kw):
    base = {"symbol": "X", "composite_score": 50, "status": "Watching", "change_pct": 0.0, "rel_volume": 1.0}
    base.update(kw)
    return base


def _many(extra=None):
    rows = [_row(symbol=f"S{i}", composite_score=60) for i in range(12)]
    return rows + (extra or [])


def test_big_mover_without_stored_confluence_is_not_flagged():
    rows = _many([_row(symbol="CEG", change_pct=12.1)])  # no confluence key, as in real radar output
    assert [f for f in _detect_anomalies(rows) if f["symbol"] == "CEG"] == []


def test_armed_without_stored_expansion_is_not_flagged():
    rows = _many([_row(symbol="HOLX", status="Armed", composite_score=80)])
    assert [f for f in _detect_anomalies(rows) if f["symbol"] == "HOLX"] == []


def test_real_checks_still_fire():
    rows = _many([_row(symbol="ABNB", composite_score=100, status="Avoid", weis_signal="SPRING"),
                  _row(symbol="HOLX", rel_volume=12.3)])
    kinds = {(f["symbol"], f["type"]) for f in _detect_anomalies(rows)}
    assert ("ABNB", "SCORE_STATUS_MISMATCH") in kinds and ("HOLX", "VOLUME_SPIKE") in kinds
    assert _detect_anomalies([_row()])[0]["type"] == "LOW_DATA_COUNT"


def test_missing_or_none_rel_volume_does_not_crash():
    _detect_anomalies(_many([_row(symbol="N", rel_volume=None)]))
