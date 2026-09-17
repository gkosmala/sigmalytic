"""
tools/render_daily_report_generator.py
-----------------------------------------
Daily subscriber intelligence report generator -- cron entry point.

Calls the backend's /api/admin/generate-report endpoint once per day.
Unlike the nightly campaign refresh (a long-running, multi-minute
pipeline that was moved to direct in-process execution specifically to
avoid gunicorn's worker-recycling killing it mid-run), report
generation is a single, fast HTTP call -- fetches up to 100 already-
enriched rows, builds an HTML document, stores it in Redis. This
completes in seconds, not minutes, so a simple HTTP-based cron script
is appropriate and safe here.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone


def main() -> int:
    backend = os.getenv("SIGMALYTIC_BACKEND_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
    report_date = os.getenv("SIGMALYTIC_REPORT_DATE")  # optional override, e.g. for manual backfills
    url = f"{backend}/api/admin/generate-report"
    if report_date:
        url += f"?date={report_date}"

    # ADDED (2026-09-16): confirmed a real, genuine gap -- this
    # endpoint requires admin authentication, which this automated
    # cron job had no way to provide, so every single scheduled run
    # was very likely failing this same way, not just the one
    # reported. REPORT_CRON_SECRET must be set to the SAME value on
    # both this cron service and the backend service on Render for
    # this to work -- logging clearly here so a missing/mismatched
    # secret is immediately obvious in the logs, not another mystery.
    cron_secret = os.getenv("REPORT_CRON_SECRET", "")
    if not cron_secret:
        print("[REPORT_CRON] WARNING: REPORT_CRON_SECRET is not set on this service -- "
              "this request will be rejected as unauthenticated.", flush=True)

    print(f"[REPORT_CRON] Requesting report generation: {url}", flush=True)
    req = urllib.request.Request(url, headers={"X-Cron-Secret": cron_secret} if cron_secret else {})
    try:
        with urllib.request.urlopen(req, timeout=320) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[REPORT_CRON] Failed: {exc}", flush=True)
        return 1

    if body.get("ok"):
        print(f"[REPORT_CRON] Success -- date={body.get('date')} length={body.get('length')}", flush=True)
        return 0

    print(f"[REPORT_CRON] Backend reported failure: {body}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
