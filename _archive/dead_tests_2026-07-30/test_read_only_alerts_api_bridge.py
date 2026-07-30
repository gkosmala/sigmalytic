import sys
import types
if "fastapi" not in sys.modules:
    fastapi_stub = types.ModuleType("fastapi")
    class APIRouter:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    def Body(default=None, *args, **kwargs):
        return default
    fastapi_stub.APIRouter = APIRouter
    fastapi_stub.Body = Body
    sys.modules["fastapi"] = fastapi_stub
from backend.alerts_api import read_only_alert_review, read_only_alert_status
def make_bars(count=20, start=100.0, step=1.0):
    bars = []
    price = start
    for i in range(count):
        open_price = price
        close = price + step
        bars.append(
            {
                "timestamp_utc": f"2026-07-07T14:{i:02d}:00Z",
                "open": open_price,
                "high": close + 0.25,
                "low": open_price - 0.25,
                "close": close,
                "volume": 1000 + i,
            }
        )
        price = close
    return bars
def explicit_source():
    return {
        "symbol": "TEST",
        "level_type": "EXPLICIT_SUPPORT_ZONE",
        "price_low": 100.0,
        "price_mid": 110.0,
        "price_high": 125.0,
        "source_method": "SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT",
        "source_reference": "api-bridge-unit-test-explicit-source",
        "is_explicit": True,
        "is_inferred": False,
        "is_proxy": False,
    }
def proxy_source():
    return {
        "symbol": "TEST",
        "level_type": "PROXY_ZONE",
        "price_low": 100.0,
        "price_mid": 110.0,
        "price_high": 125.0,
        "source_method": "OHLCV_DERIVED_PROFILE_APPROXIMATION",
        "source_reference": "api-bridge-unit-test-proxy-source",
        "is_explicit": False,
        "is_inferred": True,
        "is_proxy": True,
    }
def test_status_endpoint_remains_no_drift():
    result = read_only_alert_status()
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["not_a_trade_signal"] is True
    assert result["guardrails"]["writes_to_supabase"] is False
    assert result["guardrails"]["mutates_campaigns"] is False
    assert result["guardrails"]["executes_d3d"] is False
    assert result["guardrails"]["authorizes_d3d"] is False
def test_review_endpoint_valid_explicit_source_is_diagnostic_only():
    result = read_only_alert_review(
        {
            "symbol": "TEST",
            "bars": make_bars(),
            "structural_source": explicit_source(),
        }
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
    review = result["review"]
    assert review["operator_control_confirmed"] is False
    assert review["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert review["alert_c"]["verdict"] == "WATCHLIST_CONFIRMING_DEMAND"
def test_review_endpoint_proxy_source_is_blocked():
    result = read_only_alert_review(
        {
            "symbol": "TEST",
            "bars": make_bars(),
            "structural_source": proxy_source(),
        }
    )
    assert result["ok"] is True
    assert result["operator_control_confirmed"] is False
    assert result["d3d_execution_recommendation"] == "DO_NOT_EXECUTE_D3D"
    assert result["review"]["alert_b"]["bias"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
    assert result["review"]["alert_c"]["verdict"] == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
if __name__ == "__main__":
    test_status_endpoint_remains_no_drift()
    test_review_endpoint_valid_explicit_source_is_diagnostic_only()
    test_review_endpoint_proxy_source_is_blocked()
    print("ALERT_API_BRIDGE_MANUAL_TESTS_PASS")
