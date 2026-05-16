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
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import JSONResponse

from behavior import get_db, update_regime_memory, \
    calculate_risk_score, calculate_execution_quality, \
    calculate_composite
from supabase_isolation import get_user_id_from_request

csv_router = APIRouter(prefix="/api/import", tags=["import"])

BROKER_SIGNATURES = {
    "alpaca":       {"required": ["symbol","side","qty","filled_avg_price"], "optional": ["filled_at","created_at"], "name": "Alpaca"},
    "tdameritrade": {"required": ["symbol","quantity","price","action"],     "optional": ["date","description","amount"], "name": "TD Ameritrade / Schwab"},
    "schwab":       {"required": ["symbol","quantity","price","action"],     "optional": ["date","description","fees & comm"], "name": "Schwab"},
    "ibkr":         {"required": ["symbol","quantity","t. price","proceeds"],"optional": ["date/time","comm/fee","realized p/l"], "name": "Interactive Brokers"},
    "robinhood":    {"required": ["symbol","quantity","average price","side"],"optional": ["activity date","instrument","amount"], "name": "Robinhood"},
    "webull":       {"required": ["ticker","side","filled qty","avg price"],  "optional": ["filled time","order type"], "name": "Webull"},
}

COLUMN_MAPS = {
    "alpaca":       {"symbol":"symbol","side":"side","qty":"qty","filled_avg_price":"price","filled_at":"timestamp","created_at":"timestamp"},
    "tdameritrade": {"symbol":"symbol","action":"side","quantity":"qty","price":"price","date":"timestamp"},
    "schwab":       {"symbol":"symbol","action":"side","quantity":"qty","price":"price","date":"timestamp"},
    "ibkr":         {"symbol":"symbol","quantity":"qty","t. price":"price","date/time":"timestamp"},
    "robinhood":    {"symbol":"symbol","instrument":"symbol","side":"side","quantity":"qty","average price":"price","activity date":"timestamp"},
    "webull":       {"ticker":"symbol","side":"side","filled qty":"qty","avg price":"price","filled time":"timestamp"},
}

SIDE_MAP = {
    "buy":"buy","sell":"sell","b":"buy","s":"sell",
    "bought":"buy","sold":"sell",
    "buy to open":"buy","buy to close":"buy",
    "sell to open":"sell","sell to close":"sell",
    "purchase":"buy","redemption":"sell","long":"buy","short":"sell",
}


def detect_broker(df):
    cols = set(c.lower().strip() for c in df.columns)
    scores = {}
    for broker, sig in BROKER_SIGNATURES.items():
        req = sum(1 for r in sig["required"] if r in cols)
        opt = sum(1 for o in sig["optional"] if o in cols)
        if req == len(sig["required"]):
            scores[broker] = req * 10 + opt
        elif req >= len(sig["required"]) - 1:
            scores[broker] = req * 5 + opt
    return max(scores, key=scores.get) if scores else "generic"


def normalize_columns(df, broker):
    col_map = COLUMN_MAPS.get(broker, {})
    df.columns = [c.lower().strip() for c in df.columns]
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    return df.rename(columns=rename)


def clean_price(val):
    if pd.isna(val): return None
    s = str(val).strip().replace("$","").replace(",","").replace(" ","")
    if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
    try: return float(s)
    except: return None


def clean_qty(val):
    if pd.isna(val): return None, None
    s = str(val).strip().replace(",","")
    try: return abs(float(s)), float(s) < 0
    except: return None, None


def normalize_side(val, qty_negative=False):
    if qty_negative: return "sell"
    if pd.isna(val): return "buy"
    return SIDE_MAP.get(str(val).lower().strip(), "buy")


def parse_timestamp(val):
    if pd.isna(val): return None
    s = str(val).strip()
    for fmt in ["%Y-%m-%dT%H:%M:%SZ","%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M:%S","%m/%d/%Y","%Y-%m-%d","%d/%m/%Y","%m/%d/%y"]:
        try: return datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
        except: continue
    return None


def reconstruct_trades(rows):
    by_symbol = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    trades, open_positions = [], []

    for symbol, execs in by_symbol.items():
        execs.sort(key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))
        buy_queue = []

        for ex in execs:
            side, qty, price, ts = ex["side"], ex["qty"], ex["price"], ex.get("timestamp")
            if side == "buy":
                buy_queue.append({"qty": qty, "price": price, "ts": ts})
            elif side == "sell":
                remaining = qty
                while remaining > 0 and buy_queue:
                    buy = buy_queue[0]
                    matched = min(buy["qty"], remaining)
                    pnl     = (price - buy["price"]) * matched
                    pnl_pct = ((price - buy["price"]) / buy["price"] * 100) if buy["price"] else 0
                    trades.append({
                        "symbol":      symbol, "direction": "long",
                        "entry_price": round(buy["price"], 4),
                        "exit_price":  round(price, 4),
                        "size":        matched,
                        "entry_time":  buy["ts"].isoformat() if buy["ts"] else None,
                        "exit_time":   ts.isoformat() if ts else None,
                        "pnl":         round(pnl, 2),
                        "pnl_percent": round(pnl_pct, 2),
                        "status":      "closed", "source": "csv_import",
                    })
                    buy["qty"] -= matched
                    remaining  -= matched
                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

        for b in buy_queue:
            if b["qty"] > 0:
                open_positions.append({
                    "symbol": symbol, "direction": "long",
                    "entry_price": b["price"], "size": b["qty"],
                    "entry_time": b["ts"].isoformat() if b["ts"] else None,
                    "status": "open", "source": "csv_import",
                })

    return trades, open_positions


def analyze_behavior(trades):
    if not trades: return {}
    closed = [t for t in trades if t["status"] == "closed"]
    if not closed: return {}

    total    = len(closed)
    winners  = [t for t in closed if t["pnl"] > 0]
    losers   = [t for t in closed if t["pnl"] <= 0]
    win_rate = round(len(winners) / total * 100, 1)
    avg_win  = round(sum(t["pnl"] for t in winners) / len(winners), 2) if winners else 0
    avg_loss = round(sum(t["pnl"] for t in losers)  / len(losers),  2) if losers  else 0
    total_pnl= round(sum(t["pnl"] for t in closed), 2)
    rr_ratio = round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0

    holding_times = []
    for t in closed:
        if t.get("entry_time") and t.get("exit_time"):
            try:
                e = datetime.fromisoformat(t["entry_time"])
                x = datetime.fromisoformat(t["exit_time"])
                holding_times.append((x - e).total_seconds())
            except: pass
    avg_hold_secs  = sum(holding_times) / len(holding_times) if holding_times else 0

    mws = mls = cw = cl = 0
    for t in closed:
        if t["pnl"] > 0: cw += 1; cl = 0; mws = max(mws, cw)
        else:             cl += 1; cw = 0; mls = max(mls, cl)

    by_sym = defaultdict(list)
    for t in closed: by_sym[t["symbol"]].append(t)
    sym_perf = {s: {"trades": len(ts), "win_rate": round(sum(1 for t in ts if t["pnl"]>0)/len(ts)*100,1),
                    "total_pnl": round(sum(t["pnl"] for t in ts),2)} for s, ts in by_sym.items()}
    best_sym  = max(sym_perf, key=lambda s: sym_perf[s]["total_pnl"]) if sym_perf else None
    worst_sym = min(sym_perf, key=lambda s: sym_perf[s]["total_pnl"]) if sym_perf else None

    dow = defaultdict(lambda: {"trades":0,"wins":0,"pnl":0})
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    for t in closed:
        if t.get("entry_time"):
            try:
                dt = datetime.fromisoformat(t["entry_time"])
                d  = days[dt.weekday()]
                dow[d]["trades"] += 1; dow[d]["pnl"] += t["pnl"]
                if t["pnl"] > 0: dow[d]["wins"] += 1
            except: pass
    best_day  = max(dow, key=lambda d: dow[d]["pnl"]) if dow else None
    worst_day = min(dow, key=lambda d: dow[d]["pnl"]) if dow else None

    tpd = defaultdict(int)
    for t in closed:
        if t.get("entry_time"):
            try: tpd[datetime.fromisoformat(t["entry_time"]).strftime("%Y-%m-%d")] += 1
            except: pass
    overtrade_days = sum(1 for v in tpd.values() if v > 3)
    overtrade_rate = round(overtrade_days / len(tpd) * 100, 1) if tpd else 0

    flags = []
    if win_rate < 40:              flags.append("Low win rate — review entry criteria")
    if rr_ratio < 1.0 and win_rate < 60: flags.append("Risk/reward unfavorable — average loss exceeds average win")
    if avg_hold_secs < 300 and total > 20: flags.append("Very short hold times — potential overtrading or scalping pattern")
    if overtrade_rate > 30:        flags.append(f"Overtrading detected — {overtrade_rate}% of trading days had 4+ trades")
    if mls >= 5:                   flags.append(f"Max losing streak of {mls} — review risk management")
    if rr_ratio > 1.5 and win_rate > 50: flags.append("Strong risk/reward discipline — maintain this edge")
    if win_rate > 60 and total > 30: flags.append("Above-average win rate — system has statistical edge")

    edge = round((win_rate/100)*avg_win + (1-win_rate/100)*avg_loss, 2) if avg_win and avg_loss else 0

    def hd(s):
        if s < 60: return f"{int(s)}s"
        if s < 3600: return f"{int(s//60)}m"
        if s < 86400: return f"{int(s//3600)}h {int((s%3600)//60)}m"
        return f"{int(s//86400)}d {int((s%86400)//3600)}h"

    return {
        "total_trades": total, "win_rate": win_rate, "total_pnl": total_pnl,
        "avg_win": avg_win, "avg_loss": avg_loss, "rr_ratio": rr_ratio,
        "edge_score": edge, "avg_hold_time": hd(avg_hold_secs),
        "max_win_streak": mws, "max_loss_streak": mls,
        "best_symbol": best_sym, "worst_symbol": worst_sym,
        "best_day": best_day, "worst_day": worst_day,
        "overtrade_rate": overtrade_rate,
        "symbol_performance": dict(sym_perf),
        "day_performance": {k: dict(v) for k, v in dow.items()},
        "behavioral_flags": flags,
    }


def persist_trades(trades, user_id, analysis):
    conn = get_db()
    cur  = conn.cursor()
    for t in trades:
        trade_id = "trade_" + uuid.uuid4().hex[:12]
        t["trade_id"] = trade_id
        cur.execute("""
            INSERT INTO trades
            (trade_id,user_id,symbol,direction,entry_price,exit_price,
             size,entry_time,exit_time,pnl,pnl_percent,
             market_regime_entry,signal_score_entry,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'neutral',50,%s)
            ON CONFLICT (trade_id) DO NOTHING
        """, (trade_id, user_id, t.get("symbol",""), t.get("direction","long"),
              t.get("entry_price",0), t.get("exit_price",0), t.get("size",0),
              t.get("entry_time"), t.get("exit_time"),
              t.get("pnl",0), t.get("pnl_percent",0), t.get("status","closed")))
        if t.get("status") == "closed":
            risk      = calculate_risk_score(None, t["entry_price"], None, t["size"], t["direction"])
            execution = calculate_execution_quality(85.0, 80.0, risk)
            composite = calculate_composite(60.0, execution, 80.0, risk)
            flag      = "plan_followed" if t["pnl_percent"] > 0 else "neutral"
            cur.execute("""
                INSERT INTO decision_scorecards
                (scorecard_id,user_id,trade_id,symbol,
                 setup_quality_score,execution_quality_score,discipline_score,
                 timing_score,risk_management_score,confidence_calibration_score,
                 composite_decision_score,primary_behavior_flag,notes,timestamp)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (scorecard_id) DO NOTHING
            """, ("sc_"+uuid.uuid4().hex[:12], user_id, trade_id, t["symbol"],
                  60.0, round(execution,1), 80.0, 85.0, round(risk,1), 80.0,
                  round(composite,1), flag, "Imported from brokerage CSV",
                  t.get("exit_time") or datetime.now(timezone.utc).isoformat()))
            update_regime_memory(conn, user_id, "neutral", t["symbol"],
                                 t.get("pnl_percent",0), 60.0, flag)
    cur.execute("""
        INSERT INTO behavioral_events
        (event_id,user_id,event_type,symbol,timestamp,metadata)
        VALUES (%s,%s,'csv_imported','PORTFOLIO',NOW(),%s)
    """, ("evt_"+uuid.uuid4().hex[:12], user_id, json.dumps(analysis)))
    conn.commit()
    cur.close()
    conn.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@csv_router.post("/upload")
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id_from_request),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")
    contents = await file.read()
    for enc in ["utf-8","latin-1","cp1252"]:
        try:
            df = pd.read_csv(io.StringIO(contents.decode(enc)), skip_blank_lines=True)
            break
        except: continue
    else:
        raise HTTPException(400, "Could not decode CSV")
    df = df.dropna(how="all").reset_index(drop=True)
    broker      = detect_broker(df)
    broker_name = BROKER_SIGNATURES.get(broker, {}).get("name", "Generic CSV")
    df = normalize_columns(df, broker)
    if any(c not in df.columns for c in ["symbol","price"]):
        return JSONResponse({"broker":"generic","columns":list(df.columns),
                             "row_count":len(df),"needs_mapping":True})
    rows = []
    for _, row in df.iterrows():
        price = clean_price(row.get("price"))
        if not price or price <= 0: continue
        qty, is_sell = clean_qty(row.get("qty"))
        if qty is None or qty <= 0: continue
        symbol = str(row.get("symbol","")).strip().upper()
        if not symbol or len(symbol) > 10: continue
        rows.append({"symbol":symbol,"side":normalize_side(row.get("side",""),qty_negative=(is_sell or False)),
                     "qty":qty,"price":price,"timestamp":parse_timestamp(row.get("timestamp"))})
    if not rows: raise HTTPException(400, "No valid rows found")
    trades, open_pos = reconstruct_trades(rows)
    analysis = analyze_behavior(trades)
    try: persist_trades(trades, user_id, analysis)
    except: pass
    return {"ok":True,"broker":broker,"broker_name":broker_name,"raw_rows":len(rows),
            "trades_closed":len(trades),"trades_open":len(open_pos),"analysis":analysis}


@csv_router.post("/upload-generic")
async def upload_generic(
    request: Request,
    file: UploadFile = File(...),
    symbol_col:    str = "symbol",
    side_col:      str = "side",
    qty_col:       str = "qty",
    price_col:     str = "price",
    timestamp_col: str = "date",
    user_id: str = Depends(get_user_id_from_request),
):
    contents = await file.read()
    try:
        df = pd.read_csv(io.StringIO(contents.decode("utf-8", errors="replace")), skip_blank_lines=True)
        df = df.dropna(how="all")
    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {e}")

    col_map = {symbol_col:"symbol", side_col:"side", qty_col:"qty",
               price_col:"price", timestamp_col:"timestamp"}
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns={k.lower(): v for k, v in col_map.items()})

    for alt in ["action", "type", "direction", "transaction"]:
        if "side" not in df.columns and alt in df.columns:
            df = df.rename(columns={alt: "side"})
            break

    rows = []
    for _, row in df.iterrows():
        price = clean_price(row.get("price"))
        if price is None or price <= 0: continue
        qty, is_sell = clean_qty(row.get("qty"))
        if qty is None: continue
        symbol = str(row.get("symbol","")).strip().upper()
        if not symbol: continue
        rows.append({"symbol":symbol,
                     "side":normalize_side(str(row.get("side","")), qty_negative=(is_sell or False)),
                     "qty":qty, "price":price,
                     "timestamp":parse_timestamp(row.get("timestamp"))})

    trades, open_pos = reconstruct_trades(rows)
    analysis = analyze_behavior(trades)
    try: persist_trades(trades, user_id, analysis)
    except: pass

    return {"ok":True,"broker":"generic","broker_name":"Generic CSV",
            "raw_rows":len(rows),"trades_closed":len(trades),
            "trades_open":len(open_pos),"analysis":analysis}


@csv_router.get("/analysis/{user_id}")
def get_analysis(user_id: str):
    try:
        conn = get_db()
        cur  = conn.cursor()
        cur.execute("""
            SELECT symbol, entry_price, exit_price, size, entry_time, exit_time,
                   pnl, pnl_percent, status
            FROM trades
            WHERE user_id=%s AND status='closed'
            ORDER BY entry_time ASC
        """, (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {}

        trades = []
        for r in rows:
            trades.append({
                "symbol":      r[0],
                "entry_price": r[1],
                "exit_price":  r[2],
                "size":        r[3],
                "entry_time":  r[4].isoformat() if r[4] else None,
                "exit_time":   r[5].isoformat() if r[5] else None,
                "pnl":         r[6],
                "pnl_percent": r[7],
                "status":      r[8],
            })
        return analyze_behavior(trades)
    except Exception as e:
        return {}
