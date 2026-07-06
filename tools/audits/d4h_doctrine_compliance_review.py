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


NO_DRIFT_DOCTRINE = [
    "Operator control is evidence, not a score.",
    "Operator control SHALL NOT be derived from composite score, campaign score, survival score, rank, tier, gamma/options overlay, probability, edge, expected return, historical outcomes, target projections, future returns, or trade signals.",
    "D3D is the only production mutation gate.",
    "D3A = candidate only.",
    "D3C = shadow/read-only.",
    "D3D = production mutation only.",
    "D3C.2 layers are read-only diagnostic/enrichment and cannot confirm operator control.",
    "HVN_ABSORPTION_PROXY is not true HVN/POC.",
    "Explicit SML/structural location is required for future D3D eligibility.",
    "Inferred SML must be rejected by D3U/D3V/D3Z for D3D preflight eligibility.",
    "Read-only endpoints must never mutate, score, rank, transition, confirm/unconfirm operator control, or produce trade signals.",
]


def _fetch_json(url: str, attempts: int = 8, sleep_seconds: int = 15) -> dict[str, Any]:
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Sigmalytic-D4H-Doctrine-Compliance-Review/1.0"},
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
    _require_equal(
        failures,
        "d4f_operator_control_unconfirmed",
        d4f_payload.get("operator_control_unconfirmed_by_this_endpoint"),
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
                "check": "d4f_constructed_hvn_poc_prototype_count",
                "expected": ">= 1",
                "actual": constructed_count,
            }
        )

    constructed_results: list[dict[str, Any]] = []
    prototype_only_results: list[dict[str, Any]] = []
    d3d_ineligible_results: list[dict[str, Any]] = []

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

        if construction.get("d3d_eligibility_from_this_endpoint") is False:
            d3d_ineligible_results.append(item)

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
                "expected": "at least one D4F constructed prototype",
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

    if len(d3d_ineligible_results) != len(results):
        failures.append(
            {
                "check": "all_results_are_d3d_ineligible",
                "expected": len(results),
                "actual": len(d3d_ineligible_results),
            }
        )

    doctrine_findings = {
        "operator_control_evidence_status": "NOT_CONFIRMED_BY_D4F_OR_D4H",
        "operator_control_score_derivation_status": "NOT_USED",
        "structural_location_status": "PROTOTYPE_ONLY_NOT_EXPLICIT_TRUE_HVN_POC",
        "true_hvn_poc_status": "NOT_AVAILABLE_FROM_DAILY_OHLCV",
        "explicit_sml_status": "NOT_ESTABLISHED_FOR_D3D_BY_D4F",
        "hvn_absorption_proxy_status": "NOT_TREATED_AS_TRUE_HVN_POC",
        "d3d_mutation_gate_status": "NOT_AUTHORIZED",
        "trade_signal_status": "NOT_PRODUCED",
        "read_only_status": "PRESERVED",
        "final_gate_decision": "STOP_BEFORE_D3D",
    }

    d4h_passed = len(failures) == 0

    output = {
        "engine": "D4H_DOCTRINE_COMPLIANCE_REVIEW",
        "version": "phase_d4h_doctrine_compliance_review_v1",
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_endpoint": D4F_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "d4f_runtime_counts": runtime_counts,
        "d4h_doctrine_findings": doctrine_findings,
        "d4h_source_conclusion": {
            "d4f_constructed_read_only_profile": len(constructed_results) > 0,
            "d4f_profile_is_ohlcv_derived_prototype_only": len(prototype_only_results) == len(constructed_results),
            "true_exchange_volume_at_price_available": False,
            "tick_or_intrabar_volume_at_price_available": False,
            "daily_ohlcv_sufficient_for_d3d_true_hvn_poc": False,
            "d4h_can_authorize_d3d": False,
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "d4h_status": (
                "PASS_D4H_DOCTRINE_COMPLIANCE_REVIEW_STOP_BEFORE_D3D"
                if d4h_passed
                else "FAIL_D4H_DOCTRINE_COMPLIANCE_REVIEW"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4h_makes_any_campaign_d3d_eligible": False,
            "next_action": (
                "STOP_BEFORE_D3D_UNLESS_TRUE_EXPLICIT_HVN_POC_OR_EXPLICIT_SML_SOURCE_IS_ADDED"
                if d4h_passed
                else "BLOCKED_UNTIL_D4H_FAILURES_RESOLVED"
            ),
            "reason": (
                "D4H confirms D4F is read-only and doctrine-compliant, but the constructed geometry is "
                "OHLCV-derived prototype-only rather than true exchange volume-at-price or explicit SML. "
                "Therefore D3D remains blocked and the correct final decision is STOP before D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if d4h_passed:
        print("FINAL RESULT: PASS - D4H doctrine-compliance review completed; D3D remains blocked; STOP before D3D.")
        return 0

    print("FINAL RESULT: FAIL - D4H doctrine-compliance review failed; D3D remains blocked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
