"""Tests for backend/broker_portfolio_layers.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import broker_portfolio_layers as L

RUSSELL = {
    "AAPL": {"name": "Apple", "sector": "Information Technology", "industry": "Hardware"},
    "MSFT": {"name": "Microsoft", "sector": "Information Technology", "industry": "Software"},
    "JPM": {"name": "JPM", "sector": "Financials", "industry": "Banks"},
}


def test_real_russell_file_loads_with_sectors():
    m = L.load_russell_map()
    assert len(m) > 900
    assert m["AAPL"]["sector"] == "Information Technology"


def test_tag_marks_only_index_symbols_and_counts_outside():
    ex = [
        {"symbol": "AAPL", "side": "BUY", "date": "2026-01-02", "price": 1, "quantity": 1},
        {"symbol": "ZZZZ", "side": "SELL", "date": "2026-01-03", "price": 1, "quantity": 1},
    ]
    r = L.tag_russell_1000(ex, RUSSELL)
    assert r["russell_1000_trades"] == 1 and r["outside_index"] == 1
    assert r["trades"][0]["sector"] == "Information Technology"


def test_tag_uses_point_in_time_reading_when_given():
    ex = [{"symbol": "AAPL", "side": "BUY", "date": "2026-01-02", "price": 1, "quantity": 1}]
    seen = []
    r = L.tag_russell_1000(ex, RUSSELL, reading_fn=lambda s, d: seen.append((s, d)) or {"bias": "up"})
    assert seen == [("AAPL", "2026-01-02")]
    assert r["trades"][0]["sigmalytic_reading"] == {"bias": "up"}


def test_tag_survives_a_failing_reading():
    def boom(s, d): raise RuntimeError("no data")
    ex = [{"symbol": "AAPL", "side": "BUY", "date": "d", "price": 1, "quantity": 1}]
    r = L.tag_russell_1000(ex, RUSSELL, reading_fn=boom)
    assert r["status"] == "ok" and r["trades"][0]["sigmalytic_reading"] is None


def test_fees_insufficient_without_fee_column():
    ex = [{"symbol": "A", "side": "BUY", "quantity": 1, "price": 10, "fees": 0}]
    assert L.fees_analysis(ex, 5)["status"] == "insufficient"


def test_fees_measured():
    ex = [{"symbol": "A", "side": "BUY", "quantity": 10, "price": 10, "fees": 1},
          {"symbol": "A", "side": "SELL", "quantity": 10, "price": 12, "fees": 1}]
    r = L.fees_analysis(ex, realized_pnl=18, capital_base=1000)
    assert r["total_fees"] == 2 and r["gross_pnl_before_fees"] == 20
    assert r["gross_return_per_dollar_of_cost"] == 10.0
    assert r["total_cost_pct_of_assets"] == 0.2


def test_tax_lot_mix_splits_at_one_year():
    trips = [{"entry_time": "2024-01-01T10:00:00", "exit_time": "2026-01-01T10:00:00", "pnl": 300},
             {"entry_time": "2026-01-01T10:00:00", "exit_time": "2026-02-01T10:00:00", "pnl": 100}]
    r = L.tax_lot_mix(trips)
    assert r["long_term_pnl"] == 300 and r["short_term_pnl"] == 100
    assert r["long_term_share_of_gains"] == 0.75
    assert L.tax_lot_mix([])["status"] == "insufficient"


def _positions():
    return L.parse_positions([
        {"Symbol": "AAPL", "Quantity": "10", "Price": "100", "Cost Basis": "800"},
        {"Symbol": "MSFT", "Quantity": "10", "Price": "100", "Cost Basis": "900"},
        {"Symbol": "JPM", "Quantity": "10", "Price": "100", "Cost Basis": "1100"},
        {"Symbol": "Cash", "Market Value": "1000"},
    ])


def test_snapshot_values_cash_and_sectors():
    s = L.portfolio_snapshot(_positions(), RUSSELL)
    assert s["total_value"] == 4000 and s["cash_pct"] == 0.25
    assert s["holdings"] == 3
    assert s["largest_sector"] == "Information Technology"
    assert s["russell_1000_weight"] == 0.75
    assert s["unrealized_pnl"] == 200


def test_snapshot_without_positions_is_insufficient():
    assert L.portfolio_snapshot([], RUSSELL)["status"] == "insufficient"


def test_health_penalizes_concentration():
    spread = [{"symbol": f"S{i}", "quantity": 1, "market_value": 100, "cost_basis": 0, "is_cash": False} for i in range(20)]
    conc = [{"symbol": "AAPL", "quantity": 1, "market_value": 900, "cost_basis": 0, "is_cash": False},
            {"symbol": "MSFT", "quantity": 1, "market_value": 100, "cost_basis": 0, "is_cash": False}]
    good = L.portfolio_health(L.portfolio_snapshot(spread, {}))
    bad = L.portfolio_health(L.portfolio_snapshot(conc, RUSSELL))
    assert good["score"] > bad["score"]
    assert good["grade"] in "AB" and bad["grade"] in "DF"


def test_cash_protective_vs_unproductive():
    s = L.portfolio_snapshot(_positions(), RUSSELL)
    up = L.cash_analysis(s, 10.0)
    down = L.cash_analysis(s, -10.0)
    assert up["cash_kind"] == "unproductive" and up["estimated_effect_pct_of_account"] == -2.5
    assert down["cash_kind"] == "protective" and down["estimated_effect_pct_of_account"] == 2.5
    assert L.cash_analysis(s, None)["status"] == "insufficient"


def test_benchmark_needs_base_and_prices():
    assert L.benchmark_comparison(100, None, 5)["status"] == "insufficient"
    assert L.benchmark_comparison(100, 1000, None)["status"] == "insufficient"


def test_benchmark_value_added_and_drawdown():
    r = L.benchmark_comparison(80, 1000, 10.8, fees_total=8, daily_pnl={"d1": 50, "d2": -100, "d3": 130})
    assert r["account_return_pct"] == 8.0 and r["value_added_pct"] == -2.8
    assert r["verdict"] == "did not beat the benchmark"
    assert r["fees_effect_pct"] == -0.8
    assert r["max_drawdown_pct"] == round(-100 / 1050 * 100, 2)
