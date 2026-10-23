from datetime import date, datetime, timedelta

import pytest

from backend import catalyst_engine as ce

ET = ce.ET


def _trading_days(start: date, n: int):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(dates, moves):
    """Daily bars with a 0.1% drift and the given % moves on chosen dates."""
    bars, p = [], 100.0
    for d in dates:
        p *= 1 + moves.get(d, 0.1) / 100
        bars.append({"t": f"{d}T04:00:00Z", "c": round(p, 6)})
    return bars


def _filing(day: str, hhmm: str, items):
    h, m = map(int, hhmm.split(":"))
    acc = datetime.fromisoformat(day).replace(hour=h, minute=m, tzinfo=ET)
    return {"form": "8-K", "items": items, "accepted": acc, "url": f"https://sec.example/{day}"}


DATES = _trading_days(date(2025, 1, 2), 400)


def test_reaction_day_rules():
    # After the close -> next trading day; before the open -> same day; Saturday -> Monday.
    assert DATES[ce.reaction_index(DATES, datetime(2025, 1, 2, 16, 5, tzinfo=ET))] == "2025-01-03"
    assert DATES[ce.reaction_index(DATES, datetime(2025, 1, 3, 7, 0, tzinfo=ET))] == "2025-01-03"
    assert DATES[ce.reaction_index(DATES, datetime(2025, 1, 4, 12, 0, tzinfo=ET))] == "2025-01-06"
    assert ce.timing_label(datetime(2025, 1, 2, 16, 5, tzinfo=ET)) == "after close"
    assert ce.timing_label(datetime(2025, 1, 2, 7, 0, tzinfo=ET)) == "before open"


def test_earnings_dedupe_drops_second_filing_same_week():
    fs = [_filing("2025-04-22", "16:05", ["2.02", "9.01"]), _filing("2025-04-24", "08:00", ["2.02"]),
          _filing("2025-07-23", "16:05", ["2.02"]), _filing("2025-05-01", "16:00", ["5.07"])]
    ev = ce.earnings_events(sorted(fs, key=lambda f: f["accepted"]))
    assert [e["accepted"].date().isoformat() for e in ev] == ["2025-04-22", "2025-07-23"]


def _scenario():
    i_e1, i_e2, i_e3 = 100, 160, 220          # earnings reaction-day indexes
    i_pre, i_cat = 150, 120                    # pre-announcement and catalyst days in window 2
    moves = {DATES[i_e1]: 6.0, DATES[i_e2]: -9.0, DATES[i_e3]: 4.0,
             DATES[i_pre]: 5.0, DATES[i_cat]: -7.0, DATES[200]: -3.0}
    bars = _bars(DATES, moves)
    bench = _bars(DATES, {})
    filings = [_filing(DATES[i - 1], "16:05", ["2.02", "9.01"]) for i in (i_e1, i_e2, i_e3)]
    filings.append(_filing(DATES[i_cat], "08:00", ["8.01"]))
    filings.sort(key=lambda f: f["accepted"])
    news = {i_pre: [{"headline": "Company Q2 deliveries beat estimates", "symbols": ["X"], "url": "u1"}],
            i_cat: [{"headline": "Company recalls vehicles", "symbols": ["X"], "url": "u2"}]}
    lookup = lambda idxs: {i: news.get(i, []) for i in idxs}
    return bars, bench, filings, lookup, (i_e2, i_pre, i_cat)


def test_analyze_with_keyword_finds_pre_announcement_and_catalyst():
    bars, bench, filings, lookup, (i_e2, i_pre, i_cat) = _scenario()
    out = ce.analyze("X", bars, bench, filings, lookup, keyword="deliveries")
    assert out["summary"]["quarters"] == 2
    q2 = out["rows"][1]                                   # newest first, so index 1 is the earlier window
    assert q2["reaction_date"] == DATES[i_e2]
    assert q2["earn_move"] == pytest.approx(-9.0, abs=1e-6)
    assert q2["earn_abn"] == pytest.approx(-9.1, abs=1e-3)   # minus the benchmark's +0.1%
    assert q2["pre"]["date"] == DATES[i_pre] and q2["pre"]["move"] == pytest.approx(5.0, abs=1e-6)
    assert q2["lead_source"] == "pre-announcement" and q2["status"] == "Reversal"
    assert q2["catalyst"]["date"] == DATES[i_cat] and q2["catalyst"]["explained"]
    assert q2["catalyst"]["filings"][0]["label"] == "Other material event"
    assert q2["timing"] == "after close"


def test_analyze_without_keyword_uses_run_up():
    bars, bench, filings, lookup, _ = _scenario()
    out = ce.analyze("X", bars, bench, filings, lookup)
    newest = out["rows"][0]
    assert newest["pre"] is None and newest["lead_source"] == "run-up"
    # Window 3 contains a -3% day; the catalyst is the biggest market-adjusted move there, with no news -> unexplained.
    assert newest["catalyst"]["date"] == DATES[200] and not newest["catalyst"]["explained"]
    s = out["summary"]
    assert s["reversal_rate"] is not None and 0 <= s["reversal_rate"] <= 100
    assert s["avg_abs_earn"] == pytest.approx(6.5, abs=1e-6)


def test_build_rejects_missing_history(monkeypatch):
    monkeypatch.setattr(ce, "fetch_bars", lambda syms, years: {s: [] for s in syms})
    ce._cache.clear()
    with pytest.raises(ValueError):
        ce.build("ZZZZ", 4, "")


def test_ui_renders_payload():
    import sys, json, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))
    from catalyst_engine_ui import render
    from dash.development.base_component import Component
    bars, bench, filings, lookup, _ = _scenario()
    for kw in ("deliveries", ""):
        out = ce.analyze("X", bars, bench, filings, lookup, keyword=kw)
        out.update(years=4, notes=["n"])
        comp = render(json.loads(json.dumps(out)))      # round-trip through JSON like the real API call
        assert isinstance(comp, Component)
        assert "Reversal rate" in json.dumps(comp.to_plotly_json(), default=lambda o: o.to_plotly_json())
