"""Tests for backend/paper_trader.py: pure rules, then full cycles against a real Postgres
(DATABASE_URL) with market data and plans mocked. Nothing here touches a broker."""
import os
import sys
from datetime import datetime, date

import pytest

try:
    from backend import paper_trader as pt
except ImportError:  # running next to the module
    sys.path.insert(0, os.path.dirname(__file__))
    import paper_trader as pt  # noqa: E402

ET = pt.ET
S = dict(pt.DEFAULT_SETTINGS)


def et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


# ── pure rules ─────────────────────────────────────────────────────────────
def test_clean_settings_rejects_bad_values():
    s = pt.clean_settings({"direction": "sideways", "risk_pct": 99, "max_positions": "7", "bogus": 1, "enabled": 0})
    assert s["direction"] == "long" and s["risk_pct"] == 5.0 and s["max_positions"] == 7
    assert s["enabled"] is False and "bogus" not in s


def test_size_position_risk_and_caps():
    assert pt.size_position(1_000_000, 1_000_000, 101, 98, S) == 990          # 10% cap binds
    s2 = dict(S, max_position_pct=50)
    assert pt.size_position(1_000_000, 1_000_000, 101, 98, s2) == 1666        # 0.5% risk: 5000 / 3
    assert pt.size_position(1_000_000, 10_000, 101, 98, s2) == 98             # cash binds
    assert pt.size_position(1_000_000, 1_000_000, 50, 50, S) == 0             # no risk distance


def test_entry_fill_trigger_rules():
    plan = {"side": "Long", "entry_trigger": 101, "stop": 98, "target": 108}
    assert pt.entry_fill(plan, {"o": 100, "h": 100.9, "l": 99}, S) == {}
    assert pt.entry_fill(plan, {"o": 100, "h": 102, "l": 99}, S) == {"fill": 101}
    assert pt.entry_fill(plan, {"o": 103, "h": 104, "l": 102}, S) == {"fill": 103}     # gap: open
    assert "skip" in pt.entry_fill(plan, {"o": 109, "h": 110, "l": 108.5}, S)          # past target
    short = {"side": "Short", "entry_trigger": 50, "stop": 52, "target": 45}
    assert pt.entry_fill(short, {"o": 51, "h": 51.5, "l": 49.5}, S) == {"fill": 50}


def test_exit_rules_stop_first_and_gap():
    pos = {"side": "Long", "qty_open": 100, "stop": 98, "target": 108, "exit_mode": "target", "time_limit": 10}
    both = pt.exit_checks(pos, {"o": 100, "h": 109, "l": 97}, 100, None, False)
    assert both == [{"qty": 100, "price": 98, "reason": "Stop (invalidation)"}]
    gap = pt.exit_checks(pos, {"o": 95, "h": 96, "l": 94}, 95, None, False)
    assert gap[0]["price"] == 95
    tgt = pt.exit_checks(pos, {"o": 104, "h": 108.2, "l": 103}, 107, None, False)
    assert tgt == [{"qty": 100, "price": 108, "reason": "Target"}]


def test_exit_half_2r_and_time_limit():
    pos = {"side": "Long", "qty_open": 100, "stop": 98, "target": 110, "t1_price": 107, "t1_done": False,
           "exit_mode": "half_2r", "time_limit": 10, "sessions_held": 3}
    a = pt.exit_checks(pos, {"o": 104, "h": 107.5, "l": 103}, 107, None, False)
    assert a == [{"qty": 50, "price": 107, "reason": "First target (2x risk), half"}]
    pos2 = dict(pos, exit_mode="target", target=120, sessions_held=10)
    assert pt.exit_checks(pos2, {"o": 104, "h": 105, "l": 103}, 104.5, None, True)[0]["reason"].startswith("Time limit")
    assert pt.exit_checks(pos2, {"o": 104, "h": 105, "l": 103}, 104.5, None, False) == []


def test_exit_status_mode():
    pos = {"side": "Long", "qty_open": 10, "stop": 98, "target": None, "exit_mode": "status", "time_limit": 0}
    assert pt.exit_checks(pos, {"o": 100, "h": 101, "l": 99}, 100.5, "Armed", False) == []
    assert pt.exit_checks(pos, {"o": 100, "h": 101, "l": 99}, 100.5, "Avoid", False)[0]["qty"] == 10


# ── full cycles against Postgres ─────────────────────────────────────────────
# The database tests DROP the paper_* tables, so they never use DATABASE_URL (production);
# they run only against a throwaway database named in PAPER_TEST_DATABASE_URL.
TEST_DB = os.getenv("PAPER_TEST_DATABASE_URL")
pytestmark_db = pytest.mark.skipif(not TEST_DB, reason="needs PAPER_TEST_DATABASE_URL (a throwaway database)")


@pytest.fixture(autouse=True)
def _test_database(monkeypatch):
    if TEST_DB:
        monkeypatch.setenv("DATABASE_URL", TEST_DB)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)

PLANS = {
    "AAA:1Day:2026-11-20T05:00:00Z:Long": {"symbol": "AAA", "side": "Long", "test_bar_time": "2026-11-20T05:00:00Z",
                                            "entry_trigger": 101, "invalidation": 98, "target": 108},
    "BBB:1Day:2026-11-20T05:00:00Z:Long": {"symbol": "BBB", "side": "Long", "test_bar_time": "2026-11-20T05:00:00Z",
                                            "entry_trigger": 50, "invalidation": 49, "target": 53},
    "CCC:1Day:2026-11-20T05:00:00Z:Short": {"symbol": "CCC", "side": "Short", "test_bar_time": "2026-11-20T05:00:00Z",
                                             "entry_trigger": 30, "invalidation": 31, "target": 27},
    "DDD:1Day:2026-11-20T05:00:00Z:Long": {"symbol": "DDD", "side": "Long", "test_bar_time": "2026-11-20T05:00:00Z",
                                            "entry_trigger": 20, "invalidation": 19, "target": 23,
                                            "outcome": {"status": "OPEN"}},
}


def _snap(day, bars, latest):
    return {s: {"latest": latest.get(s), "bar": dict(b, t=day)} for s, b in bars.items()}


@pytestmark_db
def test_full_week(monkeypatch):
    conn = pt._db(); cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS paper_account, paper_plans, paper_positions, paper_fills, paper_equity")
    conn.commit(); conn.close()
    monkeypatch.setattr(pt, "load_plans", lambda: PLANS)
    monkeypatch.setattr(pt, "load_radar_statuses", lambda syms: {})
    monkeypatch.setattr(pt, "fetch_daily_bars", lambda sym, start: [])
    # account created on Saturday (deploy day)
    s = pt.summary(); assert s["equity"] == 1_000_000 and s["starting_cash"] == 1_000_000

    spy = {"SPY": {"o": 680, "h": 690, "l": 675, "c": 685}}
    # Monday 10:00 -- AAA trades through its trigger, BBB gaps above it
    day = "2026-11-23"
    data = _snap(day, {**spy, "AAA": {"o": 100, "h": 101.5, "l": 99.5, "c": 101.2},
                       "BBB": {"o": 51, "h": 51.2, "l": 50.8, "c": 51}},
                 {"SPY": 685, "AAA": 101.2, "BBB": 51})
    monkeypatch.setattr(pt, "fetch_snapshots", lambda syms: data)
    r = pt.run_cycle(now=et(2026, 11, 23, 10, 0)); assert r["ok"], r
    s = pt.summary()
    pos = {p["symbol"]: p for p in s["positions"]}
    assert set(pos) == {"AAA", "BBB"}
    assert pos["AAA"]["qty"] == 990 and pos["AAA"]["entry_price"] == 101
    assert pos["BBB"]["qty"] == 1960 and pos["BBB"]["entry_price"] == 51
    j = pt.journal()
    reasons = {x["symbol"]: x["reason"] for x in j["not_taken"]}
    assert "shorts are turned off" in reasons["CCC"] and "already triggered" in reasons["DDD"]
    # running the same cycle again does not double-trade
    pt.run_cycle(now=et(2026, 11, 23, 10, 5))
    assert len(pt.summary()["positions"]) == 2 and len(pt.journal()["fills"]) == 2

    # Tuesday: no exits; Wednesday: AAA hits target, BBB gaps to the stop
    day = "2026-11-24"
    data2 = _snap(day, {**spy, "AAA": {"o": 102, "h": 104, "l": 101, "c": 103},
                        "BBB": {"o": 51, "h": 52, "l": 50, "c": 51.5}}, {"SPY": 686, "AAA": 103, "BBB": 51.5})
    monkeypatch.setattr(pt, "fetch_snapshots", lambda syms: data2)
    pt.run_cycle(now=et(2026, 11, 24, 10, 0))
    assert len(pt.summary()["positions"]) == 2
    day = "2026-11-25"
    data3 = _snap(day, {**spy, "AAA": {"o": 105, "h": 108.5, "l": 104.5, "c": 108.1},
                        "BBB": {"o": 48.8, "h": 49.5, "l": 48.5, "c": 49}}, {"SPY": 690, "AAA": 108.1, "BBB": 49})
    monkeypatch.setattr(pt, "fetch_snapshots", lambda syms: data3)
    pt.run_cycle(now=et(2026, 11, 25, 10, 0))
    s = pt.summary()
    assert s["positions"] == []
    closed = {c["symbol"]: c for c in s["closed"]}
    fee = lambda q, p: round(q * p * 5 / 10000, 2)
    assert closed["AAA"]["pnl"] == round(990 * 7 - fee(990, 101) - fee(990, 108), 2)
    assert closed["BBB"]["pnl"] == round(1960 * (48.8 - 51) - fee(1960, 51) - fee(1960, 48.8), 2)
    assert s["cash"] == s["equity"] == round(1_000_000 + closed["AAA"]["pnl"] + closed["BBB"]["pnl"], 2)
    assert s["stats"]["closed_trades"] == 2 and s["stats"]["wins"] == 1

    # pausing stops trading; reset starts a new run at $1,000,000
    pt.save_settings({"enabled": False})
    assert pt.summary()["settings"]["enabled"] is False
    r = pt.reset(); assert r["ok"] and r["run_id"] == 2
    s = pt.summary(); assert s["equity"] == 1_000_000 and s["closed"] == []


@pytestmark_db
def test_catch_up_after_downtime_and_half_2r(monkeypatch):
    pt.reset()
    pt.save_settings({"enabled": True, "exit_mode": "half_2r", "max_position_pct": 100})
    plans = {"EEE:1Day:2026-11-27T05:00:00Z:Long": {"symbol": "EEE", "side": "Long",
             "test_bar_time": "2026-11-27T05:00:00Z", "entry_trigger": 100, "invalidation": 98, "target": 110}}
    monkeypatch.setattr(pt, "load_plans", lambda: plans)
    monkeypatch.setattr(pt, "load_radar_statuses", lambda syms: {})
    monkeypatch.setattr(pt, "fetch_daily_bars", lambda sym, start: [])
    spy = {"SPY": {"o": 680, "h": 690, "l": 675, "c": 685}}
    d1 = _snap("2026-11-30", {**spy, "EEE": {"o": 99, "h": 100.5, "l": 98.8, "c": 100.2}}, {"SPY": 685, "EEE": 100.2})
    monkeypatch.setattr(pt, "fetch_snapshots", lambda syms: d1)
    pt.run_cycle(now=et(2026, 11, 30, 10, 0))
    p = pt.summary()["positions"][0]
    assert p["qty"] == 2500 and p["t1_price"] == 104          # 5,000 risk / 2; 2x risk = 104
    # backend down Tue-Wed; Thursday it catches up: Tue reached 104.5 (half out), Wed hit the stop
    missed = [{"t": "2026-12-01", "o": 101, "h": 104.5, "l": 100.5, "c": 104},
              {"t": "2026-12-02", "o": 103, "h": 103.5, "l": 97.5, "c": 98}]
    monkeypatch.setattr(pt, "fetch_daily_bars", lambda sym, start: missed)
    d4 = _snap("2026-12-03", {**spy, "EEE": {"o": 97, "h": 98, "l": 96, "c": 97}}, {"SPY": 685, "EEE": 97})
    monkeypatch.setattr(pt, "fetch_snapshots", lambda syms: d4)
    pt.run_cycle(now=et(2026, 12, 3, 10, 0))
    s = pt.summary()
    assert s["positions"] == []
    fills = [f for f in pt.journal()["fills"] if f["symbol"] == "EEE"]
    sells = sorted((f["reason"], f["qty"], f["price"]) for f in fills if f["action"] == "SELL")
    assert sells == [("First target (2x risk), half", 1250, 104.0), ("Stop (invalidation)", 1250, 98.0)]
