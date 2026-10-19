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
    assert set("MSFT AAPL AMD NVDA MU AMZN GOOGL META ORCL IBM TSLA CSCO DELL".split()) <= set(t)
    assert set("AVGO JPM BRK.B LLY XOM WMT ABBV COST PLTR BAC INTC".split()) <= set(t)
    assert t["WMT"]["ipo_utc"] == "1970-10-01 13:30 UTC" and t["INTC"]["ipo_utc"] == "1971-10-13 13:30 UTC"   # EDT; 1970-71 DST ended in late October
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


def test_square_of_nine_matches_the_source_example():
    # source material: pivot 7002.28, 45 degrees down -> about 6,960.50, 90 down -> 6,918.85, 360 down -> 6,671.56
    lv = {x["label"]: x["price"] for x in ar.sq9_levels(7002.28, "p")}
    assert abs(lv["p down 45 deg"] - 6960.50) < 0.1 and abs(lv["p down 90 deg"] - 6918.85) < 0.1
    assert abs(lv["p down 360 deg"] - 6671.56) < 0.1


def test_natal_lines_match_the_source_for_aapl():
    n = ar.ipo_chart("AAPL")
    assert abs(n["Jupiter"]["lon"] - 187.59) < 0.1 and abs(n["Sun"]["lon"] - 260.74) < 0.1
    mof = ar.mean_lons(n)["Mean of Five"]
    assert abs(mof - 215.91) < 0.1
    lines = ar.planet_lines({"Jupiter": n["Jupiter"]["lon"]}, 190.0, 1.0, 0.1, "natal")
    assert abs(lines[0]["price"] - 187.59) < 0.1


def test_time_counts_match_the_source_example():
    c = ar.time_counts("2026-01-28", "2026-05-01")
    assert c["days"] == 93 and c["nearest_day_number"] == 90 and c["nearest_week_number"] == 13 and c["flag"]


def test_price_unit():
    assert ar.price_unit(6400) == 10 and ar.price_unit(305) == 1 and ar.price_unit(5) == 0.1


def test_confluence_needs_two_families():
    lv = [{"price": 100.0, "family": "sq9", "label": "a"}, {"price": 100.1, "family": "pivot", "label": "b"},
          {"price": 120.0, "family": "sq9", "label": "c"}, {"price": 120.05, "family": "sq9", "label": "d"}]
    z = ar.confluence(lv)
    assert len(z) == 1 and 99.9 < z[0]["price"] < 100.2


def test_report_end_to_end_with_synthetic_bars(monkeypatch):
    monkeypatch.setattr(ar, "fetch_bars", lambda s, y=8: _bars(2100))
    r = ar.report("MSFT", "2026-06-15")
    assert len(r["blocks"]) == 7 and r["pivot_rows"] and r["ref_date"] < "2026-06-15"
    assert "HOURLY TACTICAL PLAN" in r["draft"] and "Not a signal and not investment advice" in r["draft"]
    assert all(b["time_et"] for b in r["blocks"])
    # exact events carry real aspect names and times inside the session
    assert all(e["time"].endswith("ET") for e in r["exact_events"])


def test_report_uses_only_bars_before_the_date(monkeypatch):
    bars = _bars(2100)
    monkeypatch.setattr(ar, "fetch_bars", lambda s, y=8: bars)
    day = bars[1500]["t"][:10]
    r = ar.report("AAPL", day)
    assert r["ref_date"] < day and r["actual"] is not None
    assert all(p["date"] < day for p in r["pivot_rows"])


def test_admin_page_builds_with_astro_section(monkeypatch):
    """Regression: an invalid Dash property once broke the Astro Research controls. The admin builder must produce them."""
    import os
    import sys
    monkeypatch.setenv("SIGMALYTIC_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASTRO_RESEARCH_EMAILS", "admin@example.com")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
    import app as dash_app

    def ids(x, out):
        if getattr(x, "id", None):
            out.append(x.id)
        ch = getattr(x, "children", None)
        for c in (ch if isinstance(ch, list) else [ch]):
            if c is not None and not isinstance(c, (str, int, float)):
                ids(c, out)
        return out

    found = ids(dash_app.build_astro_tab({"email": "admin@example.com"}), [])
    assert {"astro-symbol", "astro-start", "astro-since", "astro-run-btn", "astro-bt-btn"} <= set(found)
    assert dash_app.is_astro_owner({"email": "admin@example.com"})
    assert not dash_app.is_astro_owner({"email": "other@example.com"})
    assert "restricted" in dash_app.build_astro_tab({"email": "other@example.com"}).children


def test_owner_gate(monkeypatch):
    monkeypatch.delenv("ASTRO_RESEARCH_EMAILS", raising=False)
    assert ar.is_owner("Greg.Kosmala@gmail.com") and not ar.is_owner("someone@else.com") and not ar.is_owner("")
    monkeypatch.setenv("ASTRO_RESEARCH_EMAILS", "a@b.com, c@d.com")
    assert ar.is_owner("c@d.com") and not ar.is_owner("greg.kosmala@gmail.com")


def test_mdb_is_listed_with_user_confirmed_values():
    from backend import astro_research as ar
    r = ar.BY_SYMBOL["MDB"]
    assert r["ipo_date"] == "2017-10-19" and r["status"] == "minute-only" and r["elev_m"] == 16
    assert abs(r["lat"] - 40.75) < 1e-9 and abs(r["lon"] + 73.98333333) < 1e-6
    assert r["first_trade_et"] == "10:53" and "confirmed by the user" in r["time_note"]
    assert ar.ipo_moment_utc(r).strftime("%Y-%m-%d %H:%M") == "2017-10-19 14:53"   # EDT = UTC-4


def test_hpe_is_listed_with_user_confirmed_values():
    from backend import astro_research as ar
    r = ar.BY_SYMBOL["HPE"]
    assert r["ipo_date"] == "2015-10-19" and r["status"] == "minute-only" and r["elev_m"] == 85
    assert abs(r["lat"] - 37.4) < 1e-9 and abs(r["lon"] + 122.13333333) < 1e-6
    assert r["first_trade_et"] == "09:30" and "confirmed by the user" in r["time_note"]
    assert ar.ipo_moment_utc(r).strftime("%Y-%m-%d %H:%M") == "2015-10-19 13:30"   # EDT = UTC-4


def test_wday_is_listed_with_user_confirmed_values():
    from backend import astro_research as ar
    r = ar.BY_SYMBOL["WDAY"]
    assert r["ipo_date"] == "2012-10-12" and r["status"] == "minute-only" and r["elev_m"] == 104
    assert abs(r["lat"] - 37.683333333) < 1e-6 and abs(r["lon"] + 121.916666667) < 1e-6
    assert r["first_trade_et"] == "10:17" and "confirmed by the user" in r["time_note"]
    assert ar.ipo_moment_utc(r).strftime("%Y-%m-%d %H:%M") == "2012-10-12 14:17"   # EDT = UTC-4


def test_astro_dropdown_lists_every_backend_symbol(monkeypatch):
    """The symbol dropdown in the Astro tab is a hard-coded list; it must match the backend table."""
    import sys, os
    monkeypatch.setenv("SIGMALYTIC_ADMIN_EMAILS", "admin@example.com")
    monkeypatch.setenv("ASTRO_RESEARCH_EMAILS", "admin@example.com")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
    import app as dash_app
    from backend import astro_research as ar
    tab = str(dash_app.build_astro_tab({"email": "admin@example.com"}))
    for sym in ar.BY_SYMBOL:
        assert f"'value': '{sym}'" in tab, sym


def test_closest_cross_family_gap_ignores_same_method_pairs():
    lv = [{"price": 100.0, "family": "a", "label": "A1"}, {"price": 100.05, "family": "a", "label": "A2"},
          {"price": 101.0, "family": "b", "label": "B1"}]
    g = ar.closest_cross_family_gap(lv)
    assert g["a"].startswith("A2") and g["b"].startswith("B1") and abs(g["gap_pct"] - 0.945) < 0.01
    assert ar.closest_cross_family_gap([{"price": 1.0, "family": "a", "label": "x"}]) is None


def test_empty_confluence_is_explained_and_nearest_levels_are_shown(monkeypatch):
    monkeypatch.setattr(ar, "fetch_bars", lambda s, y=8: _bars(2100))
    monkeypatch.setattr(ar, "confluence", lambda levels, tol_pct=0.2: [])
    r = ar.report("MDB", "2026-06-15")
    assert r["top_zones"] == [] and r["confluence_diag"]["tolerance_pct"] == 0.2
    t = r["draft"]
    assert "No confluence found" in t and "Nearest single-method levels (NOT confluence)" in t
    assert all("near_above" in b and "near_below" in b for b in r["blocks"])
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
    import astro_research_ui as ui
    assert "No confluence found" in ui._no_conf(r)
    assert ui._zones_cell(r["blocks"][0], "above", "near_above").startswith("nearest (not confluence)") or r["blocks"][0]["near_above"] == []


def test_octagon_levels_known_mdb_case():
    from backend import astro_research as ar
    lv = ar.octagon_levels({"Mean of Five": 226.16, "Cycle of Eight": 217.17}, 337.57, 1, 0.12, "Natal")
    got = {(x["body"], x["offset"]): round(x["price"], 2) for x in lv}
    assert got[("Mean of Five", 90)] == 316.16 and got[("Mean of Five", 135)] == 361.16
    assert got[("Cycle of Eight", 90)] == 307.17 and got[("Cycle of Eight", 135)] == 352.17
    assert all(abs(x["price"] / 337.57 - 1) <= 0.12 for x in lv)


def test_mean_bands_pair_nearest_levels_and_dedupe():
    from backend import astro_research as ar
    lv = ar.octagon_levels({"Mean of Five": 226.16, "Cycle of Eight": 217.17}, 337.57, 1, 0.12, "Natal")
    bands = ar.mean_bands(lv, [{"price": 360.0, "label": "Other"}])
    assert len({tuple(b["key"]) for b in bands}) == len(bands)
    b = next(b for b in bands if b["low"] == 352.17)
    assert b["high"] == 361.16 and b["width_pct"] == 2.55 and any("Other" in s for s in b["inside"])
    assert [x["width_pct"] for x in bands] == sorted(x["width_pct"] for x in bands)


def test_level_test_classifies_touches_and_runs(monkeypatch):
    from backend import astro_research as ar, astro_level_test as lt
    bar = {"o": 100, "h": 106, "l": 99, "c": 105}
    assert lt.classify({"kind": "zone", "lo": 103, "hi": 103}, 100, bar, 110)["result"] == "through"
    assert lt.classify({"kind": "zone", "lo": 107, "hi": 107}, 100, bar, 110) is None
    assert lt.classify({"kind": "zone", "lo": 105.5, "hi": 105.5}, 100, bar, 110)["result"] == "reversal"
    assert lt.classify({"kind": "band", "lo": 103, "hi": 108}, 100, bar, 99)["result"] == "stalled"
    dn = {"o": 100, "h": 101, "l": 94, "c": 95}
    r = lt.classify({"kind": "zone", "lo": 97, "hi": 97}, 100, dn, 90)
    assert r["result"] == "through" and round(r["follow"], 2) == 5.26
    bars = _bars(2100)
    res = lt.level_test(bars, lambda d: ar.report("MDB", d, bars=bars), max_days=15, draws=25, kinds=("band",))
    assert res["days_tested"] == 15 and len(res["metrics"]) == 4 and res["kinds"] == ["band"]
