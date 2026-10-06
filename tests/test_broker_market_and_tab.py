"""Market-data integration (stubbed network) and tab rendering for Broker Behavioural Intelligence."""
import os
import sys
from datetime import datetime, timedelta

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "frontend"))

import broker_market_data as md
import broker_review
import broker_vault_store as vs


def _bars(n=420, start="2025-01-02", seed=7):
    rng = np.random.default_rng(seed)
    px, out, d = 100.0, [], datetime.strptime(start, "%Y-%m-%d")
    for _ in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        o = px
        c = px * (1 + rng.normal(0, 0.012))
        out.append({"t": d.strftime("%Y-%m-%dT05:00:00Z"), "o": o, "h": max(o, c) * 1.004,
                    "l": min(o, c) * 0.996, "c": c, "v": float(rng.integers(8e5, 2e6))})
        px, d = c, d + timedelta(days=1)
    return out


def test_parse_date_formats():
    for s in ("2026-03-01", "03/01/2026", "03/01/26", "2026-03-01 10:00:00", "2026-03-01T10:00:00Z"):
        assert md.parse_date(s).year == 2026
    assert md.parse_date("not a date") is None and md.parse_date("") is None


def test_alignment_rules():
    long_ok = {"sequence_confirmed": True, "setup_side": "Long"}
    short_ok = {"sequence_confirmed": True, "setup_side": "Short"}
    assert md.alignment("BUY", long_ok) == "with the setup"
    assert md.alignment("SELL", long_ok) == "against the setup"
    assert md.alignment("SELL", short_ok) == "with the setup"
    assert md.alignment("BUY", short_ok) == "against the setup"
    assert md.alignment("BUY", {"sequence_confirmed": False}) == "no confirmed setup"
    assert md.alignment("BUY", None) == "no confirmed setup"


def test_point_in_time_uses_only_bars_up_to_trade_date(monkeypatch):
    data = {"AAPL": _bars()}
    seen_last = []

    def fake_fetch(symbols, start, end):
        return {s: data.get(s, []) for s in symbols}

    monkeypatch.setattr(md, "fetch_daily_bars", fake_fetch)

    import pandas as pd
    try:
        from backend.research_engine import wyckoff_verdict_engine as wve
    except Exception:
        from research_engine import wyckoff_verdict_engine as wve
    orig = wve.WyckoffVerdictEngine.evaluate_bars

    def spy(self, df, symbol=""):
        seen_last.append(len(df))
        return orig(self, df, symbol=symbol)

    monkeypatch.setattr(wve.WyckoffVerdictEngine, "evaluate_bars", spy)

    trades = [{"symbol": "AAPL", "date": "2026-02-02", "side": "BUY"},
              {"symbol": "AAPL", "date": "2026-02-02", "side": "SELL"},   # same date: read once
              {"symbol": "AAPL", "date": "2025-02-03", "side": "BUY"}]    # too early: < 60 bars
    out = md.point_in_time_readings(trades)
    late = out[("AAPL", "2026-02-02")]
    assert late is not None and late["as_of"] == "2026-02-02"
    assert late["setup_grade"] in ("A", "B", "C") and late["setup_side"] in ("Long", "Short")
    assert out[("AAPL", "2025-02-03")] is None
    # the engine must never see a bar after the trade date
    cutoff_rows = [b for b in data["AAPL"] if b["t"][:10] <= "2026-02-02"]
    assert seen_last == [len(cutoff_rows)]


def test_failed_market_data_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(md, "fetch_daily_bars", lambda s, a, b: {x: [] for x in s})
    assert md.benchmark_stats(datetime(2026, 1, 1), datetime(2026, 2, 1)) is None
    out = md.point_in_time_readings([{"symbol": "AAPL", "date": "2026-02-02", "side": "BUY"}])
    assert out[("AAPL", "2026-02-02")] is None


def test_review_survives_total_market_outage(monkeypatch):
    monkeypatch.setattr(md, "fetch_daily_bars", lambda s, a, b: {x: [] for x in s})
    rows = []
    for i in range(1, 9):
        rows += [{"date": f"2026-03-{i:02d}", "symbol": "AAPL", "side": "BUY", "quantity": 10, "price": 100, "fees": 1},
                 {"date": f"2026-03-{i:02d} 15:00:00", "symbol": "AAPL", "side": "SELL", "quantity": 10, "price": 102, "fees": 1}]
    st = vs.MemoryVaultStore()
    st.add_statement("u", 1, {"kind": "trades", "rows": rows, "row_count": len(rows), "filename": "f"})
    rv = broker_review.build_review({"slot": 1}, st.list_statements("u", 1, with_rows=True), md)
    assert rv["behavior"]["graded"] is True
    assert rv["benchmark"]["status"] == "insufficient"
    assert rv["russell_1000"]["alignment_counts"]["not read"] == 16


def test_tab_renders_review_and_layout(monkeypatch):
    import broker_bi_tab as tab
    review = {
        "vault": {"slot": 1, "name": "Schwab IRA", "broker": "Schwab"},
        "statements": {"trades": 1, "positions": 1}, "executions": 16,
        "behavior": {"graded": True, "overall_grade": "B", "overall_score": 81.2, "profile": "p",
                     "flags": ["QUICK_REENTRY_AFTER_LOSS_PATTERN"],
                     "components": {k: {"grade": "B", "score": 80, "basis": ["x"]} for k in tab.COMPONENT_LABELS}},
        "results": {"round_trip_trades": 8, "win_rate": 0.6, "realized_pnl": 10, "profit_factor": 1.4,
                    "average_win": 5, "average_loss": -3, "max_losing_streak": 2},
        "portfolio": {"status": "insufficient", "reason": "Add a holdings CSV."},
        "portfolio_health": {"status": "insufficient"},
        "benchmark": {"status": "insufficient", "reason": "x"}, "fees": {"status": "insufficient", "reason": "x"},
        "cash": {"status": "insufficient", "reason": "x"}, "tax_lots": {"status": "insufficient", "reason": "x"},
        "russell_1000": {"status": "ok", "russell_1000_trades": 1, "all_trades": 2, "share_of_trades": 0.5,
                         "alignment_counts": {"with the setup": 1}, "trades": [
                             {"date": "2026-03-01", "symbol": "AAPL", "side": "BUY", "sector": "IT",
                              "sigmalytic_reading": {"wyckoff_verdict": "v", "wyckoff_phase": "p", "setup_side": "Long", "setup_grade": "B"},
                              "alignment": "with the setup"}]},
    }
    assert tab.render_review(review).to_plotly_json()["props"]["children"]

    class R:  # backend unreachable -> layout still builds with a notice
        pass
    monkeypatch.setattr(tab._rq, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    layout = tab.build_broker_bi_tab(session=None)
    ids = []

    def walk(c):
        if isinstance(c, (list, tuple)):
            for x in c: walk(x)
        elif hasattr(c, "to_plotly_json"):
            j = c.to_plotly_json()
            cid = j["props"].get("id")
            if cid is not None:
                ids.append(str(cid))
            walk(j["props"].get("children"))
    walk(layout)
    assert len(ids) == len(set(ids)), "duplicate component ids"
    assert sum("bbi-upload" in i for i in ids) == 5


def test_setup_grade_move_is_behaviour_identical_to_original():
    """setup_grade.compute_setup_grade must equal the original radar_service function on many inputs."""
    import random
    import subprocess
    import setup_grade
    src = subprocess.run(["git", "show", "origin/main:backend/radar_service.py"], capture_output=True,
                         text=True, cwd=ROOT).stdout.split("\n")
    start = next(i for i, l in enumerate(src) if l.startswith("def _compute_setup_grade"))
    end = next(i for i, l in enumerate(src) if i > start and l.startswith("def _attach_methodology_verdicts"))
    ns = {"_f": setup_grade._f}
    exec("\n".join(src[start:end]), ns)
    rng = random.Random(3)
    for _ in range(500):
        wv = {"spring_score": rng.choice([0, 30, 64, 65, 100]), "upthrust_score": rng.choice([0, 64, 65, 90])}
        wsv = {k: rng.choice([0, 50, 100]) for k in ("volume_exhaustion", "upwave_confirmation",
                                                      "buying_exhaustion", "downwave_confirmation")}
        wsv["range_is_mature"] = rng.choice([True, False])
        assert setup_grade.compute_setup_grade(wv, wsv) == ns["_compute_setup_grade"](wv, wsv)
    assert setup_grade.compute_setup_grade({}, {}) == ns["_compute_setup_grade"]({}, {})
