# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_review.py
------------------------
Builds the full review for one vault from its stored statements. Market data
is injected (`market`) so the whole review is testable without a network.

`market` must provide:
    benchmark_stats(start: datetime, end: datetime) -> {"return_pct", "max_drawdown_pct"} | None
    point_in_time_readings(trades: list) -> {(symbol, date): reading | None}
    alignment(side, reading) -> str
    parse_date(text) -> datetime | None
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import broker_intelligence as bi
    import broker_portfolio_layers as layers
    from import_history_restore_api import _analyze_trades
except ImportError:  # pragma: no cover - package-style import
    from backend import broker_intelligence as bi
    from backend import broker_portfolio_layers as layers
    from backend.import_history_restore_api import _analyze_trades


def _period(trades: List[Dict[str, Any]], market: Any):
    dates = [d for d in (market.parse_date(t.get("date")) for t in trades) if d]
    return (min(dates), max(dates)) if dates else (None, None)


def build_review(vault: Dict[str, Any], statements: List[Dict[str, Any]], market: Any = None) -> Dict[str, Any]:
    trade_batches = [s.get("rows") or [] for s in statements if s.get("kind") == "trades"]
    position_rows: List[Dict[str, Any]] = []
    # Use the most recent positions statement: holdings are a point-in-time snapshot.
    pos_statements = [s for s in statements if s.get("kind") == "positions"]
    if pos_statements:
        position_rows = pos_statements[-1].get("rows") or []

    executions = bi.merge_executions(trade_batches)
    review: Dict[str, Any] = {
        "vault": {"slot": vault.get("slot"), "name": vault.get("name"), "broker": vault.get("broker")},
        "statements": {"trades": len(trade_batches), "positions": len(pos_statements)},
        "executions": len(executions),
    }

    if not executions:
        review["behavior"] = {"graded": False, "overall_grade": "N/A",
                              "reason": "Upload a transactions (trades) CSV to grade this broker."}
    analysis = _analyze_trades(executions, include_round_trips=True) if executions else {}
    round_trips = analysis.pop("round_trips_all", []) if analysis else []
    if executions:
        review["behavior"] = bi.grade_behavior(analysis)
        review["results"] = {
            k: analysis.get(k) for k in (
                "round_trip_trades", "win_rate", "realized_pnl", "profit_factor", "expectancy_per_trade",
                "average_win", "average_loss", "average_hold_minutes", "max_losing_streak",
                "best_symbols", "worst_symbols", "daily_pnl")
        }

    # Portfolio layers (positions CSV)
    positions = layers.parse_positions(position_rows)
    snapshot = layers.portfolio_snapshot(positions)
    review["portfolio"] = snapshot
    review["portfolio_health"] = layers.portfolio_health(snapshot)

    capital = snapshot.get("total_value") if snapshot.get("status") == "ok" else None
    realized = float(analysis.get("realized_pnl") or 0.0) if analysis else 0.0
    review["fees"] = (layers.fees_analysis(executions, realized, capital) if executions
                      else {"status": "insufficient", "reason": "No transactions uploaded."})
    review["tax_lots"] = layers.tax_lot_mix(round_trips)

    # Benchmark (Russell 1000 proxy) over the trading period
    bench = None
    start, end = _period(executions, market) if (market and executions) else (None, None)
    if market and start and end and end > start:
        bench = market.benchmark_stats(start, end)
    fees_total = review["fees"].get("total_fees", 0.0) if review["fees"].get("status") == "ok" else 0.0
    review["benchmark"] = layers.benchmark_comparison(
        realized, capital, bench["return_pct"] if bench else None, fees_total,
        analysis.get("daily_pnl") if analysis else None,
        bench["max_drawdown_pct"] if bench else None)
    review["cash"] = layers.cash_analysis(snapshot, bench["return_pct"] if bench else None)

    # Russell 1000: every buy/sell of an index symbol, read as of the trade date
    readings: Dict[Any, Any] = {}
    reasons: Dict[Any, str] = {}   # (symbol, date) -> why that trade could not be read
    if market and executions:
        in_index = [e for e in executions
                    if str(e.get("symbol", "")).upper() in layers.load_russell_map()
                    and str(e.get("side", "")).upper() in ("BUY", "SELL")]
        readings = market.point_in_time_readings(in_index) if in_index else {}
        if in_index:
            # Optional on the injected market object (older fakes do not provide it).
            reasons = getattr(market, "last_reading_reasons", lambda: {})()

    def reading_fn(sym: str, date: str):
        return readings.get((sym, date))

    tagged = layers.tag_russell_1000(executions, reading_fn=reading_fn if readings else None)
    if tagged.get("status") == "ok" and market:
        counts = {"with the setup": 0, "against the setup": 0, "no confirmed setup": 0, "not read": 0}
        for row in tagged["trades"]:
            r = row.get("sigmalytic_reading")
            if r is None:
                counts["not read"] += 1
                row["alignment"] = "not read"
                why = reasons.get((row["symbol"], str(row.get("date"))))
                if why:
                    row["reading_reason"] = why
                continue
            row["alignment"] = market.alignment(row["side"], r)
            counts[row["alignment"]] += 1
        tagged["alignment_counts"] = counts
        tagged["trades"] = tagged["trades"][-60:]
    review["russell_1000"] = tagged
    return review
