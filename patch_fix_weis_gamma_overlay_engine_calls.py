from pathlib import Path

path = Path("backend/campaign_engine/campaign_evidence_builder.py")
text = path.read_text(encoding="utf-8")

old = '''        attempts = []

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
'''

new = '''        attempts = []

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
'''

if old not in text:
    raise SystemExit("Could not find _engine_build attempts block.")

text = text.replace(old, new, 1)

old_profile_call = '''        symbol_profile = cls._engine_build(
            SymbolBehaviorProfile,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
        )
'''

new_profile_call = '''        symbol_profile = cls._build_symbol_profile_fallback(
            bars=bars,
            symbol=symbol,
        )
'''

if old_profile_call not in text:
    raise SystemExit("Could not find symbol profile call block.")

text = text.replace(old_profile_call, new_profile_call, 1)

insert_before = '''    @classmethod
    def _build_weis_gamma_overlay(
'''

profile_helper = '''    @classmethod
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

'''

if insert_before not in text:
    raise SystemExit("Could not find _build_weis_gamma_overlay insertion point.")

text = text.replace(insert_before, profile_helper + insert_before, 1)

path.write_text(text, encoding="utf-8")
print("Patched engine dispatcher and symbol profile fallback.")
