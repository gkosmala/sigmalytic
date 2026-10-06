"""Tests for Broker Behavioural Intelligence grading (backend/broker_intelligence.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import broker_intelligence as bi
from import_history_restore_api import _analyze_trades


def _pair(sym, day, buy, sell, qty=100):
    return [
        {"date": f"2026-03-{day:02d} 10:00:00", "symbol": sym, "side": "BUY", "quantity": qty, "price": buy, "fees": 0},
        {"date": f"2026-03-{day:02d} 14:00:00", "symbol": sym, "side": "SELL", "quantity": qty, "price": sell, "fees": 0},
    ]


def _trades(results):
    out = []
    for i, (buy, sell) in enumerate(results, start=1):
        out += _pair(f"S{i}", i, buy, sell)
    return out


def test_letter_bands():
    assert bi.letter_from_score(95) == "A"
    assert bi.letter_from_score(90) == "A"
    assert bi.letter_from_score(89.9) == "B"
    assert bi.letter_from_score(80) == "B"
    assert bi.letter_from_score(70) == "C"
    assert bi.letter_from_score(60) == "D"
    assert bi.letter_from_score(59.9) == "F"
    assert bi.letter_from_score(None) == "N/A"


def test_too_few_trades_is_not_graded():
    a = _analyze_trades(_trades([(10, 11), (10, 11)]))
    g = bi.grade_behavior(a)
    assert g["graded"] is False
    assert g["overall_grade"] == "N/A"
    assert "at least 5" in g["reason"]


def test_strong_record_grades_well():
    a = _analyze_trades(_trades([(10, 12)] * 8 + [(10, 9.5)] * 2))
    g = bi.grade_behavior(a)
    assert g["graded"] is True
    assert g["overall_grade"] in ("A", "B")
    assert set(g["components"]) == {"execution", "discipline", "timing", "risk_management"}


def test_losing_record_grades_poorly():
    a = _analyze_trades(_trades([(10, 8)] * 8 + [(10, 10.5)] * 2))
    g = bi.grade_behavior(a)
    assert g["graded"] is True
    assert g["overall_grade"] in ("D", "F")
    assert g["components"]["execution"]["grade"] in ("D", "F")


def test_better_record_never_grades_below_worse_record():
    good = bi.grade_behavior(_analyze_trades(_trades([(10, 12)] * 7 + [(10, 9)] * 3)))
    bad = bi.grade_behavior(_analyze_trades(_trades([(10, 12)] * 3 + [(10, 9)] * 7)))
    assert good["overall_score"] > bad["overall_score"]


def test_every_component_explains_itself():
    g = bi.grade_behavior(_analyze_trades(_trades([(10, 12)] * 6 + [(10, 9)] * 4)))
    for comp in g["components"].values():
        assert comp["basis"], "each component must list its evidence"
        assert 0 <= comp["score"] <= 100


def test_weights_sum_to_one():
    assert abs(sum(bi.COMPONENT_WEIGHTS.values()) - 1.0) < 1e-9


def test_merge_drops_overlap_between_statements_only():
    fill = {"date": "2026-03-01", "symbol": "AAA", "side": "BUY", "quantity": 10, "price": 5.0}
    a = [dict(fill), dict(fill)]          # two genuine identical fills in one statement
    b = [dict(fill), dict(fill)]          # the overlapping export repeats them
    assert len(bi.merge_executions([a, b])) == 2
    c = [dict(fill), dict(fill), dict(fill)]
    assert len(bi.merge_executions([a, c])) == 3


def test_merge_keeps_distinct_fills():
    a = [{"date": "d1", "symbol": "A", "side": "BUY", "quantity": 1, "price": 1}]
    b = [{"date": "d2", "symbol": "A", "side": "BUY", "quantity": 1, "price": 1}]
    assert len(bi.merge_executions([a, b])) == 2
