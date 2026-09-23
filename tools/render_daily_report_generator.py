"""
tools/render_daily_report_generator.py
-----------------------------------------
Daily subscriber intelligence report generator -- cron entry point.

Queues the report job, waits for the worker to finish, verifies its saved
archive and content, and reports an actual failure if delivery fails.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone


def _get_json(url: str, headers=None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    backend = os.getenv("SIGMALYTIC_BACKEND_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
    report_date = os.getenv("SIGMALYTIC_REPORT_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
        print("[REPORT_CRON] REPORT_CRON_SECRET is missing; report not started.", flush=True)
        return 1

    print(f"[REPORT_CRON] Starting report for {report_date}", flush=True)
    query = urllib.parse.urlencode({"date": report_date})
    headers = {"X-Cron-Secret": cron_secret}
    try:
        body = _get_json(f"{backend}/api/admin/generate-report?{query}", headers)
    except Exception as exc:
        print(f"[REPORT_CRON] Failed: {exc}", flush=True)
        return 1

    if not body.get("ok") or body.get("status") != "started":
        print(f"[REPORT_CRON] Could not queue report: {body}", flush=True)
        return 1

    unknown_count = 0
    deadline = time.monotonic() + 45 * 60
    while time.monotonic() < deadline:
        time.sleep(10)
        try:
            status = _get_json(f"{backend}/api/admin/generate-report-status?{query}", headers)
        except Exception as exc:
            status = {"status": "unknown", "error": str(exc)}
        if status.get("status") == "running":
            unknown_count = 0
            continue
        if status.get("status") == "unknown":
            unknown_count += 1
            if unknown_count < 5:
                continue
        if status.get("status") != "done":
            print(f"[REPORT_CRON] Report failed: {status}", flush=True)
            return 1
        if status.get("backup_ok") is not True:
            print("[REPORT_CRON] Report was generated, but archive backup failed.", flush=True)
            return 1
        if status.get("email_error") or status.get("email_failed", 0):
            print(f"[REPORT_CRON] Report saved, email delivery failed: {status}", flush=True)
            return 1
        try:
            catalog = _get_json(f"{backend}/api/reports/list")
            report = _get_json(f"{backend}/api/reports/{urllib.parse.quote(report_date)}")
            if not catalog.get("ok") or report_date not in catalog.get("dates", []):
                raise ValueError("Report missing from saved history")
            if not report.get("ok") or not report.get("html"):
                raise ValueError("Saved report content cannot be opened")
        except Exception as exc:
            print(f"[REPORT_CRON] Saved report verification failed: {exc}", flush=True)
            return 1
        print(f"[REPORT_CRON] Report saved for {report_date}; "
              f"subscriber emails sent: {status.get('email_sent', 0)}", flush=True)
        return 0

    print(f"[REPORT_CRON] Timed out waiting for {report_date}; inspect worker logs.", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
