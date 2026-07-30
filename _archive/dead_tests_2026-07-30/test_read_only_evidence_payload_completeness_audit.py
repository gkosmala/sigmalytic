from __future__ import annotations
from backend.alerts.evidence_payload_completeness_audit import (
    build_read_only_evidence_payload_completeness_from_source_coverage,
)
def test_evidence_payload_completeness_blocks_without_source_coverage_no_drift():
    coverage = {
        "source_coverage_completion_status": "SOURCE_COVERAGE_INCOMPLETE_READ_ONLY",
        "coverage_is_complete": False,
        "requested_symbols": ["SPY", "QQQ"],
        "requested_symbol_count": 2,
        "audited_symbol_count": 2,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "coverage_rows": [
            {"symbol": "SPY", "coverage_complete": True, "coverage_blockers": []},
            {
                "symbol": "QQQ",
                "coverage_complete": False,
                "coverage_blockers": ["EXPLICIT_STRUCTURAL_SOURCE_COVERAGE_MISSING_READ_ONLY"],
            },
        ],
    }
    result = build_read_only_evidence_payload_completeness_from_source_coverage(
        coverage=coverage,
    )
    assert result["ok"] is True
    assert result["component"] == "EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_READ_ONLY"
    assert result["diagnostic_only"] is True
    assert result["read_only"] is True
    assert result["writes_to_supabase"] is False
    assert result["mutates_campaigns"] is False
    assert result["executes_d3d"] is False
    assert result["authorizes_d3d"] is False
    assert result["operator_control_confirmed"] is False
    assert result["not_a_trade_signal"] is True
    assert result["changes_scores"] is False
    assert result["changes_ranks"] is False
    assert result["changes_states"] is False
    assert result["changes_probabilities"] is False
    assert result["changes_edge"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
    assert result["evidence_payload_completeness_status"] == "EVIDENCE_PAYLOAD_INCOMPLETE_OR_BLOCKED_READ_ONLY"
    assert result["evidence_payload_missing_symbols"] == ["SPY"]
    assert result["evidence_payload_blocked_by_coverage_symbols"] == ["QQQ"]
    assert result["evidence_audit_applies_no_changes"] is True
    assert result["evidence_audit_is_read_only"] is True
def test_evidence_payload_completeness_complete_when_required_families_present_no_drift():
    evidence_payload = {
        "wyckoff_evidence": {},
        "livermore_evidence": {},
        "weis_evidence": {},
        "tested_supply_exhaustion": {},
        "active_demand_support_validation": {},
        "structurally_meaningful_location": {
            "prior_resistance_or_supply_zone": {},
            "base_or_range_context": {},
            "breakout_or_spring_location": {},
            "volume_price_context": {},
            "multi_timeframe_alignment_context": {},
        },
        "absence_of_contrary_failure": {},
    }
    coverage = {
        "source_coverage_completion_status": "SOURCE_COVERAGE_COMPLETE_READ_ONLY",
        "coverage_is_complete": True,
        "requested_symbols": ["SPY"],
        "requested_symbol_count": 1,
        "audited_symbol_count": 1,
        "guardrail_failure_count": 0,
        "guardrail_failures": [],
        "coverage_rows": [
            {
                "symbol": "SPY",
                "coverage_complete": True,
                "coverage_blockers": [],
                "evidence_payload": evidence_payload,
            },
        ],
    }
    result = build_read_only_evidence_payload_completeness_from_source_coverage(
        coverage=coverage,
    )
    assert result["evidence_payload_completeness_status"] == "EVIDENCE_PAYLOAD_COMPLETE_READ_ONLY"
    assert result["evidence_payload_complete_symbols"] == ["SPY"]
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["can_execute_d3d"] is False
if __name__ == "__main__":
    test_evidence_payload_completeness_blocks_without_source_coverage_no_drift()
    test_evidence_payload_completeness_complete_when_required_families_present_no_drift()
    print("EVIDENCE_PAYLOAD_COMPLETENESS_AUDIT_MANUAL_TESTS_PASS")
