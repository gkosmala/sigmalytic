from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable, Optional


GUARDRAILS = {
    "diagnostic_only": True,
    "read_only": True,
    "writes_to_supabase": False,
    "mutates_campaigns": False,
    "executes_d3d": False,
    "authorizes_d3d": False,
    "operator_control_confirmed": False,
    "not_a_trade_signal": True,
    "changes_scores": False,
    "changes_ranks": False,
    "changes_states": False,
    "changes_probabilities": False,
    "changes_edge": False,
    "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
}


@dataclass(frozen=True)
class Bar:
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ExplicitStructuralSource:
    symbol: str
    level_type: str
    price_low: float
    price_mid: float
    price_high: float
    source_method: str
    source_reference: str
    is_explicit: bool
    is_inferred: bool = False
    is_proxy: bool = False


def assert_no_drift_guardrails() -> None:
    must_be_false = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed",
        "changes_scores",
        "changes_ranks",
        "changes_states",
        "changes_probabilities",
        "changes_edge",
    ]

    for key in must_be_false:
        if GUARDRAILS.get(key) is not False:
            raise RuntimeError(f"NO-DRIFT FAILURE: {key} must remain False")

    must_be_true = [
        "diagnostic_only",
        "read_only",
        "not_a_trade_signal",
    ]

    for key in must_be_true:
        if GUARDRAILS.get(key) is not True:
            raise RuntimeError(f"NO-DRIFT FAILURE: {key} must remain True")

    if GUARDRAILS.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        raise RuntimeError("NO-DRIFT FAILURE: D3D must remain blocked")


def close_location(bar: Bar) -> float:
    spread = max(float(bar.high) - float(bar.low), 1e-9)
    return (float(bar.close) - float(bar.low)) / spread


def evaluate_alert_a_immediate_20_bar_tape(symbol: str, bars: Iterable[Bar]) -> dict:
    assert_no_drift_guardrails()

    window = list(bars)[-20:]

    if len(window) < 20:
        return {
            "alert": "ALERT_A",
            "symbol": symbol,
            "bias": "INSUFFICIENT_DATA",
            "lookback_bars": len(window),
            "contrary_warning_active": False,
            "guardrails": GUARDRAILS,
            "explanation": ["Fewer than 20 bars supplied."],
        }

    closes = [float(b.close) for b in window]
    volumes = [max(float(b.volume), 0.0) for b in window]
    locations = [close_location(b) for b in window]

    progress = closes[-1] - closes[0]
    strong_closes = sum(1 for x in locations if x >= 0.70)
    weak_closes = sum(1 for x in locations if x <= 0.30)

    avg_volume = sum(volumes) / len(volumes)
    latest_elevated_volume = volumes[-1] > (1.25 * avg_volume)
    latest_weak_finish = locations[-1] <= 0.35

    contrary_warning_active = bool(
        latest_elevated_volume
        and latest_weak_finish
        and progress <= 0
    )

    if contrary_warning_active:
        bias = "CONTRARY_WARNING"
    elif progress > 0 and strong_closes >= weak_closes:
        bias = "IMMEDIATE_DEMAND"
    elif progress < 0 and weak_closes >= strong_closes:
        bias = "IMMEDIATE_SUPPLY"
    else:
        bias = "NEUTRAL_TEST"

    return {
        "alert": "ALERT_A",
        "symbol": symbol,
        "bias": bias,
        "lookback_bars": 20,
        "progress_20_bar": progress,
        "strong_closes": strong_closes,
        "weak_closes": weak_closes,
        "latest_close_location": locations[-1],
        "latest_elevated_volume": latest_elevated_volume,
        "contrary_warning_active": contrary_warning_active,
        "guardrails": GUARDRAILS,
        "explanation": [
            f"20-bar progress = {progress:.4f}.",
            f"Strong closes = {strong_closes}; weak closes = {weak_closes}.",
            f"Latest close location = {locations[-1]:.2f}; elevated volume = {latest_elevated_volume}.",
        ],
    }


def source_is_valid_explicit_structural_source(source: Optional[ExplicitStructuralSource]) -> bool:
    if source is None:
        return False
    if not source.is_explicit:
        return False
    if source.is_inferred:
        return False
    if source.is_proxy:
        return False
    if source.price_low > source.price_mid:
        return False
    if source.price_mid > source.price_high:
        return False
    return True


def evaluate_alert_b_campaign_context(
    symbol: str,
    latest_price: float,
    source: Optional[ExplicitStructuralSource],
    contrary_warning_active: bool,
) -> dict:
    assert_no_drift_guardrails()

    if not source_is_valid_explicit_structural_source(source):
        return {
            "alert": "ALERT_B",
            "symbol": symbol,
            "bias": "SOURCE_BLOCKED_DIAGNOSTIC_ONLY",
            "explicit_source_available": False,
            "price_inside_explicit_range": None,
            "price_position_vs_midpoint": None,
            "guardrails": GUARDRAILS,
            "explanation": ["No valid explicit structural source is available."],
        }

    assert source is not None

    inside_range = source.price_low <= latest_price <= source.price_high
    position = "BELOW_MIDPOINT" if latest_price < source.price_mid else "ABOVE_OR_AT_MIDPOINT"

    if contrary_warning_active:
        bias = "DISTRIBUTION_RISK"
    elif inside_range:
        bias = "CAMPAIGN_CONSTRUCTIVE"
    else:
        bias = "CAMPAIGN_NEUTRAL"

    return {
        "alert": "ALERT_B",
        "symbol": symbol,
        "bias": bias,
        "explicit_source_available": True,
        "explicit_source": asdict(source),
        "latest_price": latest_price,
        "price_inside_explicit_range": inside_range,
        "price_position_vs_midpoint": position,
        "guardrails": GUARDRAILS,
        "explanation": [
            "Valid explicit structural source present.",
            f"Inside explicit range = {inside_range}.",
            f"Position vs midpoint = {position}.",
        ],
    }


def evaluate_alert_c_read_only_fusion(symbol: str, alert_a: dict, alert_b: dict) -> dict:
    assert_no_drift_guardrails()

    immediate_bias = alert_a.get("bias")
    campaign_bias = alert_b.get("bias")

    if campaign_bias == "SOURCE_BLOCKED_DIAGNOSTIC_ONLY":
        verdict = "SOURCE_BLOCKED_DIAGNOSTIC_ONLY"
    elif immediate_bias == "IMMEDIATE_DEMAND" and campaign_bias == "CAMPAIGN_CONSTRUCTIVE":
        verdict = "WATCHLIST_CONFIRMING_DEMAND"
    elif immediate_bias in {"IMMEDIATE_SUPPLY", "CONTRARY_WARNING"} and campaign_bias == "CAMPAIGN_CONSTRUCTIVE":
        verdict = "CAMPAIGN_CONTEXT_WARNING"
    elif campaign_bias == "DISTRIBUTION_RISK":
        verdict = "SUPPLY_WARNING_AT_STRUCTURE"
    else:
        verdict = "HOLD_READ_ONLY"

    return {
        "alert": "ALERT_C",
        "symbol": symbol,
        "verdict": verdict,
        "immediate_bias": immediate_bias,
        "campaign_bias": campaign_bias,
        "guardrails": GUARDRAILS,
        "explanation": [
            "Read-only fusion alert only.",
            "No mutation, no confirmation, no D3D execution.",
        ],
    }


def run_read_only_alert_review(
    symbol: str,
    bars: list[Bar],
    source: Optional[ExplicitStructuralSource],
) -> dict:
    assert_no_drift_guardrails()

    alert_a = evaluate_alert_a_immediate_20_bar_tape(symbol=symbol, bars=bars)
    latest_price = float(bars[-1].close) if bars else 0.0

    alert_b = evaluate_alert_b_campaign_context(
        symbol=symbol,
        latest_price=latest_price,
        source=source,
        contrary_warning_active=bool(alert_a.get("contrary_warning_active", False)),
    )

    alert_c = evaluate_alert_c_read_only_fusion(
        symbol=symbol,
        alert_a=alert_a,
        alert_b=alert_b,
    )

    return {
        "symbol": symbol,
        "diagnostic_only": True,
        "read_only": True,
        "not_a_trade_signal": True,
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
        "operator_control_confirmed": False,
        "alert_a": alert_a,
        "alert_b": alert_b,
        "alert_c": alert_c,
        "guardrails": GUARDRAILS,
    }
