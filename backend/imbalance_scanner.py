# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/imbalance_scanner.py
----------------------------
Runs the Imbalance Alert engine over the scan universe, logs every alert, and
(only when switched live) emails it.

Universe: SPY (S&P 500), QQQ (Nasdaq-100) and the Mag 11.

Modes (environment):
  IMBALANCE_SCAN_ENABLED=1   schedule the scan during market hours (default off)
  IMBALANCE_ALERTS_LIVE=1    email alerts to subscribers (default off = shadow:
                             alerts are only logged, with outcomes tracked)
  IMBALANCE_ADMIN_PREVIEW=1  while NOT live, email each alert to the admin
                             addresses only (SIGMALYTIC_ADMIN_EMAILS)

Shadow mode is how the "high-probability" label is earned: every alert is
logged with its entry price, and the 1/3/5/10-day outcome is filled in later.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    from backend import imbalance_engine as ie
except Exception:  # run from inside backend/ (tests, scripts)
    import imbalance_engine as ie

log = logging.getLogger("imbalance_scanner")

INDEX_SYMBOLS = ["SPY", "QQQ"]
MAG_7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
MAG_11 = MAG_7 + ["AMD", "ORCL", "MU", "AVGO"]
UNIVERSE = INDEX_SYMBOLS + MAG_11  # 13 symbols

OUTCOME_HORIZONS = (1, 3, 5, 10)
BARS_LOOKBACK_DAYS = 120


def is_live() -> bool:
    return os.getenv("IMBALANCE_ALERTS_LIVE", "").strip() in ("1", "true", "TRUE", "yes")


def admin_preview() -> bool:
    return os.getenv("IMBALANCE_ADMIN_PREVIEW", "").strip() in ("1", "true", "TRUE", "yes")


def admin_emails() -> List[str]:
    raw = os.getenv("SIGMALYTIC_ADMIN_EMAILS") or os.getenv("SIGMALYTIC_ADMIN_EMAIL") or ""
    return sorted({e.strip().lower() for e in raw.split(",") if e.strip()})


def scan_enabled() -> bool:
    return os.getenv("IMBALANCE_SCAN_ENABLED", "").strip() in ("1", "true", "TRUE", "yes")


# ---------------------------------------------------------------------------
# Log store
# ---------------------------------------------------------------------------

class MemoryLogStore:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def add(self, row: Dict[str, Any]) -> None:
        self.rows.append(dict(row))

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return sorted(self.rows, key=lambda r: r["fired_at"], reverse=True)[:limit]

    def open_rows(self) -> List[Dict[str, Any]]:
        return [r for r in self.rows if r.get("outcomes_complete") is not True]

    def update(self, alert_id: str, fields: Dict[str, Any]) -> None:
        for r in self.rows:
            if r["alert_id"] == alert_id:
                r.update(fields)


class SupabaseLogStore:
    TABLE = "imbalance_alert_log"

    def __init__(self, client: Any) -> None:
        self.sb = client

    @staticmethod
    def _rows(res: Any) -> List[Dict[str, Any]]:
        data = getattr(res, "data", None)
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    def add(self, row: Dict[str, Any]) -> None:
        self.sb.table(self.TABLE).insert(row).execute()

    def recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._rows(self.sb.table(self.TABLE).select("*").order("fired_at", desc=True).limit(limit).execute())

    def open_rows(self) -> List[Dict[str, Any]]:
        return self._rows(self.sb.table(self.TABLE).select("*").eq("outcomes_complete", False).execute())

    def update(self, alert_id: str, fields: Dict[str, Any]) -> None:
        self.sb.table(self.TABLE).update(fields).eq("alert_id", alert_id).execute()


def default_store() -> Any:
    url = os.getenv("SUPABASE_URL", "")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
           or os.getenv("SUPABASE_KEY") or "")
    if url and key:
        try:
            from supabase import create_client
            return SupabaseLogStore(create_client(url, key))
        except Exception as exc:
            log.warning("imbalance log store: Supabase unavailable (%s); using memory", exc)
    return _MEMORY


_MEMORY = MemoryLogStore()


# ---------------------------------------------------------------------------
# Data fetchers (network). Injectable so tests never touch the network.
# ---------------------------------------------------------------------------

def fetch_bars(symbols: List[str]) -> Dict[str, List[dict]]:
    try:
        from backend import broker_market_data as md
    except Exception:
        import broker_market_data as md
    end = datetime.now(timezone.utc)
    return md.fetch_daily_bars(symbols, end - timedelta(days=BARS_LOOKBACK_DAYS), end)


def fetch_options(symbol: str, spot: float) -> Dict[str, Any]:
    """Returns {"opt": gamma-matrix result or None, "call_volume": float|None, "put_volume": float|None}."""
    try:
        try:
            from backend.gamma.alpaca_option_chain_adapter import AlpacaOptionChainAdapter
            from backend.gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine
        except Exception:
            from gamma.alpaca_option_chain_adapter import AlpacaOptionChainAdapter
            from gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine
        chain = AlpacaOptionChainAdapter.fetch_chain(symbol, spot_price=spot, feed=None)
        data = chain.get("options_data") or []
        if not data:
            return {"opt": None, "call_volume": None, "put_volume": None}
        opt = GammaStrikeMatrixEngine.build(options_data=data, symbol=symbol, spot_price=spot)
        calls = sum(float(r.get("volume") or 0) for r in data
                    if str(r.get("option_type", "")).lower() in GammaStrikeMatrixEngine.CALL_VALUES)
        puts = sum(float(r.get("volume") or 0) for r in data
                   if str(r.get("option_type", "")).lower() in GammaStrikeMatrixEngine.PUT_VALUES)
        return {"opt": opt, "call_volume": calls, "put_volume": puts}
    except Exception as exc:  # never fatal
        log.warning("options fetch failed for %s: %s", symbol, exc)
        return {"opt": None, "call_volume": None, "put_volume": None}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _subject(res: Dict[str, Any], entry: float) -> str:
    arrow = "LONG" if res["direction"] == ie.LONG else "SHORT"
    return (f"Imbalance Alert: {res['symbol']} {arrow} "
            f"({res['pillars_agreeing']} of 3 pillars, {res['tier']}) at ${entry:,.2f}")


_PILLAR_LABELS = {"options_flow": "Options flow", "price_structure": "Price structure", "volume_flow": "Volume flow"}


def build_email_html(res: Dict[str, Any], entry: float) -> str:
    rows = ""
    for key, label in _PILLAR_LABELS.items():
        p = res["pillars"][key]
        if not p["available"]:
            vote = "No data"
        else:
            vote = f"{p['direction']} ({p['strength']:.0f})"
        ev = "<br>".join(p["evidence"])
        rows += (f"<tr><td style='padding:6px 10px;font-weight:600'>{label}</td>"
                 f"<td style='padding:6px 10px'>{vote}</td><td style='padding:6px 10px'>{ev}</td></tr>")
    notes = "".join(f"<li>{n}</li>" for n in res["guardrail"]["notes"])
    guard = f"<p><b>Behaviour check:</b></p><ul>{notes}</ul>" if notes else ""
    return (f"<div style='font-family:Arial,sans-serif;max-width:640px'>"
            f"<h2>{_subject(res, entry)}</h2>"
            f"<table style='border-collapse:collapse;width:100%'>{rows}</table>{guard}"
            f"<p style='color:#888;font-size:12px'>Market evidence only. Not investment advice.</p></div>")


def send_alert(res: Dict[str, Any], entry: float) -> bool:
    import asyncio
    import threading
    try:
        try:
            from backend.email_service import dispatch_alert_to_all_users
        except Exception:
            from email_service import dispatch_alert_to_all_users
        meta = {"symbol": res["symbol"], "alert_type": "imbalance", "score": res["strength"],
                "timestamp": datetime.now(timezone.utc)}
        threading.Thread(
            target=lambda: asyncio.run(dispatch_alert_to_all_users(
                alert=meta, subject=_subject(res, entry), html_body=build_email_html(res, entry))),
            daemon=True).start()
        return True
    except Exception as exc:
        log.error("imbalance email failed for %s: %s", res.get("symbol"), exc)
        return False


def send_admin_preview(res: Dict[str, Any], entry: float) -> bool:
    """Email the alert to the admin addresses only. Subscribers receive nothing."""
    import asyncio
    import threading
    recipients = admin_emails()
    if not recipients:
        log.warning("imbalance admin preview: no admin emails configured")
        return False
    try:
        try:
            from backend.email_service import _send_via_resend
        except Exception:
            from email_service import _send_via_resend
        subject = "[ADMIN PREVIEW] " + _subject(res, entry)
        html = build_email_html(res, entry).replace(
            "<h2>", "<p style='color:#b45309'><b>Admin preview. Subscribers did not receive this.</b></p><h2>", 1)

        def _run():
            async def _all():
                for to in recipients:
                    await _send_via_resend(to, subject, html)
            asyncio.run(_all())

        threading.Thread(target=_run, daemon=True).start()
        return True
    except Exception as exc:
        log.error("imbalance admin preview failed for %s: %s", res.get("symbol"), exc)
        return False


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

_GATE = ie.AlertGate()


def run_scan(symbols: Optional[List[str]] = None,
             bars_fn: Callable[[List[str]], Dict[str, List[dict]]] = fetch_bars,
             options_fn: Callable[[str, float], Dict[str, Any]] = fetch_options,
             store: Any = None, gate: Optional[ie.AlertGate] = None,
             live: Optional[bool] = None, send_fn: Callable[[Dict[str, Any], float], bool] = send_alert,
             preview: Optional[bool] = None,
             preview_fn: Callable[[Dict[str, Any], float], bool] = send_admin_preview,
             config: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Dict[str, Any]:
    symbols = [s.upper() for s in (symbols or UNIVERSE)]
    store = store if store is not None else default_store()
    gate = gate if gate is not None else _GATE
    live = is_live() if live is None else live
    preview = admin_preview() if preview is None else preview
    now = time.time() if now is None else now

    bars_by = bars_fn(symbols)
    fired, skipped, errors = [], [], []
    for sym in symbols:
        bars = bars_by.get(sym) or []
        if len(bars) < ie.MIN_BARS:
            skipped.append({"symbol": sym, "reason": f"only {len(bars)} daily bars"})
            continue
        try:
            spot = float(bars[-1]["c"])
            o = options_fn(sym, spot)
            res = ie.evaluate(sym, bars, o.get("opt"), o.get("call_volume"), o.get("put_volume"), config=config)
        except Exception as exc:
            errors.append({"symbol": sym, "error": str(exc)[:200]})
            continue
        if not res["fired"]:
            continue
        if not gate.allow(sym, res["direction"], now):
            skipped.append({"symbol": sym, "reason": "cooldown"})
            continue
        row = {
            "alert_id": uuid.uuid4().hex,
            "symbol": sym,
            "direction": res["direction"],
            "tier": res["tier"],
            "pillars_agreeing": res["pillars_agreeing"],
            "strength": res["strength"],
            "entry_price": spot,
            "fired_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "emailed": False,
            "outcomes": {},
            "outcomes_complete": False,
            "detail": {"pillars": res["pillars"], "agreeing": res["agreeing"]},
        }
        if live:
            row["emailed"] = bool(send_fn(res, spot))
        elif preview:
            row["emailed"] = bool(preview_fn(res, spot))  # admins only
        store.add(row)
        fired.append({"symbol": sym, "direction": res["direction"], "tier": res["tier"], "emailed": row["emailed"]})
    return {"live": live, "admin_preview": bool(preview and not live), "scanned": len(symbols), "fired": fired, "skipped": skipped, "errors": errors}


def update_outcomes(store: Any = None,
                    bars_fn: Callable[[List[str]], Dict[str, List[dict]]] = fetch_bars) -> int:
    """Fill in the 1/3/5/10-day forward move (in the alert's direction) for open log rows."""
    store = store if store is not None else default_store()
    open_rows = store.open_rows()
    if not open_rows:
        return 0
    bars_by = bars_fn(sorted({r["symbol"] for r in open_rows}))
    updated = 0
    for r in open_rows:
        bars = bars_by.get(r["symbol"]) or []
        fired_day = str(r["fired_at"])[:10]
        after = [b for b in bars if str(b.get("t", ""))[:10] > fired_day]
        sign = 1 if r["direction"] == ie.LONG else -1
        entry = float(r.get("entry_price") or 0)
        if entry <= 0:
            continue
        outcomes = dict(r.get("outcomes") or {})
        for h in OUTCOME_HORIZONS:
            if str(h) not in outcomes and len(after) >= h:
                outcomes[str(h)] = round(sign * (float(after[h - 1]["c"]) / entry - 1.0) * 100.0, 3)
        complete = all(str(h) in outcomes for h in OUTCOME_HORIZONS)
        if outcomes != (r.get("outcomes") or {}) or complete != bool(r.get("outcomes_complete")):
            store.update(r["alert_id"], {"outcomes": outcomes, "outcomes_complete": complete})
            updated += 1
    return updated


def track_record(store: Any = None) -> Dict[str, Any]:
    """Hit rate and average move per horizon over all logged alerts."""
    store = store if store is not None else default_store()
    rows = store.recent(5000)
    out: Dict[str, Any] = {"alerts": len(rows), "by_horizon": {}}
    for h in OUTCOME_HORIZONS:
        vals = [float(r["outcomes"][str(h)]) for r in rows if (r.get("outcomes") or {}).get(str(h)) is not None]
        if vals:
            out["by_horizon"][str(h)] = {
                "n": len(vals),
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3),
                "avg_move_pct": round(sum(vals) / len(vals), 3),
            }
    return out
