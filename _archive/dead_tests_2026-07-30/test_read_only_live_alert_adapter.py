from __future__ import annotations
import json
from pathlib import Path
from backend.alerts.live_data_adapter import run_read_only_live_alert_review
ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = ROOT / "runtime_sources" / "explicit_sml_runtime_source.json"
def _sample_bars():
    bars = []
    price = 720.0
    for i in range(20):
        open_price = price
        close_price = price + 1.0
        bars.append(
            {
                "timestamp": f"2026-07-07T14:{i:02d}:00Z",
                "open": open_price,
                "high": close_price + 0.25,
                "low": open_price - 0.25,
                "close": close_price,
                "volume": 1000 + i,
            }
        )
        price = close_price
    return bars
def test_payload_bars_and_runtime_explicit_source_review():
    payload = json.loads(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    result = run_read_only_live_alert_review(
        symbol="SPY",
        requested_timeframe="1Min",
        lookback_bars=20,
        minimum_usable_bars=20,
        candidate_payload={
            "bars": _sample_bars(),
            "explicit_sml_records": payload["explicit_sml_records"],
        },
    )
    assert result["ok"] is True
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
    assert result["guardrail_failure_count"] == 0
    assert result["bar_adapter"]["adapter_status"] == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
    assert result["explicit_source_adapter"]["adapter_status"] == "SRC7B_OK_VALID_EXPLICIT_SML_RECORDS_LOADED_READ_ONLY"
    assert result["review"]["alert_c"]["verdict"] == "WATCHLIST_CONFIRMING_DEMAND"
def test_no_matching_explicit_source_blocks_confirmation():
    result = run_read_only_live_alert_review(
        symbol="NOPE",
        requested_timeframe="1Min",
        lookback_bars=20,
        minimum_usable_bars=20,
        candidate_payload={
            "bars": _sample_bars(),
        },
    )
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["bar_adapter"]["adapter_status"] == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
    assert result["explicit_source_available"] is False
    assert result["review"]["alert_b"]["bias"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
    assert result["review"]["alert_c"]["verdict"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
if __name__ == "__main__":
    test_payload_bars_and_runtime_explicit_source_review()
    test_no_matching_explicit_source_blocks_confirmation()
    print("ALERT_LIVE_DATA_ADAPTER_MANUAL_TESTS_PASS")
