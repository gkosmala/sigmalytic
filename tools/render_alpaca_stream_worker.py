"""
tools/render_alpaca_stream_worker.py
--------------------------------------
Standalone, continuously-running Alpaca live-price streaming worker.

WHY THIS EXISTS: Command Center's on_tick previously polled Alpaca's
REST endpoint every 10 seconds -- meaning the "live" price was always
up to 10 seconds stale by construction, not by any real Alpaca
limitation (confirmed: this account has SIP streaming access, and
Alpaca's WebSocket API is comparable to TradeStation's). This worker
replaces that poll with an actual persistent connection to Alpaca's
SIP stream, writing sub-second-fresh prices into Redis for on_tick to
read instead of calling Alpaca directly.

Deliberately its own separate Render worker service, not folded into
sigmalytic-radar-scanner: that service's own jobs (gex_scan, radar_scan,
the daily Weis Radar scan) are heavy, periodic, batch-style scans of
~1000 symbols, fundamentally different in shape from a lightweight,
always-on, latency-sensitive streaming connection for 1-2 actively-
viewed symbols. Mixing them risks exactly the kind of memory/stability
problem that already motivated splitting the radar scanner out from
the main backend in the first place (see that file's own docstring).

ARCHITECTURE:
  - LeaderLock ensures exactly one instance of this worker (across
    however many processes/replicas might exist -- deliberately not
    assumed to be exactly one, since that was never confirmed) holds
    the actual Alpaca WebSocket connection at a time.
  - SubscriptionManager is the decoupling layer: Dash callbacks
    (load_symbol() for Command Center, the Weis Analysis fetch
    trigger) write which symbols they want streamed into Redis.
    Only the elected leader reads that and reconciles its real
    Alpaca subscriptions against it.
  - alpaca-py's StockDataStream.subscribe_trades()/unsubscribe_trades()
    are confirmed safe to call from a different thread than the one
    running stream.run() -- the SDK itself uses
    asyncio.run_coroutine_threadsafe() internally for exactly this.
    So stream.run() runs on its own dedicated thread, and the
    reconciliation loop below calls subscribe/unsubscribe directly
    from the main thread without needing any additional locking.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo_root)

RECONCILE_INTERVAL_SECONDS = 5
LIVE_TICK_KEY_PREFIX = "live_tick:"
LIVE_TICK_TTL_SECONDS = 90  # covers a full ~60s bar interval plus margin


def write_trade_to_hash(redis_client, symbol: str, price: float, size, ts: float):
    """
    Atomically updates only the trade-derived fields of this symbol's
    tick hash -- never reads or rewrites the quote/bar fields another
    handler owns, so there's no read-modify-write race between event
    types arriving close together on the same symbol.
    """
    redis_client.hset(f"{LIVE_TICK_KEY_PREFIX}{symbol}", mapping={
        "last_price": price, "last_size": size or 0, "last_ts": ts,
    })
    redis_client.expire(f"{LIVE_TICK_KEY_PREFIX}{symbol}", LIVE_TICK_TTL_SECONDS)


def write_quote_to_hash(redis_client, symbol: str, bid_price, bid_size, ask_price, ask_size, ts: float):
    redis_client.hset(f"{LIVE_TICK_KEY_PREFIX}{symbol}", mapping={
        "bid_price": bid_price or 0, "bid_size": bid_size or 0,
        "ask_price": ask_price or 0, "ask_size": ask_size or 0,
        "quote_ts": ts,
    })
    redis_client.expire(f"{LIVE_TICK_KEY_PREFIX}{symbol}", LIVE_TICK_TTL_SECONDS)


def write_bar_to_hash(redis_client, symbol: str, open_, high, low, close, volume, ts: float):
    redis_client.hset(f"{LIVE_TICK_KEY_PREFIX}{symbol}", mapping={
        "bar_open": open_, "bar_high": high, "bar_low": low, "bar_close": close,
        "bar_volume": volume or 0, "bar_ts": ts,
    })
    redis_client.expire(f"{LIVE_TICK_KEY_PREFIX}{symbol}", LIVE_TICK_TTL_SECONDS)


def reconcile_subscriptions(stream, desired_symbols: set, currently_subscribed: set,
                             on_trade_handler, on_quote_handler, on_bar_handler, log=print) -> set:
    """
    Diffs desired vs. currently-subscribed symbols and calls
    stream.subscribe_*()/unsubscribe_*() for all three event types
    (trades, quotes, bars) together per symbol, since a coherent tick
    needs all three -- there's no partial subscription to a symbol.
    Extracted as a standalone function (rather than a closure inside
    main()) so it can be tested directly against a fake stream object,
    without needing a real Alpaca connection.
    """
    to_add = desired_symbols - currently_subscribed
    to_remove = currently_subscribed - desired_symbols

    if to_add:
        try:
            stream.subscribe_trades(on_trade_handler, *to_add)
            stream.subscribe_quotes(on_quote_handler, *to_add)
            stream.subscribe_bars(on_bar_handler, *to_add)
            log(f"[ALPACA_STREAM] Subscribed (trades+quotes+bars): {sorted(to_add)}")
        except Exception as exc:
            log(f"[ALPACA_STREAM] Error subscribing to {to_add}: {exc}")
            to_add = set()  # don't record as subscribed if any part failed

    if to_remove:
        try:
            stream.unsubscribe_trades(*to_remove)
            stream.unsubscribe_quotes(*to_remove)
            stream.unsubscribe_bars(*to_remove)
            log(f"[ALPACA_STREAM] Unsubscribed (trades+quotes+bars): {sorted(to_remove)}")
        except Exception as exc:
            log(f"[ALPACA_STREAM] Error unsubscribing from {to_remove}: {exc}")
            to_remove = set()

    return (currently_subscribed | to_add) - to_remove


def main() -> int:
    print("[ALPACA_STREAM] Starting standalone Alpaca stream worker...", flush=True)

    required_env = ["ALPACA_API_KEY", "ALPACA_API_SECRET", "REDIS_URL"]
    missing = [name for name in required_env if not (os.getenv(name) or "").strip()]
    if missing:
        print(f"[ALPACA_STREAM] Missing required environment variables: {', '.join(missing)}.",
              flush=True)
        return 2

    # FIX (2026-09-07): originally imported _redis_client FROM
    # backend.radar_service directly -- but that module's own
    # top-level import chain transitively pulls in backend/
    # email_service.py, which does RESEND_API_KEY = os.environ[...]
    # (no default) at MODULE level, crashing this entire, otherwise-
    # unrelated worker on import if that var isn't set. This worker
    # only ever needs a bare Redis connection, never anything else
    # radar_service.py provides -- building it directly here, using
    # the exact same connection logic radar_service.py itself uses
    # (see that file's own "Redis heartbeat client" block), avoids
    # depending on that whole module's unrelated, heavier requirements
    # entirely, rather than chasing down and adding each additional
    # env var that heavy import chain might need one at a time.
    import redis as _redis_module
    try:
        _redis_client = _redis_module.Redis.from_url(
            os.environ["REDIS_URL"], decode_responses=True, socket_timeout=2
        )
        _redis_client.ping()
    except Exception as exc:
        print(f"[ALPACA_STREAM] Failed to connect to Redis: {exc}", flush=True)
        return 1

    if not _redis_client:
        print("[ALPACA_STREAM] Shared Redis client is not configured. Exiting.", flush=True)
        return 1

    from backend.leader_lock import LeaderLock
    from backend.subscription_manager import SubscriptionManager
    from alpaca.data.live import StockDataStream
    from alpaca.data.enums import DataFeed

    lock = LeaderLock(_redis_client)
    subs = SubscriptionManager(_redis_client)

    api_key = os.environ["ALPACA_API_KEY"]
    api_secret = os.environ["ALPACA_API_SECRET"]

    state = {
        "stream": None,           # the current StockDataStream instance, or None
        "stream_thread": None,    # the thread running stream.run(), or None
        "subscribed": set(),      # symbols we believe we're currently subscribed to
    }

    # ADDED (2026-09-15): confirmed a real, genuine anti-pattern -- each
    # handler below is `async def`, running directly inside alpaca-py's
    # own asyncio event loop that receives and dispatches every
    # incoming WebSocket message. But write_trade_to_hash/
    # write_quote_to_hash/write_bar_to_hash all call the standard,
    # SYNCHRONOUS redis-py client (imported above as _redis_module,
    # not redis.asyncio). Each of those calls blocks that same event
    # loop for its full network round-trip -- during which no new
    # incoming trade/quote/bar frame can be received or parsed.
    # Confirmed this matters, not just in theory: live checks against
    # this app's own diagnostic endpoint showed AAPL trades arriving
    # ~25-45s apart on a paid, "0 delay" SIP plan during active market
    # hours, with zero write errors logged -- consistent with messages
    # being silently missed while the loop was blocked, not with the
    # feed or account being at fault. run_in_executor offloads each
    # write to a background thread, letting the event loop return
    # immediately to receiving the next message.
    async def _on_trade(trade):
        # Called by the SDK on its own event-loop thread for every
        # incoming trade. Only ever writes the trade-owned fields (see
        # write_trade_to_hash) -- never reads or touches the quote/bar
        # fields another handler owns, so concurrent events for the
        # same symbol can't race or clobber each other.
        # FIX (2026-09-15): confirmed via live logs a real, active bug
        # in the async offload itself -- asyncio.get_event_loop() was
        # called once, outside these handlers, on whatever thread
        # first defined them. But this stream runs on its OWN,
        # separate thread (see the threading.Thread below), which has
        # its own, different event loop -- so every single write was
        # failing with "attached to a different loop", 100% failure
        # rate, likely worse than before this fix and a plausible
        # cause of the reported memory spike (a failed task per event,
        # at real-time trade frequency). get_running_loop() call
        # inside each handler always returns the loop that specific
        # coroutine is actually executing on, correctly, regardless of
        # which thread it's running in.
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, write_trade_to_hash, _redis_client, trade.symbol,
                float(trade.price), getattr(trade, "size", None), time.time(),
            )
        except Exception as exc:
            print(f"[ALPACA_STREAM] Error writing trade for {getattr(trade, 'symbol', '?')}: {exc}",
                  flush=True)

    async def _on_quote(quote):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, write_quote_to_hash, _redis_client, quote.symbol,
                float(quote.bid_price) if quote.bid_price else None,
                getattr(quote, "bid_size", None),
                float(quote.ask_price) if quote.ask_price else None,
                getattr(quote, "ask_size", None),
                time.time(),
            )
        except Exception as exc:
            print(f"[ALPACA_STREAM] Error writing quote for {getattr(quote, 'symbol', '?')}: {exc}",
                  flush=True)

    async def _on_bar(bar):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, write_bar_to_hash, _redis_client, bar.symbol,
                float(bar.open), float(bar.high), float(bar.low), float(bar.close),
                getattr(bar, "volume", None), time.time(),
            )
        except Exception as exc:
            print(f"[ALPACA_STREAM] Error writing bar for {getattr(bar, 'symbol', '?')}: {exc}",
                  flush=True)

    def _start_stream():
        stream = StockDataStream(api_key, api_secret, feed=DataFeed.SIP)
        state["stream"] = stream
        state["subscribed"] = set()

        def _run():
            try:
                stream.run()
            except Exception as exc:
                print(f"[ALPACA_STREAM] Stream thread exited with error: {exc}", flush=True)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        state["stream_thread"] = t
        print("[ALPACA_STREAM] Became leader -- Alpaca SIP stream started.", flush=True)

    def _stop_stream():
        stream = state.get("stream")
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                print(f"[ALPACA_STREAM] Error stopping stream: {exc}", flush=True)
        state["stream"] = None
        state["stream_thread"] = None
        state["subscribed"] = set()
        print("[ALPACA_STREAM] Lost leadership -- Alpaca stream stopped.", flush=True)

    def _reconcile_subscriptions():
        stream = state.get("stream")
        if stream is None:
            return
        desired = subs.get_desired_symbols()
        # DIAGNOSTIC (2026-09-07, temporary, at explicit request while
        # debugging why subscriptions written by the frontend never
        # appear to reach this worker): logs exactly what THIS worker's
        # Redis connection actually sees, every cycle. If this ever
        # prints a symbol the frontend logged requesting (e.g. AAPL),
        # the pipeline is connected correctly and any remaining problem
        # is downstream, in subscribe_trades/quotes/bars itself. If this
        # NEVER shows a requested symbol despite the frontend
        # confirming it wrote one, that's definitive, direct evidence
        # this worker's REDIS_URL points at a different Redis instance
        # or database than the frontend's -- not something to keep
        # guessing about via manually comparing URL strings.
        print(f"[ALPACA_STREAM_DIAG] desired_symbols={desired}", flush=True)
        state["subscribed"] = reconcile_subscriptions(
            stream, desired, state["subscribed"], _on_trade, _on_quote, _on_bar
        )

    was_leader = False
    print("[ALPACA_STREAM] Running. Checking leadership and reconciling "
          f"subscriptions every {RECONCILE_INTERVAL_SECONDS}s.", flush=True)
    while True:
        try:
            is_leader = lock.try_acquire_or_renew()

            if is_leader and not was_leader:
                _start_stream()
            elif was_leader and not is_leader:
                _stop_stream()

            if is_leader:
                _reconcile_subscriptions()

            was_leader = is_leader
        except Exception as exc:
            print(f"[ALPACA_STREAM] Error in main loop: {exc}", flush=True)

        time.sleep(RECONCILE_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
