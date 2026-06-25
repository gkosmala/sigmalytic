from backend.campaign_api import _attach_weis_gamma_summary

sample = {
    "symbol": "TEST",
    "current_state": "SURVIVING",
    "evidence": {
        "weis_gamma": {
            "status": "OK",
            "wired_into_evidence_builder": True,
            "state_transition_enabled": False,
            "phase": {
                "weis_phase": "WEIS_ONLY_GAMMA_STALE",
                "mapped_campaign_state": "SURVIVING",
                "phase_confidence": 0.45,
            },
            "ranking": {
                "rank_score": 38.5,
                "rank_bucket": "LOW_PRIORITY",
                "reason": "Weis evidence remains, but Gamma is stale.",
            },
            "gamma_matrix": {
                "status": "NO_OPTION_CHAIN_INPUT",
                "net_gamma_regime": None,
            },
            "gamma_freshness": {
                "router_state": "YELLOW",
                "gamma_data_fresh": False,
            },
            "fusion": {
                "fusion_state": "WEIS_ONLY_GAMMA_STALE",
            },
            "zero_dte": {
                "squeeze_state": "NO_0DTE_INPUT",
            },
            "warnings": ["Weis-only overlay created because no option chain was supplied."],
        }
    }
}

out = _attach_weis_gamma_summary(sample)

print("weis_gamma_present:", out["weis_gamma_present"])
print("weis_gamma_status:", out["weis_gamma_status"])
print("weis_gamma_transition_enabled:", out["weis_gamma_transition_enabled"])
print("weis_gamma_phase:", out["weis_gamma_phase"])
print("weis_gamma_mapped_state:", out["weis_gamma_mapped_state"])
print("weis_gamma_rank_score:", out["weis_gamma_rank_score"])
print("weis_gamma_rank_bucket:", out["weis_gamma_rank_bucket"])
print("weis_gamma_gamma_status:", out["weis_gamma_gamma_status"])
print("weis_gamma_fusion_state:", out["weis_gamma_fusion_state"])
print("weis_gamma_warning:", out["weis_gamma_warning"])
