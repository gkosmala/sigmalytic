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

SRC2_URL = BASE_URL + "/api/campaign/src2-read-only-intraday-source-probe?" + urllib.parse.urlencode(
    {
        "symbols": "SPY",
        "timeframe": "1Min",
        "lookback_bars": "390",
        "minimum_usable_bars": "30",
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
                headers={"User-Agent": "Sigmalytic-SRC3-Intraday-Source-Quality-Review/1.0"},
            )

            with urllib.request.urlopen(request, timeout=75) as response:
                body = response.read().decode("utf-8", errors="replace")
                return json.loads(body)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTPError {exc.code}: {body[:1200]}"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(sleep_seconds)

    raise RuntimeError(f"Unable to fetch SRC2 endpoint after {attempts} attempts. Last error: {last_error}")


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
    src2_payload = _fetch_json(SRC2_URL)

    failures: list[dict[str, Any]] = []

    runtime_counts = src2_payload.get("runtime_counts") or {}
    runtime_decision = src2_payload.get("runtime_decision") or {}
    runtime_distributions = src2_payload.get("runtime_distributions") or {}
    results = _as_list(src2_payload.get("results"))

    _require_equal(
        failures,
        "src2_audit_status",
        src2_payload.get("audit_status"),
        "PASS_SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE_RESPONDED_NO_MUTATION",
    )
    _require_equal(failures, "src2_read_only", src2_payload.get("read_only"), True)
    _require_equal(failures, "src2_writes_to_supabase", src2_payload.get("writes_to_supabase"), False)
    _require_equal(failures, "src2_mutates_campaigns", src2_payload.get("mutates_campaigns"), False)
    _require_equal(failures, "src2_executes_d3d", src2_payload.get("executes_d3d"), False)
    _require_equal(failures, "src2_authorizes_d3d", src2_payload.get("authorizes_d3d"), False)
    _require_equal(failures, "src2_constructs_hvn_poc", src2_payload.get("constructs_hvn_poc"), False)
    _require_equal(
        failures,
        "src2_operator_control_confirmed",
        src2_payload.get("operator_control_confirmed_by_this_endpoint"),
        False,
    )
    _require_equal(failures, "src2_not_a_trade_signal", src2_payload.get("not_a_trade_signal"), True)
    _require_equal(failures, "src2_guardrail_failure_count", src2_payload.get("guardrail_failure_count"), 0)
    _require_equal(
        failures,
        "src2_d3d_execution_recommendation",
        runtime_decision.get("d3d_execution_recommendation"),
        "DO_NOT_EXECUTE_D3D",
    )
    _require_equal(
        failures,
        "src2_makes_any_campaign_d3d_eligible",
        runtime_decision.get("src2_makes_any_campaign_d3d_eligible"),
        False,
    )

    usable_intraday_count = int(runtime_counts.get("symbol_count_with_usable_intraday_bars") or 0)

    if usable_intraday_count < 1:
        failures.append(
            {
                "check": "usable_intraday_bar_count",
                "expected": ">= 1",
                "actual": usable_intraday_count,
            }
        )

    if runtime_decision.get("source_status") != "SRC2_INTRADAY_OHLCV_SOURCE_AVAILABLE":
        failures.append(
            {
                "check": "src2_source_status",
                "expected": "SRC2_INTRADAY_OHLCV_SOURCE_AVAILABLE",
                "actual": runtime_decision.get("source_status"),
            }
        )

    if str(src2_payload.get("requested_timeframe")) == "1Day":
        failures.append(
            {
                "check": "requested_timeframe",
                "expected": "intraday timeframe",
                "actual": src2_payload.get("requested_timeframe"),
            }
        )

    usable_results: list[dict[str, Any]] = []
    source_types: list[str] = []
    window_start_values: list[str] = []
    window_end_values: list[str] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        if (
            item.get("adapter_status") == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
            and int(item.get("bar_count") or 0) >= 30
        ):
            usable_results.append(item)

        if item.get("source_type"):
            source_types.append(str(item.get("source_type")))

        if item.get("window_start"):
            window_start_values.append(str(item.get("window_start")))

        if item.get("window_end"):
            window_end_values.append(str(item.get("window_end")))

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]:
            if item.get(field) is not False:
                failures.append(
                    {
                        "check": f"result_{field}",
                        "symbol": item.get("symbol"),
                        "expected": False,
                        "actual": item.get(field),
                    }
                )

    if len(usable_results) < 1:
        failures.append(
            {
                "check": "usable_intraday_result_presence",
                "expected": "at least one usable intraday result",
                "actual": len(usable_results),
            }
        )

    source_quality_findings = {
        "src2_confirmed_intraday_ohlcv_source": len(usable_results) > 0,
        "intraday_source_types": source_types,
        "window_start_values": window_start_values,
        "window_end_values": window_end_values,
        "true_exchange_volume_at_price_available": False,
        "tick_level_trade_print_source_available": False,
        "intrabar_volume_at_price_available": False,
        "intraday_ohlcv_has_price_time_volume_bars": len(usable_results) > 0,
        "intraday_ohlcv_is_better_than_daily_ohlcv_for_profile_estimation": len(usable_results) > 0,
        "intraday_ohlcv_is_true_volume_at_price": False,
        "intraday_ohlcv_sufficient_for_d3d_true_hvn_poc": False,
        "source_quality_classification": (
            "SRC3_PASS_INTRADAY_OHLCV_AVAILABLE_FOR_READ_ONLY_PROFILE_REFINEMENT_NOT_D3D"
            if len(usable_results) > 0
            else "SRC3_FAIL_INTRADAY_OHLCV_NOT_AVAILABLE"
        ),
        "source_quality_limitation": (
            "1-minute OHLCV bars improve structural resolution versus daily OHLCV, but they still aggregate volume across each bar. "
            "They are not true exchange volume-at-price, tick data, or explicit SML. They can support read-only profile refinement only."
        ),
    }

    d4d3d_decision = {
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src3_makes_any_campaign_d3d_eligible": False,
        "operator_control_confirmed_by_src3": False,
        "reason": (
            "SRC3 confirms intraday OHLCV is available, but intraday OHLCV is still not true exchange volume-at-price "
            "and not explicit SML. Therefore SRC3 can only advance to a read-only SRC4 intraday profile refinement prototype."
        ),
    }

    src3_passed = len(failures) == 0

    output = {
        "engine": "SRC3_INTRADAY_SOURCE_QUALITY_REVIEW",
        "version": "source_resolution_src3_intraday_source_quality_review_v1",
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_endpoint": SRC2_URL,
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "constructs_hvn_poc": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "not_a_trade_signal": True,
        "no_drift_doctrine": NO_DRIFT_DOCTRINE,
        "src2_runtime_counts": runtime_counts,
        "src2_runtime_distributions": runtime_distributions,
        "src3_source_quality_findings": source_quality_findings,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src3_status": (
                "PASS_SRC3_INTRADAY_SOURCE_QUALITY_REVIEW_READY_FOR_SRC4"
                if src3_passed
                else "FAIL_SRC3_INTRADAY_SOURCE_QUALITY_REVIEW"
            ),
            "next_action": (
                "PROCEED_TO_SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_PROTOTYPE"
                if src3_passed
                else "STOP_UNTIL_SRC3_FAILURES_RESOLVED"
            ),
            **d4d3d_decision,
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if src3_passed:
        print("FINAL RESULT: PASS - SRC3 intraday source-quality review passed; proceed to SRC4 read-only intraday profile refinement; D3D remains blocked.")
        return 0

    print("FINAL RESULT: FAIL - SRC3 intraday source-quality review failed; D3D remains blocked.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
