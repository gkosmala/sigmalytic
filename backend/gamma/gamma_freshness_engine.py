from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import math


@dataclass
class GammaFreshnessResult:
    symbol: str
    engine: str
    status: str

    timeframe_profile: str
    market_condition: str
    gamma_regime: str

    atr_ratio: float
    macro_iv_level: float
    active_0dte: bool
    zero_dte_vol_oi_ratio: float

    order_book_ttl_seconds: float
    gamma_ttl_seconds: float
    intraday_wave_ttl_seconds: float
    campaign_state_ttl_seconds: float

    order_book_age_seconds: Optional[float]
    gamma_data_age_seconds: Optional[float]
    intraday_wave_age_seconds: Optional[float]
    campaign_state_age_seconds: Optional[float]

    order_book_data_fresh: bool
    gamma_data_fresh: bool
    intraday_wave_data_fresh: bool
    campaign_state_fresh: bool

    router_state: str
    freshness_warning: str
    phase_confidence_modifier: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GammaFreshnessEngine:
    """
    Dynamic Gamma Freshness / TTL Engine.

    Purpose:
    - Prevent stale Gamma/options data from confirming a Weis-Gamma phase.
    - Tighten freshness clocks when ATR expands, net gamma turns negative,
      VIX/RVX rises, or 0DTE activity becomes abnormal.
    - Loosen freshness clocks when markets are positive-gamma and compressed.
    - Output GREEN / YELLOW / RED router state.

    This module does NOT trade.
    This module does NOT replace Weis.
    This module tells downstream engines whether Gamma evidence is fresh enough
    to trust.
    """

    VALID_TIMEFRAMES = {
        "SCALP",
        "INTRADAY",
        "SWING",
        "DAILY",
    }

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    @staticmethod
    def _normalize_gamma_regime(value: Any) -> str:
        text = str(value or "UNKNOWN").strip().upper()

        aliases = {
            "DEEP_POS": "DEEP_POSITIVE",
            "POS": "POSITIVE",
            "NEG": "NEGATIVE",
            "DEEP_NEG": "DEEP_NEGATIVE",
        }

        return aliases.get(text, text)

    @staticmethod
    def _normalize_timeframe(value: Any) -> str:
        text = str(value or "SWING").strip().upper()

        if text in {"TICK", "1M", "1MIN", "1-MIN", "SCALP"}:
            return "SCALP"

        if text in {"5M", "15M", "30M", "INTRADAY"}:
            return "INTRADAY"

        if text in {"1H", "4H", "HOURLY", "SWING"}:
            return "SWING"

        if text in {"1D", "DAILY", "DAY"}:
            return "DAILY"

        return "SWING"

    @classmethod
    def _classify_market_condition(
        cls,
        atr_ratio: float,
        gamma_regime: str,
        macro_iv_level: float,
        active_0dte: bool,
        zero_dte_vol_oi_ratio: float,
    ) -> str:
        """
        Order matters.

        The extreme / deep-negative condition must be checked before the
        broader negative-gamma branch, otherwise the worst condition gets
        swallowed by a less severe rule.
        """
        deep_negative = gamma_regime == "DEEP_NEGATIVE"
        negative = gamma_regime in {"NEGATIVE", "DEEP_NEGATIVE"}
        positive = gamma_regime in {"POSITIVE", "DEEP_POSITIVE"}

        extreme_atr = atr_ratio >= 3.5
        high_atr = atr_ratio >= 2.0
        compressed_atr = atr_ratio > 0 and atr_ratio < 1.0

        macro_panic = macro_iv_level >= 30.0
        macro_warning = macro_iv_level >= 25.0

        zero_dte_extreme = active_0dte and zero_dte_vol_oi_ratio >= 1.0
        zero_dte_active = active_0dte and zero_dte_vol_oi_ratio >= 0.35

        if deep_negative or extreme_atr or macro_panic or zero_dte_extreme:
            return "CRITICAL_CASCADING_SQUEEZE"

        if negative or high_atr or macro_warning or zero_dte_active:
            return "HIGH_VOL_NEGATIVE_GAMMA"

        if positive and compressed_atr and macro_iv_level < 18.0:
            return "LOW_VOL_POSITIVE_GAMMA"

        return "NORMAL_ACTIVE_EXPANSION"

    @classmethod
    def _base_ttls_for_condition(cls, condition: str) -> Dict[str, float]:
        if condition == "LOW_VOL_POSITIVE_GAMMA":
            return {
                "order_book": 5.0,
                "gamma": 1800.0,
                "intraday_wave": 900.0,
                "campaign_state": 86400.0,
            }

        if condition == "NORMAL_ACTIVE_EXPANSION":
            return {
                "order_book": 2.0,
                "gamma": 600.0,
                "intraday_wave": 300.0,
                "campaign_state": 43200.0,
            }

        if condition == "HIGH_VOL_NEGATIVE_GAMMA":
            return {
                "order_book": 1.0,
                "gamma": 120.0,
                "intraday_wave": 120.0,
                "campaign_state": 7200.0,
            }

        if condition == "CRITICAL_CASCADING_SQUEEZE":
            return {
                "order_book": 0.5,
                "gamma": 60.0,
                "intraday_wave": 60.0,
                "campaign_state": 3600.0,
            }

        return {
            "order_book": 2.0,
            "gamma": 600.0,
            "intraday_wave": 300.0,
            "campaign_state": 43200.0,
        }

    @classmethod
    def _apply_timeframe_scaling(cls, ttls: Dict[str, float], timeframe: str) -> Dict[str, float]:
        """
        Freshness depends on the strategy horizon.

        SCALP requires the tightest clock.
        SWING/DAILY can tolerate older Gamma snapshots than scalp logic,
        unless the volatility/gamma regime is critical.
        """
        out = dict(ttls)

        if timeframe == "SCALP":
            out["order_book"] = min(out["order_book"], 1.0)
            out["gamma"] = min(out["gamma"], 60.0)
            out["intraday_wave"] = min(out["intraday_wave"], 60.0)

        elif timeframe == "INTRADAY":
            out["order_book"] = min(out["order_book"], 2.0)
            out["gamma"] = min(out["gamma"], 300.0)
            out["intraday_wave"] = min(out["intraday_wave"], 180.0)

        elif timeframe == "SWING":
            out["order_book"] = max(out["order_book"], 2.0)
            out["gamma"] = max(out["gamma"], 300.0)
            out["intraday_wave"] = max(out["intraday_wave"], 300.0)

        elif timeframe == "DAILY":
            out["order_book"] = max(out["order_book"], 5.0)
            out["gamma"] = max(out["gamma"], 900.0)
            out["intraday_wave"] = max(out["intraday_wave"], 900.0)
            out["campaign_state"] = max(out["campaign_state"], 86400.0)

        return out

    @classmethod
    def _apply_speed_adjustment(
        cls,
        ttls: Dict[str, float],
        atr_ratio: float,
        macro_iv_level: float,
        zero_dte_vol_oi_ratio: float,
    ) -> Dict[str, float]:
        """
        Scale clocks dynamically.

        Higher ATR, higher macro IV, and higher 0DTE activity tighten the clocks.
        """
        out = dict(ttls)

        atr_ratio = max(atr_ratio, 0.1)

        speed_factor = 1.0

        if atr_ratio > 1.0:
            speed_factor *= min(atr_ratio, 5.0)

        if macro_iv_level >= 25.0:
            speed_factor *= min(macro_iv_level / 20.0, 2.5)

        if zero_dte_vol_oi_ratio >= 0.35:
            speed_factor *= min(1.0 + zero_dte_vol_oi_ratio, 3.0)

        if speed_factor > 1.0:
            out["order_book"] = max(0.5, out["order_book"] / speed_factor)
            out["gamma"] = max(30.0, out["gamma"] / speed_factor)
            out["intraday_wave"] = max(30.0, out["intraday_wave"] / speed_factor)
            out["campaign_state"] = max(1800.0, out["campaign_state"] / min(speed_factor, 4.0))

        return out

    @classmethod
    def _is_fresh(cls, age: Optional[float], ttl: float) -> bool:
        if age is None:
            return False

        return cls._safe_float(age, 10**9) <= ttl

    @classmethod
    def build(
        cls,
        symbol: str,
        gamma_regime: str = "UNKNOWN",
        atr_ratio: float = 1.0,
        macro_iv_level: Optional[float] = None,
        vix: Optional[float] = None,
        rvx: Optional[float] = None,
        timeframe_profile: str = "SWING",
        active_0dte: bool = False,
        zero_dte_vol_oi_ratio: float = 0.0,
        gamma_data_age_seconds: Optional[float] = None,
        order_book_age_seconds: Optional[float] = None,
        intraday_wave_age_seconds: Optional[float] = None,
        campaign_state_age_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        timeframe = cls._normalize_timeframe(timeframe_profile)
        gamma_regime = cls._normalize_gamma_regime(gamma_regime)

        atr_ratio = cls._safe_float(atr_ratio, 1.0)
        zero_dte_vol_oi_ratio = cls._safe_float(zero_dte_vol_oi_ratio)

        if macro_iv_level is None:
            if vix is not None:
                macro_iv_level = cls._safe_float(vix)
            elif rvx is not None:
                macro_iv_level = cls._safe_float(rvx)
            else:
                macro_iv_level = 15.0

        macro_iv_level = cls._safe_float(macro_iv_level, 15.0)

        condition = cls._classify_market_condition(
            atr_ratio=atr_ratio,
            gamma_regime=gamma_regime,
            macro_iv_level=macro_iv_level,
            active_0dte=active_0dte,
            zero_dte_vol_oi_ratio=zero_dte_vol_oi_ratio,
        )

        ttls = cls._base_ttls_for_condition(condition)
        ttls = cls._apply_timeframe_scaling(ttls, timeframe)
        ttls = cls._apply_speed_adjustment(
            ttls=ttls,
            atr_ratio=atr_ratio,
            macro_iv_level=macro_iv_level,
            zero_dte_vol_oi_ratio=zero_dte_vol_oi_ratio,
        )

        order_book_ttl = round(ttls["order_book"], 3)
        gamma_ttl = round(ttls["gamma"], 3)
        intraday_wave_ttl = round(ttls["intraday_wave"], 3)
        campaign_state_ttl = round(ttls["campaign_state"], 3)

        order_book_fresh = cls._is_fresh(order_book_age_seconds, order_book_ttl)
        gamma_fresh = cls._is_fresh(gamma_data_age_seconds, gamma_ttl)
        intraday_wave_fresh = cls._is_fresh(intraday_wave_age_seconds, intraday_wave_ttl)
        campaign_state_fresh = cls._is_fresh(campaign_state_age_seconds, campaign_state_ttl)

        stale_items = []

        if not order_book_fresh:
            stale_items.append("order_book")

        if not gamma_fresh:
            stale_items.append("gamma")

        if not intraday_wave_fresh:
            stale_items.append("intraday_wave")

        if not campaign_state_fresh:
            stale_items.append("campaign_state")

        if not stale_items:
            router_state = "GREEN"
            warning = "All freshness clocks valid."
            confidence_modifier = 1.0

        elif condition == "CRITICAL_CASCADING_SQUEEZE" and ("gamma" in stale_items or "order_book" in stale_items):
            router_state = "RED"
            warning = "Critical regime with stale fast-changing data. Stand down."
            confidence_modifier = 0.0

        elif "gamma" in stale_items or "order_book" in stale_items:
            router_state = "YELLOW"
            warning = "Fast-changing Gamma/order-book data is stale. Refresh required before confirmation."
            confidence_modifier = 0.35

        else:
            router_state = "YELLOW"
            warning = "Some slower evidence clocks are stale. Reduce confidence."
            confidence_modifier = 0.65

        status = "OK" if router_state in {"GREEN", "YELLOW"} else "BLOCKED"

        return GammaFreshnessResult(
            symbol=symbol,
            engine="GAMMA_FRESHNESS",
            status=status,
            timeframe_profile=timeframe,
            market_condition=condition,
            gamma_regime=gamma_regime,
            atr_ratio=round(atr_ratio, 4),
            macro_iv_level=round(macro_iv_level, 4),
            active_0dte=bool(active_0dte),
            zero_dte_vol_oi_ratio=round(zero_dte_vol_oi_ratio, 4),
            order_book_ttl_seconds=order_book_ttl,
            gamma_ttl_seconds=gamma_ttl,
            intraday_wave_ttl_seconds=intraday_wave_ttl,
            campaign_state_ttl_seconds=campaign_state_ttl,
            order_book_age_seconds=order_book_age_seconds,
            gamma_data_age_seconds=gamma_data_age_seconds,
            intraday_wave_age_seconds=intraday_wave_age_seconds,
            campaign_state_age_seconds=campaign_state_age_seconds,
            order_book_data_fresh=order_book_fresh,
            gamma_data_fresh=gamma_fresh,
            intraday_wave_data_fresh=intraday_wave_fresh,
            campaign_state_fresh=campaign_state_fresh,
            router_state=router_state,
            freshness_warning=warning,
            phase_confidence_modifier=round(confidence_modifier, 4),
        ).to_dict()
