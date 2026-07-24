"""
RFA11 authenticated Render cron caller for Sigmalytic nightly campaign refresh.

This script is intended to run as a Render cron job. It does not import the
pipeline directly and does not access Supabase. It calls the backend's protected
nightly route using a shared secret header.

No secret values are printed.

FIX (2026-07-24): The original `_compact()` used a hard depth cutoff of 3 combined
with a narrow key whitelist for recursion below depth 2. The real backend response
nests discovery diagnostics 5+ levels deep
(response -> steps -> campaign_pipeline -> result -> discovery -> diagnostics),
so the old logic silently dropped the entire `discovery` block (not even printed
as truncated -- just absent from the key list) and stringified even simple
booleans like `ok` as "...truncated..." once they fell past depth 3.

This version recurses through the full object graph up to a generous depth cap
(12, chosen because the real payload is at most ~7 levels deep) and only
truncates lists over `max_list_items`, with a visible count of how many items
were dropped. Secret-like keys are still redacted regardless of depth.
"""

from __future__ import annotations

import json
import os
import sys
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


def _compact(obj, depth: int = 0, max_depth: int = 12, max_list_items: int = 20):
    """
    Recursively copy `obj`, redacting secret-like keys and truncating only
    lists that exceed `max_list_items`. Dict keys and nested structure are
    preserved in full up to `max_depth`, which is deliberately generous
    relative to the actual response shape so nothing important is silently
    dropped.
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
            keep[key] = _compact(value, depth + 1, max_depth, max_list_items)
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

    url = f"{backend_url}/api/admin/run-full-nightly"
    timeout_seconds = _int_env("SIGMALYTIC_NIGHTLY_CRON_TIMEOUT_SECONDS", 900)

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Sigmalytic-RFA11-Render-Nightly-Campaign-Cron",
            "X-Sigmalytic-Cron-Token": token,
        },
    )

    started_at = datetime.utcnow().isoformat()

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status_code = resp.status

        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw_preview": raw[:4000]}

        ok = bool(isinstance(data, dict) and data.get("ok") is True)
        compact = _compact(data)

        print(
            json.dumps(
                {
                    "ok": ok,
                    "http_status": status_code,
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                    "response": compact,
                },
                indent=2,
                default=str,
            )
        )

        return 0 if ok else 1

    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")[:4000]
        print(
            json.dumps(
                {
                    "ok": False,
                    "http_status": exc.code,
                    "error": str(exc),
                    "response_preview": response_body,
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 1

    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "source": "rfa11_render_nightly_campaign_refresh",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
