from pathlib import Path

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_OPTIONS_WORDING_ONLY
# Only removes stale visible "synthetic options" UI wording from live frontend file.

replacements = {
    "Synthetic options layer - Alpaca options feed active.":
        "Options intelligence layer - Alpaca options feed active.",

    "Synthetic options layer — connect Tradier or CBOE for live institutional flow data.":
        "Options intelligence layer - Alpaca options feed active.",

    "Synthetic options layer â€” connect Tradier or CBOE for live institutional flow data.":
        "Options intelligence layer - Alpaca options feed active.",

    "Synthetic options layer GÇö Alpaca options feed active.":
        "Options intelligence layer - Alpaca options feed active.",

    "Synthetic intelligence from price, volume, volatility proxy, and decision score.":
        "Options intelligence from Alpaca options feed, price, volume, volatility proxy, and decision score.",

    "SYNTHETIC OPTIONS INTELLIGENCE":
        "ALPACA OPTIONS INTELLIGENCE",

    "Synthetic Options":
        "Alpaca Options",

    "synthetic options":
        "Alpaca options",
}

for old, new in replacements.items():
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("OPTIONS WORDING ONLY FIX APPLIED")
