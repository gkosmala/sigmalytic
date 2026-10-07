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
    assert "AAA" in out and "1 symbols compared" in out and "last 252" in out


def test_state_on_last_252_uses_only_the_last_252_bars():
    seen = []
    orig = rbc._state
    rbc._state = lambda bars: seen.append(len(bars)) or "x"
    try:
        fresh = [_b(f"2025-01-{(i % 28) + 1:02d}", 100) for i in range(300)]
        r = rbc.compare_symbol("AAA", [], fresh, None)
    finally:
        rbc._state = orig
    assert r["state_on_fresh_last_252"] == "x" and 252 in seen and 300 in seen


def _flat(n):
    return [_b(f"2025-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", 100 + (i % 7)) for i in range(n)]


def test_bars_used_records_count_window_and_last_ten_closes():
    from backend import radar_service as rs
    done = _flat(40)
    u = rs._bars_used(done)
    assert u["count"] == 40 and u["first"] == done[0]["t"][:10] and u["last"] == done[-1]["t"][:10]
    assert len(u["tail"]) == 10 and u["tail"][-1][0] == u["last"]


def test_used_comparison_same_and_different():
    from backend import radar_service as rs
    fresh = _flat(300)
    done = rbc.wss.drop_incomplete(rbc.wss._normalize(fresh), "1Day")[-252:]
    used = rs._bars_used(done)
    same = rbc._used_comparison(used, fresh)
    assert same["same_window"] is True and same["tail_differences"] == []
    stale = rs._bars_used(done[:-3])                      # worker three bars behind
    d = rbc._used_comparison(stale, fresh)
    assert d["same_window"] is False and len(d["tail_differences"]) >= 3
    assert rbc._used_comparison(None, fresh)["same_window"] is None


def test_state_with_radar_tail_swaps_the_workers_last_bars_in():
    from backend import radar_service as rs
    fresh = _flat(300)
    done = rbc.wss.drop_incomplete(rbc.wss._normalize(fresh), "1Day")[-252:]
    wrong = [dict(b) for b in done]
    wrong[-1]["c"] = 123.45                                  # the worker's last close differs
    used = rs._bars_used(wrong)
    swapped = rbc._with_radar_tail(fresh, used)
    assert swapped[-1]["c"] == 123.45 and swapped[-2]["c"] == done[-2]["c"] and len(swapped) == 252
    assert rbc._with_radar_tail(fresh, {"tail": [["2025-01-01", 1.0]]}) is None       # old two-field shape


def test_run_check_reports_redis_copy_and_supabase_rows():
    class R:
        def ttl(self, k): return 3600
        def strlen(self, k): return 123
    fresh = {"AAA": _flat(40)}
    out = rbc.run_check(["AAA"], {}, {}, lambda syms, **kw: fresh, redis_client=R(),
                        sb_fetch=lambda syms: {"AAA": [{"date": "2026-10-06", "close": 1.0, "updated_at": "x"}]})
    assert out["redis_copy"]["present"] and out["redis_copy"]["age_hours"] == 23.0
    assert out["rows"][0]["supabase_rows"][0]["date"] == "2026-10-06"
