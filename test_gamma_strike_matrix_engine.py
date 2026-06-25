from backend.gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine

options_data = [
    {"strike": 630, "option_type": "PUT",  "open_interest": 12000, "volume": 4500,  "gamma_exposure": 680000,  "net_delta_shares": 680000,  "dte": 0},
    {"strike": 635, "option_type": "PUT",  "open_interest": 8000,  "volume": 2200,  "gamma_exposure": 110000,  "net_delta_shares": 110000,  "dte": 0},
    {"strike": 640, "option_type": "PUT",  "open_interest": 16000, "volume": 9000,  "gamma_exposure": -520000, "net_delta_shares": -520000, "dte": 0},
    {"strike": 645, "option_type": "CALL", "open_interest": 9500,  "volume": 3300,  "gamma_exposure": 250000,  "net_delta_shares": 220000,  "dte": 0},
    {"strike": 650, "option_type": "CALL", "open_interest": 21000, "volume": 11000, "gamma_exposure": 850000,  "net_delta_shares": 700000,  "dte": 0},
    {"strike": 655, "option_type": "CALL", "open_interest": 7000,  "volume": 1500,  "gamma_exposure": 120000,  "net_delta_shares": 100000,  "dte": 7},
]

result = GammaStrikeMatrixEngine.build(
    options_data=options_data,
    symbol="TEST",
    spot_price=642.50,
    top_n=3,
    proximity_pct=0.02,
    data_age_seconds=1.2,
)

print("STATUS:", result["status"])
print("NET GAMMA REGIME:", result["net_gamma_regime"])
print("NEAREST WALL:", result["nearest_gamma_wall"], result["nearest_wall_type"], result["nearest_wall_status"])
print("ZERO GAMMA LEVEL:", result["zero_gamma_level"])
print("ACTIVE 0DTE:", result["active_0dte"])
print("0DTE VOL/OI:", result["zero_dte_vol_oi_ratio"])
print("TOP CALL WALLS:", [(w["strike"], w["wall_type"], w["call_wall_strength"]) for w in result["top_call_walls"]])
print("TOP PUT WALLS:", [(w["strike"], w["wall_type"], w["put_wall_strength"]) for w in result["top_put_walls"]])
print("ACTIVE WALLS:", [(w["strike"], w["wall_type"], w["status"]) for w in result["active_walls"]])
