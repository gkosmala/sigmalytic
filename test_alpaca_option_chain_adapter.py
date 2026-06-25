from backend.gamma.alpaca_option_chain_adapter import AlpacaOptionChainAdapter

sample = {
    "snapshots": {
        "AAPL260117C00195000": {
            "greeks": {
                "gamma": 0.012,
                "delta": 0.54,
                "theta": -0.04,
                "vega": 0.18,
                "implied_volatility": 0.31,
            },
            "latest_trade": {
                "price": 5.10,
                "size": 12,
                "timestamp": "2026-06-25T18:30:00Z",
            },
            "latest_quote": {
                "bid_price": 5.00,
                "ask_price": 5.20,
                "timestamp": "2026-06-25T18:30:00Z",
            },
            "open_interest": 10000,
            "volume": 14000,
        },
        "AAPL260117P00185000": {
            "greeks": {
                "gamma": 0.009,
                "delta": -0.42,
                "theta": -0.05,
                "vega": 0.16,
                "implied_volatility": 0.34,
            },
            "latest_trade": {
                "price": 4.70,
                "size": 8,
                "timestamp": "2026-06-25T18:30:00Z",
            },
            "latest_quote": {
                "bid_price": 4.60,
                "ask_price": 4.80,
                "timestamp": "2026-06-25T18:30:00Z",
            },
            "open_interest": 8000,
            "volume": 9000,
        },
    }
}

rows = AlpacaOptionChainAdapter.normalize_chain(
    payload=sample,
    underlying_symbol="AAPL",
    spot_price=190.00,
)

print("ROWS:", len(rows))
for row in rows:
    print(row)

assert len(rows) == 2
assert rows[0]["option_type"] == "CALL"
assert rows[1]["option_type"] == "PUT"
assert rows[0]["strike"] == 195.0
assert rows[1]["strike"] == 185.0
assert rows[0]["gamma_exposure"] > 0
assert rows[1]["gamma_exposure"] < 0

print("STATUS: OK")
