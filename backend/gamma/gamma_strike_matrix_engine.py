from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Union

import math
import pandas as pd


@dataclass
class GammaWall:
    strike: float
    wall_type: str
    distance_to_spot: float
    distance_to_spot_pct: float

    call_open_interest: float
    put_open_interest: float
    call_volume: float
    put_volume: float

    call_wall_strength: float
    put_wall_strength: float
    total_wall_strength: float

    net_gamma_exposure: float
    net_delta_shares: float

    zero_dte_volume: float
    zero_dte_open_interest: float
    zero_dte_vol_oi_ratio: float

    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GammaStrikeMatrixEngine:
    """
    Gamma Strike Matrix Engine.

    Purpose:
    - Track multiple strike walls at the same time.
    - Identify top call walls, top put walls, nearest walls above/below spot,
      zero-gamma estimate, net gamma regime, and 0DTE pressure.
    - This module does NOT create trades.
    - This module does NOT replace Weis.
    - It creates the gamma battlefield that the Weis-Gamma Fusion Engine will use.

    Required input can be a pandas DataFrame or list of dictionaries.

    Expected columns, flexible naming supported:
    - strike
    - option_type / type / right  -> CALL or PUT
    - open_interest / oi
    - volume
    - gamma_exposure / gex / net_gamma
    - net_delta_shares / delta_shares
    - dte
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
                    "gamma_exposure",
                    "net_delta_shares",
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

        out["gamma_exposure"] = pd.to_numeric(
            cls._coalesce_column(df, ["gamma_exposure", "gex", "net_gamma", "gamma"]),
            errors="coerce",
        ).fillna(0.0)

        out["net_delta_shares"] = pd.to_numeric(
            cls._coalesce_column(df, ["net_delta_shares", "delta_shares", "net_delta", "dealer_delta"]),
            errors="coerce",
        ).fillna(0.0)

        out["dte"] = pd.to_numeric(
            cls._coalesce_column(df, ["dte", "days_to_expiration", "daysToExpiration"]),
            errors="coerce",
        ).fillna(9999)

        out = out.dropna(subset=["strike"]).reset_index(drop=True)

        return out

    @classmethod
    def _classify_wall_type(cls, call_strength: float, put_strength: float) -> str:
        if call_strength <= 0 and put_strength <= 0:
            return "NO_WALL"

        if call_strength >= put_strength * 1.25:
            return "CALL_WALL"

        if put_strength >= call_strength * 1.25:
            return "PUT_WALL"

        return "MIXED_GAMMA_CLUSTER"

    @classmethod
    def _wall_status(cls, wall: GammaWall, spot_price: float, proximity_pct: float) -> str:
        if abs(wall.distance_to_spot_pct) > proximity_pct:
            return "OUTSIDE_PROXIMITY"

        if wall.wall_type == "CALL_WALL" and wall.strike >= spot_price:
            return "CALL_GAMMA_RESISTANCE"

        if wall.wall_type == "CALL_WALL" and wall.strike < spot_price:
            return "BROKEN_CALL_WALL_BELOW_SPOT"

        if wall.wall_type == "PUT_WALL" and wall.strike <= spot_price:
            return "PUT_GAMMA_SUPPORT"

        if wall.wall_type == "PUT_WALL" and wall.strike > spot_price:
            return "PUT_WALL_ABOVE_SPOT"

        if wall.wall_type == "MIXED_GAMMA_CLUSTER":
            return "MIXED_PIN_ZONE"

        return "MONITORING"

    @classmethod
    def _estimate_zero_gamma_level(cls, grouped: pd.DataFrame) -> Optional[float]:
        if grouped.empty or "net_gamma_exposure" not in grouped.columns:
            return None

        ordered = grouped.sort_values("strike").reset_index(drop=True)
        cumulative = ordered["net_gamma_exposure"].cumsum()

        if len(cumulative) == 0:
            return None

        # FIX (2026-07-30): confirmed via a real AAPL request that this
        # was returning $5 as the "zero gamma level" for a stock trading
        # around $302. Root cause: many deep out-of-the-money strikes at
        # the low end of a sorted chain genuinely have zero gamma
        # exposure (no real open interest/activity there), so the
        # cumulative sum sits at exactly 0 through a long leading run of
        # them -- and the old "if prev_val == 0" check treated the very
        # first such occurrence as a genuine sign crossing, returning a
        # spuriously low strike from that leading dead zone rather than
        # the real crossing point near where actual trading activity
        # exists. Skipping past that leading run of trivial zeros before
        # looking for a genuine crossing.
        first_active_idx = None
        for i, val in enumerate(cumulative):
            if cls._safe_float(val) != 0:
                first_active_idx = i
                break
        if first_active_idx is None:
            # Every strike had zero net gamma exposure -- no real signal
            # anywhere in this chain to estimate a crossing from.
            return None

        # First try to locate a genuine sign crossing, only considering
        # the region from the first real (non-zero) activity onward.
        for i in range(max(1, first_active_idx), len(cumulative)):
            prev_val = cls._safe_float(cumulative.iloc[i - 1])
            curr_val = cls._safe_float(cumulative.iloc[i])

            if prev_val != 0 and curr_val == 0:
                return cls._safe_float(ordered["strike"].iloc[i])

            if (prev_val < 0 and curr_val > 0) or (prev_val > 0 and curr_val < 0):
                return cls._safe_float(ordered["strike"].iloc[i])

        # If there is no sign crossing, use the strike where cumulative exposure
        # is closest to zero, again only considering the active region so the
        # leading dead zone of far-OTM zero-exposure strikes can't win by default.
        active_cumulative = cumulative.iloc[first_active_idx:]
        idx = active_cumulative.abs().idxmin()
        return cls._safe_float(ordered["strike"].iloc[idx])

    @classmethod
    def _net_gamma_regime(cls, spot_price: float, zero_gamma_level: Optional[float]) -> str:
        # FIX (2026-07-30): user gave a precise definition of the gamma
        # flip regime: dealers are net long gamma (positive zone) when
        # price is ABOVE the flip level, and net short gamma (negative
        # zone) when price is BELOW it -- the regime is defined by where
        # spot price sits relative to the flip point itself. This
        # previously classified the regime from total_gex (the aggregate
        # GEX summed across the entire chain), a different metric that
        # doesn't directly reference where current price sits relative
        # to the flip level and can diverge from it. Deriving the regime
        # directly from the price-vs-flip-level comparison instead, per
        # the exact definition given.
        if zero_gamma_level is None or zero_gamma_level <= 0 or spot_price <= 0:
            return "NEUTRAL"

        distance_pct = (spot_price - zero_gamma_level) / zero_gamma_level * 100

        if distance_pct >= 2.0:
            return "DEEP_POSITIVE"
        if distance_pct > 0:
            return "POSITIVE"
        if distance_pct <= -2.0:
            return "DEEP_NEGATIVE"
        if distance_pct < 0:
            return "NEGATIVE"
        return "NEUTRAL"

    @classmethod
    def build(
        cls,
        options_data: Union[pd.DataFrame, List[Dict[str, Any]]],
        symbol: str,
        spot_price: float,
        top_n: int = 5,
        proximity_pct: float = 0.015,
        data_age_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []

        spot_price = cls._safe_float(spot_price)

        if spot_price <= 0:
            return {
                "symbol": symbol,
                "engine": "GAMMA_STRIKE_MATRIX",
                "status": "INVALID_SPOT",
                "spot_price": spot_price,
                "warnings": ["Invalid spot price."],
            }

        df = cls._prepare_options_data(options_data)

        if df.empty:
            return {
                "symbol": symbol,
                "engine": "GAMMA_STRIKE_MATRIX",
                "status": "NO_OPTIONS_DATA",
                "spot_price": spot_price,
                "top_call_walls": [],
                "top_put_walls": [],
                "active_walls": [],
                "nearest_wall_above": None,
                "nearest_wall_below": None,
                "nearest_gamma_wall": None,
                "nearest_wall_type": None,
                "zero_gamma_level": None,
                "net_gamma_regime": "UNKNOWN",
                "active_0dte": False,
                "zero_dte_vol_oi_ratio": 0.0,
                "data_age_seconds": data_age_seconds,
                "warnings": ["No options data supplied."],
            }

        df["is_call"] = df["option_type"].isin(cls.CALL_VALUES)
        df["is_put"] = df["option_type"].isin(cls.PUT_VALUES)

        unknown_types = int((~df["is_call"] & ~df["is_put"]).sum())
        if unknown_types:
            warnings.append(f"{unknown_types} contracts had unknown option_type.")

        df["call_open_interest"] = df.apply(lambda r: r["open_interest"] if r["is_call"] else 0.0, axis=1)
        df["put_open_interest"] = df.apply(lambda r: r["open_interest"] if r["is_put"] else 0.0, axis=1)

        df["call_volume"] = df.apply(lambda r: r["volume"] if r["is_call"] else 0.0, axis=1)
        df["put_volume"] = df.apply(lambda r: r["volume"] if r["is_put"] else 0.0, axis=1)

        df["call_gamma_abs"] = df.apply(lambda r: abs(r["gamma_exposure"]) if r["is_call"] else 0.0, axis=1)
        df["put_gamma_abs"] = df.apply(lambda r: abs(r["gamma_exposure"]) if r["is_put"] else 0.0, axis=1)

        df["zero_dte_volume"] = df.apply(lambda r: r["volume"] if cls._safe_float(r["dte"]) <= 0 else 0.0, axis=1)
        df["zero_dte_open_interest"] = df.apply(lambda r: r["open_interest"] if cls._safe_float(r["dte"]) <= 0 else 0.0, axis=1)

        grouped = df.groupby("strike", as_index=False).agg(
            call_open_interest=("call_open_interest", "sum"),
            put_open_interest=("put_open_interest", "sum"),
            call_volume=("call_volume", "sum"),
            put_volume=("put_volume", "sum"),
            call_gamma_abs=("call_gamma_abs", "sum"),
            put_gamma_abs=("put_gamma_abs", "sum"),
            net_gamma_exposure=("gamma_exposure", "sum"),
            net_delta_shares=("net_delta_shares", "sum"),
            zero_dte_volume=("zero_dte_volume", "sum"),
            zero_dte_open_interest=("zero_dte_open_interest", "sum"),
        )

        walls: List[GammaWall] = []

        for _, row in grouped.iterrows():
            strike = cls._safe_float(row["strike"])

            call_oi = cls._safe_float(row["call_open_interest"])
            put_oi = cls._safe_float(row["put_open_interest"])
            call_vol = cls._safe_float(row["call_volume"])
            put_vol = cls._safe_float(row["put_volume"])
            call_gex_abs = cls._safe_float(row["call_gamma_abs"])
            put_gex_abs = cls._safe_float(row["put_gamma_abs"])
            net_gex = cls._safe_float(row["net_gamma_exposure"])
            net_delta = cls._safe_float(row["net_delta_shares"])

            zero_dte_volume = cls._safe_float(row["zero_dte_volume"])
            zero_dte_oi = cls._safe_float(row["zero_dte_open_interest"])
            zero_dte_vol_oi_ratio = round(zero_dte_volume / zero_dte_oi, 4) if zero_dte_oi > 0 else 0.0

            # Wall strength uses exposure first, then OI/volume as fallback.
            call_strength = call_gex_abs + call_oi + call_vol
            put_strength = put_gex_abs + put_oi + put_vol
            total_strength = call_strength + put_strength + abs(net_delta)

            wall_type = cls._classify_wall_type(call_strength, put_strength)

            distance = strike - spot_price
            distance_pct = round(distance / spot_price, 6) if spot_price > 0 else 0.0

            wall = GammaWall(
                strike=round(strike, 6),
                wall_type=wall_type,
                distance_to_spot=round(distance, 6),
                distance_to_spot_pct=distance_pct,
                call_open_interest=round(call_oi, 2),
                put_open_interest=round(put_oi, 2),
                call_volume=round(call_vol, 2),
                put_volume=round(put_vol, 2),
                call_wall_strength=round(call_strength, 2),
                put_wall_strength=round(put_strength, 2),
                total_wall_strength=round(total_strength, 2),
                net_gamma_exposure=round(net_gex, 2),
                net_delta_shares=round(net_delta, 2),
                zero_dte_volume=round(zero_dte_volume, 2),
                zero_dte_open_interest=round(zero_dte_oi, 2),
                zero_dte_vol_oi_ratio=zero_dte_vol_oi_ratio,
                status="PENDING",
            )

            wall.status = cls._wall_status(wall, spot_price, proximity_pct)
            walls.append(wall)

        wall_dicts = [w.to_dict() for w in walls]

        top_call_walls = sorted(
            [w for w in wall_dicts if w["call_wall_strength"] > 0],
            key=lambda x: x["call_wall_strength"],
            reverse=True,
        )[:top_n]

        top_put_walls = sorted(
            [w for w in wall_dicts if w["put_wall_strength"] > 0],
            key=lambda x: x["put_wall_strength"],
            reverse=True,
        )[:top_n]

        active_walls = sorted(
            [w for w in wall_dicts if abs(cls._safe_float(w["distance_to_spot_pct"])) <= proximity_pct],
            key=lambda x: abs(cls._safe_float(x["distance_to_spot_pct"])),
        )

        walls_above = sorted(
            [w for w in wall_dicts if cls._safe_float(w["strike"]) > spot_price],
            key=lambda x: abs(cls._safe_float(x["distance_to_spot"])),
        )

        walls_below = sorted(
            [w for w in wall_dicts if cls._safe_float(w["strike"]) < spot_price],
            key=lambda x: abs(cls._safe_float(x["distance_to_spot"])),
        )

        nearest_wall_above = walls_above[0] if walls_above else None
        nearest_wall_below = walls_below[0] if walls_below else None

        nearest_gamma_wall = None
        if active_walls:
            nearest_gamma_wall = active_walls[0]
        else:
            all_nearest = sorted(wall_dicts, key=lambda x: abs(cls._safe_float(x["distance_to_spot"])))
            nearest_gamma_wall = all_nearest[0] if all_nearest else None

        total_gex = cls._safe_float(grouped["net_gamma_exposure"].sum())
        zero_gamma_level = cls._estimate_zero_gamma_level(grouped)
        net_gamma_regime = cls._net_gamma_regime(spot_price, zero_gamma_level)

        total_zero_dte_volume = cls._safe_float(grouped["zero_dte_volume"].sum())
        total_zero_dte_oi = cls._safe_float(grouped["zero_dte_open_interest"].sum())
        zero_dte_vol_oi_ratio = round(total_zero_dte_volume / total_zero_dte_oi, 4) if total_zero_dte_oi > 0 else 0.0
        active_0dte = bool(total_zero_dte_volume > 0 or total_zero_dte_oi > 0)

        return {
            "symbol": symbol,
            "engine": "GAMMA_STRIKE_MATRIX",
            "status": "OK",
            "spot_price": round(spot_price, 6),
            "proximity_pct": round(proximity_pct, 6),
            "strike_count": int(len(grouped)),
            "contract_count": int(len(df)),
            "top_call_walls": top_call_walls,
            "top_put_walls": top_put_walls,
            "active_walls": active_walls,
            "nearest_wall_above": nearest_wall_above,
            "nearest_wall_below": nearest_wall_below,
            "nearest_gamma_wall": nearest_gamma_wall["strike"] if nearest_gamma_wall else None,
            "nearest_wall_type": nearest_gamma_wall["wall_type"] if nearest_gamma_wall else None,
            "nearest_wall_status": nearest_gamma_wall["status"] if nearest_gamma_wall else None,
            "zero_gamma_level": round(zero_gamma_level, 6) if zero_gamma_level is not None else None,
            "net_gamma_exposure": round(total_gex, 2),
            "net_gamma_regime": net_gamma_regime,
            "active_0dte": active_0dte,
            "zero_dte_volume": round(total_zero_dte_volume, 2),
            "zero_dte_open_interest": round(total_zero_dte_oi, 2),
            "zero_dte_vol_oi_ratio": zero_dte_vol_oi_ratio,
            "data_age_seconds": data_age_seconds,
            "warnings": warnings,
        }
