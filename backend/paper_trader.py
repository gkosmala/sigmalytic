# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/paper_trader.py
-----------------------
Admin Paper Trading: a simulated $1,000,000 account that trades the platform's
own Trade Finder setups automatically, for the administrator to test.

NOTHING HERE SENDS AN ORDER ANYWHERE. There is no broker call in this module:
fills are simulated inside Sigmalytic from Alpaca market data (read-only
snapshots and daily bars). Results live only in the paper_* tables and are
shown only in the Admin tab, never in a subscriber's Journal or Portfolio.

Where the trades come from
  The Weis Radar scan (scanner worker) writes every Trade Finder plan to Redis
  key weis_radar:trade_finder:v1: symbol, side, entry_trigger, invalidation
  (stop) and target, one plan per Armed test bar (backend/weis_trade_finder.py).
  This module reads those plans; it never changes them.

The default rules copy weis_trade_finder.evaluate_trade_path exactly, so the
paper account is a live replica of the platform's own trade definition:
  entry  when a later bar reaches the entry trigger, at the trigger or a worse
         opening gap; skipped if that fill is already past the target
  stop   the plan's invalidation; a bar that reaches stop and target resolves
         at the stop; a gap through the stop fills at the open
  target the plan's target
  time   closed at the close of the 10th session after entry
  costs  5 basis points per side (WEIS_TRADE_COST_BPS_PER_SIDE default)
Every rule is an admin setting (DEFAULT_SETTINGS). A settings change applies to
trades opened afterwards; open trades keep the rules they were opened with.

How it runs
  run_cycle() is called every 5 minutes by a background thread started at
  backend startup (start_background_loop). A Postgres advisory lock makes sure
  only one process runs a cycle at a time, and every plan id is unique in
  paper_plans, so a plan can never be traded twice.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

log = logging.getLogger("paper_trader")
ET = ZoneInfo("America/New_York")
TRADE_FINDER_KEY = "weis_radar:trade_finder:v1"
RADAR_CACHE_KEY = "radar:cache"
LOCK_ID = 774_201_126           # Postgres advisory lock id for one cycle at a time
CYCLE_SECONDS = 300
DEFAULT_STARTING_CASH = 1_000_000.0

DEFAULT_SETTINGS: Dict[str, Any] = {
    "enabled": True,              # auto-trading on/off (off = no buys or sells; prices still update)
    "direction": "long",          # "long" | "both"
    "entry_mode": "trigger",      # "trigger" (platform rule) | "armed" (buy when the plan appears)
    "sizing": "risk",             # "risk" | "fixed"
    "risk_pct": 0.5,              # % of equity lost if the stop is hit (sizing = risk)
    "fixed_pct": 5.0,             # % of equity per position (sizing = fixed)
    "max_position_pct": 10.0,     # cap per position, % of equity
    "max_positions": 15,
    "exit_mode": "target",        # "target" (platform rule) | "half_2r" | "status"
    "time_limit": 10,             # sessions after entry; 0 = no limit
    "entry_window": 10,           # sessions a plan may wait for its trigger before it expires
    "cost_bps": 5.0,              # cost per side, basis points
}
CHOICES = {
    "direction": ("long", "both"),
    "entry_mode": ("trigger", "armed"),
    "sizing": ("risk", "fixed"),
    "exit_mode": ("target", "half_2r", "status"),
}
LIMITS = {  # numeric settings: (min, max)
    "risk_pct": (0.05, 5.0), "fixed_pct": (0.5, 50.0), "max_position_pct": (1.0, 100.0),
    "max_positions": (1, 100), "time_limit": (0, 60), "entry_window": (1, 60), "cost_bps": (0.0, 100.0),
}


# ════════════════════════════════════════════════════════════════════════════
# Pure trading rules (no database, no network) -- unit-tested in tests/test_paper_trader.py
# ════════════════════════════════════════════════════════════════════════════

def clean_settings(raw: Optional[dict], base: Optional[dict] = None) -> Dict[str, Any]:
    """Merge raw into base (default: DEFAULT_SETTINGS), keeping only known keys and valid values."""
    out = dict(base or DEFAULT_SETTINGS)
    for k, v in (raw or {}).items():
        if k not in DEFAULT_SETTINGS or v is None:
            continue
        if k == "enabled":
            out[k] = bool(v)
        elif k in CHOICES:
            if v in CHOICES[k]:
                out[k] = v
        elif k in LIMITS:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            lo, hi = LIMITS[k]
            f = min(max(f, lo), hi)
            out[k] = int(round(f)) if isinstance(DEFAULT_SETTINGS[k], int) else f
    return out


def size_position(equity: float, cash: float, entry: float, stop: float, settings: dict) -> int:
    """Shares to trade. Never more than the cash available or the per-position cap."""
    if entry <= 0 or equity <= 0:
        return 0
    cap_value = equity * settings["max_position_pct"] / 100.0
    if settings["sizing"] == "risk":
        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return 0
        shares = (equity * settings["risk_pct"] / 100.0) / risk_per_share
    else:
        shares = (equity * settings["fixed_pct"] / 100.0) / entry
    fee_factor = 1 + settings["cost_bps"] / 10000.0
    shares = min(shares, cap_value / entry, max(cash, 0.0) / (entry * fee_factor))
    return max(int(math.floor(shares)), 0)


def entry_fill(plan: dict, bar: dict, settings: dict, latest: Optional[float] = None) -> Dict[str, Any]:
    """Decide whether a waiting plan fills on this session's bar.
    bar = {"o","h","l"} for a session AFTER the plan's test bar.
    Returns {"fill": price} | {"skip": reason} | {} (keep waiting)."""
    side = plan["side"]
    trigger, stop, target = float(plan["entry_trigger"]), float(plan["stop"]), float(plan["target"])
    o, h, l = float(bar["o"]), float(bar["h"]), float(bar["l"])
    if settings.get("entry_mode") == "armed":
        if latest is None:
            return {}
        price = float(latest)
    else:
        if side == "Long" and h < trigger or side == "Short" and l > trigger:
            return {}
        price = max(o, trigger) if side == "Long" else min(o, trigger)
    if side == "Long" and price >= target or side == "Short" and price <= target:
        return {"skip": "price already past the target"}
    if side == "Long" and price <= stop or side == "Short" and price >= stop:
        return {"skip": "price already through the stop"}
    return {"fill": round(price, 4)}


def exit_checks(pos: dict, bar: Optional[dict], latest: Optional[float], radar_status: Optional[str],
                session_closing: bool) -> List[Dict[str, Any]]:
    """Exits due for an open position. bar = this session's {"o","h","l","c"} or None.
    On the entry session, bar must hold only prices seen after the fill (the caller passes
    the low/high of observed latest prices). Returns a list of {"qty","price","reason"}."""
    side = pos["side"]
    long = side == "Long"
    qty = int(pos["qty_open"])
    if qty <= 0:
        return []
    stop, target = float(pos["stop"]), (float(pos["target"]) if pos.get("target") else None)
    mode = pos["exit_mode"]
    out: List[Dict[str, Any]] = []
    if bar:
        o, h, l = float(bar["o"]), float(bar["h"]), float(bar["l"])
        hit_stop = l <= stop if long else h >= stop
        if hit_stop:   # a bar that reaches both levels resolves at the stop (platform rule)
            price = (min(o, stop) if long else max(o, stop)) if not pos.get("entry_session_bar") else stop
            return [{"qty": qty, "price": price, "reason": "Stop (invalidation)"}]
        if mode == "half_2r" and not pos.get("t1_done") and pos.get("t1_price"):
            t1 = float(pos["t1_price"])
            if (h >= t1 if long else l <= t1):
                half = qty // 2 if qty > 1 else qty
                out.append({"qty": half, "price": t1, "reason": "First target (2x risk), half"})
                qty -= half
        if mode in ("target", "half_2r") and target and qty > 0 and (h >= target if long else l <= target):
            out.append({"qty": qty, "price": target, "reason": "Target"})
            return out
    if qty > 0 and mode == "status" and radar_status is not None and latest:
        st = (radar_status or "").strip()
        ended = st in ("Avoid", "No setup") or (long and st.startswith("Short")) or (not long and st == "Armed")
        if ended:
            out.append({"qty": qty, "price": float(latest), "reason": f"Radar status changed to {st}"})
            return out
    limit = int(pos.get("time_limit") or 0)
    if qty > 0 and limit and session_closing and int(pos.get("sessions_held") or 0) >= limit and latest:
        out.append({"qty": qty, "price": float(latest), "reason": f"Time limit ({limit} sessions)"})
    return out


def fill_cost(qty: int, price: float, cost_bps: float) -> float:
    return round(qty * price * cost_bps / 10000.0, 2)


def trade_pnl(side: str, qty: int, entry: float, exit_price: float) -> float:
    return round((exit_price - entry) * qty if side == "Long" else (entry - exit_price) * qty, 2)


# ════════════════════════════════════════════════════════════════════════════
# Market data (read-only Alpaca data API)
# ════════════════════════════════════════════════════════════════════════════

def _alpaca():
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")
    return base, {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, bool(key and secret)


def fetch_snapshots(symbols: List[str]) -> Dict[str, dict]:
    """{symbol: {"latest": price, "bar": {"t","o","h","l","c"}}} for today's session."""
    import requests
    base, headers, ok = _alpaca()
    out: Dict[str, dict] = {}
    if not ok or not symbols:
        return out
    feed = os.getenv("PAPER_TRADER_FEED", "sip")
    syms = sorted(set(symbols))
    for i in range(0, len(syms), 100):
        try:
            r = requests.get(f"{base}/v2/stocks/snapshots", headers=headers,
                             params={"symbols": ",".join(syms[i:i + 100]), "feed": feed}, timeout=15)
            if not r.ok:
                log.warning("paper snapshots %s: %s", r.status_code, r.text[:200])
                continue
            for sym, snap in (r.json() or {}).items():
                snap = snap or {}
                lt = (snap.get("latestTrade") or {}).get("p")
                db = snap.get("dailyBar") or {}
                bar = None
                if db.get("t"):
                    bar = {"t": _et_date(db["t"]).isoformat(), "o": db.get("o"), "h": db.get("h"),
                           "l": db.get("l"), "c": db.get("c")}
                out[sym] = {"latest": float(lt) if lt else None, "bar": bar}
        except Exception as exc:
            log.warning("paper snapshots failed: %s", exc)
    return out


def fetch_daily_bars(symbol: str, start: date) -> List[dict]:
    """Completed and current daily bars from start (ET dates), oldest first."""
    import requests
    base, headers, ok = _alpaca()
    if not ok:
        return []
    try:
        r = requests.get(f"{base}/v2/stocks/{symbol}/bars", headers=headers,
                         params={"timeframe": "1Day", "start": start.isoformat(), "limit": 100,
                                 "adjustment": "raw", "feed": os.getenv("PAPER_TRADER_FEED", "sip")}, timeout=15)
        if not r.ok:
            return []
        return [{"t": _et_date(b["t"]).isoformat(), "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
                for b in (r.json() or {}).get("bars") or []]
    except Exception:
        return []


def _et_date(ts: str) -> date:
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(ET).date()


def _redis():
    try:
        from backend.radar_service import _redis_client
        return _redis_client
    except Exception:
        return None


def load_plans() -> Dict[str, dict]:
    r = _redis()
    if not r:
        return {}
    try:
        raw = r.get(TRADE_FINDER_KEY)
        plans = json.loads(raw) if raw else {}
        return plans if isinstance(plans, dict) else {}
    except Exception as exc:
        log.warning("paper: trade finder read failed: %s", exc)
        return {}


def load_radar_statuses(symbols: List[str]) -> Dict[str, str]:
    r = _redis()
    if not r or not symbols:
        return {}
    try:
        raw = r.get(RADAR_CACHE_KEY)
        cache = json.loads(raw) if raw else {}
        out = {}
        for s in symbols:
            row = cache.get(s) or {}
            st = row.get("status")
            if st == "Armed" and row.get("status_direction") == "short":
                st = "Short Armed"
            if st:
                out[s] = st
        return out
    except Exception:
        return {}


# ════════════════════════════════════════════════════════════════════════════
# Database
# ════════════════════════════════════════════════════════════════════════════

def _db():
    import psycopg2
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_account (
    id INT PRIMARY KEY, run_id INT NOT NULL DEFAULT 1, starting_cash NUMERIC NOT NULL, cash NUMERIC NOT NULL,
    settings JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL, spy_start NUMERIC, last_cycle TIMESTAMPTZ,
    last_cycle_note TEXT);
CREATE TABLE IF NOT EXISTS paper_plans (
    run_id INT NOT NULL, trade_id TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
    entry_trigger NUMERIC, stop NUMERIC, target NUMERIC, test_bar_date DATE, first_seen TIMESTAMPTZ,
    status TEXT NOT NULL, reason TEXT, sessions_waited INT NOT NULL DEFAULT 0, last_session DATE,
    settings JSONB, position_id TEXT, PRIMARY KEY (run_id, trade_id));
CREATE TABLE IF NOT EXISTS paper_positions (
    position_id TEXT PRIMARY KEY, run_id INT NOT NULL, trade_id TEXT, symbol TEXT NOT NULL, side TEXT NOT NULL,
    qty_initial INT NOT NULL, qty_open INT NOT NULL, entry_price NUMERIC NOT NULL, entry_time TIMESTAMPTZ NOT NULL,
    entry_session DATE NOT NULL, stop NUMERIC NOT NULL, target NUMERIC, t1_price NUMERIC, t1_done BOOLEAN DEFAULT FALSE,
    exit_mode TEXT NOT NULL, time_limit INT NOT NULL, cost_bps NUMERIC NOT NULL, status TEXT NOT NULL,
    last_price NUMERIC, last_marked TIMESTAMPTZ, seen_low NUMERIC, seen_high NUMERIC, sessions_held INT DEFAULT 0,
    last_session DATE, realized_pnl NUMERIC DEFAULT 0, fees NUMERIC DEFAULT 0, exit_time TIMESTAMPTZ, exit_reason TEXT);
CREATE TABLE IF NOT EXISTS paper_fills (
    fill_id TEXT PRIMARY KEY, run_id INT NOT NULL, position_id TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
    action TEXT NOT NULL, qty INT NOT NULL, price NUMERIC NOT NULL, fee NUMERIC NOT NULL, pnl NUMERIC,
    reason TEXT, cash_after NUMERIC, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS paper_equity (
    run_id INT NOT NULL, day DATE NOT NULL, equity NUMERIC, cash NUMERIC, positions_value NUMERIC,
    open_positions INT, spy_close NUMERIC, PRIMARY KEY (run_id, day));
"""


def ensure_schema(cur) -> None:
    cur.execute(_SCHEMA)


def _account(cur) -> dict:
    cur.execute("SELECT run_id, starting_cash, cash, settings, created_at, spy_start, last_cycle, last_cycle_note "
                "FROM paper_account WHERE id = 1")
    row = cur.fetchone()
    if not row:
        now = datetime.now(timezone.utc)
        cur.execute("INSERT INTO paper_account (id, run_id, starting_cash, cash, settings, created_at) "
                    "VALUES (1, 1, %s, %s, %s::jsonb, %s)",
                    (DEFAULT_STARTING_CASH, DEFAULT_STARTING_CASH, json.dumps(DEFAULT_SETTINGS), now))
        return {"run_id": 1, "starting_cash": DEFAULT_STARTING_CASH, "cash": DEFAULT_STARTING_CASH,
                "settings": dict(DEFAULT_SETTINGS), "created_at": now, "spy_start": None,
                "last_cycle": None, "last_cycle_note": None}
    s = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
    return {"run_id": row[0], "starting_cash": float(row[1]), "cash": float(row[2]),
            "settings": clean_settings(s), "created_at": row[4],
            "spy_start": float(row[5]) if row[5] is not None else None, "last_cycle": row[6],
            "last_cycle_note": row[7]}


def _open_positions(cur, run_id: int) -> List[dict]:
    cur.execute("SELECT position_id, trade_id, symbol, side, qty_initial, qty_open, entry_price, entry_time, "
                "entry_session, stop, target, t1_price, t1_done, exit_mode, time_limit, cost_bps, last_price, "
                "seen_low, seen_high, sessions_held, last_session, realized_pnl, fees "
                "FROM paper_positions WHERE run_id = %s AND status = 'open' ORDER BY entry_time", (run_id,))
    cols = ["position_id", "trade_id", "symbol", "side", "qty_initial", "qty_open", "entry_price", "entry_time",
            "entry_session", "stop", "target", "t1_price", "t1_done", "exit_mode", "time_limit", "cost_bps",
            "last_price", "seen_low", "seen_high", "sessions_held", "last_session", "realized_pnl", "fees"]
    out = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        for k in ("entry_price", "stop", "target", "t1_price", "cost_bps", "last_price", "seen_low", "seen_high",
                  "realized_pnl", "fees"):
            d[k] = float(d[k]) if d[k] is not None else None
        out.append(d)
    return out


def _record_fill(cur, acct, pos, action, qty, price, reason, pnl, now) -> None:
    fee = fill_cost(qty, price, float(pos["cost_bps"]))
    # Cash model: a long ties up its cost; a short holds its entry value as collateral.
    if action == "BUY":
        acct["cash"] -= qty * price + fee
    elif action == "SELL":
        acct["cash"] += qty * price - fee
    elif action == "SHORT":
        acct["cash"] -= qty * price + fee
    elif action == "COVER":
        acct["cash"] += qty * float(pos["entry_price"]) + (pnl or 0.0) - fee
    cur.execute("INSERT INTO paper_fills (fill_id, run_id, position_id, symbol, side, action, qty, price, fee, pnl, "
                "reason, cash_after, at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                ("pf_" + uuid.uuid4().hex[:14], acct["run_id"], pos["position_id"], pos["symbol"], pos["side"],
                 action, qty, round(price, 4), fee, pnl, reason, round(acct["cash"], 2), now))
    pos["fees"] = round(float(pos.get("fees") or 0) + fee, 2)


def _equity(acct: dict, positions: List[dict]) -> float:
    total = acct["cash"]
    for p in positions:
        px = p.get("last_price") or p["entry_price"]
        if p["side"] == "Long":
            total += p["qty_open"] * px
        else:  # collateral back plus open profit
            total += p["qty_open"] * (2 * p["entry_price"] - px)
    return round(total, 2)


# ════════════════════════════════════════════════════════════════════════════
# One cycle
# ════════════════════════════════════════════════════════════════════════════

def _session_state(now_et: datetime):
    open_t = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now_et.weekday() < 5
    in_session = weekday and open_t <= now_et < close_t
    closing = weekday and now_et >= now_et.replace(hour=15, minute=55, second=0, microsecond=0)
    return in_session, closing


def run_cycle(force: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    """One pass: discover new plans, fill triggered entries, apply exits, mark to market,
    snapshot equity. Safe to call any time; outside market hours it only catches up on
    completed sessions."""
    now = now or datetime.now(timezone.utc)
    now_et = now.astimezone(ET)
    in_session, closing = _session_state(now_et)
    notes: List[str] = []
    conn = _db()
    try:
        conn.autocommit = False
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,))
        if not cur.fetchone()[0]:
            conn.rollback()
            return {"ok": True, "skipped": "another cycle is running"}
        try:
            acct = _account(cur)
            s = acct["settings"]
            run_id = acct["run_id"]
            today = now_et.date()

            # 1. discover new Trade Finder plans (only those made after the account started)
            # Plans from the last 5 days are still eligible, so a new account can act on setups
            # that are waiting for their trigger (the entry window then decides).
            start_day = acct["created_at"].astimezone(ET).date() - timedelta(days=5)
            plans = load_plans()
            cur.execute("SELECT trade_id FROM paper_plans WHERE run_id = %s", (run_id,))
            known = {r[0] for r in cur.fetchall()}
            new_count = 0
            for tid, p in plans.items():
                if tid in known or not isinstance(p, dict):
                    continue
                try:
                    test_day = _et_date(p.get("test_bar_time")) if "T" in str(p.get("test_bar_time")) \
                        else date.fromisoformat(str(p.get("test_bar_time"))[:10])
                except Exception:
                    continue
                if test_day < start_day:
                    continue
                side = p.get("side")
                status, reason = "waiting", None
                if side not in ("Long", "Short"):
                    status, reason = "skipped", "unknown side"
                elif side == "Short" and s["direction"] == "long":
                    status, reason = "skipped", "shorts are turned off"
                elif (p.get("outcome") or {}).get("status") not in (None, "NO_ENTRY"):
                    status, reason = "missed", "the setup had already triggered before the paper account saw it"
                cur.execute("INSERT INTO paper_plans (run_id, trade_id, symbol, side, entry_trigger, stop, target, "
                            "test_bar_date, first_seen, status, reason, settings) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING",
                            (run_id, tid, p.get("symbol"), side, p.get("entry_trigger"), p.get("invalidation"),
                             p.get("target"), test_day, now, status, reason, json.dumps(s)))
                new_count += 1
            if new_count:
                notes.append(f"{new_count} new plan(s)")

            cur.execute("SELECT trade_id, symbol, side, entry_trigger, stop, target, test_bar_date, sessions_waited, "
                        "last_session, settings FROM paper_plans WHERE run_id = %s AND status = 'waiting'", (run_id,))
            waiting = [dict(zip(["trade_id", "symbol", "side", "entry_trigger", "stop", "target", "test_bar_date",
                                 "sessions_waited", "last_session", "settings"], r)) for r in cur.fetchall()]
            positions = _open_positions(cur, run_id)
            symbols = sorted({w["symbol"] for w in waiting} | {p["symbol"] for p in positions} | {"SPY"})
            snaps = fetch_snapshots(symbols)
            statuses = load_radar_statuses([p["symbol"] for p in positions])

            # 2. exits for open positions
            trading = s["enabled"] or force
            for pos in positions:
                snap = snaps.get(pos["symbol"]) or {}
                latest = snap.get("latest")
                bars = _sessions_to_check(pos, snap, today) if trading else []
                for bar in bars:
                    is_today = bar["t"] == today.isoformat()
                    if bar["t"] == str(pos["entry_session"]):
                        if latest is None or not is_today:
                            continue
                        lo = min(x for x in (pos.get("seen_low"), latest) if x is not None)
                        hi = max(x for x in (pos.get("seen_high"), latest) if x is not None)
                        pos["seen_low"], pos["seen_high"] = lo, hi
                        check_bar = {"o": pos["entry_price"], "h": hi, "l": lo, "c": latest}
                        pos_view = dict(pos, entry_session_bar=True)
                    else:
                        if bar["t"] != (str(pos["last_session"]) if pos.get("last_session") else None):
                            pos["sessions_held"] = int(pos.get("sessions_held") or 0) + 1
                            pos["last_session"] = bar["t"]
                        check_bar, pos_view = bar, pos
                    closing_bar = (is_today and closing) or not is_today
                    px_close = latest if is_today else float(bar["c"])
                    actions = exit_checks(pos_view, check_bar, px_close,
                                          statuses.get(pos["symbol"]) if is_today and in_session else None,
                                          closing_bar)
                    for a in actions:
                        qty = min(int(a["qty"]), pos["qty_open"])
                        if qty <= 0:
                            continue
                        pnl = trade_pnl(pos["side"], qty, pos["entry_price"], a["price"])
                        _record_fill(cur, acct, pos, "SELL" if pos["side"] == "Long" else "COVER", qty,
                                     float(a["price"]), a["reason"], pnl, now)
                        pos["qty_open"] -= qty
                        pos["realized_pnl"] = round(float(pos.get("realized_pnl") or 0) + pnl, 2)
                        if "First target" in a["reason"]:
                            pos["t1_done"] = True
                        notes.append(f"{pos['symbol']}: {a['reason']} {qty} @ {a['price']:.2f}")
                    if pos["qty_open"] <= 0:
                        pos["exit_reason"] = actions[-1]["reason"] if actions else None
                        break
                pos["last_price"] = latest if latest else pos.get("last_price")
                _save_position(cur, pos, now)

            # 3. entries for waiting plans
            positions = _open_positions(cur, run_id)
            held = {p["symbol"] for p in positions}
            equity = _equity(acct, positions)
            for w in waiting:
                snap = snaps.get(w["symbol"]) or {}
                bar, latest = snap.get("bar"), snap.get("latest")
                ps = s  # the current settings apply to every trade opened from now on
                if not bar or date.fromisoformat(bar["t"]) <= w["test_bar_date"]:
                    continue
                if bar["t"] != (str(w["last_session"]) if w["last_session"] else None):
                    w["sessions_waited"] = int(w["sessions_waited"] or 0) + 1
                    cur.execute("UPDATE paper_plans SET sessions_waited = %s, last_session = %s "
                                "WHERE run_id = %s AND trade_id = %s",
                                (w["sessions_waited"], bar["t"], run_id, w["trade_id"]))
                if not s["enabled"] and not force:
                    continue
                plan = {"side": w["side"], "entry_trigger": float(w["entry_trigger"]), "stop": float(w["stop"]),
                        "target": float(w["target"])}
                decision = entry_fill(plan, bar, ps, latest if in_session else None)
                if "skip" in decision:
                    _close_plan(cur, run_id, w["trade_id"], "skipped", decision["skip"])
                    continue
                if "fill" not in decision:
                    if w["sessions_waited"] >= int(ps["entry_window"]) and (closing or bar["t"] < today.isoformat()):
                        _close_plan(cur, run_id, w["trade_id"], "expired",
                                    f"trigger not reached within {ps['entry_window']} sessions")
                    continue
                if w["symbol"] in held:
                    _close_plan(cur, run_id, w["trade_id"], "skipped", "already holding this symbol")
                    continue
                if len(held) >= int(ps["max_positions"]):
                    _close_plan(cur, run_id, w["trade_id"], "skipped", f"{ps['max_positions']} positions already open")
                    continue
                price = decision["fill"]
                qty = size_position(equity, acct["cash"], price, plan["stop"], ps)
                if qty <= 0:
                    _close_plan(cur, run_id, w["trade_id"], "skipped", "not enough cash for this position")
                    continue
                risk = abs(price - plan["stop"])
                t1 = (price + 2 * risk if w["side"] == "Long" else price - 2 * risk) if ps["exit_mode"] == "half_2r" else None
                pos = {"position_id": "pp_" + uuid.uuid4().hex[:14], "trade_id": w["trade_id"], "symbol": w["symbol"],
                       "side": w["side"], "qty_initial": qty, "qty_open": qty, "entry_price": price,
                       "entry_time": now, "entry_session": date.fromisoformat(bar["t"]), "stop": plan["stop"],
                       "target": None if ps["exit_mode"] == "status" else plan["target"], "t1_price": t1,
                       "t1_done": False, "exit_mode": ps["exit_mode"], "time_limit": int(ps["time_limit"]),
                       "cost_bps": float(ps["cost_bps"]), "last_price": latest or price,
                       "seen_low": price, "seen_high": price, "sessions_held": 0, "last_session": None,
                       "realized_pnl": 0.0, "fees": 0.0}
                cur.execute("INSERT INTO paper_positions (position_id, run_id, trade_id, symbol, side, qty_initial, "
                            "qty_open, entry_price, entry_time, entry_session, stop, target, t1_price, t1_done, "
                            "exit_mode, time_limit, cost_bps, status, last_price, last_marked, seen_low, seen_high) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s)",
                            (pos["position_id"], run_id, pos["trade_id"], pos["symbol"], pos["side"], qty, qty, price,
                             now, pos["entry_session"], pos["stop"], pos["target"], t1, False, pos["exit_mode"],
                             pos["time_limit"], pos["cost_bps"], pos["last_price"], now, price, price))
                _record_fill(cur, acct, pos, "BUY" if w["side"] == "Long" else "SHORT", qty, price,
                             "Entry at trigger" if ps["entry_mode"] == "trigger" else "Entry when Armed", None, now)
                cur.execute("UPDATE paper_positions SET fees = %s WHERE position_id = %s",
                            (pos["fees"], pos["position_id"]))
                _close_plan(cur, run_id, w["trade_id"], "filled", None, pos["position_id"])
                held.add(w["symbol"])
                notes.append(f"{w['symbol']}: {'bought' if w['side'] == 'Long' else 'shorted'} {qty} @ {price:.2f}")

            # 4. mark to market and snapshot equity
            positions = _open_positions(cur, run_id)
            equity = _equity(acct, positions)
            spy = (snaps.get("SPY") or {}).get("latest")
            if acct["spy_start"] is None and spy:
                acct["spy_start"] = spy
            bar_day = ((snaps.get("SPY") or {}).get("bar") or {}).get("t")
            if bar_day:
                pv = round(equity - acct["cash"], 2)
                cur.execute("INSERT INTO paper_equity (run_id, day, equity, cash, positions_value, open_positions, "
                            "spy_close) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id, day) DO UPDATE SET "
                            "equity = EXCLUDED.equity, cash = EXCLUDED.cash, positions_value = EXCLUDED.positions_value, "
                            "open_positions = EXCLUDED.open_positions, spy_close = EXCLUDED.spy_close",
                            (run_id, bar_day, equity, round(acct["cash"], 2), pv, len(positions), spy))
            note = "; ".join(notes)[:900] if notes else ("paused" if not s["enabled"] else "no changes")
            cur.execute("UPDATE paper_account SET cash = %s, spy_start = %s, last_cycle = %s, last_cycle_note = %s "
                        "WHERE id = 1", (round(acct["cash"], 2), acct["spy_start"], now, note))
            conn.commit()
            return {"ok": True, "notes": notes, "equity": equity, "open_positions": len(positions),
                    "waiting_plans": len(waiting)}
        finally:
            try:
                cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
                conn.commit()
            except Exception:
                pass
    except Exception as exc:
        conn.rollback()
        log.exception("paper cycle failed")
        return {"ok": False, "error": str(exc)[:300]}
    finally:
        conn.close()


def _sessions_to_check(pos: dict, snap: dict, today: date) -> List[dict]:
    """Sessions since the last one checked: missed completed sessions (catch-up after a
    restart) from the daily-bars endpoint, then today's bar from the snapshot."""
    last = pos.get("last_session")
    entry = pos["entry_session"]
    since = (date.fromisoformat(str(last)) if last else entry)
    bars: List[dict] = []
    if since < today - timedelta(days=1):
        bars = [b for b in fetch_daily_bars(pos["symbol"], since) if b["t"] > str(since) and b["t"] < today.isoformat()]
    tb = snap.get("bar")
    if tb and tb["t"] >= str(since):
        bars = [b for b in bars if b["t"] != tb["t"]] + [tb]
    return bars


def _save_position(cur, pos: dict, now: datetime) -> None:
    closed = pos["qty_open"] <= 0
    cur.execute("UPDATE paper_positions SET qty_open = %s, last_price = %s, last_marked = %s, seen_low = %s, "
                "seen_high = %s, sessions_held = %s, last_session = %s, realized_pnl = %s, fees = %s, t1_done = %s, "
                "status = %s, exit_time = %s, exit_reason = %s WHERE position_id = %s",
                (max(pos["qty_open"], 0), pos.get("last_price"), now, pos.get("seen_low"), pos.get("seen_high"),
                 int(pos.get("sessions_held") or 0), pos.get("last_session"), pos.get("realized_pnl") or 0,
                 pos.get("fees") or 0, bool(pos.get("t1_done")), "closed" if closed else "open",
                 now if closed else None, pos.get("exit_reason") if closed else None, pos["position_id"]))


def _close_plan(cur, run_id, trade_id, status, reason, position_id=None) -> None:
    cur.execute("UPDATE paper_plans SET status = %s, reason = %s, position_id = %s WHERE run_id = %s AND trade_id = %s",
                (status, reason, position_id, run_id, trade_id))


# ════════════════════════════════════════════════════════════════════════════
# Admin API helpers (called from backend/main.py, all behind require_admin)
# ════════════════════════════════════════════════════════════════════════════

def summary() -> Dict[str, Any]:
    conn = _db()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        acct = _account(cur)
        conn.commit()
        run_id = acct["run_id"]
        positions = _open_positions(cur, run_id)
        equity = _equity(acct, positions)
        cur.execute("SELECT trade_id, symbol, side, entry_trigger, stop, target, test_bar_date, sessions_waited "
                    "FROM paper_plans WHERE run_id = %s AND status = 'waiting' ORDER BY test_bar_date DESC, symbol",
                    (run_id,))
        waiting = [{"trade_id": r[0], "symbol": r[1], "side": r[2], "entry_trigger": _f(r[3]), "stop": _f(r[4]),
                    "target": _f(r[5]), "test_bar_date": str(r[6]), "sessions_waited": r[7]} for r in cur.fetchall()]
        cur.execute("SELECT position_id, symbol, side, qty_initial, entry_price, entry_time, exit_time, exit_reason, "
                    "realized_pnl, fees, stop FROM paper_positions WHERE run_id = %s AND status = 'closed' "
                    "ORDER BY exit_time DESC", (run_id,))
        closed = []
        for r in cur.fetchall():
            risk_dollars = abs(float(r[4]) - float(r[10])) * int(r[3]) or None
            net = float(r[8] or 0) - float(r[9] or 0)
            per_share = float(r[8] or 0) / int(r[3]) if r[3] else 0.0
            exit_avg = round(float(r[4]) + per_share if r[2] == "Long" else float(r[4]) - per_share, 4)
            closed.append({"position_id": r[0], "symbol": r[1], "side": r[2], "qty": r[3], "entry_price": _f(r[4]),
                           "exit_avg": exit_avg, "entry_time": _iso(r[5]), "exit_time": _iso(r[6]), "exit_reason": r[7],
                           "pnl": round(net, 2), "r_multiple": round(net / risk_dollars, 2) if risk_dollars else None})
        cur.execute("SELECT day, equity, spy_close FROM paper_equity WHERE run_id = %s ORDER BY day", (run_id,))
        curve = [{"day": str(r[0]), "equity": _f(r[1]), "spy": _f(r[2])} for r in cur.fetchall()]
        cur.execute("SELECT status, COUNT(*) FROM paper_plans WHERE run_id = %s GROUP BY status", (run_id,))
        plan_counts = {r[0]: r[1] for r in cur.fetchall()}
        wins = [c for c in closed if c["pnl"] > 0]
        losses = [c for c in closed if c["pnl"] <= 0]
        gross_win, gross_loss = sum(c["pnl"] for c in wins), -sum(c["pnl"] for c in losses)
        peak, max_dd = None, 0.0
        for pt in curve:
            e = pt["equity"] or 0
            peak = e if peak is None or e > peak else peak
            if peak:
                max_dd = max(max_dd, (peak - e) / peak * 100)
        last_spy = next((pt["spy"] for pt in reversed(curve) if pt["spy"]), None)
        open_rows = []
        for p in positions:
            px = p.get("last_price") or p["entry_price"]
            unreal = trade_pnl(p["side"], p["qty_open"], p["entry_price"], px)
            open_rows.append({"symbol": p["symbol"], "side": p["side"], "qty": p["qty_open"],
                              "entry_price": p["entry_price"], "last_price": px, "stop": p["stop"],
                              "target": p["target"], "t1_price": p["t1_price"], "t1_done": bool(p["t1_done"]),
                              "unrealized": unreal, "realized": p["realized_pnl"] or 0,
                              "sessions_held": p["sessions_held"], "time_limit": p["time_limit"],
                              "exit_mode": p["exit_mode"], "entry_time": _iso(p["entry_time"]),
                              "value": round(p["qty_open"] * px, 2)})
        return {"ok": True, "run_id": run_id, "started": _iso(acct["created_at"]),
                "starting_cash": acct["starting_cash"], "cash": round(acct["cash"], 2), "equity": equity,
                "pnl": round(equity - acct["starting_cash"], 2),
                "return_pct": round((equity / acct["starting_cash"] - 1) * 100, 2),
                "spy_return_pct": round((last_spy / acct["spy_start"] - 1) * 100, 2)
                if last_spy and acct["spy_start"] else None,
                "settings": acct["settings"], "last_cycle": _iso(acct["last_cycle"]),
                "last_cycle_note": acct["last_cycle_note"],
                "stats": {"closed_trades": len(closed), "wins": len(wins), "losses": len(losses),
                          "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
                          "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
                          "avg_r": round(sum(c["r_multiple"] or 0 for c in closed) / len(closed), 2) if closed else None,
                          "max_drawdown_pct": round(max_dd, 2), "plans": plan_counts},
                "positions": open_rows, "waiting": waiting, "closed": closed[:200], "curve": curve}
    finally:
        conn.close()


def journal(limit: int = 300) -> Dict[str, Any]:
    conn = _db()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        acct = _account(cur)
        conn.commit()
        cur.execute("SELECT at, symbol, side, action, qty, price, fee, pnl, reason, cash_after FROM paper_fills "
                    "WHERE run_id = %s ORDER BY at DESC LIMIT %s", (acct["run_id"], int(limit)))
        fills = [{"at": _iso(r[0]), "symbol": r[1], "side": r[2], "action": r[3], "qty": r[4], "price": _f(r[5]),
                  "fee": _f(r[6]), "pnl": _f(r[7]), "reason": r[8], "cash_after": _f(r[9])} for r in cur.fetchall()]
        cur.execute("SELECT symbol, side, test_bar_date, status, reason, first_seen FROM paper_plans "
                    "WHERE run_id = %s AND status IN ('skipped','expired','missed') ORDER BY first_seen DESC LIMIT 200",
                    (acct["run_id"],))
        passed = [{"symbol": r[0], "side": r[1], "test_bar_date": str(r[2]), "status": r[3], "reason": r[4],
                   "seen": _iso(r[5])} for r in cur.fetchall()]
        return {"ok": True, "fills": fills, "not_taken": passed}
    finally:
        conn.close()


def save_settings(raw: dict) -> Dict[str, Any]:
    conn = _db()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        acct = _account(cur)
        new = clean_settings(raw, acct["settings"])
        cur.execute("UPDATE paper_account SET settings = %s::jsonb WHERE id = 1", (json.dumps(new),))
        conn.commit()
        return {"ok": True, "settings": new}
    finally:
        conn.close()


def reset(starting_cash: float = DEFAULT_STARTING_CASH) -> Dict[str, Any]:
    """Start a new run. Earlier runs stay in the tables under their run_id."""
    cash = float(starting_cash or DEFAULT_STARTING_CASH)
    if not 1_000 <= cash <= 1_000_000_000:
        return {"ok": False, "error": "Starting cash must be between $1,000 and $1,000,000,000."}
    conn = _db()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        acct = _account(cur)
        now = datetime.now(timezone.utc)
        cur.execute("UPDATE paper_account SET run_id = %s, starting_cash = %s, cash = %s, created_at = %s, "
                    "spy_start = NULL, last_cycle = NULL, last_cycle_note = 'account reset' WHERE id = 1",
                    (acct["run_id"] + 1, cash, cash, now))
        conn.commit()
        return {"ok": True, "run_id": acct["run_id"] + 1, "starting_cash": cash}
    finally:
        conn.close()


def _f(v):
    return float(v) if v is not None else None


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)


# ════════════════════════════════════════════════════════════════════════════
# Background loop
# ════════════════════════════════════════════════════════════════════════════

_loop_started = False


def start_background_loop() -> None:
    """Started once per process from backend startup. Turn off with PAPER_TRADER_LOOP=0."""
    global _loop_started
    if _loop_started or os.getenv("PAPER_TRADER_LOOP", "1") == "0" or not os.getenv("DATABASE_URL"):
        return
    _loop_started = True

    def _loop():
        time.sleep(60)
        while True:
            try:
                now_et = datetime.now(ET)
                if now_et.weekday() < 5 and (9, 30) <= (now_et.hour, now_et.minute) <= (16, 10):
                    run_cycle()
            except Exception:
                log.exception("paper loop")
            time.sleep(CYCLE_SECONDS)

    threading.Thread(target=_loop, name="paper-trader", daemon=True).start()
    log.info("paper trader loop started (every %ss in market hours)", CYCLE_SECONDS)
