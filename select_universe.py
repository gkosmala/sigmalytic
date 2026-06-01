# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
select_universe.py
Sigmalytic Quant Corporation

Selects a principled 250-stock backtest universe from a large-cap seed list.

Methodology (investor-defensible):
  1. Start with 500+ large-cap seed symbols (S&P 500 proxy for Russell 1000)
  2. Validate via Alpaca: 5yr continuous history + $50M avg daily dollar volume
  3. Sector-balance: proportional to Russell 1000 GICS weights
  4. Rank within each sector by ADV (behavioral signal richness proxy)
  5. Output: backtest_universe.csv

Usage:
  python select_universe.py \
    --api-key YOUR_ALPACA_KEY \
    --secret-key YOUR_ALPACA_SECRET \
    --output backtest_universe.csv \
    --target 250

  # Dry run (no Alpaca calls, mock data):
  python select_universe.py --api-key x --secret-key x --dry-run
"""

import argparse
import time
import sys
import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOOKBACK_YEARS  = 5
TARGET_SIZE     = 250
MIN_ADV_USD     = 50_000_000   # $50M
MIN_DAYS        = 900          # ~3.5 yrs of trading days (buffer for gaps)

ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

# Russell 1000 approximate GICS sector weights
SECTOR_WEIGHTS = {
    "Information Technology":   0.29,
    "Health Care":              0.12,
    "Financials":               0.13,
    "Consumer Discretionary":   0.10,
    "Industrials":              0.09,
    "Communication Services":   0.08,
    "Consumer Staples":         0.06,
    "Energy":                   0.04,
    "Real Estate":              0.03,
    "Materials":                0.03,
    "Utilities":                0.03,
}

# Sector normalisation map
SECTOR_MAP = {
    "Information Technology":       "Information Technology",
    "Technology":                   "Information Technology",
    "Health Care":                  "Health Care",
    "Healthcare":                   "Health Care",
    "Financials":                   "Financials",
    "Financial Services":           "Financials",
    "Consumer Discretionary":       "Consumer Discretionary",
    "Industrials":                  "Industrials",
    "Communication Services":       "Communication Services",
    "Telecommunication Services":   "Communication Services",
    "Consumer Staples":             "Consumer Staples",
    "Energy":                       "Energy",
    "Real Estate":                  "Real Estate",
    "Materials":                    "Materials",
    "Utilities":                    "Utilities",
}

# ---------------------------------------------------------------------------
# Seed list — S&P 500 symbols with GICS sectors (hardcoded for reliability)
# This avoids Wikipedia scraping and works in any environment.
# ---------------------------------------------------------------------------

SEED = [
    # Information Technology
    ("AAPL","Apple Inc","Information Technology"),
    ("MSFT","Microsoft Corp","Information Technology"),
    ("NVDA","NVIDIA Corp","Information Technology"),
    ("AVGO","Broadcom Inc","Information Technology"),
    ("ORCL","Oracle Corp","Information Technology"),
    ("CRM","Salesforce Inc","Information Technology"),
    ("CSCO","Cisco Systems","Information Technology"),
    ("ACN","Accenture plc","Information Technology"),
    ("IBM","IBM Corp","Information Technology"),
    ("NOW","ServiceNow Inc","Information Technology"),
    ("INTU","Intuit Inc","Information Technology"),
    ("TXN","Texas Instruments","Information Technology"),
    ("QCOM","Qualcomm Inc","Information Technology"),
    ("AMD","Advanced Micro Devices","Information Technology"),
    ("AMAT","Applied Materials","Information Technology"),
    ("MU","Micron Technology","Information Technology"),
    ("LRCX","Lam Research","Information Technology"),
    ("KLAC","KLA Corp","Information Technology"),
    ("ADBE","Adobe Inc","Information Technology"),
    ("PANW","Palo Alto Networks","Information Technology"),
    ("SNPS","Synopsys Inc","Information Technology"),
    ("CDNS","Cadence Design","Information Technology"),
    ("MSI","Motorola Solutions","Information Technology"),
    ("FTNT","Fortinet Inc","Information Technology"),
    ("MCHP","Microchip Technology","Information Technology"),
    ("ON","ON Semiconductor","Information Technology"),
    ("STX","Seagate Technology","Information Technology"),
    ("WDC","Western Digital","Information Technology"),
    ("HPQ","HP Inc","Information Technology"),
    ("HPE","Hewlett Packard Enterprise","Information Technology"),
    ("GEN","Gen Digital","Information Technology"),
    ("JNPR","Juniper Networks","Information Technology"),
    ("KEYS","Keysight Technologies","Information Technology"),
    ("TER","Teradyne Inc","Information Technology"),
    ("ENPH","Enphase Energy","Information Technology"),
    ("GLW","Corning Inc","Information Technology"),
    ("NTAP","NetApp Inc","Information Technology"),
    ("FFIV","F5 Inc","Information Technology"),
    ("ANSS","Ansys Inc","Information Technology"),
    ("PTC","PTC Inc","Information Technology"),
    # Health Care
    ("LLY","Eli Lilly","Health Care"),
    ("UNH","UnitedHealth Group","Health Care"),
    ("JNJ","Johnson & Johnson","Health Care"),
    ("ABBV","AbbVie Inc","Health Care"),
    ("MRK","Merck & Co","Health Care"),
    ("TMO","Thermo Fisher Scientific","Health Care"),
    ("ABT","Abbott Laboratories","Health Care"),
    ("DHR","Danaher Corp","Health Care"),
    ("BMY","Bristol-Myers Squibb","Health Care"),
    ("AMGN","Amgen Inc","Health Care"),
    ("PFE","Pfizer Inc","Health Care"),
    ("SYK","Stryker Corp","Health Care"),
    ("ISRG","Intuitive Surgical","Health Care"),
    ("GILD","Gilead Sciences","Health Care"),
    ("MDT","Medtronic plc","Health Care"),
    ("CVS","CVS Health","Health Care"),
    ("CI","Cigna Group","Health Care"),
    ("ELV","Elevance Health","Health Care"),
    ("HUM","Humana Inc","Health Care"),
    ("ZBH","Zimmer Biomet","Health Care"),
    ("BSX","Boston Scientific","Health Care"),
    ("BDX","Becton Dickinson","Health Care"),
    ("REGN","Regeneron Pharmaceuticals","Health Care"),
    ("VRTX","Vertex Pharmaceuticals","Health Care"),
    ("IQV","IQVIA Holdings","Health Care"),
    ("A","Agilent Technologies","Health Care"),
    ("BIIB","Biogen Inc","Health Care"),
    ("BAX","Baxter International","Health Care"),
    ("HOLX","Hologic Inc","Health Care"),
    ("TECH","Bio-Techne Corp","Health Care"),
    # Financials
    ("BRK.B","Berkshire Hathaway","Financials"),
    ("JPM","JPMorgan Chase","Financials"),
    ("BAC","Bank of America","Financials"),
    ("WFC","Wells Fargo","Financials"),
    ("GS","Goldman Sachs","Financials"),
    ("MS","Morgan Stanley","Financials"),
    ("BLK","BlackRock Inc","Financials"),
    ("SCHW","Charles Schwab","Financials"),
    ("AXP","American Express","Financials"),
    ("C","Citigroup Inc","Financials"),
    ("CB","Chubb Ltd","Financials"),
    ("PGR","Progressive Corp","Financials"),
    ("MET","MetLife Inc","Financials"),
    ("PRU","Prudential Financial","Financials"),
    ("USB","US Bancorp","Financials"),
    ("PNC","PNC Financial","Financials"),
    ("TFC","Truist Financial","Financials"),
    ("AIG","American Intl Group","Financials"),
    ("COF","Capital One Financial","Financials"),
    ("DFS","Discover Financial","Financials"),
    ("MCO","Moody's Corp","Financials"),
    ("SPGI","S&P Global","Financials"),
    ("ICE","Intercontinental Exchange","Financials"),
    ("CME","CME Group","Financials"),
    ("AON","Aon plc","Financials"),
    ("MMC","Marsh McLennan","Financials"),
    ("AFL","Aflac Inc","Financials"),
    ("ALL","Allstate Corp","Financials"),
    ("HIG","Hartford Financial","Financials"),
    ("MTB","M&T Bank","Financials"),
    ("RF","Regions Financial","Financials"),
    ("CFG","Citizens Financial","Financials"),
    ("FITB","Fifth Third Bancorp","Financials"),
    # Consumer Discretionary
    ("AMZN","Amazon.com","Consumer Discretionary"),
    ("TSLA","Tesla Inc","Consumer Discretionary"),
    ("HD","Home Depot","Consumer Discretionary"),
    ("MCD","McDonald's Corp","Consumer Discretionary"),
    ("NKE","Nike Inc","Consumer Discretionary"),
    ("LOW","Lowe's Companies","Consumer Discretionary"),
    ("SBUX","Starbucks Corp","Consumer Discretionary"),
    ("TJX","TJX Companies","Consumer Discretionary"),
    ("BKNG","Booking Holdings","Consumer Discretionary"),
    ("CMG","Chipotle Mexican Grill","Consumer Discretionary"),
    ("ABNB","Airbnb Inc","Consumer Discretionary"),
    ("MAR","Marriott International","Consumer Discretionary"),
    ("HLT","Hilton Worldwide","Consumer Discretionary"),
    ("GM","General Motors","Consumer Discretionary"),
    ("F","Ford Motor","Consumer Discretionary"),
    ("ORLY","O'Reilly Automotive","Consumer Discretionary"),
    ("AZO","AutoZone Inc","Consumer Discretionary"),
    ("ROST","Ross Stores","Consumer Discretionary"),
    ("DHI","D.R. Horton","Consumer Discretionary"),
    ("LEN","Lennar Corp","Consumer Discretionary"),
    ("PHM","PulteGroup Inc","Consumer Discretionary"),
    ("YUM","Yum! Brands","Consumer Discretionary"),
    ("DRI","Darden Restaurants","Consumer Discretionary"),
    ("BBY","Best Buy","Consumer Discretionary"),
    ("EBAY","eBay Inc","Consumer Discretionary"),
    # Industrials
    ("GE","GE Aerospace","Industrials"),
    ("CAT","Caterpillar Inc","Industrials"),
    ("HON","Honeywell Intl","Industrials"),
    ("UPS","United Parcel Service","Industrials"),
    ("RTX","RTX Corp","Industrials"),
    ("LMT","Lockheed Martin","Industrials"),
    ("NOC","Northrop Grumman","Industrials"),
    ("GD","General Dynamics","Industrials"),
    ("DE","Deere & Company","Industrials"),
    ("MMM","3M Company","Industrials"),
    ("BA","Boeing Co","Industrials"),
    ("FDX","FedEx Corp","Industrials"),
    ("CSX","CSX Corp","Industrials"),
    ("NSC","Norfolk Southern","Industrials"),
    ("UNP","Union Pacific","Industrials"),
    ("EMR","Emerson Electric","Industrials"),
    ("ETN","Eaton Corp","Industrials"),
    ("PH","Parker Hannifin","Industrials"),
    ("ROK","Rockwell Automation","Industrials"),
    ("IR","Ingersoll Rand","Industrials"),
    ("CARR","Carrier Global","Industrials"),
    ("OTIS","Otis Worldwide","Industrials"),
    ("WAB","Wabtec Corp","Industrials"),
    ("GWW","W.W. Grainger","Industrials"),
    ("CPRT","Copart Inc","Industrials"),
    ("VRSK","Verisk Analytics","Industrials"),
    # Communication Services
    ("GOOGL","Alphabet Inc A","Communication Services"),
    ("GOOG","Alphabet Inc C","Communication Services"),
    ("META","Meta Platforms","Communication Services"),
    ("NFLX","Netflix Inc","Communication Services"),
    ("DIS","Walt Disney Co","Communication Services"),
    ("CMCSA","Comcast Corp","Communication Services"),
    ("T","AT&T Inc","Communication Services"),
    ("VZ","Verizon Communications","Communication Services"),
    ("TMUS","T-Mobile US","Communication Services"),
    ("CHTR","Charter Communications","Communication Services"),
    ("PARA","Paramount Global","Communication Services"),
    ("WBD","Warner Bros Discovery","Communication Services"),
    ("OMC","Omnicom Group","Communication Services"),
    ("IPG","Interpublic Group","Communication Services"),
    ("EA","Electronic Arts","Communication Services"),
    ("TTWO","Take-Two Interactive","Communication Services"),
    ("MTCH","Match Group","Communication Services"),
    ("PINS","Pinterest Inc","Communication Services"),
    ("SNAP","Snap Inc","Communication Services"),
    # Consumer Staples
    ("WMT","Walmart Inc","Consumer Staples"),
    ("PG","Procter & Gamble","Consumer Staples"),
    ("COST","Costco Wholesale","Consumer Staples"),
    ("KO","Coca-Cola Co","Consumer Staples"),
    ("PEP","PepsiCo Inc","Consumer Staples"),
    ("PM","Philip Morris","Consumer Staples"),
    ("MO","Altria Group","Consumer Staples"),
    ("MDLZ","Mondelez International","Consumer Staples"),
    ("CL","Colgate-Palmolive","Consumer Staples"),
    ("GIS","General Mills","Consumer Staples"),
    ("KHC","Kraft Heinz","Consumer Staples"),
    ("HSY","Hershey Co","Consumer Staples"),
    ("KR","Kroger Co","Consumer Staples"),
    ("SYY","Sysco Corp","Consumer Staples"),
    ("STZ","Constellation Brands","Consumer Staples"),
    ("BG","Bunge Global","Consumer Staples"),
    # Energy
    ("XOM","Exxon Mobil","Energy"),
    ("CVX","Chevron Corp","Energy"),
    ("COP","ConocoPhillips","Energy"),
    ("EOG","EOG Resources","Energy"),
    ("SLB","SLB","Energy"),
    ("MPC","Marathon Petroleum","Energy"),
    ("PSX","Phillips 66","Energy"),
    ("VLO","Valero Energy","Energy"),
    ("HAL","Halliburton Co","Energy"),
    ("BKR","Baker Hughes","Energy"),
    ("DVN","Devon Energy","Energy"),
    ("FANG","Diamondback Energy","Energy"),
    ("OXY","Occidental Petroleum","Energy"),
    ("HES","Hess Corp","Energy"),
    ("APA","APA Corp","Energy"),
    # Real Estate
    ("PLD","Prologis Inc","Real Estate"),
    ("AMT","American Tower","Real Estate"),
    ("EQIX","Equinix Inc","Real Estate"),
    ("CCI","Crown Castle","Real Estate"),
    ("SPG","Simon Property Group","Real Estate"),
    ("O","Realty Income","Real Estate"),
    ("DLR","Digital Realty Trust","Real Estate"),
    ("WELL","Welltower Inc","Real Estate"),
    ("VTR","Ventas Inc","Real Estate"),
    ("PSA","Public Storage","Real Estate"),
    ("EXR","Extra Space Storage","Real Estate"),
    ("AVB","AvalonBay Communities","Real Estate"),
    ("EQR","Equity Residential","Real Estate"),
    # Materials
    ("LIN","Linde plc","Materials"),
    ("SHW","Sherwin-Williams","Materials"),
    ("ECL","Ecolab Inc","Materials"),
    ("APD","Air Products","Materials"),
    ("NEM","Newmont Corp","Materials"),
    ("FCX","Freeport-McMoRan","Materials"),
    ("NUE","Nucor Corp","Materials"),
    ("VMC","Vulcan Materials","Materials"),
    ("MLM","Martin Marietta","Materials"),
    ("ALB","Albemarle Corp","Materials"),
    ("MOS","Mosaic Co","Materials"),
    ("CF","CF Industries","Materials"),
    # Utilities
    ("NEE","NextEra Energy","Utilities"),
    ("SO","Southern Co","Utilities"),
    ("DUK","Duke Energy","Utilities"),
    ("AEP","American Electric Power","Utilities"),
    ("SRE","Sempra","Utilities"),
    ("EXC","Exelon Corp","Utilities"),
    ("XEL","Xcel Energy","Utilities"),
    ("WEC","WEC Energy","Utilities"),
    ("ES","Eversource Energy","Utilities"),
    ("AWK","American Water Works","Utilities"),
    ("PPL","PPL Corp","Utilities"),
    ("CMS","CMS Energy","Utilities"),
]


def build_seed_df() -> pd.DataFrame:
    df = pd.DataFrame(SEED, columns=["Symbol", "Company", "Sector"])
    df["Symbol"] = df["Symbol"].str.upper().str.strip()
    df = df.drop_duplicates(subset="Symbol").reset_index(drop=True)
    print(f"  ✅ Seed universe: {len(df)} symbols across {df['Sector'].nunique()} sectors")
    return df


# ---------------------------------------------------------------------------
# Alpaca validation
# ---------------------------------------------------------------------------

def validate_via_alpaca(symbols: list, api_key: str, secret_key: str) -> dict:
    from datetime import datetime, timedelta

    end   = datetime.now()
    start = end - timedelta(days=365 * LOOKBACK_YEARS + 60)

    headers = {
        "APCA-API-KEY-ID":     api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }

    results   = {}
    batch_size = 50

    for i in range(0, len(symbols), batch_size):
        batch = [s for s in symbols[i:i+batch_size] if "/" not in s]  # skip crypto-style
        if not batch:
            continue

        params = {
            "symbols":    ",".join(batch),
            "timeframe":  "1Day",
            "start":      start.strftime("%Y-%m-%dT00:00:00Z"),
            "end":        end.strftime("%Y-%m-%dT00:00:00Z"),
            "limit":      10000,
            "adjustment": "all",
            "feed":       "iex",
        }

        try:
            resp = requests.get(
                f"{ALPACA_DATA_URL}/stocks/bars",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for sym, bars in data.get("bars", {}).items():
                if not bars:
                    continue
                df = pd.DataFrame(bars)
                df["dv"] = df["c"] * df["v"]
                results[sym] = {
                    "adv":  float(df["dv"].mean()),
                    "days": int(len(df)),
                }
        except Exception as e:
            print(f"\n  ⚠️  Batch {i//batch_size+1} failed, retrying one by one...")
            for sym in batch:
                try:
                    p2 = dict(params); p2["symbols"] = sym
                    r2 = requests.get(f"{ALPACA_DATA_URL}/stocks/bars", headers=headers, params=p2, timeout=15)
                    r2.raise_for_status()
                    for s, bars in r2.json().get("bars", {}).items():
                        if bars:
                            import pandas as pd
                            df2 = pd.DataFrame(bars)
                            df2["dv"] = df2["c"] * df2["v"]
                            results[s] = {"adv": float(df2["dv"].mean()), "days": int(len(df2))}
                    time.sleep(0.2)
                except Exception:
                    pass

        time.sleep(0.35)
        done = min(i + batch_size, len(symbols))
        print(f"  Validated {done}/{len(symbols)} symbols...  ", end="\r", flush=True)

    print()
    return results


# ---------------------------------------------------------------------------
# Sector-balanced selection
# ---------------------------------------------------------------------------

def select_balanced(candidates: pd.DataFrame, target: int) -> pd.DataFrame:
    candidates = candidates.copy()
    candidates["Sector_Normalized"] = candidates["Sector"].map(SECTOR_MAP).fillna("Other")

    selected = []
    print(f"\n{'Sector':<38} {'Target':>6}  {'Avail':>5}  {'Chosen':>6}")
    print("-" * 62)

    for sector, weight in SECTOR_WEIGHTS.items():
        n = max(1, round(target * weight))
        pool = candidates[candidates["Sector_Normalized"] == sector].sort_values("ADV_USD", ascending=False)
        chosen = pool.head(n)
        selected.append(chosen)
        print(f"  {sector:<36} {n:>6}  {len(pool):>5}  {len(chosen):>6}")

    result = pd.concat(selected, ignore_index=True)

    # Fill any remaining slots from unselected candidates ranked by ADV
    remaining = target - len(result)
    if remaining > 0:
        leftovers = candidates[~candidates["Symbol"].isin(result["Symbol"])].sort_values("ADV_USD", ascending=False)
        extra = leftovers.head(remaining)
        result = pd.concat([result, extra], ignore_index=True)
        print(f"  {'Other / fill':36} {remaining:>6}  {len(leftovers):>5}  {len(extra):>6}")

    return result.sort_values("ADV_USD", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sigmalytic Backtest Universe Selector")
    parser.add_argument("--api-key",    required=True)
    parser.add_argument("--secret-key", required=True)
    parser.add_argument("--output",     default="backtest_universe.csv")
    parser.add_argument("--target",     type=int,   default=TARGET_SIZE)
    parser.add_argument("--min-adv",    type=float, default=MIN_ADV_USD)
    parser.add_argument("--dry-run",    action="store_true", help="Use mock data — no Alpaca calls")
    args = parser.parse_args()

    print("\n" + "=" * 62)
    print("  SIGMALYTIC — BACKTEST UNIVERSE SELECTOR")
    print(f"  Target: {args.target} stocks | Min ADV: ${args.min_adv/1e6:.0f}M | Lookback: {LOOKBACK_YEARS}yr")
    print("=" * 62 + "\n")

    # Step 1 — Build seed
    print("📋 Building seed universe...")
    df = build_seed_df()

    # Step 2 — Validate
    if args.dry_run:
        print("\n⚠️  DRY RUN — using mock ADV data\n")
        rng = np.random.default_rng(42)
        df["ADV_USD"]      = rng.uniform(20e6, 600e6, len(df))
        df["Trading_Days"] = rng.integers(800, 1270, len(df))
    else:
        print(f"\n📡 Validating {len(df)} symbols via Alpaca SIP (5-year daily bars)...")
        print("   This takes ~3–5 minutes. Please wait.\n")
        bar_data = validate_via_alpaca(df["Symbol"].tolist(), args.api_key, args.secret_key)
        df["ADV_USD"]      = df["Symbol"].map(lambda s: bar_data.get(s, {}).get("adv",  0))
        df["Trading_Days"] = df["Symbol"].map(lambda s: bar_data.get(s, {}).get("days", 0))

    # Filter
    before = len(df)
    df = df[(df["ADV_USD"] >= args.min_adv) & (df["Trading_Days"] >= MIN_DAYS)].copy()
    print(f"\n  Passed filters: {len(df)} / {before}  (excluded {before-len(df)} low-ADV or insufficient history)\n")

    if len(df) < args.target:
        print(f"  ⚠️  Only {len(df)} candidates passed filters — universe will be smaller than {args.target}.")

    # Step 3 — Sector balance
    print(f"⚖️  Sector-balanced selection → {args.target} stocks\n")
    universe = select_balanced(df, args.target)

    # Save
    out_cols = ["Symbol","Company","Sector","Sector_Normalized","ADV_USD","Trading_Days"]
    out_cols = [c for c in out_cols if c in universe.columns]
    universe[out_cols].to_csv(args.output, index=False)

    # Summary
    print(f"\n{'=' * 62}")
    print(f"  ✅ DONE — {len(universe)} symbols written to {args.output}")
    print(f"{'=' * 62}\n")
    print("📊 Sector breakdown:\n")
    summary = (
        universe.groupby("Sector_Normalized")
        .agg(Count=("Symbol","count"), Avg_ADV_M=("ADV_USD", lambda x: f"${x.mean()/1e6:.0f}M"))
        .sort_values("Count", ascending=False)
    )
    print(summary.to_string())
    print()


if __name__ == "__main__":
    main()
