# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/broker_portfolio_layers.py
----------------------------------
The second layer of Broker Behavioural Intelligence: portfolio health,
fees, cash, tax-lot mix, benchmark comparison and the Russell 1000 tag.

Every function returns {"status": "ok", ...} or
{"status": "insufficient", "reason": "..."}; none of them guesses. A trades
CSV cannot show cash or what is held today, so those sections need a
positions CSV; the benchmark needs prices, which the caller injects.
Pure functions: no network, no database.
"""
from __future__ import annotations

import csv
import math
import os
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from broker_intelligence import letter_from_score
except ImportError:  # pragma: no cover - package-style import
    from backend.broker_intelligence import letter_from_score

_DATA = os.path.join(os.path.dirname(__file__), "data")
_R1000_PATH = os.path.join(_DATA, "russell1000_sector_industry.csv")
BENCHMARK_SYMBOL = "IWB"          # iShares Russell 1000 ETF: the Russell 1000 proxy
CASH_NAMES = {"CASH", "USD", "CASH&CASHINVESTMENTS", "CASHANDCASHINVESTMENTS", "MONEYMARKET", "SWEEP"}

_R1000_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def _insufficient(reason: str) -> Dict[str, Any]:
    return {"status": "insufficient", "reason": reason}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        v = float(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
        return default if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Russell 1000
# ---------------------------------------------------------------------------

def load_russell_map() -> Dict[str, Dict[str, str]]:
    global _R1000_CACHE
    if _R1000_CACHE is None:
        out: Dict[str, Dict[str, str]] = {}
        try:
            with open(_R1000_PATH, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    t = (row.get("ticker") or "").strip().upper()
                    if t:
                        out[t] = {
                            "name": row.get("name", ""),
                            "sector": row.get("sector", ""),
                            "industry": row.get("industry", ""),
                        }
        except OSError:
            pass
        _R1000_CACHE = out
    return _R1000_CACHE


def tag_russell_1000(
    executions: Iterable[Dict[str, Any]],
    russell: Optional[Dict[str, Dict[str, str]]] = None,
    reading_fn: Optional[Callable[[str, str], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Mark every buy/sell whose symbol is in the Russell 1000, with sector and
    industry. `reading_fn(symbol, date)` may return Sigmalytic's read of that
    symbol as of the trade date (point-in-time, no hindsight); it is injected
    so this module stays free of network calls.
    """
    russell = load_russell_map() if russell is None else russell
    rows: List[Dict[str, Any]] = []
    total = 0
    for ex in executions:
        sym = str(ex.get("symbol") or "").upper()
        side = str(ex.get("side") or "").upper()
        if side not in ("BUY", "SELL") or not sym:
            continue
        total += 1
        meta = russell.get(sym)
        if not meta:
            continue
        row = {
            "symbol": sym, "side": side, "date": ex.get("date"),
            "price": ex.get("price"), "quantity": ex.get("quantity"),
            "sector": meta["sector"], "industry": meta["industry"],
        }
        if reading_fn is not None:
            try:
                row["sigmalytic_reading"] = reading_fn(sym, str(ex.get("date")))
            except Exception:  # a failed lookup must not sink the whole review
                row["sigmalytic_reading"] = None
        rows.append(row)
    if total == 0:
        return _insufficient("No buy or sell rows found.")
    return {
        "status": "ok",
        "russell_1000_trades": len(rows),
        "all_trades": total,
        "share_of_trades": round(len(rows) / total, 4),
        "trades": rows,
        "outside_index": total - len(rows),
    }


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------

def fees_analysis(executions: List[Dict[str, Any]], realized_pnl: float,
                  capital_base: Optional[float] = None) -> Dict[str, Any]:
    fills = [e for e in executions if str(e.get("side", "")).upper() in ("BUY", "SELL")]
    if not fills:
        return _insufficient("No buy or sell rows found.")
    fees = sum(abs(_f(e.get("fees"))) for e in fills)
    if fees <= 0:
        return _insufficient("The statements show no commission or fee column, so costs cannot be measured.")
    notional = sum(abs(_f(e.get("quantity")) * _f(e.get("price"))) for e in fills)
    gross = realized_pnl + fees
    out = {
        "status": "ok",
        "total_fees": round(fees, 2),
        "fees_per_trade": round(fees / len(fills), 2),
        "fees_pct_of_traded_value": round(fees / notional * 100, 4) if notional else None,
        "gross_pnl_before_fees": round(gross, 2),
        "net_pnl_after_fees": round(realized_pnl, 2),
        "gross_return_per_dollar_of_cost": round(gross / fees, 2),
        "fees_consumed_pct_of_gross_profit": round(fees / gross * 100, 1) if gross > 0 else None,
    }
    if capital_base and capital_base > 0:
        out["total_cost_pct_of_assets"] = round(fees / capital_base * 100, 4)
    return out


# ---------------------------------------------------------------------------
# Tax-lot mix
# ---------------------------------------------------------------------------

def tax_lot_mix(round_trips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Short-term (held a year or less) versus long-term share of realized gains."""
    def parse(s):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(str(s)[:19], fmt)
            except ValueError:
                continue
        return None

    short_gain = long_gain = 0.0
    dated = 0
    for t in round_trips:
        a, b = parse(t.get("entry_time") or t.get("entry_date")), parse(t.get("exit_time") or t.get("exit_date"))
        if not a or not b:
            continue
        dated += 1
        pnl = _f(t.get("pnl"))
        if (b - a).days > 365:
            long_gain += pnl
        else:
            short_gain += pnl
    if dated == 0:
        return _insufficient("Entry and exit dates are needed to split short-term from long-term results.")
    total_pos = max(short_gain, 0) + max(long_gain, 0)
    return {
        "status": "ok",
        "short_term_pnl": round(short_gain, 2),
        "long_term_pnl": round(long_gain, 2),
        "long_term_share_of_gains": round(max(long_gain, 0) / total_pos, 4) if total_pos else None,
        "note": "Mix only. Actual tax depends on account type and each lot's cost basis.",
    }


# ---------------------------------------------------------------------------
# Positions: snapshot, concentration, cash, health grade
# ---------------------------------------------------------------------------

def parse_positions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize rows of a positions/holdings CSV (already keyed by column name)."""
    def pick(row, names):
        keys = {"".join(c for c in k.lower() if c.isalnum()): k for k in row}
        for n in names:
            if n in keys:
                return row[keys[n]]
        return None

    out = []
    for r in rows:
        sym = str(pick(r, ["symbol", "ticker", "security", "description"]) or "").strip().upper()
        if not sym:
            continue
        qty = _f(pick(r, ["quantity", "qty", "shares"]))
        price = _f(pick(r, ["price", "lastprice", "currentprice", "marketprice"]))
        value = _f(pick(r, ["marketvalue", "value", "currentvalue", "totalvalue"]))
        if value == 0 and qty and price:
            value = qty * price
        cost = _f(pick(r, ["costbasis", "totalcost", "cost"]))
        out.append({"symbol": sym, "quantity": qty, "market_value": value, "cost_basis": cost,
                    "is_cash": "".join(c for c in sym if c.isalnum()) in CASH_NAMES})
    return out


def portfolio_snapshot(positions: List[Dict[str, Any]],
                       russell: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
    if not positions:
        return _insufficient("Add a positions or holdings CSV to see what the account holds.")
    russell = load_russell_map() if russell is None else russell
    cash = sum(p["market_value"] for p in positions if p["is_cash"])
    held = [p for p in positions if not p["is_cash"] and p["market_value"] > 0]
    invested = sum(p["market_value"] for p in held)
    total = invested + cash
    if total <= 0 or not held:
        return _insufficient("The positions file shows no invested value.")

    weights = sorted(((p["symbol"], p["market_value"] / total) for p in held), key=lambda x: -x[1])
    hhi = sum((p["market_value"] / invested) ** 2 for p in held)
    sectors: Dict[str, float] = {}
    for p in held:
        sec = (russell.get(p["symbol"]) or {}).get("sector") or "Not in Russell 1000 / unclassified"
        sectors[sec] = sectors.get(sec, 0.0) + p["market_value"] / total
    cost = sum(p["cost_basis"] for p in held if p["cost_basis"] > 0)
    unreal = (invested - cost) if cost > 0 else None
    top5 = sum(w for _, w in weights[:5])
    return {
        "status": "ok",
        "total_value": round(total, 2),
        "cash": round(cash, 2),
        "cash_pct": round(cash / total, 4),
        "invested": round(invested, 2),
        "holdings": len(held),
        "effective_holdings": round(1.0 / hhi, 1) if hhi else None,
        "largest_positions": [{"symbol": s, "weight": round(w, 4)} for s, w in weights[:5]],
        "top5_weight": round(top5, 4),
        "sector_weights": {k: round(v, 4) for k, v in sorted(sectors.items(), key=lambda kv: -kv[1])},
        "largest_sector": max(sectors.items(), key=lambda kv: kv[1])[0] if sectors else None,
        "unrealized_pnl": round(unreal, 2) if unreal is not None else None,
        "russell_1000_weight": round(sum(w for s, w in weights if s in russell), 4),
    }


def portfolio_health(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if snapshot.get("status") != "ok":
        return _insufficient(snapshot.get("reason", "No portfolio snapshot."))
    score = 100.0
    basis: List[str] = []
    n, eff = snapshot["holdings"], snapshot["effective_holdings"] or 0
    if n >= 2 and eff < n * 0.6:
        score -= min(25.0, (n * 0.6 - eff) / max(n, 1) * 60)
    basis.append(f"{n} holdings behave like about {eff:.0f} independent positions")
    top5 = snapshot["top5_weight"]
    if top5 > 0.5:
        score -= min(25.0, (top5 - 0.5) * 80)
    basis.append(f"Top five positions are {top5 * 100:.0f}% of the account")
    sec_top = max(snapshot["sector_weights"].values()) if snapshot["sector_weights"] else 0
    if sec_top > 0.4:
        score -= min(20.0, (sec_top - 0.4) * 60)
    basis.append(f"Largest sector ({snapshot['largest_sector']}) is {sec_top * 100:.0f}% of the account")
    cash = snapshot["cash_pct"]
    if cash > 0.2:
        score -= min(15.0, (cash - 0.2) * 50)
    basis.append(f"Cash is {cash * 100:.0f}% of the account")
    if n < 8:
        score -= (8 - n) * 3
        basis.append("Fewer than 8 holdings")
    score = round(max(0.0, min(100.0, score)), 1)
    return {"status": "ok", "score": score, "grade": letter_from_score(score), "basis": basis}


def cash_analysis(snapshot: Dict[str, Any], benchmark_return_pct: Optional[float]) -> Dict[str, Any]:
    """Cash is a position: protective when the market fell, unproductive when it rose."""
    if snapshot.get("status") != "ok":
        return _insufficient(snapshot.get("reason", "No portfolio snapshot."))
    if benchmark_return_pct is None:
        return _insufficient("A benchmark return for the statement period is needed to judge cash.")
    pct = snapshot["cash_pct"]
    effect = pct * benchmark_return_pct   # return in account-percent that cash gave up (or avoided)
    kind = "unproductive" if benchmark_return_pct > 0 else "protective"
    return {
        "status": "ok",
        "cash_pct": pct,
        "benchmark_return_pct": round(benchmark_return_pct, 2),
        "cash_kind": kind,
        "estimated_effect_pct_of_account": round(-effect, 2),
        "reading": (
            f"Cash was {pct * 100:.0f}% of the account while the Russell 1000 proxy moved "
            f"{benchmark_return_pct:+.1f}%: this cash was {kind}, "
            f"worth about {abs(effect):.1f}% of the account "
            f"{'given up' if kind == 'unproductive' else 'protected'}."
        ),
    }


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def max_drawdown_pct(daily_pnl: Dict[str, float], capital_base: float) -> Optional[float]:
    if not daily_pnl or capital_base <= 0:
        return None
    equity, peak, worst = capital_base, capital_base, 0.0
    for day in sorted(daily_pnl):
        equity += daily_pnl[day]
        peak = max(peak, equity)
        worst = min(worst, (equity - peak) / peak * 100)
    return round(worst, 2)


def benchmark_comparison(
    realized_pnl: float,
    capital_base: Optional[float],
    benchmark_return_pct: Optional[float],
    fees_total: float = 0.0,
    daily_pnl: Optional[Dict[str, float]] = None,
    benchmark_drawdown_pct: Optional[float] = None,
) -> Dict[str, Any]:
    if not capital_base or capital_base <= 0:
        return _insufficient("A positions file (or account value) is needed to turn profit into a return.")
    if benchmark_return_pct is None:
        return _insufficient("Benchmark prices for the statement period were not available.")
    ret = realized_pnl / capital_base * 100
    gross_ret = (realized_pnl + fees_total) / capital_base * 100
    value_added = ret - benchmark_return_pct
    out = {
        "status": "ok",
        "benchmark": f"Russell 1000 ({BENCHMARK_SYMBOL})",
        "account_return_pct": round(ret, 2),
        "return_before_fees_pct": round(gross_ret, 2),
        "benchmark_return_pct": round(benchmark_return_pct, 2),
        "value_added_pct": round(value_added, 2),
        "fees_effect_pct": round(-(fees_total / capital_base * 100), 2),
        "max_drawdown_pct": max_drawdown_pct(daily_pnl or {}, capital_base),
        "benchmark_max_drawdown_pct": benchmark_drawdown_pct,
        "verdict": "added value" if value_added > 0 else "did not beat the benchmark",
    }
    out["reading"] = (
        f"The account returned {ret:+.1f}% after fees against {benchmark_return_pct:+.1f}% for the Russell 1000 "
        f"proxy over the same period: {abs(value_added):.1f} points "
        f"{'ahead' if value_added > 0 else 'behind'}."
    )
    return out
