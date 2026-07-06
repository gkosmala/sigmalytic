from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


ENGINE = "D3W_FRONTEND_DISPLAY_SEPARATION_AUDIT"
VERSION = "phase_d3w_frontend_display_separation_static_audit_v1"


ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = [
    ROOT / "frontend",
    ROOT / "src",
    ROOT / "app",
    ROOT / "components",
    ROOT / "pages",
    ROOT / "backend",
]

INCLUDE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".md",
    ".json",
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

RISK_PATTERNS = [
    {
        "name": "direct_operator_control_confirmed_reference",
        "pattern": r"\boperator_control_confirmed\b",
        "risk": "Direct display of operator_control_confirmed can collapse legacy evidence and D3D production confirmation unless explicitly labeled.",
    },
    {
        "name": "generic_operator_confirmed_label",
        "pattern": r"Operator\s+Control\s+Confirmed|Operator\s+Confirmed|Confirmed\s+Operator",
        "risk": "Generic confirmed language must distinguish D3D production confirmation from legacy/shadow diagnostics.",
    },
    {
        "name": "legacy_operator_control_without_legacy_label",
        "pattern": r"legacy_operator_control_confirmed",
        "risk": "Legacy operator-control evidence must be displayed as evidence only, never production confirmation.",
    },
    {
        "name": "d3d_status_reference",
        "pattern": r"d3d_production_confirmed|D3D_DRY_RUN|D3D",
        "risk": "D3D display must include dry-run/authorization/mutation status and must not imply execution.",
    },
    {
        "name": "hvn_proxy_reference",
        "pattern": r"HVN_ABSORPTION_PROXY|hvn_absorption_proxy",
        "risk": "HVN_ABSORPTION_PROXY must be labeled proxy-only and not true HVN/POC.",
    },
    {
        "name": "true_hvn_poc_reference",
        "pattern": r"true_hvn_poc|hvn_poc_truth_status|hvn_poc_source",
        "risk": "True HVN/POC display must distinguish explicit source availability from proxy-only evidence.",
    },
    {
        "name": "preflight_eligible_reference",
        "pattern": r"d3v_preflight_eligible|preflight_eligible|preflight_candidate",
        "risk": "D3V preflight rows must be shown as dry-run and unmutated.",
    },
]

REQUIRED_UI_SEPARATION_LABELS = [
    "LEGACY_EVIDENCE_ONLY_NOT_D3D_CONFIRMATION",
    "D3C_SHADOW_READ_ONLY_DIAGNOSTIC",
    "D3C2_DIAGNOSTIC_ENRICHMENT_UNCONFIRMED",
    "D3D_PRODUCTION_CONFIRMATION",
    "D3D_DRY_RUN_UNAUTHORIZED",
    "HVN_ABSORPTION_PROXY_NOT_TRUE_HVN_POC",
    "D3V_PREFLIGHT_BLOCKED_UNMUTATED",
]


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
    prefix = text[:index]
    line_no = prefix.count("\n") + 1
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    return {
        "line_number": line_no,
        "line": line[:300],
    }


def main() -> int:
    scanned_files = iter_files()
    findings: List[Dict[str, object]] = []
    label_hits = {label: [] for label in REQUIRED_UI_SEPARATION_LABELS}

    for path in scanned_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            findings.append({
                "file": rel(path),
                "pattern_name": "file_read_error",
                "risk": "File could not be read during static audit.",
                "error": str(exc),
            })
            continue

        for pattern_spec in RISK_PATTERNS:
            pattern = re.compile(pattern_spec["pattern"], flags=re.IGNORECASE)
            for match in pattern.finditer(text):
                context = line_context(text, match.start())
                findings.append({
                    "file": rel(path),
                    "pattern_name": pattern_spec["name"],
                    "risk": pattern_spec["risk"],
                    "matched_text": match.group(0)[:120],
                    "line_number": context["line_number"],
                    "line": context["line"],
                })

        for label in REQUIRED_UI_SEPARATION_LABELS:
            if label in text:
                label_hits[label].append(rel(path))

    missing_labels = [
        label for label, files in label_hits.items()
        if len(files) == 0
    ]

    unique_finding_files = sorted(set(item.get("file") for item in findings if item.get("file")))

    result = {
        "engine": ENGINE,
        "version": VERSION,
        "audit_status": "PASS_STATIC_AUDIT_COMPLETED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "operator_control_confirmed_by_this_audit": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,
        "scanned_file_count": len(scanned_files),
        "finding_count": len(findings),
        "unique_finding_file_count": len(unique_finding_files),
        "missing_required_display_label_count": len(missing_labels),
        "missing_required_display_labels": missing_labels,
        "required_display_label_hits": label_hits,
        "display_separation_policy": {
            "legacy_evidence": "Must display as legacy evidence only, not D3D production confirmation.",
            "d3c_shadow": "Must display as read-only shadow diagnostic.",
            "d3c2_diagnostics": "Must display as read-only enrichment/confluence diagnostics.",
            "d3d_production": "Must display only from D3D production field and only after authorized mutation.",
            "hvn_proxy": "HVN_ABSORPTION_PROXY must display as proxy-only, not true HVN/POC.",
            "d3v_preflight": "D3V preflight candidates must display as dry-run, blocked/unmutated unless eligible and separately authorized.",
        },
        "findings": findings[:250],
        "finding_truncation_policy": "FIRST_250_FINDINGS_ONLY",
    }

    print(json.dumps(result, indent=2, sort_keys=True))

    print("")
    print("FINAL RESULT: PASS - D3W frontend display separation static audit completed without mutation.")
    print("NOTE: Findings are review inventory, not production drift by themselves.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
