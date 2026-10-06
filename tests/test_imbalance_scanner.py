"""Imbalance scanner: universe, shadow vs live, cooldown, outcomes, track record, API wiring."""
import os
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

import imbalance_engine as ie
import imbalance_scanner as sc
from test_imbalance_engine import _bars, _breakout_up


def _dated(bars, start_day=1):
    for i, b in enumerate(bars):
        b["t"] = f"2026-08-{(i % 28) + 1:02d}T05:00:00Z" if False else f"2026-{1 + i // 28:02d}-{i % 28 + 1:02d}T05:00:00Z"
    return bars


def _bars_fn(mapping):
    return lambda symbols: {s: mapping.get(s, []) for s in symbols}


NO_OPT = lambda sym, spot: {"opt": None, "call_volume": None, "put_volume": None}


def test_universe_is_spy_qqq_and_mag_11():
    assert sc.UNIVERSE[:2] == ["SPY", "QQQ"]
    assert len(sc.MAG_11) == 11 and len(sc.UNIVERSE) == 13 and len(set(sc.UNIVERSE)) == 13
    for t in ("AMD", "ORCL", "MU", "AVGO", "NVDA", "TSLA"):
        assert t in sc.UNIVERSE


def test_shadow_mode_logs_but_does_not_email():
    store, sent = sc.MemoryLogStore(), []
    res = sc.run_scan(["AAPL", "MSFT"], _bars_fn({"AAPL": _breakout_up(), "MSFT": _bars(60)}), NO_OPT,
                      store=store, gate=ie.AlertGate(), live=False, send_fn=lambda r, e: sent.append(r) or True)
    assert [f["symbol"] for f in res["fired"]] == ["AAPL"]
    assert sent == [] and len(store.rows) == 1 and store.rows[0]["emailed"] is False


def test_live_mode_emails_and_marks_row():
    store, sent = sc.MemoryLogStore(), []
    sc.run_scan(["AAPL"], _bars_fn({"AAPL": _breakout_up()}), NO_OPT, store=store, gate=ie.AlertGate(),
                live=True, send_fn=lambda r, e: sent.append(r) or True)
    assert len(sent) == 1 and store.rows[0]["emailed"] is True


def test_cooldown_blocks_second_alert():
    store, gate = sc.MemoryLogStore(), ie.AlertGate(3600)
    kw = dict(store=store, gate=gate, live=False)
    data = _bars_fn({"AAPL": _breakout_up()})
    sc.run_scan(["AAPL"], data, NO_OPT, now=1000.0, **kw)
    r2 = sc.run_scan(["AAPL"], data, NO_OPT, now=1500.0, **kw)
    assert r2["fired"] == [] and r2["skipped"][0]["reason"] == "cooldown" and len(store.rows) == 1


def test_short_history_and_errors_never_crash():
    def boom(sym, spot):
        raise RuntimeError("chain down")
    res = sc.run_scan(["AAPL", "MSFT"], _bars_fn({"AAPL": _bars(5), "MSFT": _breakout_up()}), boom,
                      store=sc.MemoryLogStore(), gate=ie.AlertGate(), live=False)
    assert res["skipped"][0]["symbol"] == "AAPL" and res["errors"][0]["symbol"] == "MSFT"


def test_outcomes_filled_in_alert_direction_and_track_record():
    store = sc.MemoryLogStore()
    store.add({"alert_id": "a1", "symbol": "AAPL", "direction": "LONG", "entry_price": 100.0,
               "fired_at": "2026-01-01T15:00:00+00:00", "outcomes": {}, "outcomes_complete": False})
    store.add({"alert_id": "a2", "symbol": "AAPL", "direction": "SHORT", "entry_price": 100.0,
               "fired_at": "2026-01-01T15:00:00+00:00", "outcomes": {}, "outcomes_complete": False})
    closes = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    bars = [{"t": f"2026-01-{2 + i:02d}T05:00:00Z", "c": c} for i, c in enumerate(closes)]
    assert sc.update_outcomes(store, _bars_fn({"AAPL": bars})) == 2
    long_row = next(r for r in store.rows if r["alert_id"] == "a1")
    short_row = next(r for r in store.rows if r["alert_id"] == "a2")
    assert long_row["outcomes"]["1"] == 1.0 and long_row["outcomes"]["10"] == 10.0 and long_row["outcomes_complete"]
    assert short_row["outcomes"]["1"] == -1.0
    tr = sc.track_record(store)
    assert tr["alerts"] == 2 and tr["by_horizon"]["1"]["hit_rate"] == 0.5


def test_email_html_lists_pillars_and_guardrail():
    res = ie.evaluate("AAPL", _breakout_up(), behavior={"losing_streak": 4})
    html = sc.build_email_html(res, 123.45)
    assert "Price structure" in html and "Volume flow" in html and "Behaviour check" in html
    assert "Options flow" in html and "No data" in html


def test_flags_default_off(monkeypatch):
    monkeypatch.delenv("IMBALANCE_ALERTS_LIVE", raising=False)
    monkeypatch.delenv("IMBALANCE_SCAN_ENABLED", raising=False)
    assert not sc.is_live() and not sc.scan_enabled()
    monkeypatch.setenv("IMBALANCE_ALERTS_LIVE", "1")
    assert sc.is_live()


def test_router_exposes_expected_routes():
    import imbalance_api
    paths = {r.path for r in imbalance_api.imbalance_router.routes}
    assert paths == {"/api/imbalance/universe", "/api/imbalance/log",
                     "/api/imbalance/track-record", "/api/imbalance/scan"}


# ---- admin preview, endpoint auth, tab rendering ---------------------------------

def test_admin_preview_emails_admins_only_when_not_live():
    store, preview, sent = sc.MemoryLogStore(), [], []
    res = sc.run_scan(["AAPL"], _bars_fn({"AAPL": _breakout_up()}), NO_OPT, store=store, gate=ie.AlertGate(),
                      live=False, preview=True, send_fn=lambda r, e: sent.append(r) or True,
                      preview_fn=lambda r, e: preview.append(r) or True)
    assert len(preview) == 1 and sent == [] and res["admin_preview"] is True and store.rows[0]["emailed"] is True


def test_live_overrides_preview_and_no_preview_means_no_email():
    preview, sent = [], []
    kw = dict(gate=ie.AlertGate(), send_fn=lambda r, e: sent.append(r) or True,
              preview_fn=lambda r, e: preview.append(r) or True)
    sc.run_scan(["AAPL"], _bars_fn({"AAPL": _breakout_up()}), NO_OPT, store=sc.MemoryLogStore(),
                live=True, preview=True, **kw)
    assert len(sent) == 1 and preview == []
    sc.run_scan(["MSFT"], _bars_fn({"MSFT": _breakout_up()}), NO_OPT, store=sc.MemoryLogStore(),
                live=False, preview=False, **kw)
    assert len(sent) == 1 and preview == []


def test_admin_emails_parsed(monkeypatch):
    monkeypatch.setenv("SIGMALYTIC_ADMIN_EMAILS", " A@x.com, b@x.com ,")
    assert sc.admin_emails() == ["a@x.com", "b@x.com"]
    monkeypatch.setenv("SIGMALYTIC_ADMIN_EMAILS", "")
    monkeypatch.delenv("SIGMALYTIC_ADMIN_EMAIL", raising=False)
    assert sc.admin_emails() == []
    assert sc.send_admin_preview({"symbol": "X", "direction": "LONG", "tier": "STANDARD",
                                  "pillars_agreeing": 2, "strength": 70, "pillars": {}, "guardrail": {"notes": []}}, 1.0) is False


def test_log_endpoints_require_admin_and_header_is_read(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    import imbalance_api

    seen = {}

    def fake_require_admin(authorization=""):
        seen["auth"] = authorization
        if authorization != "Bearer good":
            raise HTTPException(status_code=401, detail="no")
        return "admin@x.com"

    monkeypatch.setattr(imbalance_api, "_admin_dependency", lambda: fake_require_admin)
    monkeypatch.setattr(imbalance_api.sc, "default_store", lambda: imbalance_api.sc.MemoryLogStore())
    app = FastAPI()
    app.include_router(imbalance_api.imbalance_router)
    c = TestClient(app)
    for path in ("/api/imbalance/log", "/api/imbalance/track-record"):
        assert c.get(path).status_code == 401
        assert c.get(path, headers={"Authorization": "Bearer good"}).status_code == 200
    assert seen["auth"] == "Bearer good"
    assert c.post("/api/imbalance/scan").status_code == 401
    assert c.get("/api/imbalance/universe").status_code == 200


def test_tab_renders_for_admin_and_non_admin(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "frontend"))
    import imbalance_tab as tab
    from dash import html

    def text(node):
        if node is None:
            return ""
        if isinstance(node, (str, int, float)):
            return str(node)
        if isinstance(node, (list, tuple)):
            return " ".join(text(n) for n in node)
        return text(getattr(node, "children", None))

    assert "soon" in text(tab.build_imbalance_tab({}, admin=False))

    data = {
        "/api/imbalance/universe": {"symbols": ["SPY", "QQQ"], "live": False, "scan_enabled": True, "admin_preview": True},
        "/api/imbalance/track-record": {"alerts": 2, "by_horizon": {"1": {"n": 2, "hit_rate": 0.5, "avg_move_pct": 0.4}}},
        "/api/imbalance/log?limit=100": {"alerts": [{
            "fired_at": "2026-10-06T15:00:00+00:00", "symbol": "NVDA", "direction": "LONG", "tier": "STANDARD",
            "pillars_agreeing": 2, "entry_price": 123.4, "emailed": True, "outcomes": {"1": 1.25},
            "detail": {"agreeing": ["price_structure", "volume_flow"]}}]},
    }
    monkeypatch.setattr(tab, "_get", lambda path, session: data[path])
    out = text(tab.build_imbalance_tab({"access_token": "t"}, admin=True))
    for needle in ("administrators only", "NVDA", "Price structure", "+1.25%", "pending", "50%"):
        assert needle in out, needle

    def boom(path, session):
        raise RuntimeError("down")
    monkeypatch.setattr(tab, "_get", boom)
    assert "Could not load" in text(tab.build_imbalance_tab({}, admin=True))


def test_app_wires_the_imbalance_tab():
    src = open(os.path.join(ROOT, "frontend", "app.py")).read()
    assert src.count('("imbalance",   "Imbalance Alerts")') == 1
    assert "'tab-imbalance'" in src and 'Input("tab-imbalance","n_clicks")' in src
    assert 'elif tab=="imbalance":' in src
    # nav id list and Input list must stay in the same order (index lookup)
    ids = src[src.index("const buttons = ["):src.index("];", src.index("const buttons = ["))]
    assert ids.rstrip().endswith("'tab-imbalance'")


def test_imports_the_way_production_does():
    """Render starts `backend.main:app` from the repo root, so modules load as `backend.*`
    with NO backend/ directory on sys.path. This is what broke the first deploy."""
    import subprocess
    code = ("import sys; sys.path[:] = [p for p in sys.path if not p.rstrip('/').endswith('backend')];"
            "import backend.imbalance_api as a, backend.imbalance_scanner as s;"
            "assert len(s.UNIVERSE) == 13; print('ok', sorted(r.path for r in a.imbalance_router.routes))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr[-600:]
