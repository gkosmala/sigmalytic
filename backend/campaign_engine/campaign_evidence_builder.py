"""
backend/campaign_engine/campaign_evidence_builder.py

Sigmalytic V2
True OHLCV-Based Campaign Evidence Builder

Purpose:
Convert raw OHLCV bars into explicit Wyckoff / Livermore / Weis evidence.

Important:
This file does NOT derive evidence from birth_score, MCI, survival_score,
or any other existing campaign score.

Evidence must come from tape behavior:
- price
- spread
- volume
- close location
- pivots
- reactions
- thrust
- follow-through
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


class CampaignEvidenceBuilder:
    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            if pd.isna(value):
                return default
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _prepare(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        for col in ["open", "high", "low", "close", "volume"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")

        out = out.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)

        out["spread"] = (out["high"] - out["low"]).replace(0, np.nan)
        out["body"] = out["close"] - out["open"]
        out["close_location"] = ((out["close"] - out["low"]) / out["spread"]).replace([np.inf, -np.inf], np.nan).fillna(0.5)
        out["down_result"] = (out["open"] - out["close"]).clip(lower=0)
        out["up_result"] = (out["close"] - out["open"]).clip(lower=0)

        out["vol_ma20"] = out["volume"].rolling(20, min_periods=5).mean()
        out["spread_ma20"] = out["spread"].rolling(20, min_periods=5).mean()
        out["close_ma10"] = out["close"].rolling(10, min_periods=5).mean()
        out["close_ma20"] = out["close"].rolling(20, min_periods=10).mean()

        out["effort_ratio"] = (out["volume"] / out["vol_ma20"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        out["spread_ratio"] = (out["spread"] / out["spread_ma20"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)

        return out

    @classmethod
    def build_from_bars(
        cls,
        df: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "DAILY",
        lookback: int = 60,
    ) -> Dict[str, Any]:
        """
        Build Wyckoff / Livermore / Weis evidence from actual OHLCV bars only.
        """

        if df is None or df.empty or len(df) < 30:
            return cls.empty(symbol=symbol, timeframe=timeframe, reason="INSUFFICIENT_BARS")

        bars = cls._prepare(df)

        if len(bars) < 30:
            return cls.empty(symbol=symbol, timeframe=timeframe, reason="INSUFFICIENT_CLEAN_BARS")

        recent = bars.tail(min(lookback, len(bars))).copy()
        last20 = bars.tail(20).copy()
        last10 = bars.tail(10).copy()
        last5 = bars.tail(5).copy()

        latest = bars.iloc[-1]

        # ------------------------------------------------------------
        # Wyckoff: persistent absorption
        # High effort, limited downside result, constructive close location.
        # ------------------------------------------------------------
        absorption_bars = recent[
            (recent["effort_ratio"] >= 1.25)
            & (recent["spread_ratio"] <= 1.20)
            & (recent["close_location"] >= 0.55)
        ]

        persistent_absorption = int(len(absorption_bars)) >= 3

        # ------------------------------------------------------------
        # Wyckoff: failing downside result
        # Sellers try, but bars close off lows and downside progress is limited.
        # ------------------------------------------------------------
        down_effort = recent[
            (recent["body"] < 0)
            & (recent["effort_ratio"] >= 1.10)
        ]

        failing_downside_count = int(
            (
                (down_effort["close_location"] >= 0.45)
                & (down_effort["spread_ratio"] <= 1.25)
            ).sum()
        ) if len(down_effort) else 0

        failing_downside_result = failing_downside_count >= 2

        # ------------------------------------------------------------
        # Wyckoff: successful test
        # Pullback toward recent support, lower volume, narrow spread,
        # constructive close, no breakdown.
        # ------------------------------------------------------------
        prior_support = cls._safe_float(bars["low"].tail(40).min())
        latest_low = cls._safe_float(latest["low"])
        latest_close = cls._safe_float(latest["close"])
        latest_volume = cls._safe_float(latest["volume"])
        vol20 = cls._safe_float(latest["vol_ma20"], 1.0)
        latest_spread_ratio = cls._safe_float(latest["spread_ratio"], 1.0)
        latest_close_location = cls._safe_float(latest["close_location"], 0.5)

        near_support = prior_support > 0 and latest_low <= prior_support * 1.03
        volume_dry_up = vol20 > 0 and latest_volume <= vol20 * 0.90
        narrow_spread = latest_spread_ratio <= 0.90
        constructive_close = latest_close_location >= 0.50
        held_support = prior_support > 0 and latest_close >= prior_support

        successful_test = bool(
            near_support
            and volume_dry_up
            and narrow_spread
            and constructive_close
            and held_support
        )

        # ------------------------------------------------------------
        # Wyckoff: supply failure
        # Intraday/recent break attempt reclaimed.
        # ------------------------------------------------------------
        recent_support = cls._safe_float(bars["low"].tail(20).iloc[:-1].min()) if len(bars) > 21 else prior_support

        broke_support_intraday = recent_support > 0 and latest_low < recent_support
        reclaimed_support = recent_support > 0 and latest_close > recent_support
        supply_failure = bool(
            broke_support_intraday
            and reclaimed_support
            and latest_close_location >= 0.60
        )

        # ------------------------------------------------------------
        # Livermore: higher pivot
        # Use simple rolling swing lows/highs.
        # ------------------------------------------------------------
        lows = bars["low"].tail(60).reset_index(drop=True)
        highs = bars["high"].tail(60).reset_index(drop=True)

        pivot_lows = []
        pivot_highs = []

        for i in range(2, len(lows) - 2):
            if lows.iloc[i] < lows.iloc[i - 1] and lows.iloc[i] < lows.iloc[i + 1]:
                pivot_lows.append(float(lows.iloc[i]))
            if highs.iloc[i] > highs.iloc[i - 1] and highs.iloc[i] > highs.iloc[i + 1]:
                pivot_highs.append(float(highs.iloc[i]))

        higher_pivot = False
        if len(pivot_lows) >= 2:
            higher_pivot = pivot_lows[-1] > pivot_lows[-2]

        # ------------------------------------------------------------
        # Livermore: line of least resistance
        # Direction where price is making easier progress.
        # ------------------------------------------------------------
        close_now = cls._safe_float(bars["close"].iloc[-1])
        close_10 = cls._safe_float(bars["close"].iloc[-10]) if len(bars) >= 10 else close_now
        close_20 = cls._safe_float(bars["close"].iloc[-20]) if len(bars) >= 20 else close_now

        upside_progress = close_now > close_10 and close_now > close_20
        support_intact = close_now >= cls._safe_float(bars["low"].tail(20).min())

        if higher_pivot and upside_progress and support_intact:
            line_of_least_resistance = "UPWARD"
        elif close_now < close_10 and close_now < close_20:
            line_of_least_resistance = "DOWNWARD"
        else:
            line_of_least_resistance = "NEUTRAL"

        # ------------------------------------------------------------
        # Weis: demand dominance
        # Up bars produce better result than down bars.
        # ------------------------------------------------------------
        up_bars = last20[last20["body"] > 0]
        down_bars = last20[last20["body"] < 0]

        up_progress = cls._safe_float(up_bars["up_result"].sum())
        down_progress = cls._safe_float(down_bars["down_result"].sum())

        up_volume = cls._safe_float(up_bars["volume"].sum(), 1.0)
        down_volume = cls._safe_float(down_bars["volume"].sum(), 1.0)

        up_efficiency = up_progress / up_volume if up_volume else 0.0
        down_efficiency = down_progress / down_volume if down_volume else 0.0

        demand_dominance = bool(
            up_progress > down_progress
            and up_efficiency >= down_efficiency
        )

        # ------------------------------------------------------------
        # Weis: wave continuity
        # Structure holds through reactions.
        # ------------------------------------------------------------
        higher_wave_low = higher_pivot
        wave_structure_broken = close_now < cls._safe_float(bars["low"].tail(20).min())

        wave_continuity = bool(
            higher_wave_low
            and not wave_structure_broken
            and line_of_least_resistance in {"UPWARD", "NEUTRAL"}
        )

        # ------------------------------------------------------------
        # Weis: shortening of downside thrust
        # Recent downside thrust is less damaging than prior downside thrust.
        # ------------------------------------------------------------
        first_half = recent.iloc[: max(1, len(recent) // 2)]
        second_half = recent.iloc[max(1, len(recent) // 2):]

        prior_down_thrust = cls._safe_float(first_half["down_result"].sum())
        current_down_thrust = cls._safe_float(second_half["down_result"].sum())

        shortening_of_downside_thrust = bool(
            prior_down_thrust > 0
            and current_down_thrust <= prior_down_thrust * 0.85
            and latest_close_location >= 0.45
        )

        # ------------------------------------------------------------
        # Context: reaction quality
        # ------------------------------------------------------------
        recent_high = cls._safe_float(bars["high"].tail(40).max())
        recent_low = cls._safe_float(bars["low"].tail(40).min())

        drawdown_from_recent_high = ((recent_high - close_now) / recent_high) if recent_high else 0.0
        range_position = ((close_now - recent_low) / (recent_high - recent_low)) if recent_high > recent_low else 0.5

        if drawdown_from_recent_high <= 0.08 and range_position >= 0.50:
            reaction_quality = "NORMAL"
        elif drawdown_from_recent_high <= 0.04:
            reaction_quality = "SHALLOW"
        elif drawdown_from_recent_high >= 0.18:
            reaction_quality = "ABNORMAL"
        else:
            reaction_quality = "UNKNOWN"

        # ------------------------------------------------------------
        # Context: ease of movement and follow-through
        # ------------------------------------------------------------
        last5_return = ((close_now - cls._safe_float(bars["close"].iloc[-5])) / cls._safe_float(bars["close"].iloc[-5])) if len(bars) >= 5 and cls._safe_float(bars["close"].iloc[-5]) else 0.0
        last5_avg_volume = cls._safe_float(last5["volume"].mean(), 1.0)
        last20_avg_volume = cls._safe_float(last20["volume"].mean(), 1.0)

        ease_of_movement = "HIGH" if last5_return > 0.04 and last5_avg_volume >= last20_avg_volume else "UNKNOWN"
        follow_through = bool(last5_return > 0.03 and close_now >= cls._safe_float(last5["close"].max()) * 0.98)

        raw_metrics = {
            "absorption_bar_count": int(len(absorption_bars)),
            "failing_downside_count": int(failing_downside_count),
            "prior_support": round(prior_support, 4),
            "recent_support": round(recent_support, 4),
            "latest_close_location": round(latest_close_location, 4),
            "latest_effort_ratio": round(cls._safe_float(latest["effort_ratio"], 1.0), 4),
            "latest_spread_ratio": round(latest_spread_ratio, 4),
            "up_progress_20": round(up_progress, 6),
            "down_progress_20": round(down_progress, 6),
            "up_efficiency_20": up_efficiency,
            "down_efficiency_20": down_efficiency,
            "prior_down_thrust": round(prior_down_thrust, 6),
            "current_down_thrust": round(current_down_thrust, 6),
            "drawdown_from_recent_high": round(drawdown_from_recent_high, 6),
            "range_position_40": round(range_position, 6),
            "last5_return": round(last5_return, 6),
        }

        evidence = {
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
            "wyckoff": {
                "persistent_absorption": bool(persistent_absorption),
                "failing_downside_result": bool(failing_downside_result),
                "successful_test": bool(successful_test),
                "supply_failure": bool(supply_failure),
            },
            "livermore": {
                "higher_pivot": bool(higher_pivot),
                "line_of_least_resistance": line_of_least_resistance,
            },
            "weis": {
                "demand_dominance": bool(demand_dominance),
                "wave_continuity": bool(wave_continuity),
                "shortening_of_downside_thrust": bool(shortening_of_downside_thrust),
            },
            "context": {
                "reaction_quality": reaction_quality,
                "ease_of_movement": ease_of_movement,
                "follow_through": bool(follow_through),
            },
            "raw_metrics": raw_metrics,
        }

        return evidence

    @staticmethod
    def empty(symbol: str = "", timeframe: str = "DAILY", reason: str = "EMPTY") -> Dict[str, Any]:
        return {
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
            "wyckoff": {
                "persistent_absorption": False,
                "failing_downside_result": False,
                "successful_test": False,
                "supply_failure": False,
            },
            "livermore": {
                "higher_pivot": False,
                "line_of_least_resistance": "NEUTRAL",
            },
            "weis": {
                "demand_dominance": False,
                "wave_continuity": False,
                "shortening_of_downside_thrust": False,
            },
            "context": {
                "reaction_quality": "UNKNOWN",
                "ease_of_movement": "UNKNOWN",
                "follow_through": False,
            },
            "raw_metrics": {
                "reason": reason,
            },
        }
