import pandas as pd

from backend.campaign_engine.campaign_evidence_builder import CampaignEvidenceBuilder

rows = []
price = 100.0

for i in range(90):
    open_price = price
    close_price = price + 0.20 + (i * 0.01)
    high_price = max(open_price, close_price) + 0.75
    low_price = min(open_price, close_price) - 0.55

    rows.append({
        "timestamp": f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": 1_000_000 + (i * 2500),
    })

    price = close_price

df = pd.DataFrame(rows)

spot = float(df["close"].iloc[-1])

option_chain = [
    {
        "contract_symbol": "TEST260117C00120000",
        "underlying_symbol": "TEST",
        "strike": 120.0,
        "option_type": "CALL",
        "expiration_date": "2026-01-17",
        "dte": 0,
        "open_interest": 10000,
        "volume": 15000,
        "gamma": 0.012,
        "delta": 0.55,
        "theta": -0.04,
        "vega": 0.18,
        "gamma_exposure": 0.012 * 10000 * 100 * spot,
        "net_delta_shares": 0.55 * 10000 * 100,
    },
    {
        "contract_symbol": "TEST260117P00110000",
        "underlying_symbol": "TEST",
        "strike": 110.0,
        "option_type": "PUT",
        "expiration_date": "2026-01-17",
        "dte": 0,
        "open_interest": 9000,
        "volume": 11000,
        "gamma": 0.010,
        "delta": -0.45,
        "theta": -0.05,
        "vega": 0.16,
        "gamma_exposure": -0.010 * 9000 * 100 * spot,
        "net_delta_shares": -0.45 * 9000 * 100,
    },
]

evidence = CampaignEvidenceBuilder.build_from_bars(
    df,
    symbol="TEST",
    timeframe="DAILY",
    option_chain=option_chain,
    gamma_snapshot_time="2026-06-25T20:30:00Z",
    minutes_to_close=120,
)

wg = evidence.get("weis_gamma") or {}
gamma_matrix = wg.get("gamma_matrix") or {}
gamma_freshness = wg.get("gamma_freshness") or {}
zero_dte = wg.get("zero_dte") or {}

print("WEIS_GAMMA_STATUS:", wg.get("status"))
print("GAMMA_MATRIX_STATUS:", gamma_matrix.get("status"))
print("GAMMA_REGIME:", gamma_matrix.get("net_gamma_regime"))
print("GAMMA_ROUTER:", gamma_freshness.get("router_state"))
print("GAMMA_FRESH:", gamma_freshness.get("gamma_data_fresh"))
print("ZERO_DTE_STATUS:", zero_dte.get("status"))
print("ZERO_DTE_STATE:", zero_dte.get("squeeze_state"))

assert gamma_matrix.get("status") != "CALL_SIGNATURE_MISMATCH"
assert gamma_freshness.get("status") != "CALL_SIGNATURE_MISMATCH"
assert zero_dte.get("status") != "CALL_SIGNATURE_MISMATCH"

print("STATUS: OK")
