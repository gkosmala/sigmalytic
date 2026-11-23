
# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Tastytrade futures market-data service coordinator.
# Read-only. No account access or order execution.

import asyncio
import logging
import time
from datetime import datetime, timezone

from backend.tastytrade_futures import discover_futures
from backend.tastytrade_dxlink import DXLinkFutures

log = logging.getLogger(__name__)

CATALOG_REFRESH_SECONDS = 3600
RESTART_DELAY_SECONDS = 10


class TastytradeFuturesService:
    def __init__(self):
        self.stream = DXLinkFutures()
        self.contracts = []
        self.running = False
        self.last_catalog_refresh = None
        self.last_catalog_error = None
        self._task = None
        self._stop_event = asyncio.Event()

    async def refresh_catalog(self):
        """Retrieve available futures and configure subscriptions."""

        contracts = await asyncio.to_thread(
            discover_futures
        )

        if not isinstance(contracts, list):
            raise RuntimeError(
                "Futures discovery returned invalid data"
            )

        if not contracts:
            raise RuntimeError(
                "Futures discovery returned no contracts"
            )

        self.contracts = contracts
        self.stream.set_symbols(contracts + [dict(streamer_symbol=x,symbol=x,root=x) for x in ('VXX', 'VIX', '$VIX', '.VIX', 'VIX:X', 'SPX', '$SPX', '.SPX', 'SPX:X', 'SPX.X', '$SPX.X', 'SPX:XCBO', 'SPX:INDEX', 'SPX.CBOE')])

        self.last_catalog_refresh = datetime.now(
            timezone.utc
        ).isoformat()

        self.last_catalog_error = None

        log.info(
            "Tastytrade futures catalog loaded: %d contracts",
            len(contracts),
        )

        return len(contracts)

    async def _run(self):
        """Manage the catalog and streaming connection."""

        self.running = True

        try:
            while not self._stop_event.is_set():
                try:
                    await self.refresh_catalog()

                    # Run the streaming engine until the
                    # next scheduled catalog refresh.
                    stream_task = asyncio.create_task(
                        self.stream.run()
                    )

                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=CATALOG_REFRESH_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        pass
                    finally:
                        await self.stream.stop()

                        stream_task.cancel()
                        await asyncio.gather(
                            stream_task,
                            return_exceptions=True,
                        )

                        # Create a fresh engine for the next
                        # subscription cycle.
                        self.stream = DXLinkFutures()

                except asyncio.CancelledError:
                    raise

                except Exception as exc:
                    self.last_catalog_error = (
                        type(exc).__name__
                    )

                    log.warning(
                        "Tastytrade futures service error: %s",
                        type(exc).__name__,
                    )

                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=RESTART_DELAY_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        pass

        finally:
            self.running = False

    async def start(self):
        """Start background futures market-data processing."""

        if self._task is not None and not self._task.done():
            return

        self._stop_event.clear()
        self.stream = DXLinkFutures()

        self._task = asyncio.create_task(
            self._run(),
            name="tastytrade-futures-market-data",
        )

    async def stop(self):
        """Stop futures market-data processing cleanly."""

        self._stop_event.set()
        await self.stream.stop()

        if self._task is not None:
            self._task.cancel()

            await asyncio.gather(
                self._task,
                return_exceptions=True,
            )

            self._task = None

        self.running = False

    def status(self):
        """Return diagnostic status without exposing credentials."""

        stream_status = self.stream.snapshot()

        return {
            "provider": "tastytrade",
            "market": "futures",
            "mode": "read_only",
            "service_running": self.running,
            "contracts_discovered": len(self.contracts),
            "last_catalog_refresh": self.last_catalog_refresh,
            "last_catalog_error": self.last_catalog_error,
            "stream_connected": stream_status["connected"],
            "stream_authorized": stream_status["authorized"],
            "entitlement_level": stream_status["entitlement_level"],
            "subscribed_symbols": stream_status["subscribed_symbols"],
            "received_symbols": stream_status["received_symbols"],
            "stream_error": stream_status["last_error"],
        }

    def quotes(self):
        """Return the latest received futures market data."""

        return self.stream.snapshot()["quotes"]


tastytrade_futures_service = TastytradeFuturesService()
