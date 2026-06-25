from backend.gamma.gamma_freshness_engine import GammaFreshnessEngine

cases = [
    {
        "name": "LOW VOL POSITIVE GAMMA",
        "kwargs": {
            "symbol": "TEST",
            "gamma_regime": "POSITIVE",
            "atr_ratio": 0.75,
            "vix": 14.8,
            "timeframe_profile": "SWING",
            "active_0dte": False,
            "zero_dte_vol_oi_ratio": 0.05,
            "gamma_data_age_seconds": 300,
            "order_book_age_seconds": 1.5,
            "intraday_wave_age_seconds": 120,
            "campaign_state_age_seconds": 3600,
        },
    },
    {
        "name": "HIGH VOL NEGATIVE GAMMA",
        "kwargs": {
            "symbol": "TEST",
            "gamma_regime": "NEGATIVE",
            "atr_ratio": 2.8,
            "vix": 26.5,
            "timeframe_profile": "INTRADAY",
            "active_0dte": True,
            "zero_dte_vol_oi_ratio": 0.55,
            "gamma_data_age_seconds": 45,
            "order_book_age_seconds": 0.4,
            "intraday_wave_age_seconds": 20,
            "campaign_state_age_seconds": 600,
        },
    },
    {
        "name": "CRITICAL STALE DATA",
        "kwargs": {
            "symbol": "TEST",
            "gamma_regime": "DEEP_NEGATIVE",
            "atr_ratio": 4.2,
            "vix": 34.1,
            "timeframe_profile": "SCALP",
            "active_0dte": True,
            "zero_dte_vol_oi_ratio": 1.4,
            "gamma_data_age_seconds": 300,
            "order_book_age_seconds": 5.0,
            "intraday_wave_age_seconds": 200,
            "campaign_state_age_seconds": 5000,
        },
    },
]

for case in cases:
    result = GammaFreshnessEngine.build(**case["kwargs"])
    print("\nCASE:", case["name"])
    print("CONDITION:", result["market_condition"])
    print("ROUTER:", result["router_state"])
    print("GAMMA TTL:", result["gamma_ttl_seconds"])
    print("GAMMA FRESH:", result["gamma_data_fresh"])
    print("ORDER BOOK TTL:", result["order_book_ttl_seconds"])
    print("ORDER BOOK FRESH:", result["order_book_data_fresh"])
    print("WARNING:", result["freshness_warning"])
    print("CONFIDENCE MODIFIER:", result["phase_confidence_modifier"])
