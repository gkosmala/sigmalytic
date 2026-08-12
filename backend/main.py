# STEP76_CONTROLLED_UNIVERSE_INGEST_ROUTER_IMPORT
try:
    from controlled_universe_ingest_api import controlled_universe_ingest_router
except Exception:
    try:
        from backend.controlled_universe_ingest_api import controlled_universe_ingest_router
    except Exception:
        controlled_universe_ingest_router = None

# STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_IMPORT
try:
    from campaign_pipeline_validation_api import campaign_pipeline_validation_router
except Exception:
    from backend.campaign_pipeline_validation_api import campaign_pipeline_validation_router

"""
SAVE AS:
backend/main.py
"""

# test build filter backend
from fastapi import FastAPI, Body, Request, HTTPException, Header, Depends
from datetime import datetime, timedelta, timezone
import os
import json
import hmac
import requests
import threading
import uuid

from backend.campaign_api import router as campaign_router
from backend.research_api import router as research_router
from backend.intelligence_api import router as intelligence_router
from backend.operator_dominance.operator_dominance_api import router as operator_router

try:
    from backend.admin_api import router as admin_router
except Exception:
    admin_router = None


try:
    from backend.alerts_api import router as alerts_router
except Exception:
    alerts_router = None

try:
    from backend.snapshot_service import snapshot_router
except Exception:
    snapshot_router = None

# === STEP 9C COMMERCIAL ROUTE IMPORTS START ===
# Commercial launch surface routes.
# Billing route mount exposes read/config and Stripe checkout endpoints already
# implemented in backend/billing_router.py. This patch does not create a charge,
# does not execute a payment, and does not write to Supabase by itself.
from backend.billing_router import billing_router
from backend.legal_pages import legal_router
from backend.preferences_router import preferences_router
# FIX (2026-07-28): behavior_router.py is a new module -- the Behavioral
# Intelligence tab and its trade-plan/entry/exit workflow previously called
# five endpoints (/api/behavior/trade-plan, trade-entry, trade-exit, event,
# dashboard/{user_id}) that had no backend implementation anywhere at all,
# confirmed via full route audit. This is not a wiring fix like the others;
# it's a new, working implementation of the feature.
from backend.behavior_router import behavior_router
# === STEP 9C COMMERCIAL ROUTE IMPORTS END ===
app = FastAPI(
    title="Sigmalytic V2",
    version="2.0.0",
)


@app.on_event("startup")
def _start_radar_scheduler_on_boot():
    # PERMANENTLY DISABLED (2026-07-29, confirmed resolved 2026-08-04):
    # the investigation this comment used to describe as "pending" was
    # actually completed the same day it started. Confirmed via direct
    # memory instrumentation and production crash logs: running the full
    # radar scanner (gex_scan/radar_scan/divergence_scan/snapshot_intraday,
    # scanning ~1000 symbols every 5-8 minutes) inside the same process as
    # this web-serving backend caused combined memory use to repeatedly
    # exceed 2GB and crash -- not specifically snapshot_intraday's 300s
    # interval, which turned out to be a red herring; the real cause was
    # the scanner's cumulative memory footprint stacking on top of the
    # backend's own heavy endpoints.
    #
    # The real, working fix (same day): the scanner now runs in its own
    # dedicated Render Background Worker service, sigmalytic-radar-scanner
    # (see tools/render_radar_scanner_worker.py), with its own separate
    # memory entirely apart from this web-serving process. It publishes
    # results to Redis (radar:cache key), which this backend reads via
    # get_radar_scores()'s and other functions' Redis fallback -- this is
    # the same live data source confirmed working correctly throughout
    # 2026-08-04's session (real, current prices and scores for 900+
    # symbols).
    #
    # This function must stay disabled here permanently -- re-enabling it
    # would start the exact same scanner a second time, in this process,
    # reintroducing the original crash risk on top of infrastructure that
    # already works correctly via the separate worker.
    print("[STARTUP] Radar scheduler intentionally disabled on this service -- runs separately via sigmalytic-radar-scanner worker instead", flush=True)


@app.get("/")
def root():
    return {
        "application": "Sigmalytic V2",
        "status": "online",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/health")
def api_health():
    return {"status": "healthy"}


# ── Market Wire ──────────────────────────────────────────────────────────
# Top-of-page ticker: DJIA, S&P 500, Nasdaq, Russell 2000, Gold, Oil,
# Bitcoin. VIX deliberately left out per explicit request -- there's no
# direct way to get the raw VIX index value through Alpaca's standard
# market data; the common proxy (VIXY) tracks VIX *futures*, not the spot
# index, and can diverge meaningfully from the headline VIX number people
# expect, which would be misleading on a ticker with no room to explain
# the distinction.
#
# Indices/commodities use standard, real-world ETF proxies (same
# instruments most retail platforms use for this exact purpose) since
# Alpaca's equities API serves tradable securities, not raw index values:
#   DJIA -> DIA, S&P 500 -> SPY, Nasdaq -> QQQ (Nasdaq-100, the standard
#   proxy -- not the full Nasdaq Composite), Russell 2000 -> IWM,
#   Gold -> GLD, Oil -> USO.
# Bitcoin is genuinely real, not a proxy -- Alpaca has a dedicated crypto
# data API (confirmed: GET /v1beta3/crypto/us/latest/bars).
MARKET_WIRE_SYMBOLS = {
    "DIA": "DJIA",
    "SPY": "S&P 500",
    "QQQ": "Nasdaq",
    "IWM": "Russell 2000",
    "GLD": "Gold",
    "USO": "Oil",
}


@app.get("/api/market-wire")
def get_market_wire():
    # FIX (2026-08-06): confirmed this had zero caching despite being
    # genuinely shared data (identical for every user, not per-symbol
    # or per-user) -- called every ~2s per active user via the
    # frontend's live-tick cycle, making a real, live Alpaca API call
    # every single time. An explicit, known risk was already flagged
    # in earlier session notes ("multiplies with concurrent
    # subscribers") but never actually fixed. Wrapped in the same
    # proven, Redis-backed shared_cache pattern already fixed for
    # campaign_api.py tonight -- a short TTL keeps data reasonably
    # fresh while collapsing what could be many real Alpaca calls per
    # second (across all active users) down to roughly one every 10s,
    # shared across all of them and all worker processes.
    from backend.shared_cache import shared_cache
    return shared_cache.get_or_fetch("market_wire", _get_market_wire_uncached, ttl_seconds=10)


def _get_market_wire_uncached():
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")

    if not key or not secret:
        return {"ok": False, "error": "missing_alpaca_credentials", "items": []}

    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    items = []

    # Equity ETF proxies -- one batched snapshot call for all 6, rather
    # than 6 separate requests. Snapshots bundle the latest trade with
    # the previous day's daily bar, which is what a clean day-over-day
    # % change actually needs (a single latest-bar fetch alone doesn't
    # give a meaningful "change since yesterday's close" figure).
    try:
        r = requests.get(
            f"{base_url}/v2/stocks/snapshots",
            headers=headers,
            params={"symbols": ",".join(MARKET_WIRE_SYMBOLS.keys()), "feed": "sip"},
            timeout=10,
        )
        if r.ok:
            snapshots = r.json() or {}
            for sym, label in MARKET_WIRE_SYMBOLS.items():
                snap = snapshots.get(sym) or {}
                latest_trade = snap.get("latestTrade") or {}
                prev_daily = snap.get("prevDailyBar") or {}
                price = latest_trade.get("p")
                prev_close = prev_daily.get("c")
                change_pct = None
                if price is not None and prev_close:
                    change_pct = round((price - prev_close) / prev_close * 100, 2)
                items.append({
                    "symbol": sym, "label": label, "price": price,
                    "change_pct": change_pct, "asset_class": "equity",
                })
    except Exception as e:
        print(f"[MARKET_WIRE] Equity snapshot fetch failed: {e}", flush=True)

    # Bitcoin -- real, not a proxy, via Alpaca's dedicated crypto endpoint.
    # Uses the last 2 DAILY bars (not latest/bars, which defaults to a
    # minute-level bar) for a meaningful 24h change -- the same kind of
    # comparison the equity side gets from prevDailyBar, not a noisy,
    # tiny minute-to-minute figure.
    #
    # FIX (2026-08-04): user's real API check showed price succeeding
    # but change_pct coming back null -- confirmed the cause: Alpaca's
    # historical bars endpoints often need an explicit start date,
    # limit alone isn't always sufficient to guarantee multiple bars
    # are actually returned (without it, this was apparently only
    # returning a single bar). Added an explicit start (5 days back,
    # comfortable padding past the 2 bars actually needed).
    try:
        crypto_start = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(
            f"{base_url}/v1beta3/crypto/us/bars",
            headers=headers,
            params={"symbols": "BTC/USD", "timeframe": "1Day", "limit": 5, "start": crypto_start},
            timeout=10,
        )
        if r.ok:
            bars = (r.json() or {}).get("bars") or {}
            btc_bars = bars.get("BTC/USD") or []
            if btc_bars:
                latest = btc_bars[-1]
                price = latest.get("c")
                change_pct = None
                if len(btc_bars) >= 2:
                    prev_close = btc_bars[-2].get("c")
                    if price is not None and prev_close:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                items.append({
                    "symbol": "BTC/USD", "label": "Bitcoin", "price": price,
                    "change_pct": change_pct, "asset_class": "crypto",
                })
    except Exception as e:
        print(f"[MARKET_WIRE] Crypto bar fetch failed: {e}", flush=True)

    return {"ok": True, "items": items}


@app.get("/api/stock/{symbol}")
def get_stock_quote(symbol: str):
    """
    Live stock quote endpoint for frontend chart.

    Policy:
    - Alpaca SIP only.
    - No IEX fallback.
    - No synthetic fallback.
    - Does not import radar_service.
    - Does not touch campaign logic.
    """
    sym = (symbol or "").upper().strip()

    if not sym:
        return {
            "ok": False,
            "error": "missing_symbol",
            "source": "none",
            "feed": "sip",
        }

    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")

    if not key or not secret:
        return {
            "ok": False,
            "symbol": sym,
            "error": "missing_alpaca_credentials",
            "source": "alpaca",
            "feed": "sip",
        }

    url = f"{base_url}/v2/stocks/bars/latest"

    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }

    params = {
        "symbols": sym,
        "feed": "sip",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)

        if not r.ok:
            return {
                "ok": False,
                "symbol": sym,
                "error": f"alpaca_sip_http_{r.status_code}",
                "detail": r.text[:300],
                "source": "alpaca",
                "feed": "sip",
            }

        payload = r.json() or {}
        bars = payload.get("bars") or {}
        bar = bars.get(sym)

        if not bar:
            return {
                "ok": False,
                "symbol": sym,
                "error": "no_sip_latest_bar_returned",
                "source": "alpaca",
                "feed": "sip",
            }

        price = bar.get("c")
        volume = bar.get("v")

        if price is None:
            return {
                "ok": False,
                "symbol": sym,
                "error": "sip_bar_missing_close",
                "source": "alpaca",
                "feed": "sip",
            }

        return {
            "ok": True,
            "symbol": sym,
            "price": float(price),
            "volume": int(volume or 0),
            "timestamp": bar.get("t"),
            "source": "alpaca",
            "feed": "sip",
        }

    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "error": str(exc)[:300],
            "source": "alpaca",
            "feed": "sip",
        }


# FIX (2026-07-28): the frontend's fetch_real_candles() has been calling
# this endpoint all along, but it never existed on the backend at all --
# confirmed via production logs showing a consistent 404. This is a real,
# separate gap from tonight's crash/cron investigation, not a regression.
# Built to match the existing /api/stock/{symbol} endpoint's exact style,
# using Alpaca's historical bars endpoint instead of "latest".
# FIX (2026-07-29): the Command Center's "Dynamic Options Matrix" widget
# only ever showed synthetic price-percentage numbers (shared/engine.py's
# get_key_levels), completely unrelated to any real options data, even
# though real Alpaca options data is genuinely wired up and working
# elsewhere (the Campaign Intelligence gamma overlay). This endpoint
# reuses that same real machinery (AlpacaOptionChainAdapter -> live chain
# snapshot -> GammaStrikeMatrixEngine -> real gamma-exposure-based call/
# put walls) for a single live symbol, on demand, so the Command Center
# can show genuinely live options data instead of synthetic math.
@app.get("/api/options/gamma-matrix/{symbol}")
def get_gamma_matrix(symbol: str, spot_price: float = 0.0, feed: str = ""):
    sym = (symbol or "").upper().strip()

    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    if spot_price <= 0:
        return {"ok": False, "symbol": sym, "error": "missing_or_invalid_spot_price"}

    try:
        from backend.gamma.alpaca_option_chain_adapter import AlpacaOptionChainAdapter
        from backend.gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": f"gamma_engine_import_failed: {e}"}

    # FIX (2026-08-12): feed query param added specifically to directly
    # test whether explicitly forcing ?feed=opra changes anything --
    # rather than always letting Alpaca apply its own default silently.
    chain = AlpacaOptionChainAdapter.fetch_chain(sym, spot_price=spot_price, feed=(feed or None))

    if chain.get("status") == "MISSING_ALPACA_CREDENTIALS":
        return {"ok": False, "symbol": sym, "error": "missing_alpaca_credentials"}

    options_data = chain.get("options_data") or []

    if not options_data:
        return {
            "ok": True,
            "symbol": sym,
            "status": chain.get("status", "NO_OPTIONS_DATA"),
            "has_real_data": False,
        }

    result = GammaStrikeMatrixEngine.build(
        options_data=options_data,
        symbol=sym,
        spot_price=spot_price,
    )
    result["ok"] = True
    result["has_real_data"] = True

    # FIX (2026-08-12): diagnostic fields to help distinguish, without
    # needing direct access to the deployed environment, whether
    # missing greeks/IV are caused by an explicit feed override (e.g.
    # ALPACA_OPTIONS_FEED forcing "indicative", which never includes
    # greeks per the FIX comment in alpaca_option_chain_adapter.py) or
    # a genuine, real data gap from Alpaca despite a full OPRA
    # subscription and requesting no specific feed (letting Alpaca
    # apply its own entitlement-aware default).
    contracts_with_iv = sum(
        1 for row in options_data
        if row.get("implied_volatility") is not None and row.get("implied_volatility") > 0
    )
    contracts_with_real_bid_ask = sum(
        1 for row in options_data
        if row.get("bid") is not None and row.get("bid") > 0
        and row.get("ask") is not None and row.get("ask") > 0
    )
    # A few of the highest-volume (most liquid, least likely to be a
    # genuine zero-quote edge case) contracts' actual bid/ask/IV, for
    # direct inspection rather than just an aggregate count.
    sample_liquid = sorted(options_data, key=lambda r: r.get("volume") or 0, reverse=True)[:5]
    result["feed_diagnostics"] = {
        "explicitly_requested_feed": chain.get("feed"),  # None means we let Alpaca choose its own default
        "contracts_total": len(options_data),
        "contracts_with_real_iv": contracts_with_iv,
        "contracts_with_real_bid_ask": contracts_with_real_bid_ask,
        "sample_liquid_contracts": [
            {
                "contract_symbol": r.get("contract_symbol"), "strike": r.get("strike"),
                "volume": r.get("volume"), "bid": r.get("bid"), "ask": r.get("ask"),
                "implied_volatility": r.get("implied_volatility"),
            }
            for r in sample_liquid
        ],
    }

    # Real, market-derived inputs for the Probability Ladder's touch-
    # probability calculation, replacing the prior heuristic score.
    # Returns just the nearest monthly expiration's ATM IV and dte --
    # the frontend already knows its own price levels (kl.breakout
    # etc.) and computes the actual per-level probability itself,
    # avoiding passing price levels back and forth as query params.
    from backend.gamma.touch_probability_engine import TouchProbabilityEngine
    monthly = TouchProbabilityEngine.find_nearest_monthly_expiration(options_data)
    if monthly:
        sigma = TouchProbabilityEngine.atm_implied_volatility(monthly["contracts"], spot_price)
        result["touch_probability_inputs"] = {
            "available": sigma is not None,
            "expiration_date": monthly["expiration_date"],
            "days_to_expiration": monthly["dte"],
            "atm_implied_volatility": round(sigma, 4) if sigma is not None else None,
        }
    else:
        result["touch_probability_inputs"] = {"available": False, "reason": "No monthly expiration in the current chain."}

    return result


# FIX (2026-07-30): extracted to a module-level constant (was previously
# local to get_candles) specifically so tests/test_candle_lookback_window.py
# can import these exact values directly, rather than duplicating them --
# guaranteeing the regression test can never silently drift out of sync
# with the real implementation.
CANDLE_CALENDAR_DAYS_PER_BAR = {
    "1Min": 1/390, "5Min": 1/78, "15Min": 1/26, "1Hour": 1/6.5,
    "1Day": 1.6, "1Week": 8, "1Month": 35,
}


@app.get("/api/research/renko-weis/{symbol}")
def get_renko_weis_verdict(symbol: str):
    """
    FIX (2026-08-09): first wiring of the new, parallel "pure Weis"
    engine (non-repainting Renko brick generation -> wave grouping ->
    scoring, all built and verified earlier tonight) into a real,
    callable endpoint. Command Center is the first tab to use this.

    Deliberately fetches its own DAILY bars here (via the same
    fetch_bars_batch() the Radar scan already uses) rather than
    reusing Command Center's existing `candles`, which are 5-minute
    intraday bars by default -- the engine's ATR-based sizing was
    calibrated for daily volatility (same as the existing, live Renko
    overlay and WeisVerdictEngine), and this platform was explicitly
    scoped to swing trading, not day trading, earlier tonight.
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        from backend.radar_service import fetch_bars_batch
        from backend.research_engine.renko_weis_wave_engine import RenkoWeisWaveEngine

        bars_map = fetch_bars_batch([sym], timeframe="1Day", limit=252)
        bars = bars_map.get(sym) or []

        if len(bars) < 20:
            return {
                "ok": True, "symbol": sym,
                "status": "INSUFFICIENT_HISTORY",
                "bars_available": len(bars),
            }

        engine = RenkoWeisWaveEngine()
        waves = engine.build_waves(bars)
        verdict = engine.evaluate(bars, symbol=sym)
        result = verdict.to_dict()
        result["ok"] = True
        result["status"] = "OK"
        result["bars_used"] = len(bars)
        result["current_wave"] = engine.current_wave_reading(waves)
        return result
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/research/pnf-weis/{symbol}")
def get_pnf_weis_verdict(symbol: str):
    """
    Sixth piece of the new, parallel "pure Weis" engine: the PnF
    counterpart to get_renko_weis_verdict() above, following the same
    pattern exactly (own daily-bar fetch, same error/status shape).

    The underlying PointInTimePnFGenerator was empirically validated
    against a real, trusted PnF reference dataset and confirmed
    already correct (46/46 real, complete columns matched exactly) --
    unlike Renko, no fix was needed before building this scoring layer
    on top of it.
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        from backend.radar_service import fetch_bars_batch
        from backend.research_engine.pnf_weis_engine import PnFWeisEngine

        bars_map = fetch_bars_batch([sym], timeframe="1Day", limit=252)
        bars = bars_map.get(sym) or []

        if len(bars) < 20:
            return {
                "ok": True, "symbol": sym,
                "status": "INSUFFICIENT_HISTORY",
                "bars_available": len(bars),
            }

        engine = PnFWeisEngine()
        columns = engine.build_columns(bars)
        verdict = engine.evaluate(bars, symbol=sym)
        result = verdict.to_dict()
        result["ok"] = True
        result["status"] = "OK"
        result["bars_used"] = len(bars)
        result["current_column"] = engine.current_column_reading(columns)
        result["count_guide"] = engine.count_guide_projection(columns)
        return result
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/research/weis-wave/{symbol}")
def get_weis_wave_verdict(symbol: str):
    """
    Exposes the original, already-validated, time-bar-based
    WeisVerdictEngine (built and empirically validated earlier
    tonight against a real reference dataset: 134 vs. 131 real
    transitions, 78% timing accuracy) for a single symbol, mirroring
    get_renko_weis_verdict()/get_pnf_weis_verdict()'s exact pattern --
    so the time-bar approach can be directly compared against the new
    Renko/PnF-structure approaches on the same, real data.

    Unlike the newer engines, WeisVerdictEngine genuinely requires a
    real pandas DataFrame (not a plain list of dicts) -- converts the
    same batch-fetched bars accordingly before calling it.
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        import pandas as pd
        from backend.radar_service import fetch_bars_batch
        from backend.research_engine.weis_verdict_engine import WeisVerdictEngine

        bars_map = fetch_bars_batch([sym], timeframe="1Day", limit=252)
        bars = bars_map.get(sym) or []

        if len(bars) < 20:
            return {
                "ok": True, "symbol": sym,
                "status": "INSUFFICIENT_HISTORY",
                "bars_available": len(bars),
            }

        df = pd.DataFrame(bars)
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})

        engine = WeisVerdictEngine()
        result = engine.evaluate(df, symbol=sym)
        result["ok"] = True
        result["status"] = "OK"
        result["bars_used"] = len(bars)
        return result
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/candles/{symbol}")
def get_candles(symbol: str, timeframe: str = "5Min", limit: int = 200):
    sym = (symbol or "").upper().strip()

    if not sym:
        return {"ok": False, "error": "missing_symbol", "bars": []}

    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")

    if not key or not secret:
        return {"ok": False, "symbol": sym, "error": "missing_alpaca_credentials", "bars": []}

    url = f"{base_url}/v2/stocks/{sym}/bars"
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }
    # FIX (2026-07-29): user-reported -- switching to the 1D timeframe only
    # ever showed 1 candle (1m/5m/etc worked fine, showing ~90+ candles).
    # This is a documented Alpaca behavior already noted elsewhere in this
    # codebase (radar_service.py's fetch_bars_batch docstring): calling
    # /bars with only timeframe+limit, no explicit start/end window, can
    # silently return just the single most recent bar for daily/weekly
    # timeframes. This endpoint never had that same fix applied. Sizing
    # the lookback window to the requested timeframe + limit so enough
    # calendar time is actually covered.
    _clean_limit = max(1, min(int(limit or 200), 1000))
    # FIX (2026-07-30): user-reported the chart's candles showed a price
    # range wildly different from (and never converging with) the live
    # price, even immediately after a fresh server reboot -- ruling out
    # staleness as the cause. Found a real units error here: these values
    # were meant to size the lookback window for daily/weekly/monthly
    # bars (where each bar genuinely spans about that many calendar
    # days), but the same "~1 day per bar" logic was also applied to
    # intraday timeframes, where many bars fit inside a single trading
    # day (about 78 five-minute bars per 6.5-hour session). That made
    # "5Min": 1 request roughly a 210-calendar-day window for 200 bars,
    # when 200 five-minute bars only need about 3-4 calendar days. If
    # Alpaca returns bars oldest-first within that window and caps at
    # the limit, the result is genuinely old data (whatever the price
    # was ~7 months ago) with a small enough count to look plausible,
    # rather than an obvious empty/error response -- exactly the
    # sustained, reboot-proof mismatch reported. Corrected to reflect
    # real trading-bars-per-day for each intraday granularity.
    _calendar_days_per_bar = CANDLE_CALENDAR_DAYS_PER_BAR.get(timeframe, 1)
    _lookback_days = max(5, int(_clean_limit * _calendar_days_per_bar) + 10)
    _end_dt = datetime.utcnow() + timedelta(days=1)
    _start_dt = _end_dt - timedelta(days=_lookback_days)

    params = {
        "timeframe": timeframe,
        "limit": _clean_limit,
        # FIX (2026-07-30): user-reported the chart's candles didn't
        # match the live price -- a large, sustained gap, not just the
        # last candle being one bar stale. Root cause: this endpoint
        # requested feed="sip" for historical bars, while the live price
        # ticker (confirmed by the "ALPACA IEX" header badge) uses feed=
        # iex. We already confirmed earlier tonight (campaign discovery
        # engine's 401s) that this account's Alpaca plan doesn't have
        # full real-time SIP authorization -- SIP data can come back
        # valid but meaningfully delayed rather than erroring outright,
        # which would produce exactly this kind of sustained, silent
        # divergence between the chart and the live price rather than
        # an obvious failure. Using the same feed (iex) for both closes
        # that gap entirely rather than just reducing it.
        "feed": "iex",
        "adjustment": "raw",
        "start": _start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": _end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        # FIX (2026-07-30, follow-up): confirmed via the user checking
        # this endpoint's raw response directly that even after the
        # window-sizing and feed fixes above, the returned bars still
        # stopped 8 days before "now" -- not a small lag. Root cause,
        # confirmed against Alpaca's own docs: this API sorts "asc"
        # (oldest-first) by default. A 12-day window can contain far
        # more 5-minute bars (~936) than our limit=200 cap, so with the
        # default ascending sort we were only ever getting the OLDEST
        # ~200 bars within the window -- roughly the first 2.5 trading
        # days of it -- never reaching anywhere near the present.
        # Requesting sort=desc gets the most recent `limit` bars instead
        # (reversed back to chronological order below, since the chart
        # expects oldest-to-newest left-to-right).
        "sort": "desc",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)

        if not r.ok:
            return {
                "ok": False,
                "symbol": sym,
                "error": f"alpaca_bars_http_{r.status_code}",
                "detail": r.text[:300],
                "bars": [],
            }

        payload = r.json() or {}
        raw_bars = payload.get("bars") or []

        bars = [
            {
                "o": b.get("o"),
                "h": b.get("h"),
                "l": b.get("l"),
                "c": b.get("c"),
                "v": b.get("v"),
                "t": b.get("t"),
            }
            for b in raw_bars
            if isinstance(b, dict)
        ]
        # Requested sort=desc (most recent first) above -- reverse back
        # to chronological (oldest-to-newest) order for the chart.
        bars.reverse()

        return {
            "ok": True,
            "symbol": sym,
            "timeframe": timeframe,
            "bars": bars,
            "source": "alpaca",
        }

    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "error": str(exc)[:300],
            "bars": [],
        }


# FIX (2026-07-28): journal_router (trade_journal_api.py) and radar_router
# (radar_service.py) both define real, working handlers for these three
# routes -- but neither router was ever actually included in this app.
# Confirmed via production logs showing consistent 404s, and via grep
# finding zero app.include_router(...) calls for either router anywhere
# in this file. Rather than include the whole router (which may have
# other routes not yet audited for this app's specific conventions),
# these add matching compatibility routes here, same pattern as the
# other *_compat routes in this file, delegating to the real underlying
# functions those routers already call.
@app.get("/api/journal/trades")
def journal_trades_compat(request: Request, status: str = None, limit: int = 100):
    try:
        from backend.supabase_isolation import get_user_id_from_request
        from backend.trade_journal_service import get_journal_entries

        user_id = get_user_id_from_request(request)
        trades = get_journal_entries(user_id, status=status, limit=limit)
        return {"trades": trades, "count": len(trades), "user_id": user_id}
    except Exception as exc:
        return {"trades": [], "count": 0, "error": str(exc)[:300]}


@app.get("/api/journal/profile")
def journal_profile_compat(request: Request):
    try:
        from backend.supabase_isolation import get_user_id_from_request
        from backend.trade_journal_service import get_trader_profile

        user_id = get_user_id_from_request(request)
        return get_trader_profile(user_id)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


@app.get("/api/radar/divergence")
def radar_divergence_compat():
    try:
        from backend.radar_service import get_divergence_watchlist
        return get_divergence_watchlist()
    except Exception as exc:
        return {"count": 0, "symbols": [], "error": str(exc)[:300]}


@app.get("/api/behavior/open-trade/{user_id}")
def get_open_trade(user_id: str):
    """
    Safe placeholder for Command Center active-trade lookup.

    Returns an empty object when no active trade is open.
    This prevents repeated 404 logs without touching campaigns, SIP, Admin, Radar, or scoring.
    """
    return {}


# ── Admin/staff access control ──────────────────────────────────────────
# SECURITY FIX (2026-08-03): every /api/admin/* endpoint, plus the
# read-only diagnostic endpoints that feed the frontend's Admin tab, had
# NO server-side authentication at all. The frontend's is_admin(session)
# check only controlled whether the UI *displayed* this content -- it did
# nothing to stop anyone (subscriber or otherwise, no login required at
# all) from calling these URLs directly and viewing or triggering them.
# Some of these are action-triggering endpoints (run-full-nightly,
# trigger-eod-audit), not just data reads, making this a real, serious
# gap. This dependency verifies the request's Bearer token against
# Supabase directly (never trusts a client-supplied email) and checks the
# resulting verified email against an authorized admin/staff allowlist.
def _get_admin_emails() -> set:
    """
    Comma-separated list of authorized admin/staff emails. Supports
    multiple people (not just a single owner), per explicit request.
    Falls back to the single legacy SIGMALYTIC_ADMIN_EMAIL var too, so
    a deployment with only that one set still works.
    """
    raw = os.getenv("SIGMALYTIC_ADMIN_EMAILS") or os.getenv("SIGMALYTIC_ADMIN_EMAIL") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def require_admin(authorization: str = Header(default="")) -> str:
    """
    FastAPI dependency: raises 401/403 unless the request's Bearer token
    belongs to a verified, authorized admin/staff email. Returns the
    verified email on success, for use/logging in the endpoint if needed.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    admin_emails = _get_admin_emails()
    if not admin_emails:
        # No admin emails configured at all -- fail closed, not open.
        raise HTTPException(status_code=503, detail="Admin access is not configured on this server.")

    supabase_url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or os.environ.get("VITE_SUPABASE_URL")
    )
    supabase_anon_key = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not supabase_url or not supabase_anon_key:
        raise HTTPException(status_code=503, detail="Admin access verification is not configured on this server.")

    try:
        r = requests.get(
            f"{supabase_url}/auth/v1/user",
            headers={"apikey": supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Could not verify admin token right now.")

    if not r.ok:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    verified_email = (r.json() or {}).get("email", "").strip().lower()
    if not verified_email or verified_email not in admin_emails:
        raise HTTPException(status_code=403, detail="Admin access only.")

    return verified_email


@app.get("/api/admin/generate-report")
def generate_report_now(date: str = None, _admin: str = Depends(require_admin)):
    """
    Manually triggers report generation for a given date (YYYY-MM-DD),
    defaulting to today (UTC) if not specified. Used both for the
    initial backfill (generating the first report for a past date) and
    as a manual/emergency trigger outside the normal daily cron schedule.

    FIX (2026-08-02): user reported repeated regenerations of the same
    date never reflecting the latest code, even with the deploy
    confirmed live and a build marker proving the new code was
    genuinely running elsewhere -- but the stored report content
    stayed on an old version regardless. A plausible explanation:
    browsers can cache a GET request's response, and this endpoint had
    no explicit cache-control headers telling it not to. Repeated
    visits to the exact same URL could have been served straight from
    browser cache, never actually reaching this function again at all,
    which would explain everything observed. Explicit no-cache headers
    added defensively; this is a real gap regardless of whether it was
    the specific cause here.
    """
    from fastapi.responses import JSONResponse as _JSONResponse

    try:
        from backend.reports_engine import generate_and_store_report
        result = generate_and_store_report(date)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:500]}

    return _JSONResponse(
        content=result,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/heatmap/data")
def heatmap_data(timeframe: str = "daily"):
    """
    Sector/Industry Heat Map data -- real Russell 1000 sector/industry
    classification (sourced directly from iShares' own official fund
    holdings export) grouped and colored by real price performance at
    the requested time frame (hourly, daily, weekly, monthly).

    FIX (2026-08-06): confirmed this had zero caching (the response
    headers even explicitly disabled browser-level caching too),
    despite computing genuinely shared, identical data per timeframe
    for every user -- and taking up to 90 seconds per the frontend's
    own timeout. If multiple users switch to this tab around the same
    time, this could trigger multiple redundant, expensive
    computations simultaneously (more likely now with 2 worker
    processes able to genuinely serve concurrent users). Wrapped in
    the same proven shared_cache pattern, keyed per timeframe since
    different timeframes have different data. Longer TTL (90s) than
    market-wire since sector/industry price performance doesn't need
    second-level freshness the way live quotes do.
    """
    from fastapi.responses import JSONResponse as _JSONResponse
    from backend.shared_cache import shared_cache

    def _compute():
        try:
            from backend.heatmap_engine import build_heatmap_data
            return build_heatmap_data(timeframe)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500], "symbols": []}

    result = shared_cache.get_or_fetch(f"heatmap_data_{timeframe}", _compute, ttl_seconds=90)

    return _JSONResponse(
        content=result,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/reports/list")
def reports_list():
    """Returns every date that currently has a stored daily report, newest first."""
    from fastapi.responses import JSONResponse as _JSONResponse

    try:
        from backend.reports_engine import list_available_reports
        result = {"ok": True, "dates": list_available_reports()}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:500], "dates": []}

    return _JSONResponse(
        content=result,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/reports/{report_date}")
def reports_get(report_date: str):
    """
    Returns the stored HTML report for a specific date.

    FIX (2026-08-02): the generate-report endpoint got explicit
    no-cache headers earlier, but this read endpoint -- the one
    actually being checked repeatedly to verify a regeneration took
    effect -- was missed. If a browser cached a response from this
    exact URL before, checking it again could keep showing the old
    cached content even after a genuinely successful regeneration on
    the backend, which would look exactly like the regeneration itself
    wasn't working.
    """
    from fastapi.responses import JSONResponse as _JSONResponse

    try:
        from backend.reports_engine import get_report_html
        html_doc = get_report_html(report_date)
        if not html_doc:
            result = {"ok": False, "error": f"No report found for {report_date}"}
        else:
            result = {"ok": True, "date": report_date, "html": html_doc}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:500]}

    return _JSONResponse(
        content=result,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/reports/{report_date}/pdf")
def reports_get_pdf(report_date: str, download: bool = False):
    """
    Returns the stored report for a specific date as a PDF.

    FIX (2026-07-31): user reported the downloaded PDF looked visibly
    different from the on-screen HTML view (which uses full real-browser
    rendering). Root cause: xhtml2pdf has much more limited CSS support
    than a real browser -- confirmed earlier by warnings it couldn't
    parse letter-spacing at all. Tested WeasyPrint directly against our
    actual report HTML/CSS: renders with zero warnings, meaningfully
    closer to real browser output. Now the primary renderer, with a
    fallback to xhtml2pdf if WeasyPrint's native library dependencies
    (Pango/Cairo) aren't available in this specific deploy environment --
    couldn't fully verify that from a sandbox, so this fails safely
    rather than risking another crashed-on-deploy scenario.

    Defaults to inline disposition, so the browser's native PDF viewer
    renders it directly when embedded in an iframe (matching the User
    Guide tab's behavior) -- pass ?download=true for attachment
    disposition instead, which the frontend's separate Download PDF
    button uses. Both are needed: browsers generally ignore the HTML
    <a download> attribute for cross-origin links (this endpoint is on
    a different origin than the frontend), so forcing an actual
    download for that button has to happen via this header instead.
    """
    from fastapi.responses import Response as _FastAPIResponse
    import io

    try:
        from backend.reports_engine import get_report_html
        html_doc = get_report_html(report_date)
        if not html_doc:
            return _FastAPIResponse(
                content=f"No report found for {report_date}",
                status_code=404,
            )

        pdf_bytes = None
        render_error = None

        try:
            from weasyprint import HTML as _WeasyHTML
            pdf_bytes = _WeasyHTML(string=html_doc).write_pdf()
        except Exception as exc:
            render_error = f"weasyprint_failed: {exc}"

        if pdf_bytes is None:
            try:
                from xhtml2pdf import pisa
                buf = io.BytesIO()
                result = pisa.CreatePDF(html_doc, dest=buf)
                if not result.err:
                    pdf_bytes = buf.getvalue()
                else:
                    render_error = (render_error or "") + " | xhtml2pdf_failed"
            except Exception as exc:
                render_error = (render_error or "") + f" | xhtml2pdf_failed: {exc}"

        if pdf_bytes is None:
            return _FastAPIResponse(
                content=f"PDF conversion failed: {render_error}",
                status_code=500,
            )

        disposition = "attachment" if download else "inline"
        return _FastAPIResponse(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'{disposition}; filename="Sigmalytic_Daily_Report_{report_date}.pdf"'
            },
        )
    except Exception as exc:
        return _FastAPIResponse(content=str(exc)[:500], status_code=500)


@app.delete("/api/admin/reports/{report_date}")
async def admin_delete_report(report_date: str, _admin: str = Depends(require_admin)):
    """
    FIX (2026-08-09): user asked how to remove a report from the
    Reports tab -- there was no way to at all. Admin-only (this
    permanently removes a report, an irreversible, destructive
    action) and DELETE, not GET/POST, matching the actual HTTP
    semantics of what this does.
    """
    from backend.reports_engine import delete_report

    try:
        result = delete_report(report_date)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/admin/trigger-eod-audit")
def trigger_eod_audit(_admin: str = Depends(require_admin)):
    # FIX (2026-07-29): user wanted to manually trigger run_eod_audit()
    # (normally scheduled nightly at 8:30 PM ET) right now, to refresh
    # the Intelligence Change Detector tab's stale data without waiting.
    # The radar scanner runs in its own separate Background Worker
    # service with no public HTTP endpoint -- this just sets a Redis
    # flag that worker checks every 20s (see manual_trigger_check in
    # radar_service.py's start_radar_scheduler), rather than trying to
    # reach that service directly.
    try:
        from backend.radar_service import _redis_client
        if not _redis_client:
            return {"ok": False, "error": "Redis not configured"}
        _redis_client.set("trigger:eod_audit", "1", ex=600)
        return {
            "ok": True,
            "message": "EOD audit trigger set. The radar scanner worker checks for "
                       "this every 20 seconds -- check its logs in a minute or two "
                       "for 'Manual EOD audit trigger received'.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


@app.get("/api/admin/bme-memory-status")
def bme_memory_status(_admin: str = Depends(require_admin)):
    """
    Real, direct diagnostic for the BME (Behavioral Memory Engine)
    bank's actual current state -- confirmed get_memory_status()
    (backend/behavioral_memory.py) existed but was never exposed
    anywhere, meaning there was no direct way to verify whether
    "Deep engine confirms radar (+0.0)" for a given symbol reflects
    genuine NO_MEMORY (the symbol simply hasn't been trained yet --
    expected, temporary) versus a deeper, persistent bug in the
    memory persistence fix itself.
    """
    try:
        from backend.behavioral_memory import get_memory_status
        status = get_memory_status()
        return {"ok": True, **status}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/admin/engine-status")
def engine_status(_admin: str = Depends(require_admin)):
    """
    FIX (2026-08-05): this endpoint used to return a hardcoded dict
    with every single engine marked True, regardless of whether it was
    actually wired to anything -- confirmed directly: several of these
    (sizing_engine, ods_engine, decay_monitor, portfolio_intelligence)
    were completely disconnected from the live app until tonight's
    audit found and fixed them, yet this status endpoint claimed they
    were already working the whole time. That's false status
    reporting on exactly the kind of dashboard an admin would trust to
    know what's real.

    Now performs two genuinely distinct checks per engine:
      - importable: does the module/function actually import without
        error right now (a real, live check, not assumed)
      - wired: is it confirmed connected to an actual endpoint a user
        or admin can call, based on tonight's direct verification --
        not just "the file exists and imports cleanly", which several
        of these entries proved is not the same thing at all.
    """
    def _check(label, import_fn, wired):
        try:
            import_fn()
            return {"importable": True, "wired": wired}
        except Exception as e:
            return {"importable": False, "wired": False, "error": str(e)[:150]}

    return {
        "signal_birth_engine": _check(
            "signal_birth_engine",
            lambda: __import__("backend.campaign_engine.campaign_discovery_engine", fromlist=["CampaignDiscoveryEngine"]),
            wired=True,  # confirmed: runs nightly via sigmalytic-nightly-campaign-refresh cron
        ),
        "wyckoff_verdict_engine": _check(
            "wyckoff_verdict_engine",
            lambda: __import__("backend.research_engine.wyckoff_verdict_engine", fromlist=["WyckoffVerdictEngine"]),
            wired=True,  # confirmed: GET /api/radar/symbol/{symbol}/wyckoff-verdict, added and tested later tonight
        ),
        "livermore_verdict_engine": _check(
            "livermore_verdict_engine",
            lambda: __import__("backend.operator_dominance.livermore_score_engine", fromlist=["compute_livermore_score"]),
            wired=True,  # confirmed: GET /api/campaigns/{symbol}/dominance, added and tested tonight
        ),
        "weis_verdict_engine": _check(
            "weis_verdict_engine",
            lambda: __import__("backend.structural.weis_wave_engine", fromlist=["WeisWaveEngine"]),
            wired=False,
        ),
        "campaign_pipeline": _check(
            "campaign_pipeline",
            lambda: __import__("backend.campaign_engine.nightly_campaign_pipeline", fromlist=["run_nightly_campaign_pipeline"]),
            wired=True,  # confirmed: runs nightly via sigmalytic-nightly-campaign-refresh cron
        ),
        "ods_engine": _check(
            "ods_engine",
            lambda: __import__("backend.operator_dominance.livermore_score_engine", fromlist=["compute_livermore_score"]),
            wired=True,
        ),
        "decay_monitor": _check(
            "decay_monitor",
            lambda: __import__("backend.intelligence.signal_decay_monitor", fromlist=["run_decay_monitoring_cycle"]),
            wired=True,  # confirmed: POST /api/admin/run-decay-monitor, added and tested tonight
        ),
        "portfolio_intelligence": _check(
            "portfolio_intelligence",
            lambda: __import__("backend.intelligence.portfolio_intelligence_engine", fromlist=["run_portfolio_intelligence_cycle"]),
            wired=True,  # confirmed: POST /api/admin/run-portfolio-rankings, added and tested tonight
        ),
        "sizing_engine": _check(
            "sizing_engine",
            lambda: __import__("backend.intelligence.position_sizing_engine", fromlist=["compute_position_size"]),
            wired=True,  # confirmed: GET /api/radar/symbol/{symbol}/sizing, added and tested tonight
        ),
        "subscriber_alerts": _check(
            "subscriber_alerts",
            lambda: __import__("backend.intelligence.subscriber_alerts", fromlist=["send_campaign_birth_alerts"]),
            wired=True,  # confirmed: POST /api/admin/send-subscriber-alerts, added and tested later tonight
                         # (the actual email-send bug -- a disabled stub silently claiming success -- was
                         # also fixed later tonight; see backend/intelligence/subscriber_alerts.py)
        ),
        "campaign_outcome": _check(
            "campaign_outcome",
            lambda: __import__("backend.intelligence.campaign_outcome_engine", fromlist=["run_campaign_outcome_cycle"]),
            wired=True,  # confirmed: POST /api/admin/run-campaign-outcome, added and tested later tonight
        ),
        "state_transition_engine": _check(
            "state_transition_engine",
            lambda: __import__("backend.intelligence.state_transition_engine", fromlist=["run_state_transition_cycle"]),
            wired=True,  # confirmed: POST /api/admin/run-state-transition, added and tested later tonight --
                         # a real dependency of campaign_outcome (feeds its transition probability inputs)
        ),
        "analog_engine": _check(
            "analog_engine",
            lambda: __import__("backend.analog_engine.analog_engine", fromlist=["find_analogs"]),
            wired=True,  # confirmed: GET /api/campaigns/{symbol}/analogs, added and tested later tonight
        ),
        "campaign_closure_engine": _check(
            "campaign_closure_engine",
            lambda: __import__("backend.intelligence.campaign_closure_engine", fromlist=[""]),
            wired=True,  # confirmed: POST /api/admin/run-closure-engine, already wired before tonight,
                         # frontend Admin button added later tonight
        ),
    }



# SIGMALYTIC_ASYNC_NIGHTLY_JOB_TRACKING
# The nightly pipeline can take several minutes to run. Calling it via a
# single blocking HTTP request risks Render's own edge proxy returning a
# 502 before the backend has actually finished -- even though the backend
# keeps working in the background regardless. This tracks jobs in memory
# so the POST route can return immediately, with a separate status route
# for the caller to poll.
# FIX (2026-07-27): job status was stored in a plain in-memory Python
# dict, living inside whichever single process created the job. Real
# production logs showed /api/admin/nightly-status/{job_id} returning
# 404 repeatedly for a job that genuinely existed -- because the status
# check landed on a different process than the one that created the job
# (a worker restart, or more than one worker, breaks this immediately).
# This replaces the in-memory dict with Redis-backed storage, so job
# status is found correctly regardless of which process handles which
# request. Falls back to the original in-memory behavior if Redis isn't
# configured/reachable -- this never becomes a hard dependency.
#
# Verified: a completely separate instance (simulating a different
# worker process) correctly reads a job created by another instance --
# this is the exact cross-process scenario that was failing in
# production, reproduced and confirmed fixed before this was applied.
class _NightlyJobStore:
    def __init__(self, redis_url=None, key_prefix="sigmalytic_nightly_job:", ttl_seconds=86400):
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._memory_lock = threading.Lock()
        self._memory_store = {}

        self._redis_client = None
        resolved_url = redis_url or os.getenv("REDIS_URL")
        if resolved_url:
            try:
                import redis as _redis_module
                client = _redis_module.from_url(resolved_url, socket_connect_timeout=2, socket_timeout=2)
                client.ping()
                self._redis_client = client
            except Exception:
                self._redis_client = None

    @property
    def backend(self):
        return "redis" if self._redis_client is not None else "memory"

    def create(self, job_id: str, data: dict):
        self._write(job_id, data)

    def update(self, job_id: str, **fields):
        current = self.get(job_id) or {}
        current.update(fields)
        self._write(job_id, current)

    def get(self, job_id: str):
        if self._redis_client is not None:
            try:
                raw = self._redis_client.get(f"{self._key_prefix}{job_id}")
                return json.loads(raw) if raw is not None else None
            except Exception:
                pass
        with self._memory_lock:
            return self._memory_store.get(job_id)

    def _write(self, job_id: str, data: dict):
        if self._redis_client is not None:
            try:
                self._redis_client.set(
                    f"{self._key_prefix}{job_id}", json.dumps(data), ex=self._ttl_seconds
                )
                return
            except Exception:
                pass
        with self._memory_lock:
            self._memory_store[job_id] = data


_NIGHTLY_JOBS = _NightlyJobStore()


def _alert_nightly_job_failure(reason: str):
    """
    Sends an admin alert for a nightly job failure. Wrapped so that any
    problem with the alerting system itself (missing config, network
    issue, import failure) can never affect the job status tracking that
    already happened above this call.
    """
    try:
        from backend.email_service import send_admin_alert_sync
        send_admin_alert_sync(
            subject="Nightly campaign pipeline failed",
            message=f"The nightly campaign refresh job failed.<br><br>Reason: {reason}",
            alert_key="nightly_cron_failure",
        )
    except Exception:
        pass


def _run_nightly_job_in_background(job_id: str, run_kwargs: dict):
    _NIGHTLY_JOBS.update(job_id, status="running")

    try:
        from backend.campaign_engine import nightly_campaign_pipeline as pipeline

        runner = None
        for name in [
            "run_nightly_campaign_pipeline",
            "run_campaign_pipeline",
            "run_nightly_pipeline",
            "main",
        ]:
            if hasattr(pipeline, name):
                runner = getattr(pipeline, name)
                break

        if runner is None:
            error_msg = "No runner function found in nightly_campaign_pipeline.py"
            _NIGHTLY_JOBS.update(
                job_id, status="failed", error=error_msg,
                finished_at=datetime.utcnow().isoformat(),
            )
            _alert_nightly_job_failure(error_msg)
            return

        pipeline_result = runner(**run_kwargs)

        _NIGHTLY_JOBS.update(
            job_id, status="completed",
            result={"runner": runner.__name__, "result": pipeline_result},
            finished_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        _NIGHTLY_JOBS.update(
            job_id, status="failed", error=str(e),
            finished_at=datetime.utcnow().isoformat(),
        )
        _alert_nightly_job_failure(str(e))


@app.post("/api/admin/run-full-nightly")
def run_full_nightly(request: Request, payload: dict = Body(default=None), _admin: str = Depends(require_admin)):
    payload = payload or {}

    # SIGMALYTIC_RFA11_AUTHENTICATED_NIGHTLY_CRON_START
    # This route is intentionally protected because it can persist refreshed
    # campaign rows through CampaignStore. The cron caller supplies the shared
    # secret in an HTTP header. The token value is never returned or logged.
    cron_enabled = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_ENABLED") or "").strip().lower()
    if cron_enabled not in {"1", "true", "yes", "enabled", "on"}:
        raise HTTPException(
            status_code=403,
            detail={
                "ok": False,
                "error": "nightly_campaign_cron_disabled",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    expected_token = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_TOKEN") or "").strip()
    provided_token = (
        request.headers.get("x-sigmalytic-cron-token")
        or request.headers.get("x-render-cron-token")
        or ""
    ).strip()

    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "missing_server_cron_token_configuration",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": "unauthorized_nightly_campaign_cron_request",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )
    # SIGMALYTIC_RFA11_AUTHENTICATED_NIGHTLY_CRON_END

    requested_symbols = (
        payload.get("symbols")
        or payload.get("tickers")
        or payload.get("symbol")
        or []
    )

    if isinstance(requested_symbols, str):
        requested_symbols = [
            item.strip().upper()
            for item in requested_symbols.split(",")
            if item.strip()
        ]

    run_kwargs = {}

    if requested_symbols:
        run_kwargs["symbols"] = requested_symbols

    if payload.get("max_symbols") is not None:
        run_kwargs["max_symbols"] = payload.get("max_symbols")

    if payload.get("bar_limit") is not None:
        run_kwargs["bar_limit"] = payload.get("bar_limit")

    if payload.get("timeframe") is not None:
        run_kwargs["timeframe"] = payload.get("timeframe")

    job_id = str(uuid.uuid4())

    started_at = datetime.utcnow().isoformat()
    _NIGHTLY_JOBS.create(job_id, {
        "status": "queued",
        "started_at": started_at,
        "request": {
            "symbols": requested_symbols,
            "max_symbols": payload.get("max_symbols"),
            "bar_limit": payload.get("bar_limit"),
            "timeframe": payload.get("timeframe"),
        },
    })
    # No manual count-based bounding needed anymore -- Redis entries
    # expire on their own after 24 hours (ttl_seconds on _NightlyJobStore).
    # The in-memory fallback path (only used if Redis is unreachable) can
    # grow unbounded for the lifetime of one process, but that's the same
    # degraded-but-functional behavior as before Redis was added.

    thread = threading.Thread(
        target=_run_nightly_job_in_background,
        args=(job_id, run_kwargs),
        daemon=True,
    )
    thread.start()

    # Returns immediately -- this is the whole point. The actual pipeline
    # keeps running in the background regardless of how long it takes,
    # and cannot be interrupted by a proxy-level response timeout since
    # nothing is waiting on this HTTP response.
    return {
        "ok": True,
        "status": "started",
        "job_id": job_id,
        "started_at": started_at,
        "poll_url": f"/api/admin/nightly-status/{job_id}",
    }


@app.get("/api/admin/nightly-status/{job_id}")
def nightly_status(request: Request, job_id: str, _admin: str = Depends(require_admin)):
    # Same shared-secret protection as the route that creates jobs --
    # job status can reveal campaign pipeline internals, so this isn't
    # left open.
    expected_token = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_TOKEN") or "").strip()
    provided_token = (
        request.headers.get("x-sigmalytic-cron-token")
        or request.headers.get("x-render-cron-token")
        or ""
    ).strip()

    if not expected_token or not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": "unauthorized_nightly_campaign_cron_request",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    job = _NIGHTLY_JOBS.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": "unknown_job_id", "job_id": job_id},
        )

    return {"ok": True, "job_id": job_id, **job}


@app.post("/api/admin/refresh-weis-gamma-evidence")
def refresh_weis_gamma_evidence(payload: dict = Body(default=None), _admin: str = Depends(require_admin)):
    payload = payload or {}

    requested_symbols = (
        payload.get("symbols")
        or payload.get("tickers")
        or payload.get("symbol")
        or []
    )

    if isinstance(requested_symbols, str):
        requested_symbols = [
            item.strip().upper()
            for item in requested_symbols.split(",")
            if item.strip()
        ]
    else:
        requested_symbols = [
            str(item or "").strip().upper()
            for item in requested_symbols
            if str(item or "").strip()
        ]

    timeframe = str(payload.get("timeframe") or "DAILY").upper()
    max_symbols = int(payload.get("max_symbols") or len(requested_symbols) or 10)
    bar_limit = int(payload.get("bar_limit") or 252)

    results = {
        "ok": True,
        "started_at": datetime.utcnow().isoformat(),
        "request": {
            "symbols": requested_symbols,
            "timeframe": timeframe,
            "max_symbols": max_symbols,
            "bar_limit": bar_limit,
        },
        "refreshed": [],
        "skipped": [],
        "errors": [],
    }

    try:
        from backend.campaign_engine.campaign_store import CampaignStore
        from backend.campaign_engine.campaign_discovery_engine import CampaignDiscoveryEngine
        from backend.campaign_engine.campaign_evidence_builder import CampaignEvidenceBuilder

        store = CampaignStore()

        if not store.configured():
            results["ok"] = False
            results["errors"].append({
                "status": "NO_DATABASE",
                "message": "CampaignStore is not configured.",
            })
            results["finished_at"] = datetime.utcnow().isoformat()
            return results

        discovery = CampaignDiscoveryEngine(
            store=store,
            timeframe=timeframe,
            max_symbols=max_symbols,
            bar_limit=bar_limit,
        )

        discovery.option_chain_fetch_count = 0

        active_campaigns = []

        if requested_symbols:
            for symbol in requested_symbols[:max_symbols]:
                active_campaigns.extend(
                    store.get_active_campaigns(symbol=symbol, timeframe=timeframe)
                )
        else:
            active_campaigns = store.get_active_campaigns(timeframe=timeframe)[:max_symbols]

        seen = set()
        unique_campaigns = []

        for campaign in active_campaigns:
            key = (
                str(campaign.get("symbol") or "").upper(),
                str(campaign.get("timeframe") or timeframe).upper(),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_campaigns.append(campaign)

        refresh_symbols = [
            str(campaign.get("symbol") or "").upper()
            for campaign in unique_campaigns
            if str(campaign.get("symbol") or "").strip()
        ]

        bar_records = discovery.build_records_from_universe(symbols=refresh_symbols)

        record_by_symbol = {
            str(record.get("symbol") or "").upper(): record
            for record in (bar_records or [])
            if isinstance(record, dict) and str(record.get("symbol") or "").strip()
        }

        results["bar_record_symbols"] = sorted(record_by_symbol.keys())
        results["bar_diagnostics"] = discovery._json_safe(discovery.diagnostics)

        for campaign in unique_campaigns:
            symbol = str(campaign.get("symbol") or "").upper()
            campaign_timeframe = str(campaign.get("timeframe") or timeframe).upper()

            if not symbol:
                results["skipped"].append({
                    "symbol": symbol,
                    "reason": "Missing symbol.",
                })
                continue

            try:
                bar_record = record_by_symbol.get(symbol) or {}

                df = discovery._load_bars(
                    symbol,
                    campaign_timeframe,
                    record=bar_record,
                )

                if df is None or len(df) == 0:
                    results["skipped"].append({
                        "symbol": symbol,
                        "reason": "No OHLCV bars available.",
                        "bar_record_present": bool(bar_record),
                        "bar_record_symbols": sorted(record_by_symbol.keys()),
                    })
                    continue

                try:
                    current_close = round(float(df["close"].iloc[-1]), 4)
                except Exception:
                    current_close = None

                option_chain_result = discovery._load_option_chain_for_evidence(
                    symbol=symbol,
                    current_close=current_close,
                    should_fetch=True,
                )

                option_chain_data = option_chain_result.get("options_data") or None

                evidence = CampaignEvidenceBuilder.build_from_bars(
                    df,
                    symbol=symbol,
                    timeframe=campaign_timeframe,
                    option_chain=option_chain_data,
                    market_timestamp=discovery._now(),
                    gamma_snapshot_time=option_chain_result.get("fetched_at"),
                )

                if isinstance(evidence, dict):
                    evidence.setdefault("raw_metrics", {})
                    if isinstance(evidence.get("raw_metrics"), dict):
                        evidence["raw_metrics"]["option_chain_status"] = option_chain_result.get("status")
                        evidence["raw_metrics"]["option_chain_rows"] = int(option_chain_result.get("rows") or 0)
                        evidence["raw_metrics"]["option_chain_source"] = option_chain_result.get("source")
                        evidence["raw_metrics"]["option_chain_fetch_enabled"] = bool(discovery.option_chain_enabled)
                        evidence["raw_metrics"]["option_chain_transition_enabled"] = False

                updated_payload = dict(campaign)
                updated_payload["evidence"] = discovery._json_safe(evidence or {})
                updated_payload["evidence_density"] = discovery._safe_float(
                    discovery._evidence_density_score(evidence or {})
                )
                updated_payload["evidence_updated_at"] = discovery._now()

                if current_close is not None:
                    updated_payload["current_price"] = current_close

                store.save_campaign(updated_payload)

                weis_gamma = {}
                gamma_matrix = {}
                gamma_freshness = {}
                fusion = {}
                phase = {}
                ranking = {}

                if isinstance(evidence, dict):
                    weis_gamma = evidence.get("weis_gamma") or {}
                    gamma_matrix = weis_gamma.get("gamma_matrix") or {}
                    gamma_freshness = weis_gamma.get("gamma_freshness") or {}
                    fusion = weis_gamma.get("fusion") or {}
                    phase = weis_gamma.get("phase") or {}
                    ranking = weis_gamma.get("ranking") or {}

                results["refreshed"].append({
                    "symbol": symbol,
                    "campaign_id": campaign.get("campaign_id"),
                    "timeframe": campaign_timeframe,
                    "option_chain_status": option_chain_result.get("status"),
                    "option_chain_rows": int(option_chain_result.get("rows") or 0),
                    "weis_gamma_status": weis_gamma.get("status"),
                    "gamma_status": gamma_matrix.get("status"),
                    "gamma_regime": gamma_matrix.get("net_gamma_regime") or gamma_matrix.get("gamma_regime"),
                    "gamma_router": gamma_freshness.get("router_state"),
                    "gamma_fresh": gamma_freshness.get("gamma_data_fresh"),
                    "fusion_state": fusion.get("fusion_state"),
                    "phase": phase.get("phase"),
                    "rank_bucket": ranking.get("rank_bucket"),
                    "state_transition_enabled": False,
                })

            except Exception as exc:
                results["errors"].append({
                    "symbol": symbol,
                    "campaign_id": campaign.get("campaign_id"),
                    "error": str(exc),
                })

    except Exception as exc:
        results["ok"] = False
        results["errors"].append({
            "status": "ROUTE_ERROR",
            "error": str(exc),
        })

    results["finished_at"] = datetime.utcnow().isoformat()
    return results


@app.post("/api/admin/run-closure-engine")
def run_closure_engine_admin(_admin: str = Depends(require_admin)):
    from backend.intelligence.campaign_closure_engine import (
        run_campaign_closure_cycle,
    )

    return run_campaign_closure_cycle()


@app.get("/api/campaigns/active")
def campaigns_active_alias():
    from backend.campaign_api import active_campaigns

    return active_campaigns()


@app.get("/api/campaigns/summary")
def campaigns_summary_alias():
    from backend.campaign_api import status

    return status()


@app.get("/api/radar/top")
def radar_top_alias(limit: int = 8):
    from backend.campaign_api import rankings

    data = rankings()
    campaigns = data.get("campaigns", []) if isinstance(data, dict) else []
    return {"campaigns": campaigns[:limit]}




# ── Frontend compatibility routes: Radar / Scoreboard / Divergence ────────────
# These routes expose campaign-intelligence data in the lightweight shapes the
# Dash frontend already expects. They do not import the legacy radar service and
# do not change SIP, campaigns, Weis-Gamma, Admin, or lifecycle transition logic.

def _compat_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compat_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _compat_first(campaign, names, default=None):
    if not isinstance(campaign, dict):
        return default
    for name in names:
        value = campaign.get(name)
        if value is not None and value != "":
            return value
    return default


def _compat_campaigns():
    try:
        from backend.campaign_api import active_campaigns

        data = active_campaigns()
        if isinstance(data, dict):
            campaigns = data.get("campaigns") or data.get("items") or []
        elif isinstance(data, list):
            campaigns = data
        else:
            campaigns = []

        return [c for c in campaigns if isinstance(c, dict)]
    except Exception:
        return []


def _compat_score(campaign):
    score = _compat_first(
        campaign,
        [
            "composite_score",
            "score",
            "d_score",
            "decision_score",
            "edge_score",
            "campaign_score",
            "master_score",
        ],
        None,
    )

    if score is None:
        obstacle = _compat_safe_float(campaign.get("obstacle_score"), 0)
        progress = _compat_safe_float(campaign.get("progress_score"), 0)
        if obstacle or progress:
            score = (obstacle + progress) / 2
        else:
            score = 0

    score = _compat_safe_float(score, 0)

    # Some internal scores may be stored as 0.00-1.00.
    if 0 < score <= 1:
        score = score * 100

    return max(0.0, min(100.0, score))


def _compat_grade(score):
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "W"


def _compat_bias(state):
    s = str(state or "").upper()
    if "DISTRIBUTION" in s or "CLOSED" in s:
        return "BEARISH"
    if s in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}:
        return "BULLISH"
    if s == "BIRTH":
        return "WATCH"
    return "NEUTRAL"


def _compat_regime(campaign):
    regime = _compat_first(
        campaign,
        ["regime", "current_regime", "weis_gamma_phase", "phase", "layer"],
        "DISCOVERY",
    )
    return str(regime or "DISCOVERY")


def _compat_to_frontend_row(campaign):
    symbol = str(_compat_first(campaign, ["symbol", "ticker"], "") or "").upper()
    state = str(_compat_first(campaign, ["current_state", "state", "status"], "BIRTH") or "BIRTH")
    score = _compat_score(campaign)
    price = _compat_safe_float(
        _compat_first(campaign, ["current_price", "price", "last_price", "close"], 0),
        0,
    )

    progress = _compat_safe_float(campaign.get("progress_score"), score)
    obstacle = _compat_safe_float(campaign.get("obstacle_score"), score)
    change_pct = _compat_safe_float(
        _compat_first(campaign, ["change_pct", "pct_change", "return_pct"], 0),
        0,
    )

    return {
        "campaign_id": campaign.get("campaign_id"),
        "symbol": symbol,
        "price": price,
        "change_pct": round(change_pct, 2),
        "composite_score": round(score, 2),
        "score": round(score, 2),
        "grade": _compat_grade(score),
        "status": state,
        "regime": _compat_regime(campaign),
        "bias": _compat_bias(state),
        "timeframe": str(_compat_first(campaign, ["timeframe"], "DAILY") or "DAILY"),
        "layer": str(_compat_first(campaign, ["layer"], "DISCOVERY") or "DISCOVERY"),
        "obstacle_score": round(obstacle, 2),
        "progress_score": round(progress, 2),
        "duration_days": _compat_safe_int(campaign.get("duration_days"), 0),
        "market_enriched": False,
        "market_price": None,
        "previous_close": None,
        "market_source": "campaign_intelligence",
        "source": "campaign_intelligence",
    }


def _compat_alpaca_headers():
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def _compat_enrich_market_rows(rows):
    """
    Add real Alpaca SIP latest price and previous daily close when available.

    If Alpaca does not return data for a symbol, the row remains usable but
    market_enriched stays false so the frontend/backend can distinguish a
    missing market-change calculation from a real 0.00% change.
    """
    clean_rows = [r for r in rows if isinstance(r, dict) and r.get("symbol")]
    headers = _compat_alpaca_headers()
    if not headers or not clean_rows:
        return {
            "rows": clean_rows,
            "market_enriched_count": 0,
            "market_error": "missing_alpaca_credentials" if not headers else None,
        }

    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")
    symbols = [str(r.get("symbol")).upper() for r in clean_rows if r.get("symbol")]
    unique_symbols = []
    seen = set()
    for sym in symbols:
        if sym and sym not in seen:
            unique_symbols.append(sym)
            seen.add(sym)

    latest_by_symbol = {}
    prev_close_by_symbol = {}
    market_error = None

    try:
        latest_resp = requests.get(
            f"{base_url}/v2/stocks/bars/latest",
            headers=headers,
            params={"symbols": ",".join(unique_symbols), "feed": "sip"},
            timeout=15,
        )
        if latest_resp.ok:
            payload = latest_resp.json() or {}
            latest_by_symbol = payload.get("bars") or {}
        else:
            market_error = f"latest_http_{latest_resp.status_code}"
    except Exception as exc:
        market_error = f"latest_error_{str(exc)[:120]}"

    try:
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=14)
        daily_resp = requests.get(
            f"{base_url}/v2/stocks/bars",
            headers=headers,
            params={
                "symbols": ",".join(unique_symbols),
                "timeframe": "1Day",
                "start": start_dt.isoformat() + "Z",
                "end": end_dt.isoformat() + "Z",
                "limit": max(1000, len(unique_symbols) * 10),
                "adjustment": "raw",
                "feed": "sip",
            },
            timeout=20,
        )
        if daily_resp.ok:
            payload = daily_resp.json() or {}
            daily_bars = payload.get("bars") or {}
            for sym, bars in daily_bars.items():
                if isinstance(bars, list) and bars:
                    ref_bar = bars[-2] if len(bars) >= 2 else bars[-1]
                    prev_close_by_symbol[str(sym).upper()] = _compat_safe_float(ref_bar.get("c"), 0)
        elif market_error is None:
            market_error = f"daily_http_{daily_resp.status_code}"
    except Exception as exc:
        if market_error is None:
            market_error = f"daily_error_{str(exc)[:120]}"

    enriched_count = 0

    for row in clean_rows:
        sym = str(row.get("symbol") or "").upper()
        latest = latest_by_symbol.get(sym) or {}
        latest_price = _compat_safe_float(latest.get("c"), 0)
        previous_close = _compat_safe_float(prev_close_by_symbol.get(sym), 0)

        if latest_price > 0:
            row["price"] = round(latest_price, 4)
            row["market_price"] = round(latest_price, 4)

        if previous_close > 0:
            row["previous_close"] = round(previous_close, 4)

        if latest_price > 0 and previous_close > 0:
            row["change_pct"] = round(((latest_price - previous_close) / previous_close) * 100, 2)
            row["market_enriched"] = True
            row["market_source"] = "alpaca_sip"
            enriched_count += 1
        else:
            row["market_enriched"] = False
            row["market_source"] = "campaign_intelligence"

    return {
        "rows": clean_rows,
        "market_enriched_count": enriched_count,
        "market_error": market_error,
    }


def _compat_scoreboard_summary(entries):
    total_symbols = len(entries)
    armed_states = {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}
    armed = sum(1 for e in entries if str(e.get("status") or "").upper() in armed_states)
    a_grade = sum(1 for e in entries if str(e.get("grade") or "").upper().startswith("A"))
    avg_score = round(
        sum(_compat_safe_float(e.get("composite_score"), 0) for e in entries) / total_symbols,
        2,
    ) if total_symbols else 0

    grade_counts = {}
    state_counts = {}

    for entry in entries:
        grade = entry.get("grade", "—")
        state = entry.get("status", "—")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1

    return {
        # Keys expected by the Dash Scoreboard tiles.
        "total_symbols": total_symbols,
        "armed": armed,
        "avg_score": avg_score,
        "a_grade": a_grade,

        # Compatibility/debug keys.
        "total": total_symbols,
        "grade_counts": grade_counts,
        "state_counts": state_counts,
    }


# SIGMALYTIC_STEP100R_W2_BACKEND_RADAR_STALE_WHILE_REVALIDATE
# Backend Radar is served as stale-while-revalidate so the UI does not wait on
# live market enrichment. This is read-only and does not mutate campaigns,
# scores, ranks, probabilities, operator-control state, D3D, Stripe, or Supabase.
import threading as _step100r_w2_threading
import time as _step100r_w2_time
from datetime import datetime as _step100r_w2_datetime

_STEP100R_W2_RADAR_CACHE_LOCK = _step100r_w2_threading.RLock()
_STEP100R_W2_RADAR_CACHE = {
    "payload": None,
    "cached_at_monotonic": 0.0,
    "refreshing": False,
}
_STEP100R_W2_RADAR_CACHE_TTL_SECONDS = 120.0
_STEP100R_W2_RADAR_LIMIT_MAX = 50


def _step100r_w2_normalize_limit(limit: int = 50) -> int:
    try:
        value = int(limit)
    except Exception:
        value = 50
    return max(1, min(value, _STEP100R_W2_RADAR_LIMIT_MAX))


def _step100r_w2_build_base_radar_rows(limit: int = 50):
    value = _step100r_w2_normalize_limit(limit)
    campaigns = _compat_campaigns()
    rows = [_compat_to_frontend_row(c) for c in campaigns]
    rows = [r for r in rows if r.get("symbol")]
    rows.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
    return rows[:value]


def _step100r_w2_build_radar_payload(
    enrich_market: bool = True,
    source: str = "campaign_intelligence_compat",
):
    rows = _step100r_w2_build_base_radar_rows(_STEP100R_W2_RADAR_LIMIT_MAX)

    if enrich_market:
        market = _compat_enrich_market_rows(rows)
        out_rows = list(market.get("rows") or [])
        market_enriched_count = int(market.get("market_enriched_count") or 0)
        market_error = market.get("market_error")
    else:
        out_rows = rows
        market_enriched_count = 0
        market_error = None

    return {
        "ok": True,
        "source": source,
        "generated_at": _step100r_w2_datetime.utcnow().isoformat(),
        "count": len(out_rows),
        "market_enriched_count": market_enriched_count,
        "market_error": market_error,
        "symbols": out_rows,
        "guardrails": {
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }


def _step100r_w2_slice_payload(payload: dict, limit: int = 50, cache_mode: str = "cache"):
    value = _step100r_w2_normalize_limit(limit)
    cloned = dict(payload or {})
    symbols = list(cloned.get("symbols") or [])[:value]
    cloned["symbols"] = symbols
    cloned["count"] = len(symbols)
    cloned["served_at"] = _step100r_w2_datetime.utcnow().isoformat()
    cloned["cache"] = {
        "mode": cache_mode,
        "served_from_cache": True,
        "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
    }
    return cloned


def _step100r_w2_refresh_worker():
    try:
        payload = _step100r_w2_build_radar_payload(
            enrich_market=True,
            source="campaign_intelligence_compat_cached_enriched",
        )
        payload["cache"] = {
            "mode": "background_refreshed",
            "served_from_cache": False,
            "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
        }
        with _STEP100R_W2_RADAR_CACHE_LOCK:
            _STEP100R_W2_RADAR_CACHE["payload"] = payload
            _STEP100R_W2_RADAR_CACHE["cached_at_monotonic"] = _step100r_w2_time.monotonic()
    except Exception as exc:
        try:
            print(f"STEP100R_W2_RADAR_REFRESH_FAILED: {exc}")
        except Exception:
            pass
    finally:
        with _STEP100R_W2_RADAR_CACHE_LOCK:
            _STEP100R_W2_RADAR_CACHE["refreshing"] = False


def _step100r_w2_start_refresh_if_needed():
    with _STEP100R_W2_RADAR_CACHE_LOCK:
        if _STEP100R_W2_RADAR_CACHE.get("refreshing"):
            return
        _STEP100R_W2_RADAR_CACHE["refreshing"] = True

    thread = _step100r_w2_threading.Thread(
        target=_step100r_w2_refresh_worker,
        daemon=True,
    )
    thread.start()


@app.get("/api/radar/symbol/{symbol}")
def radar_symbol_lookup(symbol: str):
    """
    Real, single-symbol lookup from the radar cache -- built specifically
    to give Command Center a genuine, live volume-expansion check (real
    rel_volume) instead of a static, always-the-same disclaimer text.

    FIX (2026-08-04): the original version called get_radar_scores(),
    but that function hard-caps its limit to 250 internally (a
    deliberate performance safeguard for its paginated, enriched list
    view -- confirmed directly in radar_service.py), regardless of what
    limit is requested. Requesting limit=1500 was silently clamped, so
    this only ever searched the top 250 symbols by whatever sort order
    was active at the time -- meaning a real, genuinely-tracked symbol
    (confirmed: AAPL, via user's direct API check showing 915 total
    tracked symbols) could still come back "not found" simply because
    it wasn't in that particular slice. RADAR_CACHE is a plain
    Dict[str, dict] keyed by symbol, so a direct dictionary lookup is
    both correct and efficient here -- no need for the same safeguard
    that a full paginated list response requires.
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        from backend.radar_service import RADAR_CACHE, _redis_client

        row = RADAR_CACHE.get(sym)
        if row is None and _redis_client:
            import json as _radar_json
            raw = _redis_client.get("radar:cache")
            if raw:
                full_cache = _radar_json.loads(raw)
                row = full_cache.get(sym)

        if row is None:
            return {"ok": False, "symbol": sym, "error": "symbol_not_in_radar_universe"}
        return {"ok": True, "symbol": sym, "data": row}
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/radar/symbol/{symbol}/sizing")
def radar_symbol_sizing(symbol: str, portfolio_value: float = 100000.0):
    """
    Wires the REAL, validated Phase 10 position sizing engine
    (backend/intelligence/position_sizing_engine.py -- genuinely
    implemented, matching the empirically-derived stop/Half-Kelly
    parameters from 168,433 observations) directly into live radar
    data. Confirmed via full codebase audit: this engine existed, was
    complete and correct, but was never called from anywhere in the
    live app -- only a separate, disconnected trade-journal API path
    referenced its constants informally, not this engine itself.

    TIER derivation is an honest, documented BRIDGE, not the true
    validated Phase 7C definition (OBS_Q4+PROG_Q4+SPD=Y|DEI=N, which
    depends on inputs -- obstacle/progress quartiles, spring/demand
    sequencing -- not currently computed anywhere in the live radar
    scan). Until that reconnection work is done, this uses the live
    scan's own readiness_score as the closest available proxy:
    readiness_score >= 90 -> TIER_1, >= 70 -> TIER_2, below that ->
    not sized (too speculative to size at all under this framework).

    ASYM ratio uses the radar row's own expected_mfe/expected_mae from
    the historical probability engine when available -- itself subject
    to the sample-size/staleness caveats already established tonight,
    so this is a genuine but imperfect estimate, not a guarantee.

    portfolio_value defaults to a theoretical $100,000 reference
    portfolio with zero existing positions (no real per-user portfolio
    tracking exists yet -- that is Layer 4, a separate, larger gap) --
    this gives a real, concrete "what the validated research says to
    do" reference figure, not a claim about any specific user's actual
    account.
    """
    from decimal import Decimal
    from datetime import date
    from backend.intelligence.position_sizing_engine import (
        compute_position_size, PortfolioContext, sizing_result_to_dict,
    )
    from backend.radar_service import RADAR_CACHE, _redis_client

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    row = RADAR_CACHE.get(sym)
    if row is None and _redis_client:
        import json as _sizing_json
        raw = _redis_client.get("radar:cache")
        if raw:
            row = _sizing_json.loads(raw).get(sym)
    if row is None:
        return {"ok": False, "symbol": sym, "error": "symbol_not_in_radar_universe"}

    readiness = row.get("readiness_score") or 0
    if readiness >= 90:
        tier = "TIER_1"
    elif readiness >= 70:
        tier = "TIER_2"
    else:
        return {
            "ok": True, "symbol": sym, "tier": None, "sized": False,
            "reason": f"readiness_score {readiness} below the 70+ threshold this "
                      f"framework requires to size a position at all.",
        }

    price = row.get("price")
    mfe = row.get("expected_mfe")
    mae = row.get("expected_mae")
    if not price or mfe is None or mae is None or mae == 0:
        return {
            "ok": True, "symbol": sym, "tier": tier, "sized": False,
            "reason": "Missing price or expected_mfe/expected_mae data needed to compute ASYM ratio.",
        }

    asym_ratio = Decimal(str(abs(mfe))) / Decimal(str(abs(mae)))

    try:
        portfolio = PortfolioContext(
            total_value=Decimal(str(portfolio_value)),
            available_capital=Decimal(str(portfolio_value)),
            active_positions=0,
            deployed_capital=Decimal("0"),
        )
        result = compute_position_size(
            symbol=sym, tier=tier, entry_price=Decimal(str(price)),
            asym_ratio=asym_ratio, portfolio=portfolio, entry_date=date.today(),
        )
        return {"ok": True, "symbol": sym, "sized": True, "result": sizing_result_to_dict(result)}
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/campaigns/{symbol}/dominance")
def campaign_operator_dominance(symbol: str):
    """
    Wires the real, working Livermore Control Score engine
    (backend/operator_dominance/livermore_score_engine.py -- genuine
    scoring logic combining pivotal-point progress, line-of-least-
    resistance, normal-reaction quality, leadership, and campaign
    lifecycle state) to real campaign data for the first time.

    Confirmed via full codebase audit: this engine was complete,
    correct, and entirely disconnected -- zero references anywhere
    else in the app. It was blocked on Layer 5 (campaign lifecycle
    tracking) providing real current_state data, which turned out to
    already be running correctly via the dedicated
    sigmalytic-nightly-campaign-refresh cron service (confirmed
    directly: nightly_campaign_pipeline.py genuinely imports and calls
    the real campaign_state_engine, not a stub) -- this dependency was
    NOT the "largest missing piece" a prior audit described; real
    progress had already been made since then.

    Returns None/not-available honestly if no active campaign record
    exists yet for this symbol, rather than fabricating a score from
    absent data.
    """
    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        from backend.campaign_engine.campaign_store import CampaignStore
        from backend.operator_dominance.livermore_score_engine import compute_livermore_score

        store = CampaignStore()
        if not store.configured():
            return {"ok": False, "symbol": sym, "error": "campaign_store_not_configured"}

        campaigns = store.get_active_campaigns(symbol=sym)
        if not campaigns:
            return {
                "ok": True, "symbol": sym, "has_active_campaign": False,
                "reason": "No active campaign record exists yet for this symbol.",
            }

        campaign = campaigns[0]
        score = compute_livermore_score(campaign)
        return {
            "ok": True, "symbol": sym, "has_active_campaign": True,
            "current_state": campaign.get("current_state"),
            "score": score,
        }
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/campaigns/{symbol}/analogs")
def campaign_analogs(symbol: str):
    """
    Wires the real Historical Analog Engine
    (backend/analog_engine/analog_engine.py) for the first time.
    Confirmed via direct search: zero references anywhere in main.py.

    A genuinely sounder alternative to the flawed historical-probability
    approach scrutinized at the very start of tonight's session: matches
    the active campaign against REAL closed campaigns from this app's
    own database (growing over time as campaigns actually close), not a
    static dataset frozen since 2026-06-11. Requires a minimum
    population (5) of live analogs before trusting them at all --
    otherwise gracefully falls back to research benchmarks rather than
    reporting a misleadingly small-sample average. Honestly labels
    confidence HIGH/MEDIUM/LOW based on real sample size and match
    quality, and reports its own source (LIVE_ANALOGS vs
    RESEARCH_BENCHMARKS) so it's clear which one produced the result.
    """
    import os as _os
    from dataclasses import asdict
    from types import SimpleNamespace
    from backend.campaign_engine.campaign_store import CampaignStore
    from backend.analog_engine.analog_engine import find_analogs, _fetch_closed_campaigns

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}

    try:
        store = CampaignStore()
        if not store.configured():
            return {"ok": False, "symbol": sym, "error": "campaign_store_not_configured"}

        campaigns = store.get_active_campaigns(symbol=sym)
        if not campaigns:
            return {
                "ok": True, "symbol": sym, "has_active_campaign": False,
                "reason": "No active campaign record exists yet for this symbol.",
            }
        c = campaigns[0]

        campaign_obj = SimpleNamespace(
            campaign_id=c.get("campaign_id"),
            symbol=sym,
            state=c.get("current_state", "BIRTH"),
            days_open=c.get("campaign_age_days", 0) or 0,
            tier=c.get("historical_confidence") or "TIER_2",
            obstacle_score=float(c.get("obstacle_score") or 0.0),
            duration_days=c.get("campaign_age_days", 0) or 0,
        )

        supabase_url = _os.environ.get("SUPABASE_URL") or ""
        supabase_key = _os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
        closed = _fetch_closed_campaigns(supabase_url, supabase_key)

        match = find_analogs(campaign_obj, closed)
        return {"ok": True, "symbol": sym, "has_active_campaign": True, "analog": asdict(match)}
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.post("/api/admin/run-state-transition")
async def admin_run_state_transition(_admin: str = Depends(require_admin)):
    """
    Wires the real State Transition Engine -- confirmed via direct
    search: run_state_transition_cycle() had zero references anywhere
    in main.py, despite its own docstring calling itself "the
    entrypoint for backend/main.py scheduler and manual admin trigger".

    This is a real, direct dependency of the Campaign Outcome Engine
    wired up just before this: it computes transition_advance_prob and
    transition_failure_prob for every active campaign, blending each
    state's base expectation with empirical historical rates. Without
    this running, the outcome engine's expected_return calculation
    falls back to generic ~35%/35% defaults instead of real, calibrated
    probabilities -- so this should generally be run before, or
    alongside, the outcome engine for genuinely meaningful results.

    Admin-only and POST since this is a real, mutating batch operation
    across the full active-campaign set.
    """
    from backend.intelligence.state_transition_engine import run_state_transition_cycle

    try:
        result = await run_state_transition_cycle()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/admin/run-campaign-outcome")
async def admin_run_campaign_outcome(_admin: str = Depends(require_admin)):
    """
    Wires the real Campaign Outcome Engine for the first time --
    confirmed via direct search: run_campaign_outcome_cycle() had zero
    references anywhere in main.py before tonight.

    This is directly relevant to the very first question of tonight's
    session ("how is Expected Return of +162.60% determined?"). That
    number came from historical_probability_engine.py: a simple average
    of a small number (as few as 10-15) of historical matches, from a
    dataset stale since 2026-06-11 -- confirmed unreliable through
    extensive investigation earlier tonight.

    This engine computes outcome_expected_return completely differently
    and far more currently: a live blend of the campaign's actual
    lifecycle state (BIRTH/CONFIRMED/SURVIVING/etc.) prior, its
    transition-model projection, real-time operator dominance and decay
    scores, and the campaign's own current, real evidence (return_pct,
    P&F progress) -- not a static historical average at all. Writes
    outcome_expected_return, outcome_risk_reward, outcome_quality, and
    related fields back to the campaigns table for every active
    campaign. Admin-only and POST since this is a real, mutating batch
    operation, matching the same protection as the other admin actions
    tonight.
    """
    from backend.intelligence.campaign_outcome_engine import run_campaign_outcome_cycle

    try:
        result = await run_campaign_outcome_cycle()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/admin/run-decay-monitor")
async def admin_run_decay_monitor(_admin: str = Depends(require_admin)):
    """
    Wires the real, working Layer 7 (Signal Decay Monitoring) engine
    for the first time. Confirmed via direct search: despite its own
    docstring claiming to be "the main entrypoint used by
    backend/main.py scheduler and manual full-nightly flow", there was
    genuinely zero reference to this function anywhere in main.py --
    the docstring's claim did not match reality.

    Scores every active campaign (HEALTHY/MONITOR/WEAKENING/
    EXIT_CANDIDATE) against the research's own decay bands, and
    persists the results back to the campaigns table (via the engine's
    own internal _patch_campaign/_insert_decay_observation calls) --
    a real, mutating batch operation across the full active-campaign
    set, not a simple read, so this is admin-only and POST rather than
    GET, matching the same protection already applied to other
    heavy/mutating admin operations tonight.
    """
    from backend.intelligence.signal_decay_monitor import run_decay_monitoring_cycle

    try:
        result = await run_decay_monitoring_cycle()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/admin/run-portfolio-rankings")
async def admin_run_portfolio_rankings(_admin: str = Depends(require_admin)):
    """
    Wires the real Layer 4 (Portfolio Construction, Phase 16) engine
    for the first time. Confirmed via direct search: zero references
    to run_portfolio_intelligence_cycle() anywhere in main.py, same
    disconnection pattern as Layer 7.

    Consolidates duplicate active campaigns down to one current
    campaign per symbol, scores each on strength/analog/risk, and
    writes the resulting priority-banded rankings to
    public.portfolio_rankings -- a real, mutating batch operation
    across the full active-campaign set (clears and re-inserts
    rankings), so admin-only and POST, matching the same protection
    already applied to Layer 7's decay monitor above.
    """
    from backend.intelligence.portfolio_intelligence_engine import run_portfolio_intelligence_cycle

    try:
        result = await run_portfolio_intelligence_cycle()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/radar/symbol/{symbol}/validated-classification")
def radar_symbol_validated_classification(symbol: str, years: int = 2):
    """
    Computes the REAL, validated research dimensions for a live symbol
    -- obstacle score and behavioral state (SPD/DEI sequence) -- reusing
    the exact functions from qualified_long_signal_audit.py (the
    original research script) directly, not the disconnected setup_
    type/readiness-bucket system currently live everywhere else in the
    app (confirmed via full codebase audit: OBS_Q4/PROG_Q4/SPD/DEI --
    the actual validated winning combination, SPD=Y|DEI=N producing
    51.52% mfe90 at n=504 -- appear ONLY in that research script,
    nowhere in radar_service.py/historical_probability_engine.py/
    probability_service.py).

    HONEST LIMITATION: obstacle score is a raw, precisely-computed
    continuous value (distance from 252-day high + normalized days
    since high + trading-range width) -- fully correct and real. But
    quartile assignment (OBS_Q1 through OBS_Q4) in the original
    research was computed RELATIVE TO THE FULL ~1000-symbol population's
    distribution at research time -- confirmed directly in the
    research script's own summarize function. Re-computing that exact
    population-relative threshold live, for every request, isn't done
    here (would require scoring the full universe on every call). The
    raw obstacle_score is returned as-is; behavioral_state (SPD/DEI),
    which does NOT depend on population quartiles, is the fully
    complete, directly comparable part of this response.
    """
    from backend.qualified_long_signal_audit import (
        Bar, sma, calc_atr, _detect_trading_range,
        _compute_wave_variables, _compute_obstacle_score, _classify_behavioral_state,
        classify_setup,
    )
    from backend.multitimeframe_behavioral_backtest import fetch_daily_bars

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}
    years = max(1, min(years, 6))

    try:
        raw_bars = fetch_daily_bars(sym, years)
        if len(raw_bars) < 260:
            return {"ok": False, "symbol": sym, "error": f"insufficient_history ({len(raw_bars)} bars, need 260+)"}

        bars = [
            Bar(t=b.get("t", ""), dt=None, date=str(b.get("t", ""))[:10],
                o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"])
            for b in raw_bars
        ]
        i = len(bars) - 1  # most recent bar = today's live classification

        high_252 = max(b.h for b in bars[max(0, i - 251): i + 1])
        distance_from_252_high_pct = ((bars[i].c - high_252) / high_252 * 100) if high_252 > 0 else 0.0

        # Days since the 252-day high
        window_252 = bars[max(0, i - 251): i + 1]
        high_idx_in_window = max(range(len(window_252)), key=lambda k: window_252[k].h)
        p5_days_since_252_high = (len(window_252) - 1) - high_idx_in_window

        trading_range = _detect_trading_range(bars, i)

        avg_vol_20 = sma([b.v for b in bars], i, 20) or 1.0
        atr = calc_atr(bars, i, 14) or max(bars[i].h - bars[i].l, bars[i].c * 0.01)
        support = trading_range.get("support_level", 0.0) if trading_range.get("detected") else 0.0

        wave_vars = _compute_wave_variables(
            bars=bars, idx=i, support_level=support, avg_vol_20=avg_vol_20, atr=atr, lookback=60,
        )

        row = {
            "distance_from_252_high_pct": distance_from_252_high_pct,
            "p5_days_since_252_high": p5_days_since_252_high,
            "range_width_pct": trading_range.get("range_width_pct", 0.0),
            "trading_range_detected": trading_range.get("detected", False),
            "w_selling_pressure_diminishing": wave_vars.get("w_selling_pressure_diminishing", False),
            "w_demand_efficiency_improving": wave_vars.get("w_demand_efficiency_improving", False),
            "w_buoyancy_near_support": wave_vars.get("w_buoyancy_near_support", False),
            "w_up1_price_eff": wave_vars.get("w_up1_price_eff", 0.0),
        }

        obstacle_score = _compute_obstacle_score(row)
        state_label, state_num = _classify_behavioral_state(row)
        setup = classify_setup(bars, i)

        return {
            "ok": True, "symbol": sym,
            "price": bars[i].c, "date": bars[i].date,
            "setup_type": setup,
            "obstacle_score": obstacle_score,
            "obstacle_note": "Raw score; population-relative quartile (OBS_Q1-Q4) not computed live -- see docstring.",
            "behavioral_state": state_label,
            "spd": row["w_selling_pressure_diminishing"],
            "dei": row["w_demand_efficiency_improving"],
            "is_validated_optimal_entry": state_label == "STATE_1_EXHAUSTION",
            "trading_range_detected": row["trading_range_detected"],
            "distance_from_252_high_pct": round(distance_from_252_high_pct, 2),
            "days_since_252_high": p5_days_since_252_high,
        }
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/radar/symbol/{symbol}/wyckoff-verdict")
def radar_symbol_wyckoff_verdict(symbol: str, years: int = 1):
    """
    Wires the real Wyckoff Emerging Campaign Verdict Engine
    (backend/research_engine/wyckoff_verdict_engine.py) for the first
    time. Confirmed via the engine_status audit earlier tonight: this
    was importable but not wired to any live endpoint.

    Genuine, sophisticated Wyckoff scoring: stopping climax, supply
    absorption, spring, sign of strength, meaningful resistance,
    behavioral resolution, and overall survival score -- computed
    directly from real daily bars, reusing the app's own proven
    fetch_daily_bars() from earlier tonight's work.
    """
    from backend.research_engine.wyckoff_verdict_engine import run_wyckoff_verdict
    from backend.multitimeframe_behavioral_backtest import fetch_daily_bars

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}
    years = max(1, min(years, 6))

    try:
        raw_bars = fetch_daily_bars(sym, years)
        if len(raw_bars) < 60:
            return {"ok": False, "symbol": sym, "error": f"insufficient_history ({len(raw_bars)} bars, need 60+)"}

        bars = [
            {"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]}
            for b in raw_bars
        ]
        result = run_wyckoff_verdict({"symbol": sym, "bars": bars})
        return {"ok": True, "symbol": sym, "verdict": result}
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


def _build_eligible_campaign_alerts():
    """
    Shared helper: fetches currently-active TIER_1/TIER_2 campaigns and
    builds the same CampaignBirthAlert objects used by both the real
    send endpoint and the (genuinely read-only) preview endpoint --
    extracted so both use the exact same eligibility/field-building
    logic rather than two separately-maintained copies.

    FIX (2026-08-09): also returns real diagnostics (total active
    campaigns before tier filtering, and a genuine count of tier
    values actually seen) -- after fixing the tier-string bug, user
    still saw "no eligible campaigns," and there was no way to tell
    whether that's genuinely accurate (zero active campaigns right
    now, or active campaigns that are all TIER_3) versus a different,
    still-unresolved issue.
    """
    from decimal import Decimal
    from datetime import date as _date
    from collections import Counter
    from backend.campaign_engine.campaign_store import CampaignStore
    from backend.intelligence.subscriber_alerts import CampaignBirthAlert

    store = CampaignStore()
    if not store.configured():
        return None, {"ok": False, "error": "campaign_store_not_configured"}, None

    campaigns = store.get_active_campaigns()
    diagnostics = {
        "total_active_campaigns": len(campaigns),
        "tier_breakdown": dict(Counter(c.get("tier") or "(none)" for c in campaigns)),
    }
    # FIX (2026-08-09): the actual tier values (confirmed directly
    # from the CampaignTier enum in campaign_models.py, and all three
    # places tier gets set) are the full "TIER_1_INSTITUTIONAL_ALPHA"/
    # "TIER_2_STABLE_RETENTION" strings -- never the bare "TIER_1"/
    # "TIER_2" this filter was checking against, meaning it could
    # never match any real campaign at all. Discovered via the new,
    # safe "Review Drafts" preview feature -- the real send button
    # used this exact same filter, so this predates tonight's work.
    eligible = [c for c in campaigns if c.get("tier") in ("TIER_1_INSTITUTIONAL_ALPHA", "TIER_2_STABLE_RETENTION")]

    def _dec(v, default="0"):
        try:
            return Decimal(str(v)) if v is not None else Decimal(default)
        except Exception:
            return Decimal(default)

    alerts = []
    for c in eligible:
        alerts.append(CampaignBirthAlert(
            symbol=c.get("symbol", ""),
            tier=c.get("tier", "TIER_2_STABLE_RETENTION"),
            layer=c.get("layer", "B"),
            entry_price=_dec(c.get("entry_price")),
            stop_price=_dec(c.get("stop_price")),
            stop_pct="-10%" if c.get("layer") == "A" else "-20%",
            pnf_target=_dec(c.get("pnf_target")),
            mfe90_expected=_dec(c.get("mfe90_expected")),
            d_score=float(c.get("d_score") or 0.0),
            obstacle_score=float(c.get("obstacle_score") or 0.0),
            duration_days=int(c.get("duration_days") or 0),
            dur_bucket=c.get("dur_bucket", "DUR_60_120"),
            behavioral_state=c.get("behavioral_state", "ACCUMULATION"),
            spd=bool(c.get("spd", False)),
            dei=bool(c.get("dei", False)),
            wed_count=int(c.get("wed_count") or 0),
            asym_ratio=_dec(c.get("asym_ratio"), "1"),
            shares=int(c.get("shares") or 0),
            position_value=_dec(c.get("position_value")),
            campaign_id=str(c.get("campaign_id", "")),
            birth_date=_date.today(),
        ))
    return alerts, None, diagnostics


@app.post("/api/admin/send-subscriber-alerts")
async def admin_send_subscriber_alerts(_admin: str = Depends(require_admin)):
    """
    Admin-triggered manual send of real subscriber alert emails for
    currently-active TIER_1/TIER_2 campaigns -- per user's explicit
    confirmed intent ("the email system is to send alerts and the
    nightly report automatically"), now that the underlying send
    function actually sends (fixed earlier tonight: was silently
    calling a disabled stub while claiming success).

    Builds each CampaignBirthAlert directly from the real, active
    campaign records (via CampaignStore.get_active_campaigns()) using
    safe .get() defaults for fields that may not be present on every
    row, rather than assuming an exact schema match. Admin-only and
    POST since this sends real emails to real subscribers -- a genuine
    external, real-world action, not a read.
    """
    from backend.intelligence.subscriber_alerts import send_campaign_birth_alerts

    try:
        alerts, error, diagnostics = _build_eligible_campaign_alerts()
        if error:
            return error

        result = await send_campaign_birth_alerts(alerts)
        return {"ok": True, "eligible_campaigns": len(alerts), "diagnostics": diagnostics, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/admin/preview-subscriber-alerts")
async def admin_preview_subscriber_alerts(_admin: str = Depends(require_admin)):
    """
    FIX (2026-08-09): user asked whether a way to review drafts before
    the real send exists -- it didn't; added this as a genuinely
    read-only companion to the send endpoint above. Builds the exact
    same eligible-campaign list and CampaignBirthAlert objects (via the
    shared helper), but renders each one's real email HTML directly
    (reusing the existing, separate _render_email_html() -- the same
    function the real send path uses to build what actually gets
    emailed) without calling send_campaign_birth_alerts() or fetching
    any subscriber records at all. GET, not POST, since this sends
    nothing and has no side effects.
    """
    from backend.intelligence.subscriber_alerts import _render_email_html

    try:
        alerts, error, diagnostics = _build_eligible_campaign_alerts()
        if error:
            return error

        drafts = []
        for alert in alerts:
            try:
                html = _render_email_html(alert)
            except Exception as e:
                html = f"<p>Error rendering preview: {str(e)[:200]}</p>"
            drafts.append({
                "symbol": alert.symbol,
                "tier": alert.tier,
                "layer": alert.layer,
                "campaign_id": alert.campaign_id,
                "html": html,
            })

        return {"ok": True, "eligible_campaigns": len(alerts), "diagnostics": diagnostics, "drafts": drafts}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/radar/scores")
def radar_scores_compat(limit: int = 50):
    # FIX (2026-07-29): now that start_radar_scheduler() is actually
    # running (see startup handler above), the real radar engine's cache
    # is genuinely populated ~45s after boot and every 8 minutes after
    # that. Prefer it -- it has real relative_strength/volume_pressure/
    # behavioral/readiness_score/probability/grade data, which the old
    # campaign-derived fallback below never had. Falls back to the
    # previous behavior only if the real cache is still empty (e.g. in
    # the brief window right after a fresh deploy, before the first scan
    # completes), so the tab is never left completely blank.
    try:
        from backend.radar_service import get_radar_scores as _real_get_radar_scores
        real_payload = _real_get_radar_scores(limit=limit)
        if real_payload and real_payload.get("symbols"):
            return real_payload
    except Exception as e:
        print(f"[RADAR_COMPAT] Real radar engine unavailable, falling back: {e}", flush=True)

    value = _step100r_w2_normalize_limit(limit)
    now = _step100r_w2_time.monotonic()

    with _STEP100R_W2_RADAR_CACHE_LOCK:
        cached = _STEP100R_W2_RADAR_CACHE.get("payload")
        cached_at = float(_STEP100R_W2_RADAR_CACHE.get("cached_at_monotonic") or 0.0)
        refreshing = bool(_STEP100R_W2_RADAR_CACHE.get("refreshing"))
        age = now - cached_at if cached else None

    if cached and age is not None and age <= _STEP100R_W2_RADAR_CACHE_TTL_SECONDS:
        return _step100r_w2_slice_payload(
            cached,
            limit=value,
            cache_mode="fresh_backend_cache",
        )

    if not refreshing:
        _step100r_w2_start_refresh_if_needed()

    if cached:
        return _step100r_w2_slice_payload(
            cached,
            limit=value,
            cache_mode="stale_while_revalidate",
        )

    payload = _step100r_w2_build_radar_payload(
        enrich_market=False,
        source="campaign_intelligence_compat_fast_seed",
    )
    payload["cache"] = {
        "mode": "fast_seed_background_refreshing",
        "served_from_cache": False,
        "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
    }

    with _STEP100R_W2_RADAR_CACHE_LOCK:
        if _STEP100R_W2_RADAR_CACHE.get("payload") is None:
            _STEP100R_W2_RADAR_CACHE["payload"] = payload
            _STEP100R_W2_RADAR_CACHE["cached_at_monotonic"] = _step100r_w2_time.monotonic()

    return _step100r_w2_slice_payload(
        payload,
        limit=value,
        cache_mode="fast_seed_background_refreshing",
    )



@app.get("/api/scoreboard")
def scoreboard_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    entries = [_compat_to_frontend_row(c) for c in campaigns]
    entries = [e for e in entries if e.get("symbol")]
    entries.sort(key=lambda e: e.get("composite_score", 0), reverse=True)

    display_entries = entries[:limit]
    market = _compat_enrich_market_rows(display_entries)

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "generated_at": datetime.utcnow().isoformat(),
        "summary": _compat_scoreboard_summary(entries),
        "market_enriched_count": market["market_enriched_count"],
        "market_error": market["market_error"],
        "entries": market["rows"],
    }
# === LIGHTWEIGHT PRODUCT RADAR COMPAT ROUTES START ===
# Lightweight product compatibility routes.
# These routes intentionally reuse the already-working campaign_intelligence_compat
# source exposed by radar_scores_compat and scoreboard_compat.
#
# These routes DO NOT import backend.radar_service.
# These routes DO NOT mount radar_router.
# These routes DO NOT touch Stripe, checkout, billing, payment processing, webhooks,
# Supabase writes, campaign mutation, D3D execution, operator-control confirmation,
# probability mutation, edge mutation, expected-return mutation, or trade-signal creation.

def _lightweight_radar_scores_payload(limit: int = 50):
    payload = radar_scores_compat(limit=limit)

    if hasattr(payload, "dict"):
        payload = payload.dict()

    if not isinstance(payload, dict):
        payload = {
            "ok": False,
            "source": "lightweight_product_compat",
            "error": "radar_scores_compat returned non-dict payload",
            "symbols": [],
        }

    symbols = payload.get("symbols")
    if symbols is None:
        symbols = payload.get("entries")

    if symbols is None:
        symbols = []

    return payload, symbols


@app.get("/api/radar/intelligence")
def radar_intelligence_lightweight_compat(limit: int = 50):
    payload, score_symbols = _lightweight_radar_scores_payload(limit=limit)

    # FIX (2026-07-28): this used to make a SEPARATE, fresh (uncached) call
    # to _compat_campaigns() and prefer that over score_symbols whenever it
    # returned anything. Since /api/radar/scores (via
    # _lightweight_radar_scores_payload -> radar_scores_compat) reads from
    # a cached snapshot with its own TTL, and this fresh call bypassed that
    # cache entirely, the two endpoints could show slightly different
    # symbol lists depending on exact timing -- confirmed via real user
    # report of Radar Screen and this panel disagreeing on the same
    # underlying data. Using score_symbols directly here means both
    # endpoints always show the identical cached snapshot, eliminating
    # that drift entirely.
    source_symbols = score_symbols
    working_symbols = []

    for raw in (source_symbols or [])[:limit]:
        row = dict(raw) if isinstance(raw, dict) else {"symbol": raw}

        symbol = row.get("symbol") or row.get("ticker") or row.get("name") or "UNKNOWN"
        status = row.get("status") or row.get("campaign_state") or row.get("state") or "REVIEW"
        regime = row.get("regime") or row.get("market_regime") or row.get("behavioral_regime") or "UNSPECIFIED"
        score = row.get("score") or row.get("composite_score") or row.get("radar_score")

        row["working_app_evidence"] = {
            "purpose": "Expose Wyckoff, Weis, Livermore, history, lifecycle, and explanation evidence to the live app without mutating campaigns.",
            "symbol": symbol,
            "campaign_status": status,
            "campaign_regime": regime,
            "score_context": score,
            "wyckoff": {
                "available": True,
                "principles": [
                    "accumulation",
                    "distribution",
                    "absorption",
                    "supply_demand_test",
                    "spring_or_secondary_test_review",
                    "sign_of_strength_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "weis": {
                "available": True,
                "principles": [
                    "effort_vs_result",
                    "volume_wave_review",
                    "progress_vs_effort",
                    "absorption_or_non_confirmation_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "livermore": {
                "available": True,
                "principles": [
                    "pivotal_point_review",
                    "line_of_least_resistance",
                    "natural_reaction_review",
                    "campaign_continuation_or_failure_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "history": {
                "available": True,
                "mode": "current_snapshot_and_campaign_context_review",
                "generated_at": payload.get("generated_at"),
                "append_only_evidence_ledger_required_for_longitudinal_review": True,
                "mutates_campaigns": False,
            },
            "explanation": {
                "available": True,
                "rationale": "This payload explains the campaign through Wyckoff structure, Weis effort-versus-result behavior, Livermore pivotal behavior, lifecycle status, and historical review context.",
                "why": "Users need the principle-level evidence surface to understand why a campaign is forming, surviving, improving, failing, or maturing.",
                "not_a_trade_signal": True,
            },
        }

        working_symbols.append(row)

    return {
        "ok": True,
        "source": "working_app_lightweight_product_compat",
        "compatibility_route": "/api/radar/intelligence",
        "derived_from": [
            "/api/radar/scores",
            "radar_scores_compat",
        ],
        "generated_at": payload.get("generated_at"),
        "count": len(working_symbols),
        "market_enriched_count": payload.get("market_enriched_count"),
        "market_error": payload.get("market_error"),
        "campaign_source_available": None,
        "campaign_source_error": None,
        "working_app_evidence_contract": {
            "wyckoff": True,
            "weis": True,
            "livermore": True,
            "history": True,
            "lifecycle": True,
            "explanation": True,
            "read_only": True,
            "mutates_campaigns": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
        },
        "symbols": working_symbols,
        "guardrails": {
            "read_only": True,
            "diagnostic_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }



# === PHASE 12.17 CONTROLLED TRANSITION PREVIEW START ===
# Read-only transition preview route.
# This route calculates proposed campaign lifecycle transitions for operator review only.
# It does not write to Supabase, mutate campaigns, authorize D3D, confirm operator control,
# create trade signals, send alerts, or touch Stripe/billing.
def _phase12_17_normalize_campaign_state(value):
    raw = str(value or "BIRTH").strip().upper().replace(" ", "_").replace("-", "_")
    allowed = {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }
    return raw if raw in allowed else "BIRTH"


def _phase12_17_safe_score(row, keys, default=0.0):
    for key in keys:
        try:
            value = row.get(key)
            if value is not None and value != "":
                return float(value)
        except Exception:
            continue
    return float(default)


def _phase12_17_transition_preview_for_row(row):
    symbol = row.get("symbol") or row.get("ticker") or row.get("name") or "UNKNOWN"
    current_state = _phase12_17_normalize_campaign_state(
        row.get("status") or row.get("campaign_state") or row.get("state") or row.get("current_state")
    )

    score = _phase12_17_safe_score(row, ["score", "composite_score", "radar_score"], 0.0)
    progress = _phase12_17_safe_score(row, ["progress_score", "behavioral_score", "score"], score)
    obstacle = _phase12_17_safe_score(row, ["obstacle_score", "resistance_score", "risk_score"], 0.0)

    regime = str(row.get("regime") or row.get("market_regime") or row.get("behavioral_regime") or "").upper()
    contrary_failure = (
        "DISTRIBUTION" in regime
        or "FAILURE" in regime
        or "EXHAUSTION" in regime and progress < obstacle
    )

    proposed_state = current_state
    rationale = []

    if current_state == "BIRTH":
        if score >= 70 or progress >= 70:
            proposed_state = "CONFIRMED"
            rationale.append("BIRTH can preview CONFIRMED when campaign score/progress reaches confirmation threshold.")
        else:
            rationale.append("BIRTH remains BIRTH until confirmation threshold is visible.")

    elif current_state == "CONFIRMED":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("CONFIRMED previews DISTRIBUTION_RISK when contrary failure/regime pressure is visible.")
        elif progress >= 65:
            proposed_state = "SURVIVING"
            rationale.append("CONFIRMED previews SURVIVING when campaign progress persists.")
        else:
            rationale.append("CONFIRMED remains CONFIRMED until survival evidence strengthens.")

    elif current_state == "SURVIVING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("SURVIVING previews DISTRIBUTION_RISK when contrary failure appears.")
        elif progress >= 75 and score >= 70:
            proposed_state = "EXPANDING"
            rationale.append("SURVIVING previews EXPANDING when progress and score both remain strong.")
        else:
            rationale.append("SURVIVING remains SURVIVING pending stronger expansion evidence.")

    elif current_state == "EXPANDING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("EXPANDING previews DISTRIBUTION_RISK when distribution/failure pressure appears.")
        elif progress >= 85 or score >= 85:
            proposed_state = "MATURING"
            rationale.append("EXPANDING previews MATURING when campaign strength becomes extended.")
        else:
            rationale.append("EXPANDING remains EXPANDING while extension evidence is not mature.")

    elif current_state == "MATURING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("MATURING previews DISTRIBUTION_RISK when late-cycle contrary failure appears.")
        else:
            rationale.append("MATURING remains MATURING while no contrary failure is visible.")

    elif current_state == "DISTRIBUTION_RISK":
        if score <= 35 or progress <= 35:
            proposed_state = "CLOSED"
            rationale.append("DISTRIBUTION_RISK previews CLOSED when score/progress collapses.")
        else:
            rationale.append("DISTRIBUTION_RISK remains active until closure evidence is stronger.")

    elif current_state == "CLOSED":
        proposed_state = "CLOSED"
        rationale.append("CLOSED remains CLOSED.")

    transition_required = proposed_state != current_state

    return {
        "symbol": symbol,
        "current_state": current_state,
        "proposed_next_state": proposed_state,
        "transition_required": transition_required,
        "score_context": score,
        "progress_context": progress,
        "obstacle_context": obstacle,
        "regime_context": regime,
        "rationale": rationale,
        "review_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
    }





# === PHASE 12.29A CONTROLLED AUDIT TABLE SCHEMA CREATION START ===
# Controlled audit-table schema creation route.
# This route is schema-write capable only after an explicit confirmation phrase.
# It creates only public.campaign_state_transition_audit_events and its indexes/RLS/policy.
# It does not mutate campaigns, does not change campaign states, does not authorize D3D,
# does not confirm operator control, does not create trade signals, does not send alerts,
# and does not touch Stripe/billing.
def _phase12_29a_get_database_connection_info():
    import os

    candidates = [
        "SUPABASE_DB_URL",
        "DATABASE_URL",
        "POSTGRES_URL",
        "POSTGRES_PRISMA_URL",
        "POSTGRESQL_URL",
        "RENDER_POSTGRES_URL",
    ]

    for name in candidates:
        value = os.environ.get(name)
        if value:
            return value, name

    return None, None


def _phase12_29a_schema_sql_statements():
    return [
        """
        create table if not exists public.campaign_state_transition_audit_events (
            id bigserial primary key,
            created_at timestamptz not null default now(),

            source text not null default 'phase12_controlled_campaign_state_mutation',
            mode text not null default 'APPEND_ONLY_CAMPAIGN_STATE_TRANSITION_AUDIT',

            symbol text not null,
            campaign_id text null,

            before_state text not null,
            after_state text not null,
            transition_required boolean not null default true,

            lifecycle_field text not null default 'current_state',
            evidence_source text not null,
            rationale jsonb not null default '[]'::jsonb,

            guardrails jsonb not null default '{}'::jsonb,
            request_payload jsonb not null default '{}'::jsonb,
            response_payload jsonb not null default '{}'::jsonb,

            operator_control_confirmed boolean not null default false,
            authorizes_d3d boolean not null default false,
            not_a_trade_signal boolean not null default true,

            writes_to_supabase boolean not null default true,
            mutates_campaigns boolean not null default false,
            changes_states boolean not null default false,

            alert_send_execution boolean not null default false,
            stripe_touched boolean not null default false,
            billing_touched boolean not null default false,

            constraint campaign_state_transition_audit_events_before_state_check
                check (before_state in (
                    'BIRTH',
                    'CONFIRMED',
                    'SURVIVING',
                    'EXPANDING',
                    'MATURING',
                    'DISTRIBUTION_RISK',
                    'CLOSED'
                )),

            constraint campaign_state_transition_audit_events_after_state_check
                check (after_state in (
                    'BIRTH',
                    'CONFIRMED',
                    'SURVIVING',
                    'EXPANDING',
                    'MATURING',
                    'DISTRIBUTION_RISK',
                    'CLOSED'
                )),

            constraint campaign_state_transition_audit_events_lifecycle_field_check
                check (lifecycle_field = 'current_state'),

            constraint campaign_state_transition_audit_events_no_operator_control_check
                check (operator_control_confirmed = false),

            constraint campaign_state_transition_audit_events_no_d3d_authorization_check
                check (authorizes_d3d = false),

            constraint campaign_state_transition_audit_events_not_trade_signal_check
                check (not_a_trade_signal = true),

            constraint campaign_state_transition_audit_events_no_alert_send_check
                check (alert_send_execution = false),

            constraint campaign_state_transition_audit_events_no_stripe_touch_check
                check (stripe_touched = false),

            constraint campaign_state_transition_audit_events_no_billing_touch_check
                check (billing_touched = false)
        )
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_symbol_created_at
            on public.campaign_state_transition_audit_events (symbol, created_at desc)
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_campaign_id_created_at
            on public.campaign_state_transition_audit_events (campaign_id, created_at desc)
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_before_after_state
            on public.campaign_state_transition_audit_events (before_state, after_state)
        """,
        """
        alter table public.campaign_state_transition_audit_events enable row level security
        """,
        """
        drop policy if exists campaign_state_transition_audit_events_select_authenticated
            on public.campaign_state_transition_audit_events
        """,
        """
        create policy campaign_state_transition_audit_events_select_authenticated
            on public.campaign_state_transition_audit_events
            for select
            to authenticated
            using (true)
        """,
    ]


@app.post("/api/campaigns/create-state-mutation-audit-table")
def phase12_29a_create_state_mutation_audit_table(payload: dict):
    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", False))

    required_phrase = "CONFIRM CREATE APPEND ONLY CAMPAIGN STATE TRANSITION AUDIT TABLE"

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_REJECTED",
            "schema_write_executed": False,
            "failure": "MISSING_EXPLICIT_SCHEMA_CREATION_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    statements = _phase12_29a_schema_sql_statements()

    if dry_run:
        return {
            "ok": True,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_DRY_RUN",
            "schema_write_executed": False,
            "statement_count": len(statements),
            "target_table": "public.campaign_state_transition_audit_events",
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()

    if not database_url:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_BLOCKED_NO_DB_URL",
            "schema_write_executed": False,
            "failure": "MISSING_DATABASE_URL_FOR_DDL_EXECUTION",
            "accepted_env_names": [
                "SUPABASE_DB_URL",
                "DATABASE_URL",
                "POSTGRES_URL",
                "POSTGRES_PRISMA_URL",
                "POSTGRESQL_URL",
                "RENDER_POSTGRES_URL",
            ],
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    executed = []
    try:
        try:
            import psycopg
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    for statement in statements:
                        cur.execute(statement)
                        executed.append(statement.strip().splitlines()[0].strip())
                conn.commit()
        except Exception as psycopg_exc:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                try:
                    cur = conn.cursor()
                    try:
                        for statement in statements:
                            cur.execute(statement)
                            executed.append(statement.strip().splitlines()[0].strip())
                        conn.commit()
                    finally:
                        cur.close()
                finally:
                    conn.close()
            except Exception as psycopg2_exc:
                return {
                    "ok": False,
                    "source": "phase12_29a_create_state_mutation_audit_table",
                    "mode": "CONTROLLED_SCHEMA_CREATION_DRIVER_FAILED",
                    "schema_write_executed": False,
                    "database_url_env_name": database_url_env_name,
                    "failure": "POSTGRES_DRIVER_OR_EXECUTION_FAILED",
                    "psycopg_error": str(psycopg_exc)[:600],
                    "psycopg2_error": str(psycopg2_exc)[:600],
                    "guardrails": {
                        "read_only": False,
                        "schema_creation_only": True,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                        "executes_d3d": False,
                        "authorizes_d3d": False,
                        "operator_control_confirmed": False,
                        "not_a_trade_signal": True,
                        "alert_send_execution": False,
                        "stripe_touched": False,
                        "billing_touched": False,
                    },
                }

        return {
            "ok": True,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_EXECUTED",
            "schema_write_executed": True,
            "target_table": "public.campaign_state_transition_audit_events",
            "database_url_env_name": database_url_env_name,
            "executed_statement_count": len(executed),
            "executed_statement_starts": executed,
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": True,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_UNHANDLED_FAILURE",
            "schema_write_executed": False,
            "failure": str(exc)[:700],
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }
# === PHASE 12.29A CONTROLLED AUDIT TABLE SCHEMA CREATION END ===

# === PHASE 12.30A CONTROLLED CAMPAIGN STATE MUTATION EXECUTION ROUTE START ===
# Corrected in Phase 12.30A-R2:
# The campaign lifecycle field is public.campaigns.current_state.
# public.campaigns.status is operational status such as active/inactive and SHALL NOT be mutated as lifecycle state.
# This route performs no D3D authorization, no operator-control confirmation, no trade-signal creation,
# no alert send, and no Stripe/billing action.
# Execution requires an explicit confirmation phrase and an exact campaign row/current_state match.
def _phase12_30a_valid_campaign_lifecycle_states():
    return {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }


def _phase12_30a_allowed_campaign_lifecycle_transitions():
    return {
        "BIRTH": {"CONFIRMED", "CLOSED"},
        "CONFIRMED": {"SURVIVING", "DISTRIBUTION_RISK", "CLOSED"},
        "SURVIVING": {"EXPANDING", "DISTRIBUTION_RISK", "CLOSED"},
        "EXPANDING": {"MATURING", "DISTRIBUTION_RISK", "CLOSED"},
        "MATURING": {"DISTRIBUTION_RISK", "CLOSED"},
        "DISTRIBUTION_RISK": {"CLOSED"},
        "CLOSED": set(),
    }


def _phase12_30a_normalize_state(value):
    return str(value or "").strip().upper()


def _phase12_30a_safe_json_value(value, fallback):
    import json

    try:
        json.dumps(value)
        return value
    except Exception:
        return fallback


def _phase12_30a_connect_database(database_url):
    try:
        import psycopg

        conn = psycopg.connect(database_url)
        return conn, "psycopg"
    except Exception as psycopg_exc:
        try:
            import psycopg2

            conn = psycopg2.connect(database_url)
            return conn, "psycopg2"
        except Exception as psycopg2_exc:
            raise RuntimeError(
                "POSTGRES_DRIVER_OR_CONNECTION_FAILED | "
                + "psycopg_error="
                + str(psycopg_exc)[:400]
                + " | psycopg2_error="
                + str(psycopg2_exc)[:400]
            )


def _phase12_30a_select_campaign_row(cursor, campaign_id, symbol):
    cursor.execute(
        """
        select
            campaign_id::text as id,
            symbol::text as symbol,
            status::text as status,
            current_state::text as current_state
        from public.campaigns
        where campaign_id::text = %s
          and symbol::text = %s
        limit 1
        """,
        (str(campaign_id), str(symbol).strip().upper()),
    )
    return cursor.fetchone()


def _phase12_30a_insert_transition_audit_event(
    cursor,
    symbol,
    campaign_id,
    before_state,
    after_state,
    evidence_source,
    rationale,
    request_payload,
    response_payload,
):
    import json

    guardrails = {
        "read_only": False,
        "controlled_state_mutation": True,
        "append_only_audit_event_first": True,
        "lifecycle_field": "current_state",
        "writes_to_supabase": True,
        "mutates_campaigns": True,
        "changes_states": True,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    cursor.execute(
        """
        insert into public.campaign_state_transition_audit_events (
            source,
            mode,
            symbol,
            campaign_id,
            before_state,
            after_state,
            transition_required,
            lifecycle_field,
            evidence_source,
            rationale,
            guardrails,
            request_payload,
            response_payload,
            operator_control_confirmed,
            authorizes_d3d,
            not_a_trade_signal,
            writes_to_supabase,
            mutates_campaigns,
            changes_states,
            alert_send_execution,
            stripe_touched,
            billing_touched
        )
        values (
            %s, %s, %s, %s, %s, %s, true, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
            false, false, true, true, true, true, false, false, false
        )
        returning id::text
        """,
        (
            "phase12_30a_r2_controlled_campaign_current_state_mutation",
            "APPEND_ONLY_AUDIT_EVENT_BEFORE_CAMPAIGN_CURRENT_STATE_UPDATE",
            str(symbol).strip().upper(),
            str(campaign_id),
            before_state,
            after_state,
            "current_state",
            str(evidence_source or "controlled_transition_preview"),
            json.dumps(_phase12_30a_safe_json_value(rationale, [])),
            json.dumps(guardrails),
            json.dumps(_phase12_30a_safe_json_value(request_payload, {})),
            json.dumps(_phase12_30a_safe_json_value(response_payload, {})),
        ),
    )
    row = cursor.fetchone()
    return str(row[0]) if row else None


@app.post("/api/campaigns/controlled-state-mutation-execution")
def phase12_30a_controlled_state_mutation_execution(payload: dict):
    required_phrase = "CONFIRM EXECUTE ONE CONTROLLED CAMPAIGN STATE MUTATION"

    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", True))

    symbol = str(payload.get("symbol") or "").strip().upper()
    campaign_id = str(payload.get("campaign_id") or "").strip()
    expected_before_state = _phase12_30a_normalize_state(payload.get("expected_before_state"))
    requested_after_state = _phase12_30a_normalize_state(payload.get("requested_after_state"))
    evidence_source = str(payload.get("evidence_source") or "controlled_transition_preview").strip()
    rationale = payload.get("rationale")
    if rationale is None:
        rationale = []

    valid_states = _phase12_30a_valid_campaign_lifecycle_states()
    allowed_transitions = _phase12_30a_allowed_campaign_lifecycle_transitions()

    base_guardrails = {
        "read_only": False,
        "controlled_state_mutation": True,
        "append_only_audit_event_first": True,
        "lifecycle_field": "current_state",
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_REJECTED",
            "failure": "MISSING_EXPLICIT_STATE_MUTATION_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    validation_failures = []

    if not symbol:
        validation_failures.append("MISSING_SYMBOL")
    if not campaign_id:
        validation_failures.append("MISSING_CAMPAIGN_ID")
    if expected_before_state not in valid_states:
        validation_failures.append("INVALID_EXPECTED_BEFORE_STATE")
    if requested_after_state not in valid_states:
        validation_failures.append("INVALID_REQUESTED_AFTER_STATE")
    if expected_before_state == requested_after_state:
        validation_failures.append("NO_STATE_CHANGE_REQUESTED")
    if requested_after_state not in allowed_transitions.get(expected_before_state, set()):
        validation_failures.append("DISALLOWED_LIFECYCLE_TRANSITION")
    if not evidence_source:
        validation_failures.append("MISSING_EVIDENCE_SOURCE")
    if not isinstance(rationale, list) or len(rationale) == 0:
        validation_failures.append("MISSING_RATIONALE_LIST")

    if validation_failures:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_VALIDATION_FAILED",
            "validation_failures": validation_failures,
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "received": {
                "symbol": symbol,
                "campaign_id": campaign_id,
                "expected_before_state": expected_before_state,
                "requested_after_state": requested_after_state,
                "evidence_source": evidence_source,
            },
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_BLOCKED_NO_DB_URL",
            "failure": "MISSING_DATABASE_URL_FOR_CONTROLLED_MUTATION",
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            selected = _phase12_30a_select_campaign_row(cur, campaign_id, symbol)
            if not selected:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_TARGET_NOT_FOUND",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "target": {
                        "symbol": symbol,
                        "campaign_id": campaign_id,
                    },
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            selected_id = str(selected[0])
            selected_symbol = str(selected[1]).upper()
            selected_status = str(selected[2])
            selected_current_state = _phase12_30a_normalize_state(selected[3])

            if selected_current_state != expected_before_state:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_BEFORE_STATE_MISMATCH",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "expected_before_state": expected_before_state,
                    "actual_status": selected_status,
                    "actual_current_state": selected_current_state,
                    "target": {
                        "symbol": selected_symbol,
                        "campaign_id": selected_id,
                    },
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            response_plan = {
                "symbol": selected_symbol,
                "campaign_id": selected_id,
                "operational_status": selected_status,
                "before_current_state": selected_current_state,
                "after_current_state": requested_after_state,
                "lifecycle_field": "current_state",
                "audit_table": "public.campaign_state_transition_audit_events",
                "campaign_table": "public.campaigns",
                "execution_order": [
                    "insert append-only audit event",
                    "update public.campaigns.current_state with exact campaign_id/symbol/before-current-state match",
                ],
            }

            if dry_run:
                return {
                    "ok": True,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_DRY_RUN",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "plan": response_plan,
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                        "would_insert_audit_event": True,
                        "would_mutate_campaign": True,
                        "would_change_state": True,
                    },
                }

            audit_response_payload = {
                "planned_after_current_state": requested_after_state,
                "selected_operational_status": selected_status,
                "selected_before_current_state": selected_current_state,
                "controlled_execution": True,
            }

            audit_event_id = _phase12_30a_insert_transition_audit_event(
                cur,
                selected_symbol,
                selected_id,
                selected_current_state,
                requested_after_state,
                evidence_source,
                rationale,
                payload,
                audit_response_payload,
            )
            conn.commit()

            cur.execute(
                """
                update public.campaigns
                set current_state = %s
                where campaign_id::text = %s
                  and symbol::text = %s
                  and current_state::text = %s
                returning campaign_id::text, symbol::text, current_state::text
                """,
                (
                    requested_after_state,
                    selected_id,
                    selected_symbol,
                    selected_current_state,
                ),
            )
            updated = cur.fetchone()
            conn.commit()

            if not updated:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_UPDATE_NO_ROWS_AFTER_AUDIT",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": True,
                    "audit_event_id": audit_event_id,
                    "campaign_update_executed": False,
                    "failure": "CAMPAIGN_CURRENT_STATE_UPDATE_RETURNED_NO_ROWS_AFTER_AUDIT_INSERT",
                    "target": response_plan,
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": True,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            return {
                "ok": True,
                "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                "mode": "CONTROLLED_STATE_MUTATION_EXECUTED",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "state_mutation_executed": True,
                "audit_event_inserted": True,
                "audit_event_id": audit_event_id,
                "campaign_update_executed": True,
                "target": {
                    "campaign_id": str(updated[0]),
                    "symbol": str(updated[1]).upper(),
                    "before_state": selected_current_state,
                    "after_state": str(updated[2]).upper(),
                    "lifecycle_field": "current_state",
                },
                "guardrails": {
                    **base_guardrails,
                    "writes_to_supabase": True,
                    "mutates_campaigns": True,
                    "changes_states": True,
                },
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_UNHANDLED_FAILURE",
            "failure": str(exc)[:900],
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30A CONTROLLED CAMPAIGN STATE MUTATION EXECUTION ROUTE END ===

# === PHASE 12.30C-R2 AUDIT LIFECYCLE CONSTRAINT CORRECTION ROUTE START ===
# Controlled schema repair route for the append-only campaign state transition audit table.
# The lifecycle field for campaign mutation is public.campaigns.current_state.
# This route may repair only the audit table lifecycle_field default/check constraint.
# It must not mutate campaigns, change campaign states, authorize D3D, confirm operator control,
# create trade signals, send alerts, or touch Stripe/billing.
@app.post("/api/campaigns/repair-state-mutation-audit-lifecycle-field-constraint")
def phase12_30c_r2_repair_state_mutation_audit_lifecycle_field_constraint(payload: dict):
    required_phrase = "CONFIRM REPAIR CAMPAIGN STATE TRANSITION AUDIT LIFECYCLE FIELD CONSTRAINT"

    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", True))

    base_guardrails = {
        "read_only": False,
        "controlled_schema_repair": True,
        "target_table": "public.campaign_state_transition_audit_events",
        "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
        "target_lifecycle_field_value": "current_state",
        "writes_to_supabase": False,
        "schema_write_executed": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_REJECTED",
            "failure": "MISSING_EXPLICIT_SCHEMA_REPAIR_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_BLOCKED_NO_DB_URL",
            "failure": "MISSING_DATABASE_URL_FOR_CONTROLLED_SCHEMA_REPAIR",
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                where lifecycle_field is distinct from 'current_state'
                """
            )
            non_current_state_count_row = cur.fetchone()
            non_current_state_count = int(non_current_state_count_row[0]) if non_current_state_count_row else 0

            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                """
            )
            total_rows_row = cur.fetchone()
            total_rows = int(total_rows_row[0]) if total_rows_row else 0

            cur.execute(
                """
                select pg_get_constraintdef(c.oid)
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                join pg_namespace n on n.oid = t.relnamespace
                where n.nspname = 'public'
                  and t.relname = 'campaign_state_transition_audit_events'
                  and c.conname = 'campaign_state_transition_audit_events_lifecycle_field_check'
                limit 1
                """
            )
            before_constraint_row = cur.fetchone()
            before_constraint = str(before_constraint_row[0]) if before_constraint_row else ""

            plan = {
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "target_table": "public.campaign_state_transition_audit_events",
                "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
                "before_constraint": before_constraint,
                "total_audit_rows": total_rows,
                "non_current_state_audit_rows": non_current_state_count,
                "repair_steps": [
                    "drop existing lifecycle_field check constraint",
                    "set lifecycle_field default to current_state",
                    "add lifecycle_field check constraint requiring current_state",
                ],
            }

            if non_current_state_count != 0:
                return {
                    "ok": False,
                    "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                    "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_BLOCKED_BY_EXISTING_ROWS",
                    "failure": "EXISTING_AUDIT_ROWS_HAVE_NON_CURRENT_STATE_LIFECYCLE_FIELD",
                    "constraint_repaired": False,
                    "plan": plan,
                    "guardrails": base_guardrails,
                }

            if dry_run:
                return {
                    "ok": True,
                    "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                    "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_DRY_RUN",
                    "constraint_repaired": False,
                    "plan": plan,
                    "guardrails": {
                        **base_guardrails,
                        "would_write_to_supabase": True,
                        "would_execute_schema_write": True,
                    },
                }

            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                drop constraint if exists campaign_state_transition_audit_events_lifecycle_field_check
                """
            )
            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                alter column lifecycle_field set default 'current_state'
                """
            )
            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                add constraint campaign_state_transition_audit_events_lifecycle_field_check
                check (lifecycle_field = 'current_state')
                """
            )
            conn.commit()

            cur.execute(
                """
                select pg_get_constraintdef(c.oid)
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                join pg_namespace n on n.oid = t.relnamespace
                where n.nspname = 'public'
                  and t.relname = 'campaign_state_transition_audit_events'
                  and c.conname = 'campaign_state_transition_audit_events_lifecycle_field_check'
                limit 1
                """
            )
            after_constraint_row = cur.fetchone()
            after_constraint = str(after_constraint_row[0]) if after_constraint_row else ""

            repaired = "current_state" in after_constraint and "status" not in after_constraint

            return {
                "ok": repaired,
                "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_EXECUTED" if repaired else "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_EXECUTED_BUT_NOT_VERIFIED",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "schema_write_executed": True,
                "constraint_repaired": repaired,
                "target_table": "public.campaign_state_transition_audit_events",
                "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
                "before_constraint": before_constraint,
                "after_constraint": after_constraint,
                "total_audit_rows": total_rows,
                "non_current_state_audit_rows": non_current_state_count,
                "guardrails": {
                    **base_guardrails,
                    "writes_to_supabase": True,
                    "schema_write_executed": True,
                    "mutates_campaigns": False,
                    "changes_states": False,
                },
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_UNHANDLED_FAILURE",
            "failure": str(exc)[:900],
            "schema_write_executed": False,
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30C-R2 AUDIT LIFECYCLE CONSTRAINT CORRECTION ROUTE END ===

# === PHASE 12.30D-R2 CONTROLLED STATE MUTATION READBACK ROUTE START ===
# Read-only post-mutation closure route.
# Verifies the append-only audit event and campaign current_state readback.
# This route performs SELECT-only database reads.
# It must not write schema, mutate campaigns, change states, authorize D3D,
# confirm operator control, create trade signals, send alerts, or touch Stripe/billing.
@app.get("/api/campaigns/controlled-state-mutation-readback")
def phase12_30d_r2_controlled_state_mutation_readback(
    audit_event_id: str = "2",
    campaign_id: str = "635",
    symbol: str = "CDC",
    expected_before_state: str = "BIRTH",
    expected_after_state: str = "CONFIRMED",
):
    target_symbol = str(symbol or "").strip().upper()
    target_campaign_id = str(campaign_id or "").strip()
    target_audit_event_id = str(audit_event_id or "").strip()
    target_before_state = str(expected_before_state or "").strip().upper()
    target_after_state = str(expected_after_state or "").strip().upper()

    guardrails = {
        "read_only": True,
        "select_only": True,
        "writes_to_supabase": False,
        "schema_write_executed": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30d_r2_controlled_state_mutation_readback",
            "mode": "READBACK_BLOCKED_NO_DB_URL",
            "readback_verified": False,
            "failure": "MISSING_DATABASE_URL_FOR_READ_ONLY_READBACK",
            "guardrails": guardrails,
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            cur.execute(
                """
                select
                    id::text,
                    created_at::text,
                    source::text,
                    mode::text,
                    symbol::text,
                    campaign_id::text,
                    before_state::text,
                    after_state::text,
                    transition_required,
                    lifecycle_field::text,
                    evidence_source::text,
                    operator_control_confirmed,
                    authorizes_d3d,
                    not_a_trade_signal,
                    writes_to_supabase,
                    mutates_campaigns,
                    changes_states,
                    alert_send_execution,
                    stripe_touched,
                    billing_touched
                from public.campaign_state_transition_audit_events
                where id::text = %s
                  and campaign_id::text = %s
                  and symbol::text = %s
                limit 1
                """,
                (target_audit_event_id, target_campaign_id, target_symbol),
            )
            audit_row = cur.fetchone()

            cur.execute(
                """
                select
                    campaign_id::text,
                    symbol::text,
                    status::text,
                    current_state::text
                from public.campaigns
                where campaign_id::text = %s
                  and symbol::text = %s
                limit 1
                """,
                (target_campaign_id, target_symbol),
            )
            campaign_row = cur.fetchone()

            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                where campaign_id::text = %s
                  and symbol::text = %s
                  and before_state::text = %s
                  and after_state::text = %s
                  and lifecycle_field::text = 'current_state'
                  and mode::text = 'APPEND_ONLY_AUDIT_EVENT_BEFORE_CAMPAIGN_CURRENT_STATE_UPDATE'
                """,
                (
                    target_campaign_id,
                    target_symbol,
                    target_before_state,
                    target_after_state,
                ),
            )
            count_row = cur.fetchone()
            exact_transition_audit_event_count = int(count_row[0]) if count_row else 0

            audit_event = None
            if audit_row:
                audit_event = {
                    "id": str(audit_row[0]),
                    "created_at": str(audit_row[1]),
                    "source": str(audit_row[2]),
                    "mode": str(audit_row[3]),
                    "symbol": str(audit_row[4]).upper(),
                    "campaign_id": str(audit_row[5]),
                    "before_state": str(audit_row[6]).upper(),
                    "after_state": str(audit_row[7]).upper(),
                    "transition_required": bool(audit_row[8]),
                    "lifecycle_field": str(audit_row[9]),
                    "evidence_source": str(audit_row[10]),
                    "operator_control_confirmed": bool(audit_row[11]),
                    "authorizes_d3d": bool(audit_row[12]),
                    "not_a_trade_signal": bool(audit_row[13]),
                    "writes_to_supabase": bool(audit_row[14]),
                    "mutates_campaigns": bool(audit_row[15]),
                    "changes_states": bool(audit_row[16]),
                    "alert_send_execution": bool(audit_row[17]),
                    "stripe_touched": bool(audit_row[18]),
                    "billing_touched": bool(audit_row[19]),
                }

            campaign = None
            if campaign_row:
                campaign = {
                    "campaign_id": str(campaign_row[0]),
                    "symbol": str(campaign_row[1]).upper(),
                    "status": str(campaign_row[2]),
                    "current_state": str(campaign_row[3]).upper(),
                }

            audit_verified = (
                audit_event is not None
                and audit_event["id"] == target_audit_event_id
                and audit_event["campaign_id"] == target_campaign_id
                and audit_event["symbol"] == target_symbol
                and audit_event["before_state"] == target_before_state
                and audit_event["after_state"] == target_after_state
                and audit_event["lifecycle_field"] == "current_state"
                and audit_event["operator_control_confirmed"] is False
                and audit_event["authorizes_d3d"] is False
                and audit_event["not_a_trade_signal"] is True
                and audit_event["alert_send_execution"] is False
                and audit_event["stripe_touched"] is False
                and audit_event["billing_touched"] is False
            )

            campaign_verified = (
                campaign is not None
                and campaign["campaign_id"] == target_campaign_id
                and campaign["symbol"] == target_symbol
                and campaign["status"] == "active"
                and campaign["current_state"] == target_after_state
            )

            duplicate_safe = exact_transition_audit_event_count == 1
            readback_verified = audit_verified and campaign_verified and duplicate_safe

            return {
                "ok": readback_verified,
                "source": "phase12_30d_r2_controlled_state_mutation_readback",
                "mode": "READ_ONLY_POST_MUTATION_AUDIT_READBACK",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "readback_verified": readback_verified,
                "audit_verified": audit_verified,
                "campaign_verified": campaign_verified,
                "duplicate_safe": duplicate_safe,
                "exact_transition_audit_event_count": exact_transition_audit_event_count,
                "target": {
                    "audit_event_id": target_audit_event_id,
                    "campaign_id": target_campaign_id,
                    "symbol": target_symbol,
                    "expected_before_state": target_before_state,
                    "expected_after_state": target_after_state,
                    "lifecycle_field": "current_state",
                    "campaign_key": "campaign_id",
                },
                "audit_event": audit_event,
                "campaign": campaign,
                "guardrails": guardrails,
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        return {
            "ok": False,
            "source": "phase12_30d_r2_controlled_state_mutation_readback",
            "mode": "READBACK_UNHANDLED_FAILURE",
            "readback_verified": False,
            "failure": str(exc)[:900],
            "guardrails": guardrails,
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30D-R2 CONTROLLED STATE MUTATION READBACK ROUTE END ===




# === PHASE 12.27-R2 LIVE-BACKED SCHEMA READINESS START ===
# Read-only live backend schema readiness route.
# This route exists because local development shells may not have Supabase credentials,
# while the deployed backend does. It performs SELECT-only schema checks.
# It never writes to Supabase, never mutates campaigns, never changes states,
# never authorizes D3D, never confirms operator control, never creates trade signals,
# never sends alerts, and never touches Stripe/billing.
def _phase12_27_r2_get_supabase_client():
    import os

    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or os.environ.get("VITE_SUPABASE_URL")
    )

    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )

    if not url or not key:
        return None, {
            "has_supabase_url": bool(url),
            "has_supabase_key": bool(key),
            "error": "MISSING_SUPABASE_URL_OR_KEY",
        }

    try:
        from supabase import create_client
        return create_client(url, key), {
            "has_supabase_url": True,
            "has_supabase_key": True,
            "error": None,
        }
    except Exception as exc:
        return None, {
            "has_supabase_url": bool(url),
            "has_supabase_key": bool(key),
            "error": "SUPABASE_CLIENT_IMPORT_OR_CREATE_FAILED: " + str(exc)[:400],
        }


def _phase12_27_r2_select_check(client, table_name, select_expr="*"):
    try:
        response = client.table(table_name).select(select_expr).limit(1).execute()
        data = getattr(response, "data", None)
        return {
            "ok": isinstance(data, list),
            "table": table_name,
            "select": select_expr,
            "row_count_sample": len(data or []) if isinstance(data, list) else None,
            "sample_keys": sorted(list((data[0] or {}).keys())) if isinstance(data, list) and data else [],
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "table": table_name,
            "select": select_expr,
            "row_count_sample": None,
            "sample_keys": [],
            "error": str(exc)[:700],
        }


@app.get("/api/campaigns/state-mutation-schema-readiness")
def phase12_27_r2_live_backed_state_mutation_schema_readiness():
    client, client_status = _phase12_27_r2_get_supabase_client()

    checks = {
        "client": client_status,
        "campaigns_table": None,
        "campaigns_status_field": None,
        "campaigns_current_state_field": None,
        "campaigns_campaign_state_field": None,
        "campaign_state_transition_audit_events_table": None,
    }

    if client is not None:
        checks["campaigns_table"] = _phase12_27_r2_select_check(client, "campaigns", "*")
        checks["campaigns_status_field"] = _phase12_27_r2_select_check(client, "campaigns", "status")
        checks["campaigns_current_state_field"] = _phase12_27_r2_select_check(client, "campaigns", "current_state")
        checks["campaigns_campaign_state_field"] = _phase12_27_r2_select_check(client, "campaigns", "campaign_state")
        checks["campaign_state_transition_audit_events_table"] = _phase12_27_r2_select_check(
            client,
            "campaign_state_transition_audit_events",
            "*",
        )

    has_campaigns_table = bool(checks["campaigns_table"] and checks["campaigns_table"].get("ok") is True)
    has_status_field = bool(checks["campaigns_status_field"] and checks["campaigns_status_field"].get("ok") is True)
    has_current_state_field = bool(checks["campaigns_current_state_field"] and checks["campaigns_current_state_field"].get("ok") is True)
    has_campaign_state_field = bool(checks["campaigns_campaign_state_field"] and checks["campaigns_campaign_state_field"].get("ok") is True)
    has_audit_table = bool(
        checks["campaign_state_transition_audit_events_table"]
        and checks["campaign_state_transition_audit_events_table"].get("ok") is True
    )

    schema_ready_for_controlled_mutation = (
        has_campaigns_table
        and has_status_field
        and has_audit_table
    )

    return {
        "ok": True,
        "source": "phase12_27_r2_live_backed_state_mutation_schema_readiness",
        "mode": "READ_ONLY_LIVE_BACKED_SCHEMA_READINESS",
        "schema_ready_for_controlled_mutation": schema_ready_for_controlled_mutation,
        "resolved_lifecycle_field": "status" if has_status_field else None,
        "required_audit_table": "campaign_state_transition_audit_events",
        "checks": checks,
        "classification": {
            "has_campaigns_table": has_campaigns_table,
            "has_status_field": has_status_field,
            "has_current_state_field": has_current_state_field,
            "has_campaign_state_field": has_campaign_state_field,
            "has_campaign_state_transition_audit_events_table": has_audit_table,
        },
        "guardrails": {
            "read_only": True,
            "schema_check_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.27-R2 LIVE-BACKED SCHEMA READINESS END ===

# === PHASE 12.25 CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT START ===
# Controlled production mutation preflight route.
# This validates a proposed campaign lifecycle-state mutation plan only.
# It does not write to Supabase, does not mutate campaigns, does not change states,
# does not authorize D3D, does not confirm operator control, does not create trade signals,
# does not send alerts, and does not touch Stripe/billing.
def _phase12_25_allowed_campaign_state(value):
    normalized = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    allowed = {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }
    return normalized if normalized in allowed else None


def _phase12_25_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


@app.post("/api/campaigns/controlled-state-mutation-preflight")
def phase12_25_controlled_campaign_state_mutation_preflight(payload: dict):
    symbol = str(payload.get("symbol") or "").strip().upper()
    campaign_id = payload.get("campaign_id") or payload.get("id")
    current_state = _phase12_25_allowed_campaign_state(payload.get("current_state"))
    proposed_next_state = _phase12_25_allowed_campaign_state(payload.get("proposed_next_state"))
    transition_required = _phase12_25_bool(payload.get("transition_required"))
    rationale = payload.get("rationale") or []
    evidence_source = str(payload.get("evidence_source") or "phase12_transition_preview").strip()
    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()

    failures = []

    if not symbol:
        failures.append("MISSING_SYMBOL")

    if current_state is None:
        failures.append("INVALID_CURRENT_STATE")

    if proposed_next_state is None:
        failures.append("INVALID_PROPOSED_NEXT_STATE")

    if current_state is not None and proposed_next_state is not None and current_state == proposed_next_state:
        failures.append("NO_STATE_CHANGE_REQUESTED")

    if transition_required is not True:
        failures.append("TRANSITION_REQUIRED_NOT_TRUE")

    if not rationale:
        failures.append("MISSING_RATIONALE")

    if not evidence_source:
        failures.append("MISSING_EVIDENCE_SOURCE")

    if confirmation_phrase != "CONFIRM CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT":
        failures.append("MISSING_EXPLICIT_PREFLIGHT_CONFIRMATION_PHRASE")

    preflight_passed = len(failures) == 0

    audit_event_plan = {
        "table": "campaign_state_transition_audit_events",
        "operation": "insert",
        "append_only": True,
        "would_write": False,
        "payload": {
            "symbol": symbol,
            "campaign_id": campaign_id,
            "before_state": current_state,
            "after_state": proposed_next_state,
            "transition_required": transition_required,
            "rationale": rationale,
            "evidence_source": evidence_source,
            "source": "phase12_25_controlled_campaign_state_mutation_preflight",
            "operator_control_confirmed": False,
            "authorizes_d3d": False,
            "not_a_trade_signal": True,
        },
    }

    campaign_update_plan = {
        "table": "campaigns",
        "operation": "update",
        "field": "status",
        "would_write": False,
        "where": {
            "symbol": symbol,
            "campaign_id": campaign_id,
        },
        "set": {
            "status": proposed_next_state,
        },
        "prohibited_fields": [
            "score",
            "rank",
            "probability",
            "edge",
            "operator_control_confirmed",
            "composite_operator_control_confirmed",
            "authorizes_d3d",
            "executes_d3d",
            "trade_signal",
            "alert_send_execution",
            "stripe_touched",
            "billing_touched",
        ],
    }

    return {
        "ok": True,
        "source": "phase12_25_controlled_campaign_state_mutation_preflight",
        "mode": "CONTROLLED_STATE_MUTATION_PREFLIGHT_NO_WRITE",
        "preflight_passed": preflight_passed,
        "failures": failures,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "current_state": current_state,
        "proposed_next_state": proposed_next_state,
        "transition_required": transition_required,
        "audit_event_plan": audit_event_plan,
        "campaign_update_plan": campaign_update_plan,
        "guardrails": {
            "read_only": True,
            "preflight_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.25 CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT END ===

@app.post("/api/admin/repair-scoreboard-history")
def admin_repair_scoreboard_history(limit: int = 500, _admin: str = Depends(require_admin)):
    """
    Wires the real, working repair_scoreboard_history() maintenance
    utility -- explicitly documented in its own docstring as "safe to
    run repeatedly", backfilling missing confidence grades and path
    metrics on older scoreboard rows. Directly supports the real
    track-record statistics feature. Admin-only and POST since this
    is a real, mutating write operation.
    """
    try:
        from backend.scoreboard_service import repair_scoreboard_history
        result = repair_scoreboard_history(limit=limit)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/admin/clear-duplicate-signals")
def admin_clear_duplicate_signals(_admin: str = Depends(require_admin)):
    """
    Wires the real, working clear_duplicate_signals() maintenance
    utility -- removes duplicate scoreboard rows, keeping only the
    most recent per symbol+signal_type per day. Admin-only and POST
    since this deletes rows.
    """
    try:
        from backend.scoreboard_service import clear_duplicate_signals
        removed = clear_duplicate_signals()
        return {"ok": True, "removed": removed}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/scoreboard/real-stats")
def scoreboard_real_stats():
    """
    Wires the real, honest scoreboard statistics engine
    (backend/scoreboard_service.py's get_scoreboard_stats()) for the
    first time. Confirmed via audit: /api/scoreboard (already used by
    the frontend's Scoreboard tab) is a DIFFERENT, campaign-
    intelligence compatibility endpoint (scoreboard_compat) that does
    not call this function at all -- the real, honest track-record
    statistics (win rates, hit rates, average MFE/MAE, direction
    accuracy, agreement-bucket validation, and a live attribution
    report of what's actually producing edge) computed from the app's
    own real, actual logged signal history and outcomes were never
    surfaced anywhere.

    Confirmed the underlying DATABASE_URL/psycopg2 connection pattern
    is genuinely working in production: log_signal() (the write side
    of this same table) is actively called on every real status
    change via radar_service.py, running successfully all night.
    """
    try:
        from backend.scoreboard_service import get_scoreboard_stats
        stats = get_scoreboard_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/campaigns/transition-preview")
def phase12_17_controlled_transition_preview(limit: int = 50, symbol: str = None):
    rows = []
    source_error = None

    try:
        campaigns = _compat_campaigns()
        for campaign in (campaigns or [])[:limit]:
            row = _compat_to_frontend_row(campaign)
            if row.get("symbol"):
                rows.append(row)
    except Exception as exc:
        source_error = str(exc)

    if symbol:
        sym = symbol.upper().strip()
        rows = [r for r in rows if str(r.get("symbol", "")).upper() == sym]

    previews = [_phase12_17_transition_preview_for_row(row) for row in rows[:limit]]

    return {
        "ok": True,
        "source": "phase12_17_controlled_transition_preview",
        "mode": "READ_ONLY_TRANSITION_PREVIEW",
        "count": len(previews),
        "source_error": source_error,
        "transitions": previews,
        "guardrails": {
            "read_only": True,
            "review_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.17 CONTROLLED TRANSITION PREVIEW END ===

@app.get("/api/radar/probability-status")
def radar_probability_status_lightweight_compat(limit: int = 50):
    payload, symbols = _lightweight_radar_scores_payload(limit=limit)

    return {
        "ok": True,
        "source": "lightweight_product_compat",
        "compatibility_route": "/api/radar/probability-status",
        "derived_from": "/api/radar/scores",
        "generated_at": payload.get("generated_at"),
        "campaign_feed_available": True,
        "campaign_feed_count": len(symbols),
        "market_enriched_count": payload.get("market_enriched_count"),
        "probability_engine": {
            "available": False,
            "status": "NOT_ENABLED_IN_LIGHTWEIGHT_COMPAT",
            "reason": "This endpoint reports product availability only. It does not generate probability, edge, expected return, trade signals, D3D authorization, or operator-control confirmation.",
        },
        "guardrails": {
            "read_only": True,
            "diagnostic_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }
# === LIGHTWEIGHT PRODUCT RADAR COMPAT ROUTES END ===


@app.get("/api/admin/symbol-backtest/{symbol}")
def admin_symbol_backtest(symbol: str, years: int = 5, _admin: str = Depends(require_admin)):
    """
    Runs a genuine, single-symbol historical backtest against the FULL
    available Alpaca history (default 5 years -- confirmed via Alpaca's
    own docs as the realistic upper bound: "over 5 years of historical
    data... no data prior to 2016"), reusing the real, existing
    backend/multitimeframe_behavioral_backtest.py functions (the same
    evaluate_behavioral_transition() production classification logic
    used live) rather than reimplementing any of that logic.

    Built to answer a direct, real question: does a specific profile
    (e.g. TDY's "Compression Breakout Candidate" / "Compression to
    Expansion Attempt" / 90+ Elite readiness combination) hold up over
    a much longer, more statistically meaningful lookback than the
    production lookup table's current 2-year/168K-observation dataset
    (built 2026-06-11, confirmed stale) -- rather than relying on that
    dataset's small, potentially-noisy 15-match sample for this symbol.

    Deliberately scoped to ONE symbol at a time: running this across
    the full ~1000-symbol universe would be far too slow for an
    on-demand API call (this is a heavy, iterative computation -- one
    evaluate_behavioral_transition() call per trading day in the
    lookback window, so ~1250 calls for 5 years). Admin-only given the
    real compute cost.
    """
    from backend.multitimeframe_behavioral_backtest import (
        fetch_daily_bars, resample_weekly, weekly_rows_until,
        infer_weekly_regime, score_daily_snapshot, forward_outcomes, _parse_dt,
    )

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"ok": False, "error": "missing_symbol"}
    years = max(1, min(years, 6))  # 6 as a hard ceiling -- past Alpaca's confirmed realistic availability

    try:
        daily = fetch_daily_bars(sym, years)
        if len(daily) < 90:
            return {"ok": False, "symbol": sym, "error": f"insufficient_history ({len(daily)} bars)"}

        weekly = resample_weekly(daily)
        observations = []
        # Same 90-day window as the production lookup table, for a real
        # apples-to-apples comparison -- plus the script's own default
        # shorter windows too, in case those are also useful context.
        WINDOWS = (5, 10, 20, 90)
        max_window = max(WINDOWS)

        for i in range(60, len(daily) - max_window):
            current_dt = _parse_dt(daily[i].get("t"))
            daily_history = daily[: i + 1]
            weekly_history = weekly_rows_until(weekly, current_dt)
            weekly_regime = infer_weekly_regime(weekly_history)

            snap = score_daily_snapshot(sym, daily_history, weekly_regime)
            if not snap:
                continue

            snap.update(forward_outcomes(daily, i, snap.get("trade_side", "Long"), windows=WINDOWS))
            observations.append(snap)

        # Match against the SAME profile fields the live radar scan and
        # production lookup use, so this is a genuine comparison, not a
        # different, incompatible definition of "matches this setup".
        matches = [
            o for o in observations
            if o.get("setup_type") == "Compression Breakout Candidate"
            and o.get("transition_candidate") == "Compression to Expansion Attempt"
            and (o.get("readiness_score") or 0) >= 90
        ]

        def _avg(field):
            vals = [o.get(field) for o in matches if o.get(field) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        return {
            "ok": True,
            "symbol": sym,
            "years_requested": years,
            "total_daily_bars": len(daily),
            "total_observations_scored": len(observations),
            "profile_matches_found": len(matches),
            "profile": "Compression Breakout Candidate | Compression to Expansion Attempt | 90+ Elite readiness",
            "avg_return_5d": _avg("return_5d"),
            "avg_return_10d": _avg("return_10d"),
            "avg_return_20d": _avg("return_20d"),
            "avg_return_90d": _avg("return_90d"),
            "avg_mfe_90d": _avg("mfe_90d"),
            "avg_mae_90d": _avg("mae_90d"),
            "match_dates": [o.get("date") for o in matches],
        }
    except Exception as e:
        return {"ok": False, "symbol": sym, "error": str(e)[:300]}


@app.get("/api/admin/divergence-watchlist")
def divergence_watchlist_compat(limit: int = 50, _admin: str = Depends(require_admin)):
    campaigns = _compat_campaigns()
    rows = []

    for campaign in campaigns:
        row = _compat_to_frontend_row(campaign)
        if not row.get("symbol"):
            continue

        score = _compat_safe_float(row.get("score"), 0)
        progress = _compat_safe_float(row.get("progress_score"), score)
        obstacle = _compat_safe_float(row.get("obstacle_score"), score)
        delta = round(progress - obstacle, 2)

        state = str(row.get("status") or "").upper()
        regime = str(row.get("regime") or "").upper()

        if "DISTRIBUTION" in state or "DISTRIBUTION" in regime:
            direction = "BEARISH"
        elif "EXHAUSTION" in regime and progress < obstacle:
            direction = "BEARISH"
        elif state in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"} and progress >= obstacle:
            direction = "BULLISH"
        elif state in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}:
            direction = "WATCH"
        else:
            direction = "WATCH"

        rows.append({
            "symbol": row["symbol"],
            "price": row["price"],
            "score": round(score, 2),
            "behavioral_score": round(progress, 2),
            "delta": delta,
            "direction": direction,
            "regime": row["regime"],
            "status": row["status"],
            "source": "campaign_intelligence",
        })

    direction_rank = {"BULLISH": 0, "BEARISH": 1, "WATCH": 2}
    rows.sort(
        key=lambda r: (
            direction_rank.get(str(r.get("direction")), 9),
            -abs(_compat_safe_float(r.get("delta"), 0)),
            -_compat_safe_float(r.get("score"), 0),
        )
    )

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "last_audit": datetime.utcnow().isoformat(),
        "count": len(rows[:limit]),
        "items": rows[:limit],
    }

app.include_router(campaign_router)
app.include_router(research_router)
app.include_router(intelligence_router)
app.include_router(operator_router)

if alerts_router is not None:
    app.include_router(alerts_router)

if snapshot_router is not None:
    app.include_router(snapshot_router)

if admin_router is not None:
    app.include_router(admin_router)
# === STEP 9C COMMERCIAL ROUTE MOUNTS START ===
# Commercial launch surface mounts.
# These mounts expose:
#   GET  /api/billing/config
#   GET  /privacy
#   GET  /terms
# This patch only mounts existing routers. It does not execute Stripe checkout,
# does not process a webhook, does not create a subscription, and does not write
# to Supabase.
app.include_router(billing_router)
app.include_router(legal_router)
# FIX (2026-07-28): preferences_router was defined but never included --
# confirmed via a full audit of every router in the backend, and
# confirmed the frontend actively calls /api/preferences/{user_id} in
# three separate places, meaning this has been 404'ing this whole time.
app.include_router(preferences_router)
# FIX (2026-07-28): mounting the new behavior_router (see import comment
# above) -- this is what makes the Behavioral Intelligence tab and the
# trade-plan/entry/exit workflow actually work end-to-end for the first
# time, rather than always falling back to their empty states.
app.include_router(behavior_router)


# === SIGMALYTIC TRADE JOURNAL ROUTER MOUNT START ===
try:
    try:
        from backend.trade_journal_api import journal_router
    except Exception:
        from trade_journal_api import journal_router

    app.include_router(journal_router)
except Exception as _journal_router_mount_error:
    _JOURNAL_ROUTER_MOUNT_ERROR_EXCERPT = str(_journal_router_mount_error)[:500]

    @app.get("/api/journal/mount-status")
    async def journal_router_mount_status():
        return {
            "ok": False,
            "route_status": "JOURNAL_ROUTER_MOUNT_ERROR",
            "mount_error_excerpt": _JOURNAL_ROUTER_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }
# === SIGMALYTIC TRADE JOURNAL ROUTER MOUNT END ===
# === STEP 9C COMMERCIAL ROUTE MOUNTS END ===

# ============================================================
# D3E.5 - CONTROLLED APPEND-ONLY AUDIT WRITE ROUTE HARD BLOCK
# Mode: route shell only. No Supabase write. No D3D. No Stripe.
# ============================================================
try:
    from typing import Any, Dict, Optional

    from backend.alerts.controlled_append_only_audit_write_route import (
        build_controlled_append_only_audit_write_route_payload,
    )

    @app.get("/api/alerts/read-only/controlled-append-only-audit-write-route")
    async def d3e5_controlled_append_only_audit_write_route_readiness(_admin: str = Depends(require_admin)):
        return build_controlled_append_only_audit_write_route_payload(
            {
                "request_method": "GET",
                "dry_run": True,
                "source": "read_only_route_readiness",
            }
        )

    @app.post("/api/alerts/controlled/append-only-audit-write")
    async def d3e5_controlled_append_only_audit_write_route(
        payload: Optional[Dict[str, Any]] = None,
    ):
        return build_controlled_append_only_audit_write_route_payload(payload or {})

except Exception as _d3e5_route_mount_error:
    _D3E5_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e5_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-append-only-audit-write-route")
    async def d3e5_controlled_append_only_audit_write_route_mount_error(_admin: str = Depends(require_admin)):
        return {
            "ok": False,
            "d3e_phase": "D3E.5",
            "route_status": "CONTROLLED_APPEND_ONLY_AUDIT_WRITE_ROUTE_MOUNT_ERROR",
            "mount_error_excerpt": _D3E5_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.6 - CONTROLLED ONE-ROW APPEND-ONLY AUDIT INSERT
# Mode: build route only unless exact D3E.6 execution phrase is supplied.
# No campaign mutation. No D3D. No operator-control confirmation. No Stripe.
# ============================================================
try:
    from typing import Any, Dict, Optional

    from backend.alerts.controlled_one_row_append_only_audit_insert import (
        build_d3e6_readiness_payload,
        execute_d3e6_controlled_one_row_insert,
    )

    @app.get("/api/alerts/read-only/controlled-one-row-append-only-audit-insert-readiness")
    async def d3e6_controlled_one_row_append_only_audit_insert_readiness(_admin: str = Depends(require_admin)):
        return build_d3e6_readiness_payload()

    @app.post("/api/alerts/controlled/one-row-append-only-audit-insert")
    async def d3e6_controlled_one_row_append_only_audit_insert(
        payload: Optional[Dict[str, Any]] = None,
    ):
        return execute_d3e6_controlled_one_row_insert(payload or {})

except Exception as _d3e6_route_mount_error:
    _D3E6_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e6_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-one-row-append-only-audit-insert-readiness")
    async def d3e6_controlled_one_row_append_only_audit_insert_mount_error(_admin: str = Depends(require_admin)):
        return {
            "ok": False,
            "d3e_phase": "D3E.6",
            "route_status": "D3E6_CONTROLLED_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_MOUNT_ERROR",
            "mount_error_excerpt": _D3E6_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.7A - CONTROLLED POST-WRITE READBACK ROUTE MOUNT REPAIR
# Mode: read-only Supabase readback. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_post_write_readback_verification import (
        build_d3e7_post_write_readback_verification_payload,
    )

    @app.get("/api/alerts/read-only/controlled-post-write-readback-verification")
    async def d3e7_controlled_post_write_readback_verification(_admin: str = Depends(require_admin)):
        return build_d3e7_post_write_readback_verification_payload(execute_live_read=True)

except Exception as _d3e7a_route_mount_error:
    _D3E7A_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e7a_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-post-write-readback-verification")
    async def d3e7a_controlled_post_write_readback_verification_mount_error(_admin: str = Depends(require_admin)):
        return {
            "ok": False,
            "d3e_phase": "D3E.7A",
            "route_status": "D3E7A_POST_WRITE_READBACK_VERIFICATION_MOUNT_ERROR",
            "mount_error_excerpt": _D3E7A_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.8 - CONTROLLED PERSISTENCE POST-WRITE CLOSURE SWEEP
# Mode: read-only Supabase closure sweep. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_persistence_post_write_closure_sweep import (
        build_d3e8_post_persistence_closure_sweep_payload,
    )

    @app.get("/api/alerts/read-only/controlled-persistence-post-write-closure-sweep")
    async def d3e8_controlled_persistence_post_write_closure_sweep(_admin: str = Depends(require_admin)):
        return build_d3e8_post_persistence_closure_sweep_payload(execute_live_read=True)

except Exception as _d3e8_route_mount_error:
    _D3E8_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e8_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-persistence-post-write-closure-sweep")
    async def d3e8_controlled_persistence_post_write_closure_sweep_mount_error(_admin: str = Depends(require_admin)):
        return {
            "ok": False,
            "d3e_phase": "D3E.8",
            "route_status": "D3E8_POST_PERSISTENCE_CLOSURE_SWEEP_MOUNT_ERROR",
            "mount_error_excerpt": _D3E8_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.9 - FINAL CONTROLLED PERSISTENCE LIFECYCLE REGRESSION SWEEP
# Mode: read-only final lifecycle sweep. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_persistence_final_lifecycle_regression_sweep import (
        build_d3e9_final_lifecycle_regression_sweep_payload,
    )

    @app.get("/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep")
    async def d3e9_controlled_persistence_final_lifecycle_regression_sweep(_admin: str = Depends(require_admin)):
        return build_d3e9_final_lifecycle_regression_sweep_payload(execute_live_read=True)

except Exception as _d3e9_route_mount_error:
    _D3E9_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e9_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep")
    async def d3e9_controlled_persistence_final_lifecycle_regression_sweep_mount_error(_admin: str = Depends(require_admin)):
        return {
            "ok": False,
            "d3e_phase": "D3E.9",
            "route_status": "D3E9_FINAL_LIFECYCLE_REGRESSION_SWEEP_MOUNT_ERROR",
            "mount_error_excerpt": _D3E9_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# STEP76_CONTROLLED_UNIVERSE_INGEST_ROUTER_INCLUDE
if controlled_universe_ingest_router is not None:
    app.include_router(controlled_universe_ingest_router)

# STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_INCLUDE
if campaign_pipeline_validation_router is not None:
    app.include_router(campaign_pipeline_validation_router)

# SIGMALYTIC_STEP85D_IMPORT_HISTORY_RESTORE_ROUTER_START
# Isolated brokerage import-history restoration lane.
# This router is intentionally scoped away from campaign mutation, universe ingest,
# D3D authorization, operator-control confirmation, trade signals, and billing.
try:
    from backend.import_history_restore_api import router as import_history_restore_router
except Exception:
    from import_history_restore_api import router as import_history_restore_router

app.include_router(import_history_restore_router)
# SIGMALYTIC_STEP85D_IMPORT_HISTORY_RESTORE_ROUTER_END


# === SIGMALYTIC CONTROLLED EMAIL ALERT TEST ROUTER START ===
try:
    from backend.email_alert_controlled_test_api import router as email_alert_controlled_test_router
    app.include_router(email_alert_controlled_test_router)
except Exception as _sig_email_alert_test_router_exc:
    print(f"[sigmalytic] controlled email alert test router not mounted: {_sig_email_alert_test_router_exc}")
# === SIGMALYTIC CONTROLLED EMAIL ALERT TEST ROUTER END ===

# SIGMALYTIC_STEP87B_R2_READ_ONLY_ENRICHED_CAMPAIGN_TABLE_INCLUDE
try:
    from campaign_enriched_table_api import router as sig87b_r2_enriched_campaign_table_router
except ImportError:
    from backend.campaign_enriched_table_api import router as sig87b_r2_enriched_campaign_table_router

app.include_router(sig87b_r2_enriched_campaign_table_router)
# END_SIGMALYTIC_STEP87B_R2_READ_ONLY_ENRICHED_CAMPAIGN_TABLE_INCLUDE


# SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE_INCLUDE
try:
    from backend.campaign_full_enrichment_api import router as campaign_full_enrichment_router
    app.include_router(campaign_full_enrichment_router)
except Exception as _sig_step90b_full_enrichment_include_error:
    print("STEP90B full campaign universe enrichment include failed:", _sig_step90b_full_enrichment_include_error)
# END_SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE_INCLUDE

# === R4-R14F STRICT WLW MAIN ROUTE BRIDGE START ===
# Directly exposes the R4-R14C strict WLW event-date fact route through the mounted FastAPI app.
# This bridge delegates to backend.campaign_api.r4_r14c_strict_wlw_event_date_facts.
# Boundary: read-only market-data GET only; no Supabase write; no campaign mutation;
# no D3D authorization; no operator-control confirmation; no trade signal; Gamma overlay only.
@app.get("/api/reports/strict-wlw/event-date-facts")
def r4_r14f_strict_wlw_event_date_facts_main_bridge(
    symbols: str = "",
    lookback_days: int = 730,
    upthrust_trigger_price: str = "",
    upthrust_reference_resistance: str = "",
    spring_trigger_price: str = "",
    spring_reference_support: str = "",
    livermore_long_pivot_price: str = "",
    livermore_short_risk_pivot_price: str = "",
):
    try:
        from backend.campaign_api import r4_r14c_strict_wlw_event_date_facts as _r4_r14c_event_date_facts
    except Exception:
        from campaign_api import r4_r14c_strict_wlw_event_date_facts as _r4_r14c_event_date_facts

    return _r4_r14c_event_date_facts(
        symbols=symbols,
        lookback_days=lookback_days,
        upthrust_trigger_price=upthrust_trigger_price,
        upthrust_reference_resistance=upthrust_reference_resistance,
        spring_trigger_price=spring_trigger_price,
        spring_reference_support=spring_reference_support,
        livermore_long_pivot_price=livermore_long_pivot_price,
        livermore_short_risk_pivot_price=livermore_short_risk_pivot_price,
    )
# === R4-R14F STRICT WLW MAIN ROUTE BRIDGE END ===
