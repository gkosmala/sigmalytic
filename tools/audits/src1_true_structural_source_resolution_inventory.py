from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

D4E_URL = BASE_URL + "/api/campaign/d4e-read-only-live-bar-source-probe?" + urllib.parse.urlencode(
    {
        "symbols": "SPY",
        "lookback_bars": "60",
        "minimum_usable_bars": "5",
    }
)

D4F_URL = BASE_URL + "/api/campaign/d4f-read-only-hvn-poc-construction-prototype?" + urllib.parse.urlencode(
    {
        "symbols": "SPY",
        "lookback_bars": "60",
        "minimum_usable_bars": "5",
        "profile_bins": "48",
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

SOURCE_PATTERNS = {
    "explicit_sml_or_structural_location": re.compile(
        r"\b(explicit[_\- ]?sml|sml[_\- ]?source|structural[_\- ]?location|support[_\- ]?resistance[_\- ]?level|market[_\- ]?structure[_\- ]?level)\b",
        re.IGNORECASE,
    ),
    "true_hvn_poc_or_volume_at_price": re.compile(
        r"\b(true[_\- ]?hvn|true[_\- ]?poc|volume[_\- ]?at[_\- ]?price|vap|market[_\- ]?profile|volume[_\- ]?profile)\b",
        re.IGNORECASE,
    ),
    "tick_or_intraday_source": re.compile(
        r"\b(tick|1min|1_min|minute|intraday|timeframe|barset|trades|quotes)\b",
        re.IGNORECASE,
    ),
    "proxy_or_inferred_source": re.compile(
        r"\b(proxy|inferred|derived|approximation|estimated|synthetic)\b",
        re.IGNORECASE,
    ),
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
}

SCAN_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}


def _fetch_json(url: str, attempts: int = 6, sleep_seconds: int = 10) -> dict[str, Any]:
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Sigmalytic-SRC1-True-Structural-Source-Inventory/1.0"},
            )

            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "http_status": response.status,
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
        "http_status": None,
        "url": url,
        "payload": None,
        "error": last_error,
    }


def _scan_repository() -> dict[str, Any]:
    findings: dict[str, Any] = {}

    for pattern_name in SOURCE_PATTERNS:
        findings[pattern_name] = {
            "match_count": 0,
            "files": [],
        }

    scanned_file_count = 0

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue

        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue

        scanned_file_count += 1

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        relative_path = str(path.relative_to(ROOT)).replace("\\", "/")

        for pattern_name, pattern in SOURCE_PATTERNS.items():
            matches = pattern.findall(text)

            if not matches:
                continue

            bucket = findings[pattern_name]
            bucket["match_count"] += len(matches)

            if len(bucket["files"]) < 25:
                bucket["files"].append(relative_path)

    return {
        "scanned_file_count": scanned_file_count,
        "pattern_findings": findings,
    }


def _compact_d4e(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "D4E payload unavailable.",
        }

    runtime_counts = payload.get("runtime_counts") or {}
    runtime_decision = payload.get("runtime_decision") or {}

    return {
        "available": True,
        "audit_status": payload.get("audit_status"),
        "source_status": runtime_decision.get("source_status"),
        "d4f_readiness": runtime_decision.get("d4f_readiness"),
        "symbol_count_with_usable_bars": runtime_counts.get("symbol_count_with_usable_bars"),
        "guardrail_failure_count": payload.get("guardrail_failure_count"),
        "writes_to_supabase": payload.get("writes_to_supabase"),
        "mutates_campaigns": payload.get("mutates_campaigns"),
        "executes_d3d": payload.get("executes_d3d"),
        "authorizes_d3d": payload.get("authorizes_d3d"),
        "constructs_hvn_poc": payload.get("constructs_hvn_poc"),
        "d3d_execution_recommendation": runtime_decision.get("d3d_execution_recommendation"),
    }


def _compact_d4f(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "D4F payload unavailable.",
        }

    runtime_counts = payload.get("runtime_counts") or {}
    runtime_decision = payload.get("runtime_decision") or {}
    results = payload.get("results")

    if isinstance(results, dict):
        result_list = [results]
    elif isinstance(results, list):
        result_list = results
    else:
        result_list = []

    construction_classifications: list[str] = []
    construction_statuses: list[str] = []

    for item in result_list:
        if not isinstance(item, dict):
            continue

        construction = item.get("construction") or {}

        construction_status = construction.get("d4f_construction_status")
        classification = construction.get("hvn_poc_construction_classification")

        if construction_status:
            construction_statuses.append(str(construction_status))

        if classification:
            construction_classifications.append(str(classification))

    return {
        "available": True,
        "audit_status": payload.get("audit_status"),
        "construction_status": runtime_decision.get("construction_status"),
        "d4g_readiness": runtime_decision.get("d4g_readiness"),
        "d4h_readiness": runtime_decision.get("d4h_readiness"),
        "symbol_count_with_constructed_hvn_poc_prototype": runtime_counts.get("symbol_count_with_constructed_hvn_poc_prototype"),
        "construction_statuses": construction_statuses,
        "construction_classifications": construction_classifications,
        "guardrail_failure_count": payload.get("guardrail_failure_count"),
        "writes_to_supabase": payload.get("writes_to_supabase"),
        "mutates_campaigns": payload.get("mutates_campaigns"),
        "executes_d3d": payload.get("executes_d3d"),
        "authorizes_d3d": payload.get("authorizes_d3d"),
        "operator_control_confirmed_by_this_endpoint": payload.get("operator_control_confirmed_by_this_endpoint"),
        "d3d_execution_recommendation": runtime_decision.get("d3d_execution_recommendation"),
        "d4f_makes_any_campaign_d3d_eligible": runtime_decision.get("d4f_makes_any_campaign_d3d_eligible"),
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
        "d3d_execution_recommendation",
        "candidate_count",
        "eligible_candidate_count",
        "d3d_eligible_count",
    ]:
        if key in payload:
            compact[key] = payload.get(key)

    return compact


def main() -> int:
    d4e_fetch = _fetch_json(D4E_URL)
    d4f_fetch = _fetch_json(D4F_URL)
    d3v_fetch = _fetch_json(D3V_URL)
    repo_inventory = _scan_repository()

    failures: list[dict[str, Any]] = []

    d4e_payload = d4e_fetch.get("payload") if d4e_fetch.get("ok") else None
    d4f_payload = d4f_fetch.get("payload") if d4f_fetch.get("ok") else None
    d3v_payload = d3v_fetch.get("payload") if d3v_fetch.get("ok") else None

    d4e_compact = _compact_d4e(d4e_payload)
    d4f_compact = _compact_d4f(d4f_payload)
    d3v_compact = _compact_d3v(d3v_payload)

    if not d4e_fetch.get("ok"):
        failures.append(
            {
                "check": "d4e_live_read_only_source_available",
                "expected": True,
                "actual": False,
                "error": d4e_fetch.get("error"),
            }
        )

    if not d4f_fetch.get("ok"):
        failures.append(
            {
                "check": "d4f_live_read_only_hvn_poc_prototype_available",
                "expected": True,
                "actual": False,
                "error": d4f_fetch.get("error"),
            }
        )

    if d4f_compact.get("writes_to_supabase") is not False:
        failures.append(
            {
                "check": "d4f_writes_to_supabase",
                "expected": False,
                "actual": d4f_compact.get("writes_to_supabase"),
            }
        )

    if d4f_compact.get("mutates_campaigns") is not False:
        failures.append(
            {
                "check": "d4f_mutates_campaigns",
                "expected": False,
                "actual": d4f_compact.get("mutates_campaigns"),
            }
        )

    if d4f_compact.get("authorizes_d3d") is not False:
        failures.append(
            {
                "check": "d4f_authorizes_d3d",
                "expected": False,
                "actual": d4f_compact.get("authorizes_d3d"),
            }
        )

    if d4f_compact.get("d4f_makes_any_campaign_d3d_eligible") is not False:
        failures.append(
            {
                "check": "d4f_makes_any_campaign_d3d_eligible",
                "expected": False,
                "actual": d4f_compact.get("d4f_makes_any_campaign_d3d_eligible"),
            }
        )

    if d4f_compact.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "check": "d4f_d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": d4f_compact.get("d3d_execution_recommendation"),
            }
        )

    if d3v_fetch.get("ok"):
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

        if d3v_compact.get("execution_authorized") is not False:
            failures.append(
                {
                    "check": "d3v_execution_authorized",
                    "expected": False,
                    "actual": d3v_compact.get("execution_authorized"),
                }
            )

    source_resolution_findings = {
        "d4e_confirmed_live_read_only_ohlcv_source": d4e_compact.get("source_status") == "LIVE_READ_ONLY_BAR_SOURCE_AVAILABLE",
        "d4f_confirmed_read_only_hvn_poc_prototype": (
            int(d4f_compact.get("symbol_count_with_constructed_hvn_poc_prototype") or 0) > 0
        ),
        "d4f_profile_classification": d4f_compact.get("construction_classifications"),
        "true_exchange_volume_at_price_runtime_source_confirmed": False,
        "tick_level_or_intrabar_volume_profile_runtime_source_confirmed": False,
        "explicit_sml_runtime_source_confirmed_for_d3d": False,
        "daily_ohlcv_profile_sufficient_for_d3d": False,
        "true_structural_source_available_for_d3d": False,
        "d3d_preflight_should_run": False,
        "source_gap": [
            "D4F constructed an OHLCV-derived prototype only.",
            "Daily OHLCV bars do not provide true intrabar volume-at-price.",
            "No true exchange volume-at-price or tick-derived HVN/POC runtime source has been confirmed.",
            "No explicit SML/structural-location runtime source has been confirmed for D3D.",
            "D3D remains blocked until true structural source evidence exists.",
        ],
        "acceptable_next_source_resolution_paths": [
            "SRC2A: add explicit SML or structural-location source that is not inferred.",
            "SRC2B: add true exchange volume-at-price provider or tick-derived volume profile source.",
            "SRC2C: add intraday profile source-quality bridge, but keep it blocked from D3D unless D4G/D4H-equivalent review confirms true structural eligibility.",
        ],
    }

    output = {
        "engine": "SRC1_TRUE_STRUCTURAL_SOURCE_RESOLUTION_INVENTORY",
        "version": "source_resolution_src1_true_structural_source_inventory_v1",
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
        "live_endpoint_inventory": {
            "d4e_fetch": {
                "ok": d4e_fetch.get("ok"),
                "url": D4E_URL,
                "error": d4e_fetch.get("error"),
                "compact": d4e_compact,
            },
            "d4f_fetch": {
                "ok": d4f_fetch.get("ok"),
                "url": D4F_URL,
                "error": d4f_fetch.get("error"),
                "compact": d4f_compact,
            },
            "d3v_fetch": {
                "ok": d3v_fetch.get("ok"),
                "url": D3V_URL,
                "error": d3v_fetch.get("error"),
                "compact": d3v_compact,
            },
        },
        "repository_pattern_inventory": repo_inventory,
        "source_resolution_findings": source_resolution_findings,
        "guardrail_failure_count": len(failures),
        "guardrail_failures": failures,
        "runtime_decision": {
            "src1_status": (
                "PASS_SRC1_TRUE_STRUCTURAL_SOURCE_INVENTORY_COMPLETED"
                if len(failures) == 0
                else "FAIL_SRC1_TRUE_STRUCTURAL_SOURCE_INVENTORY"
            ),
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src1_makes_any_campaign_d3d_eligible": False,
            "next_action": (
                "PROCEED_TO_SRC2_SOURCE_SELECTION_OR_IMPLEMENTATION"
                if len(failures) == 0
                else "RESOLVE_SRC1_FAILURES_BEFORE_SOURCE_SELECTION"
            ),
            "reason": (
                "SRC1 confirms that the system has live read-only OHLCV access and a read-only D4F profile prototype, "
                "but no true structural source sufficient for D3D. The correct next step is source selection or implementation, not D3D."
            ),
        },
    }

    print(json.dumps(output, indent=2, sort_keys=True))
    print("")

    if failures:
        print("FINAL RESULT: FAIL - SRC1 inventory found guardrail failures; D3D remains blocked.")
        return 1

    print("FINAL RESULT: PASS - SRC1 inventory completed; true D3D structural source is still missing; proceed to SRC2 source selection or implementation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
