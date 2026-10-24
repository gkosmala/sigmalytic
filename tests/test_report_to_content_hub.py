from backend import reports_engine as re_


def _report_html():
    setups = [{"symbol": "AAPL", "label": "Near support", "price": 231.4, "date": "2026-10-23", "evidence": "x", "priority": 1},
              {"symbol": "MSFT", "label": "Near resistance", "price": 512.0, "date": "2026-10-23", "evidence": "y", "priority": 2}]
    exh = [{"symbol": "AAPL", "label": "Selling exhaustion", "price": 231.4, "date": "2026-10-23", "evidence": "z", "priority": 1}]
    movers = [{"symbol": "TSLA", "price": 374.58, "change_pct": -3.08, "rel_volume": 1.4, "volume": 123456789}]
    return ("<html><body><section><h2>Market Overview</h2><p>no table</p></section>"
            + re_._opportunity_table(setups, "Setting Up: Near Tested Levels", "note")
            + re_._opportunity_table([], "Buying and Selling Climaxes", "note")
            + re_._opportunity_table(exh, "Buying and Selling Exhaustion", "note")
            + re_._movers_table(movers) + "</body></html>")


def test_symbols_by_section():
    secs = re_.symbols_from_report_html(_report_html())
    assert [s["title"] for s in secs] == ["Setting Up: Near Tested Levels (2)", "Buying and Selling Exhaustion (1)",
                                         "What Happened in the Market Today"]
    assert [x["symbol"] for x in secs[0]["symbols"]] == ["AAPL", "MSFT"]
    assert secs[0]["symbols"][0] == {"symbol": "AAPL", "detail": "Near support", "price": "231.40"}
    assert secs[2]["symbols"][0] == {"symbol": "TSLA", "detail": "-3.08%", "price": "374.58"}


def test_report_symbols_uses_latest(monkeypatch):
    monkeypatch.setattr(re_, "report_catalog", lambda: {"ok": True, "dates": ["2026-10-23", "2026-10-22"]})
    monkeypatch.setattr(re_, "get_report_html", lambda d: _report_html() if d == "2026-10-23" else None)
    out = re_.report_symbols()
    assert out["ok"] and out["date"] == "2026-10-23" and len(out["sections"]) == 3
    assert not re_.report_symbols("2026-10-22")["ok"]


def test_endpoints_and_same_day_reuse(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main, content_hub
    calls = []
    monkeypatch.setattr(content_hub, "build_package", lambda s, use_ai=True: calls.append(s) or {"symbol": s})
    monkeypatch.setattr(re_, "report_symbols", lambda d=None: {"ok": True, "date": d or "latest", "sections": []})
    main._CONTENT_HUB_REUSE.clear()
    main.app.dependency_overrides[main.require_admin] = lambda: "admin"
    try:
        c = TestClient(main.app)
        assert c.get("/api/admin/report-symbols", params={"date": "2026-10-23"}).json()["date"] == "2026-10-23"
        assert not c.get("/api/admin/report-symbols", params={"date": "bad"}).json()["ok"]
        a = c.post("/api/admin/content-hub/generate", json={"symbol": "aapl", "reuse": True}).json()
        b = c.post("/api/admin/content-hub/generate", json={"symbol": "AAPL", "reuse": True}).json()
        fresh = c.post("/api/admin/content-hub/generate", json={"symbol": "AAPL", "reuse": False}).json()
        plain = c.post("/api/admin/content-hub/generate", json={"symbol": "AAPL"}).json()   # Content Hub card: always fresh
        assert a["ok"] and not a.get("reused") and b.get("reused") and not fresh.get("reused") and not plain.get("reused")
        assert calls == ["AAPL", "AAPL", "AAPL"]
    finally:
        main.app.dependency_overrides.clear()


def test_report_lists_breakouts_and_breakdowns_separately(monkeypatch):
    import backend.heatmap_engine as hm
    def row(sym, events):
        return {"symbol": sym, "price": 100.0, "last_bar_date": "2026-10-23", "events": events, "setups": [],
                "climaxes": [], "volume_exhaustion": 0, "buying_exhaustion": 0, "change_pct": 1.0}
    rows = [row("UPP", [{"type": "BREAKOUT", "level": 98, "pct_beyond": 2.0, "days_back": 1, "date": "2026-10-22"}]),
            row("DWN", [{"type": "BREAKDOWN", "level": 102, "pct_beyond": -2.0, "days_back": 0}]),
            row("SPR", [{"type": "SPRING", "level": 95, "score": 80}])]
    rows += [row(f"B{i:02d}", [{"type": "BREAKOUT", "level": 90, "pct_beyond": 1.0, "days_back": 2}]) for i in range(25)]
    monkeypatch.setattr(re_, "_run_full_universe_renko_weis_scan", lambda: rows)
    monkeypatch.setattr(hm, "_load_sector_lookup", lambda: {r["symbol"]: {"sector": "Tech"} for r in rows})
    html_doc = re_.build_report_html("2026-10-23")
    secs = {s["title"]: [x["symbol"] for x in s["symbols"]] for s in re_.symbols_from_report_html(html_doc)}
    assert secs["Breakouts (26)"][0] == "UPP" and len(secs["Breakouts (26)"]) == 26     # full list, newest first
    assert secs["Breakdowns (1)"] == ["DWN"]
    assert secs["Observed Springs and Upthrusts (1)"] == ["SPR"]
    assert "Upthrusts and Crossings" not in html_doc
