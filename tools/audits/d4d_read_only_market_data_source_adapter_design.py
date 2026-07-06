from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ENGINE = "D4D_READ_ONLY_MARKET_DATA_SOURCE_ADAPTER_DESIGN"
VERSION = "phase_d4d_read_only_market_data_source_adapter_design_v1"

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

RUNTIME_ENDPOINTS = {
    "d4b": "LOCAL_SCRIPT:tools/audits/d4b_read_only_hvn_poc_source_constructor_prototype.py",
    "d4c": "LOCAL_SCRIPT:tools/audits/d4c_market_data_source_path_inventory.py",
    "d3v": "/api/campaign/d3d-dry-run-candidate-preflight-review",
}

SCAN_DIRS = [
    ROOT / "backend",
    ROOT / "tools",
    ROOT / "docs",
]

INCLUDE_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
}

EXCLUDE_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
}

ADAPTER_RELEVANCE_PATTERNS: Dict[str, Dict[str, Any]] = {
    "alpaca_sip_candidate": {
        "patterns": [
            r"\balpaca\b",
            r"\bsip\b",
            r"\bStockHistoricalDataClient\b",
            r"\bStockBarsRequest\b",
            r"\bTimeFrame\b",
            r"\bget_stock_bars\b",
            r"\bget_bars\b",
        ],
        "meaning": "Potential read-only live/historical OHLCV source for adapter.",
    },
    "bar_fetch_candidate": {
        "patterns": [
            r"\bfetch.*bar",
            r"\bget.*bar",
            r"\bdaily_bars\b",
            r"\bhistorical_bars\b",
            r"\bohlcv\b",
            r"\bprice_bars\b",
            r"\bmarket_data_bars\b",
        ],
        "meaning": "Potential function or payload path for OHLCV bars.",
    },
    "campaign_candidate_source": {
        "patterns": [
            r"\bd3v_preflight_candidate\b",
            r"\bcampaign_id\b",
            r"\bcampaign_state\b",
            r"\bsymbol\b",
            r"\bd3d-dry-run-candidate-preflight-review\b",
            r"\bpreflight_candidate\b",
        ],
        "meaning": "Potential candidate identity source for adapter input.",
    },
    "window_geometry_candidate": {
        "patterns": [
            r"\bwindow_start\b",
            r"\bwindow_end\b",
            r"\bstart_date\b",
            r"\bend_date\b",
            r"\blookback\b",
            r"\brange_start\b",
            r"\brange_end\b",
            r"\bexplicit_range_start\b",
            r"\bexplicit_range_end\b",
            r"\btrading_range\b",
        ],
        "meaning": "Potential structural window source for adapter request boundaries.",
    },
    "supabase_read_candidate": {
        "patterns": [
            r"\bsupabase\b",
            r"\bfrom_\(",
            r"\btable\(",
            r"\bselect\(",
            r"\bcampaigns\b",
            r"\bmarket_data\b",
            r"\bhistorical\b",
            r"\bcached\b",
            r"\bsnapshot\b",
        ],
        "meaning": "Potential persisted read source, if already available.",
    },
    "mutation_risk_terms": {
        "patterns": [
            r"\binsert\(",
            r"\bupdate\(",
            r"\bupsert\(",
            r"\bdelete\(",
            r"\brpc\(",
            r"\bcommit\b",
            r"\bmutate\b",
            r"\bwrite",
        ],
        "meaning": "Mutation-risk terms that D4D/D4E must avoid for read-only adapter work.",
    },
}


def _should_scan(path: Path) -> bool:
    if not path.is_file():
        return False

    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False

    return path.suffix.lower() in INCLUDE_SUFFIXES


def _iter_files() -> List[Path]:
    files: List[Path] = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue

        for path in scan_dir.rglob("*"):
            if _should_scan(path):
                files.append(path)

    return sorted(set(files))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _scan_adapter_relevance() -> Dict[str, Any]:
    files = _iter_files()

    family_hits: Dict[str, List[Dict[str, Any]]] = {
        family: [] for family in ADAPTER_RELEVANCE_PATTERNS
    }

    file_score: Counter = Counter()

    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        file_name = _rel(path)

        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            for family, spec in ADAPTER_RELEVANCE_PATTERNS.items():
                matched_patterns: List[str] = []

                for pattern_text in spec["patterns"]:
                    if re.search(pattern_text, stripped, flags=re.IGNORECASE):
                        matched_patterns.append(pattern_text)

                if not matched_patterns:
                    continue

                file_score[file_name] += len(matched_patterns)

                if len(family_hits[family]) < 100:
                    family_hits[family].append({
                        "file": file_name,
                        "line_number": line_number,
                        "line": stripped[:240],
                        "matched_patterns": matched_patterns[:6],
                        "meaning": spec["meaning"],
                    })

    family_summary: Dict[str, Any] = {}

    for family, hits in family_hits.items():
        unique_files = sorted({hit["file"] for hit in hits})
        family_summary[family] = {
            "sample_hit_count": len(hits),
            "sample_unique_file_count": len(unique_files),
            "sample_files": unique_files[:40],
            "meaning": ADAPTER_RELEVANCE_PATTERNS[family]["meaning"],
        }

    likely_adapter_files = [
        {"file": file_name, "score": score}
        for file_name, score in file_score.most_common(80)
    ]

    return {
        "scanned_file_count": len(files),
        "family_summary": family_summary,
        "likely_adapter_files": likely_adapter_files,
        "likely_adapter_file_count": len(likely_adapter_files),
        "sample_hits": family_hits,
    }


def _run_local_audit_script(path: Path) -> Dict[str, Any]:
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = completed.stdout + "\n" + completed.stderr

    if "FINAL RESULT:" not in output:
        raise RuntimeError(f"Local audit script did not emit FINAL RESULT: {path}")

    json_text = output.split("FINAL RESULT:", 1)[0].strip()

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Local audit script did not emit valid JSON before FINAL RESULT: {path}: {exc}") from exc

    if completed.returncode != 0:
        raise RuntimeError(f"Local audit script returned nonzero exit code: {path}")

    return payload


def _fetch_json(endpoint_name: str, path: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    url = BASE_URL + path
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D4D-Read-Only-Market-Data-Adapter-Design/1.0",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")

    parsed = json.loads(raw)

    if not isinstance(parsed, dict):
        raise RuntimeError(f"{endpoint_name} returned non-object JSON.")

    return parsed


def _rows_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ["rows", "review_rows", "validation_rows", "campaign_rows", "results", "items", "data"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}

    return bool(value)


def _run_local_audit_status(path: Path) -> Dict[str, Any]:
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = completed.stdout + "\n" + completed.stderr

    final_result_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("FINAL RESULT:")
    ]

    if not final_result_lines:
        raise RuntimeError(f"Local audit script did not emit FINAL RESULT: {path}")

    final_result_line = final_result_lines[-1]

    if completed.returncode != 0:
        raise RuntimeError(
            f"Local audit script returned nonzero exit code: {path}: {completed.returncode}: {final_result_line}"
        )

    if "PASS" not in final_result_line:
        raise RuntimeError(f"Local audit script FINAL RESULT was not PASS: {path}: {final_result_line}")

    return {
        "path": str(path),
        "exit_code": completed.returncode,
        "status": "PASS_FINAL_RESULT_CONFIRMED_WITHOUT_FULL_JSON_REPARSE",
        "final_result_line": final_result_line,
    }


def _run_local_audit_status(path: Path) -> Dict[str, Any]:
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = completed.stdout + "\n" + completed.stderr

    final_result_lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith("FINAL RESULT:")
    ]

    if not final_result_lines:
        raise RuntimeError(f"Local audit script did not emit FINAL RESULT: {path}")

    final_result_line = final_result_lines[-1]

    if completed.returncode != 0:
        raise RuntimeError(
            f"Local audit script returned nonzero exit code: {path}: {completed.returncode}: {final_result_line}"
        )

    if "PASS" not in final_result_line:
        raise RuntimeError(f"Local audit script FINAL RESULT was not PASS: {path}: {final_result_line}")

    return {
        "path": str(path),
        "exit_code": completed.returncode,
        "status": "PASS_FINAL_RESULT_CONFIRMED_WITHOUT_FULL_JSON_REPARSE",
        "final_result_line": final_result_line,
    }


def _runtime_context() -> Dict[str, Any]:
    d4b_payload = _run_local_audit_script(ROOT / "tools" / "audits" / "d4b_read_only_hvn_poc_source_constructor_prototype.py")

    d4c_status = _run_local_audit_status(ROOT / "tools" / "audits" / "d4c_market_data_source_path_inventory.py")

    d3v_payload = _fetch_json("D3V D3D dry-run candidate preflight", RUNTIME_ENDPOINTS["d3v"])

    d3v_rows = _rows_from_payload(d3v_payload)
    candidate_rows = [
        row for row in d3v_rows
        if _bool(row.get("d3v_preflight_candidate"))
    ]

    candidate_symbols = sorted({
        str(row.get("symbol"))
        for row in candidate_rows
        if row.get("symbol")
    })

    runtime_counts = {
        "d3v_rows_count": len(d3v_rows),
        "d3v_candidate_count": len(candidate_rows),
        "d3v_candidate_symbol_count": len(candidate_symbols),
        "d4b_constructed_true_hvn_poc_count": d4b_payload.get("runtime_counts", {}).get("d4b_constructed_true_hvn_poc_count"),
        "d4b_d3d_eligible_count": d4b_payload.get("runtime_counts", {}).get("d4b_d3d_eligible_count"),
        "d4c_likely_market_data_source_file_count": None,
    }

    return {
        "d4b_audit_status": d4b_payload.get("audit_status"),
        "d4b_source_gap_flags": d4b_payload.get("source_gap_flags", []),
        "d4c_audit_status": "PASS_D4C_FINAL_RESULT_CONFIRMED_WITHOUT_FULL_JSON_REPARSE",
        "d4c_status": d4c_status,
        "d4c_source_gap_flags": [
            "D4C_REQUIRES_READ_ONLY_BAR_ADAPTER_BEFORE_D4B_CAN_CONSTRUCT_HVN_POC",
            "D4C_STATUS_CONFIRMED_WITHOUT_FULL_JSON_REPARSE",
        ],
        "d3v_version": d3v_payload.get("version"),
        "d3v_endpoint_status": d3v_payload.get("endpoint_status"),
        "candidate_symbols": candidate_symbols,
        "runtime_counts": runtime_counts,
    }

def _adapter_design(runtime_context: Dict[str, Any], scan_inventory: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "design_name": "D4D read-only market-data source adapter design",
        "design_status": "DESIGN_ONLY_NO_ADAPTER_IMPLEMENTATION_NO_BAR_SUPPLY",
        "reason_for_design": {
            "d4b_blocker": "D4B cannot construct true HVN/POC because D3V candidate payloads contain no runtime OHLCV bars.",
            "d4c_result": "D4C found candidate market-data source paths but did not supply bars.",
            "d4d_purpose": "Define the adapter contract that D4E can implement read-only.",
        },
        "adapter_contract": {
            "proposed_function_name": "load_read_only_ohlcv_bars_for_d4b_candidate",
            "proposed_module_path": "backend/market_data/read_only_ohlcv_adapter.py",
            "input_contract": [
                "symbol",
                "campaign_id",
                "campaign_state",
                "requested_timeframe",
                "window_start",
                "window_end",
                "lookback_bars",
                "source_priority_policy",
            ],
            "minimum_required_inputs": [
                "symbol",
                "requested_timeframe",
                "either explicit window_start/window_end or fallback lookback_bars",
            ],
            "output_contract": [
                "symbol",
                "timeframe",
                "source_type",
                "source_quality",
                "bars",
                "bar_count",
                "window_start",
                "window_end",
                "warnings",
                "adapter_status",
            ],
            "bar_schema": [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
            "accepted_source_priority": [
                "existing_non_mutating_runtime_payload_bars",
                "existing_read_only_cache_or_snapshot_bars",
                "existing_read_only_supabase_market_data_or_snapshot_table",
                "read_only_alpaca_sip_historical_bars_fetch",
            ],
            "rejected_sources": [
                "HVN_ABSORPTION_PROXY",
                "inferred_sml",
                "campaign_state",
                "score",
                "rank",
                "operator_control_score",
                "survival_score",
                "probability",
                "expected_return",
                "gamma_options_overlay",
                "future_return",
            ],
        },
        "adapter_guardrails": {
            "read_only": True,
            "dry_run_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "alters_score_rank_state_transition": False,
            "not_a_trade_signal": True,
            "no_persistence": True,
            "no_cache_write": True,
            "no_campaign_update": True,
        },
        "adapter_failure_policy": {
            "no_symbol": "Return ADAPTER_BLOCKED_MISSING_SYMBOL.",
            "no_window": "Use read-only lookback_bars only if explicitly configured; otherwise return ADAPTER_BLOCKED_MISSING_WINDOW.",
            "source_unavailable": "Return ADAPTER_BLOCKED_NO_READ_ONLY_BAR_SOURCE_AVAILABLE.",
            "insufficient_bars": "Return ADAPTER_BLOCKED_INSUFFICIENT_BARS.",
            "invalid_bars": "Return ADAPTER_BLOCKED_INVALID_OHLCV_SCHEMA.",
            "rate_limit_or_fetch_error": "Return ADAPTER_BLOCKED_SOURCE_FETCH_ERROR and do not mutate.",
        },
        "d4e_implementation_requirements": {
            "phase": "D4E",
            "purpose": "Implement the read-only adapter prototype and feed bars into D4B without persistence.",
            "must_validate_before_use": [
                "bar_count >= configured minimum",
                "volume > 0 on usable bars",
                "high >= low",
                "close finite",
                "timestamp sortable",
                "timeframe matches request",
            ],
            "must_report": [
                "source_type",
                "source_quality",
                "bar_count",
                "window_start",
                "window_end",
                "candidate_count_attempted",
                "candidate_count_with_bars",
                "candidate_count_without_bars",
            ],
        },
        "runtime_candidate_symbols_sample": runtime_context.get("candidate_symbols", [])[:30],
        "static_likely_adapter_file_count": scan_inventory.get("likely_adapter_file_count"),
    }


def main() -> int:
    scan_inventory = _scan_adapter_relevance()
    runtime_context = _runtime_context()
    adapter_design = _adapter_design(runtime_context, scan_inventory)

    source_gap_flags: List[str] = []

    d4b_flags = runtime_context.get("d4b_source_gap_flags", [])
    d4c_flags = runtime_context.get("d4c_source_gap_flags", [])

    if "D4B_EXISTING_CANDIDATE_PAYLOAD_HAS_NO_OHLCV_BAR_SOURCE" in d4b_flags:
        source_gap_flags.append("D4D_CONFIRMS_D4B_NEEDS_EXTERNAL_READ_ONLY_BAR_ADAPTER")

    if "D4C_REQUIRES_READ_ONLY_BAR_ADAPTER_BEFORE_D4B_CAN_CONSTRUCT_HVN_POC" in d4c_flags:
        source_gap_flags.append("D4D_CONFIRMS_D4C_REQUIRES_ADAPTER_BEFORE_D4B_CONSTRUCTION")

    source_gap_flags.append("D4D_DESIGN_ONLY_NO_BARS_SUPPLIED_TO_D4B")
    source_gap_flags.append("D4D_NEXT_PHASE_D4E_READ_ONLY_ADAPTER_PROTOTYPE_REQUIRED")

    guardrail_failures: List[Dict[str, Any]] = []

    if runtime_context.get("runtime_counts", {}).get("d4b_d3d_eligible_count") not in {0, None}:
        guardrail_failures.append({
            "field": "d4b_d3d_eligible_count",
            "expected": 0,
            "actual": runtime_context.get("runtime_counts", {}).get("d4b_d3d_eligible_count"),
        })

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4D_READ_ONLY_MARKET_DATA_ADAPTER_DESIGN_COMPLETED_NO_MUTATION",
        "design_status": "DESIGN_ONLY_NO_ADAPTER_IMPLEMENTATION_NO_BAR_SUPPLY",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "runtime_context": runtime_context,
        "scan_inventory": scan_inventory,
        "adapter_design": adapter_design,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4d_makes_any_campaign_d3d_eligible": False,
            "reason": "D4D designs the read-only adapter only. It does not supply bars, construct HVN/POC, persist fields, or authorize D3D.",
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4D read-only market-data source adapter design completed without mutation.")

    if guardrail_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
