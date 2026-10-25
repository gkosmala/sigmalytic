import math
from datetime import date, timedelta

import pytest

from backend import ma_study as ms


def _bars(closes, vols=None):
    out, d = [], date(2022, 1, 3)
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"t": f"{d}T05:00:00Z", "c": c, "v": (vols or [1000] * len(closes))[i]})
        d += timedelta(days=1)
    return out


def _brute(closes, n):
    sides = []
    for i in range(n - 1, len(closes)):
        m = sum(closes[i - n + 1:i + 1]) / n
        sides.append(1 if closes[i] > m else (-1 if closes[i] < m else (sides[-1] if sides else 1)))
    runs, cur = [], 1
    for a, b in zip(sides, sides[1:]):
        if a == b:
            cur += 1
        else:
            runs.append((a, cur)); cur = 1
    runs.append((sides[-1], cur))
    return sides, runs


def test_runs_and_crossings_match_brute_force():
    closes = [100 + 10 * math.sin(i / 7) + (i % 5) * 0.3 for i in range(400)]
    r = ms.analyze("X", _bars(closes), 20)
    sides, runs = _brute(closes, 20)
    assert r["crossings"] == len(runs) - 1
    assert r["sides"]["above"]["days_total"] == sides.count(1)
    assert r["sides"]["below"]["days_total"] == sides.count(-1)
    done_above = sorted(d for s, d in runs[1:-1] if s == 1)
    assert r["sides"]["above"]["run_days"]["count"] == len(done_above)
    assert r["sides"]["above"]["run_days"]["max"] == max(done_above)
    assert r["current"]["days"] == runs[-1][1]
    assert sum(b["count"] for b in r["sides"]["below"]["buckets"]) == r["sides"]["below"]["run_days"]["count"]


def test_volume_split_and_follow_through():
    closes, vols = [], []
    for k in range(12):                       # alternating 15-day up and down legs
        for j in range(15):
            closes.append(100 + (j if k % 2 == 0 else 15 - j))
            vols.append(1000)
    sides, _ = _brute(closes, 10)             # make every day that crosses above the average heavy volume
    for k in range(1, len(sides)):
        if sides[k] == 1 and sides[k - 1] == -1:
            vols[k + 9] = 3000
    r = ms.analyze("X", _bars(closes, vols), 10)
    up = r["sides"]["above"]
    assert up["volume"]["heavy_cross"]["count"] >= 1
    assert up["follow_through"]["5d"]["all"]["count"] >= 1
    assert r["trend"]["ma"] > 0 and "text" not in r
    txt = ms.summary_text(r)
    assert "crossings" in txt.lower() and "Current:" in txt and "Recent runs" in txt


def test_needs_history():
    with pytest.raises(ValueError):
        ms.analyze("X", _bars([100.0] * 30), 20)


def test_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import main
    monkeypatch.setattr(ms, "build", lambda s, l, y: {"symbol": s, "length": l, "years": y})
    main.app.dependency_overrides[main.require_admin] = lambda: "admin"
    try:
        c = TestClient(main.app)
        assert c.post("/api/admin/ma-study/run", json={"symbol": "app", "length": 20}).json() == \
            {"ok": True, "symbol": "APP", "length": 20, "years": 10}
        assert not c.post("/api/admin/ma-study/run", json={"symbol": "??"}).json()["ok"]
    finally:
        main.app.dependency_overrides.clear()


def test_admin_page_builds_with_every_card():
    """Regression: the Admin page must build (a card once used a style defined later and broke the whole tab)."""
    import os, sys, json
    os.environ["SIGMALYTIC_ADMIN_EMAILS"] = "owner@example.com"
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))
    import app as A
    A.req.get = lambda *a, **k: type("R", (), {"ok": False, "status_code": 500, "json": lambda s: {}})()
    tab = A.build_admin_tab({"email": "owner@example.com", "access_token": "t"}, "http://x")
    s = json.dumps(tab.to_plotly_json(), default=lambda o: o.to_plotly_json())
    for cid in ("ma-study-run-btn", "catalyst-run-btn", "report-hub-load-btn", "content-hub-run-btn"):
        assert cid in s, cid
