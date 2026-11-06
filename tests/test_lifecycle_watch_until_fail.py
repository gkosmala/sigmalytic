"""Breakout/breakdown lifecycle: start at the crossing bar, keep watching after
CONFIRMED with no time limit, fail on a close back through the level, and number
repeat attempts at the same level."""
from backend.weis_radar_lifecycle import WeisRadarLifecycleTracker, get_lifecycle_snapshot


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def bar(day, o, h, l, c):
    return {"t": f"2026-10-{day:02d}T04:00:00Z", "o": o, "h": h, "l": l, "c": c, "v": 1000}


def breakout_hit(day, level=100.0):
    return {"type": "BREAKOUT", "level": level, "date": f"2026-10-{day:02d}", "days_back": 0, "pct_beyond": 1.0}


def only_event(tracker):
    events = list(tracker.events.values())
    assert len(events) == 1
    return events[0]


def test_starts_on_crossing_bar_even_when_first_seen_later():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101),   # crosses 100 on the 2nd, high 102
            bar(3, 101, 101.5, 100.5, 101), bar(5, 101, 102, 100.5, 101.5)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    t.process_symbol("ABC", bars, [breakout_hit(2)])           # first noticed on the 5th
    e = only_event(t)
    assert e["trigger_bar_time"].startswith("2026-10-02")
    assert e["confirmation_level"] == 102 and e["invalidation_level"] == 100.0
    assert e["stage"] == "TRIGGERED" and e["bars_observed_after_trigger"] == 2   # sideways, not yet confirmed
    assert e["attempt"] == 1


def test_confirmed_keeps_watching_then_fails_after_confirmation():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    t.process_symbol("ABC", bars, [breakout_hit(2)])
    t.save()

    bars += [bar(5, 101, 104, 101, 103.5)]                       # close above 102 -> confirmed
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s2")
    t.process_symbol("ABC", bars, [breakout_hit(2)])
    e = only_event(t)
    assert e["stage"] == "CONFIRMED" and e["confirmed_bar_time"].startswith("2026-10-05")
    t.save()

    for day, close in [(6, 106), (7, 108), (8, 104)]:            # keeps trending, still watched
        bars += [bar(day, close, close + 1, close - 1, close)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s3")
    t.process_symbol("ABC", bars, [breakout_hit(2)])
    e = only_event(t)
    assert e["stage"] == "CONFIRMED" and e["best_close"] == 108
    assert e["pct_since_trigger"] == round((104 / 101 - 1) * 100, 2)
    t.save()

    bars += [bar(9, 101, 101, 99, 99.5)]                          # closes back below 100 -> failed
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s4")
    t.process_symbol("ABC", bars, [])
    e = only_event(t)
    assert e["stage"] == "INVALIDATED" and e["failed_after_confirmation"] is True
    assert e["terminal_bar_time"].startswith("2026-10-09")
    assert e["confirmed_bar_time"].startswith("2026-10-05")       # confirmation history kept
    t.save()
    assert get_lifecycle_snapshot(r)["summary"]["INVALIDATED"] == 1


def test_same_crossing_seen_again_is_not_duplicated():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101)]
    for scan in ("s1", "s2", "s3"):
        t = WeisRadarLifecycleTracker(r, "1Day", scan_id=scan)
        t.process_symbol("ABC", bars, [breakout_hit(2, level=100.3 if scan == "s3" else 100.0)])
        t.save()
    assert len(t.events) == 1


def test_second_attempt_after_failure_is_numbered():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101), bar(5, 100, 100, 98, 99)]   # fails on the 5th
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    t.process_symbol("ABC", bars, [breakout_hit(2)])
    assert only_event(t)["stage"] == "INVALIDATED"
    t.save()

    bars += [bar(6, 99, 101, 99, 100.8)]                          # crosses the same level again
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s2")
    t.process_symbol("ABC", bars, [breakout_hit(6, level=100.2)])
    new = [e for e in t.events.values() if e["trigger_bar_time"].startswith("2026-10-06")]
    assert len(new) == 1 and new[0]["attempt"] == 2 and new[0]["stage"] == "TRIGGERED"


def test_breakdown_mirror():
    r = FakeRedis()
    hit = {"type": "BREAKDOWN", "level": 50.0, "date": "2026-10-02"}
    bars = [bar(1, 51, 52, 50.5, 51), bar(2, 50, 50.2, 48, 49), bar(5, 49, 49, 47, 47.5),
            bar(6, 48, 51, 48, 50.5)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    t.process_symbol("XYZ", bars, [hit])
    e = only_event(t)
    assert e["direction"] == "Bearish"
    assert e["confirmed_bar_time"].startswith("2026-10-05")       # close below the crossing low of 48
    assert e["stage"] == "INVALIDATED" and e["failed_after_confirmation"] is True


def test_other_signals_unchanged_confirmed_is_final():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 97, 99, 95, 98.5)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    t.process_symbol("ABC", bars, [{"type": "SPRING", "level": 96, "score": 80}])
    t.save()
    bars += [bar(5, 99, 100, 98, 99.5), bar(6, 90, 91, 89, 90)]   # confirms, then collapses
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s2")
    t.process_symbol("ABC", bars, [])
    e = only_event(t)
    assert e["stage"] == "CONFIRMED" and e["terminal_bar_time"].startswith("2026-10-05")


def test_separate_state_key():
    r = FakeRedis()
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1", state_key="report:lifecycle:v1")
    t.process_symbol("ABC", [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101)], [breakout_hit(2)])
    t.save()
    assert get_lifecycle_snapshot(r, "report:lifecycle:v1")["events"]
    assert not get_lifecycle_snapshot(r)["events"]


def test_report_sections_from_lifecycle(monkeypatch):
    import backend.heatmap_engine as hm
    from backend import reports_engine as re_
    r = FakeRedis()
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1", state_key=re_.REPORT_LIFECYCLE_KEY)
    # NEW: crosses on the report date (Oct 9). CONF: crossed Oct 2, confirmed Oct 5.
    # SIDE: crossed Oct 6, sideways. FAIL: confirmed then fails on Oct 9.
    t.process_symbol("NEW", [bar(8, 98, 99, 97, 98), bar(9, 99, 102, 99, 101)], [breakout_hit(9)])
    t.process_symbol("CONF", [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101), bar(5, 101, 104, 101, 103.5),
                              bar(9, 104, 106, 103, 105)], [breakout_hit(2)])
    t.process_symbol("SIDE", [bar(5, 98, 99, 97, 98), bar(6, 99, 102, 99, 101), bar(9, 101, 101.5, 100.5, 101)],
                     [breakout_hit(6)])
    t.process_symbol("FAIL", [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101), bar(5, 101, 104, 101, 103.5),
                              bar(9, 100, 100, 98, 99)], [breakout_hit(2)])

    def row(sym):
        events = [e for e in t.events.values() if e["symbol"] == sym]
        return {"symbol": sym, "price": 100.0, "last_bar_date": "2026-10-09", "events": [], "setups": [],
                "climaxes": [], "volume_exhaustion": 0, "buying_exhaustion": 0, "change_pct": 1.0,
                "lifecycle": re_._report_lifecycle_events(events, "2026-10-09")}
    rows = [row(s) for s in ("NEW", "CONF", "SIDE", "FAIL")]
    monkeypatch.setattr(re_, "_run_full_universe_renko_weis_scan", lambda: rows)
    monkeypatch.setattr(hm, "_load_sector_lookup", lambda: {x["symbol"]: {"sector": "Tech"} for x in rows})
    html_doc = re_.build_report_html("2026-10-09")
    secs = {s["title"]: [x["symbol"] for x in s["symbols"]] for s in re_.symbols_from_report_html(html_doc)}
    assert secs["Breakouts: New Today (1)"] == ["NEW"]
    assert secs["Breakouts: Confirmed and Holding (1)"] == ["CONF"]
    assert secs["Breakouts: Holding, Not Yet Confirmed (1)"] == ["SIDE"]
    assert secs["Breakouts: Failed Today (1)"] == ["FAIL"]
    assert "Breakouts and Breakdowns: Summary" in html_doc
    assert "Failed after confirmation" in html_doc and "Bullish breakout, day 1" in html_doc
    assert "Needs a close above 102.00 to confirm" in html_doc


def test_failed_earlier_stays_on_watch_until_new_attempt(monkeypatch):
    from backend import reports_engine as re_
    r = FakeRedis()
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1", state_key=re_.REPORT_LIFECYCLE_KEY)
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101), bar(5, 100, 100, 98, 99), bar(9, 99, 99.5, 98, 99)]
    t.process_symbol("RTY", bars, [breakout_hit(2)])                    # failed on the 5th
    events = list(t.events.values())
    shown = re_._report_lifecycle_events(events, "2026-10-09")
    rows = [{"symbol": "RTY", "price": 99.0, "change_pct": 0.0, "lifecycle": shown}]
    sec = re_._lifecycle_sections(rows, "2026-10-09", "BREAKOUT")
    assert [i["symbol"] for i in sec["retry"]] == ["RTY"] and "watching for attempt 2" in sec["retry"][0]["status"]

    bars += [bar(12, 99, 101, 99, 100.8)]                                # second attempt
    t.process_symbol("RTY", bars, [breakout_hit(12, level=100.2)])
    shown = re_._report_lifecycle_events(list(t.events.values()), "2026-10-12")
    rows = [{"symbol": "RTY", "price": 100.8, "change_pct": 1.8, "lifecycle": shown}]
    sec = re_._lifecycle_sections(rows, "2026-10-12", "BREAKOUT")
    assert sec["retry"] == [] and [i["attempt"] for i in sec["new"]] == [2]


def test_four_hour_alignment():
    from backend import reports_engine as re_
    up = [{"c": 100 + i * 0.1} for i in range(25)]
    assert re_._four_hour_alignment(up, 101.0, True) == "Aligned"
    assert re_._four_hour_alignment(up, 110.0, True) == "Mixed"
    assert re_._four_hour_alignment(up, 101.0, False) == "Against"
    assert re_._four_hour_alignment(up[:5], 101.0, True) == "n/a"


def test_adopts_open_event_recorded_before_crossing_bar_ids():
    r = FakeRedis()
    bars = [bar(1, 98, 99, 97, 98), bar(2, 99, 102, 99, 101), bar(5, 101, 101.5, 100.5, 101)]
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s1")
    old = t._new_event("ABC", "BREAKOUT", bars[-1], breakout_hit(2))   # old style: keyed to the scan bar
    t.events[old["event_id"]] = old
    t.save()
    t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s2")
    t.process_symbol("ABC", bars, [breakout_hit(2)])
    assert len(t.events) == 1



def test_trend_blank_until_gate_then_dated(monkeypatch):
    from backend import reports_engine as re_
    import backend.heatmap_engine as hm
    monkeypatch.setattr(hm, "_load_sector_lookup", lambda: {"UP": {"sector": "Tech"}})
    # 25 flat days at 100, breakout on day 26 to 101, then a slow climb.
    closes = [100.0] * 25 + [101.0, 101.2, 101.4, 101.6, 101.8, 102.0, 102.6, 103.2, 103.8]
    bars = [{"t": f"2026-09-{d:02d}T04:00:00Z" if d <= 30 else f"2026-10-{d - 30:02d}T04:00:00Z",
             "o": c, "h": c + 0.2, "l": c - 0.2, "c": c, "v": 1000} for d, c in enumerate(closes, start=1)]
    def tracked(upto):
        r = FakeRedis()
        t = WeisRadarLifecycleTracker(r, "1Day", scan_id="s", state_key=re_.REPORT_LIFECYCLE_KEY)
        t.process_symbol("UP", bars[:upto], [{"type": "BREAKOUT", "level": 100.5, "date": bars[25]["t"][:10]}])
        rows = [{"symbol": "UP", "price": closes[upto - 1], "change_pct": 0.1, "last_bar_date": bars[upto - 1]["t"][:10],
                 "lifecycle": [e for e in t.events.values()]}]
        re_._enrich_crossing_rows(rows, {"UP": bars[:upto]}, lambda *a, **k: {}, lambda b, tf: b)
        return rows, rows[0]["lifecycle"][0]
    rows, e = tracked(30)                      # day 5: gate not crossed (10-day change +1.8%)
    assert not e.get("trend_since") and e["report_context"]["day"] == 5
    sec = re_._lifecycle_sections(rows, rows[0]["last_bar_date"], "BREAKOUT")
    item = (sec["confirmed"] + sec["holding"])[0]
    assert item["trend"] == "Sideways, day 5" and item["direction"] == "Bullish breakout, day 5"
    rows, e = tracked(len(bars))               # later: gate crossed
    assert e["trend_since"] and e["trend_since_day"] >= 6
    sec = re_._lifecycle_sections(rows, rows[0]["last_bar_date"], "BREAKOUT")
    item = (sec["confirmed"] + sec["holding"])[0]
    assert item["trend"].startswith("Trending bullish since ")
