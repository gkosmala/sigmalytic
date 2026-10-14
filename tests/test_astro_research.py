from datetime import datetime, timedelta, timezone

from backend import astro_research as ar


def _bars(n=1800, seed=1):
    import random
    random.seed(seed)
    out, p, d = [], 100.0, datetime(2019, 1, 2)
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() >= 5:
            continue
        o = p
        p = p * (1 + random.gauss(0.0004, 0.015))
        out.append({"t": d.strftime("%Y-%m-%dT05:00:00Z"), "o": o, "h": max(o, p) * 1.005, "l": min(o, p) * 0.995, "c": p})
    return out


def test_table_has_all_symbols_and_utc_moments():
    t = {r["symbol"]: r for r in ar.table()}
    assert set(t) == set("MSFT AAPL AMD NVDA MU AMZN GOOGL META ORCL IBM TSLA CSCO DELL".split())
    assert t["MSFT"]["ipo_utc"] == "1986-03-13 14:30 UTC"      # EST
    assert t["TSLA"]["ipo_utc"] == "2010-06-29 13:30 UTC"      # EDT
    assert all(r["elev_status"].startswith("user-supplied") for r in t.values())


def test_pivots_follow_documented_rules():
    bars = _bars()
    p = {x["name"]: x for x in ar.compute_pivots(bars)["pivots"]}
    assert p["Absolute Cycle Low"]["price"] < p["Major Higher Low"]["price"] < p["Intermediate High"]["price"]
    assert p["Absolute Cycle High"]["price"] >= max(x["price"] for x in p.values())
    assert p["Absolute Cycle Low"]["date"] < p["Absolute Cycle High"]["date"]


def test_pivot_check_reports_differences():
    fake = {"pivots": [{"name": "Absolute Cycle Low", "price": 140.0, "date": "2020-03-23"}]}
    rows = ar.check_pivots("MSFT", fake)
    low = next(r for r in rows if r["name"] == "Absolute Cycle Low")
    assert low["diff_pct"] == round((140 / 137.35 - 1) * 100, 2) and low["date_match"] is True
    assert ar.check_pivots("AAPL", fake) == []


def test_backtest_is_deterministic_and_complete():
    bars = _bars()
    ev = {"kind": "moon_phase", "phase": "full"}
    a, b = ar.backtest(bars, ev, "MSFT"), ar.backtest(bars, ev, "MSFT")
    assert a == b and [x["horizon"] for x in a["results"]] == [1, 5, 10, 20]
    assert 70 <= a["events_found"] <= 100          # about one full moon per 29.5 days over ~7 years
    assert all(0 < x["p_value"] <= 1 for x in a["results"] if x["n"])


def test_event_kinds_run():
    bars = _bars()
    assert ar.backtest(bars, {"kind": "station", "body": "Mercury", "to": "retrograde"}, "MSFT")["events_found"] >= 15
    assert "results" in ar.backtest(bars, {"kind": "ipo_aspect", "body": "Mars", "natal": "Sun", "aspect": "conjunction", "orb": 1.0}, "AAPL")


def test_windows_and_hourly():
    start = datetime(2026, 10, 14, 13, tzinfo=timezone.utc)
    w = ar.transit_windows("MSFT", start, 48)
    assert w and all(x["tightest_orb"] <= 1.0 for x in w)
    h = ar.hourly_table("MSFT", start, 6)
    assert len(h) == 6 and "Moon" in h[0]["bodies"]
    d = ar.plan_draft("MSFT", start, 48, w, ar.compute_pivots(_bars()))
    assert "Not a signal and not investment advice" in d
