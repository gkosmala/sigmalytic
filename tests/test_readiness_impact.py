"""Readiness-impact diagnostic: read-only, exact engine arithmetic, admin only."""
import os
import random
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

for _k in ("RESEND_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "ALPACA_API_KEY", "ALPACA_API_SECRET"):
    os.environ.setdefault(_k, "dummy")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

from backend import readiness_impact as ri
from backend import behavioral_transition_engine as bte

BASE = dict(symbol="X", price=100, trigger=100.5, invalidation=98, setup_type="Monitoring", regime="Neutral",
            status="Watching", intelligence_delta=0, deep_score=0, agreement_score=100)
NEUTRAL = dict(relative_strength=55, volume_pressure=50, behavioral=50, expansion_node=0, confluence=50)


def _res(status="Watching", **factors):
    f = dict(NEUTRAL, composite=0)
    f.update(factors)
    return dict(BASE, status=status, _factors=f)


def test_missing_factors_cost_long_exactly_20_and_short_exactly_2():
    """Same row, factors missing vs neutral values: the exact points the zeros cost."""
    for status, cost in (("Watching", 20.0), ("Short Armed", 2.0)):
        row = dict(BASE, status=status, composite_score=0)
        shipped = bte.evaluate_behavioral_transition(row)["readiness_score"]
        neutral = bte.evaluate_behavioral_transition(dict(row, **NEUTRAL))["readiness_score"]
        assert round(neutral - shipped, 1) == cost, (status, shipped, neutral)


def test_compare_readiness_neutral_factors_reproduce_the_exact_cost():
    long_ = ri.compare_readiness(_res("Watching"), weis_composite=0)
    short = ri.compare_readiness(_res("Short Armed"), weis_composite=0)
    assert long_["side"] == "Long" and long_["stage2"]["delta"] == 20.0
    assert short["side"] == "Short" and short["stage2"]["delta"] == 2.0


def test_stage1_has_no_composite_and_stage2_uses_the_live_weis_composite():
    r = ri.compare_readiness(_res("Watching", composite=70), weis_composite=100)
    assert r["stage1"]["delta"] != r["stage2"]["delta"] or r["stage1"]["restored"] != r["stage2"]["restored"]
    now1 = bte.evaluate_behavioral_transition(dict(BASE, status="Watching"))["readiness_score"]
    assert r["stage1"]["now"]["readiness"] == now1  # composite absent at stage 1, as shipped


def test_summary_counts_and_transitions():
    rows = [ri.compare_readiness(_res("Watching"), 100) for _ in range(3)] + \
           [ri.compare_readiness(_res("Short Armed"), 100)]
    s = ri.summarize(rows)
    assert s["symbols"] == 4 and s["stage2"]["Long"]["n"] == 3 and s["stage2"]["Short"]["n"] == 1
    assert s["stage2"]["Long"]["mean_delta"] == 20.0 and s["stage2"]["Short"]["mean_delta"] == 2.0
    assert ri.summary_or_empty([]) == {"symbols": 0}


def test_pick_sample_is_spread_and_capped():
    syms = [f"S{i:03d}" for i in range(500)]
    pick = ri.pick_sample(syms, 50)
    assert len(pick) == 50 and pick[0] == "S000" and pick[-1] >= "S450"
    assert len(ri.pick_sample(syms, 9999)) == ri.MAX_SAMPLE
    assert ri.pick_sample(["B", "A"], 10) == ["A", "B"]


def test_run_diagnostic_with_stubs_skips_bad_symbols_and_is_read_only():
    cache = {"AAA": {"composite_score": 100}, "BBB": {"composite_score": 78}, "CCC": {}}
    calls = []

    def score(sym, snap, bars, _return_factors=False):
        calls.append((sym, _return_factors))
        return _res("Watching") if sym != "BBB" else {}

    out = ri.run_diagnostic(cache, 10,
                            fetch_snapshots=lambda s: {"AAA": {"x": 1}, "BBB": {"x": 1}},   # CCC has no snapshot
                            fetch_bars=lambda s: {"AAA": [{}] * 30, "BBB": [{}] * 30, "CCC": [{}] * 30},
                            score_symbol=score)
    assert [r["symbol"] for r in out["rows"]] == ["X"] and out["summary"]["symbols"] == 1
    reasons = {x["symbol"]: x["reason"] for x in out["skipped"]}
    assert reasons["BBB"] == "score_symbol rejected the data" and reasons["CCC"] == "no snapshot"
    assert all(flag is True for _, flag in calls)


def test_score_symbol_output_is_unchanged_unless_factors_requested():
    from backend import radar_service as rs
    random.seed(5)
    px, bars = 100.0, []
    for _ in range(80):
        o, c = px, px * (1 + random.gauss(0.001, 0.01))
        bars.append({"o": o, "h": max(o, c) * 1.004, "l": min(o, c) * 0.996, "c": c, "v": 1_200_000}); px = c
    last = bars[-1]
    snap = {"dailyBar": {"o": last["o"], "h": last["h"], "l": last["l"], "c": last["c"], "v": 2_000_000, "vw": last["c"]},
            "prevDailyBar": {"c": bars[-2]["c"]}, "latestTrade": {"p": last["c"]}}
    plain = rs.score_symbol("T", snap, bars)
    with_f = rs.score_symbol("T", snap, bars, _return_factors=True)
    assert "_factors" not in plain and "_factors" in with_f
    strip = lambda d: {k: v for k, v in d.items() if k not in ("_factors", "updated_at")}
    assert strip(plain) == strip(with_f)
    assert set(with_f["_factors"]) == {"confluence", "expansion_node", "relative_strength",
                                       "volume_pressure", "behavioral", "composite"}


def test_endpoint_requires_admin(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    def fake_admin(authorization=""):
        if authorization != "Bearer good":
            raise HTTPException(status_code=401, detail="no")
        return "a@x.com"

    monkeypatch.setattr(ri, "_admin_dependency", lambda: fake_admin)
    app = FastAPI(); app.include_router(ri.readiness_router)
    c = TestClient(app)
    assert c.get("/api/admin/readiness-impact").status_code == 401


def test_imports_the_way_production_does():
    code = ("import sys; sys.path[:] = [p for p in sys.path if not p.rstrip('/').endswith('backend')];"
            "import backend.readiness_impact as r; print('ok', [x.path for x in r.readiness_router.routes])")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0 and "readiness-impact" in out.stdout, out.stderr[-500:]


def test_admin_card_and_view_render():
    sys.path.insert(0, os.path.join(ROOT, "frontend"))
    import readiness_impact_view as view

    def text(node):
        if node is None:
            return ""
        if isinstance(node, (str, int, float)):
            return str(node)
        if isinstance(node, (list, tuple)):
            return " ".join(text(n) for n in node)
        return text(getattr(node, "children", None))

    rows = [ri.compare_readiness(dict(_res("Watching"), symbol="LONGY"), 100),
            ri.compare_readiness(dict(_res("Short Armed"), symbol="SHORTY"), 78)]
    payload = {"summary": ri.summarize(rows), "rows": rows, "skipped": [], "note": "n"}
    out = text(view.render_readiness_impact(payload))
    for needle in ("2 symbols scored live", "+20.0", "+2.0", "LONGY", "SHORTY", "Page shown to users"):
        assert needle in out, needle
    assert "No symbols could be scored" in text(view.render_readiness_impact({"summary": {"symbols": 0}, "skipped": []}))
    assert "Unexpected response" in text(view.render_readiness_impact({"oops": 1}))

    src = open(os.path.join(ROOT, "frontend", "app.py")).read()
    assert 'id="btn-readiness-impact"' in src and 'Output("readiness-impact-output", "children")' in src
    assert "readiness_impact_block,\n        weis_state_block,\n        radar_bars_block,\n        grade_grid" in src
