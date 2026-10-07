"""Tests for backend/weis_state_preview.py (read-only admin preview)."""
from backend import weis_state_preview as wsp


def _bars(n=80, base=100.0):
    out = []
    for i in range(n):
        c = base + (i % 20 if i % 20 < 10 else 20 - i % 20)
        out.append({"t": f"2026-01-{(i % 28) + 1:02d}T{i:04d}", "o": c, "h": c + 0.2, "l": c - 0.2, "c": c, "v": 1000})
    return out


def test_swing_preview_runs_and_labels_rows():
    cache = {"AAA": {"status": "Watching", "composite_score": 60}}
    calls = []

    def fake_fetch(symbols, timeframe="1Day", lookback_days=280):
        calls.append(timeframe)
        return {s: _bars() for s in symbols}

    out = wsp.run_preview(cache, None, 10, "swing", fake_fetch)
    assert calls == ["1Day"] and out["mode"] == "swing"
    assert out["summary"]["symbols"] == 1
    assert out["rows"][0]["radar_status_today"] == "Watching"
    assert "NOT from Weis" in out["note"]


def test_day_preview_fetches_three_frames_and_uses_ladder():
    calls = []

    def fake_fetch(symbols, timeframe="1Day", lookback_days=280):
        calls.append(timeframe)
        return {s: _bars() for s in symbols}

    out = wsp.run_preview({}, ["aaa"], 5, "day", fake_fetch)
    assert sorted(calls) == ["15Min", "1Day", "1Hour"]
    assert out["ladder"]["structure"] == ["1Hour", "1Day"]
    assert out["rows"][0]["symbol"] == "AAA"
    row = out["rows"][0]
    assert row["state"] == "No setup" or "1Hour" in row["trends_by_frame"]


def test_too_few_bars_is_skipped_not_an_error():
    out = wsp.run_preview({}, ["ZZZ"], 5, "swing", lambda s, timeframe="1Day", lookback_days=280: {"ZZZ": _bars(5)})
    assert out["rows"] == [] and out["skipped"][0]["symbol"] == "ZZZ"


def test_route_requires_admin(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    def fake_admin(authorization=""):
        if authorization != "Bearer good":
            raise HTTPException(status_code=401, detail="no")
        return "a@x.com"

    monkeypatch.setattr(wsp, "_admin_dependency", lambda: fake_admin)
    app = FastAPI(); app.include_router(wsp.weis_state_router)
    assert TestClient(app).get("/api/admin/weis-state-preview").status_code == 401


def test_imports_the_way_production_does():
    import subprocess, sys, os
    root = os.path.dirname(os.path.dirname(__file__))
    code = ("import sys; sys.path[:] = [p for p in sys.path if not p.rstrip('/').endswith('backend')];"
            "import backend.weis_state_preview as r; print('ok', [x.path for x in r.weis_state_router.routes])")
    out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert out.returncode == 0 and "weis-state-preview" in out.stdout, out.stderr[-500:]


def test_fetch_is_chunked_to_avoid_the_10000_bar_cap():
    sizes = []

    def fake_fetch(symbols, timeframe="1Day", lookback_days=280):
        sizes.append(len(symbols))
        return {s: _bars() for s in symbols}

    syms = [f"S{i}" for i in range(25)]
    wsp.run_preview({}, syms, 25, "swing", fake_fetch)
    assert sizes == [10, 10, 5]
