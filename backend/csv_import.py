"""
SigmAlytic — Brokerage CSV Import Engine
Supports: Alpaca, TD Ameritrade/Schwab, Interactive Brokers,
          Robinhood, Webull, Generic CSV (with column mapper)

Attach to FastAPI via: app.include_router(csv_router)
"""

from __future__ import annotations
import io
import uuid
import json
import re
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import behavior DB helpers
from behavior import get_db, update_regime_memory, calculate_timing_score, \
    calculate_discipline_score, calculate_risk_score, calculate_setup_quality, \
    calculate_execution_quality, calculate_composite, determine_behavior_flag

csv_router = APIRouter(prefix="/api/import", tags=["import"])

USER_ID = "demo_user_001"

# ── Broker format signatures ───────────────────────────────────────────────────
# Each broker has a unique set of column names we detect to identify the format.

BROKER_SIGNATURES = {
    "alpaca": {
        "required": ["symbol", "side", "qty", "filled_avg_price"],
        "optional": ["filled_at", "created_at", "order_type"],
        "name": "Alpaca",
    },
    "tdameritrade": {
        "required": ["symbol", "quantity", "price", "action"],
        "optional": ["date", "description", "amount", "commission"],
        "name": "TD Ameritrade / Schwab",
    },
    "schwab": {
        "required": ["symbol", "quantity", "price", "action"],
        "optional": ["date", "description", "fees & comm"],
        "name": "Schwab",
    },
    "ibkr": {
        "required": ["symbol", "quantity", "t. price", "proceeds"],
        "optional": ["date/time", "comm/fee", "realized p/l", "asset category"],
        "name": "Interactive Brokers",
    },
    "robinhood": {
        "required": ["symbol", "quantity", "average price", "side"],
        "optional": ["activity date", "process date", "instrument", "description", "amount"],
        "name": "Robinhood",
    },
    "webull": {
        "required": ["ticker", "side", "filled qty", "avg price"],
        "optional": ["filled time", "order type", "commission"],
        "name": "Webull",
    },
}

# ── Column normalizers ─────────────────────────────────────────────────────────
# Maps each broker's columns to our internal schema:
# symbol, side, qty, price, timestamp, commission, order_type

COLUMN_MAPS = {
    "alpaca": {
        "symbol":     "symbol",
        "side":       "side",
        "qty":        "qty",
        "filled_avg_price": "price",
        "filled_at":  "timestamp",
        "created_at": "timestamp",
        "commission": "commission",
        "order_type": "order_type",
    },
    "tdameritrade": {
        "symbol":     "symbol",
        "action":     "side",
        "quantity":   "qty",
        "price":      "price",
        "date":       "timestamp",
        "commission": "commission",
        "amount":     "amount",
    },
    "schwab": {
        "symbol":     "symbol",
        "action":     "side",
        "quantity":   "qty",
        "price":      "price",
        "date":       "timestamp",
        "fees & comm":"commission",
    },
    "ibkr": {
        "symbol":     "symbol",
        "quantity":   "qty",
        "t. price":   "price",
        "date/time":  "timestamp",
        "comm/fee":   "commission",
        "realized p/l": "realized_pnl",
    },
    "robinhood": {
        "symbol":     "symbol",
        "instrument": "symbol",
        "side":       "side",
        "quantity":   "qty",
        "average price": "price",
        "activity date": "timestamp",
        "amount":     "amount",
    },
    "webull": {
        "ticker":     "symbol",
        "side":       "side",
        "filled qty": "qty",
        "avg price":  "price",
        "filled time":"timestamp",
        "commission": "commission",
    },
}

# Side normalization — map broker-specific terms to buy/sell
SIDE_MAP = {
    "buy": "buy", "sell": "sell",
    "b": "buy", "s": "sell",
    "bought": "buy", "sold": "sell",
    "buy to open": "buy", "buy to close": "buy",
    "sell to open": "sell", "sell to close": "sell",
    "purchase": "buy", "redemption": "sell",
    "reinvestment": "buy",
    "long": "buy", "short": "sell",
}


# ── Format detection ───────────────────────────────────────────────────────────

def detect_broker(df: pd.DataFrame) -> str:
    """Identify broker from column names. Returns broker key or 'generic'."""
    cols_lower = set(c.lower().strip() for c in df.columns)

    scores = {}
    for broker, sig in BROKER_SIGNATURES.items():
        required_hits = sum(1 for r in sig["required"] if r in cols_lower)
        optional_hits = sum(1 for o in sig["optional"] if o in cols_lower)
        if required_hits == len(sig["required"]):
            scores[broker] = required_hits * 10 + optional_hits
        elif required_hits >= len(sig["required"]) - 1:
            scores[broker] = required_hits * 5 + optional_hits

    return max(scores, key=scores.get) if scores else "generic"


def normalize_columns(df: pd.DataFrame, broker: str) -> pd.DataFrame:
    """Rename broker-specific columns to our internal schema."""
    col_map = COLUMN_MAPS.get(broker, {})
    # Lowercase and strip all column names first
    df.columns = [c.lower().strip() for c in df.columns]
    # Apply rename
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)
    return df


def clean_price(val) -> Optional[float]:
    """Convert '$1,234.56' or '(234.56)' to float."""
    if pd.isna(val):
        return None
    s = str(val).strip().replace("$", "").replace(",", "").replace(" ", "")
    # Parentheses = negative
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def clean_qty(val) -> Optional[float]:
    if pd.isna(val):
        return None
    s = str(val).strip().replace(",", "")
    # IBKR uses negative qty for sells
    try:
        return abs(float(s)), float(s) < 0  # (qty, is_sell)
    except ValueError:
        return None, None


def normalize_side(val, qty_negative: bool = False) -> str:
    if qty_negative:
        return "sell"
    if pd.isna(val):
        return "buy"
    return SIDE_MAP.get(str(val).lower().strip(), "buy")


def parse_timestamp(val) -> Optional[datetime]:
    if pd.isna(val):
        return None
    s = str(val).strip()
    formats = [
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y",
        "%m/%d/%y", "%Y%m%d  %H%M%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ── Trade reconstruction (FIFO matching) ──────────────────────────────────────

def reconstruct_trades(rows: list[dict]) -> list[dict]:
    """
    Match buy executions to sell executions using FIFO per symbol.
    Returns list of completed trade dicts with entry/exit/pnl.
    """
    # Group by symbol
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    trades = []
    open_positions = []  # Track open (unmatched) buys

    for symbol, execs in by_symbol.items():
        # Sort by timestamp
        execs.sort(key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))

        buy_queue  = []  # FIFO queue of open buys
        sell_queue = []

        for ex in execs:
            side = ex.get("side", "buy")
            qty  = ex.get("qty", 0)
            price= ex.get("price", 0)
            ts   = ex.get("timestamp")

            if side == "buy":
                buy_queue.append({"qty": qty, "price": price, "ts": ts})
            elif side == "sell":
                remaining_sell = qty
                while remaining_sell > 0 and buy_queue:
                    buy = buy_queue[0]
                    matched_qty = min(buy["qty"], remaining_sell)

                    entry_price = buy["price"]
                    exit_price  = price
                    pnl         = (exit_price - entry_price) * matched_qty
                    pnl_pct     = ((exit_price - entry_price) / entry_price * 100
                                   if entry_price else 0)

                    trades.append({
                        "symbol":       symbol,
                        "direction":    "long",
                        "entry_price":  round(entry_price, 4),
                        "exit_price":   round(exit_price, 4),
                        "size":         matched_qty,
                        "entry_time":   buy["ts"].isoformat() if buy["ts"] else None,
                        "exit_time":    ts.isoformat() if ts else None,
                        "pnl":          round(pnl, 2),
                        "pnl_percent":  round(pnl_pct, 2),
                        "status":       "closed",
                        "source":       "csv_import",
                    })

                    buy["qty"] -= matched_qty
                    remaining_sell -= matched_qty
                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

        # Any remaining buys are open positions
        for b in buy_queue:
            if b["qty"] > 0:
                open_positions.append({
                    "symbol":      symbol,
                    "direction":   "long",
                    "entry_price": b["price"],
                    "size":        b["qty"],
                    "entry_time":  b["ts"].isoformat() if b["ts"] else None,
                    "status":      "open",
                    "source":      "csv_import",
                })

    return trades, open_positions


# ── Behavioral analysis ────────────────────────────────────────────────────────

def analyze_behavior(trades: list[dict]) -> dict:
    """
    Derive behavioral metrics from historical trade records.
    Returns a behavioral snapshot dict.
    """
    if not trades:
        return {}

    closed = [t for t in trades if t["status"] == "closed"]
    if not closed:
        return {}

    total       = len(closed)
    winners     = [t for t in closed if t["pnl"] > 0]
    losers      = [t for t in closed if t["pnl"] <= 0]
    win_rate    = round(len(winners) / total * 100, 1)

    avg_win     = round(sum(t["pnl"] for t in winners) / len(winners), 2) if winners else 0
    avg_loss    = round(sum(t["pnl"] for t in losers)  / len(losers),  2) if losers  else 0
    total_pnl   = round(sum(t["pnl"] for t in closed), 2)

    # Risk/reward reality
    rr_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

    # Holding time analysis
    holding_times = []
    for t in closed:
        if t.get("entry_time") and t.get("exit_time"):
            try:
                entry = datetime.fromisoformat(t["entry_time"])
                exit_ = datetime.fromisoformat(t["exit_time"])
                holding_times.append((exit_ - entry).total_seconds())
            except Exception:
                pass
    avg_hold_secs = sum(holding_times) / len(holding_times) if holding_times else 0
    avg_hold_human = _human_duration(avg_hold_secs)

    # Win/loss streaks
    max_win_streak = max_loss_streak = curr_win = curr_loss = 0
    for t in closed:
        if t["pnl"] > 0:
            curr_win += 1; curr_loss = 0
            max_win_streak = max(max_win_streak, curr_win)
        else:
            curr_loss += 1; curr_win = 0
            max_loss_streak = max(max_loss_streak, curr_loss)

    # Symbol performance
    by_symbol = defaultdict(list)
    for t in closed:
        by_symbol[t["symbol"]].append(t)
    symbol_perf = {}
    for sym, ts in by_symbol.items():
        w = [t for t in ts if t["pnl"] > 0]
        symbol_perf[sym] = {
            "trades":   len(ts),
            "win_rate": round(len(w) / len(ts) * 100, 1),
            "total_pnl":round(sum(t["pnl"] for t in ts), 2),
        }
    best_symbol  = max(symbol_perf, key=lambda s: symbol_perf[s]["total_pnl"]) if symbol_perf else None
    worst_symbol = min(symbol_perf, key=lambda s: symbol_perf[s]["total_pnl"]) if symbol_perf else None

    # Day of week performance
    dow_perf = defaultdict(lambda: {"trades":0,"wins":0,"pnl":0})
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    for t in closed:
        if t.get("entry_time"):
            try:
                dt = datetime.fromisoformat(t["entry_time"])
                day = days[dt.weekday()]
                dow_perf[day]["trades"] += 1
                dow_perf[day]["pnl"]    += t["pnl"]
                if t["pnl"] > 0:
                    dow_perf[day]["wins"] += 1
            except Exception:
                pass
    best_day  = max(dow_perf, key=lambda d: dow_perf[d]["pnl"]) if dow_perf else None
    worst_day = min(dow_perf, key=lambda d: dow_perf[d]["pnl"]) if dow_perf else None

    # Overtrading detection — days with > 3 trades
    trades_per_day = defaultdict(int)
    for t in closed:
        if t.get("entry_time"):
            try:
                dt  = datetime.fromisoformat(t["entry_time"])
                key = dt.strftime("%Y-%m-%d")
                trades_per_day[key] += 1
            except Exception:
                pass
    overtrade_days  = sum(1 for v in trades_per_day.values() if v > 3)
    overtrade_rate  = round(overtrade_days / len(trades_per_day) * 100, 1) if trades_per_day else 0

    # Behavioral flags
    flags = []
    if win_rate < 40:
        flags.append("Low win rate — review entry criteria")
    if rr_ratio < 1.0 and win_rate < 60:
        flags.append("Risk/reward unfavorable — average loss exceeds average win")
    if avg_hold_secs < 300 and total > 20:
        flags.append("Very short hold times — potential overtrading or scalping pattern")
    if overtrade_rate > 30:
        flags.append(f"Overtrading detected — {overtrade_rate}% of trading days had 4+ trades")
    if max_loss_streak >= 5:
        flags.append(f"Max losing streak of {max_loss_streak} — review risk management")
    if rr_ratio > 1.5 and win_rate > 50:
        flags.append("Strong risk/reward discipline — maintain this edge")
    if win_rate > 60 and total > 30:
        flags.append("Above-average win rate — system has statistical edge")

    # Mathematical edge score
    edge_score = round(
        (win_rate / 100) * avg_win +
        (1 - win_rate / 100) * avg_loss,
        2
    ) if avg_win and avg_loss else 0

    return {
        "total_trades":    total,
        "win_rate":        win_rate,
        "total_pnl":       total_pnl,
        "avg_win":         avg_win,
        "avg_loss":        avg_loss,
        "rr_ratio":        rr_ratio,
        "edge_score":      edge_score,
        "avg_hold_time":   avg_hold_human,
        "max_win_streak":  max_win_streak,
        "max_loss_streak": max_loss_streak,
        "best_symbol":     best_symbol,
        "worst_symbol":    worst_symbol,
        "best_day":        best_day,
        "worst_day":       worst_day,
        "overtrade_rate":  overtrade_rate,
        "symbol_performance": dict(symbol_perf),
        "day_performance":    {k: dict(v) for k, v in dow_perf.items()},
        "behavioral_flags":   flags,
    }


def _human_duration(secs: float) -> str:
    if secs < 60:       return f"{int(secs)}s"
    if secs < 3600:     return f"{int(secs//60)}m"
    if secs < 86400:    return f"{int(secs//3600)}h {int((secs%3600)//60)}m"
    return f"{int(secs//86400)}d {int((secs%86400)//3600)}h"


# ── Persist to behavior DB ────────────────────────────────────────────────────

def persist_trades(trades: list[dict], user_id: str, analysis: dict):
    """Write reconstructed trades and initial scorecards to the behavior DB."""
    con = get_db()

    for t in trades:
        trade_id = "trade_" + uuid.uuid4().hex[:12]
        t["trade_id"] = trade_id

        # Insert trade
        con.execute("""
            INSERT OR IGNORE INTO trades
            (trade_id, user_id, symbol, direction, entry_price, exit_price,
             size, entry_time, exit_time, pnl, pnl_percent,
             market_regime_entry, signal_score_entry, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'neutral',50,?)
        """, (
            trade_id, user_id,
            t.get("symbol",""), t.get("direction","long"),
            t.get("entry_price",0), t.get("exit_price",0),
            t.get("size",0),
            t.get("entry_time"), t.get("exit_time"),
            t.get("pnl",0), t.get("pnl_percent",0),
            t.get("status","closed"),
        ))

        if t.get("status") == "closed":
            # Generate a basic scorecard from what we know
            # We don't have signal price so use entry as proxy
            timing    = 85.0  # assume reasonable — no signal price to compare
            discipline= 80.0  # assume — no plan data from CSV
            risk      = calculate_risk_score(None, t["entry_price"], None,
                                             t["size"], t["direction"])
            setup     = 60.0  # neutral — no confluence data
            execution = calculate_execution_quality(timing, discipline, risk)
            composite = calculate_composite(setup, execution, discipline, risk)
            flag      = "plan_followed" if t["pnl_percent"] > 0 else "neutral"

            sc_id = "sc_" + uuid.uuid4().hex[:12]
            con.execute("""
                INSERT OR IGNORE INTO decision_scorecards
                (scorecard_id, user_id, trade_id, symbol,
                 setup_quality_score, execution_quality_score, discipline_score,
                 timing_score, risk_management_score, confidence_calibration_score,
                 composite_decision_score, primary_behavior_flag, notes, timestamp)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                sc_id, user_id, trade_id, t["symbol"],
                round(setup,1), round(execution,1), round(discipline,1),
                round(timing,1), round(risk,1), round(discipline,1),
                round(composite,1), flag,
                "Imported from brokerage CSV",
                t.get("exit_time") or datetime.now(timezone.utc).isoformat(),
            ))

            # Update regime memory
            update_regime_memory(
                con, user_id, "neutral", t["symbol"],
                t.get("pnl_percent", 0), 60.0, flag
            )

    # Store analysis snapshot as behavioral event
    con.execute("""
        INSERT INTO behavioral_events
        (event_id, user_id, event_type, symbol, timestamp, metadata)
        VALUES (?,?,'csv_imported','PORTFOLIO',datetime('now'),?)
    """, ("evt_" + uuid.uuid4().hex[:12], user_id, json.dumps(analysis)))

    con.commit()
    con.close()


# ── API Endpoints ─────────────────────────────────────────────────────────────

@csv_router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Upload a brokerage CSV.
    Returns detected broker, parsed trade count, and behavioral analysis.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    contents = await file.read()

    try:
        # Try common encodings
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                df = pd.read_csv(io.StringIO(contents.decode(enc)),
                                 skip_blank_lines=True)
                break
            except Exception:
                continue
        else:
            raise HTTPException(400, "Could not decode CSV file")

        # Drop completely empty rows/cols
        df = df.dropna(how="all").reset_index(drop=True)

    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {e}")

    # Detect broker
    broker      = detect_broker(df)
    broker_name = BROKER_SIGNATURES.get(broker, {}).get("name", "Generic CSV")

    # Normalize columns
    df = normalize_columns(df, broker)

    # Ensure required columns exist
    required = ["symbol", "price"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        # Return column list for generic mapper
        return JSONResponse({
            "broker":    "generic",
            "columns":   list(df.columns),
            "row_count": len(df),
            "needs_mapping": True,
            "message": f"Could not auto-detect format. Please map columns.",
        })

    # Parse rows
    rows = []
    for _, row in df.iterrows():
        price = clean_price(row.get("price"))
        if price is None or price <= 0:
            continue

        raw_qty = row.get("qty")
        qty, is_sell_by_sign = clean_qty(raw_qty)
        if qty is None or qty <= 0:
            continue

        side_raw = row.get("side", "")
        side = normalize_side(side_raw, qty_negative=(is_sell_by_sign or False))

        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or len(symbol) > 10:
            continue

        ts = parse_timestamp(row.get("timestamp"))

        rows.append({
            "symbol":    symbol,
            "side":      side,
            "qty":       qty,
            "price":     price,
            "timestamp": ts,
        })

    if not rows:
        raise HTTPException(400, "No valid trade rows found in CSV")

    # Reconstruct trades via FIFO matching
    trades, open_positions = reconstruct_trades(rows)

    # Behavioral analysis
    analysis = analyze_behavior(trades)

    # Persist to DB
    persist_trades(trades, USER_ID, analysis)

    return {
        "ok":              True,
        "broker":          broker,
        "broker_name":     broker_name,
        "raw_rows":        len(rows),
        "trades_closed":   len(trades),
        "trades_open":     len(open_positions),
        "analysis":        analysis,
        "message":         (
            f"Successfully imported {len(trades)} closed trades "
            f"from {broker_name}. Behavioral profile updated."
        ),
    }


@csv_router.post("/upload-generic")
async def upload_generic(
    file: UploadFile = File(...),
    symbol_col:    str = "symbol",
    side_col:      str = "side",
    qty_col:       str = "qty",
    price_col:     str = "price",
    timestamp_col: str = "date",
):
    """
    Generic CSV upload with explicit column mapping.
    Used when auto-detection fails.
    """
    contents = await file.read()
    try:
        df = pd.read_csv(io.StringIO(contents.decode("utf-8", errors="replace")),
                         skip_blank_lines=True)
        df = df.dropna(how="all")
    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {e}")

    # Apply user-provided column mapping
    col_map = {
        symbol_col:    "symbol",
        side_col:      "side",
        qty_col:       "qty",
        price_col:     "price",
        timestamp_col: "timestamp",
    }
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns={k.lower(): v for k, v in col_map.items()})

    rows = []
    for _, row in df.iterrows():
        price = clean_price(row.get("price"))
        if price is None or price <= 0:
            continue
        qty, is_sell = clean_qty(row.get("qty"))
        if qty is None:
            continue
        side   = normalize_side(row.get("side",""), qty_negative=(is_sell or False))
        symbol = str(row.get("symbol","")).strip().upper()
        ts     = parse_timestamp(row.get("timestamp"))
        if symbol:
            rows.append({"symbol":symbol,"side":side,"qty":qty,"price":price,"timestamp":ts})

    trades, open_positions = reconstruct_trades(rows)
    analysis = analyze_behavior(trades)
    persist_trades(trades, USER_ID, analysis)

    return {
        "ok":            True,
        "broker":        "generic",
        "broker_name":   "Generic CSV",
        "raw_rows":      len(rows),
        "trades_closed": len(trades),
        "trades_open":   len(open_positions),
        "analysis":      analysis,
    }


@csv_router.get("/analysis/{user_id}")
def get_analysis(user_id: str):
    """Return the latest CSV import analysis for a user."""
    con = get_db()
    row = con.execute("""
        SELECT metadata FROM behavioral_events
        WHERE user_id=? AND event_type='csv_imported'
        ORDER BY timestamp DESC LIMIT 1
    """, (user_id,)).fetchone()
    con.close()
    if not row:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}