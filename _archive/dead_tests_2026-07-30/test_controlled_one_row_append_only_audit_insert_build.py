from backend.alerts.controlled_one_row_append_only_audit_insert import (
    D3E6_AUTHORIZATION_PHRASE,
    build_d3e6_audit_row,
    build_d3e6_readiness_payload,
    execute_d3e6_controlled_one_row_insert,
)


def assert_no_doctrine_drift(payload):
    assert payload["mutates_campaigns"] is False
    assert payload["executes_d3d"] is False
    assert payload["authorizes_d3d"] is False
    assert payload["operator_control_confirmed"] is False
    assert payload["composite_operator_control_confirmed"] is False
    assert payload["not_a_trade_signal"] is True
    assert payload["changes_scores"] is False
    assert payload["changes_ranks"] is False
    assert payload["changes_states"] is False
    assert payload["changes_probabilities"] is False
    assert payload["changes_edge"] is False
    assert payload["touches_stripe"] is False


def test_readiness_does_not_write():
    payload = build_d3e6_readiness_payload()
    assert payload["ok"] is True
    assert payload["route_is_mounted"] is True
    assert payload["writes_to_supabase"] is False
    assert payload["supabase_write_authorized"] is False
    assert payload["persistence_write_authorized"] is False
    assert_no_doctrine_drift(payload)


def test_audit_row_contains_only_audit_status_not_campaign_mutation():
    row = build_d3e6_audit_row({"symbol": "D3E6_TEST"})
    assert row["symbol"] == "D3E6_TEST"
    assert row["audit_component"] == "controlled_one_row_append_only_audit_insert"
    assert row["audit_version"] == "D3E.6"
    assert row["operator_control_evidence_audit_status"] == "NOT_OPERATOR_CONTROL_CONFIRMATION"
    assert row["d3d_dry_run_gate_audit_status"] == "D3D_NOT_AUTHORIZED_NOT_EXECUTED"
    assert row["payload"]["one_row_only"] is True
    assert row["payload"]["append_only"] is True


def test_missing_phrase_blocks_insert():
    payload = execute_d3e6_controlled_one_row_insert({"dry_run": False})
    assert payload["authorization_phrase_recognized"] is False
    assert payload["writes_to_supabase"] is False
    assert payload["supabase_write_authorized"] is False
    assert payload["persistence_write_authorized"] is False
    assert payload["insert_attempted"] is False
    assert payload["insert_status"] == "NOT_ATTEMPTED"
    assert_no_doctrine_drift(payload)


def test_exact_phrase_with_dry_run_still_does_not_insert():
    payload = execute_d3e6_controlled_one_row_insert(
        {
            "authorization_phrase": D3E6_AUTHORIZATION_PHRASE,
            "dry_run": True,
            "symbol": "D3E6_TEST",
        }
    )
    assert payload["authorization_phrase_recognized"] is True
    assert payload["writes_to_supabase"] is False
    assert payload["supabase_write_authorized"] is False
    assert payload["persistence_write_authorized"] is False
    assert payload["insert_attempted"] is False
    assert payload["insert_status"] == "DRY_RUN_ONLY"
    assert_no_doctrine_drift(payload)


if __name__ == "__main__":
    test_readiness_does_not_write()
    test_audit_row_contains_only_audit_status_not_campaign_mutation()
    test_missing_phrase_blocks_insert()
    test_exact_phrase_with_dry_run_still_does_not_insert()
    print("CONTROLLED_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_BUILD_TESTS_PASS")
