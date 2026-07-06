#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

BASE_URL = "https://sigmalytic-backend.onrender.com"
LABEL_POLICY = "LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION"

def request_json(path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = BASE_URL.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}

    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Optional[Exception] = None

    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"REQUEST_FAILED attempt={attempt} method={method} path={path}: {exc}")
            time.sleep(10)

    raise RuntimeError(f"Request failed after 3 attempts: {method} {path}") from last_error

def require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"PASS {label}: {actual!r}")

def main() -> int:
    print("SIGMALYTIC V2 D3P NO-DRIFT LIVE AUDIT")
    print("BASE_URL", BASE_URL)
    print("MUTATION_MODE", "READ_ONLY")

    rankings = request_json("/api/campaign/evidence-diagnostic-rankings")

    print("")
    print("D3M CONTRACT")
    print("legacy_operator_control_evidence_count", rankings.get("legacy_operator_control_evidence_count"))
    print("d3d_production_confirmed_operator_control_count", rankings.get("d3d_production_confirmed_operator_control_count"))
    print("operator_control_confirmation_label_policy", rankings.get("operator_control_confirmation_label_policy"))
    print("operator_control_confirmed_count", rankings.get("operator_control_confirmed_count"))

    require_equal("old operator_control_confirmed_count absent", rankings.get("operator_control_confirmed_count"), None)
    require_equal("D3D production confirmed count", rankings.get("d3d_production_confirmed_operator_control_count"), 0)
    require_equal("label policy", rankings.get("operator_control_confirmation_label_policy"), LABEL_POLICY)

    d3j = request_json("/api/campaign/operator-control-plausibility-status-review")

    print("")
    print("D3J PLAUSIBILITY")
    print("total_campaigns", d3j.get("total_campaigns"))
    print("guardrail_failure_count", d3j.get("guardrail_failure_count"))
    print("plausibility_status_distribution", json.dumps(d3j.get("plausibility_status_distribution"), sort_keys=True))
    print("no_drift_status_distribution", json.dumps(d3j.get("no_drift_status_distribution"), sort_keys=True))

    require_equal("D3J guardrail failure count", d3j.get("guardrail_failure_count"), 0)
    require_equal("D3J PASS equals total campaigns", (d3j.get("no_drift_status_distribution") or {}).get("PASS"), d3j.get("total_campaigns"))

    d3d = request_json(
        "/api/campaign/operator-control-production-mutation-gate",
        method="POST",
        body={"execute": False},
    )

    print("")
    print("D3D DRY-RUN GATE")
    for key in ["dry_run", "execution_authorized", "writes_to_supabase", "mutates_campaigns", "eligible_count", "mutations_succeeded"]:
        print(key, d3d.get(key))

    require_equal("D3D dry_run", d3d.get("dry_run"), True)
    require_equal("D3D execution_authorized", d3d.get("execution_authorized"), False)
    require_equal("D3D writes_to_supabase", d3d.get("writes_to_supabase"), False)
    require_equal("D3D mutates_campaigns", d3d.get("mutates_campaigns"), False)
    require_equal("D3D eligible_count", d3d.get("eligible_count"), 0)
    require_equal("D3D mutations_succeeded", d3d.get("mutations_succeeded"), 0)

    print("")
    print("FINAL RESULT: PASS - D3P no-drift live audit succeeded.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print("FINAL RESULT: FAIL")
        print(exc, file=sys.stderr)
        raise
