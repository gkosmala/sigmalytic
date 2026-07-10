from __future__ import annotations

import csv
import io
import json
import math
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["import-history-restore"])

STORE_DIR = Path(__file__).resolve().parent / "data" / "import_history"
LAST_IMPORT_PATH = STORE_DIR / "last_import.json"

COLUMN_ALIASES = {
    "date": ["date", "time", "datetime", "trade_date", "transaction_date", "executed_at", "fill_time"],
    "symbol": ["symbol", "ticker", "asset", "underlying", "instrument"],
    "side": ["side", "action", "type", "transaction_type", "buy_sell", "instruction"],
    "quantity": ["quantity", "qty", "shares", "filled_qty", "filled_quantity", "amount"],
    "price": ["price", "avg_price", "average_price", "fill_price", "execution_price", "trade_price"],
    "fees": ["fees", "fee", "commission", "commissions"],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _build_key_map(fieldnames: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    normalized = {_clean_key(name): name for name in fieldnames if name is not None}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            hit = normalized.get(_clean_key(alias))
            if hit:
                out[canonical] = hit
                break
    return out


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
    if text == "":
        return default
    try:
        number = float(text)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_side(value: Any) -> str:
    text = _safe_text(value).lower()
    if text in {"b", "buy", "bought", "bot", "long", "open buy"}:
        return "BUY"
    if text in {"s", "sell", "sold", "short", "open sell", "close sell"}:
        return "SELL"
    if "buy" in text:
        return "BUY"
    if "sell" in text or "sold" in text:
        return "SELL"
    return text.upper() if text else "UNKNOWN"


def _parse_trade_datetime(value: Any):
    text = _safe_text(value)
    if not text:
        return None

    text = text.replace("Z", "+00:00")

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%m/%d/%y",
    ]

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue

    return None


def _trade_date_key(dt_obj, fallback: str) -> str:
    if dt_obj is not None:
        return dt_obj.date().isoformat()
    return _safe_text(fallback)[:10] or "UNKNOWN_DATE"


def _minutes_between(a, b) -> float:
    if a is None or b is None:
        return 0.0
    try:
        return max(0.0, (b - a).total_seconds() / 60.0)
    except Exception:
        return 0.0


def _max_streak(values: List[bool]) -> int:
    best = 0
    current = 0
    for item in values:
        if item:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _analyze_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Real brokerage behavioral analysis.

    The prior version only counted imported executions. This version converts
    executions into round-trip trades and calculates realized P&L, win/loss
    behavior, streaks, symbol damage, sizing behavior, re-entry behavior,
    holding time, and daily loss behavior.
    """
    executions = []

    for idx, row in enumerate(trades):
        dt_obj = _parse_trade_datetime(row.get("date"))
        qty = abs(_safe_float(row.get("quantity")))
        price = _safe_float(row.get("price"))
        side = _normalize_side(row.get("side"))
        symbol = _safe_text(row.get("symbol")).upper()
        fees = abs(_safe_float(row.get("fees")))

        if not symbol or qty <= 0 or price <= 0 or side not in {"BUY", "SELL"}:
            continue

        executions.append({
            "index": idx,
            "datetime": dt_obj,
            "date": row.get("date"),
            "date_key": _trade_date_key(dt_obj, row.get("date")),
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "price": price,
            "fees": fees,
            "notional": abs(qty * price),
            "raw": row.get("raw") or {},
        })

    executions.sort(key=lambda x: (x["datetime"] is None, x["datetime"] or datetime.min, x["index"]))

    long_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    short_lots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    round_trips: List[Dict[str, Any]] = []

    def close_trade(symbol: str, open_lot: Dict[str, Any], close_exec: Dict[str, Any], qty: float, direction: str) -> Dict[str, Any]:
        open_fee = open_lot.get("fee_per_share", 0.0) * qty
        close_fee = (close_exec.get("fees", 0.0) / close_exec.get("quantity", qty)) * qty if close_exec.get("quantity") else 0.0

        if direction == "LONG":
            pnl = (close_exec["price"] - open_lot["price"]) * qty - open_fee - close_fee
        else:
            pnl = (open_lot["price"] - close_exec["price"]) * qty - open_fee - close_fee

        entry_dt = open_lot.get("datetime")
        exit_dt = close_exec.get("datetime")
        hold_minutes = _minutes_between(entry_dt, exit_dt)

        return {
            "symbol": symbol,
            "direction": direction,
            "entry_date": open_lot.get("date"),
            "exit_date": close_exec.get("date"),
            "exit_date_key": _trade_date_key(exit_dt, close_exec.get("date")),
            "entry_time": entry_dt.isoformat() if entry_dt else None,
            "exit_time": exit_dt.isoformat() if exit_dt else None,
            "quantity": round(qty, 6),
            "entry_price": round(open_lot["price"], 6),
            "exit_price": round(close_exec["price"], 6),
            "notional": round(abs(qty * open_lot["price"]), 2),
            "pnl": round(pnl, 2),
            "return_pct": round((pnl / abs(qty * open_lot["price"])) * 100.0, 4) if qty and open_lot["price"] else 0.0,
            "hold_minutes": round(hold_minutes, 2),
            "winner": pnl > 0,
        }

    for ex in executions:
        symbol = ex["symbol"]
        qty_remaining = ex["quantity"]

        if ex["side"] == "BUY":
            while qty_remaining > 0 and short_lots[symbol]:
                lot = short_lots[symbol][0]
                qty = min(qty_remaining, lot["quantity"])
                round_trips.append(close_trade(symbol, lot, ex, qty, "SHORT"))
                lot["quantity"] -= qty
                qty_remaining -= qty
                if lot["quantity"] <= 1e-9:
                    short_lots[symbol].pop(0)

            if qty_remaining > 0:
                long_lots[symbol].append({
                    "datetime": ex["datetime"],
                    "date": ex["date"],
                    "price": ex["price"],
                    "quantity": qty_remaining,
                    "fee_per_share": ex["fees"] / ex["quantity"] if ex["quantity"] else 0.0,
                    "notional": qty_remaining * ex["price"],
                })

        elif ex["side"] == "SELL":
            while qty_remaining > 0 and long_lots[symbol]:
                lot = long_lots[symbol][0]
                qty = min(qty_remaining, lot["quantity"])
                round_trips.append(close_trade(symbol, lot, ex, qty, "LONG"))
                lot["quantity"] -= qty
                qty_remaining -= qty
                if lot["quantity"] <= 1e-9:
                    long_lots[symbol].pop(0)

            if qty_remaining > 0:
                short_lots[symbol].append({
                    "datetime": ex["datetime"],
                    "date": ex["date"],
                    "price": ex["price"],
                    "quantity": qty_remaining,
                    "fee_per_share": ex["fees"] / ex["quantity"] if ex["quantity"] else 0.0,
                    "notional": qty_remaining * ex["price"],
                })

    total_executions = len(executions)
    total_rows = len(trades)
    total_round_trips = len(round_trips)

    symbols = Counter(ex["symbol"] for ex in executions)
    execution_sides = Counter(ex["side"] for ex in executions)

    total_notional = sum(abs(ex["notional"]) for ex in executions)
    average_execution_notional = total_notional / total_executions if total_executions else 0.0

    realized_pnl = sum(t["pnl"] for t in round_trips)
    winners = [t for t in round_trips if t["pnl"] > 0]
    losers = [t for t in round_trips if t["pnl"] < 0]

    gross_profit = sum(t["pnl"] for t in winners)
    gross_loss = sum(t["pnl"] for t in losers)

    win_rate = len(winners) / total_round_trips if total_round_trips else 0.0
    loss_rate = len(losers) / total_round_trips if total_round_trips else 0.0
    average_win = gross_profit / len(winners) if winners else 0.0
    average_loss = gross_loss / len(losers) if losers else 0.0
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else (999.0 if gross_profit > 0 else 0.0)
    expectancy = realized_pnl / total_round_trips if total_round_trips else 0.0
    avg_hold_minutes = sum(t["hold_minutes"] for t in round_trips) / total_round_trips if total_round_trips else 0.0

    loss_streak_flags = [t["pnl"] < 0 for t in round_trips]
    win_streak_flags = [t["pnl"] > 0 for t in round_trips]
    max_losing_streak = _max_streak(loss_streak_flags)
    max_winning_streak = _max_streak(win_streak_flags)

    symbol_pnl: Dict[str, float] = defaultdict(float)
    symbol_trades: Dict[str, int] = defaultdict(int)
    symbol_wins: Dict[str, int] = defaultdict(int)

    day_pnl: Dict[str, float] = defaultdict(float)
    day_trades: Dict[str, int] = defaultdict(int)

    hour_pnl: Dict[str, float] = defaultdict(float)
    hour_trades: Dict[str, int] = defaultdict(int)

    for t in round_trips:
        symbol_pnl[t["symbol"]] += t["pnl"]
        symbol_trades[t["symbol"]] += 1
        if t["pnl"] > 0:
            symbol_wins[t["symbol"]] += 1

        day_pnl[t["exit_date_key"]] += t["pnl"]
        day_trades[t["exit_date_key"]] += 1

        if t.get("exit_time"):
            try:
                hour = str(datetime.fromisoformat(t["exit_time"]).hour).zfill(2) + ":00"
                hour_pnl[hour] += t["pnl"]
                hour_trades[hour] += 1
            except Exception:
                pass

    trading_days = len(day_pnl)
    losing_days = sum(1 for value in day_pnl.values() if value < 0)
    winning_days = sum(1 for value in day_pnl.values() if value > 0)
    losing_day_rate = losing_days / trading_days if trading_days else 0.0

    worst_symbols = [
        {
            "symbol": sym,
            "pnl": round(pnl, 2),
            "trades": symbol_trades[sym],
            "win_rate": round(symbol_wins[sym] / symbol_trades[sym], 4) if symbol_trades[sym] else 0.0,
        }
        for sym, pnl in sorted(symbol_pnl.items(), key=lambda item: item[1])[:8]
    ]

    best_symbols = [
        {
            "symbol": sym,
            "pnl": round(pnl, 2),
            "trades": symbol_trades[sym],
            "win_rate": round(symbol_wins[sym] / symbol_trades[sym], 4) if symbol_trades[sym] else 0.0,
        }
        for sym, pnl in sorted(symbol_pnl.items(), key=lambda item: item[1], reverse=True)[:8]
    ]

    worst_hours = [
        {
            "hour": hour,
            "pnl": round(pnl, 2),
            "trades": hour_trades[hour],
        }
        for hour, pnl in sorted(hour_pnl.items(), key=lambda item: item[1])[:5]
    ]

    quick_reentry_after_loss = 0
    size_after_loss_events = 0

    for prev, curr in zip(round_trips, round_trips[1:]):
        prev_exit = _parse_trade_datetime(prev.get("exit_time"))
        curr_entry = _parse_trade_datetime(curr.get("entry_time"))

        if prev["pnl"] < 0:
            if prev_exit and curr_entry and _minutes_between(prev_exit, curr_entry) <= 60:
                quick_reentry_after_loss += 1

            if curr.get("notional", 0.0) > prev.get("notional", 0.0) * 1.25:
                size_after_loss_events += 1

    behavioral_flags: List[str] = []

    if total_round_trips == 0:
        behavioral_flags.append("NO_ROUND_TRIP_TRADES_DETECTED")
    if total_round_trips and win_rate < 0.35:
        behavioral_flags.append("LOW_WIN_RATE_BELOW_35_PERCENT")
    if total_round_trips and profit_factor < 0.75:
        behavioral_flags.append("NEGATIVE_EXPECTANCY_PROFIT_FACTOR_BELOW_0_75")
    if max_losing_streak >= 5:
        behavioral_flags.append("LOSS_STREAK_CONTINUATION_RISK")
    if losing_day_rate >= 0.60:
        behavioral_flags.append("HIGH_LOSING_DAY_FREQUENCY")
    if quick_reentry_after_loss >= 3:
        behavioral_flags.append("QUICK_REENTRY_AFTER_LOSS_PATTERN")
    if size_after_loss_events >= 3:
        behavioral_flags.append("SIZE_INCREASE_AFTER_LOSS_PATTERN")
    if worst_symbols and len(worst_symbols) > 0 and worst_symbols[0]["pnl"] < realized_pnl * 0.25:
        behavioral_flags.append("SYMBOL_SPECIFIC_DAMAGE_CONCENTRATION")
    if avg_hold_minutes and avg_hold_minutes < 30 and profit_factor < 1.0:
        behavioral_flags.append("SHORT_HOLD_NEGATIVE_EXPECTANCY_PATTERN")

    if not behavioral_flags:
        behavioral_flags.append("NO_MAJOR_BEHAVIORAL_FAILURE_FLAGS_DETECTED")

    if total_round_trips == 0:
        behavioral_profile = "No round-trip behavioral profile is available because the import did not contain matched entries and exits."
    elif realized_pnl < 0 and profit_factor < 1.0:
        behavioral_profile = (
            "Behavioral analysis shows negative expectancy. The major focus should be reducing loss-streak continuation, "
            "avoiding rapid re-entry after losses, and isolating the symbols and time windows causing the most damage."
        )
    elif win_rate < 0.40:
        behavioral_profile = (
            "Behavioral analysis shows a low win-rate profile. Improvement should focus on setup selectivity, entry timing, "
            "and stopping repeated attempts in the same weak context."
        )
    else:
        behavioral_profile = (
            "Imported history is sufficient for a preliminary behavioral profile. Continue tracking round-trip trades to refine the edge map."
        )

    return {
        "execution_rows_received": total_rows,
        "executions_analyzed": total_executions,
        "execution_count": total_executions,
        "round_trip_trades": total_round_trips,
        "total_trades": total_round_trips,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate": round(win_rate, 4),
        "loss_rate": round(loss_rate, 4),
        "realized_pnl": round(realized_pnl, 2),
        "total_pnl": round(realized_pnl, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 4),
        "expectancy_per_trade": round(expectancy, 2),
        "average_win": round(average_win, 2),
        "average_loss": round(average_loss, 2),
        "average_hold_minutes": round(avg_hold_minutes, 2),
        "max_losing_streak": max_losing_streak,
        "max_winning_streak": max_winning_streak,
        "trading_days": trading_days,
        "winning_days": winning_days,
        "losing_days": losing_days,
        "losing_day_rate": round(losing_day_rate, 4),
        "quick_reentry_after_loss_count": quick_reentry_after_loss,
        "size_after_loss_count": size_after_loss_events,
        "unique_symbols": len(symbols),
        "symbols": dict(symbols.most_common(25)),
        "sides": dict(execution_sides),
        "total_notional": round(total_notional, 2),
        "average_trade_notional": round(average_execution_notional, 2),
        "largest_symbol": symbols.most_common(1)[0][0] if symbols else None,
        "worst_symbols": worst_symbols,
        "best_symbols": best_symbols,
        "worst_hours": worst_hours,
        "daily_pnl": {k: round(v, 2) for k, v in sorted(day_pnl.items())},
        "behavioral_flags": behavioral_flags,
        "behavioral_profile": behavioral_profile,
        "summary": {
            "executions_imported": total_executions,
            "round_trip_trades": total_round_trips,
            "win_rate": round(win_rate, 4),
            "realized_pnl": round(realized_pnl, 2),
            "profit_factor": round(profit_factor, 4),
            "max_losing_streak": max_losing_streak,
            "behavioral_flag_count": len(behavioral_flags),
        },
        "round_trips_preview": round_trips[:100],
    }



def _parse_csv_bytes(filename: str, raw: bytes) -> Dict[str, Any]:
    text = _decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row.")

    key_map = _build_key_map(reader.fieldnames)
    if "symbol" not in key_map:
        raise HTTPException(status_code=400, detail="CSV must include a symbol/ticker column.")

    trades: List[Dict[str, Any]] = []
    ignored_rows = 0
    total_rows = 0

    for row in reader:
        total_rows += 1

        symbol = _safe_text(row.get(key_map.get("symbol", ""))).upper()
        if not symbol:
            ignored_rows += 1
            continue

        quantity = _safe_float(row.get(key_map.get("quantity", "")))
        price = _safe_float(row.get(key_map.get("price", "")))
        side = _normalize_side(row.get(key_map.get("side", "")))
        date_value = _safe_text(row.get(key_map.get("date", "")))
        fees = _safe_float(row.get(key_map.get("fees", "")))

        notional = abs(quantity * price) if quantity and price else 0.0

        trades.append({
            "date": date_value,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "notional": round(notional, 2),
            "raw": row,
        })

    analysis = _analyze_trades(trades)

    return {
        "ok": True,
        "success": True,
        "status": "PASS",
        "message": f"Imported {len(trades)} trades from {filename}.",
        "import_id": str(uuid.uuid4()),
        "filename": filename,
        "received_at_utc": _now_iso(),
        "rows_received": total_rows,
        "parsed_rows": len(trades),
        "ignored_rows": ignored_rows,
        "column_map": key_map,
        "trades_imported": len(trades),
        "analysis": analysis,
        "behavioral_analysis": analysis,
        "behavioral_flags": analysis.get("behavioral_flags", []),
        "summary": analysis.get("summary", {}),
        "trades_preview": trades[:50],
    }


def _save_import(payload: Dict[str, Any]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_IMPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@router.post("/api/import/upload-generic")
async def upload_generic_import_history(request: Request) -> Dict[str, Any]:
    form = await request.form()
    upload = form.get("file")

    if upload is None:
        raise HTTPException(status_code=400, detail="Missing multipart file field named 'file'.")

    filename = getattr(upload, "filename", None) or "uploaded_brokerage_history.csv"
    raw = await upload.read()

    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty.")

    payload = _parse_csv_bytes(filename, raw)
    _save_import(payload)
    return payload


@router.get("/api/trades/history")
async def get_trade_import_history() -> Dict[str, Any]:
    if not LAST_IMPORT_PATH.exists():
        return {
            "ok": True,
            "success": True,
            "has_history": False,
            "message": "No import history found.",
            "analysis": None,
            "behavioral_analysis": None,
        }

    return json.loads(LAST_IMPORT_PATH.read_text(encoding="utf-8"))


@router.post("/api/trades/reset")
@router.delete("/api/trades/reset")
async def reset_trade_import_history() -> Dict[str, Any]:
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    removed = []
    for path in STORE_DIR.glob("*.json"):
        removed.append(path.name)
        path.unlink()

    return {
        "ok": True,
        "success": True,
        "reset": True,
        "removed_files": removed,
        "message": "Import history reset. Upload a new brokerage CSV to rebuild behavioral intelligence.",
        "doctrine": {
            "scoped_import_reset_only": True,
            "no_campaign_delete": True,
            "no_universe_delete": True,
            "no_supabase_write": True,
            "no_billing": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
        },
    }

# SIGMALYTIC_STEP85F_UI_COMPAT_WRAPPER_START
# Compatibility wrapper for the existing Dash Import History UI.
# This exposes the legacy top-level response keys expected by the browser:
# broker, total_trades, win_rate, total_pnl, and behavioral profile fields.
# It does not mutate campaigns, universe snapshots, D3D, operator-control evidence, or billing.
def _sigmalytic_step85f_legacy_compat(payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = payload.get("analysis") or payload.get("behavioral_analysis") or {}

    round_trips = int(
        analysis.get("round_trip_trades")
        or analysis.get("total_trades")
        or payload.get("trades_imported")
        or payload.get("parsed_rows")
        or 0
    )

    executions = int(
        analysis.get("executions_analyzed")
        or analysis.get("execution_count")
        or payload.get("parsed_rows")
        or 0
    )

    filename = str(payload.get("filename") or "").lower()
    broker = "Generic CSV"

    if "alpaca" in filename:
        broker = "Alpaca"
    elif "schwab" in filename or "td" in filename or "ameritrade" in filename:
        broker = "TD Ameritrade / Schwab"
    elif "ibkr" in filename or "interactive" in filename:
        broker = "Interactive Brokers"
    elif "robinhood" in filename:
        broker = "Robinhood"
    elif "webull" in filename:
        broker = "Webull"

    total_pnl = float(analysis.get("realized_pnl") or analysis.get("total_pnl") or 0.0)
    win_rate = float(analysis.get("win_rate") or 0.0)

    return {
        "broker": broker,
        "broker_detected": broker,
        "detected_broker": broker,
        "total_trades": round_trips,
        "round_trip_trades": round_trips,
        "executions_imported": executions,
        "trades": round_trips,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "realized_pnl": total_pnl,
        "pnl": total_pnl,
        "total_pnl_display": f"${total_pnl:,.2f}",
        "profit_factor": analysis.get("profit_factor"),
        "max_losing_streak": analysis.get("max_losing_streak"),
        "behavioral_snapshot": analysis,
        "behavioral_profile": analysis.get("behavioral_profile"),
        "profile": analysis,
        "flags": analysis.get("behavioral_flags", []),
    }


_sigmalytic_step85f_original_parse_csv_bytes = _parse_csv_bytes


def _parse_csv_bytes(filename: str, raw: bytes) -> Dict[str, Any]:
    payload = _sigmalytic_step85f_original_parse_csv_bytes(filename, raw)
    payload.update(_sigmalytic_step85f_legacy_compat(payload))
    return payload
# SIGMALYTIC_STEP85F_UI_COMPAT_WRAPPER_END

