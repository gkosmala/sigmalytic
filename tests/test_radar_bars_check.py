"""Read-only radar bars vs fresh bars diagnostic."""
import os
import sys

from backend import radar_bars_check as rbc

ROOT = os.path.dirname(os.path.dirname(__file__))


def _b(day, c):
    return {"t": f"{day}T04:00:00Z", "o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": 1000}


def _days(n, start=1):
    return [f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(start, start + n)]


def test_identical_bars_have_no_differences_and_same_state():
    bars = [_b(d, 100 + (i % 5)) for i, d in enumerate(_days(60))]
    r = rbc.compare_symbol("AAA", bars, list(bars), {"status": "No setup"})
    assert r["different_closes"] == 0 and r["days_only_in_radar"] == [] and r["days_only_in_fresh"] == []
    assert r["state_on_radar_bars"] == r["state_on_fresh_bars"]


def test_missing_days_and_changed_close_are_reported():
    fresh = [_b(d, 100 + (i % 5)) for i, d in enumerate(_days(60))]
    radar = [dict(b) for b in fresh[:-3]]          # radar is three days behind
    radar[10] = _b(_days(60)[10], 120.0)           # and one close differs
    r = rbc.compare_symbol("BBB", radar, fresh, None)
    assert len(r["days_only_in_fresh"]) == 3 and r["different_closes"] == 1
    assert r["first_different_close"]["radar"] == 120.0
    assert r["radar_bars"]["bars"] == 57 and r["fresh_bars"]["bars"] == 60


def test_run_check_uses_supplied_bars_and_never_raises_on_empty():
    fresh = {"AAA": [_b(d, 100) for d in _days(40)]}
    out = rbc.run_check(["aaa", "zzz"], {"AAA": fresh["AAA"]}, {}, lambda syms, **kw: fresh)
    assert [r["symbol"] for r in out["rows"]] == ["AAA", "ZZZ"]
    assert out["rows"][1]["radar_bars"]["bars"] == 0


def test_view_renders_rows():
    sys.path.insert(0, os.path.join(ROOT, "frontend"))
    import radar_bars_check_view as v
    bars = [_b(d, 100) for d in _days(40)]
    payload = {"rows": [rbc.compare_symbol("AAA", bars, bars, {"status": "Armed", "status_direction": "long"})],
               "radar_cache_symbols": 1, "note": "n"}
    def text(n):
        if n is None: return ""
        if isinstance(n, (str, int, float)): return str(n)
        if isinstance(n, (list, tuple)): return " ".join(text(x) for x in n)
        return text(getattr(n, "children", None))
    out = text(v.render_radar_bars_check(payload))
    assert "AAA" in out and "long/Armed" in out and "1 symbols compared" in out
