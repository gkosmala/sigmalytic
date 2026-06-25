from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Union

import math
import pandas as pd


@dataclass
class ZeroDTESqueezeResult:
    symbol: str
    engine: str
    status: str

    active_0dte: bool
    zero_dte_contract_count: int
    zero_dte_volume: float
    zero_dte_open_interest: float
    zero_dte_vol_oi_ratio: float

    call_0dte_volume: float
    put_0dte_volume: float
    call_0dte_open_interest: float
    put_0dte_open_interest: float
    call_put_volume_ratio: float

    dominant_0dte_side: str
    squeeze_state: str
    theta_flush_risk: bool
    liquidation_risk: bool

    nearest_active_strike: Optional[float]
    nearest_active_strike_distance_pct: Optional[float]

    confidence: float
    reason: str
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ZeroDTESqueezeEngine:
    """
    0DTE Squeeze / Liquidation Engine.

    Purpose:
    - Detect abnormal same-day options pressure.
    - Measure 0DTE Volume / Open Interest.
    - Classify upside squeeze, downside liquidation, squeeze building,
      theta-flush risk, or no anomaly.
    - Feed Weis-Gamma fusion later.

    This module does NOT trade.
    This module does NOT override stale-data rules.
    This module does NOT replace the Weis Wave Engine.
    """

    CALL_VALUES = {"C", "CALL", "CALLS"}
    PUT_VALUES = {"P", "PUT", "PUTS"}

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
    def _safe_str(value: Any, default: str = "") -> str:
        try:
            if value is None:
                return default
            return str(value).strip().upper()
        except Exception:
            return default

    @classmethod
    def _coalesce_column(cls, df: pd.DataFrame, candidates: List[str], default: Any = 0.0) -> pd.Series:
        lower_map = {c.lower(): c for c in df.columns}

        for candidate in candidates:
            key = candidate.lower()
            if key in lower_map:
                return df[lower_map[key]]

        return pd.Series([default] * len(df))

    @classmethod
    def _prepare_options_data(
        cls,
        options_data: Union[pd.DataFrame, List[Dict[str, Any]]],
    ) -> pd.DataFrame:
        if isinstance(options_data, pd.DataFrame):
            df = options_data.copy()
        else:
            df = pd.DataFrame(options_data or [])

        if df.empty:
            return pd.DataFrame(
                columns=[
                    "strike",
                    "option_type",
                    "open_interest",
                    "volume",
                    "dte",
                ]
            )

        out = pd.DataFrame()

        out["strike"] = pd.to_numeric(
            cls._coalesce_column(df, ["strike", "strike_price", "k"]),
            errors="coerce",
        )

        out["option_type"] = cls._coalesce_column(
            df,
            ["option_type", "type", "right", "contract_type"],
            default="UNKNOWN",
        ).apply(lambda x: cls._safe_str(x, "UNKNOWN"))

        out["open_interest"] = pd.to_numeric(
            cls._coalesce_column(df, ["open_interest", "oi", "openInterest"]),
            errors="coerce",
        ).fillna(0.0)

        out["volume"] = pd.to_numeric(
            cls._coalesce_column(df, ["volume", "option_volume", "vol"]),
            errors="coerce",
        ).fillna(0.0)

        out["dte"] = pd.to_numeric(
            cls._coalesce_column(df, ["dte", "days_to_expiration", "daysToExpiration"]),
            errors="coerce",
        ).fillna(9999)

        out = out.dropna(subset=["strike"]).reset_index(drop=True)

        return out

    @classmethod
    def _nearest_active_strike(cls, zero_dte: pd.DataFrame, spot_price: float) -> tuple[Optional[float], Optional[float]]:
        if zero_dte.empty or spot_price <= 0:
            return None, None

        working = zero_dte.copy()
        working["distance_abs"] = (working["strike"] - spot_price).abs()
        row = working.sort_values("distance_abs").iloc[0]

        strike = cls._safe_float(row["strike"])
        distance_pct = round((strike - spot_price) / spot_price, 6)

        return round(strike, 6), distance_pct

    @classmethod
    def _classify(
        cls,
        vol_oi_ratio: float,
        dominant_side: str,
        call_put_volume_ratio: float,
        close_location: float,
        wave_direction: str,
        wave_efficiency: float,
        minutes_to_close: Optional[float],
        atr_ratio: float,
    ) -> tuple[str, bool, bool, float, str]:
        """
        Classify the 0DTE condition.

        close_location:
        - near 1.0 = close near high
        - near 0.0 = close near low

        wave_direction:
        - UP / DOWN / UNKNOWN
        """
        wave_direction = str(wave_direction or "UNKNOWN").upper()

        theta_window = minutes_to_close is not None and minutes_to_close <= 90
        late_theta_window = minutes_to_close is not None and minutes_to_close <= 45

        extreme_vol_oi = vol_oi_ratio >= 1.0
        strong_vol_oi = vol_oi_ratio >= 0.50
        building_vol_oi = vol_oi_ratio >= 0.25

        near_high = close_location >= 0.70
        near_low = close_location <= 0.30
        momentum_stalling = wave_efficiency > 0 and wave_efficiency < 0.65

        theta_flush_risk = False
        liquidation_risk = False

        if extreme_vol_oi and dominant_side == "CALL" and near_high and wave_direction == "UP":
            confidence = 0.90
            reason = "Extreme 0DTE call pressure with price closing near high and Weis wave up."
            return "0DTE_UPSIDE_SQUEEZE_CONFIRMED", theta_flush_risk, liquidation_risk, confidence, reason

        if extreme_vol_oi and dominant_side == "PUT" and near_low and wave_direction == "DOWN":
            confidence = 0.90
            liquidation_risk = True
            reason = "Extreme 0DTE put pressure with price closing near low and Weis wave down."
            return "0DTE_DOWNSIDE_LIQUIDATION_CONFIRMED", theta_flush_risk, liquidation_risk, confidence, reason

        if strong_vol_oi and dominant_side == "CALL" and near_high:
            confidence = 0.75
            reason = "Strong 0DTE call pressure with upside close location."
            return "0DTE_UPSIDE_SQUEEZE_CONFIRMED", theta_flush_risk, liquidation_risk, confidence, reason

        if strong_vol_oi and dominant_side == "PUT" and near_low:
            confidence = 0.75
            liquidation_risk = True
            reason = "Strong 0DTE put pressure with downside close location."
            return "0DTE_DOWNSIDE_LIQUIDATION_CONFIRMED", theta_flush_risk, liquidation_risk, confidence, reason

        if theta_window and strong_vol_oi and momentum_stalling:
            theta_flush_risk = True
            confidence = 0.70 if late_theta_window else 0.60
            reason = "0DTE activity is elevated late in the session while wave efficiency is stalling."
            return "0DTE_THETA_FLUSH_RISK", theta_flush_risk, liquidation_risk, confidence, reason

        if building_vol_oi:
            confidence = 0.55
            reason = "0DTE volume/open-interest pressure is building but not yet confirmed by price location."
            return "0DTE_SQUEEZE_BUILDING", theta_flush_risk, liquidation_risk, confidence, reason

        if atr_ratio >= 2.5 and vol_oi_ratio >= 0.15:
            confidence = 0.45
            reason = "ATR expansion with moderate 0DTE participation; monitor for fast squeeze development."
            return "0DTE_MONITOR", theta_flush_risk, liquidation_risk, confidence, reason

        confidence = 0.10
        reason = "No meaningful 0DTE anomaly detected."
        return "NO_0DTE_ANOMALY", theta_flush_risk, liquidation_risk, confidence, reason

    @classmethod
    def build(
        cls,
        options_data: Union[pd.DataFrame, List[Dict[str, Any]]],
        symbol: str,
        spot_price: float,
        close_location: float = 0.50,
        wave_direction: str = "UNKNOWN",
        wave_efficiency: float = 0.0,
        atr_ratio: float = 1.0,
        minutes_to_close: Optional[float] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []

        df = cls._prepare_options_data(options_data)

        spot_price = cls._safe_float(spot_price)
        close_location = max(0.0, min(cls._safe_float(close_location, 0.50), 1.0))
        wave_efficiency = cls._safe_float(wave_efficiency)
        atr_ratio = cls._safe_float(atr_ratio, 1.0)

        if df.empty:
            return ZeroDTESqueezeResult(
                symbol=symbol,
                engine="ZERO_DTE_SQUEEZE",
                status="NO_OPTIONS_DATA",
                active_0dte=False,
                zero_dte_contract_count=0,
                zero_dte_volume=0.0,
                zero_dte_open_interest=0.0,
                zero_dte_vol_oi_ratio=0.0,
                call_0dte_volume=0.0,
                put_0dte_volume=0.0,
                call_0dte_open_interest=0.0,
                put_0dte_open_interest=0.0,
                call_put_volume_ratio=0.0,
                dominant_0dte_side="NONE",
                squeeze_state="NO_0DTE_ANOMALY",
                theta_flush_risk=False,
                liquidation_risk=False,
                nearest_active_strike=None,
                nearest_active_strike_distance_pct=None,
                confidence=0.0,
                reason="No options data supplied.",
                warnings=["No options data supplied."],
            ).to_dict()

        df["is_call"] = df["option_type"].isin(cls.CALL_VALUES)
        df["is_put"] = df["option_type"].isin(cls.PUT_VALUES)

        unknown_types = int((~df["is_call"] & ~df["is_put"]).sum())
        if unknown_types:
            warnings.append(f"{unknown_types} contracts had unknown option_type.")

        zero_dte = df[df["dte"] <= 0].copy()

        if zero_dte.empty:
            return ZeroDTESqueezeResult(
                symbol=symbol,
                engine="ZERO_DTE_SQUEEZE",
                status="OK",
                active_0dte=False,
                zero_dte_contract_count=0,
                zero_dte_volume=0.0,
                zero_dte_open_interest=0.0,
                zero_dte_vol_oi_ratio=0.0,
                call_0dte_volume=0.0,
                put_0dte_volume=0.0,
                call_0dte_open_interest=0.0,
                put_0dte_open_interest=0.0,
                call_put_volume_ratio=0.0,
                dominant_0dte_side="NONE",
                squeeze_state="NO_0DTE_ANOMALY",
                theta_flush_risk=False,
                liquidation_risk=False,
                nearest_active_strike=None,
                nearest_active_strike_distance_pct=None,
                confidence=0.0,
                reason="No 0DTE contracts present.",
                warnings=warnings,
            ).to_dict()

        call_0dte = zero_dte[zero_dte["is_call"]]
        put_0dte = zero_dte[zero_dte["is_put"]]

        call_volume = cls._safe_float(call_0dte["volume"].sum())
        put_volume = cls._safe_float(put_0dte["volume"].sum())
        call_oi = cls._safe_float(call_0dte["open_interest"].sum())
        put_oi = cls._safe_float(put_0dte["open_interest"].sum())

        total_volume = call_volume + put_volume
        total_oi = call_oi + put_oi

        vol_oi_ratio = round(total_volume / total_oi, 4) if total_oi > 0 else 0.0
        call_put_volume_ratio = round(call_volume / put_volume, 4) if put_volume > 0 else (999.0 if call_volume > 0 else 0.0)

        if call_volume > put_volume * 1.25:
            dominant_side = "CALL"
        elif put_volume > call_volume * 1.25:
            dominant_side = "PUT"
        elif total_volume > 0:
            dominant_side = "MIXED"
        else:
            dominant_side = "NONE"

        nearest_strike, nearest_dist_pct = cls._nearest_active_strike(zero_dte, spot_price)

        squeeze_state, theta_flush_risk, liquidation_risk, confidence, reason = cls._classify(
            vol_oi_ratio=vol_oi_ratio,
            dominant_side=dominant_side,
            call_put_volume_ratio=call_put_volume_ratio,
            close_location=close_location,
            wave_direction=wave_direction,
            wave_efficiency=wave_efficiency,
            minutes_to_close=minutes_to_close,
            atr_ratio=atr_ratio,
        )

        active_0dte = bool(total_volume > 0 or total_oi > 0)

        return ZeroDTESqueezeResult(
            symbol=symbol,
            engine="ZERO_DTE_SQUEEZE",
            status="OK",
            active_0dte=active_0dte,
            zero_dte_contract_count=int(len(zero_dte)),
            zero_dte_volume=round(total_volume, 2),
            zero_dte_open_interest=round(total_oi, 2),
            zero_dte_vol_oi_ratio=vol_oi_ratio,
            call_0dte_volume=round(call_volume, 2),
            put_0dte_volume=round(put_volume, 2),
            call_0dte_open_interest=round(call_oi, 2),
            put_0dte_open_interest=round(put_oi, 2),
            call_put_volume_ratio=call_put_volume_ratio,
            dominant_0dte_side=dominant_side,
            squeeze_state=squeeze_state,
            theta_flush_risk=theta_flush_risk,
            liquidation_risk=liquidation_risk,
            nearest_active_strike=nearest_strike,
            nearest_active_strike_distance_pct=nearest_dist_pct,
            confidence=round(confidence, 4),
            reason=reason,
            warnings=warnings,
        ).to_dict()
