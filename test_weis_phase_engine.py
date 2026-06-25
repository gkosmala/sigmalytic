from backend.campaign_engine.weis_phase_engine import WeisPhaseEngine

weis_up = {
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
        "shortening_downside_thrust": False,
        "shortening_upside_thrust": False,
    }
}

weis_down_fail = {
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
        "shortening_downside_thrust": True,
        "shortening_upside_thrust": False,
    }
}

multi_good = {
    "dominant_wave_direction": "UP",
    "wave_coherence_score": 0.82,
    "phase_permission": "EXPANSION_CONFIRMED",
}

cases = [
    {
        "name": "GAMMA EXPANSION",
        "weis": weis_up,
        "fusion": {
            "fusion_state": "WEIS_GAMMA_EXPANSION",
            "fusion_direction": "UP",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "confidence": 0.90,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
    },
    {
        "name": "ABSORPTION SUPPORT",
        "weis": weis_down_fail,
        "fusion": {
            "fusion_state": "WEIS_GAMMA_ABSORPTION_SUPPORT",
            "fusion_direction": "UP_POTENTIAL",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "confidence": 0.80,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
    },
    {
        "name": "THETA FLUSH",
        "weis": weis_up,
        "fusion": {
            "fusion_state": "THETA_FLUSH_RISK",
            "fusion_direction": "RISK",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "confidence": 0.75,
            "theta_flush_risk": True,
            "liquidation_risk": False,
        },
    },
    {
        "name": "GAMMA STALE",
        "weis": weis_up,
        "fusion": {
            "fusion_state": "WEIS_ONLY_GAMMA_STALE",
            "fusion_direction": "UP",
            "router_state": "YELLOW",
            "gamma_data_fresh": False,
            "confidence": 0.20,
            "theta_flush_risk": False,
            "liquidation_risk": False,
        },
    },
    {
        "name": "COLLAPSE",
        "weis": weis_up,
        "fusion": {
            "fusion_state": "WEIS_GAMMA_COLLAPSE",
            "fusion_direction": "DOWN",
            "router_state": "GREEN",
            "gamma_data_fresh": True,
            "confidence": 0.88,
            "theta_flush_risk": False,
            "liquidation_risk": True,
        },
    },
]

for case in cases:
    result = WeisPhaseEngine.build(
        symbol="TEST",
        weis_wave_result=case["weis"],
        multi_scale_weis_result=multi_good,
        weis_gamma_fusion_result=case["fusion"],
    )

    print("\nCASE:", case["name"])
    print("STATUS:", result["status"])
    print("WEIS PHASE:", result["weis_phase"])
    print("MAPPED CAMPAIGN STATE:", result["mapped_campaign_state"])
    print("DIRECTION:", result["phase_direction"])
    print("CONFIDENCE:", result["phase_confidence"])
    print("RISK:", result["risk_state"])
    print("NEXT:", result["next_possible_phase"])
    print("REASON:", result["phase_reason"])
