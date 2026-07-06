from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.structural_sources.explicit_sml_contract import (  # noqa: E402
    CONTRACT_NAME,
    CONTRACT_VERSION,
    validate_explicit_sml_record,
    validate_many_explicit_sml_records,
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


def _fixture_valid_manual_support() -> dict[str, Any]:
    return {
        "symbol": "SPY",
        "campaign_id": "fixture-only-not-runtime",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "fixture_explicit_manual_markup_chart_review",
        "source_timestamp_utc": "2026-07-06T22:00:00Z",
        "observed_window_start_utc": "2023-04-24T08:00:00Z",
        "observed_window_end_utc": "2023-04-24T16:06:00Z",
        "is_explicit": True,
        "is_inferred": False,
        "is_proxy": False,
        "is_hvn_absorption_proxy": False,
        "derived_from_score": False,
        "derived_from_rank": False,
        "derived_from_probability": False,
        "derived_from_edge": False,
        "derived_from_expected_return": False,
        "derived_from_target_projection": False,
        "derived_from_trade_signal": False,
        "derived_from_gamma_options_overlay": False,
        "derived_from_ohlcv_profile_approximation": False,
        "confirms_operator_control": False,
        "authorizes_d3d": False,
        "mutates_campaigns": False,
        "writes_to_supabase": False,
        "eligible_for_immediate_d3d_mutation": False,
    }


def _invalid_fixtures() -> list[dict[str, Any]]:
    base = _fixture_valid_manual_support()

    inferred = dict(base)
    inferred["source_method"] = "INFERRED_SML"
    inferred["is_inferred"] = True

    proxy = dict(base)
    proxy["source_method"] = "HVN_ABSORPTION_PROXY"
    proxy["is_proxy"] = True
    proxy["is_hvn_absorption_proxy"] = True

    score_derived = dict(base)
    score_derived["source_method"] = "SCORE_DERIVED"
    score_derived["derived_from_score"] = True

    trade_signal = dict(base)
    trade_signal["source_reference"] = "trade signal generated level"
    trade_signal["derived_from_trade_signal"] = True

    bad_price = dict(base)
    bad_price["price_low"] = 412.00
    bad_price["price_mid"] = 411.00
    bad_price["price_high"] = 410.00

    not_explicit = dict(base)
    not_explicit["is_explicit"] = False

    unauthorized = dict(base)
    unauthorized["authorizes_d3d"] = True
    unauthorized["eligible_for_immediate_d3d_mutation"] = True

    ohlcv_approximation = dict(base)
    ohlcv_approximation["source_method"] = "OHLCV_DERIVED_PROFILE_APPROXIMATION"
    ohlcv_approximation["derived_from_ohlcv_profile_approximation"] = True

    return [
        inferred,
        proxy,
        score_derived,
        trade_signal,
        bad_price,
        not_explicit,
        unauthorized,
        ohlcv_approximation,
    ]


def main() -> int:
    failures: list[dict[str, Any]] = []

    valid_fixture = _fixture_valid_manual_support()
    valid_result = validate_explicit_sml_record(valid_fixture)

    if valid_result.get("record_valid") is not True:
        failures.append(
            {
                "check": "valid_explicit_fixture_should_pass",
                "expected": True,
                "actual": valid_result.get("record_valid"),
                "details": valid_result.get("failures"),
            }
        )

    if valid_result.get("production_mutation_authorized") is not False:
        failures.append(
            {
                "check": "valid_fixture_must_not_authorize_mutation",
                "expected": False,
                "actual": valid_result.get("production_mutation_authorized"),
            }
        )

    invalid_records = _invalid_fixtures()
    invalid_results = validate_many_explicit_sml_records(invalid_records)

    rejected_count = 0

    for index, result in enumerate(invalid_results.get("results") or []):
        if result.get("record_valid") is False:
            rejected_count += 1
        else:
            failures.append(
                {
                    "check": "invalid_fixture_should_be_rejected",
                    "fixture_index": index,
                    "expected": False,
                    "actual": result.get("record_valid"),
                }
            )

        if result.get("production_mutation_authorized") is not False:
            failures.append(
                {
                    "check": "invalid_fixture_must_not_authorize_mutation",
                    "fixture_index": index,
                    "expected": False,
                    "actual": result.get("production_mutation_authorized"),
                }
            )

    if rejected_count != len(invalid_records):
        failures.append(
            {
                "check": "all_invalid_fixtures_rejected",
                "expected": len(invalid_records),
                "actual": rejected_count,
            }
        )

    contract_status = (
        "PASS_SRC7A_EXPLICIT_SML_CONTRACT_AUDIT"
        if len(failures) == 0
        else "FAIL_SRC7A_EXPLICIT_SML_CONTRACT_AUDIT"
    )

    output = {
        "engine": "SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT_AUDIT",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "audit_timestamp_utc": datetime.now(timezone.utc).isoformat(),
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
        "valid_fixture_result": valid_result,
        "invalid_fixture_summary": {
            "invalid_fixture_count": len(invalid_records),
            "invalid_fixture_rejected_count": rejected_count,
        },
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src7a_status": contract_status,
            "next_action": (
                "PROCEED_TO_SRC7B_RUNTIME_EXPLICIT_SML_SOURCE_ADAPTER_DESIGN"
                if len(failures) == 0
                else "STOP_UNTIL_SRC7A_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7a_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC7A defines and audits the explicit SML/structural-location evidence contract. "
                "A passing contract does not itself provide runtime evidence and does not authorize D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC7A explicit SML contract audit failed; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC7A explicit SML contract created and audited; D3D remains blocked; proceed to SRC7B runtime source adapter design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
