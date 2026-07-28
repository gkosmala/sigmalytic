#!/usr/bin/env python3
"""
Sigmalytic V2 Step 3 — No-drift backend/frontend regression sweep.

Purpose:
    Verify the live D3E.9 endpoint and live Dash shell remain safe after future work.

Mode:
    HTTP GET only. No POST/PATCH/DELETE. No Supabase mutation. No D3D. No Stripe.

Usage:
    py -B 03_no_drift_regression_sweep.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

BACKEND = "https://sigmalytic-backend.onrender.com/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep"
LAYOUT = "https://sigmalytic-frontend.onrender.com/_dash-layout"
DEPENDENCIES = "https://sigmalytic-frontend.onrender.com/_dash-dependencies"

REQUIRED_FALSE_FIELDS = [
    "writes_to_supabase",
    "mutates_campaigns",
    "executes_d3d",
    "authorizes_d3d",
    "operator_control_confirmed",
    "touches_stripe",
]

REQUIRED_SHELL_MARKERS = [
    "main-content",
    "Decision Command Center",
    "Command Center",
    "Live Feed",
    "Radar Screen",
    "Scoreboard",
    "Preferences",
    "Setup",
]

FORBIDDEN_GLOBAL_MARKERS = [
    "d3f1b-today-entrypoint-controlled-persistence-mount",
    "Controlled Persistence Lifecycle",
    "D3F1B_TODAY_FRONTEND_FETCH_ERROR",
    "ATTENTION",
]


def get_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Sigmalytic-V2-NoDrift-Sweep",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        status = getattr(res, "status", None)
        if status != 200:
            raise RuntimeError(f"{url} returned HTTP {status}")
        return res.read().decode("utf-8", errors="replace")


def get_json(url: str) -> dict[str, Any]:
    text = get_text(url)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("Backend JSON payload is not an object.")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 3 NO-DRIFT REGRESSION SWEEP")
    print("MODE: GET ONLY / READ-ONLY / NO MUTATION")
    print("=" * 72)

    print("\nBACKEND D3E.9 CHECK")
    payload = get_json(BACKEND)

    require(payload.get("d3e_phase") == "D3E.9", "D3E phase is D3E.9")
    require(payload.get("final_lifecycle_verified") is True, "final lifecycle verified is True")

    for field in REQUIRED_FALSE_FIELDS:
        require(payload.get(field) is False, f"{field} is False")

    print("\nFRONTEND DASH SHELL CHECK")
    layout = get_text(LAYOUT)
    deps = get_text(DEPENDENCIES)
    combined = layout + "\n" + deps

    for marker in REQUIRED_SHELL_MARKERS:
        require(marker in combined, f"live shell marker present: {marker}")

    for marker in FORBIDDEN_GLOBAL_MARKERS:
        require(marker not in combined, f"forbidden global marker absent: {marker}")

    print("\nFINAL VERDICT")
    print("=" * 72)
    print("PASS: Step 3 no-drift regression sweep complete.")
    print("PASS: Backend D3E.9 remains clean.")
    print("PASS: Live Dash shell remains present.")
    print("PASS: Global D3F/D3E panel remains absent from live layout/dependencies.")
    print("PASS: No write, mutation, D3D, operator-control confirmation, trade signal, or Stripe action occurred.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"FAIL: network/read-only GET failed: {exc}")
        raise SystemExit(1)
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
