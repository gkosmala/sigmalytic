"""API, storage isolation and review tests for Broker Behavioural Intelligence."""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import broker_intelligence_api as api
import broker_review
import broker_vault_store as vs

TRADES_CSV = "Date,Symbol,Action,Quantity,Price,Commission\n" + "\n".join(
    line for i in range(1, 9) for line in (
        f"2026-03-{i:02d} 10:00:00,AAPL,Buy,10,100,1",
        f"2026-03-{i:02d} 15:00:00,AAPL,Sell,10,{103 if i % 4 else 97},1",
    )
)
POSITIONS_CSV = "Symbol,Quantity,Price,Cost Basis\nAAPL,10,200,1500\nMSFT,10,100,900\nCash,,,\n"


class FakeMarket:
    parse_date = staticmethod(__import__("broker_market_data").parse_date)
    alignment = staticmethod(__import__("broker_market_data").alignment)

    def benchmark_stats(self, start, end):
        return {"return_pct": 4.0, "max_drawdown_pct": -3.0}

    def point_in_time_readings(self, trades):
        return {(t["symbol"], t["date"]): {"sequence_confirmed": True, "setup_side": "Long",
                                           "setup_grade": "B", "wyckoff_verdict": "x", "wyckoff_phase": "y",
                                           "reason": "r", "as_of": "d"} for t in trades}


@pytest.fixture()
def client(monkeypatch):
    st = vs.MemoryVaultStore()
    api.set_store_for_tests(st)
    monkeypatch.setattr(api, "get_user_id_from_request",
                        lambda req: req.headers.get("X-Test-User", "demo_user_001"))
    app = FastAPI()
    app.include_router(api.broker_router)
    c = TestClient(app)
    c.store = st
    yield c
    api.set_store_for_tests(None)


def up(c, slot, text, kind="trades", user="alice"):
    return c.post(f"/api/broker-vaults/{slot}/statements", headers={"X-Test-User": user},
                  files={"file": ("s.csv", text.encode(), "text/csv")}, data={"kind": kind})


def test_demo_account_is_refused(client):
    assert client.get("/api/broker-vaults").status_code == 403
    assert client.post("/api/broker-vaults/1/statements",
                       files={"file": ("s.csv", b"x")}, data={"kind": "trades"}).status_code == 403


def test_five_slots_listed(client):
    r = client.get("/api/broker-vaults", headers={"X-Test-User": "alice"}).json()
    assert [v["slot"] for v in r["vaults"]] == [1, 2, 3, 4, 5]


def test_slot_six_rejected(client):
    r = client.put("/api/broker-vaults/6", headers={"X-Test-User": "alice"}, json={"name": "x"})
    assert r.status_code == 400


def test_upload_label_and_count(client):
    client.put("/api/broker-vaults/2", headers={"X-Test-User": "alice"}, json={"name": "Schwab IRA", "broker": "Schwab"})
    r = up(client, 2, TRADES_CSV)
    assert r.status_code == 200 and r.json()["rows"] == 16
    v = client.get("/api/broker-vaults", headers={"X-Test-User": "alice"}).json()["vaults"][1]
    assert v["name"] == "Schwab IRA" and v["statements"] == 1 and v["rows"] == 16


def test_users_cannot_see_each_others_vaults(client):
    up(client, 1, TRADES_CSV, user="alice")
    bob = client.get("/api/broker-vaults", headers={"X-Test-User": "bob"}).json()["vaults"][0]
    assert bob["statements"] == 0
    assert client.get("/api/broker-vaults/1/review", headers={"X-Test-User": "bob"}).status_code == 404
    sid = client.store.list_statements("alice", 1)[0]["statement_id"]
    assert client.delete(f"/api/broker-vaults/statements/{sid}", headers={"X-Test-User": "bob"}).status_code == 404
    assert client.delete(f"/api/broker-vaults/statements/{sid}", headers={"X-Test-User": "alice"}).status_code == 200


def test_bad_uploads_rejected(client):
    assert up(client, 1, "a,b\n1,2\n").status_code == 400                      # no symbol column
    assert up(client, 1, "Symbol,Action,Quantity,Price\nAAPL,Hold,0,0\n").status_code == 400
    assert up(client, 1, TRADES_CSV, kind="bogus").status_code == 400
    assert up(client, 1, "").status_code == 400


def test_review_grades_broker_and_marks_missing_layers(client):
    up(client, 1, TRADES_CSV)
    st = client.store
    review = broker_review.build_review({"slot": 1, "name": "A", "broker": "B"},
                                        st.list_statements("alice", 1, with_rows=True), FakeMarket())
    assert review["behavior"]["graded"] is True
    assert review["behavior"]["overall_grade"] in list("ABCDF")
    assert review["portfolio"]["status"] == "insufficient"       # no positions CSV yet
    assert review["benchmark"]["status"] == "insufficient"
    assert review["fees"]["status"] == "ok"
    r1000 = review["russell_1000"]
    assert r1000["russell_1000_trades"] == 16
    assert r1000["alignment_counts"]["with the setup"] == 8       # the 8 BUYs; SELLs go against a Long setup
    assert r1000["alignment_counts"]["against the setup"] == 8


def test_review_with_positions_unlocks_portfolio_benchmark_and_cash(client):
    up(client, 1, TRADES_CSV)
    up(client, 1, POSITIONS_CSV, kind="positions")
    review = broker_review.build_review({"slot": 1}, client.store.list_statements("alice", 1, with_rows=True), FakeMarket())
    assert review["portfolio"]["status"] == "ok"
    assert review["portfolio_health"]["grade"] in list("ABCDF")
    assert review["benchmark"]["status"] == "ok"
    assert review["benchmark"]["benchmark_return_pct"] == 4.0
    assert review["cash"]["status"] == "ok"


def test_overlapping_statements_do_not_double_count(client):
    up(client, 1, TRADES_CSV)
    up(client, 1, TRADES_CSV)          # same export uploaded twice
    review = broker_review.build_review({"slot": 1}, client.store.list_statements("alice", 1, with_rows=True), FakeMarket())
    assert review["executions"] == 16


def test_compare_grades_each_vault(client):
    up(client, 1, TRADES_CSV)
    r = client.get("/api/broker-vaults/compare", headers={"X-Test-User": "alice"}).json()["vaults"]
    assert r[0]["grade"] in list("ABCDF") and r[1]["grade"] == "N/A"


def test_review_without_market_data_still_works():
    st = vs.MemoryVaultStore()
    sid_rows = [{"date": "2026-03-01", "symbol": "AAPL", "side": "BUY", "quantity": 1, "price": 1, "fees": 0}]
    st.add_statement("u", 1, {"kind": "trades", "rows": sid_rows, "row_count": 1, "filename": "f"})
    r = broker_review.build_review({"slot": 1}, st.list_statements("u", 1, with_rows=True), None)
    assert r["behavior"]["graded"] is False
