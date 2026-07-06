from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ENGINE = "D4C_READ_ONLY_MARKET_DATA_SOURCE_PATH_INVENTORY"
VERSION = "phase_d4c_market_data_source_path_inventory_read_only_v1"

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("SIGMALYTIC_BASE_URL", "https://sigmalytic-backend.onrender.com").rstrip("/")

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

MARKET_DATA_PATTERNS: Dict[str, Dict[str, Any]] = {
    "alpaca_bar_source": {
        "patterns": [
            r"\balpaca\b",
            r"\bStockHistoricalDataClient\b",
            r"\bStockBarsRequest\b",
            r"\bget_stock_bars\b",
            r"\bget_bars\b",
            r"\bSIP\b",
            r"\bfeed\s*=\s*[\"']sip[\"']",
        ],
        "meaning": "Potential Alpaca/SIP OHLCV source path.",
    },
    "ohlcv_bar_terms": {
        "patterns": [
            r"\bohlcv\b",
            r"\bdaily_bars\b",
            r"\bbars\b",
            r"\bprice_bars\b",
            r"\bhistorical_bars\b",
            r"\bmarket_data_bars\b",
            r"\bopen\b",
            r"\bhigh\b",
            r"\blow\b",
            r"\bclose\b",
            r"\bvolume\b",
        ],
        "meaning": "Potential OHLCV bar container or field reference.",
    },
    "supabase_storage_path": {
        "patterns": [
            r"\bsupabase\b",
            r"\bfrom_\(",
            r"\btable\(",
            r"\bcampaigns\b",
            r"\bcached_renko_bricks\b",
            r"\bdebug_snapshot\b",
            r"\bmarket_data\b",
            r"\bhistorical\b",
        ],
        "meaning": "Potential Supabase persistence/read path.",
    },
    "discovery_pipeline_path": {
        "patterns": [
            r"\bdiscovery\b",
            r"\bnightly\b",
            r"\brun_full_nightly\b",
            r"\brun-full-nightly\b",
            r"\buniverse\b",
            r"\brecords_built\b",
            r"\bfetch\b",
            r"\bpagination\b",
        ],
        "meaning": "Potential discovery/nightly pipeline market-data path.",
    },
    "cache_path": {
        "patterns": [
            r"\bredis\b",
            r"\bcache\b",
            r"\bcached\b",
            r"\bsnapshot\b",
            r"\bdebug\b",
        ],
        "meaning": "Potential cached read path.",
    },
    "api_route_path": {
        "patterns": [
            r"@router\.get",
            r"@app\.get",
            r"\b/api/",
            r"\brouter\b",
        ],
        "meaning": "Potential live API route path.",
    },
    "volume_profile_path": {
        "patterns": [
            r"\bvolume_profile\b",
            r"\bvolume_by_price\b",
            r"\bhvn\b",
            r"\bpoc\b",
            r"\bvpoc\b",
            r"\bhigh_volume_node\b",
        ],
        "meaning": "Potential current or future volume-profile source path.",
    },
}

RUNTIME_ENDPOINTS = {
    "d3v": "/api/campaign/d3d-dry-run-candidate-preflight-review",
    "d3c2r": "/api/campaign/hvn-poc-source-enrichment-review",
}

BAR_CONTAINER_KEYS = {
    "bars",
    "daily_bars",
    "ohlcv",
    "ohlcv_bars",
    "price_bars",
    "historical_bars",
    "market_data_bars",
    "volume_profile_bars",
    "candidate_bars",
}

OHLCV_FIELD_KEYS = {
    "open",
    "o",
    "high",
    "h",
    "low",
    "l",
    "close",
    "c",
    "price",
    "volume",
    "v",
    "vol",
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


def _line_matches(line: str, patterns: List[str]) -> List[str]:
    hits: List[str] = []

    for pattern_text in patterns:
        if re.search(pattern_text, line, flags=re.IGNORECASE):
            hits.append(pattern_text)

    return hits


def _static_inventory() -> Dict[str, Any]:
    files = _iter_files()

    family_hits: Dict[str, List[Dict[str, Any]]] = {
        family: [] for family in MARKET_DATA_PATTERNS
    }

    file_family_counter: Counter = Counter()

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

            for family, spec in MARKET_DATA_PATTERNS.items():
                hits = _line_matches(stripped, spec["patterns"])

                if not hits:
                    continue

                file_family_counter[f"{file_name}::{family}"] += 1

                if len(family_hits[family]) < 200:
                    family_hits[family].append({
                        "file": file_name,
                        "line_number": line_number,
                        "line": stripped[:240],
                        "matched_patterns": hits[:5],
                        "meaning": spec["meaning"],
                    })

    family_summary: Dict[str, Dict[str, Any]] = {}

    for family, hits in family_hits.items():
        unique_files = sorted({hit["file"] for hit in hits})
        family_summary[family] = {
            "sample_hit_count": len(hits),
            "sample_unique_file_count": len(unique_files),
            "sample_files": unique_files[:40],
            "meaning": MARKET_DATA_PATTERNS[family]["meaning"],
        }

    likely_source_files = sorted({
        item["file"]
        for family in [
            "alpaca_bar_source",
            "ohlcv_bar_terms",
            "discovery_pipeline_path",
            "supabase_storage_path",
            "cache_path",
        ]
        for item in family_hits.get(family, [])
    })

    return {
        "scanned_file_count": len(files),
        "family_summary": family_summary,
        "sample_hits": family_hits,
        "likely_market_data_source_files": likely_source_files[:120],
        "likely_market_data_source_file_count": len(likely_source_files),
    }


def _fetch_json(endpoint_name: str, path: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    url = BASE_URL + path
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Sigmalytic-D4C-Market-Data-Source-Inventory/1.0",
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


def _find_bar_evidence(value: Any, depth: int = 0) -> Dict[str, int]:
    evidence = {
        "bar_container_key_hits": 0,
        "ohlcv_field_key_hits": 0,
        "list_of_dict_bar_like_hits": 0,
    }

    if depth > 5:
        return evidence

    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()

            if key_lower in BAR_CONTAINER_KEYS:
                evidence["bar_container_key_hits"] += 1

            if key_lower in OHLCV_FIELD_KEYS:
                evidence["ohlcv_field_key_hits"] += 1

            nested_evidence = _find_bar_evidence(nested, depth + 1)
            for evidence_key, count in nested_evidence.items():
                evidence[evidence_key] += count

    elif isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]

        if dict_items:
            sample = dict_items[:10]
            bar_like_count = 0

            for item in sample:
                lower_keys = {str(key).lower() for key in item.keys()}
                if lower_keys.intersection({"close", "c", "price"}) and lower_keys.intersection({"volume", "v", "vol"}):
                    bar_like_count += 1

            if bar_like_count > 0:
                evidence["list_of_dict_bar_like_hits"] += 1

        for item in value[:20]:
            nested_evidence = _find_bar_evidence(item, depth + 1)
            for evidence_key, count in nested_evidence.items():
                evidence[evidence_key] += count

    return evidence


def _runtime_inventory() -> Dict[str, Any]:
    runtime: Dict[str, Any] = {
        "base_url": BASE_URL,
        "endpoint_results": {},
        "runtime_candidate_bar_source_status": "UNKNOWN",
    }

    for name, path in RUNTIME_ENDPOINTS.items():
        payload = _fetch_json(name, path)
        rows = _rows_from_payload(payload)

        candidate_rows = [
            row for row in rows
            if _bool(row.get("d3v_preflight_candidate"))
        ]

        bar_evidence_counter: Counter = Counter()

        for row in candidate_rows:
            evidence = _find_bar_evidence(row)
            for key, count in evidence.items():
                if count:
                    bar_evidence_counter[key] += count

        runtime["endpoint_results"][name] = {
            "path": path,
            "version": payload.get("version"),
            "endpoint_status": payload.get("endpoint_status"),
            "row_count": len(rows),
            "candidate_row_count": len(candidate_rows),
            "bar_evidence_counter": dict(bar_evidence_counter),
            "writes_to_supabase": payload.get("writes_to_supabase"),
            "mutates_campaigns": payload.get("mutates_campaigns"),
            "operator_control_confirmed_by_this_engine": payload.get("operator_control_confirmed_by_this_engine"),
            "score_impact": payload.get("score_impact"),
            "rank_impact": payload.get("rank_impact"),
            "state_impact": payload.get("state_impact"),
            "transition_impact": payload.get("transition_impact"),
            "not_a_trade_signal": payload.get("not_a_trade_signal"),
        }

    d3v_counter = runtime["endpoint_results"].get("d3v", {}).get("bar_evidence_counter", {})

    if not d3v_counter:
        runtime["runtime_candidate_bar_source_status"] = "NO_OHLCV_BARS_IN_D3V_CANDIDATE_PAYLOAD"
    else:
        runtime["runtime_candidate_bar_source_status"] = "POSSIBLE_OHLCV_BAR_EVIDENCE_PRESENT_IN_D3V_PAYLOAD_REVIEW_REQUIRED"

    return runtime


def _build_decision(static_inventory: Dict[str, Any], runtime_inventory: Dict[str, Any]) -> Dict[str, Any]:
    likely_files = static_inventory.get("likely_market_data_source_files", [])
    runtime_status = runtime_inventory.get("runtime_candidate_bar_source_status")

    source_path_decision = {
        "d4c_decision": "MARKET_DATA_SOURCE_PATH_INVENTORY_ONLY",
        "runtime_bar_source_gap_confirmed": runtime_status == "NO_OHLCV_BARS_IN_D3V_CANDIDATE_PAYLOAD",
        "static_market_data_source_candidates_found": len(likely_files) > 0,
        "recommended_next_phase": "D4D_READ_ONLY_MARKET_DATA_SOURCE_ADAPTER_DESIGN",
        "recommended_next_phase_reason": "D4B needs OHLCV bars; D4C inventories candidate source paths; D4D should design a read-only adapter that supplies bars to D4B without persistence or campaign mutation.",
        "forbidden_shortcuts": [
            "Do not use HVN_ABSORPTION_PROXY as true HVN/POC.",
            "Do not use inferred SML as D3D eligibility by itself.",
            "Do not derive operator control from score, rank, campaign state, probability, expected return, gamma/options, target, or future return.",
            "Do not mutate Supabase campaigns from D4C.",
            "Do not execute D3D from D4C.",
        ],
    }

    return source_path_decision


def main() -> int:
    static_inventory = _static_inventory()
    runtime_inventory = _runtime_inventory()
    source_path_decision = _build_decision(static_inventory, runtime_inventory)

    guardrail_failures: List[Dict[str, Any]] = []

    for endpoint_name, endpoint_result in runtime_inventory.get("endpoint_results", {}).items():
        for key in [
            "writes_to_supabase",
            "mutates_campaigns",
            "operator_control_confirmed_by_this_engine",
        ]:
            value = endpoint_result.get(key)
            if value not in {False, None}:
                guardrail_failures.append({
                    "endpoint": endpoint_name,
                    "field": key,
                    "expected": "False or absent",
                    "actual": value,
                })

        for key in [
            "score_impact",
            "rank_impact",
            "state_impact",
            "transition_impact",
        ]:
            value = endpoint_result.get(key)
            if value not in {"NONE", None}:
                guardrail_failures.append({
                    "endpoint": endpoint_name,
                    "field": key,
                    "expected": "NONE or absent",
                    "actual": value,
                })

    source_gap_flags: List[str] = []

    if source_path_decision["runtime_bar_source_gap_confirmed"]:
        source_gap_flags.append("D4C_CONFIRMS_D3V_CANDIDATE_PAYLOAD_HAS_NO_OHLCV_BARS")

    if source_path_decision["static_market_data_source_candidates_found"]:
        source_gap_flags.append("D4C_STATIC_MARKET_DATA_SOURCE_CANDIDATES_FOUND")

    source_gap_flags.append("D4C_REQUIRES_READ_ONLY_BAR_ADAPTER_BEFORE_D4B_CAN_CONSTRUCT_HVN_POC")

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4C_MARKET_DATA_SOURCE_PATH_INVENTORY_COMPLETED_NO_MUTATION",
        "inventory_status": "READ_ONLY_STATIC_AND_RUNTIME_SOURCE_PATH_INVENTORY",
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
        "static_inventory": static_inventory,
        "runtime_inventory": runtime_inventory,
        "source_path_decision": source_path_decision,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4c_makes_any_campaign_d3d_eligible": False,
            "reason": "D4C inventories market-data source paths only. It does not supply bars to D4B, does not construct HVN/POC, and does not authorize D3D.",
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4C market-data source path inventory completed without mutation.")

    if guardrail_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
