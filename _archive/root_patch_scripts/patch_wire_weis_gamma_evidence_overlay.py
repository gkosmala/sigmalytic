from pathlib import Path

path = Path("backend/campaign_engine/campaign_evidence_builder.py")
text = path.read_text(encoding="utf-8")

old_import = '''from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
'''

new_import = '''from typing import Any, Dict, Optional

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
'''

if old_import not in text:
    raise SystemExit("Import block not found.")

text = text.replace(old_import, new_import, 1)

old_signature = '''    def build_from_bars(
        cls,
        df: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "DAILY",
        lookback: int = 60,
    ) -> Dict[str, Any]:
'''

new_signature = '''    def build_from_bars(
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
'''

if old_signature not in text:
    raise SystemExit("build_from_bars signature not found.")

text = text.replace(old_signature, new_signature, 1)

insert_after = '''    @staticmethod
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
'''

helper = '''    @staticmethod
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
            attempts.extend([
                ((), {"df": bars, "symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((), {"bars": bars, "symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((bars,), {"symbol": symbol, "timeframe": timeframe, **extra_kwargs}),
                ((symbol, bars), {"timeframe": timeframe, **extra_kwargs}),
                ((bars, symbol), {"timeframe": timeframe, **extra_kwargs}),
            ])

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

        symbol_profile = cls._engine_build(
            SymbolBehaviorProfile,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
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
            gamma_matrix = cls._engine_build(
                GammaStrikeMatrixEngine,
                symbol=symbol,
                timeframe=timeframe,
                extra_kwargs={
                    "option_chain": option_chain,
                    "spot_price": cls._safe_float(bars["close"].iloc[-1]),
                    "market_timestamp": market_timestamp,
                    "vix_level": vix_level,
                    "rvx_level": rvx_level,
                },
            )

            gamma_freshness = cls._engine_build(
                GammaFreshnessEngine,
                symbol=symbol,
                timeframe=timeframe,
                extra_kwargs={
                    "gamma_matrix_result": gamma_matrix,
                    "market_timestamp": market_timestamp,
                    "gamma_snapshot_time": gamma_snapshot_time,
                    "order_book_snapshot_time": order_book_snapshot_time,
                    "vix_level": vix_level,
                    "rvx_level": rvx_level,
                },
            )

            zero_dte = cls._engine_build(
                ZeroDTESqueezeEngine,
                symbol=symbol,
                timeframe=timeframe,
                extra_kwargs={
                    "option_chain": option_chain,
                    "spot_price": cls._safe_float(bars["close"].iloc[-1]),
                    "market_timestamp": market_timestamp,
                    "minutes_to_close": minutes_to_close,
                    "weis_wave_result": weis_wave,
                },
            )

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

'''

if insert_after not in text:
    raise SystemExit("Prepare block not found.")

text = text.replace(insert_after, insert_after + "\n" + helper, 1)

old_overlay_point = '''        evidence = {
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
'''

new_overlay_point = '''        weis_gamma_overlay = cls._build_weis_gamma_overlay(
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
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "DAILY").upper(),
'''

if old_overlay_point not in text:
    raise SystemExit("Evidence payload start not found.")

text = text.replace(old_overlay_point, new_overlay_point, 1)

old_raw_metrics = '''            "raw_metrics": raw_metrics,
        }
'''

new_raw_metrics = '''            "weis_gamma": weis_gamma_overlay,
            "raw_metrics": raw_metrics,
        }
'''

if old_raw_metrics not in text:
    raise SystemExit("raw_metrics payload block not found.")

text = text.replace(old_raw_metrics, new_raw_metrics, 1)

old_empty_raw = '''            "raw_metrics": {
                "reason": reason,
            },
        }
'''

new_empty_raw = '''            "weis_gamma": {
                "status": "EMPTY",
                "wired_into_evidence_builder": True,
                "state_transition_enabled": False,
                "reason": reason,
            },
            "raw_metrics": {
                "reason": reason,
            },
        }
'''

if old_empty_raw not in text:
    raise SystemExit("empty raw_metrics block not found.")

text = text.replace(old_empty_raw, new_empty_raw, 1)

path.write_text(text, encoding="utf-8")
print("Patched campaign_evidence_builder.py with Weis-Gamma evidence overlay.")
