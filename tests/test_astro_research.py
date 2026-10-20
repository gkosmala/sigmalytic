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
    # owner-supplied table: under $5 x100, $5-$500 1:1, over $500-$3,000 /10, over $3,000 /100
    assert ar.price_unit(6400) == 100 and ar.price_unit(3000) == 10 and ar.price_unit(800) == 10
    assert ar.price_unit(500) == 1 and ar.price_unit(305) == 1 and ar.price_unit(5.01) == 1 and ar.price_unit(5) == 0.01 and ar.price_unit(4.99) == 0.01


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
    res = lt.level_test(bars, lambda d: ar.report("MDB", d, bars=bars), max_days=15, kinds=("band",))
    assert res["days_tested"] == 15 and len(res["metrics"]) == 4 and res["kinds"] == ["band"]


def test_level_test_step_samples_days():
    from backend import astro_research as ar, astro_level_test as lt
    bars = _bars(2100)
    res = lt.level_test(bars, lambda d: ar.report("MDB", d, bars=bars), max_days=40, kinds=("band",), step=4)
    assert res["step"] == 4 and res["days_tested"] == 10


def test_level_test_groups_split_zones_by_source():
    from backend import astro_research as ar, astro_level_test as lt
    assert lt._zone_group({"families": ["Pivot", "Square of 9"]}) == "zone_price"
    assert lt._zone_group({"families": ["Planet line", "Natal planet line"]}) == "zone_planet"
    assert lt._zone_group({"families": ["Pivot", "Planet line"]}) == "zone_mixed"
    rep = {"top_zones": [{"price": 10, "families": ["Pivot", "Square of 9"]}, {"price": 11, "families": ["Pivot", "Planet line"]}],
           "top_bands": [{"low": 12, "high": 13}]}
    assert [x["lo"] for x in lt._levels(rep, ("zone_price",))] == [10.0]
    assert [x["lo"] for x in lt._levels(rep, ("zone",))] == [10.0, 11.0]
    calls = []
    bars = _bars(2100)

    def fn(d):
        calls.append(d)
        return ar.report("MDB", d, bars=bars)
    res = lt.level_test_groups(bars, fn, max_days=10, step=2)
    assert len(res["groups"]) == 5 and len(calls) == len(set(calls))


def test_level_test_render_handles_single_and_grouped():
    import sys
    sys.path.insert(0, "frontend")
    from astro_research_ui import render_level_test
    m = [{"label": "x", "real": 1.0}]
    one = {"ok": True, "kinds": ["band"], "days_tested": 5, "step": 5, "first_day": "a", "last_day": "b", "touches_real": 3,
           "metrics": m, "caveat": "c"}
    assert render_level_test(one) is not None
    assert render_level_test({"ok": True, "groups": [{**one, "label": "G"}, {"label": "H", "error": "none"}]}) is not None


def test_family_test_runs_and_matches_scalar_classifier(monkeypatch):
    import random
    from backend import astro_research as ar, astro_level_test as lt
    bars = _bars(2100)
    rep = ar.report("MDB", bars[1500]["t"][:10], bars=bars, with_levels=True)
    assert set(rep["raw_levels"]) >= {"pivot", "sq9", "natal"} and "raw_levels" not in ar.report("MDB", bars[1500]["t"][:10], bars=bars)
    res = lt.family_test(bars, lambda d: ar.report("MDB", d, bars=bars, with_levels=True), max_days=30, step=3)
    assert len(res["groups"]) == 10 and all("metrics" in g or "error" in g for g in res["groups"])
    # real-result touch counts agree with the scalar classifier
    rng = random.Random(3)
    i = 1600
    ref = bars[i - 1]["c"]
    for _ in range(200):
        price = ref * (1 + rng.uniform(-0.1, 0.1))
        sc = lt.classify({"kind": "zone", "lo": price, "hi": price}, ref, bars[i], bars[i + 5]["c"])
        o, h, l, c = (float(bars[i][k]) for k in "ohlc")
        up = price > ref
        touch = (o < price <= h) if up else (l <= price < o)
        assert (sc is not None) == touch
        if sc and sc["result"] != "stalled":
            assert (sc["result"] == "through") == ((c > price) if up else (c < price))


def test_numerology_matches_the_pdf_example_and_rules():
    from backend import astro_gann_extra as gx
    assert gx.reduce_digits(144) == 9 and gx.reduce_digits(160) == 7 and gx.reduce_digits(0) == 0
    assert gx.natal_vibration("1994-05-15")["vibration"] == 7   # PDF p. 23 worked example
    assert gx.day_vibration("2026-05-22") == 1
    lv = {x["number"]: x["why"] for x in gx.numerology_levels(160.0, 1.0, 0.05, 7)}
    assert any("digits" in w for w in lv[160]) and "ends in 9" in lv[159] and "multiple of 7" in lv[161]


def test_natal_cycle_dates_by_days_weeks_months():
    from backend import astro_gann_extra as gx
    r = {c["cycle"]: c for c in gx.natal_cycle_dates("2020-01-01", 7, "2020-01-08", 2)}
    assert r["7 days"]["on_report_day"] and r["7 days"]["next"][0]["date"] == "2020-01-08"
    assert not r["7 weeks"]["on_report_day"] and r["7 weeks"]["next"][0]["date"] == "2020-02-19"
    assert r["7 months"]["next"][0]["date"] == "2020-08-01"
    assert "49 days (Jubilee 7 x 7)" in r


def test_square_of_144_levels_time_marks_and_centres():
    from backend import astro_gann_extra as gx
    anchors = [{"label": "Low", "kind": "low", "price": 100.0, "date": "2024-01-01"},
               {"label": "High", "kind": "high", "price": 180.0, "date": "2024-01-01"}]
    out = gx.sq144(anchors, "2024-02-05", 137.0, 1.0, 0.12, high_price=180.0, low_price=100.0)
    low, high = out["boxes"][0], out["boxes"][1]
    assert [round(x["price"]) for x in low["levels"]] == [136, 148]       # 100 + 36, 100 + 48
    assert sorted(round(x["price"]) for x in high["levels"]) == [132, 144]      # 180 - 48, 180 - 36
    assert low["elapsed_days"] == 35
    d = next(t for t in low["time_marks"] if t["unit"] == "days")
    assert d["nearest_mark"] == 36 and d["days_away"] == 1
    centre = [b for b in out["boxes"] if b["kind"] == "center"]
    assert [b["price"] for b in centre] == [90.0, 140.0]


def test_sq144_anchors_follow_the_owner_rule():
    from backend import astro_gann_extra as gx
    bars = _bars(2100)
    a = gx.sq144_anchors(bars[:1500], [{"name": "Intermediate High", "price": 200.0, "date": "2023-01-01"}])
    labels = [x["label"] for x in a]
    assert labels[0].startswith("Highest") and labels[1].startswith("Lowest") and any("Minor high" in x for x in labels)
    hi = max(float(b["h"]) for b in bars[:1500])
    assert a[0]["price"] == hi


def test_cosmogram_uses_only_the_pdf_bodies_and_ranks_by_distance():
    from backend import astro_gann_extra as gx, astro_ephemeris as ae
    pos = {"Sun": {"lon": 10.0}, "Moon": {"lon": 100.0}, "Galactic Center": {"lon": 10.5}, "Mars": {"lon": 190.5}}
    nat = {"Sun": {"lon": 12.0}, "Mars": {"lon": 300.0}}
    c = gx.cosmogram(pos, nat, ae.ASPECTS)
    assert all("Galactic Center" not in (p["a"], p["b"]) for p in c["pairs"])
    assert [p["orb"] for p in c["pairs"]] == sorted(p["orb"] for p in c["pairs"])
    assert c["pairs"][0]["orb"] == 0.0 and c["pairs"][0]["aspect"] == "square"
    assert any(p["orb"] == 0.5 and p["aspect"] == "opposition" for p in c["pairs"])


def test_report_includes_the_new_sections_and_the_natal_cycle_event_study():
    from backend import astro_research as ar
    bars = _bars(2100)
    r = ar.report("MDB", bars[1500]["t"][:10], bars=bars)
    for k in ("square_of_144", "numerology", "cosmogram"):
        assert k in r
    for head in ("3c. SQUARE OF 144", "3d. NUMEROLOGY", "3e. NATAL CYCLE DATES", "3f. COSMOGRAM"):
        assert head in r["draft"]
    assert "3e2. NATAL BREAKOUT" in r["draft"] and "natal_breakout" in r
    idx = ar._event_days(bars, {"kind": "natal_cycle", "unit": "weeks", "n": 49}, "MDB")
    assert idx == sorted(set(idx))


def test_price_wheel_converts_price_to_a_degree_and_finds_aspect_prices():
    from backend import astro_gann_extra as gx, astro_ephemeris as ae
    pos = {"Sun": {"lon": 50.0}, "Mars": {"lon": 140.0}, "Moon": {"lon": 111.0}}
    c = gx.cosmogram(pos, {"Sun": {"lon": 1.0}}, ae.ASPECTS, ref=410.0, unit=1.0, band=0.12)
    pw = c["price_wheel"]
    assert pw["degree"] == 50.0                                  # $410 at 1 per degree: 410 - 360 = 50
    by = {r["body"]: r for r in pw["pairs"]}
    assert by["Sun"]["aspect"] == "conjunction" and by["Sun"]["orb"] == 0.0
    assert by["Mars"]["aspect"] == "square" and by["Mars"]["orb"] == 0.0
    prices = {round(x["price"], 2) for x in pw["levels"]}
    assert 440.0 in prices                                       # Mars 140 deg - 60 deg + 360 = 440
    assert gx.cosmogram(pos, {}, ae.ASPECTS)["price_wheel"] is None


def test_report_has_the_price_wheel_section():
    from backend import astro_research as ar
    bars = _bars(2100)
    r = ar.report("MDB", bars[1500]["t"][:10], bars=bars)
    assert r["cosmogram"]["price_wheel"]["degree"] == round((r["ref_price"] / r["unit"]) % 360.0, 2)
    assert "3g. COSMOGRAM, PRICE WHEEL" in r["draft"]


def test_master_confluence_needs_geometric_and_astrological_within_half_a_percent():
    from backend import astro_gann_extra as gx
    lv = [{"price": 100.0, "family": "pivot", "label": "P"}, {"price": 100.4, "family": "transit", "label": "T"},
          {"price": 100.2, "family": "sq144", "label": "S"}, {"price": 120.0, "family": "pivot", "label": "P2"},
          {"price": 121.0, "family": "sq9", "label": "Q"}, {"price": 140.0, "family": "natal", "label": "N"}]
    out = gx.master_confluence(lv)
    assert len(out) == 1 and out[0]["geometric"] == ["pivot", "sq144"] and out[0]["astrological"] == ["transit"]
    assert out[0]["score"] == round(100 * (0.6 * 2 / 3 + 0.4 * 1 / 4), 1)
    assert gx.master_confluence([{"price": 100.0, "family": "pivot", "label": "P"}, {"price": 100.6, "family": "transit", "label": "T"}]) == []


def test_square_out_uses_the_three_degree_and_one_trading_day_tolerances():
    from datetime import date, datetime, timezone
    from backend import astro_gann_extra as gx, astro_ephemeris as ae
    assert gx.trading_days_between(date(2026, 10, 16), date(2026, 10, 19)) == 1      # Friday to Monday
    assert gx.trading_days_between(date(2026, 10, 19), date(2026, 10, 16)) == -1
    pos = {"Sun": {"lon": 52.0}, "Mars": {"lon": 140.0}}
    ex = lambda body, target: datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)      # one trading day after the report day
    pw = gx.cosmogram(pos, {}, ae.ASPECTS, ref=410.0, unit=1.0, band=0.12, exact_fn=ex, day="2026-10-19")["price_wheel"]
    by = {r["body"]: r for r in pw["pairs"]}
    assert by["Sun"]["orb"] == 2.0 and by["Sun"]["pass_price"] and by["Sun"]["pass_time"] and by["Sun"]["square_out"]
    ex2 = lambda body, target: datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)     # four trading days away
    pw2 = gx.cosmogram(pos, {}, ae.ASPECTS, ref=410.0, unit=1.0, band=0.12, exact_fn=ex2, day="2026-10-19")["price_wheel"]
    assert not {r["body"]: r for r in pw2["pairs"]}["Sun"]["square_out"]
    pw3 = gx.cosmogram({"Sun": {"lon": 54.5}}, {}, ae.ASPECTS, ref=410.0, unit=1.0, band=0.12, exact_fn=ex, day="2026-10-19")["price_wheel"]
    assert pw3["pairs"][0]["orb"] == 4.5 and not pw3["pairs"][0]["pass_price"]


def test_report_has_square_out_flags_and_master_confluence():
    from backend import astro_research as ar
    bars = _bars(2100)
    r = ar.report("MDB", bars[1500]["t"][:10], bars=bars)
    assert all("square_out" in p for p in r["cosmogram"]["price_wheel"]["pairs"])
    assert "master_zones" in r and "3h. MASTER CONFLUENCE" in r["draft"]


def test_natal_matrix_once_and_repeating_readings():
    from backend import astro_gann_extra as gx
    m = {x["cycle"]: x for x in gx.natal_matrix("2020-01-01", "2020-02-19")}        # 49 days after listing
    assert m["49 to 52 days"]["once"] and m["49 to 52 days"]["repeating"] and m["7 days"]["repeating"] and not m["7 days"]["once"]
    assert m["45 days"]["once"] is False
    far = {x["cycle"]: x for x in gx.natal_matrix("2020-01-01", "2020-07-01")}      # six months after listing
    assert far["6-month anniversary"]["once"] and far["3-month anniversary"]["repeating"] and not far["3-month anniversary"]["once"]
    assert far["12-month anniversary"]["repeating"] is False
    assert {x["cycle"]: x for x in gx.natal_matrix("2020-01-01", "2020-04-05")}["90 to 98 days"]["once"]   # day 95


def test_natal_breakout_formula_matches_the_owner_example_and_needs_a_window():
    from backend import astro_gann_extra as gx
    lv = gx.breakout_levels([{"label": "ref", "price": 100.0, "date": "x"}], 105.0, 0.12)
    prices = {round(x["price"], 2) for x in lv}
    assert 110.25 in prices and 95.06 in prices and 121.0 not in prices     # (10 + 0.5)^2 = 110.25 is the owner's $100 example; (10 - 0.25)^2 = 95.06; (10 + 1)^2 = 121 is out of range
    bars = [{"t": f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": 100, "h": 101 + (i % 7), "l": 99 - (i % 5), "c": 100.5} for i in range(120)]
    out = gx.natal_breakout("2020-01-01", "2020-02-19", bars, 100.0, 0.12)
    assert out["flag_once"] and out["levels"] and out["listing_bar_found"]
    quiet = gx.natal_breakout("2020-01-01", "2020-02-13", bars, 100.0, 0.12)        # day 43: no cycle lands here
    assert not quiet["flag_once"] and not quiet["flag_repeating"] and quiet["levels"] == []


def test_natal_base_reads_first_year_windows_and_reports_missing_history():
    from datetime import date, timedelta
    from backend import astro_gann_extra as gx
    d0 = date(2020, 1, 6)
    bars = []
    for i in range(400):
        d = d0 + timedelta(days=i)
        if d.weekday() < 5:
            bars.append({"t": d.isoformat(), "o": 100, "h": 100 + i * 0.1, "l": 90 + i * 0.05, "c": 100})
    base = gx.natal_base("2020-01-06", bars)
    w = {x["window"]: x for x in base["windows"]}
    assert base["history_starts_at_listing"] and "49 to 52 days" in w and "3-month anniversary" in w
    seven = w["7 days"]                                   # 2020-01-13 is a Monday, a trading day
    assert seven["from"] == "2020-01-13" and seven["high_date"] == "2020-01-13"
    wk = w["49 to 52 days"]                               # the window covers several bars: high is the latest, low the earliest
    assert wk["high_date"] > wk["low_date"] or wk["high_date"] == wk["low_date"]
    lv = gx.natal_base_levels(base, w["180 days"]["high"], 0.02)
    assert any(abs(x["price"] - w["180 days"]["high"]) < 1e-9 for x in lv)
    late = gx.natal_base("2010-01-04", bars)              # history starts years after the listing
    assert not late["history_starts_at_listing"] and late["windows"] == [] and late["missing"]


def test_report_has_natal_base_section():
    from backend import astro_research as ar
    bars = _bars(2100)
    r = ar.report("MDB", bars[1500]["t"][:10], bars=bars)
    assert "natal_base" in r and "3e3. NATAL BASE" in r["draft"]


def test_keys_is_in_the_symbol_table_with_the_supplied_facts():
    from backend import astro_research as ar
    r = ar.BY_SYMBOL["KEYS"]
    assert r["ipo_date"] == "2014-10-20" and r["elev_m"] == 150 and r["first_trade_et"] == "09:30"
    assert round(r["lat"], 4) == round(38 + 28 / 60, 4) and round(r["lon"], 4) == round(-(122 + 42 / 60), 4)
    bars = _bars(2100)
    rep = ar.report("KEYS", bars[1500]["t"][:10], bars=bars)
    assert rep["row"]["symbol"] == "KEYS" and "REPORT: KEYS (Keysight Technologies)" in rep["draft"]
