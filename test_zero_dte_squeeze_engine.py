from backend.gamma.zero_dte_squeeze_engine import ZeroDTESqueezeEngine

upside_options = [
    {"strike": 645, "option_type": "CALL", "open_interest": 10000, "volume": 14000, "dte": 0},
    {"strike": 650, "option_type": "CALL", "open_interest": 12000, "volume": 18000, "dte": 0},
    {"strike": 640, "option_type": "PUT",  "open_interest": 9000,  "volume": 2500,  "dte": 0},
]

downside_options = [
    {"strike": 640, "option_type": "PUT",  "open_interest": 10000, "volume": 15000, "dte": 0},
    {"strike": 635, "option_type": "PUT",  "open_interest": 9000,  "volume": 13000, "dte": 0},
    {"strike": 645, "option_type": "CALL", "open_interest": 8000,  "volume": 1500,  "dte": 0},
]

theta_options = [
    {"strike": 645, "option_type": "CALL", "open_interest": 10000, "volume": 8000, "dte": 0},
    {"strike": 640, "option_type": "PUT",  "open_interest": 10000, "volume": 7500, "dte": 0},
]

cases = [
    {
        "name": "UPSIDE SQUEEZE",
        "data": upside_options,
        "kwargs": {
            "symbol": "TEST",
            "spot_price": 647.0,
            "close_location": 0.88,
            "wave_direction": "UP",
            "wave_efficiency": 2.1,
            "atr_ratio": 1.8,
            "minutes_to_close": 180,
        },
    },
    {
        "name": "DOWNSIDE LIQUIDATION",
        "data": downside_options,
        "kwargs": {
            "symbol": "TEST",
            "spot_price": 638.0,
            "close_location": 0.10,
            "wave_direction": "DOWN",
            "wave_efficiency": 2.4,
            "atr_ratio": 2.5,
            "minutes_to_close": 150,
        },
    },
    {
        "name": "THETA FLUSH RISK",
        "data": theta_options,
        "kwargs": {
            "symbol": "TEST",
            "spot_price": 642.0,
            "close_location": 0.52,
            "wave_direction": "UP",
            "wave_efficiency": 0.40,
            "atr_ratio": 1.2,
            "minutes_to_close": 35,
        },
    },
]

for case in cases:
    result = ZeroDTESqueezeEngine.build(options_data=case["data"], **case["kwargs"])
    print("\nCASE:", case["name"])
    print("STATUS:", result["status"])
    print("ACTIVE 0DTE:", result["active_0dte"])
    print("VOL/OI:", result["zero_dte_vol_oi_ratio"])
    print("DOMINANT SIDE:", result["dominant_0dte_side"])
    print("STATE:", result["squeeze_state"])
    print("THETA RISK:", result["theta_flush_risk"])
    print("LIQUIDATION RISK:", result["liquidation_risk"])
    print("NEAREST STRIKE:", result["nearest_active_strike"])
    print("CONFIDENCE:", result["confidence"])
    print("REASON:", result["reason"])
