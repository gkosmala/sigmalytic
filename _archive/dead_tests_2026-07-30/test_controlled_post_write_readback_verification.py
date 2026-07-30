from backend.alerts.controlled_post_write_readback_verification import (
    EXPECTED_AUDIT_COMPONENT,
    EXPECTED_AUDIT_VERSION,
    EXPECTED_D3D_STATUS,
    EXPECTED_OPERATOR_CONTROL_STATUS,
    EXPECTED_SYMBOL,
    build_d3e7_post_write_readback_verification_payload,
    validate_d3e7_readback_row,
)


def assert_no_write_or_doctrine_drift(payload):
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


def test_dry_run_read_preview_does_not_read_or_write():
    payload = build_d3e7_post_write_readback_verification_payload(execute_live_read=False)
    assert payload["ok"] is True
    assert payload["route_is_mounted"] is True
    assert payload["read_only"] is True
    assert payload["read_attempted"] is False
    assert payload["read_status"] == "DRY_RUN_READ_PREVIEW_ONLY"
    assert_no_write_or_doctrine_drift(payload)


def test_expected_row_validates():
    row = {
        "id": 1,
        "created_at": "2026-07-08T20:14:51.90562+00:00",
        "symbol": EXPECTED_SYMBOL,
        "audit_component": EXPECTED_AUDIT_COMPONENT,
        "audit_version": EXPECTED_AUDIT_VERSION,
        "operator_control_evidence_audit_status": EXPECTED_OPERATOR_CONTROL_STATUS,
        "d3d_dry_run_gate_audit_status": EXPECTED_D3D_STATUS,
    }
    result = validate_d3e7_readback_row(row)
    assert result["row_found"] is True
    assert result["readback_verified"] is True
    assert result["readback_verification_status"] == "D3E7_POST_WRITE_READBACK_VERIFIED"
    assert result["inserted_row_id"] == 1


def test_missing_row_does_not_validate():
    result = validate_d3e7_readback_row(None)
    assert result["row_found"] is False
    assert result["readback_verified"] is False
    assert result["readback_verification_status"] == "D3E7_EXPECTED_AUDIT_ROW_NOT_FOUND"


def test_wrong_row_does_not_validate():
    row = {
        "id": 2,
        "symbol": "WRONG",
        "audit_component": EXPECTED_AUDIT_COMPONENT,
        "audit_version": EXPECTED_AUDIT_VERSION,
        "operator_control_evidence_audit_status": EXPECTED_OPERATOR_CONTROL_STATUS,
        "d3d_dry_run_gate_audit_status": EXPECTED_D3D_STATUS,
    }
    result = validate_d3e7_readback_row(row)
    assert result["row_found"] is True
    assert result["readback_verified"] is False
    assert result["readback_verification_status"] == (
        "D3E7_POST_WRITE_READBACK_ROW_FOUND_BUT_FIELD_MISMATCH"
    )


if __name__ == "__main__":
    test_dry_run_read_preview_does_not_read_or_write()
    test_expected_row_validates()
    test_missing_row_does_not_validate()
    test_wrong_row_does_not_validate()
    print("CONTROLLED_POST_WRITE_READBACK_VERIFICATION_TESTS_PASS")
