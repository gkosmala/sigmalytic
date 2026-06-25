from backend.campaign_engine.weis_gamma_ranking_engine import WeisGammaRankingEngine

weis_up = {
    "evidence": {
        "wave_direction": "UP",
        "wave_distance_atr": 2.8,
        "wave_volume_z": 2.2,
        "wave_efficiency": 2.1,
    }
}

multi = {
    "wave_coherence_score": 0.84,
}

gamma_good = {
    "net_gamma_regime": "NEGATIVE",
    "nearest_gamma_wall": 650,
    "nearest_wall_type": "PUT_WALL",
    "nearest_wall_status": "PUT_GAMMA_SUPPORT",
}

fresh_green = {
    "router_state": "GREEN",
    "gamma_data_fresh": True,
}

fresh_yellow = {
    "router_state": "YELLOW",
    "gamma_data_fresh": False,
}

zero_up = {
    "active_0dte": True,
    "squeeze_state": "0DTE_UPSIDE_SQUEEZE_CONFIRMED",
    "zero_dte_vol_oi_ratio": 1.10,
    "theta_flush_risk": False,
    "liquidation_risk": False,
}

zero_theta = {
    "active_0dte": True,
    "squeeze_state": "0DTE_THETA_FLUSH_RISK",
    "zero_dte_vol_oi_ratio": 0.80,
    "theta_flush_risk": True,
    "liquidation_risk": False,
}

cases = [
    {
        "name": "A EXPANSION",
        "phase": {
            "weis_phase": "WEIS_GAMMA_EXPANSION",
            "mapped_campaign_state": "EXPANDING",
            "phase_confidence": 1.0,
            "phase_direction": "UP",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
        "fresh": fresh_green,
        "zero": zero_up,
    },
    {
        "name": "ABSORPTION WATCH",
        "phase": {
            "weis_phase": "WEIS_ABSORPTION",
            "mapped_campaign_state": "BIRTH",
            "phase_confidence": 0.88,
            "phase_direction": "UP_POTENTIAL",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
        "fresh": fresh_green,
        "zero": {"active_0dte": False, "squeeze_state": "NO_0DTE_ANOMALY"},
    },
    {
        "name": "STALE GAMMA",
        "phase": {
            "weis_phase": "WEIS_ONLY_GAMMA_STALE",
            "mapped_campaign_state": "SURVIVING",
            "phase_confidence": 0.45,
            "phase_direction": "UP",
            "router_state": "YELLOW",
            "gamma_data_fresh": False,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
        "fresh": fresh_yellow,
        "zero": {"active_0dte": False, "squeeze_state": "NO_0DTE_ANOMALY"},
    },
    {
        "name": "THETA RISK",
        "phase": {
            "weis_phase": "WEIS_THETA_FLUSH_RISK",
            "mapped_campaign_state": "MATURING",
            "phase_confidence": 0.90,
            "phase_direction": "RISK",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "theta_flush_risk": True,
            "liquidation_risk": False,
        },
        "fresh": fresh_green,
        "zero": zero_theta,
    },
]

for case in cases:
    result = WeisGammaRankingEngine.build(
        symbol="TEST",
        weis_phase_result=case["phase"],
        weis_wave_result=weis_up,
        multi_scale_weis_result=multi,
        gamma_matrix_result=gamma_good,
        gamma_freshness_result=case["fresh"],
        zero_dte_result=case["zero"],
        weis_gamma_fusion_result={"fusion_direction": case["phase"]["phase_direction"]},
    )

    print("\nCASE:", case["name"])
    print("STATUS:", result["status"])
    print("SCORE:", result["rank_score"])
    print("BUCKET:", result["rank_bucket"])
    print("DIRECTION:", result["rank_direction"])
    print("OPPORTUNITY:", result["opportunity_score"])
    print("RISK PENALTY:", result["risk_penalty"])
    print("FRESHNESS PENALTY:", result["freshness_penalty"])
    print("REASON:", result["rank_reason"])
