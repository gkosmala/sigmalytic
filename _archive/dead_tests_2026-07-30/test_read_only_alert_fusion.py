from backend.alerts import (
    Bar,
    ExplicitStructuralSource,
    GUARDRAILS,
    assert_no_drift_guardrails,
    run_read_only_alert_review,
)


def make_bars(count=20, start=100.0, step=1.0):
    bars = []
    price = start
    for i in range(count):
        open_price = price
        close = price + step
        high = close + 0.25
        low = open_price - 0.25
        bars.append(
            Bar(
                timestamp_utc=f"2026-07-07T13:{i:02d}:00Z",
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=1000 + i,
            )
        )
        price = close
    return bars


def test_guardrails_remain_no_drift():
    assert_no_drift_guardrails()
    assert GUARDRAILS["writes_to_supabase"] is False
    assert GUARDRAILS["mutates_campaigns"] is False
    assert GUARDRAILS["executes_d3d"] is False
    assert GUARDRAILS["authorizes_d3d"] is False
    assert GUARDRAILS["operator_control_confirmed"] is False
    assert GUARDRAILS["not_a_trade_signal"] is True
    assert GUARDRAILS["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"


def test_valid_explicit_source_returns_watchlist_not_confirmation():
    source = ExplicitStructuralSource(
        symbol="TEST",
        level_type="EXPLICIT_SUPPORT_ZONE",
        price_low=100.0,
        price_mid=110.0,
        price_high=125.0,
        source_method="SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT",
        source_reference="unit-test-explicit-source",
        is_explicit=True,
        is_inferred=False,
        is_proxy=False,
    )

    result = run_read_only_alert_review("TEST", make_bars(), source)

    assert result["alert_a"]["bias"] == "IMMEDIATE_DEMAND"
    assert result["alert_b"]["bias"] == "CAMPAIGN_CONSTRUCTIVE"
    assert result["alert_c"]["verdict"] == "WATCHLIST_CONFIRMING_DEMAND"
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"


def test_proxy_source_is_blocked():
    source = ExplicitStructuralSource(
        symbol="TEST",
        level_type="PROXY_ZONE",
        price_low=100.0,
        price_mid=110.0,
        price_high=125.0,
        source_method="OHLCV_DERIVED_PROFILE_APPROXIMATION",
        source_reference="unit-test-proxy-source",
        is_explicit=False,
        is_inferred=True,
        is_proxy=True,
    )

    result = run_read_only_alert_review("TEST", make_bars(), source)

    assert result["alert_b"]["bias"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
    assert result["alert_c"]["verdict"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
    assert result["operator_control_confirmed"] is False


if __name__ == "__main__":
    test_guardrails_remain_no_drift()
    test_valid_explicit_source_returns_watchlist_not_confirmation()
    test_proxy_source_is_blocked()
    print("MANUAL_TESTS_PASS")
