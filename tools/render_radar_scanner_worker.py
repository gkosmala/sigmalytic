"""
tools/render_radar_scanner_worker.py
--------------------------------------
Standalone, continuously-running radar scanner worker.

WHY THIS EXISTS (2026-07-29): the radar scanner (radar_service.py's
start_radar_scheduler -- gex_scan, radar_scan, divergence_scan,
snapshot_intraday, and related jobs, scanning ~1000 symbols every
5-8 minutes) used to run inside the same shared process as the main
web backend. Confirmed via direct memory instrumentation and production
crash logs: when this scanner's memory use stacked on top of the main
backend's own heavy endpoints (active_campaigns/rankings/status), the
combined process repeatedly exceeded 2GB and crashed.

This mirrors the exact fix already applied earlier the same day to the
nightly campaign pipeline (moved to its own Render cron service for the
same reason): the scanner now runs here, in its own separate Render
service, with its own memory entirely separate from the web-serving
process. Results are published to Redis (radar:cache key) so the main
backend can still read them -- see get_radar_scores()'s Redis fallback
in radar_service.py.

Unlike the nightly campaign pipeline (a Render Cron Job that runs once
and exits), this needs to run continuously all day, since the scanner's
own APScheduler jobs run on 5-8 minute intervals throughout market
hours. This is a Render "Background Worker" service, not a cron job:
it starts once, runs forever, and does not serve HTTP traffic.

Requires the same environment variables as the main backend that this
scanner actually uses: ALPACA credentials, SUPABASE credentials (for
the divergence watchlist), REDIS_URL (to publish results), and
RESEND_API_KEY (used by some of the scheduled report/alert jobs).
"""

from __future__ import annotations

import os
import sys
import time

# Make the repo root importable, same as the backend service does, so
# `from backend.radar_service import ...` resolves correctly.
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo_root)


def main() -> int:
    print("[RADAR_WORKER] Starting standalone radar scanner worker...", flush=True)

    required_env = ["SUPABASE_URL"]
    missing = [name for name in required_env if not (os.getenv(name) or "").strip()]
    if missing:
        print(
            f"[RADAR_WORKER] Missing required environment variables: {', '.join(missing)}. "
            f"This worker needs its own Supabase/Alpaca/Redis credentials, same as the "
            f"main backend service.",
            flush=True,
        )
        return 2

    try:
        from backend.radar_service import start_radar_scheduler
    except Exception as exc:
        print(f"[RADAR_WORKER] Failed to import radar_service: {exc}", flush=True)
        return 1

    try:
        start_radar_scheduler()
        print("[RADAR_WORKER] Radar scheduler started successfully.", flush=True)
    except Exception as exc:
        print(f"[RADAR_WORKER] Failed to start radar scheduler: {exc}", flush=True)
        return 1

    # start_radar_scheduler() launches a BackgroundScheduler, which runs
    # its jobs on background threads. Without something keeping the main
    # thread alive, this process would exit immediately and the scheduler
    # would die with it. This loop is that -- it does nothing itself,
    # just keeps the process (and therefore the background scheduler)
    # alive indefinitely.
    # ADDED (2026-08-20): pick up any pending report-generation requests
    # queued by the web backend (see backend/reports_engine.py's
    # start_report_generation_job -- it now enqueues here instead of
    # running the heavy computation inline on the web-facing process,
    # after confirming a single run of that computation could crash
    # the whole backend on its own, independent of the concurrency bug
    # fixed earlier the same day). Checked on a tight, 15-second
    # cadence -- much tighter than this loop's original 60s sleep --
    # so a subscriber clicking "Generate Report" doesn't wait
    # needlessly long for this worker to notice the request, while
    # still keeping the actual heavy work fully isolated from the web
    # backend's own memory budget, on this already-separate process.
    try:
        from backend.reports_engine import process_one_pending_report_job
    except Exception as exc:
        print(f"[RADAR_WORKER] Could not import report-job processor: {exc}", flush=True)
        process_one_pending_report_job = None

    print("[RADAR_WORKER] Running. Sleeping to keep the scheduler alive, "
          "polling for pending report-generation requests every 15s.", flush=True)
    while True:
        if process_one_pending_report_job is not None:
            try:
                processed = process_one_pending_report_job()
                if processed:
                    print("[RADAR_WORKER] Processed one queued report-generation request.", flush=True)
            except Exception as exc:
                print(f"[RADAR_WORKER] Error while checking for report jobs: {exc}", flush=True)
        time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
