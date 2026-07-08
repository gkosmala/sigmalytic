from backend.alerts.controlled_persistence_post_write_closure_sweep import (
    EXPECTED_AUDIT_COMPONENT,
    EXPECTED_AUDIT_VERSION,
    EXPECTED_D3D_STATUS,
    EXPECTED_INSERTED_ROW_ID,
    EXPECTED_OPERATOR_CONTROL_STATUS,
    EXPECTED_SYMBOL,
    build_d3e8_post_persistence_closure_sweep_payload,
    validate_d3e8_closure_row,
)


def assert_read_only_guardrails(payload):
    assert payload["writes_to_supabase"] is False
    assert payload["supabase_write_authorized"] is False
    assert payload["persistence_write_authorized"] is False
    assert payload["mutates_campaigns"] is False
    assert payload["executes_d3d"] is False
    assert payload["authorizes_d3d"] is False
    assert payload["operator_control_confirmed"] is False
    assert payload["composite_operator_control_confirmed"] is False
    assert payload["not_a_trade_signal"] is True
    assert payload["touches_stripe"] is False


def test_dry_run_closure_preview_does_not_read_or_write():
    payload = build_d3e8_post_persistence_closure_sweep_payload(execute_live_read=False)
    assert payload["ok"] is True
    assert payload["route_is_mounted"] is True
    assert payload["read_only"] is True
    assert payload["read_attempted"] is False
    assert payload["read_status"] == "DRY_RUN_CLOSURE_PREVIEW_ONLY"
    assert payload["closure_verified"] is False
    assert_read_only_guardrails(payload)


def test_expected_closure_row_validates():
    row = {
        "id": EXPECTED_INSERTED_ROW_ID,
        "created_at": "2026-07-08T20:14:51.90562+00:00",
        "symbol": EXPECTED_SYMBOL,
        "audit_component": EXPECTED_AUDIT_COMPONENT,
        "audit_version": EXPECTED_AUDIT_VERSION,
        "operator_control_evidence_audit_status": EXPECTED_OPERATOR_CONTROL_STATUS,
        "d3d_dry_run_gate_audit_status": EXPECTED_D3D_STATUS,
    }

    result = validate_d3e8_closure_row(row)

    assert result["row_found"] is True
    assert result["closure_verified"] is True
    assert result["closure_status"] == "D3E8_POST_PERSISTENCE_CLOSURE_VERIFIED_READ_ONLY"
    assert result["inserted_row_id"] == EXPECTED_INSERTED_ROW_ID
    assert all(result["expected_checks"].values())


def test_missing_row_fails_closure():
    result = validate_d3e8_closure_row(None)
    assert result["row_found"] is False
    assert result["closure_verified"] is False
    assert result["closure_status"] == "D3E8_EXPECTED_CONTROLLED_AUDIT_ROW_NOT_FOUND"


def test_wrong_row_fails_closure():
    row = {
        "id": 999,
        "symbol": "WRONG",
        "audit_component": EXPECTED_AUDIT_COMPONENT,
        "audit_version": EXPECTED_AUDIT_VERSION,
        "operator_control_evidence_audit_status": EXPECTED_OPERATOR_CONTROL_STATUS,
        "d3d_dry_run_gate_audit_status": EXPECTED_D3D_STATUS,
    }

    result = validate_d3e8_closure_row(row)

    assert result["row_found"] is True
    assert result["closure_verified"] is False
    assert result["closure_status"] == "D3E8_CONTROLLED_AUDIT_ROW_FOUND_BUT_FIELD_MISMATCH"


if __name__ == "__main__":
    test_dry_run_closure_preview_does_not_read_or_write()
    test_expected_closure_row_validates()
    test_missing_row_fails_closure()
    test_wrong_row_fails_closure()
    print("CONTROLLED_PERSISTENCE_POST_WRITE_CLOSURE_SWEEP_TESTS_PASS")
