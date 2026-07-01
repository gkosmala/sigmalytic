"""
Standalone VSA / Weis Overlay Evidence Engine.

This file is isolated.
It does not modify campaign scoring, frontend, radar, admin, preferences, or existing Weis engines.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def _prepare_bars(df: pd.DataFrame) -> pd.DataFrame:
    bars = df.copy()

    rename_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    bars = bars.rename(columns=rename_map)

    required = ["open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in bars.columns]

    if missing:
        raise ValueError(f"Missing required bar columns: {missing}")

    for col in required:
        bars[col] = pd.to_numeric(bars[col], errors="coerce")

    bars = bars.dropna(subset=required).reset_index(drop=True)

    bars["spread"] = (bars["high"] - bars["low"]).replace(0, np.nan)
    bars["spread_avg_20"] = bars["spread"].rolling(window=20, min_periods=5).mean()
    bars["volume_avg_20"] = bars["volume"].rolling(window=20, min_periods=5).mean()

    bars["close_position"] = (
        (bars["close"] - bars["low"]) / bars["spread"]
    ).replace([np.inf, -np.inf], np.nan).fillna(0.5)

    bars["bar_direction"] = np.where(
        bars["close"] > bars["close"].shift(1),
        1,
        np.where(bars["close"] < bars["close"].shift(1), -1, 0),
    )

    bars["bar_direction"] = pd.Series(bars["bar_direction"]).replace(0, np.nan).ffill().fillna(1)
    bars["bar_direction"] = np.where(bars["bar_direction"] >= 0, 1, -1)

    bars["wave_flip"] = bars["bar_direction"] != pd.Series(bars["bar_direction"]).shift(1)
    bars["wave_id"] = bars["wave_flip"].cumsum()

    wave_volume = bars.groupby("wave_id")["volume"].sum()
    bars["weis_wave_volume"] = bars["wave_id"].map(wave_volume) * bars["bar_direction"]

    return bars


def evaluate_vsa_weis_overlay(df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
    bars = _prepare_bars(df)

    if len(bars) < 10:
        return {
            "symbol": symbol,
            "engine": "VSA_WEIS_OVERLAY",
            "status": "INSUFFICIENT_BARS",
            "bar_count": int(len(bars)),
            "minimum_required": 10,
            "warnings": ["At least 10 bars are required for VSA overlay evidence."],
        }

    latest = bars.iloc[-1]

    spread_avg = float(latest.get("spread_avg_20") or 0.0)
    volume_avg = float(latest.get("volume_avg_20") or 0.0)
    spread = float(latest.get("spread") or 0.0)
    volume = float(latest.get("volume") or 0.0)
    close_position = float(latest.get("close_position") or 0.5)
    wave_volume = float(latest.get("weis_wave_volume") or 0.0)
    direction = int(latest.get("bar_direction") or 1)

    buying_climax = bool(
        wave_volume > 0
        and volume_avg > 0
        and spread_avg > 0
        and volume > volume_avg * 2.0
        and spread > spread_avg * 1.5
        and close_position < 0.6
    )

    upthrust_supply = bool(
        len(bars) >= 10
        and float(latest["high"]) >= float(bars["high"].tail(10).max())
        and close_position < 0.3
        and volume_avg > 0
        and volume > volume_avg
    )

    no_supply_test = bool(
        direction == -1
        and spread_avg > 0
        and volume_avg > 0
        and spread < spread_avg
        and volume < volume_avg * 0.7
        and close_position < 0.5
    )

    no_demand_test = bool(
        direction == 1
        and spread_avg > 0
        and volume_avg > 0
        and spread < spread_avg
        and volume < volume_avg * 0.7
        and close_position > 0.5
    )

    effort_vs_result_divergence = bool(
        volume_avg > 0
        and spread_avg > 0
        and volume > volume_avg * 1.8
        and spread < spread_avg * 0.8
    )

    if buying_climax:
        alert = "BUYING_CLIMAX_SUPPLY_ENTERING"
        bias = "BEARISH"
    elif upthrust_supply:
        alert = "UPTHRUST_SUPPLY_RETAIL_TRAP"
        bias = "BEARISH"
    elif no_supply_test:
        alert = "NO_SUPPLY_READY_TO_RALLY"
        bias = "BULLISH"
    elif no_demand_test:
        alert = "NO_DEMAND_LACK_OF_BUYERS"
        bias = "BEARISH"
    elif effort_vs_result_divergence:
        alert = "EFFORT_VS_RESULT_DIVERGENCE"
        bias = "MIXED"
    else:
        alert = "NORMAL_STRUCTURAL_ACTION"
        bias = "NEUTRAL"

    return {
        "symbol": symbol,
        "engine": "VSA_WEIS_OVERLAY",
        "status": "OK",
        "bar_count": int(len(bars)),
        "latest": {
            "spread": round(spread, 6),
            "spread_avg_20": round(spread_avg, 6),
            "volume": round(volume, 2),
            "volume_avg_20": round(volume_avg, 2),
            "close_position": round(close_position, 4),
            "bar_direction": direction,
            "weis_wave_volume": round(wave_volume, 2),
        },
        "evidence": {
            "buying_climax": buying_climax,
            "upthrust_supply": upthrust_supply,
            "no_supply_test": no_supply_test,
            "no_demand_test": no_demand_test,
            "effort_vs_result_divergence": effort_vs_result_divergence,
        },
        "vsa_alert": alert,
        "vsa_bias": bias,
        "warnings": [],
    }


def evaluate_bars(bars: Any, symbol: str = "") -> Dict[str, Any]:
    return evaluate_vsa_weis_overlay(pd.DataFrame(bars), symbol=symbol)
