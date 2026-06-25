from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import math
import pandas as pd


@dataclass
class WeisWave:
    wave_id: int
    direction: str

    start_index: int
    end_index: int
    start_price: float
    end_price: float

    wave_distance: float
    wave_distance_atr: float
    wave_volume: float
    wave_volume_z: float
    wave_effort_ratio: float
    wave_efficiency: float
    wave_duration_bars: int
    wave_close_location: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WeisWaveEngine:
    """
    David Weis-style wave engine.

    Purpose:
    - Convert time-based OHLCV bars into completed directional waves.
    - Measure Effort vs Reward on each wave.
    - Normalize reward by ATR.
    - Normalize effort by symbol-relative volume behavior.
    - Produce structured evidence for demand dominance, supply dominance,
      thrust shortening, and effort/result failure.

    This module does NOT generate trades.
    This module does NOT use Wyckoff or Livermore.
    It is the Weis foundation layer for the next V2 phase.
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
    def _z_score(cls, value: float, values: List[float]) -> float:
        clean = [cls._safe_float(v) for v in values if cls._safe_float(v) > 0]

        if len(clean) < 3:
            return 0.0

        mean = sum(clean) / len(clean)
        variance = sum((v - mean) ** 2 for v in clean) / max(len(clean) - 1, 1)
        std = math.sqrt(variance)

        if std <= 0:
            return 0.0

        return round((value - mean) / std, 4)

    @classmethod
    def _prepare_bars(cls, df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)

        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        bars = df.copy().reset_index(drop=True)

        for col in ["open", "high", "low", "close", "volume"]:
            bars[col] = pd.to_numeric(bars[col], errors="coerce")

        bars = bars.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)

        return bars

    @classmethod
    def _close_location(cls, wave_df: pd.DataFrame, end_price: float) -> float:
        wave_high = cls._safe_float(wave_df["high"].max())
        wave_low = cls._safe_float(wave_df["low"].min())
        span = wave_high - wave_low

        if span <= 0:
            return 0.5

        return round((end_price - wave_low) / span, 4)

    @classmethod
    def _build_raw_waves(
        cls,
        bars: pd.DataFrame,
        reversal_amount: float,
    ) -> List[Dict[str, Any]]:
        closes = bars["close"].astype(float).tolist()

        if len(closes) < 5 or reversal_amount <= 0:
            return []

        raw_waves: List[Dict[str, Any]] = []

        pivot_index = 0
        pivot_price = closes[0]

        direction: Optional[str] = None
        extreme_index = 0
        extreme_price = closes[0]

        for i in range(1, len(closes)):
            price = closes[i]

            if direction is None:
                if price >= pivot_price + reversal_amount:
                    direction = "UP"
                    extreme_index = i
                    extreme_price = price
                elif price <= pivot_price - reversal_amount:
                    direction = "DOWN"
                    extreme_index = i
                    extreme_price = price
                continue

            if direction == "UP":
                if price > extreme_price:
                    extreme_price = price
                    extreme_index = i
                elif extreme_price - price >= reversal_amount:
                    raw_waves.append(
                        {
                            "direction": "UP",
                            "start_index": pivot_index,
                            "end_index": extreme_index,
                            "start_price": pivot_price,
                            "end_price": extreme_price,
                        }
                    )

                    pivot_index = extreme_index
                    pivot_price = extreme_price
                    direction = "DOWN"
                    extreme_index = i
                    extreme_price = price

            elif direction == "DOWN":
                if price < extreme_price:
                    extreme_price = price
                    extreme_index = i
                elif price - extreme_price >= reversal_amount:
                    raw_waves.append(
                        {
                            "direction": "DOWN",
                            "start_index": pivot_index,
                            "end_index": extreme_index,
                            "start_price": pivot_price,
                            "end_price": extreme_price,
                        }
                    )

                    pivot_index = extreme_index
                    pivot_price = extreme_price
                    direction = "UP"
                    extreme_index = i
                    extreme_price = price

        if direction is not None and extreme_index > pivot_index:
            raw_waves.append(
                {
                    "direction": direction,
                    "start_index": pivot_index,
                    "end_index": extreme_index,
                    "start_price": pivot_price,
                    "end_price": extreme_price,
                }
            )

        return raw_waves

    @classmethod
    def _decorate_waves(
        cls,
        bars: pd.DataFrame,
        raw_waves: List[Dict[str, Any]],
        atr_value: float,
        avg_volume_20: float,
    ) -> List[Dict[str, Any]]:
        if not raw_waves:
            return []

        raw_volumes: List[float] = []

        for raw in raw_waves:
            start = int(raw["start_index"])
            end = int(raw["end_index"])
            wave_df = bars.iloc[start : end + 1]
            raw_volumes.append(cls._safe_float(wave_df["volume"].sum()))

        waves: List[Dict[str, Any]] = []

        for idx, raw in enumerate(raw_waves, start=1):
            start = int(raw["start_index"])
            end = int(raw["end_index"])
            wave_df = bars.iloc[start : end + 1]

            start_price = cls._safe_float(raw["start_price"])
            end_price = cls._safe_float(raw["end_price"])

            distance = abs(end_price - start_price)
            distance_atr = round(distance / atr_value, 4) if atr_value > 0 else 0.0

            duration = max(end - start + 1, 1)
            volume = cls._safe_float(wave_df["volume"].sum())
            volume_z = cls._z_score(volume, raw_volumes)

            expected_volume = avg_volume_20 * duration if avg_volume_20 > 0 else 0.0
            effort_ratio = round(volume / expected_volume, 4) if expected_volume > 0 else 0.0

            # Weis efficiency = normalized reward divided by normalized effort.
            # Higher means effort is producing more result.
            efficiency = round(distance_atr / max(effort_ratio, 0.01), 6)

            close_location = cls._close_location(wave_df, end_price)

            wave = WeisWave(
                wave_id=idx,
                direction=str(raw["direction"]),
                start_index=start,
                end_index=end,
                start_price=round(start_price, 6),
                end_price=round(end_price, 6),
                wave_distance=round(distance, 6),
                wave_distance_atr=distance_atr,
                wave_volume=round(volume, 2),
                wave_volume_z=volume_z,
                wave_effort_ratio=effort_ratio,
                wave_efficiency=efficiency,
                wave_duration_bars=duration,
                wave_close_location=close_location,
            )

            waves.append(wave.to_dict())

        return waves

    @classmethod
    def _latest_by_direction(cls, waves: List[Dict[str, Any]], direction: str, count: int = 3) -> List[Dict[str, Any]]:
        return [w for w in waves if w.get("direction") == direction][-count:]

    @classmethod
    def _avg(cls, values: List[float]) -> float:
        clean = [cls._safe_float(v) for v in values]
        if not clean:
            return 0.0
        return sum(clean) / len(clean)

    @classmethod
    def _evidence_from_waves(cls, waves: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not waves:
            return {
                "wave_direction": "UNKNOWN",
                "wave_distance_atr": 0.0,
                "wave_volume_z": 0.0,
                "wave_efficiency": 0.0,
                "demand_dominance": False,
                "supply_dominance": False,
                "upwave_result_improving": False,
                "downwave_result_improving": False,
                "shortening_upside_thrust": False,
                "shortening_downside_thrust": False,
                "effort_producing_upside_result": False,
                "effort_producing_downside_result": False,
                "effort_failing_upside_result": False,
                "effort_failing_downside_result": False,
            }

        latest = waves[-1]

        upwaves = cls._latest_by_direction(waves, "UP", 3)
        downwaves = cls._latest_by_direction(waves, "DOWN", 3)

        up_distance = cls._avg([w["wave_distance_atr"] for w in upwaves])
        down_distance = cls._avg([w["wave_distance_atr"] for w in downwaves])

        up_efficiency = cls._avg([w["wave_efficiency"] for w in upwaves])
        down_efficiency = cls._avg([w["wave_efficiency"] for w in downwaves])

        demand_dominance = bool(
            len(upwaves) > 0
            and up_distance >= down_distance
            and up_efficiency >= down_efficiency
        )

        supply_dominance = bool(
            len(downwaves) > 0
            and down_distance > up_distance
            and down_efficiency > up_efficiency
        )

        upwave_result_improving = False
        if len(upwaves) >= 2:
            upwave_result_improving = bool(
                cls._safe_float(upwaves[-1]["wave_distance_atr"]) > cls._safe_float(upwaves[-2]["wave_distance_atr"])
                or cls._safe_float(upwaves[-1]["wave_efficiency"]) > cls._safe_float(upwaves[-2]["wave_efficiency"])
            )

        downwave_result_improving = False
        if len(downwaves) >= 2:
            downwave_result_improving = bool(
                cls._safe_float(downwaves[-1]["wave_distance_atr"]) > cls._safe_float(downwaves[-2]["wave_distance_atr"])
                or cls._safe_float(downwaves[-1]["wave_efficiency"]) > cls._safe_float(downwaves[-2]["wave_efficiency"])
            )

        shortening_upside_thrust = False
        if len(upwaves) >= 2:
            shortening_upside_thrust = bool(
                cls._safe_float(upwaves[-1]["wave_distance_atr"]) < cls._safe_float(upwaves[-2]["wave_distance_atr"])
                and cls._safe_float(upwaves[-1]["wave_effort_ratio"]) >= cls._safe_float(upwaves[-2]["wave_effort_ratio"]) * 0.8
            )

        shortening_downside_thrust = False
        if len(downwaves) >= 2:
            shortening_downside_thrust = bool(
                cls._safe_float(downwaves[-1]["wave_distance_atr"]) < cls._safe_float(downwaves[-2]["wave_distance_atr"])
                and cls._safe_float(downwaves[-1]["wave_effort_ratio"]) >= cls._safe_float(downwaves[-2]["wave_effort_ratio"]) * 0.8
            )

        latest_direction = str(latest.get("direction", "UNKNOWN"))
        latest_distance_atr = cls._safe_float(latest.get("wave_distance_atr"))
        latest_volume_z = cls._safe_float(latest.get("wave_volume_z"))
        latest_efficiency = cls._safe_float(latest.get("wave_efficiency"))
        latest_close_location = cls._safe_float(latest.get("wave_close_location"))

        effort_producing_upside_result = bool(
            latest_direction == "UP"
            and latest_distance_atr >= 1.0
            and latest_efficiency >= max(down_efficiency, 0.0)
            and latest_close_location >= 0.60
        )

        effort_producing_downside_result = bool(
            latest_direction == "DOWN"
            and latest_distance_atr >= 1.0
            and latest_efficiency >= max(up_efficiency, 0.0)
            and latest_close_location <= 0.40
        )

        effort_failing_upside_result = bool(
            latest_direction == "UP"
            and latest_volume_z >= 1.0
            and latest_efficiency < max(down_efficiency, 0.000001)
            and latest_close_location < 0.60
        )

        effort_failing_downside_result = bool(
            latest_direction == "DOWN"
            and latest_volume_z >= 1.0
            and latest_efficiency < max(up_efficiency, 0.000001)
            and latest_close_location > 0.40
        )

        return {
            "wave_direction": latest_direction,
            "wave_distance_atr": round(latest_distance_atr, 4),
            "wave_volume_z": round(latest_volume_z, 4),
            "wave_efficiency": round(latest_efficiency, 6),
            "demand_dominance": demand_dominance,
            "supply_dominance": supply_dominance,
            "upwave_result_improving": upwave_result_improving,
            "downwave_result_improving": downwave_result_improving,
            "shortening_upside_thrust": shortening_upside_thrust,
            "shortening_downside_thrust": shortening_downside_thrust,
            "effort_producing_upside_result": effort_producing_upside_result,
            "effort_producing_downside_result": effort_producing_downside_result,
            "effort_failing_upside_result": effort_failing_upside_result,
            "effort_failing_downside_result": effort_failing_downside_result,
            "upwave_avg_distance_atr": round(up_distance, 4),
            "downwave_avg_distance_atr": round(down_distance, 4),
            "upwave_avg_efficiency": round(up_efficiency, 6),
            "downwave_avg_efficiency": round(down_efficiency, 6),
        }

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        reversal_atr: float = 1.0,
        lookback: int = 120,
    ) -> Dict[str, Any]:
        bars = cls._prepare_bars(df).tail(lookback).reset_index(drop=True)

        if len(bars) < 10:
            return {
                "symbol": symbol,
                "engine": "WEIS_WAVE",
                "status": "INSUFFICIENT_DATA",
                "wave_count": 0,
                "reversal_atr": reversal_atr,
                "reversal_amount": 0.0,
                "latest_wave": None,
                "waves": [],
                "evidence": cls._evidence_from_waves([]),
                "warnings": ["Insufficient bars for Weis Wave construction."],
            }

        atr_series = cls._atr(bars, 20)
        atr_value = cls._safe_float(atr_series.iloc[-1])

        if atr_value <= 0:
            latest_close = cls._safe_float(bars["close"].iloc[-1])
            atr_value = latest_close * 0.02 if latest_close > 0 else 1.0

        reversal_amount = atr_value * max(cls._safe_float(reversal_atr, 1.0), 0.25)
        avg_volume_20 = cls._safe_float(bars["volume"].tail(20).mean())

        raw_waves = cls._build_raw_waves(bars, reversal_amount)
        waves = cls._decorate_waves(bars, raw_waves, atr_value, avg_volume_20)

        evidence = cls._evidence_from_waves(waves)

        return {
            "symbol": symbol,
            "engine": "WEIS_WAVE",
            "status": "OK" if waves else "NO_COMPLETED_WAVES",
            "bars_count": int(len(bars)),
            "wave_count": int(len(waves)),
            "reversal_atr": round(reversal_atr, 4),
            "reversal_amount": round(reversal_amount, 6),
            "atr_value": round(atr_value, 6),
            "latest_wave": waves[-1] if waves else None,
            "waves": waves[-20:],
            "evidence": evidence,
            "warnings": [] if waves else ["No completed Weis waves at selected reversal size."],
        }
