"""Refresh the S&P 500 + Nasdaq-100 reference list used by Dividend Analyzer.

Pulls the current S&P 500 constituent list from Wikipedia and the current
Nasdaq-100 list from Nasdaq's own API, combines them, and writes the full
reference list of every current member of either index
(default: data/SP500_Companies.xlsx, sheets 'basics' and 'location').

This only refreshes the *input* reference list. To filter it (plus other
sources) for dividend payers and update data/divList.xlsx, run
add_new_dividend_payers.py next. To score a list of symbols, use
export_scores.py.

Usage:
    python scripts/update_sp500_nasdaq.py
    python scripts/update_sp500_nasdaq.py --sp500-only   # old S&P-500-only behavior
"""
import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"


def fetch_sp500_table() -> pd.DataFrame:
    """Scrape the current S&P 500 constituent table from Wikipedia."""
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(WIKI_URL, headers=headers, timeout=20)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    df = tables[0]
    df = df.rename(
        columns={
            "Symbol": "symbol",
            "Security": "name",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
            "Headquarters Location": "headquarters",
        }
    )
    # yfinance expects a hyphen instead of a dot for share-class tickers (e.g. BRK.B -> BRK-B)
    df["symbol"] = df["symbol"].str.strip().str.replace(".", "-", regex=False)
    return df[["symbol", "name", "sector", "sub_industry", "headquarters"]]


def fetch_nasdaq100_table() -> pd.DataFrame:
    """Pull the current Nasdaq-100 constituent list from Nasdaq's own API.

    No sector/sub-industry/headquarters breakdown is available from this
    endpoint, unlike the Wikipedia S&P 500 table -- left blank for these.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    resp = requests.get(NASDAQ100_API, headers=headers, timeout=20)
    resp.raise_for_status()
    rows = resp.json()["data"]["data"]["rows"]
    df = pd.DataFrame(rows)
    df = df.rename(columns={"companyName": "name"})
    df["symbol"] = df["symbol"].str.strip().str.replace(".", "-", regex=False)
    df["sector"] = ""
    df["sub_industry"] = ""
    df["headquarters"] = ""
    return df[["symbol", "name", "sector", "sub_industry", "headquarters"]]


def fetch_combined_table() -> pd.DataFrame:
    """S&P 500 + Nasdaq-100, deduplicated by symbol (S&P 500's row wins on overlap,
    since it carries sector/headquarters data the Nasdaq-100 endpoint doesn't)."""
    sp500 = fetch_sp500_table()
    nasdaq100 = fetch_nasdaq100_table()
    combined = pd.concat([sp500, nasdaq100], ignore_index=True)
    return combined.drop_duplicates(subset="symbol", keep="first")


def write_full_list(df: pd.DataFrame, out_path: Path) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    ws_basics = wb.create_sheet("basics")
    ws_basics.append(["Symbol", "Name", "Sector"])
    for _, row in df.iterrows():
        ws_basics.append([row["symbol"], row["name"], row["sector"]])

    ws_location = wb.create_sheet("location")
    ws_location.append(["Symbol", "Name", "Sector", "Headquarters"])
    for _, row in df.iterrows():
        ws_location.append([row["symbol"], row["name"], row["sector"], row["headquarters"]])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser(description="Refresh the current S&P 500 + Nasdaq-100 reference list.")
    parser.add_argument("--out", type=str, default="data/SP500_Companies.xlsx")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N symbols (for testing)")
    parser.add_argument("--sp500-only", action="store_true", help="Skip Nasdaq-100, S&P 500 only (old behavior)")
    args = parser.parse_args()

    print("Fetching current S&P 500 constituent list from Wikipedia...")
    if args.sp500_only:
        df = fetch_sp500_table()
    else:
        print("Fetching current Nasdaq-100 constituent list from Nasdaq's API...")
        df = fetch_combined_table()
    if args.limit:
        df = df.head(args.limit)
    print(f"Retrieved {len(df)} unique constituents.")

    out_path = Path(args.out)
    write_full_list(df, out_path)
    print(f"[OK] Wrote full constituent list ({len(df)} tickers) -> {out_path}")


if __name__ == "__main__":
    main()
