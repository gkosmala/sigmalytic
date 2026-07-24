"""
RFA11 authenticated Render cron caller for Sigmalytic nightly campaign refresh.

This script is intended to run as a Render cron job. It does not import the
pipeline directly and does not access Supabase. It calls the backend's protected
nightly route using a shared secret header.

No secret values are printed.

FIX (2026-07-24, compaction): The original `_compact()` used a hard depth
cutoff of 3 combined with a narrow key whitelist for recursion below depth 2.
The real backend response nests discovery diagnostics 5+ levels deep, so the
old logic silently dropped the entire `discovery` block. This version
recurses through the full object graph up to a generous depth cap (12) and
only truncates lists over `max_list_items`, with noisy per-symbol lists
capped much harder than summary/diagnostics dicts.

FIX (2026-07-24, async execution): The nightly pipeline can take 6-14+
minutes to run. The previous version sent ONE blocking HTTP POST and waited
for the entire pipeline to finish before getting a response. Render's own
edge/proxy layer has its own response timeout that is shorter than that --
independent of anything configurable in this script or in gunicorn/uvicorn --
so long runs intermittently came back as "502 Bad Gateway" even though the
backend was still working correctly in the background.

This version instead:
  1. POSTs to /api/admin/run-full-nightly, which now returns almost
     instantly with a job_id (the backend runs the actual pipeline in a
     background thread).
  2. Polls /api/admin/nightly-status/{job_id} at a fixed interval until the
     job reports "completed" or "failed", or until the overall time budget
     (SIGMALYTIC_NIGHTLY_CRON_TIMEOUT_SECONDS) is exhausted.
  3. Prints the same compacted JSON summary as before once the job finishes,
     or a clear timeout report if it doesn't finish within the budget (the
     job may still complete on the backend even if this script gives up
     waiting -- that is a distinct, correctly-labeled outcome from a
     genuine failure).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "enabled", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except Exception as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


_SECRET_KEYS = {"cron_token", "token", "secret", "authorization"}

# These keys hold per-symbol verdict/result lists with deeply nested evidence
# (Wyckoff/Livermore/Weis/option-chain trees). They are capped much harder
# than other lists so a single run's log stays readable, while every
# diagnostics/summary dict (universe_count, alpaca_bars_symbols, etc.) is
# left fully intact -- dicts are never truncated by list capping.
_NOISY_LIST_KEYS = {"results", "discovered_symbols"}
_NOISY_LIST_MAX_ITEMS = 3


def _compact(obj, depth: int = 0, max_depth: int = 12, max_list_items: int = 20):
    """
    Recursively copy `obj`, redacting secret-like keys and truncating only
    lists that exceed their item cap. Dict keys and nested structure are
    preserved in full up to `max_depth`, which is deliberately generous
    relative to the actual response shape so nothing important is silently
    dropped. Lists under a key in `_NOISY_LIST_KEYS` get a much smaller cap
    since they hold heavy per-symbol verdict data, not summary diagnostics.
    """
    if isinstance(obj, dict):
        keep = {}
        for key, value in obj.items():
            if str(key).lower() in _SECRET_KEYS:
                keep[key] = "[redacted]"
                continue
            if depth >= max_depth:
                keep[key] = "...max_depth_reached..."
                continue
            effective_max_list_items = (
                _NOISY_LIST_MAX_ITEMS if key in _NOISY_LIST_KEYS else max_list_items
            )
            keep[key] = _compact(value, depth + 1, max_depth, effective_max_list_items)
        return keep

    if isinstance(obj, list):
        if depth >= max_depth:
            return "...max_depth_reached..."
        kept_items = obj[:max_list_items]
        out = [
            _compact(item, depth + 1, max_depth, max_list_items)
            for item in kept_items
        ]
        remainder = len(obj) - len(kept_items)
        if remainder > 0:
            out.append(f"...and {remainder} more items truncated...")
        return out

    return obj


def _request_json(url: str, token: str, method: str = "GET", payload: dict | None = None,
                   timeout: int = 30):
    """
    Makes one HTTP request and returns (status_code, parsed_json_or_None,
    raw_text). Never raises for HTTP error responses -- the caller decides
    what to do with a non-200 status. Only raises for genuine connection-
    level failures (DNS, refused connection, etc.), which the caller
    catches separately.
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Sigmalytic-RFA11-Render-Nightly-Campaign-Cron",
        "X-Sigmalytic-Cron-Token": token,
    }
    body = json.dumps(payload).encode("utf-8") if payload is not None else None

    req = urllib.request.Request(url, data=body, method=method, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status_code = exc.code

    try:
        data = json.loads(raw)
    except Exception:
        data = None

    return status_code, data, raw


def main() -> int:
    backend_url = (
        os.getenv("BACKEND_URL")
        or os.getenv("SIGMALYTIC_BACKEND_URL")
        or "https://sigmalytic-backend.onrender.com"
    ).rstrip("/")

    token = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_TOKEN") or "").strip()

    if not token:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "missing_SIGMALYTIC_NIGHTLY_CRON_TOKEN",
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "generated_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 2

    payload = {
        "max_symbols": _int_env("SIGMALYTIC_NIGHTLY_CRON_MAX_SYMBOLS", 1500),
        "bar_limit": _int_env("SIGMALYTIC_NIGHTLY_CRON_BAR_LIMIT", 252),
        "timeframe": os.getenv("SIGMALYTIC_NIGHTLY_CRON_TIMEFRAME", "DAILY"),
    }

    dry_run = _truthy(os.getenv("SIGMALYTIC_NIGHTLY_CRON_DRY_RUN"))

    if dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "backend_url": backend_url,
                    "token_present": bool(token),
                    "payload": payload,
                    "would_call": f"{backend_url}/api/admin/run-full-nightly",
                    "generated_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 0

    overall_timeout_seconds = _int_env("SIGMALYTIC_NIGHTLY_CRON_TIMEOUT_SECONDS", 900)
    poll_interval_seconds = _int_env("SIGMALYTIC_NIGHTLY_CRON_POLL_INTERVAL_SECONDS", 15)

    started_at = datetime.utcnow().isoformat()
    deadline = time.monotonic() + overall_timeout_seconds

    # ---- Step 1: start the job. This call should return almost instantly. ----
    start_url = f"{backend_url}/api/admin/run-full-nightly"

    try:
        status_code, data, raw = _request_json(
            start_url, token, method="POST", payload=payload, timeout=30
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"failed_to_start_job: {exc}",
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 1

    if status_code != 200 or not isinstance(data, dict) or not data.get("job_id"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "http_status": status_code,
                    "error": "did_not_receive_job_id",
                    "response_preview": (raw or "")[:4000],
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 1

    job_id = data["job_id"]

    # ---- Step 2: poll until the job completes, fails, or we run out of time. ----
    status_url = f"{backend_url}/api/admin/nightly-status/{job_id}"
    last_status_payload = None

    while time.monotonic() < deadline:
        time.sleep(poll_interval_seconds)

        try:
            poll_status_code, poll_data, poll_raw = _request_json(
                status_url, token, method="GET", timeout=30
            )
        except Exception as exc:
            # A single failed poll doesn't mean the job failed -- the job
            # keeps running on the backend regardless. Just try again on
            # the next interval, up to the overall deadline.
            continue

        if poll_status_code != 200 or not isinstance(poll_data, dict):
            continue

        last_status_payload = poll_data
        job_status = poll_data.get("status")

        if job_status in ("completed", "failed"):
            ok = job_status == "completed"
            print(
                json.dumps(
                    {
                        "ok": ok,
                        "job_status": job_status,
                        "job_id": job_id,
                        "source": "rfa11_render_nightly_campaign_refresh",
                        "started_at": started_at,
                        "finished_at": datetime.utcnow().isoformat(),
                        "response": _compact(poll_data),
                    },
                    indent=2,
                    default=str,
                )
            )
            return 0 if ok else 1

    # ---- Deadline exceeded without the job reporting completed/failed. ----
    # This is a distinct, honestly-labeled outcome: the job may well still
    # be running (or may have finished) on the backend -- this script simply
    # gave up waiting within its own time budget. Treat as a failure for
    # the cron's exit code, but do not claim the pipeline itself failed.
    print(
        json.dumps(
            {
                "ok": False,
                "error": "polling_timeout_before_job_finished",
                "job_id": job_id,
                "note": "The job may still be running or may have finished on the backend; this script stopped waiting after its own time budget.",
                "last_known_status": _compact(last_status_payload) if last_status_payload else None,
                "source": "rfa11_render_nightly_campaign_refresh",
                "started_at": started_at,
                "finished_at": datetime.utcnow().isoformat(),
            },
            indent=2,
            default=str,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
