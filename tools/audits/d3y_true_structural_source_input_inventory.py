from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


ENGINE = "D3Y_TRUE_STRUCTURAL_SOURCE_INPUT_INVENTORY"
VERSION = "phase_d3y_true_structural_source_input_inventory_static_v1"

ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = [
    ROOT / "backend",
    ROOT / "frontend",
    ROOT / "src",
    ROOT / "app",
    ROOT / "components",
    ROOT / "pages",
]

INCLUDE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".sql",
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


FIELD_FAMILIES: Dict[str, Dict[str, object]] = {
    "true_hvn_poc_source_terms": {
        "purpose": "Locate possible explicit HVN / POC / VPOC / volume-profile source fields.",
        "patterns": [
            r"\btrue_hvn_poc\b",
            r"\bhvn_poc_source\b",
            r"\bhvn_poc_truth_status\b",
            r"\bhvn_level\b",
            r"\bpoc_level\b",
            r"\bvpoc\b",
            r"\bvolume_profile_poc\b",
            r"\bvolume_profile_node\b",
            r"\bvolume_node\b",
            r"\bmajor_volume_node\b",
            r"\bhigh_volume_node\b",
            r"\bhigh_volume_zone\b",
            r"\bvolume_profile\b",
        ],
    },
    "hvn_absorption_proxy_terms": {
        "purpose": "Locate proxy-only HVN absorption terms that must never be treated as true HVN/POC.",
        "patterns": [
            r"\bHVN_ABSORPTION_PROXY\b",
            r"\bhvn_absorption_proxy\b",
            r"\bproxy_only_true_hvn_poc_source_missing\b",
            r"\bnot_true_hvn_poc\b",
        ],
    },
    "explicit_geometry_terms": {
        "purpose": "Locate explicit structural-location geometry inputs used for SML / trading range / LP / support-resistance readiness.",
        "patterns": [
            r"\bexplicit_geometry\b",
            r"\bexplicit_geometry_sml\b",
            r"\bexplicit_trading_range\b",
            r"\bexplicit_support_resistance\b",
            r"\bstructural_location\b",
            r"\bstructural_location_input\b",
            r"\btrading_range\b",
            r"\brange_high\b",
            r"\brange_low\b",
            r"\bsupport_level\b",
            r"\bresistance_level\b",
            r"\blp_zone\b",
            r"\blast_point\b",
            r"\bSML\b",
            r"\bsml_present\b",
            r"\bsml_evidence_quality\b",
        ],
    },
    "inferred_geometry_terms": {
        "purpose": "Locate inferred geometry terms that are not sufficient for D3D production eligibility.",
        "patterns": [
            r"\binferred_sml\b",
            r"\bINFERRED_FROM_ABSORPTION_EVENT\b",
            r"\bINFERRED_FROM_CLASSICAL_EVENT\b",
            r"\bINFERRED_SML_REJECTED\b",
            r"\binferred_behavioral_location\b",
        ],
    },
    "market_data_source_terms": {
        "purpose": "Locate OHLCV / bar / volume inputs that could support future structural-source construction.",
        "patterns": [
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
    },
    "d3d_gate_terms": {
        "purpose": "Locate D3D gate references to ensure inventory remains read-only and does not imply production execution.",
        "patterns": [
            r"\bD3D\b",
            r"\bd3d_execution_allowed\b",
            r"\bd3d_source_used_by_this_engine\b",
            r"\bd3d_production_confirmed\b",
            r"\bdry_run\b",
            r"\bexecution_authorized\b",
            r"\bmutates_campaigns\b",
            r"\bwrites_to_supabase\b",
        ],
    },
}


def should_scan(path: Path) -> bool:
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False
    if path.suffix.lower() not in INCLUDE_SUFFIXES:
        return False
    return path.is_file()


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


def line_context(text: str, index: int) -> Dict[str, object]:
    line_number = text[:index].count("\n") + 1
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)

    return {
        "line_number": line_number,
        "line": text[line_start:line_end].strip()[:300],
    }


def main() -> int:
    scanned_files = iter_files()

    findings: List[Dict[str, object]] = []
    family_file_hits: Dict[str, Dict[str, int]] = {
        family: {} for family in FIELD_FAMILIES
    }
    family_hit_counts: Dict[str, int] = {
        family: 0 for family in FIELD_FAMILIES
    }

    for path in scanned_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            findings.append({
                "family": "file_read_error",
                "file": rel(path),
                "line_number": None,
                "matched_text": None,
                "line": None,
                "purpose": "File could not be read during static inventory.",
                "error": str(exc),
            })
            continue

        for family, spec in FIELD_FAMILIES.items():
            purpose = str(spec["purpose"])
            patterns = list(spec["patterns"])

            for pattern_text in patterns:
                pattern = re.compile(pattern_text, flags=re.IGNORECASE)

                for match in pattern.finditer(text):
                    context = line_context(text, match.start())
                    file_name = rel(path)

                    family_hit_counts[family] += 1
                    family_file_hits[family][file_name] = family_file_hits[family].get(file_name, 0) + 1

                    findings.append({
                        "family": family,
                        "file": file_name,
                        "line_number": context["line_number"],
                        "matched_text": match.group(0)[:120],
                        "line": context["line"],
                        "purpose": purpose,
                    })

    family_summary: Dict[str, Dict[str, object]] = {}

    for family, count in family_hit_counts.items():
        files = family_file_hits[family]
        family_summary[family] = {
            "hit_count": count,
            "unique_file_count": len(files),
            "files": sorted(files.keys()),
        }

    true_source_hit_count = family_hit_counts.get("true_hvn_poc_source_terms", 0)
    proxy_hit_count = family_hit_counts.get("hvn_absorption_proxy_terms", 0)
    explicit_geometry_hit_count = family_hit_counts.get("explicit_geometry_terms", 0)
    inferred_geometry_hit_count = family_hit_counts.get("inferred_geometry_terms", 0)
    market_data_hit_count = family_hit_counts.get("market_data_source_terms", 0)

    source_gap_flags: List[str] = []

    if true_source_hit_count == 0:
        source_gap_flags.append("NO_TRUE_HVN_POC_SOURCE_TERMS_FOUND_IN_CODE_SCAN")

    if explicit_geometry_hit_count == 0:
        source_gap_flags.append("NO_EXPLICIT_GEOMETRY_TERMS_FOUND_IN_CODE_SCAN")

    if proxy_hit_count > 0:
        source_gap_flags.append("HVN_ABSORPTION_PROXY_TERMS_PRESENT_REQUIRES_PROXY_ONLY_DISPLAY")

    if inferred_geometry_hit_count > 0:
        source_gap_flags.append("INFERRED_GEOMETRY_TERMS_PRESENT_NOT_D3D_ELIGIBLE_BY_ITSELF")

    if market_data_hit_count == 0:
        source_gap_flags.append("NO_MARKET_DATA_SOURCE_TERMS_FOUND_IN_CODE_SCAN")

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_STATIC_INVENTORY_COMPLETED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "operator_control_unconfirmed_by_this_audit": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "scanned_file_count": len(scanned_files),
        "finding_count": len(findings),
        "unique_finding_file_count": len(sorted(set(item["file"] for item in findings if item.get("file")))),
        "family_summary": family_summary,
        "source_gap_flags": source_gap_flags,
        "doctrine_result": {
            "d3y_does_not_confirm_operator_control": True,
            "d3y_does_not_execute_d3d": True,
            "d3y_inventory_only": True,
            "hvn_absorption_proxy_remains_proxy_only": True,
            "true_hvn_poc_requires_explicit_source": True,
            "inferred_sml_remains_non_eligible_for_d3d_by_itself": True,
        },
        "findings": findings[:300],
        "finding_truncation_policy": "FIRST_300_FINDINGS_ONLY",
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    print("")
    print("FINAL RESULT: PASS - D3Y true structural source input inventory completed without mutation.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
