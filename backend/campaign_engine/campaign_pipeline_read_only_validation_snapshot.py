"""
Sigmalytic V2 — Campaign Pipeline Read-Only Validation Snapshot.

Step 26E installs this as a module-only contract.

It does not install a route.
It does not run the nightly pipeline.
It does not call Alpaca.
It does not write Supabase.
It does not mutate campaigns.
It does not authorize D3D.
It does not confirm operator control.
It does not create trade signals.
It does not touch Stripe.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_CAMPAIGN_PIPELINE_READ_ONLY_SNAPSHOT_2026_07_09"

REQUIRED_SNAPSHOT_FIELDS = (
    "universe_count",
    "bars_symbols_count",
    "symbols_missing_bars",
    "record_min_bars",
    "pagination_complete",
    "schema_payload_alignment",
    "write_path_not_executed_during_validation",
)

SOURCE_FILES = (
    "backend/campaign_engine/nightly_campaign_pipeline.py",
    "backend/campaign_engine/campaign_discovery_engine.py",
    "backend/campaign_engine/campaign_store.py",
    "backend/campaign_api.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _combined_source() -> str:
    root = _repo_root()
    return "\n".join(_read_source(root / rel).lower() for rel in SOURCE_FILES)


def _source_presence() -> dict[str, bool]:
    combined = _combined_source()

    return {
        "universe_binding_present": "universe" in combined,
        "alpaca_or_bar_binding_present": "alpaca" in combined or "bars" in combined,
        "campaign_evaluation_present": "campaign" in combined and ("evaluate" in combined or "discovery" in combined),
        "schema_payload_terms_present": "payload" in combined and "schema" in combined,
        "supabase_reference_present": "supabase" in combined,
    }


def build_campaign_pipeline_read_only_validation_snapshot() -> dict[str, Any]:
    source_presence = _source_presence()

    schema_payload_alignment = bool(
        source_presence["campaign_evaluation_present"]
        and source_presence["schema_payload_terms_present"]
        and source_presence["supabase_reference_present"]
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "MODULE_ONLY_READ_ONLY_DIAGNOSTIC_NO_ROUTE_NO_NIGHTLY_RUN_NO_WRITE",
        "validation_complete": False,
        "readiness_can_advance": False,
        "reason": (
            "Module-only read-only snapshot builder is installed. "
            "A live GET route is not installed in this step. "
            "Production coverage counts are not confirmed."
        ),
        "universe_count": None,
        "bars_symbols_count": None,
        "symbols_missing_bars": [],
        "record_min_bars": None,
        "pagination_complete": False,
        "schema_payload_alignment": schema_payload_alignment,
        "write_path_not_executed_during_validation": True,
        "source_presence": source_presence,
        "required_snapshot_fields": list(REQUIRED_SNAPSHOT_FIELDS),
        "doctrine": {
            "module_only": True,
            "get_only_route_not_installed_yet": True,
            "no_nightly_run": True,
            "no_alpaca_call_from_this_module": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "campaign_pipeline_validated_remains_false": True,
        },
    }


__all__ = [
    "CONTRACT_VERSION",
    "REQUIRED_SNAPSHOT_FIELDS",
    "build_campaign_pipeline_read_only_validation_snapshot",
]
