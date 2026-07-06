from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")
D4F_PATH = "/api/campaign/d4f-read-only-hvn-poc-construction-prototype"

QUERY = {
    "symbols": "SPY",
    "lookback_bars": "60",
    "minimum_usable_bars": "5",
    "profile_bins": "48",
}

D4F_URL = BASE_URL + D4F_PATH + "?" + urllib.parse.urlencode(QUERY)


def _fetch_json(url: str, attempts: int = 8, sleep_seconds: int = 15) -> dict[str, Any]:
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Sigmalytic-D4G-Source-Quality-Review/1.0"},
            )

            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors="replace")
                return json.loads(body)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTPError {exc.code}: {body[:1000]}"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Unable to fetch D4F endpoint after {attempts} attempts. Last error: {last_error}")


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


def _require_equal(failures: list[dict[str, Any]], label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        failures.append(
            {
                "check": label,
                "expected": expected,
                "actual": actual,
            }
        )


def main() -> int:
    d4f_payload = _fetch_json(D4F_URL)
    failures: list[dict[str, Any]] = []

    runtime_decision = d4f_payload.get("runtime_decision") or {}
    runtime_counts = d4f_payload.get("runtime_counts") or {}
    results = _as_list(d4f_payload.get("results"))

    _require_equal(
        failures,
        "d4f_audit_status",
        d4f_payload.get("audit_status"),
        "PASS_D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_RESPONDED_NO_MUTATION",
    )
    _require_equal(failures, "d4f_read_only", d4f_payload.get("read_only"), True)
    _require_equal(failures, "d4f_writes_to_supabase", d4f_payload.get("writes_to_supabase"), False)
    _require_equal(failures, "d4f_mutates_campaigns", d4f_payload.get("mutates_campaigns"), False)
    _require_equal(failures, "d4f_executes_d3d", d4f_payload.get("executes_d3d"), False)
    _require_equal(failures, "d4f_authorizes_d3d", d4f_payload.get("authorizes_d3d"), False)
    _require_equal(
        failures,
        "d4f_operator_control_confirmed",
        d4f_payload.get("operator_control_confirmed_by_this_endpoint"),
        False,
    )
    _require_equal(failures, "d4f_not_a_trade_signal", d4f_payload.get("not_a_trade_signal"), True)
    _require_equal(failures, "d4f_guardrail_failure_count", d4f_payload.get("guardrail_failure_count"), 0)
    _require_equal(
        failures,
        "d4f_d3d_execution_recommendation",
        runtime_decision.get("d3d_execution_recommendation"),
        "DO_NOT_EXECUTE_D3D",
    )
    _require_equal(
        failures,
        "d4f_makes_any_campaign_d3d_eligible",
        runtime_decision.get("d4f_makes_any_campaign_d3d_eligible"),
        False,
    )

    constructed_count = int(runtime_counts.get("symbol_count_with_constructed_hvn_poc_prototype") or 0)

    if constructed_count < 1:
        failures.append(
            {
                "check": "constructed_hvn_poc_prototype_count",
                "expected": ">= 1",
                "actual": constructed_count,
            }
        )

    constructed_results: list[dict[str, Any]] = []
    prototype_only_results: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        construction = item.get("construction") or {}

        if construction.get("d4f_construction_status") == "D4F_OK_HVN_POC_CONSTRUCTED_READ_ONLY":
            constructed_results.append(item)

        if (
            construction.get("hvn_poc_construction_classification")
            == "OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE"
        ):
            prototype_only_results.append(item)

        if construction.get("d3d_eligibility_from_this_endpoint") is not False:
            failures.append(
                {
                    "check": "construction_d3d_eligibility_from_this_endpoint",
                    "symbol": item.get("symbol"),
                    "expected": False,
                    "actual": construction.get("d3d_eligibility_from_this_endpoint"),
                }
            )

    if len(constructed_results) < 1:
        failures.append(
            {
                "check": "constructed_result_presence",
                "expected": "at least one constructed result",
                "actual": len(constructed_results),
            }
        )

    if len(prototype_only_results) != len(constructed_results):
        failures.append(
            {
                "check": "all_constructed_results_are_prototype_only",
                "expected": len(constructed_results),
                "actual": len(prototype_only_results),
            }
        )

    d4g_passed = len(failures) == 0

    output = {
        "engine": "D4G_SOURCE_QUALITY_REVIEW",
        "version": "phase_d4g_source_quality_review_v1",
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_endpoint": D4F_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "d4f_runtime_counts": runtime_counts,
        "d4g_source_quality_findings": {
            "constructed_hvn_poc_prototype_count": len(constructed_results),
            "prototype_only_result_count": len(prototype_only_results),
            "true_exchange_volume_at_price_available": False,
            "tick_or_intrabar_volume_at_price_available": False,
            "d4f_constructed_true_hvn_poc": False,
            "d4f_constructed_ohlcv_derived_hvn_poc_prototype": len(constructed_results) > 0,
            "source_quality_classification": "PROTOTYPE_ONLY_DAILY_OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE",
            "source_quality_limitation": "Daily OHLCV bars do not contain true intrabar volume-at-price. D4F output is acceptable for D4H doctrine review only, not for D3D eligibility.",
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "d4g_status": (
                "PASS_D4G_SOURCE_QUALITY_REVIEW_PROTOTYPE_ONLY_READY_FOR_D4H"
                if d4g_passed
                else "FAIL_D4G_SOURCE_QUALITY_REVIEW"
            ),
            "d4h_readiness": (
                "READY_FOR_D4H_DOCTRINE_COMPLIANCE_REVIEW"
                if d4g_passed
                else "BLOCKED_UNTIL_D4G_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4g_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "D4G accepts D4F output only as an OHLCV-derived read-only prototype for D4H review. "
                "D4G does not treat the prototype as true exchange HVN/POC and does not authorize D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if d4g_passed:
        print("FINAL RESULT: PASS - D4G source-quality review passed; D4H is next; D3D remains blocked.")
        return 0

    print("FINAL RESULT: FAIL - D4G source-quality review failed; D4H remains blocked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
