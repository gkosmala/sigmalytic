"""Shared stair-step trend boxes: radar hits and the chart payload."""
import pandas as pd

from backend import trend_boxes as tb


def _rows(closes, start="2026-06-01"):
    days = pd.bdate_range(start, periods=len(closes))
    return [{"date": d.strftime("%Y-%m-%d"), "open": c, "high": c + 0.3, "low": c - 0.3, "close": c}
            for d, c in zip(days, closes)]


UP = [100.0] * 25 + [101, 101.5, 102, 102.6, 103.2, 103.8, 104.4, 105, 105.6, 106.2]
BOX1 = [105.5, 105.0, 104.8, 105.2, 105.9, 105.4, 105.1]
LEG2 = [106.8, 107.5, 108.2, 108.9, 109.6]


def test_boxes_for_crossing_walks_back_and_lists_boxes():
    rows = _rows(UP + BOX1 + LEG2)
    capped = rows[30]["date"]                                   # detector reports a later, capped date
    out = tb.boxes_for_crossing(rows, {"type": "BREAKOUT", "level": 100.5, "date": capped},
                                date_of=lambda b: str(b["t"]))
    assert out["crossing_date"] == rows[25]["date"]            # true first close beyond 100.5
    assert out["phase"] == "trending" and out["step"] == 2
    assert out["trend_label"].startswith("Trending bullish, step 2")
    box = out["boxes"][0]
    assert box["number"] == 1 and box["high"] == 106.5 and box["low"] == 104.5
    assert box["exit"] == "trend resumed" and box["top_date"] == rows[34]["date"]
    assert box["end_date"] == rows[42]["date"]                  # first close above 106.5


def test_open_box_has_no_exit_and_ends_on_latest_bar():
    rows = _rows(UP + BOX1)
    out = tb.boxes_for_crossing(rows, {"type": "BREAKOUT", "level": 100.5, "date": rows[25]["date"]},
                                date_of=lambda b: str(b["t"]))
    assert out["phase"] == "box" and out["boxes"][-1]["exit"] is None
    assert out["boxes"][-1]["end_date"] == rows[-1]["date"]


def test_radar_hit_gets_trend_fields(monkeypatch):
    from backend import weis_radar_scan as wrs

    class Engine:
        def _prepare(self, df):
            return df
        def _find_well_defined_level(self, df, idx, is_support):
            return 90.0 if is_support else 100.5
        def _score_spring(self, *a, **k):
            return 0
        def _score_upthrust(self, *a, **k):
            return 0
        def detect_breakout(self, df, idx, level):
            return {"level": 100.5, "date": df["date"].iloc[45], "days_back": idx - 45, "pct_beyond": 1.0, "held": True}
        def detect_breakdown(self, *a, **k):
            return None
        def check_building_pattern(self, *a, **k):
            return None

    df = pd.DataFrame(_rows([100.0] * 20 + UP + BOX1 + LEG2))         # 60+ bars; crossing at row 45
    df["volume"] = 1000
    hits = wrs.scan_symbol_for_weis_patterns(Engine(), df)
    h = next(x for x in hits if x["type"] == "BREAKOUT")
    assert h["trend"].startswith("Trending bullish, step 2") and h["pivots"].startswith("Prior box: R 106.50")
    assert h["trend_day"] == len(df) - 45


def test_radar_scan_rows_get_trend_fields():
    from backend.weis_radar_scan import _add_trend_boxes
    rows = _rows([100.0] * 20 + UP + BOX1 + LEG2)
    bars = [{"t": r["date"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"]} for r in rows]
    hits = [{"type": "BREAKOUT", "level": 100.5, "date": bars[50]["t"]}, {"type": "UPTHRUST", "level": 1}]
    _add_trend_boxes(hits, bars)
    assert hits[0]["true_crossing_date"] == bars[45]["t"] and hits[0]["trend"].startswith("Trending bullish, step 2")
    assert "trend" not in hits[1]
