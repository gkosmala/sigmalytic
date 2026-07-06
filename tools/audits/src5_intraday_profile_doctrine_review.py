from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

SRC4_URL = BASE_URL + "/api/campaign/src4-read-only-intraday-profile-refinement-prototype?" + urllib.parse.urlencode(
    {
        "symbols": "SPY",
        "timeframe": "1Min",
        "lookback_bars": "390",
        "minimum_usable_bars": "30",
        "profile_bins": "96",
    }
)

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
                headers={"User-Agent": "Sigmalytic-SRC5-Intraday-Profile-Doctrine-Review/1.0"},
            )

            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read().decode("utf-8", errors="replace")
                return json.loads(body)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTPError {exc.code}: {body[:1200]}"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Unable to fetch SRC4 endpoint after {attempts} attempts. Last error: {last_error}")


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
    src4_payload = _fetch_json(SRC4_URL)

    failures: list[dict[str, Any]] = []

    runtime_counts = src4_payload.get("runtime_counts") or {}
    runtime_decision = src4_payload.get("runtime_decision") or {}
    runtime_distributions = src4_payload.get("runtime_distributions") or {}
    results = _as_list(src4_payload.get("results"))

    _require_equal(
        failures,
        "src4_audit_status",
        src4_payload.get("audit_status"),
        "PASS_SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_RESPONDED_NO_MUTATION",
    )
    _require_equal(failures, "src4_read_only", src4_payload.get("read_only"), True)
    _require_equal(failures, "src4_writes_to_supabase", src4_payload.get("writes_to_supabase"), False)
    _require_equal(failures, "src4_mutates_campaigns", src4_payload.get("mutates_campaigns"), False)
    _require_equal(failures, "src4_executes_d3d", src4_payload.get("executes_d3d"), False)
    _require_equal(failures, "src4_authorizes_d3d", src4_payload.get("authorizes_d3d"), False)
    _require_equal(failures, "src4_constructs_true_hvn_poc", src4_payload.get("constructs_true_hvn_poc"), False)
    _require_equal(
        failures,
        "src4_operator_control_confirmed",
        src4_payload.get("operator_control_confirmed_by_this_endpoint"),
        False,
    )
    _require_equal(
        failures,
        "src4_operator_control_unconfirmed",
        src4_payload.get("operator_control_unconfirmed_by_this_endpoint"),
        False,
    )
    _require_equal(failures, "src4_not_a_trade_signal", src4_payload.get("not_a_trade_signal"), True)
    _require_equal(failures, "src4_guardrail_failure_count", src4_payload.get("guardrail_failure_count"), 0)
    _require_equal(
        failures,
        "src4_d3d_execution_recommendation",
        runtime_decision.get("d3d_execution_recommendation"),
        "DO_NOT_EXECUTE_D3D",
    )
    _require_equal(
        failures,
        "src4_makes_any_campaign_d3d_eligible",
        runtime_decision.get("src4_makes_any_campaign_d3d_eligible"),
        False,
    )

    constructed_count = int(runtime_counts.get("symbol_count_with_intraday_profile_refinement") or 0)

    if constructed_count < 1:
        failures.append(
            {
                "check": "src4_intraday_profile_refinement_count",
                "expected": ">= 1",
                "actual": constructed_count,
            }
        )

    profile_results: list[dict[str, Any]] = []
    approximation_results: list[dict[str, Any]] = []
    d3d_ineligible_results: list[dict[str, Any]] = []
    true_hvn_claims: list[dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        profile = item.get("profile") or {}

        if profile.get("src4_profile_status") == "SRC4_OK_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY":
            profile_results.append(item)

        if profile.get("profile_classification") == "INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE":
            approximation_results.append(item)

        if profile.get("d3d_eligibility_from_this_endpoint") is False:
            d3d_ineligible_results.append(item)

        if profile.get("constructs_true_hvn_poc") is not False:
            true_hvn_claims.append(item)

        if profile.get("d3d_eligibility_from_this_endpoint") is not False:
            failures.append(
                {
                    "check": "profile_d3d_eligibility_from_this_endpoint",
                    "symbol": item.get("symbol"),
                    "expected": False,
                    "actual": profile.get("d3d_eligibility_from_this_endpoint"),
                }
            )

        if profile.get("constructs_true_hvn_poc") is not False:
            failures.append(
                {
                    "check": "profile_constructs_true_hvn_poc",
                    "symbol": item.get("symbol"),
                    "expected": False,
                    "actual": profile.get("constructs_true_hvn_poc"),
                }
            )

    if len(profile_results) < 1:
        failures.append(
            {
                "check": "src4_profile_result_presence",
                "expected": "at least one SRC4 read-only profile result",
                "actual": len(profile_results),
            }
        )

    if len(approximation_results) != len(profile_results):
        failures.append(
            {
                "check": "all_src4_profiles_are_approximation_only",
                "expected": len(profile_results),
                "actual": len(approximation_results),
            }
        )

    if len(d3d_ineligible_results) != len(results):
        failures.append(
            {
                "check": "all_src4_results_are_d3d_ineligible",
                "expected": len(results),
                "actual": len(d3d_ineligible_results),
            }
        )

    doctrine_findings = {
        "intraday_profile_refinement_constructed": len(profile_results) > 0,
        "intraday_profile_classification": "INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
        "source_resolution_improvement": "SRC4 improves profile granularity from daily OHLCV to 1-minute OHLCV.",
        "true_exchange_volume_at_price_available": False,
        "tick_level_trade_print_source_available": False,
        "explicit_sml_or_structural_location_available": False,
        "constructs_true_hvn_poc": False,
        "operator_control_confirmed": False,
        "d3d_eligible": False,
        "final_doctrine_decision": "STOP_BEFORE_D3D_AND_PROCEED_TO_TRUE_SOURCE_SELECTION",
    }

    source_quality_conclusion = {
        "src4_is_useful_for_read_only_research": len(profile_results) > 0,
        "src4_can_support_future_visual_diagnostics": len(profile_results) > 0,
        "src4_can_support_future_hypothesis_testing": len(profile_results) > 0,
        "src4_can_replace_true_hvn_poc_for_d3d": False,
        "src4_can_replace_explicit_sml_for_d3d": False,
        "src4_can_authorize_d3d": False,
        "required_next_source": [
            "true exchange volume-at-price",
            "tick-derived volume profile",
            "explicit SML or structural-location source",
        ],
    }

    src5_passed = len(failures) == 0

    output = {
        "engine": "SRC5_INTRADAY_PROFILE_DOCTRINE_REVIEW",
        "version": "source_resolution_src5_intraday_profile_doctrine_review_v1",
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_endpoint": SRC4_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "constructs_true_hvn_poc": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "src4_runtime_counts": runtime_counts,
        "src4_runtime_distributions": runtime_distributions,
        "src5_doctrine_findings": doctrine_findings,
        "src5_source_quality_conclusion": source_quality_conclusion,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src5_status": (
                "PASS_SRC5_INTRADAY_PROFILE_DOCTRINE_REVIEW_STOP_BEFORE_D3D"
                if src5_passed
                else "FAIL_SRC5_INTRADAY_PROFILE_DOCTRINE_REVIEW"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src5_makes_any_campaign_d3d_eligible": False,
            "next_action": (
                "PROCEED_TO_SRC6_TRUE_STRUCTURAL_SOURCE_SELECTION"
                if src5_passed
                else "STOP_UNTIL_SRC5_FAILURES_RESOLVED"
            ),
            "reason": (
                "SRC5 accepts SRC4 as a useful read-only intraday OHLCV profile refinement, but confirms it is still not true "
                "volume-at-price, not tick data, not explicit SML, and not sufficient for D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if src5_passed:
        print("FINAL RESULT: PASS - SRC5 doctrine review completed; SRC4 remains read-only research only; D3D remains blocked; proceed to SRC6 true structural source selection.")
        return 0

    print("FINAL RESULT: FAIL - SRC5 doctrine review failed; D3D remains blocked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
