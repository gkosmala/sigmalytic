"""
Sigmalytic V2 — Campaign Pipeline Universe Snapshot Contract.

This contract is intentionally non-mutating.

It does not call external data providers.
It does not call any database.
It does not run the nightly pipeline.
It does not write to any database.
It does not mutate campaigns.
It does not authorize D3D.
It does not confirm operator control.
It does not create trade signals.
It does not touch billing.

Purpose:
    Represent the universe-source status discovered by read-only audits.

Important:
    Absence of a persisted universe table is not treated as success.
    A bars-symbol universe proxy may be reported as diagnostic evidence only,
    but it cannot be silently promoted into a live universe count.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CONTRACT_VERSION = "SIGMALYTIC_V2_NON_MUTATING_UNIVERSE_SNAPSHOT_CONTRACT_2026_07_09"

UNIVERSE_SOURCE_STATUS = {
    "persisted_universe_table_required_for_full_validation": True,
    "persisted_universe_table_confirmed": False,
    "external_live_universe_call_allowed": False,
    "bars_symbol_universe_proxy_allowed_as_diagnostic_only": True,
    "bars_symbol_universe_proxy_can_replace_live_universe": False,
}


def build_non_mutating_universe_snapshot(
    *,
    persisted_universe_table: str | None = None,
    persisted_universe_count: int | None = None,
    bars_symbol_count: int | None = None,
    campaign_symbol_count: int | None = None,
    locator_status: str | None = None,
    locator_recommendation_status: str | None = None,
) -> dict[str, Any]:
    persisted_universe_available = bool(
        persisted_universe_table
        and isinstance(persisted_universe_count, int)
        and persisted_universe_count > 0
    )

    bars_symbol_universe_proxy_available = bool(
        isinstance(bars_symbol_count, int)
        and bars_symbol_count > 0
    )

    full_universe_validation_complete = bool(
        persisted_universe_available
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "NON_MUTATING_UNIVERSE_SNAPSHOT_CONTRACT_NO_DB_CALL_NO_EXTERNAL_UNIVERSE_CALL_NO_WRITE",
        "locator_status": locator_status,
        "locator_recommendation_status": locator_recommendation_status,

        "persisted_universe_available": persisted_universe_available,
        "persisted_universe_table": persisted_universe_table,
        "persisted_universe_count": persisted_universe_count,

        "bars_symbol_universe_proxy_available": bars_symbol_universe_proxy_available,
        "bars_symbol_count": bars_symbol_count,
        "campaign_symbol_count": campaign_symbol_count,

        "full_universe_validation_complete": full_universe_validation_complete,
        "readiness_can_advance": False,
        "reason": (
            "A persisted universe table/count is required for full campaign pipeline validation. "
            "Bars-symbol coverage is useful diagnostic evidence but is not silently promoted "
            "into a live universe source."
        ),
        "source_status": dict(UNIVERSE_SOURCE_STATUS),
        "doctrine": {
            "non_mutating_contract_only": True,
            "no_database_call": True,
            "no_external_universe_call": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_nightly_run": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
            "billing_remains_blocked": True,
        },
    }


__all__ = [
    "CONTRACT_VERSION",
    "UNIVERSE_SOURCE_STATUS",
    "build_non_mutating_universe_snapshot",
]
