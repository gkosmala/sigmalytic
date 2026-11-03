"""
tools/render_platform_review.py
-------------------------------
Weekly Platform Review -- cron entry point (Render service sigmalytic-platform-review).

Render schedules in UTC, so this job fires at 01:15 and 02:15 UTC every Saturday. The backend lets only the call
that is Friday 9:15 pm in New York through (01:15 UTC in daylight time, 02:15 UTC in standard time) and skips the
other one, and it skips both when the Admin tab toggle is set to Manual. When a review starts, this script waits
for the report and prints a one-line result for the Render log.

Needs REPORT_CRON_SECRET set to the same value here and on sigmalytic-backend (the same secret the daily report
cron already uses).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request


def _get_json(url: str, headers=None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    backend = os.getenv("SIGMALYTIC_BACKEND_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
    secret = os.getenv("REPORT_CRON_SECRET", "")
    if not secret:
        print("[PLATFORM_REVIEW] REPORT_CRON_SECRET is missing; review not started.", flush=True)
        return 1
    headers = {"X-Cron-Secret": secret}
    try:
        body = _get_json(f"{backend}/api/admin/platform-review/scheduled", headers)
    except Exception as exc:
        print(f"[PLATFORM_REVIEW] Failed to reach the backend: {exc}", flush=True)
        return 1
    if body.get("status") == "skipped":
        print(f"[PLATFORM_REVIEW] Skipped: {body.get('reason')}", flush=True)
        return 0
    if body.get("status") not in ("started", "running"):
        print(f"[PLATFORM_REVIEW] Could not start the review: {body}", flush=True)
        return 1

    print("[PLATFORM_REVIEW] Review started; waiting for the report.", flush=True)
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        time.sleep(15)
        try:
            st = _get_json(f"{backend}/api/admin/platform-review/status", headers)
        except Exception as exc:
            print(f"[PLATFORM_REVIEW] Status check failed (will retry): {exc}", flush=True)
            continue
        if not st.get("running"):
            latest = st.get("latest") or {}
            print(f"[PLATFORM_REVIEW] Done: {latest.get('generated_at_et')} · "
                  f"{len(latest.get('findings') or [])} findings · AI used: {latest.get('ai_used')} · "
                  f"{latest.get('note') or 'ok'}", flush=True)
            return 0
    print("[PLATFORM_REVIEW] Timed out waiting for the report (15 minutes).", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
