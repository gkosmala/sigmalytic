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

try:
    from backend.campaign_engine.symbol_behavior_profile import SymbolBehaviorProfile
except Exception:
    SymbolBehaviorProfile = None

try:
    from backend.structural.weis_wave_engine import WeisWaveEngine
except Exception:
    WeisWaveEngine = None

try:
    from backend.structural.multi_scale_weis_engine import MultiScaleWeisEngine
except Exception:
    MultiScaleWeisEngine = None

try:
    from backend.gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine
except Exception:
    GammaStrikeMatrixEngine = None

try:
    from backend.gamma.gamma_freshness_engine import GammaFreshnessEngine
except Exception:
    GammaFreshnessEngine = None

try:
    from backend.gamma.zero_dte_squeeze_engine import ZeroDTESqueezeEngine
except Exception:
    ZeroDTESqueezeEngine = None

try:
    from backend.evidence.weis_gamma_fusion_engine import WeisGammaFusionEngine
except Exception:
    WeisGammaFusionEngine = None

try:
    from backend.campaign_engine.weis_phase_engine import WeisPhaseEngine
except Exception:
    WeisPhaseEngine = None

try:
    from backend.campaign_engine.weis_gamma_ranking_engine import WeisGammaRankingEngine
except Exception:
    WeisGammaRankingEngine = None

try:
    from backend.research_engine.vsa_weis_overlay import evaluate_vsa_weis_overlay
except Exception:
    evaluate_vsa_weis_overlay = None


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

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            try:
                return value.to_dict()
            except Exception:
                return {}
        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception:
                return {}
        return {}

    @classmethod
    def _build_transition_readiness_evidence(
        cls,
        bar_depth_profile: Optional[Dict[str, Any]] = None,
        operator_control: Optional[Dict[str, Any]] = None,
        vsa_weis_overlay: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        timeframe: str = "DAILY",
    ) -> Dict[str, Any]:
        """
        Build diagnostic transition-readiness evidence.

        This does not change the campaign state engine.
        It only explains what the current evidence would be ready to support.
        """
        bar_depth_profile = bar_depth_profile or cls._bar_depth_profile(0)
        operator_control = operator_control or {}
        vsa_weis_overlay = vsa_weis_overlay or {}

        bar_count = int(bar_depth_profile.get("bar_count", 0))
        depth_tier = str(bar_depth_profile.get("depth_tier", "UNKNOWN"))
        max_state_by_depth = str(bar_depth_profile.get("max_campaign_state", "NO_CAMPAIGN"))

        operator_confirmed = bool(operator_control.get("operator_control_confirmed", False))
        operator_evidence_count = int(operator_control.get("evidence_count", 0) or 0)
        operator_verdict = str(operator_control.get("verdict", "UNKNOWN"))

        vsa_alert = str(vsa_weis_overlay.get("vsa_alert", "NONE"))
        vsa_bias = str(vsa_weis_overlay.get("vsa_bias", "NEUTRAL"))
        vsa_evidence = vsa_weis_overlay.get("evidence") if isinstance(vsa_weis_overlay.get("evidence"), dict) else {}
        vsa_flag_count = int(sum(1 for value in vsa_evidence.values() if bool(value)))

        blocks = []

        if bar_count < 10:
            blocks.append("INSUFFICIENT_HISTORY_LT_10_BARS")
        if bar_count < 30:
            blocks.append("NOT_ENOUGH_DEPTH_FOR_BIRTH_OR_WATCH")
        if bar_count < 60:
            blocks.append("NOT_ENOUGH_DEPTH_FOR_OPERATOR_CONTROL_CONFIRMATION")
        if bar_count < 120:
            blocks.append("NOT_ENOUGH_DEPTH_FOR_FULL_CAMPAIGN_RANKING")
        if not operator_confirmed:
            blocks.append("OPERATOR_CONTROL_NOT_CONFIRMED")

        micro_observation_ready = bool(bar_count >= 10 and (vsa_flag_count >= 1 or operator_evidence_count >= 1))
        birth_watch_ready = bool(bar_count >= 30 and (vsa_flag_count >= 1 or operator_evidence_count >= 1))
        confirmation_ready = bool(bar_count >= 60 and operator_evidence_count >= 2)
        survival_ready = bool(bar_count >= 60 and operator_confirmed)
        full_campaign_ready = bool(bar_count >= 120 and operator_confirmed)

        if full_campaign_ready:
            readiness_verdict = "FULL_CAMPAIGN_READY_DIAGNOSTIC"
            evidence_supported_state = "MATURING"
        elif survival_ready:
            readiness_verdict = "SURVIVAL_READY_DIAGNOSTIC"
            evidence_supported_state = "SURVIVING"
        elif confirmation_ready:
            readiness_verdict = "CONFIRMATION_READY_DIAGNOSTIC"
            evidence_supported_state = "CONFIRMED"
        elif birth_watch_ready:
            readiness_verdict = "BIRTH_WATCH_READY_DIAGNOSTIC"
            evidence_supported_state = "BIRTH"
        elif micro_observation_ready:
            readiness_verdict = "MICRO_OBSERVATION_ONLY"
            evidence_supported_state = "NO_CAMPAIGN"
        else:
            readiness_verdict = "NOT_READY"
            evidence_supported_state = "NO_CAMPAIGN"

        return {
            "wired_into_evidence_builder": True,
            "diagnostic_only": True,
            "state_transition_enabled": False,
            "score_impact": "NONE",
            "state_impact": "NONE",
            "rank_impact": "NONE",
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
            "bar_count": bar_count,
            "depth_tier": depth_tier,
            "max_campaign_state_by_depth": max_state_by_depth,
            "operator_control_confirmed": operator_confirmed,
            "operator_control_verdict": operator_verdict,
            "operator_control_evidence_count": operator_evidence_count,
            "vsa_alert": vsa_alert,
            "vsa_bias": vsa_bias,
            "vsa_evidence_count": vsa_flag_count,
            "readiness_verdict": readiness_verdict,
            "evidence_supported_state": evidence_supported_state,
            "readiness_flags": {
                "micro_observation_ready": micro_observation_ready,
                "birth_watch_ready": birth_watch_ready,
                "confirmation_ready": confirmation_ready,
                "survival_ready": survival_ready,
                "full_campaign_ready": full_campaign_ready,
            },
            "blocking_reasons": blocks,
        }

    @classmethod
    def _build_operator_control_evidence(
        cls,
        bars: pd.DataFrame,
        bar_depth_profile: Optional[Dict[str, Any]] = None,
        symbol: str = "",
        timeframe: str = "DAILY",
    ) -> Dict[str, Any]:
        """
        Independent operator-control evidence from raw OHLCV tape behavior only.

        Diagnostics only:
        - no score impact
        - no state impact
        - no rank impact
        - not derived from MCI, birth_score, survival_score, or ranking score
        """
        base = {
            "wired_into_evidence_builder": True,
            "method_basis": "RAW_OHLCV_TAPE_BEHAVIOR_ONLY",
            "not_derived_from_scores": True,
            "score_impact": "NONE",
            "state_impact": "NONE",
            "rank_impact": "NONE",
        }

        if bar_depth_profile is None:
            bar_depth_profile = cls._bar_depth_profile(0 if bars is None else len(bars))

        bar_count = int(bar_depth_profile.get("bar_count", 0))

        flags = {
            "absorption_against_resistance": False,
            "supply_failure": False,
            "high_volume_controlled_spread": False,
            "higher_lows_after_tests": False,
            "recapture_after_breakdown": False,
            "shortening_downside_thrust": False,
            "demand_efficiency_dominates_supply": False,
            "survives_adverse_tests": False,
        }

        if bars is None or bars.empty or len(bars) < 30:
            return {
                **base,
                "status": "INSUFFICIENT_DEPTH" if bars is not None and not bars.empty else "EMPTY",
                "symbol": str(symbol or "").upper(),
                "timeframe": str(timeframe or "DAILY").upper(),
                "bar_count": bar_count,
                "minimum_depth_required": 60,
                "depth_requirement_met": False,
                "operator_control_confirmed": False,
                "verdict": "INSUFFICIENT_OPERATOR_CONTROL_HISTORY",
                "evidence_count": 0,
                "evidence_flags": flags,
            }

        recent = bars.tail(min(60, len(bars))).copy()
        last20 = bars.tail(min(20, len(bars))).copy()
        last10 = bars.tail(min(10, len(bars))).copy()
        last5 = bars.tail(min(5, len(bars))).copy()

        close = pd.to_numeric(bars["close"], errors="coerce")
        high = pd.to_numeric(bars["high"], errors="coerce")
        low = pd.to_numeric(bars["low"], errors="coerce")
        volume = pd.to_numeric(bars["volume"], errors="coerce")

        recent_close = pd.to_numeric(recent["close"], errors="coerce")
        recent_high = pd.to_numeric(recent["high"], errors="coerce")
        recent_low = pd.to_numeric(recent["low"], errors="coerce")
        recent_volume = pd.to_numeric(recent["volume"], errors="coerce")

        spread = (high - low).replace(0, np.nan)
        close_location = ((close - low) / spread).clip(lower=0, upper=1).fillna(0.5)
        recent_spread = (recent_high - recent_low).replace(0, np.nan)
        recent_close_location = ((recent_close - recent_low) / recent_spread).clip(lower=0, upper=1).fillna(0.5)

        avg_volume_20 = cls._safe_float(volume.tail(20).mean(), 0.0)
        avg_spread_20 = cls._safe_float(spread.tail(20).mean(), 0.0)
        latest_volume = cls._safe_float(volume.iloc[-1], 0.0)
        latest_spread = cls._safe_float(spread.iloc[-1], 0.0)
        latest_close_location = cls._safe_float(close_location.iloc[-1], 0.5)

        flags["high_volume_controlled_spread"] = bool(
            avg_volume_20 > 0
            and avg_spread_20 > 0
            and latest_volume >= avg_volume_20 * 1.25
            and latest_spread <= avg_spread_20 * 1.15
            and latest_close_location >= 0.55
        )

        resistance_high = cls._safe_float(high.tail(min(40, len(bars))).max(), 0.0)
        near_resistance = recent_high >= resistance_high * 0.97 if resistance_high else recent_high * 0 == 1
        absorption_mask = (
            (recent_volume >= cls._safe_float(recent_volume.mean(), 0.0) * 1.15)
            & (recent_spread <= cls._safe_float(recent_spread.mean(), 0.0) * 1.15)
            & (recent_close_location >= 0.50)
            & near_resistance
        )
        flags["absorption_against_resistance"] = bool(int(absorption_mask.sum()) >= 3)

        recent_body = recent_close.diff().fillna(0.0)
        down_mask = recent_body < 0
        up_mask = recent_body > 0

        down_spread = recent_spread[down_mask]
        down_volume = recent_volume[down_mask]
        down_close_location = recent_close_location[down_mask]

        flags["supply_failure"] = bool(
            len(down_spread) >= 3
            and cls._safe_float(down_volume.mean(), 0.0) >= cls._safe_float(recent_volume.mean(), 0.0) * 0.95
            and cls._safe_float(down_close_location.mean(), 0.5) >= 0.38
            and cls._safe_float(recent_close.iloc[-1], 0.0) >= cls._safe_float(recent_close.iloc[0], 0.0) * 0.97
        )

        recent_low_5 = cls._safe_float(pd.to_numeric(last5["low"], errors="coerce").min(), 0.0)
        prior_low_20 = cls._safe_float(pd.to_numeric(bars.tail(25).head(20)["low"], errors="coerce").min(), 0.0) if len(bars) >= 25 else cls._safe_float(low.tail(20).min(), 0.0)
        flags["higher_lows_after_tests"] = bool(recent_low_5 > prior_low_20 * 1.005) if prior_low_20 else False

        support_40 = cls._safe_float(low.tail(min(40, len(bars))).min(), 0.0)
        last10_low = cls._safe_float(pd.to_numeric(last10["low"], errors="coerce").min(), 0.0)
        close_now = cls._safe_float(close.iloc[-1], 0.0)
        flags["recapture_after_breakdown"] = bool(support_40 and last10_low <= support_40 * 1.01 and close_now >= support_40 * 1.03)

        recent_down_spreads = down_spread.dropna()
        if len(recent_down_spreads) >= 6:
            early_down = cls._safe_float(recent_down_spreads.head(len(recent_down_spreads) // 2).mean(), 0.0)
            late_down = cls._safe_float(recent_down_spreads.tail(len(recent_down_spreads) // 2).mean(), 0.0)
            flags["shortening_downside_thrust"] = bool(early_down > 0 and late_down <= early_down * 0.85)

        up_progress = cls._safe_float(recent_body[up_mask].sum(), 0.0)
        down_progress = abs(cls._safe_float(recent_body[down_mask].sum(), 0.0))
        up_volume = cls._safe_float(recent_volume[up_mask].sum(), 0.0)
        down_volume_total = cls._safe_float(recent_volume[down_mask].sum(), 0.0)

        demand_efficiency = up_progress / up_volume if up_volume else 0.0
        supply_efficiency = down_progress / down_volume_total if down_volume_total else 0.0

        flags["demand_efficiency_dominates_supply"] = bool(
            demand_efficiency > 0
            and supply_efficiency > 0
            and demand_efficiency >= supply_efficiency * 1.15
        )

        last10_close_min = cls._safe_float(pd.to_numeric(last10["close"], errors="coerce").min(), 0.0)
        last20_low_min = cls._safe_float(pd.to_numeric(last20["low"], errors="coerce").min(), 0.0)
        flags["survives_adverse_tests"] = bool(
            last20_low_min
            and last10_low <= last20_low_min * 1.02
            and close_now >= last10_close_min * 1.03
            and latest_close_location >= 0.45
        )

        evidence_count = int(sum(1 for value in flags.values() if value))
        depth_requirement_met = bool(bar_count >= 60)
        operator_control_confirmed = bool(depth_requirement_met and evidence_count >= 3)

        return {
            **base,
            "status": "OK",
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
            "bar_count": bar_count,
            "minimum_depth_required": 60,
            "depth_requirement_met": depth_requirement_met,
            "operator_control_confirmed": operator_control_confirmed,
            "verdict": "OPERATOR_CONTROL_EVIDENCED" if operator_control_confirmed else "OPERATOR_CONTROL_NOT_CONFIRMED",
            "evidence_count": evidence_count,
            "evidence_flags": flags,
            "raw_measurements": {
                "avg_volume_20": avg_volume_20,
                "avg_spread_20": avg_spread_20,
                "latest_volume": latest_volume,
                "latest_spread": latest_spread,
                "latest_close_location": latest_close_location,
                "demand_efficiency": demand_efficiency,
                "supply_efficiency": supply_efficiency,
            },
        }

    @staticmethod
    def _bar_depth_profile(bar_count: int) -> Dict[str, Any]:
        """
        Classify historical bar depth for campaign evidence eligibility.

        Informational diagnostics only:
        - no score impact
        - no state impact
        - no rank impact
        """
        try:
            count = int(bar_count or 0)
        except Exception:
            count = 0

        count = max(0, count)

        base = {
            "bar_count": count,
            "score_impact": "NONE",
            "state_impact": "NONE",
            "rank_impact": "NONE",
        }

        if count < 10:
            return {
                **base,
                "eligible": False,
                "depth_tier": "INSUFFICIENT_HISTORY",
                "diagnostic_key": "bar_depth_insufficient",
                "observation_mode": "REJECT",
                "max_campaign_state": "NO_CAMPAIGN",
                "ranking_eligible": False,
                "full_campaign_eligible": False,
                "allowed_evidence": [],
                "reason": "Fewer than 10 clean bars; insufficient history for campaign evidence.",
            }

        if count < 30:
            return {
                **base,
                "eligible": True,
                "depth_tier": "MICRO_ONLY",
                "diagnostic_key": "bar_depth_micro",
                "observation_mode": "MICRO_EFFORT_RESULT_ONLY",
                "max_campaign_state": "NO_CAMPAIGN",
                "ranking_eligible": False,
                "full_campaign_eligible": False,
                "allowed_evidence": [
                    "vsa_micro_observation",
                    "effort_vs_result_micro",
                ],
                "reason": "10-29 clean bars; allow only micro VSA / Effort-vs-Result observation, not full campaign state.",
            }

        if count < 60:
            return {
                **base,
                "eligible": True,
                "depth_tier": "ABSORPTION_WATCH",
                "diagnostic_key": "bar_depth_absorption",
                "observation_mode": "ABSORPTION_SPRING_UPTHRUST_WATCH",
                "max_campaign_state": "BIRTH",
                "ranking_eligible": False,
                "full_campaign_eligible": False,
                "allowed_evidence": [
                    "vsa_micro_observation",
                    "effort_vs_result",
                    "absorption_watch",
                    "spring_watch",
                    "upthrust_watch",
                    "birth_candidate",
                ],
                "reason": "30-59 clean bars; enough for watch/birth evidence, not enough for full campaign ranking.",
            }

        if count < 120:
            return {
                **base,
                "eligible": True,
                "depth_tier": "SURVIVAL_OPERATOR_CONTROL",
                "diagnostic_key": "bar_depth_survival",
                "observation_mode": "SURVIVAL_AND_OPERATOR_CONTROL_EVIDENCE",
                "max_campaign_state": "SURVIVING",
                "ranking_eligible": False,
                "full_campaign_eligible": False,
                "allowed_evidence": [
                    "vsa_micro_observation",
                    "effort_vs_result",
                    "absorption",
                    "spring_upthrust_test",
                    "operator_control_evidence",
                    "campaign_survival_evidence",
                ],
                "reason": "60-119 clean bars; enough for survival/operator-control evidence, not enough for full campaign ranking.",
            }

        return {
            **base,
            "eligible": True,
            "depth_tier": "FULL_CAMPAIGN",
            "diagnostic_key": "bar_depth_full_campaign",
            "observation_mode": "FULL_WYCKOFF_LIVERMORE_WEIS_CAMPAIGN",
            "max_campaign_state": "MATURING",
            "ranking_eligible": True,
            "full_campaign_eligible": True,
            "allowed_evidence": [
                "vsa_micro_observation",
                "effort_vs_result",
                "wyckoff_structure",
                "livermore_pivotal_progression",
                "weis_wave_confirmation",
                "operator_control_evidence",
                "campaign_survival_evidence",
                "cause_and_effect",
                "full_campaign_ranking",
            ],
            "reason": "120+ clean bars; eligible for full Wyckoff / Livermore / Weis campaign evidence and ranking diagnostics.",
        }

    @classmethod
    def _engine_build(
        cls,
        engine_cls: Any,
        bars: Optional[pd.DataFrame] = None,
        symbol: str = "",
        timeframe: str = "DAILY",
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if engine_cls is None:
            return {"status": "NOT_AVAILABLE"}

        extra_kwargs = extra_kwargs or {}

        method = None
        for name in ["build_from_bars", "build", "analyze", "run"]:
            candidate = getattr(engine_cls, name, None)
            if callable(candidate):
                method = candidate
                break

        if method is None:
            return {"status": "NO_BUILD_METHOD"}

        attempts = []

        if bars is not None:
            # Try the safest OHLCV signatures first.
            # WeisWaveEngine.build and MultiScaleWeisEngine.build expect:
            # build(df, symbol=...)
            attempts.extend([
                ((bars,), {"symbol": symbol, **extra_kwargs}),
                ((), {"df": bars, "symbol": symbol, **extra_kwargs}),
                ((), {"bars": bars, "symbol": symbol, **extra_kwargs}),
                ((bars, symbol), extra_kwargs),

                # Timeframe-aware variants are attempted only after the
                # no-timeframe signatures.
                ((bars,), {"symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((), {"df": bars, "symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((), {"bars": bars, "symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
            ])
        else:
            attempts.extend([
                ((), {"symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((), {"symbol": symbol, **extra_kwargs}),
                ((symbol,), extra_kwargs),
            ])

        last_error = None

        for args, kwargs in attempts:
            try:
                return cls._as_dict(method(*args, **kwargs))
            except TypeError as exc:
                last_error = str(exc)
                continue
            except Exception as exc:
                return {
                    "status": "ENGINE_ERROR",
                    "engine": getattr(engine_cls, "__name__", str(engine_cls)),
                    "error": str(exc),
                }

        return {
            "status": "CALL_SIGNATURE_MISMATCH",
            "engine": getattr(engine_cls, "__name__", str(engine_cls)),
            "error": last_error,
        }

    @classmethod
    def _build_symbol_profile_fallback(
        cls,
        bars: pd.DataFrame,
        symbol: str,
    ) -> Dict[str, Any]:
        try:
            if bars is None or bars.empty:
                return {"status": "EMPTY", "reason": "NO_BARS"}

            close = pd.to_numeric(bars["close"], errors="coerce")
            high = pd.to_numeric(bars["high"], errors="coerce")
            low = pd.to_numeric(bars["low"], errors="coerce")
            volume = pd.to_numeric(bars["volume"], errors="coerce")

            spread = (high - low).replace(0, np.nan)
            true_range = spread.fillna(0.0)
            atr20 = cls._safe_float(true_range.tail(20).mean())
            latest_close = cls._safe_float(close.iloc[-1])
            atr_pct = atr20 / latest_close if latest_close else 0.0

            avg_volume_20 = cls._safe_float(volume.tail(20).mean())
            avg_volume_50 = cls._safe_float(volume.tail(50).mean())
            latest_volume = cls._safe_float(volume.iloc[-1])
            latest_volume_ratio = latest_volume / avg_volume_20 if avg_volume_20 else 0.0

            vol_std_20 = cls._safe_float(volume.tail(20).std(), 0.0)
            latest_volume_z = ((latest_volume - avg_volume_20) / vol_std_20) if vol_std_20 else 0.0

            recent_high = cls._safe_float(high.tail(60).max())
            recent_low = cls._safe_float(low.tail(60).min())
            latest_range_position_60 = (
                (latest_close - recent_low) / (recent_high - recent_low)
                if recent_high > recent_low
                else 0.5
            )

            close_5 = cls._safe_float(close.iloc[-5]) if len(close) >= 5 else latest_close
            close_20 = cls._safe_float(close.iloc[-20]) if len(close) >= 20 else latest_close

            last5_return = ((latest_close - close_5) / close_5) if close_5 else 0.0
            last20_return = ((latest_close - close_20) / close_20) if close_20 else 0.0

            liquidity_class = "HIGH_LIQUIDITY" if avg_volume_20 >= 1000000 else "LOW_LIQUIDITY"
            volatility_class = "HIGH_VOLATILITY" if atr_pct >= 0.06 else "MEDIUM_VOLATILITY" if atr_pct >= 0.025 else "LOW_VOLATILITY"

            return {
                "status": "OK",
                "fallback_calculated_in_evidence_builder": True,
                "symbol": str(symbol or "").upper(),
                "bars_count": int(len(bars)),
                "atr_20": round(atr20, 6),
                "atr_pct": round(atr_pct, 6),
                "avg_volume_20": round(avg_volume_20, 4),
                "avg_volume_50": round(avg_volume_50, 4),
                "latest_volume_z": round(latest_volume_z, 4),
                "latest_volume_ratio": round(latest_volume_ratio, 4),
                "latest_spread": round(cls._safe_float(spread.iloc[-1]), 6),
                "latest_spread_pct": round(cls._safe_float(spread.iloc[-1]) / latest_close, 6) if latest_close else 0.0,
                "latest_range_position_60": round(latest_range_position_60, 6),
                "last5_return": round(last5_return, 6),
                "last20_return": round(last20_return, 6),
                "liquidity_class": liquidity_class,
                "volatility_class": volatility_class,
                "profile_quality": "FALLBACK",
                "warnings": ["SymbolBehaviorProfile class is a result dataclass; fallback profile was calculated in evidence builder."],
            }
        except Exception as exc:
            return {
                "status": "ENGINE_ERROR",
                "engine": "symbol_behavior_profile_fallback",
                "error": str(exc),
            }

    @classmethod
    def _build_vsa_weis_overlay(
        cls,
        bars: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "DAILY",
    ) -> Dict[str, Any]:
        """
        Build additive VSA/Weis microstructure evidence.

        Informational only:
        - no score impact
        - no state impact
        - no rank impact
        - does not replace existing Wyckoff, Livermore, Weis, or Gamma logic
        """
        base = {
            "wired_into_evidence_builder": True,
            "score_impact": "NONE",
            "state_impact": "NONE",
            "rank_impact": "NONE",
        }

        default_evidence = {
            "buying_climax": False,
            "upthrust_supply": False,
            "no_supply_test": False,
            "no_demand_test": False,
            "effort_vs_result_divergence": False,
        }

        if evaluate_vsa_weis_overlay is None:
            return {
                **base,
                "status": "NOT_AVAILABLE",
                "engine": "evaluate_vsa_weis_overlay",
                "warning": "VSA/Weis overlay import unavailable.",
                "vsa_alert": "NONE",
                "vsa_bias": "NEUTRAL",
                "evidence": default_evidence,
            }

        if bars is None or bars.empty:
            return {
                **base,
                "status": "EMPTY",
                "reason": "NO_BARS",
                "vsa_alert": "NONE",
                "vsa_bias": "NEUTRAL",
                "evidence": default_evidence,
            }

        call_patterns = [
            ((bars,), {"symbol": symbol, "timeframe": timeframe}),
            ((), {"bars": bars, "symbol": symbol, "timeframe": timeframe}),
            ((), {"df": bars, "symbol": symbol, "timeframe": timeframe}),
            ((bars,), {"symbol": symbol}),
            ((bars, symbol), {}),
            ((bars, symbol, timeframe), {}),
            ((bars,), {}),
        ]

        last_type_error = None

        for args, kwargs in call_patterns:
            try:
                raw = cls._as_dict(evaluate_vsa_weis_overlay(*args, **kwargs))
                nested = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}

                return {
                    **base,
                    "status": raw.get("status", "OK"),
                    "engine": "evaluate_vsa_weis_overlay",
                    "vsa_alert": raw.get("vsa_alert", "NONE"),
                    "vsa_bias": raw.get("vsa_bias", "NEUTRAL"),
                    "evidence": {
                        "buying_climax": bool(raw.get("buying_climax", nested.get("buying_climax", False))),
                        "upthrust_supply": bool(raw.get("upthrust_supply", nested.get("upthrust_supply", False))),
                        "no_supply_test": bool(raw.get("no_supply_test", nested.get("no_supply_test", False))),
                        "no_demand_test": bool(raw.get("no_demand_test", nested.get("no_demand_test", False))),
                        "effort_vs_result_divergence": bool(
                            raw.get(
                                "effort_vs_result_divergence",
                                nested.get("effort_vs_result_divergence", False),
                            )
                        ),
                    },
                }
            except TypeError as exc:
                last_type_error = exc
                continue
            except Exception as exc:
                return {
                    **base,
                    "status": "ERROR",
                    "engine": "evaluate_vsa_weis_overlay",
                    "error": str(exc),
                    "vsa_alert": "NONE",
                    "vsa_bias": "NEUTRAL",
                    "evidence": default_evidence,
                }

        return {
            **base,
            "status": "NO_COMPATIBLE_CALL_SIGNATURE",
            "engine": "evaluate_vsa_weis_overlay",
            "error": str(last_type_error) if last_type_error else "",
            "vsa_alert": "NONE",
            "vsa_bias": "NEUTRAL",
            "evidence": default_evidence,
        }

    @classmethod
    def _build_weis_gamma_overlay(
        cls,
        bars: pd.DataFrame,
        symbol: str,
        timeframe: str,
        option_chain: Optional[Any] = None,
        market_timestamp: Optional[Any] = None,
        gamma_snapshot_time: Optional[Any] = None,
        order_book_snapshot_time: Optional[Any] = None,
        vix_level: Optional[float] = None,
        rvx_level: Optional[float] = None,
        minutes_to_close: Optional[float] = None,
    ) -> Dict[str, Any]:
        warnings = []

        symbol_profile = cls._build_symbol_profile_fallback(
            bars=bars,
            symbol=symbol,
        )

        weis_wave = cls._engine_build(
            WeisWaveEngine,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
        )

        multi_scale_weis = cls._engine_build(
            MultiScaleWeisEngine,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
        )

        if option_chain is None:
            gamma_matrix = {
                "status": "NO_OPTION_CHAIN_INPUT",
                "gamma_data_fresh": False,
                "warning": "No option chain supplied to campaign evidence builder.",
            }
            gamma_freshness = {
                "status": "NO_GAMMA_INPUT",
                "router_state": "YELLOW",
                "gamma_data_fresh": False,
                "phase_confidence_modifier": 0.35,
                "warning": "Gamma freshness cannot confirm without Gamma/options input.",
            }
            zero_dte = {
                "status": "NO_OPTION_CHAIN_INPUT",
                "active_0dte": False,
                "squeeze_state": "NO_0DTE_INPUT",
                "zero_dte_vol_oi_ratio": 0.0,
                "theta_flush_risk": False,
                "liquidation_risk": False,
                "confidence": 0.0,
            }
            warnings.append("Weis-only overlay created because no option chain was supplied.")
        else:
            spot_price = cls._safe_float(bars["close"].iloc[-1])

            try:
                close_location = cls._safe_float(bars["close_location"].iloc[-1], 0.5)
            except Exception:
                close_location = 0.5

            wave_direction = str(
                weis_wave.get("wave_direction")
                or weis_wave.get("direction")
                or "UNKNOWN"
            )

            wave_efficiency = cls._safe_float(
                weis_wave.get("wave_efficiency")
                or weis_wave.get("efficiency")
                or 0.0
            )

            if GammaStrikeMatrixEngine is None:
                gamma_matrix = {
                    "status": "NOT_AVAILABLE",
                    "engine": "GammaStrikeMatrixEngine",
                    "warning": "GammaStrikeMatrixEngine import unavailable.",
                }
            else:
                try:
                    gamma_matrix = cls._as_dict(
                        GammaStrikeMatrixEngine.build(
                            options_data=option_chain,
                            symbol=symbol,
                            spot_price=spot_price,
                            top_n=5,
                            proximity_pct=0.015,
                            data_age_seconds=0.0,
                        )
                    )
                except TypeError as exc:
                    gamma_matrix = {
                        "status": "CALL_SIGNATURE_MISMATCH",
                        "engine": "GammaStrikeMatrixEngine",
                        "error": str(exc),
                    }
                except Exception as exc:
                    gamma_matrix = {
                        "status": "ENGINE_ERROR",
                        "engine": "GammaStrikeMatrixEngine",
                        "error": str(exc),
                    }

            if ZeroDTESqueezeEngine is None:
                zero_dte = {
                    "status": "NOT_AVAILABLE",
                    "active_0dte": False,
                    "squeeze_state": "NO_0DTE_ENGINE",
                    "zero_dte_vol_oi_ratio": 0.0,
                    "theta_flush_risk": False,
                    "liquidation_risk": False,
                    "confidence": 0.0,
                }
            else:
                try:
                    zero_dte = cls._as_dict(
                        ZeroDTESqueezeEngine.build(
                            options_data=option_chain,
                            symbol=symbol,
                            spot_price=spot_price,
                            close_location=close_location,
                            wave_direction=wave_direction,
                            wave_efficiency=wave_efficiency,
                            minutes_to_close=minutes_to_close,
                        )
                    )
                except TypeError as exc:
                    zero_dte = {
                        "status": "CALL_SIGNATURE_MISMATCH",
                        "engine": "ZeroDTESqueezeEngine",
                        "error": str(exc),
                        "active_0dte": False,
                        "squeeze_state": "CALL_SIGNATURE_MISMATCH",
                        "zero_dte_vol_oi_ratio": 0.0,
                        "theta_flush_risk": False,
                        "liquidation_risk": False,
                        "confidence": 0.0,
                    }
                except Exception as exc:
                    zero_dte = {
                        "status": "ENGINE_ERROR",
                        "engine": "ZeroDTESqueezeEngine",
                        "error": str(exc),
                        "active_0dte": False,
                        "squeeze_state": "ENGINE_ERROR",
                        "zero_dte_vol_oi_ratio": 0.0,
                        "theta_flush_risk": False,
                        "liquidation_risk": False,
                        "confidence": 0.0,
                    }

            gamma_regime = str(
                gamma_matrix.get("net_gamma_regime")
                or gamma_matrix.get("gamma_regime")
                or "UNKNOWN"
            )

            timeframe_profile = (
                "SWING"
                if str(timeframe or "").upper() in {"DAILY", "WEEKLY", "MONTHLY"}
                else "INTRADAY"
            )

            if GammaFreshnessEngine is None:
                gamma_freshness = {
                    "status": "NOT_AVAILABLE",
                    "router_state": "YELLOW",
                    "gamma_data_fresh": False,
                    "phase_confidence_modifier": 0.35,
                    "warning": "GammaFreshnessEngine import unavailable.",
                }
            else:
                try:
                    gamma_freshness = cls._as_dict(
                        GammaFreshnessEngine.build(
                            symbol=symbol,
                            gamma_regime=gamma_regime,
                            vix=vix_level,
                            rvx=rvx_level,
                            timeframe_profile=timeframe_profile,
                            active_0dte=bool(zero_dte.get("active_0dte", False)),
                            zero_dte_vol_oi_ratio=cls._safe_float(
                                zero_dte.get("zero_dte_vol_oi_ratio"), 0.0
                            ),
                            gamma_data_age_seconds=0.0,
                            order_book_age_seconds=0.0 if order_book_snapshot_time else None,
                            intraday_wave_age_seconds=0.0,
                            campaign_state_age_seconds=0.0,
                        )
                    )
                except TypeError as exc:
                    gamma_freshness = {
                        "status": "CALL_SIGNATURE_MISMATCH",
                        "engine": "GammaFreshnessEngine",
                        "error": str(exc),
                        "router_state": "YELLOW",
                        "gamma_data_fresh": False,
                        "phase_confidence_modifier": 0.35,
                    }
                except Exception as exc:
                    gamma_freshness = {
                        "status": "ENGINE_ERROR",
                        "engine": "GammaFreshnessEngine",
                        "error": str(exc),
                        "router_state": "YELLOW",
                        "gamma_data_fresh": False,
                        "phase_confidence_modifier": 0.35,
                    }

        fusion = cls._engine_build(
            WeisGammaFusionEngine,
            symbol=symbol,
            timeframe=timeframe,
            extra_kwargs={
                "weis_wave_result": weis_wave,
                "multi_scale_weis_result": multi_scale_weis,
                "gamma_matrix_result": gamma_matrix,
                "gamma_freshness_result": gamma_freshness,
                "zero_dte_result": zero_dte,
            },
        )

        phase = cls._engine_build(
            WeisPhaseEngine,
            symbol=symbol,
            timeframe=timeframe,
            extra_kwargs={
                "weis_wave_result": weis_wave,
                "multi_scale_weis_result": multi_scale_weis,
                "weis_gamma_fusion_result": fusion,
            },
        )

        ranking = cls._engine_build(
            WeisGammaRankingEngine,
            symbol=symbol,
            timeframe=timeframe,
            extra_kwargs={
                "weis_phase_result": phase,
                "weis_wave_result": weis_wave,
                "multi_scale_weis_result": multi_scale_weis,
                "gamma_matrix_result": gamma_matrix,
                "gamma_freshness_result": gamma_freshness,
                "zero_dte_result": zero_dte,
                "weis_gamma_fusion_result": fusion,
            },
        )

        return {
            "status": "OK",
            "wired_into_evidence_builder": True,
            "state_transition_enabled": False,
            "symbol_behavior_profile": symbol_profile,
            "weis_wave": weis_wave,
            "multi_scale_weis": multi_scale_weis,
            "gamma_matrix": gamma_matrix,
            "gamma_freshness": gamma_freshness,
            "zero_dte": zero_dte,
            "fusion": fusion,
            "phase": phase,
            "ranking": ranking,
            "warnings": warnings,
        }


    @classmethod
    def build_from_bars(
        cls,
        df: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "DAILY",
        lookback: int = 60,
        option_chain: Optional[Any] = None,
        market_timestamp: Optional[Any] = None,
        gamma_snapshot_time: Optional[Any] = None,
        order_book_snapshot_time: Optional[Any] = None,
        vix_level: Optional[float] = None,
        rvx_level: Optional[float] = None,
        minutes_to_close: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Build Wyckoff / Livermore / Weis evidence from actual OHLCV bars only.
        """

        if df is None or df.empty or len(df) < 30:
            return cls.empty(symbol=symbol, timeframe=timeframe, reason="INSUFFICIENT_BARS", bar_count=0)

        bars = cls._prepare(df)
        bar_count = int(len(bars))
        bar_depth_profile = cls._bar_depth_profile(bar_count)

        if len(bars) < 30:
            return cls.empty(symbol=symbol, timeframe=timeframe, reason="INSUFFICIENT_CLEAN_BARS", bar_count=bar_count, bar_depth_profile=bar_depth_profile)

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

        operator_control = cls._build_operator_control_evidence(
            bars=bars,
            bar_depth_profile=bar_depth_profile,
            symbol=symbol,
            timeframe=timeframe,
        )

        vsa_weis_overlay = cls._build_vsa_weis_overlay(
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
        )

        transition_readiness = cls._build_transition_readiness_evidence(
            bar_depth_profile=bar_depth_profile,
            operator_control=operator_control,
            vsa_weis_overlay=vsa_weis_overlay,
            symbol=symbol,
            timeframe=timeframe,
        )

        raw_metrics = {
            "bar_count": int(len(bars)),
            "bar_depth_tier": bar_depth_profile.get("depth_tier"),
            "bar_depth_diagnostic_key": bar_depth_profile.get("diagnostic_key"),
            "max_campaign_state_by_depth": bar_depth_profile.get("max_campaign_state"),
            "bar_depth_ranking_eligible": bool(bar_depth_profile.get("ranking_eligible", False)),
            "bar_depth_full_campaign_eligible": bool(bar_depth_profile.get("full_campaign_eligible", False)),
            "operator_control_confirmed": bool(operator_control.get("operator_control_confirmed", False)),
            "operator_control_verdict": operator_control.get("verdict"),
            "operator_control_evidence_count": int(operator_control.get("evidence_count", 0)),
            "transition_readiness_verdict": transition_readiness.get("readiness_verdict"),
            "transition_evidence_supported_state": transition_readiness.get("evidence_supported_state"),
            "transition_state_transition_enabled": bool(transition_readiness.get("state_transition_enabled", False)),
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

        weis_gamma_overlay = cls._build_weis_gamma_overlay(
            bars=bars,
            symbol=str(symbol or "").upper(),
            timeframe=str(timeframe or "DAILY").upper(),
            option_chain=option_chain,
            market_timestamp=market_timestamp,
            gamma_snapshot_time=gamma_snapshot_time,
            order_book_snapshot_time=order_book_snapshot_time,
            vix_level=vix_level,
            rvx_level=rvx_level,
            minutes_to_close=minutes_to_close,
        )

        evidence = {
            "bar_depth": bar_depth_profile,
            "operator_control": operator_control,
            "transition_readiness": transition_readiness,
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
            "vsa_weis_overlay": vsa_weis_overlay,
            "weis_gamma": weis_gamma_overlay,
            "raw_metrics": raw_metrics,
        }

        return evidence

    @staticmethod
    def empty(symbol: str = "", timeframe: str = "DAILY", reason: str = "EMPTY", bar_count: Optional[int] = None, bar_depth_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if bar_depth_profile is None:
            bar_depth_profile = CampaignEvidenceBuilder._bar_depth_profile(0 if bar_count is None else bar_count)

        return {
            "bar_depth": bar_depth_profile,
            "transition_readiness": {
                "wired_into_evidence_builder": True,
                "diagnostic_only": True,
                "state_transition_enabled": False,
                "score_impact": "NONE",
                "state_impact": "NONE",
                "rank_impact": "NONE",
                "bar_count": int(bar_depth_profile.get("bar_count", 0)),
                "depth_tier": bar_depth_profile.get("depth_tier"),
                "max_campaign_state_by_depth": bar_depth_profile.get("max_campaign_state"),
                "operator_control_confirmed": False,
                "operator_control_verdict": "NO_OPERATOR_CONTROL_EVIDENCE",
                "operator_control_evidence_count": 0,
                "transition_readiness_verdict": "NOT_READY",
                "transition_evidence_supported_state": "NO_CAMPAIGN",
                "transition_state_transition_enabled": False,
                "vsa_alert": "NONE",
                "vsa_bias": "NEUTRAL",
                "vsa_evidence_count": 0,
                "readiness_verdict": "NOT_READY",
                "evidence_supported_state": "NO_CAMPAIGN",
                "readiness_flags": {
                    "micro_observation_ready": False,
                    "birth_watch_ready": False,
                    "confirmation_ready": False,
                    "survival_ready": False,
                    "full_campaign_ready": False,
                },
                "blocking_reasons": [reason],
            },
            "operator_control": {
                "wired_into_evidence_builder": True,
                "method_basis": "RAW_OHLCV_TAPE_BEHAVIOR_ONLY",
                "not_derived_from_scores": True,
                "score_impact": "NONE",
                "state_impact": "NONE",
                "rank_impact": "NONE",
                "status": "EMPTY",
                "reason": reason,
                "bar_count": int(bar_depth_profile.get("bar_count", 0)),
                "minimum_depth_required": 60,
                "depth_requirement_met": False,
                "operator_control_confirmed": False,
                "verdict": "NO_OPERATOR_CONTROL_EVIDENCE",
                "evidence_count": 0,
                "evidence_flags": {
                    "absorption_against_resistance": False,
                    "supply_failure": False,
                    "high_volume_controlled_spread": False,
                    "higher_lows_after_tests": False,
                    "recapture_after_breakdown": False,
                    "shortening_downside_thrust": False,
                    "demand_efficiency_dominates_supply": False,
                    "survives_adverse_tests": False,
                },
            },
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
            "vsa_weis_overlay": {
                "wired_into_evidence_builder": True,
                "score_impact": "NONE",
                "state_impact": "NONE",
                "rank_impact": "NONE",
                "status": "EMPTY",
                "reason": reason,
                "vsa_alert": "NONE",
                "vsa_bias": "NEUTRAL",
                "evidence": {
                    "buying_climax": False,
                    "upthrust_supply": False,
                    "no_supply_test": False,
                    "no_demand_test": False,
                    "effort_vs_result_divergence": False,
                },
            },
            "weis_gamma": {
                "status": "EMPTY",
                "wired_into_evidence_builder": True,
                "state_transition_enabled": False,
                "reason": reason,
            },
            "raw_metrics": {
                "reason": reason,
                "bar_count": int(bar_depth_profile.get("bar_count", 0)),
                "bar_depth_tier": bar_depth_profile.get("depth_tier"),
                "bar_depth_diagnostic_key": bar_depth_profile.get("diagnostic_key"),
                "max_campaign_state_by_depth": bar_depth_profile.get("max_campaign_state"),
                "bar_depth_ranking_eligible": bool(bar_depth_profile.get("ranking_eligible", False)),
                "bar_depth_full_campaign_eligible": bool(bar_depth_profile.get("full_campaign_eligible", False)),
                "operator_control_confirmed": False,
                "operator_control_verdict": "NO_OPERATOR_CONTROL_EVIDENCE",
                "operator_control_evidence_count": 0,
            },
        }
