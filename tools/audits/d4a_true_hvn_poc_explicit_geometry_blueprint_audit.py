from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List


ENGINE = "D4A_TRUE_HVN_POC_EXPLICIT_GEOMETRY_SOURCE_CONSTRUCTION_BLUEPRINT"
VERSION = "phase_d4a_true_hvn_poc_explicit_geometry_blueprint_read_only_v1"

ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = [
    ROOT / "backend",
    ROOT / "frontend",
    ROOT / "tools",
    ROOT / "docs",
]

INCLUDE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".md",
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


SOURCE_PATTERNS: Dict[str, List[str]] = {
    "market_data_ohlcv_terms": [
        r"\bohlcv\b",
        r"\bdaily_bars\b",
        r"\bbars\b",
        r"\bopen\b",
        r"\bhigh\b",
        r"\blow\b",
        r"\bclose\b",
        r"\bvolume\b",
        r"\bvwap\b",
        r"\balpaca\b",
        r"\bsip\b",
    ],
    "true_hvn_poc_terms": [
        r"\btrue_hvn_poc\b",
        r"\bhvn_poc_source\b",
        r"\bhvn_poc_truth_status\b",
        r"\bhvn_level\b",
        r"\bpoc_level\b",
        r"\bvpoc\b",
        r"\bvolume_profile\b",
        r"\bvolume_profile_poc\b",
        r"\bhigh_volume_node\b",
        r"\bvolume_node\b",
    ],
    "proxy_terms": [
        r"\bHVN_ABSORPTION_PROXY\b",
        r"\bhvn_absorption_proxy\b",
        r"\bproxy_only_true_hvn_poc_source_missing\b",
    ],
    "explicit_geometry_terms": [
        r"\bexplicit_geometry\b",
        r"\bexplicit_geometry_sml\b",
        r"\bstructural_location\b",
        r"\btrading_range\b",
        r"\brange_high\b",
        r"\brange_low\b",
        r"\bsupport_level\b",
        r"\bresistance_level\b",
        r"\blast_point\b",
        r"\blp_zone\b",
        r"\bSML\b",
    ],
    "inferred_geometry_terms": [
        r"\binferred_sml\b",
        r"\bINFERRED_SML_REJECTED\b",
        r"\bINFERRED_FROM_ABSORPTION_EVENT\b",
        r"\bINFERRED_FROM_CLASSICAL_EVENT\b",
        r"\binferred_behavioral_location\b",
    ],
}


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False

    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False

    return path.suffix.lower() in INCLUDE_SUFFIXES


def iter_files() -> List[Path]:
    files: List[Path] = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue

        for path in scan_dir.rglob("*"):
            if should_scan(path):
                files.append(path)

    return sorted(set(files))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def scan_terms() -> Dict[str, Any]:
    files = iter_files()

    family_file_hits: Dict[str, Dict[str, int]] = {
        family: {} for family in SOURCE_PATTERNS
    }

    family_hit_counts: Dict[str, int] = {
        family: 0 for family in SOURCE_PATTERNS
    }

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        file_name = rel(path)

        for family, patterns in SOURCE_PATTERNS.items():
            for pattern_text in patterns:
                pattern = re.compile(pattern_text, flags=re.IGNORECASE)
                matches = list(pattern.finditer(text))

                if not matches:
                    continue

                family_hit_counts[family] += len(matches)
                family_file_hits[family][file_name] = family_file_hits[family].get(file_name, 0) + len(matches)

    family_summary: Dict[str, Dict[str, Any]] = {}

    for family in SOURCE_PATTERNS:
        files_for_family = family_file_hits[family]
        family_summary[family] = {
            "hit_count": family_hit_counts[family],
            "unique_file_count": len(files_for_family),
            "files": sorted(files_for_family.keys()),
        }

    return {
        "scanned_file_count": len(files),
        "family_summary": family_summary,
    }


def build_blueprint() -> Dict[str, Any]:
    return {
        "blueprint_name": "D4A true HVN/POC and explicit geometry source construction blueprint",
        "blueprint_status": "BLUEPRINT_ONLY_NO_SOURCE_CONSTRUCTION_NO_MUTATION",
        "reason_for_phase": {
            "d3z_runtime_blocker": "D3Z showed runtime true HVN/POC source availability is zero and D3V eligible count is zero.",
            "required_next_work": "Define how true HVN/POC and explicit SML geometry will be constructed before any D3D eligibility path can exist.",
        },
        "doctrine_boundary": {
            "operator_control": "Operator control is evidence, not a score.",
            "d4a_is_not_d3d": True,
            "d4a_executes_d3d": False,
            "d4a_authorizes_d3d": False,
            "d4a_confirms_operator_control": False,
            "d4a_mutates_campaigns": False,
            "d4a_writes_to_supabase": False,
            "hvn_absorption_proxy_policy": "HVN_ABSORPTION_PROXY is proxy-only and must never be treated as true HVN/POC.",
            "inferred_sml_policy": "Inferred SML is not D3D eligible by itself.",
        },
        "true_hvn_poc_source_contract": {
            "definition": "True HVN/POC must be derived from an auditable volume-by-price distribution over an explicit structural window.",
            "minimum_input_data": [
                "symbol",
                "campaign_id or candidate structural window id",
                "timestamped OHLCV bars",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "bar timeframe",
                "lookback/window start",
                "lookback/window end",
            ],
            "accepted_source_types": [
                "volume_profile_from_ohlcv_distribution",
                "anchored_volume_profile_from_explicit_range",
                "externally supplied auditable volume_profile_poc field",
                "externally supplied auditable hvn_level or vpoc field",
            ],
            "rejected_source_types": [
                "HVN_ABSORPTION_PROXY",
                "generic absorption label",
                "behavioral label without price-volume distribution",
                "rank",
                "score",
                "survival score",
                "operator-control score",
                "gamma/options overlay",
                "future return",
                "probability or expected return",
            ],
            "poc_rule": "POC is the price bin with maximum allocated volume inside the explicit structural window.",
            "hvn_rule": "HVN levels are volume-by-price bins or contiguous zones whose allocated volume exceeds the configured percentile or local-node threshold inside the explicit structural window.",
            "required_output_fields": [
                "true_hvn_poc_available",
                "true_hvn_poc_source_type",
                "true_hvn_poc_source_count",
                "poc_price",
                "hvn_levels",
                "hvn_zones",
                "volume_profile_window_start",
                "volume_profile_window_end",
                "volume_profile_bin_size",
                "volume_profile_total_volume",
                "volume_profile_source_quality",
            ],
        },
        "explicit_geometry_source_contract": {
            "definition": "Explicit geometry must identify the structural window where volume profile is computed and where SML/last-point logic is evaluated.",
            "minimum_required_geometry": [
                "explicit_range_high",
                "explicit_range_low",
                "explicit_range_start",
                "explicit_range_end",
                "structural_location_label",
                "support_or_resistance_reference",
                "last_point_or_sml_reference",
            ],
            "accepted_geometry_sources": [
                "confirmed trading range boundaries",
                "explicit support/resistance levels",
                "explicit last-point support or last-point supply zone",
                "explicit spring/upthrust/test geometry",
                "explicit re-accumulation or distribution range geometry",
            ],
            "rejected_geometry_sources": [
                "inferred_sml alone",
                "generic campaign state",
                "BIRTH/CONFIRMED/SURVIVING/EXPANDING state alone",
                "composite score",
                "rank",
                "gamma/options overlay",
                "HVN_ABSORPTION_PROXY",
            ],
            "required_output_fields": [
                "explicit_geometry_sml",
                "explicit_geometry_source_type",
                "explicit_range_high",
                "explicit_range_low",
                "explicit_range_start",
                "explicit_range_end",
                "explicit_sml_price",
                "explicit_sml_label",
                "explicit_geometry_quality",
            ],
        },
        "future_d4b_read_only_construction_plan": {
            "phase": "D4B",
            "status": "NOT_BUILT_BY_D4A",
            "purpose": "Build a read-only candidate source constructor that computes true HVN/POC and explicit geometry fields without mutating campaigns.",
            "required_guardrails": [
                "dry_run true",
                "writes_to_supabase false",
                "mutates_campaigns false",
                "executes_d3d false",
                "operator_control_confirmed_by_this_engine false",
                "score_impact NONE",
                "rank_impact NONE",
                "state_impact NONE",
                "transition_impact NONE",
                "not_a_trade_signal true",
            ],
        },
    }


def main() -> int:
    scan_result = scan_terms()
    blueprint = build_blueprint()

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_D4A_BLUEPRINT_COMPLETED_NO_MUTATION",
        "source_construction_status": "BLUEPRINT_ONLY_NO_SOURCE_CONSTRUCTION",
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
        "scan_result": scan_result,
        "blueprint": blueprint,
        "runtime_decision": {
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "reason": "D4A defines true HVN/POC and explicit geometry construction requirements only. It does not create source fields and does not make any campaign eligible for D3D.",
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D4A true HVN/POC and explicit geometry blueprint completed without mutation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
