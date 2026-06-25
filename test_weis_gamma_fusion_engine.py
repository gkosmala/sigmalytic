from backend.evidence.weis_gamma_fusion_engine import WeisGammaFusionEngine

base_weis_up = {
    "evidence": {
        "wave_direction": "UP",
        "wave_distance_atr": 2.4,
        "wave_volume_z": 2.1,
        "wave_efficiency": 1.8,
        "demand_dominance": True,
        "supply_dominance": False,
        "effort_producing_upside_result": True,
        "effort_producing_downside_result": False,
        "effort_failing_upside_result": False,
        "effort_failing_downside_result": False,
    }
}

base_weis_down_fail = {
    "evidence": {
        "wave_direction": "DOWN",
        "wave_distance_atr": 0.8,
        "wave_volume_z": 2.4,
        "wave_efficiency": 0.35,
        "demand_dominance": False,
        "supply_dominance": False,
        "effort_producing_upside_result": False,
        "effort_producing_downside_result": False,
        "effort_failing_upside_result": False,
        "effort_failing_downside_result": True,
    }
}

multi = {
    "dominant_wave_direction": "UP",
    "wave_coherence_score": 0.82,
    "phase_permission": "EXPANSION_CONFIRMED",
}

fresh = {
    "router_state": "GREEN",
    "gamma_data_fresh": True,
    "phase_confidence_modifier": 1.0,
}

stale = {
    "router_state": "YELLOW",
    "gamma_data_fresh": False,
    "phase_confidence_modifier": 0.35,
}

gamma_expansion = {
    "net_gamma_regime": "NEGATIVE",
    "nearest_gamma_wall": 650,
    "nearest_wall_type": "PUT_WALL",
    "nearest_wall_status": "PUT_GAMMA_SUPPORT",
    "active_walls": [
        {
            "strike": 650,
            "wall_type": "PUT_WALL",
            "status": "PUT_GAMMA_SUPPORT",
            "distance_to_spot_pct": 0.008,
        }
    ],
}

gamma_support = {
    "net_gamma_regime": "POSITIVE",
    "nearest_gamma_wall": 640,
    "nearest_wall_type": "PUT_WALL",
    "nearest_wall_status": "PUT_GAMMA_SUPPORT",
    "active_walls": [
        {
            "strike": 640,
            "wall_type": "PUT_WALL",
            "status": "PUT_GAMMA_SUPPORT",
            "distance_to_spot_pct": -0.004,
        }
    ],
}

z_up = {
    "active_0dte": True,
    "squeeze_state": "0DTE_UPSIDE_SQUEEZE_CONFIRMED",
    "zero_dte_vol_oi_ratio": 1.1,
    "theta_flush_risk": False,
    "liquidation_risk": False,
    "confidence": 0.9,
}

z_none = {
    "active_0dte": False,
    "squeeze_state": "NO_0DTE_ANOMALY",
    "zero_dte_vol_oi_ratio": 0.0,
    "theta_flush_risk": False,
    "liquidation_risk": False,
    "confidence": 0.0,
}

z_theta = {
    "active_0dte": True,
    "squeeze_state": "0DTE_THETA_FLUSH_RISK",
    "zero_dte_vol_oi_ratio": 0.8,
    "theta_flush_risk": True,
    "liquidation_risk": False,
    "confidence": 0.7,
}

cases = [
    {
        "name": "EXPANSION",
        "weis": base_weis_up,
        "multi": multi,
        "gamma": gamma_expansion,
        "fresh": fresh,
        "zero": z_up,
    },
    {
        "name": "ABSORPTION SUPPORT",
        "weis": base_weis_down_fail,
        "multi": multi,
        "gamma": gamma_support,
        "fresh": fresh,
        "zero": z_none,
    },
    {
        "name": "THETA FLUSH",
        "weis": base_weis_up,
        "multi": multi,
        "gamma": gamma_expansion,
        "fresh": fresh,
        "zero": z_theta,
    },
    {
        "name": "GAMMA STALE",
        "weis": base_weis_up,
        "multi": multi,
        "gamma": gamma_expansion,
        "fresh": stale,
        "zero": z_none,
    },
]

for case in cases:
    result = WeisGammaFusionEngine.build(
        symbol="TEST",
        weis_wave_result=case["weis"],
        multi_scale_weis_result=case["multi"],
        gamma_matrix_result=case["gamma"],
        gamma_freshness_result=case["fresh"],
        zero_dte_result=case["zero"],
    )

    print("\nCASE:", case["name"])
    print("STATUS:", result["status"])
    print("FUSION STATE:", result["fusion_state"])
    print("DIRECTION:", result["fusion_direction"])
    print("CONFIDENCE:", result["confidence"])
    print("REASON:", result["reason"])
