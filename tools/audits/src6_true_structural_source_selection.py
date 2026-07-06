from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
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

D3V_URL = BASE_URL + "/api/campaign/d3d-dry-run-candidate-preflight-review"

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
                headers={"User-Agent": "Sigmalytic-SRC6-True-Structural-Source-Selection/1.0"},
            )

            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read().decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "url": url,
                    "payload": json.loads(body),
                    "error": None,
                }

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTPError {exc.code}: {body[:1200]}"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(sleep_seconds)

    return {
        "ok": False,
        "url": url,
        "payload": None,
        "error": last_error,
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [value]

    return []


def _compact_src4(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "SRC4 payload unavailable.",
        }

    runtime_counts = payload.get("runtime_counts") or {}
    runtime_decision = payload.get("runtime_decision") or {}
    results = _as_list(payload.get("results"))

    profile_statuses: list[str] = []
    profile_classifications: list[str] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        profile = item.get("profile") or {}

        if profile.get("src4_profile_status"):
            profile_statuses.append(str(profile.get("src4_profile_status")))

        if profile.get("profile_classification"):
            profile_classifications.append(str(profile.get("profile_classification")))

    return {
        "available": True,
        "audit_status": payload.get("audit_status"),
        "read_only": payload.get("read_only"),
        "writes_to_supabase": payload.get("writes_to_supabase"),
        "mutates_campaigns": payload.get("mutates_campaigns"),
        "executes_d3d": payload.get("executes_d3d"),
        "authorizes_d3d": payload.get("authorizes_d3d"),
        "constructs_true_hvn_poc": payload.get("constructs_true_hvn_poc"),
        "operator_control_confirmed_by_this_endpoint": payload.get("operator_control_confirmed_by_this_endpoint"),
        "guardrail_failure_count": payload.get("guardrail_failure_count"),
        "symbol_count_with_intraday_profile_refinement": runtime_counts.get("symbol_count_with_intraday_profile_refinement"),
        "profile_status": runtime_decision.get("profile_status"),
        "d3d_execution_recommendation": runtime_decision.get("d3d_execution_recommendation"),
        "src4_makes_any_campaign_d3d_eligible": runtime_decision.get("src4_makes_any_campaign_d3d_eligible"),
        "profile_statuses": profile_statuses,
        "profile_classifications": profile_classifications,
    }


def _compact_d3v(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "D3V payload unavailable.",
        }

    compact = {
        "available": True,
        "dry_run": payload.get("dry_run"),
        "execution_authorized": payload.get("execution_authorized"),
        "writes_to_supabase": payload.get("writes_to_supabase"),
        "mutates_campaigns": payload.get("mutates_campaigns"),
        "eligible_count": payload.get("eligible_count"),
        "mutations_succeeded": payload.get("mutations_succeeded"),
    }

    for key in [
        "audit_status",
        "candidate_count",
        "eligible_candidate_count",
        "d3d_eligible_count",
        "d3d_execution_recommendation",
    ]:
        if key in payload:
            compact[key] = payload.get(key)

    return compact


def _path_score(path: dict[str, Any]) -> dict[str, Any]:
    blockers = list(path.get("blockers") or [])
    strengths = list(path.get("strengths") or [])

    return {
        **path,
        "blocker_count": len(blockers),
        "strength_count": len(strengths),
        "selection_rank_score": len(strengths) - (len(blockers) * 3),
    }


def main() -> int:
    src4_fetch = _fetch_json(SRC4_URL)
    d3v_fetch = _fetch_json(D3V_URL)

    src4_payload = src4_fetch.get("payload") if src4_fetch.get("ok") else None
    d3v_payload = d3v_fetch.get("payload") if d3v_fetch.get("ok") else None

    src4_compact = _compact_src4(src4_payload)
    d3v_compact = _compact_d3v(d3v_payload)

    failures: list[dict[str, Any]] = []

    if not src4_fetch.get("ok"):
        failures.append(
            {
                "check": "src4_endpoint_available",
                "expected": True,
                "actual": False,
                "error": src4_fetch.get("error"),
            }
        )

    if src4_compact.get("writes_to_supabase") not in [False, None]:
        failures.append(
            {
                "check": "src4_writes_to_supabase",
                "expected": False,
                "actual": src4_compact.get("writes_to_supabase"),
            }
        )

    if src4_compact.get("mutates_campaigns") not in [False, None]:
        failures.append(
            {
                "check": "src4_mutates_campaigns",
                "expected": False,
                "actual": src4_compact.get("mutates_campaigns"),
            }
        )

    if src4_compact.get("authorizes_d3d") not in [False, None]:
        failures.append(
            {
                "check": "src4_authorizes_d3d",
                "expected": False,
                "actual": src4_compact.get("authorizes_d3d"),
            }
        )

    if d3v_fetch.get("ok"):
        if d3v_compact.get("execution_authorized") is not False:
            failures.append(
                {
                    "check": "d3v_execution_authorized",
                    "expected": False,
                    "actual": d3v_compact.get("execution_authorized"),
                }
            )

        if d3v_compact.get("writes_to_supabase") is not False:
            failures.append(
                {
                    "check": "d3v_writes_to_supabase",
                    "expected": False,
                    "actual": d3v_compact.get("writes_to_supabase"),
                }
            )

        if d3v_compact.get("mutates_campaigns") is not False:
            failures.append(
                {
                    "check": "d3v_mutates_campaigns",
                    "expected": False,
                    "actual": d3v_compact.get("mutates_campaigns"),
                }
            )

    candidate_paths = [
        _path_score(
            {
                "path_id": "SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT",
                "selection_status": "SELECTED_PRIMARY_NEXT_PATH",
                "description": "Define the explicit SML/structural-location evidence contract before any production mutation can be considered.",
                "strengths": [
                    "Directly satisfies the doctrine requirement that explicit SML/structural location is required for future D3D eligibility.",
                    "Avoids pretending OHLCV-derived profile approximations are true HVN/POC.",
                    "Can be implemented as a strict read-only contract and preflight validator before any mutation path is reopened.",
                    "Allows manual, provider-supplied, or audited structural levels to be accepted only when explicitly sourced.",
                ],
                "blockers": [],
                "required_next_phase": "SRC7A",
                "d3d_allowed_after_this_path": False,
                "reason_d3d_still_blocked": "A contract alone is not evidence. D3D remains blocked until explicit structural records exist and pass D3U/D3V/D3Z-equivalent preflight.",
            }
        ),
        _path_score(
            {
                "path_id": "SRC7B_TRUE_VOLUME_AT_PRICE_PROVIDER_SELECTION",
                "selection_status": "SECONDARY_PARALLEL_RESEARCH_PATH",
                "description": "Select or integrate a true exchange volume-at-price or tick-derived volume profile source.",
                "strengths": [
                    "Would provide the cleanest future path to true HVN/POC if a reliable provider is available.",
                    "Could support true volume-at-price rather than OHLCV range-distribution approximations.",
                ],
                "blockers": [
                    "No confirmed runtime provider exists yet.",
                    "Provider availability, cost, entitlement, and symbol coverage are unknown.",
                    "Implementation cannot proceed without credentials and provider contract details.",
                ],
                "required_next_phase": "SRC7B",
                "d3d_allowed_after_this_path": False,
                "reason_d3d_still_blocked": "Provider selection is not data evidence. D3D remains blocked until true provider data is live, read-only audited, and doctrine-reviewed.",
            }
        ),
        _path_score(
            {
                "path_id": "SRC7C_TICK_DERIVED_PROFILE_RESEARCH",
                "selection_status": "SECONDARY_TECHNICAL_RESEARCH_PATH",
                "description": "Determine whether available trade prints can be transformed into true tick-derived volume-at-price profiles.",
                "strengths": [
                    "Trade prints with price and size can theoretically construct true volume-at-price.",
                    "Could avoid manual structural marking if live tick source exists.",
                ],
                "blockers": [
                    "No confirmed tick trade-print endpoint exists in the current read-only adapter.",
                    "Historical tick entitlements may be limited.",
                    "Aggregation, latency, and pagination controls would need separate no-drift review.",
                ],
                "required_next_phase": "SRC7C",
                "d3d_allowed_after_this_path": False,
                "reason_d3d_still_blocked": "Tick-derived profile remains unavailable until a live source is confirmed and audited.",
            }
        ),
        _path_score(
            {
                "path_id": "SRC7D_INTRADAY_OHLCV_RESEARCH_CONTINUATION",
                "selection_status": "RESEARCH_ONLY_NOT_D3D_PATH",
                "description": "Continue using SRC4 intraday OHLCV profile refinement for visual diagnostics and hypothesis testing only.",
                "strengths": [
                    "Already works in production read-only mode.",
                    "Provides better granularity than daily OHLCV.",
                    "Useful for future research visualization and diagnostics.",
                ],
                "blockers": [
                    "Not true exchange volume-at-price.",
                    "Not tick-level data.",
                    "Not explicit SML.",
                    "Cannot authorize D3D.",
                ],
                "required_next_phase": "RESEARCH_ONLY",
                "d3d_allowed_after_this_path": False,
                "reason_d3d_still_blocked": "SRC4 remains approximation-only and cannot become a production mutation source.",
            }
        ),
    ]

    selected_primary = "SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT"

    source_selection = {
        "selected_primary_path": selected_primary,
        "selected_next_phase": "SRC7A",
        "selection_reason": (
            "SRC7A is the correct next path because the no-drift doctrine requires explicit SML or structural-location evidence "
            "for future D3D eligibility. SRC4 intraday profiles remain useful but approximate. True volume-at-price provider work "
            "can continue in parallel, but cannot be assumed available."
        ),
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "src6_makes_any_campaign_d3d_eligible": False,
        "d3d_reopen_conditions": [
            "A strict explicit structural-location evidence contract exists.",
            "Evidence records are explicit, sourced, timestamped, symbol-bound, and non-inferred.",
            "Proxy labels such as HVN_ABSORPTION_PROXY are rejected for D3D eligibility.",
            "A future dry-run preflight proves eligible candidates without mutation.",
            "D3P no-drift remains PASS.",
            "D3D remains the only production mutation gate.",
        ],
    }

    output = {
        "engine": "SRC6_TRUE_STRUCTURAL_SOURCE_SELECTION",
        "version": "source_resolution_src6_true_structural_source_selection_v1",
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
        "live_evidence_inputs": {
            "src4_fetch": {
                "ok": src4_fetch.get("ok"),
                "url": SRC4_URL,
                "error": src4_fetch.get("error"),
                "compact": src4_compact,
            },
            "d3v_fetch": {
                "ok": d3v_fetch.get("ok"),
                "url": D3V_URL,
                "error": d3v_fetch.get("error"),
                "compact": d3v_compact,
            },
        },
        "candidate_source_paths": candidate_paths,
        "source_selection": source_selection,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src6_status": (
                "PASS_SRC6_TRUE_STRUCTURAL_SOURCE_SELECTION_COMPLETED"
                if len(failures) == 0
                else "FAIL_SRC6_TRUE_STRUCTURAL_SOURCE_SELECTION"
            ),
            "selected_next_phase": "SRC7A",
            "next_action": (
                "PROCEED_TO_SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT"
                if len(failures) == 0
                else "STOP_UNTIL_SRC6_FAILURES_RESOLVED"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src6_makes_any_campaign_d3d_eligible": False,
            "reason": (
                "SRC6 selects SRC7A as the primary next path because future D3D eligibility requires explicit SML/structural-location evidence. "
                "Intraday OHLCV profile refinement remains research-only, and true volume-at-price provider integration remains a separate unresolved source path."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC6 source selection found guardrail failures; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC6 selected SRC7A explicit SML/structural-location contract as the primary next path; D3D remains blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
