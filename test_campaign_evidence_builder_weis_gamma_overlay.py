import pandas as pd

from backend.campaign_engine.campaign_evidence_builder import CampaignEvidenceBuilder

bars = []
price = 10.0

for i in range(80):
    open_price = price
    close_price = price + (0.10 if i % 3 != 0 else -0.03)
    high_price = max(open_price, close_price) + 0.08
    low_price = min(open_price, close_price) - 0.05
    volume = 250000 + (i * 2500)

    bars.append({
        "open": round(open_price, 4),
        "high": round(high_price, 4),
        "low": round(low_price, 4),
        "close": round(close_price, 4),
        "volume": volume,
    })

    price = close_price

df = pd.DataFrame(bars)

evidence = CampaignEvidenceBuilder.build_from_bars(
    df,
    symbol="TEST",
    timeframe="DAILY",
)

print("TOP LEVEL KEYS:", sorted(evidence.keys()))
print("WEIS GAMMA STATUS:", evidence["weis_gamma"]["status"])
print("WIRED:", evidence["weis_gamma"]["wired_into_evidence_builder"])
print("STATE TRANSITION ENABLED:", evidence["weis_gamma"]["state_transition_enabled"])

print("PROFILE STATUS:", evidence["weis_gamma"]["symbol_behavior_profile"].get("status", "NO_STATUS_FIELD"))
print("WEIS WAVE STATUS:", evidence["weis_gamma"]["weis_wave"].get("status", "NO_STATUS_FIELD"))
print("MULTI SCALE STATUS:", evidence["weis_gamma"]["multi_scale_weis"].get("status", "NO_STATUS_FIELD"))
print("GAMMA STATUS:", evidence["weis_gamma"]["gamma_matrix"].get("status", "NO_STATUS_FIELD"))
print("FUSION STATE:", evidence["weis_gamma"]["fusion"].get("fusion_state"))
print("PHASE:", evidence["weis_gamma"]["phase"].get("weis_phase"))
print("RANK SCORE:", evidence["weis_gamma"]["ranking"].get("rank_score"))
print("RANK BUCKET:", evidence["weis_gamma"]["ranking"].get("rank_bucket"))
print("WARNINGS:", evidence["weis_gamma"]["warnings"])
