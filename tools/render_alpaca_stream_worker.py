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

import json
import os
import sys
import threading
import time

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo_root)

RECONCILE_INTERVAL_SECONDS = 5
LIVE_PRICE_TTL_SECONDS = 30
LIVE_PRICE_KEY_PREFIX = "live_price:"


def reconcile_subscriptions(stream, desired_symbols: set, currently_subscribed: set,
                             on_trade_handler, log=print) -> set:
    """
    Diffs desired vs. currently-subscribed symbols and calls
    stream.subscribe_trades()/unsubscribe_trades() to match. Returns
    the new, accurate set of subscribed symbols -- extracted as a
    standalone function (rather than a closure inside main()) so it
    can be tested directly against a fake stream object, without
    needing a real Alpaca connection.
    """
    to_add = desired_symbols - currently_subscribed
    to_remove = currently_subscribed - desired_symbols

    if to_add:
        try:
            stream.subscribe_trades(on_trade_handler, *to_add)
            log(f"[ALPACA_STREAM] Subscribed: {sorted(to_add)}")
        except Exception as exc:
            log(f"[ALPACA_STREAM] Error subscribing to {to_add}: {exc}")
            to_add = set()  # don't record as subscribed if it failed

    if to_remove:
        try:
            stream.unsubscribe_trades(*to_remove)
            log(f"[ALPACA_STREAM] Unsubscribed: {sorted(to_remove)}")
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

    try:
        from backend.radar_service import _redis_client
    except Exception as exc:
        print(f"[ALPACA_STREAM] Failed to import shared Redis client: {exc}", flush=True)
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

    async def _on_trade(trade):
        # Called by the SDK on its own event-loop thread for every
        # incoming trade. Kept intentionally minimal -- just the
        # latest price, written with a short TTL so a dead stream
        # naturally stops serving stale prices rather than serving
        # them forever.
        try:
            payload = {"price": float(trade.price), "ts": time.time(), "symbol": trade.symbol}
            _redis_client.set(
                f"{LIVE_PRICE_KEY_PREFIX}{trade.symbol}",
                json.dumps(payload),
                ex=LIVE_PRICE_TTL_SECONDS,
            )
        except Exception as exc:
            print(f"[ALPACA_STREAM] Error writing live price for {getattr(trade, 'symbol', '?')}: {exc}",
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
        state["subscribed"] = reconcile_subscriptions(
            stream, desired, state["subscribed"], _on_trade
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
