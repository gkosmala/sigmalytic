#!/usr/bin/env python3
"""
Sigmalytic V2 Step 10 — Production observability and deploy check.

Purpose:
    Verify essential live endpoints and local git state.

Mode:
    GET/read-only.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

URLS = [
    "https://sigmalytic-frontend.onrender.com/",
    "https://sigmalytic-frontend.onrender.com/_dash-layout",
    "https://sigmalytic-frontend.onrender.com/_dash-dependencies",
    "https://sigmalytic-backend.onrender.com/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep",
]

REPORT = Path("audit_step10_observability_deploy_check.json")


def git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout.strip()


def get_status(url: str) -> int:
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Sigmalytic-V2-Step10-Observability",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return int(res.status)


def get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Sigmalytic-V2-Step10-Observability",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode("utf-8", errors="replace"))
        if not isinstance(payload, dict):
            raise TypeError("backend payload is not a JSON object")
        return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-head", default=None)
    parser.add_argument("--strict-clean", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 10 OBSERVABILITY DEPLOY CHECK")
    print("MODE: GET ONLY / READ-ONLY")
    print("=" * 72)

    failures: list[str] = []
    warnings: list[str] = []
    endpoint_results: dict[str, int] = {}

    head = git(["rev-parse", "--short", "HEAD"])
    print(f"LOCAL HEAD: {head}")

    if args.expected_head and head != args.expected_head:
        failures.append(f"expected HEAD {args.expected_head}, got {head}")

    dirty = git(["status", "--porcelain"])
    if dirty:
        if args.strict_clean:
            failures.append("working tree is dirty under --strict-clean")
        else:
            warnings.append("working tree has local changes; acceptable for current local audit path before commit.")
            print("WARN: working tree has local changes.")
            print(dirty)
    else:
        print("PASS: working tree clean.")

    for url in URLS:
        try:
            code = get_status(url)
            endpoint_results[url] = code
            if code == 200:
                print(f"PASS: {url} returned HTTP 200")
            else:
                failures.append(f"{url} returned HTTP {code}")
        except Exception as exc:
            endpoint_results[url] = -1
            failures.append(f"{url} GET failed: {exc}")

    backend_url = URLS[-1]
    try:
        backend = get_json(backend_url)
        require(backend.get("d3e_phase") == "D3E.9", "backend D3E phase is D3E.9")
        require(backend.get("final_lifecycle_verified") is True, "backend final lifecycle verified is True")

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "operator_control_confirmed",
            "touches_stripe",
        ]:
            require(backend.get(field) is False, f"backend {field} is False")
    except Exception as exc:
        failures.append(f"backend D3E.9 payload validation failed: {exc}")

    report = {
        "mode": "GET_ONLY_READ_ONLY_NO_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "local_head": head,
        "working_tree_dirty": bool(dirty),
        "warnings": warnings,
        "failures": failures,
        "endpoint_results": endpoint_results,
        "doctrine": {
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True
        }
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report written: {REPORT}")

    if warnings:
        print("\nWARNINGS")
        for warning in warnings:
            print(f"WARN: {warning}")

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print(f"FAIL: {failure}")
        print("=" * 72)
        print("FAIL: STEP 10 OBSERVABILITY CHECK FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 10 COMPLETE — PRODUCTION OBSERVABILITY CHECK PASSED")
    print("PASS: live frontend/backend endpoints are reachable.")
    print("PASS: D3E.9 remains clean.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
