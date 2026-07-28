"""
RFA11 nightly campaign refresh -- DIRECT EXECUTION VERSION (2026-07-28)
------------------------------------------------------------------------
This replaces the earlier HTTP-based design (POST to the backend's
/api/admin/run-full-nightly, then poll /api/admin/nightly-status/{job_id}
until done or timeout).

Why this changed:
That HTTP-based design ran the actual pipeline as a background thread
INSIDE the shared backend web server process. This created an
unavoidable conflict: the backend needed periodic worker recycling
(--max-requests) to prevent memory growth from crashing it, but that
same recycling could kill the nightly job mid-run if it happened to
fire while the job was still working -- which it repeatedly did in
production. Tuning the numbers on either side just traded one failure
mode for the other; it could never fully resolve both at once as long
as the job and the recyclable web server shared one process.

This version runs the pipeline directly, in this script's own process --
the cron service, not the web service. This process starts fresh for
each scheduled run and exits when done; gunicorn's worker recycling on
the backend has nothing to do with it and can never interrupt it.
Requires this cron service to have its own Supabase and Alpaca
credentials (previously only the backend needed them, since this script
only made HTTP calls to it).

No secret values are printed.
"""

from __future__ import annotations

import json
import os
import sys
import time
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


_SECRET_KEYS = {"cron_token", "token", "secret", "authorization", "api_key", "api_secret"}
_NOISY_LIST_KEYS = {"results", "discovered_symbols"}
_NOISY_LIST_MAX_ITEMS = 3


def _compact(obj, depth: int = 0, max_depth: int = 12, max_list_items: int = 20):
    """
    Recursively copy `obj`, redacting secret-like keys and truncating only
    lists that exceed their item cap. Preserved from the previous version
    of this script -- same compaction logic, still needed since the real
    pipeline result can be large.
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


def _alert_failure(reason: str):
    """
    Sends an admin alert on failure, reusing the same alerting system
    already built for the backend. Wrapped so a problem with alerting
    itself can never mask or replace the real failure being reported.
    """
    try:
        # This script runs from the repo root (same as the backend), so
        # the same package-qualified import works here too.
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend.email_service import send_admin_alert_sync
        send_admin_alert_sync(
            subject="Nightly campaign pipeline failed",
            message=f"The nightly campaign refresh job failed (direct-execution cron).<br><br>Reason: {reason}",
            alert_key="nightly_cron_failure",
        )
    except Exception:
        pass


def main() -> int:
    started_at = datetime.utcnow().isoformat()

    required_env = ["SUPABASE_URL"]
    missing = [name for name in required_env if not (os.getenv(name) or "").strip()]
    has_supabase_key = bool(
        (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    )
    has_alpaca_key = bool(
        (os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or "").strip()
    )
    has_alpaca_secret = bool(
        (os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or "").strip()
    )

    if missing or not has_supabase_key or not has_alpaca_key or not has_alpaca_secret:
        problems = []
        if missing:
            problems.append(f"missing: {', '.join(missing)}")
        if not has_supabase_key:
            problems.append("missing: SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY")
        if not has_alpaca_key:
            problems.append("missing: ALPACA_API_KEY or APCA_API_KEY_ID")
        if not has_alpaca_secret:
            problems.append("missing: ALPACA_API_SECRET, ALPACA_SECRET_KEY, or APCA_API_SECRET_KEY")
        error_msg = "; ".join(problems)
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Cron service is missing required credentials ({error_msg}). "
                             f"This script now runs the pipeline directly and needs its own "
                             f"Supabase and Alpaca credentials, not just BACKEND_URL.",
                    "source": "rfa11_render_nightly_campaign_refresh_direct",
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
                    "source": "rfa11_render_nightly_campaign_refresh_direct",
                    "payload": payload,
                    "would_run": "backend.campaign_engine.nightly_campaign_pipeline.run_nightly_campaign_pipeline",
                    "generated_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 0

    # Make the repo root importable, same as the backend service does,
    # so `from backend.campaign_engine... import ...` resolves correctly.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, repo_root)

    try:
        from backend.campaign_engine.nightly_campaign_pipeline import run_nightly_campaign_pipeline
    except Exception as exc:
        error_msg = f"Failed to import pipeline: {exc}"
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": error_msg,
                    "source": "rfa11_render_nightly_campaign_refresh_direct",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        _alert_failure(error_msg)
        return 1

    try:
        result = run_nightly_campaign_pipeline(**payload)
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True

        print(
            json.dumps(
                {
                    "ok": ok,
                    "source": "rfa11_render_nightly_campaign_refresh_direct",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                    "result": _compact(result),
                },
                indent=2,
                default=str,
            )
        )
        if not ok:
            _alert_failure("Pipeline returned ok=False -- see result for details.")
        return 0 if ok else 1

    except Exception as exc:
        error_msg = str(exc)
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": error_msg,
                    "source": "rfa11_render_nightly_campaign_refresh_direct",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
                default=str,
            )
        )
        _alert_failure(error_msg)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
