from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import math
import pandas as pd


@dataclass
class SymbolBehaviorProfile:
    symbol: str
    bars_count: int

    atr_20: float
    atr_pct: float
    atr_ratio: float

    avg_volume_20: float
    avg_volume_50: float
    latest_volume_z: float
    latest_volume_ratio: float

    latest_spread: float
    latest_spread_pct: float
    spread_percentile_60: float

    latest_range_position_60: float
    last5_return: float
    last20_return: float

    normal_wave_distance_atr: float
    normal_reaction_atr: float
    normal_upwave_efficiency: float
    normal_downwave_efficiency: float

    liquidity_class: str
    volatility_class: str
    average_daily_volume_tier: str

    profile_quality: str
    warnings: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SymbolBehaviorProfileBuilder:
    """
    Builds a symbol-specific behavioral baseline.

    Purpose:
    - Do not compare raw price or raw volume across symbols.
    - Convert price movement, spread, volume, and wave behavior into
      symbol-relative measurements.
    - This is the foundation for Weis Wave normalization and later Gamma fusion.

    This module does NOT create trade signals.
    It creates the symbol fingerprint used by later engines.
    """

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

    @classmethod
    def _atr(cls, df: pd.DataFrame, period: int = 20) -> pd.Series:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        close = df["close"].astype(float)

        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        return tr.rolling(period, min_periods=3).mean()

    @classmethod
    def _z_score(cls, latest: float, series: pd.Series) -> float:
        series = series.dropna().astype(float)
        if len(series) < 5:
            return 0.0

        mean = cls._safe_float(series.mean())
        std = cls._safe_float(series.std())

        if std <= 0:
            return 0.0

        return round((latest - mean) / std, 4)

    @classmethod
    def _percentile_rank(cls, latest: float, series: pd.Series) -> float:
        series = series.dropna().astype(float)
        if len(series) == 0:
            return 0.0

        count = float((series <= latest).sum())
        return round(100.0 * count / len(series), 2)

    @classmethod
    def _classify_liquidity(cls, avg_volume_20: float, latest_close: float) -> str:
        dollar_volume = avg_volume_20 * latest_close

        if dollar_volume >= 500_000_000:
            return "MEGA_LIQUID"
        if dollar_volume >= 100_000_000:
            return "HIGH_LIQUIDITY"
        if dollar_volume >= 25_000_000:
            return "MEDIUM_LIQUIDITY"
        if dollar_volume >= 5_000_000:
            return "LOW_LIQUIDITY"
        return "THIN_LIQUIDITY"

    @classmethod
    def _classify_adv_tier(cls, avg_volume_20: float) -> str:
        if avg_volume_20 >= 20_000_000:
            return "MEGA_ADV"
        if avg_volume_20 >= 5_000_000:
            return "HIGH_ADV"
        if avg_volume_20 >= 1_000_000:
            return "MEDIUM_ADV"
        if avg_volume_20 >= 250_000:
            return "LOW_ADV"
        return "THIN_ADV"

    @classmethod
    def _classify_volatility(cls, atr_pct: float) -> str:
        if atr_pct >= 0.08:
            return "EXTREME_VOLATILITY"
        if atr_pct >= 0.05:
            return "HIGH_VOLATILITY"
        if atr_pct >= 0.025:
            return "MEDIUM_VOLATILITY"
        if atr_pct > 0:
            return "LOW_VOLATILITY"
        return "UNKNOWN_VOLATILITY"

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        lookback: int = 60,
    ) -> Dict[str, Any]:
        warnings: list[str] = []

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)

        if missing:
            return SymbolBehaviorProfile(
                symbol=symbol,
                bars_count=0,
                atr_20=0.0,
                atr_pct=0.0,
                atr_ratio=0.0,
                avg_volume_20=0.0,
                avg_volume_50=0.0,
                latest_volume_z=0.0,
                latest_volume_ratio=0.0,
                latest_spread=0.0,
                latest_spread_pct=0.0,
                spread_percentile_60=0.0,
                latest_range_position_60=0.0,
                last5_return=0.0,
                last20_return=0.0,
                normal_wave_distance_atr=0.0,
                normal_reaction_atr=0.0,
                normal_upwave_efficiency=0.0,
                normal_downwave_efficiency=0.0,
                liquidity_class="UNKNOWN",
                volatility_class="UNKNOWN",
                average_daily_volume_tier="UNKNOWN",
                profile_quality="INVALID",
                warnings=[f"Missing required columns: {sorted(missing)}"],
            ).to_dict()

        bars = df.copy().tail(max(lookback, 60)).reset_index(drop=True)
        bars = bars.dropna(subset=["open", "high", "low", "close", "volume"])

        if len(bars) < 10:
            warnings.append("Insufficient bars for stable symbol behavior profile.")

        for col in ["open", "high", "low", "close", "volume"]:
            bars[col] = pd.to_numeric(bars[col], errors="coerce")

        bars = bars.dropna(subset=["open", "high", "low", "close", "volume"])

        if len(bars) == 0:
            return SymbolBehaviorProfile(
                symbol=symbol,
                bars_count=0,
                atr_20=0.0,
                atr_pct=0.0,
                atr_ratio=0.0,
                avg_volume_20=0.0,
                avg_volume_50=0.0,
                latest_volume_z=0.0,
                latest_volume_ratio=0.0,
                latest_spread=0.0,
                latest_spread_pct=0.0,
                spread_percentile_60=0.0,
                latest_range_position_60=0.0,
                last5_return=0.0,
                last20_return=0.0,
                normal_wave_distance_atr=0.0,
                normal_reaction_atr=0.0,
                normal_upwave_efficiency=0.0,
                normal_downwave_efficiency=0.0,
                liquidity_class="UNKNOWN",
                volatility_class="UNKNOWN",
                average_daily_volume_tier="UNKNOWN",
                profile_quality="INVALID",
                warnings=["No valid numeric bars."],
            ).to_dict()

        latest = bars.iloc[-1]
        latest_close = cls._safe_float(latest["close"])

        atr_series = cls._atr(bars, 20)
        atr_20 = cls._safe_float(atr_series.iloc[-1])
        baseline_atr = cls._safe_float(atr_series.tail(50).mean(), atr_20)
        atr_ratio = round(atr_20 / baseline_atr, 4) if baseline_atr > 0 else 0.0
        atr_pct = round(atr_20 / latest_close, 6) if latest_close > 0 else 0.0

        spread = (bars["high"] - bars["low"]).astype(float)
        latest_spread = cls._safe_float(spread.iloc[-1])
        latest_spread_pct = round(latest_spread / latest_close, 6) if latest_close > 0 else 0.0
        spread_percentile_60 = cls._percentile_rank(latest_spread, spread.tail(60))

        avg_volume_20 = cls._safe_float(bars["volume"].tail(20).mean())
        avg_volume_50 = cls._safe_float(bars["volume"].tail(50).mean(), avg_volume_20)
        latest_volume = cls._safe_float(latest["volume"])
        latest_volume_z = cls._z_score(latest_volume, bars["volume"].tail(50))
        latest_volume_ratio = round(latest_volume / avg_volume_20, 4) if avg_volume_20 > 0 else 0.0

        range_high_60 = cls._safe_float(bars["high"].tail(60).max())
        range_low_60 = cls._safe_float(bars["low"].tail(60).min())
        range_span_60 = range_high_60 - range_low_60
        latest_range_position_60 = (
            round((latest_close - range_low_60) / range_span_60, 4)
            if range_span_60 > 0
            else 0.5
        )

        close_5 = cls._safe_float(bars["close"].iloc[-5]) if len(bars) >= 5 else latest_close
        close_20 = cls._safe_float(bars["close"].iloc[-20]) if len(bars) >= 20 else latest_close

        last5_return = round((latest_close - close_5) / close_5, 6) if close_5 > 0 else 0.0
        last20_return = round((latest_close - close_20) / close_20, 6) if close_20 > 0 else 0.0

        # Lightweight first-pass wave proxies.
        # True Weis waves will be built in weis_wave_engine.py next.
        close_diff = bars["close"].diff()
        up_moves = close_diff[close_diff > 0].abs()
        down_moves = close_diff[close_diff < 0].abs()

        normal_up_move = cls._safe_float(up_moves.tail(20).mean())
        normal_down_move = cls._safe_float(down_moves.tail(20).mean())

        normal_wave_distance = max(normal_up_move, normal_down_move)
        normal_wave_distance_atr = (
            round(normal_wave_distance / atr_20, 4) if atr_20 > 0 else 0.0
        )

        normal_reaction_atr = (
            round(normal_down_move / atr_20, 4) if atr_20 > 0 else 0.0
        )

        up_volume = cls._safe_float(bars.loc[close_diff > 0, "volume"].tail(20).mean())
        down_volume = cls._safe_float(bars.loc[close_diff < 0, "volume"].tail(20).mean())

        normal_upwave_efficiency = (
            round(normal_up_move / up_volume, 10) if up_volume > 0 else 0.0
        )
        normal_downwave_efficiency = (
            round(normal_down_move / down_volume, 10) if down_volume > 0 else 0.0
        )

        liquidity_class = cls._classify_liquidity(avg_volume_20, latest_close)
        volatility_class = cls._classify_volatility(atr_pct)
        average_daily_volume_tier = cls._classify_adv_tier(avg_volume_20)

        if len(bars) >= 50:
            profile_quality = "GOOD"
        elif len(bars) >= 20:
            profile_quality = "LIMITED"
        else:
            profile_quality = "WEAK"

        return SymbolBehaviorProfile(
            symbol=symbol,
            bars_count=int(len(bars)),
            atr_20=round(atr_20, 6),
            atr_pct=atr_pct,
            atr_ratio=atr_ratio,
            avg_volume_20=round(avg_volume_20, 2),
            avg_volume_50=round(avg_volume_50, 2),
            latest_volume_z=latest_volume_z,
            latest_volume_ratio=latest_volume_ratio,
            latest_spread=round(latest_spread, 6),
            latest_spread_pct=latest_spread_pct,
            spread_percentile_60=spread_percentile_60,
            latest_range_position_60=latest_range_position_60,
            last5_return=last5_return,
            last20_return=last20_return,
            normal_wave_distance_atr=normal_wave_distance_atr,
            normal_reaction_atr=normal_reaction_atr,
            normal_upwave_efficiency=normal_upwave_efficiency,
            normal_downwave_efficiency=normal_downwave_efficiency,
            liquidity_class=liquidity_class,
            volatility_class=volatility_class,
            average_daily_volume_tier=average_daily_volume_tier,
            profile_quality=profile_quality,
            warnings=warnings,
        ).to_dict()
