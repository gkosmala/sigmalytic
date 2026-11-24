"""PnF fixes (2026-11-24, NVDA case): the still-forming column is reported as current, the
reversal bar's volume belongs to the new column, and a one-column trend leg is not counted."""
from backend.research_engine.point_in_time_pnf_generator import PointInTimePnFGenerator
from backend.research_engine.pnf_weis_engine import PnFWeisEngine


def _bars(closes, vols=None):
    vols = vols or [1_000_000] * len(closes)
    return [{"c": c, "v": v, "t": f"2026-01-{i + 1:02d}"} for i, (c, v) in enumerate(zip(closes, vols))]


# 30 quiet days near 200, a slide to 125, then one big reversal day to 165 on huge volume
CLOSES = [200 + (i % 3) for i in range(30)] + [190, 180, 170, 160, 150, 140, 130, 125, 165]
VOLS = [1_000_000] * (len(CLOSES) - 1) + [9_000_000]


def test_completed_columns_unchanged_by_default():
    cols = PointInTimePnFGenerator().generate(_bars(CLOSES, VOLS))
    assert cols and not any(c.in_progress for c in cols)
    assert cols[-1].column_type == "O" and cols[-1].low == 125


def test_open_column_is_current_and_owns_the_reversal_volume():
    gen = PointInTimePnFGenerator()
    cols = gen.generate(_bars(CLOSES, VOLS), include_open=True)
    cur, prev = cols[-1], cols[-2]
    assert cur.in_progress and cur.column_type == "X" and cur.high == 165
    assert cur.volume == 9_000_000 and cur.bar_volumes == [9_000_000]
    assert 9_000_000 not in prev.bar_volumes            # not attributed to the finished down column


def test_engine_reads_up_and_no_count_on_a_trend_leg():
    e = PnFWeisEngine()
    cols = e.build_columns(_bars(CLOSES, VOLS), include_open=True)
    assert e.current_column_reading(cols)["direction"] == "UP"
    cg = e.count_guide_projection(cols)
    assert cg["available"] is False and cg["reason"] == "no_base"
