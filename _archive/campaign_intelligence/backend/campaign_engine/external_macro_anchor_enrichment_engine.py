"""
D3C.2B External Macro-Anchor Enrichment Engine.

Read-only historical macro support/resistance anchor diagnostic.

Doctrine:
- Operator control is evidence, not a score.
- Macro anchors are structural-location evidence only.
- Macro anchors do not confirm operator control.
- Old pivots are not accepted unless gate-validated.
- This engine does not write to Supabase.
- This engine does not mutate campaigns.
- This engine does not change score, rank, state, transition, gamma, probability,
  expected return, edge, target, or historical outcome fields.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Dict, List, Optional


ENGINE_NAME = "D3C2B_EXTERNAL_MACRO_ANCHOR_ENRICHMENT"
ENGINE_VERSION = "phase_d3c2b_external_macro_anchor_enrichment_read_only_v1"


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return {}
    if hasattr(value, "dict"):
        try:
            return value.dict()
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        number = float(value)
        if not isfinite(number):
            return default
        return number
    except Exception:
        return default


def _bar_value(bar: Dict[str, Any], key: str) -> Optional[float]:
    return _safe_float(_as_dict(bar).get(key), None)


def _usable_bars(structural_location: Dict[str, Any]) -> List[Dict[str, Any]]:
    price_series = _as_dict(structural_location.get("price_series"))
    bars: List[Dict[str, Any]] = []

    for item in _as_list(price_series.get("bars")):
        row = _as_dict(item)
        if all(_bar_value(row, key) is not None for key in ["open", "high", "low", "close", "volume"]):
            bars.append(row)

    return bars


def _touch_count(bars: List[Dict[str, Any]], level: float, tolerance: float, side: str) -> int:
    touches = 0

    for bar in bars:
        high = _bar_value(bar, "high")
        low = _bar_value(bar, "low")
        close = _bar_value(bar, "close")

        if high is None or low is None or close is None:
            continue

        if side == "support" and (abs(low - level) <= tolerance or abs(close - level) <= tolerance):
            touches += 1

        if side == "resistance" and (abs(high - level) <= tolerance or abs(close - level) <= tolerance):
            touches += 1

    return touches


def _rejection_count(bars: List[Dict[str, Any]], level: float, tolerance: float, side: str) -> int:
    rejections = 0

    for bar in bars:
        high = _bar_value(bar, "high")
        low = _bar_value(bar, "low")
        close = _bar_value(bar, "close")

        if high is None or low is None or close is None:
            continue

        if side == "support" and low <= level + tolerance and close >= level:
            rejections += 1

        if side == "resistance" and high >= level - tolerance and close <= level:
            rejections += 1

    return rejections


def _last_touch_index(bars: List[Dict[str, Any]], level: float, tolerance: float, side: str) -> Optional[int]:
    last_index: Optional[int] = None

    for index, bar in enumerate(bars):
        high = _bar_value(bar, "high")
        low = _bar_value(bar, "low")
        close = _bar_value(bar, "close")

        if high is None or low is None or close is None:
            continue

        touched = False

        if side == "support":
            touched = bool(abs(low - level) <= tolerance or abs(close - level) <= tolerance)

        if side == "resistance":
            touched = bool(abs(high - level) <= tolerance or abs(close - level) <= tolerance)

        if touched:
            last_index = index

    return last_index


def _validate_anchor(
    bars: List[Dict[str, Any]],
    level: Optional[float],
    current_price: Optional[float],
    effective_atr: Optional[float],
    side: str,
) -> Dict[str, Any]:
    if level is None or current_price is None or effective_atr is None or effective_atr <= 0:
        return {
            "level": level,
            "side": side,
            "validated": False,
            "gate": "MISSING_NUMERIC_INPUTS",
            "gate_reasons": ["MISSING_NUMERIC_INPUTS"],
            "touch_count": 0,
            "rejection_count": 0,
            "last_touch_age_bars": None,
            "distance_atr": None,
        }

    tolerance = max(effective_atr * 0.35, abs(level) * 0.005, 0.01)
    touch_count = _touch_count(bars, level, tolerance, side)
    rejection_count = _rejection_count(bars, level, tolerance, side)
    last_index = _last_touch_index(bars, level, tolerance, side)
    last_touch_age = None if last_index is None else max(0, len(bars) - 1 - last_index)
    distance_atr = abs(current_price - level) / effective_atr

    gate_reasons: List[str] = []

    if len(bars) < 60:
        gate_reasons.append("LESS_THAN_60_USABLE_BARS")
    if touch_count < 2:
        gate_reasons.append("LESS_THAN_2_VALIDATED_TOUCHES")
    if rejection_count < 1:
        gate_reasons.append("NO_CLOSE_BASED_REJECTION_OR_RECAPTURE")
    if last_touch_age is None:
        gate_reasons.append("NO_VALID_TOUCH_INDEX")
    elif last_touch_age > 126:
        gate_reasons.append("OLD_PIVOT_NOT_RECENTLY_GATE_VALIDATED")

    side_valid = True

    if side == "support" and level > current_price:
        side_valid = False
        gate_reasons.append("SUPPORT_LEVEL_ABOVE_CURRENT_PRICE")

    if side == "resistance" and level < current_price:
        side_valid = False
        gate_reasons.append("RESISTANCE_LEVEL_BELOW_CURRENT_PRICE")

    validated = bool(
        len(bars) >= 60
        and touch_count >= 2
        and rejection_count >= 1
        and last_touch_age is not None
        and last_touch_age <= 126
        and side_valid
    )

    return {
        "level": level,
        "side": side,
        "validated": validated,
        "gate": "VALIDATED_MACRO_ANCHOR" if validated else "BLOCKED_MACRO_ANCHOR",
        "gate_reasons": gate_reasons,
        "touch_count": touch_count,
        "rejection_count": rejection_count,
        "last_touch_age_bars": last_touch_age,
        "distance_atr": round(distance_atr, 4),
        "tolerance": round(tolerance, 4),
    }


def evaluate_external_macro_anchor(campaign: Dict[str, Any]) -> Dict[str, Any]:
    c = _as_dict(campaign)
    evidence = _as_dict(_get(c, "evidence", {}))
    structural_location = _as_dict(evidence.get("structural_location"))

    symbol = _get(c, "symbol")
    campaign_id = _get(c, "campaign_id") or _get(c, "id")
    campaign_state = (
        _get(c, "current_state")
        or _get(c, "state_enum")
        or _get(c, "campaign_state")
        or _get(c, "state")
        or _get(c, "lifecycle_state")
        or _get(c, "campaign_lifecycle_state")
    )

    current_price = _safe_float(structural_location.get("current_price"), None)
    range_floor = _safe_float(structural_location.get("range_floor"), None)
    range_ceiling = _safe_float(structural_location.get("range_ceiling"), None)
    support_level = _safe_float(structural_location.get("support_level"), None)
    resistance_level = _safe_float(structural_location.get("resistance_level"), None)
    effective_atr = _safe_float(structural_location.get("effective_atr"), None)

    bars = _usable_bars(structural_location)

    support_candidates = [value for value in [range_floor, support_level] if value is not None]
    resistance_candidates = [value for value in [range_ceiling, resistance_level] if value is not None]

    macro_support = _validate_anchor(
        bars=bars,
        level=min(support_candidates) if support_candidates else None,
        current_price=current_price,
        effective_atr=effective_atr,
        side="support",
    )

    macro_resistance = _validate_anchor(
        bars=bars,
        level=max(resistance_candidates) if resistance_candidates else None,
        current_price=current_price,
        effective_atr=effective_atr,
        side="resistance",
    )

    validated_count = int(bool(macro_support.get("validated"))) + int(bool(macro_resistance.get("validated")))

    if validated_count == 2:
        macro_anchor_status = "VALIDATED_SUPPORT_AND_RESISTANCE"
    elif macro_support.get("validated"):
        macro_anchor_status = "VALIDATED_SUPPORT_ONLY"
    elif macro_resistance.get("validated"):
        macro_anchor_status = "VALIDATED_RESISTANCE_ONLY"
    elif bars:
        macro_anchor_status = "MACRO_ANCHORS_PRESENT_BUT_BLOCKED"
    else:
        macro_anchor_status = "MISSING_PRICE_SERIES"

    gate_reasons: List[str] = []
    for row in [macro_support, macro_resistance]:
        for reason in row.get("gate_reasons") or []:
            if reason not in gate_reasons:
                gate_reasons.append(reason)

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "campaign_state": campaign_state,

        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,

        "macro_anchor_status": macro_anchor_status,
        "macro_anchor_validated_count": validated_count,
        "old_pivot_gate_policy": "OLD_PIVOTS_BLOCKED_UNLESS_TOUCH_AND_CLOSE_REJECTION_VALIDATED",
        "usable_bar_count": len(bars),
        "macro_support": macro_support,
        "macro_resistance": macro_resistance,
        "gate_reasons": gate_reasons,
    }
