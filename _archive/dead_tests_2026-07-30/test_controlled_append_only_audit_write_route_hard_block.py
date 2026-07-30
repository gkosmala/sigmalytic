from backend.alerts.controlled_append_only_audit_write_route import (
    FUTURE_D3E6_CONFIRMATION_PHRASE,
    build_controlled_append_only_audit_write_route_payload,
)


def assert_hard_blocked(payload):
    assert payload["ok"] is True
    assert payload["target_table"] == "alert_readiness_audit_events"
    assert payload["route_is_mounted"] is True
    assert payload["execution_blocked"] is True
    assert payload["dry_run_only"] is True
    assert payload["d3e6_required_before_any_write"] is True

    assert payload["writes_to_supabase"] is False
    assert payload["supabase_write_authorized"] is False
    assert payload["persistence_write_authorized"] is False

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


def test_default_payload_is_hard_blocked():
    payload = build_controlled_append_only_audit_write_route_payload({})
    assert_hard_blocked(payload)
    assert payload["future_confirmation_phrase_recognized"] is False


def test_future_phrase_is_recognized_but_still_blocked_in_d3e5():
    payload = build_controlled_append_only_audit_write_route_payload(
        {"confirmation_phrase": FUTURE_D3E6_CONFIRMATION_PHRASE}
    )
    assert_hard_blocked(payload)
    assert payload["future_confirmation_phrase_recognized"] is True


if __name__ == "__main__":
    test_default_payload_is_hard_blocked()
    test_future_phrase_is_recognized_but_still_blocked_in_d3e5()
    print("CONTROLLED_APPEND_ONLY_AUDIT_WRITE_ROUTE_HARD_BLOCK_TESTS_PASS")
