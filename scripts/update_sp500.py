"""Refresh the S&P 500 reference data used by Dividend Analyzer.

Pulls the current S&P 500 constituent list from Wikipedia and writes two files:

  1. A full reference list of every current index member
     (default: data/SP500_Companies.xlsx, sheets 'basics' and 'location').
  2. A filtered "input" watchlist containing only constituents that paid at
     least one dividend within the trailing N years (default 5)
     (default: data/divList.xlsx, sheet 'Sheet1', ready for `cli.py batch`).

Usage:
    python scripts/update_sp500.py
    python scripts/update_sp500.py --years 5 --limit 20   # quick test run
"""
import argparse
import io
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.data.fetcher import DataFetcher

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


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


def has_recent_dividend(fetcher: DataFetcher, symbol: str, years: int, sleep: float) -> bool:
    """Check whether a ticker paid at least one dividend within the trailing `years`."""
    try:
        divs = fetcher.fetch_all_historical_dividends(symbol)
        time.sleep(sleep)
        if divs is None or divs.empty:
            return False
        last_div_date = divs.index[-1]
        cutoff = datetime.now() - timedelta(days=years * 365)
        return last_div_date >= cutoff
    except Exception as e:
        print(f"[WARN] {symbol}: dividend check failed ({e})")
        return False


def write_dividend_watchlist(symbols: list[str], out_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["symbol", "score", "date"])
    for sym in symbols:
        ws.append([sym, "", ""])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main():
    parser = argparse.ArgumentParser(description="Refresh current S&P 500 constituent and dividend-payer lists.")
    parser.add_argument("--out-full", type=str, default="data/SP500_Companies.xlsx")
    parser.add_argument("--out-dividend", type=str, default="data/divList.xlsx")
    parser.add_argument("--years", type=int, default=5, help="Lookback window for 'recent dividend' (default: 5)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N symbols (for testing)")
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay between dividend-history requests (seconds)")
    args = parser.parse_args()

    print("Fetching current S&P 500 constituent list from Wikipedia...")
    df = fetch_sp500_table()
    if args.limit:
        df = df.head(args.limit)
    print(f"Retrieved {len(df)} constituents.")

    out_full = Path(args.out_full)
    write_full_list(df, out_full)
    print(f"[OK] Wrote full constituent list ({len(df)} tickers) -> {out_full}")

    print(f"Checking dividend history (last {args.years} years) for each constituent...")
    fetcher = DataFetcher()
    dividend_payers = []
    for i, sym in enumerate(df["symbol"], start=1):
        if has_recent_dividend(fetcher, sym, args.years, args.sleep):
            dividend_payers.append(sym)
        if i % 25 == 0 or i == len(df):
            print(f"  ...{i}/{len(df)} checked, {len(dividend_payers)} qualifying so far")

    out_div = Path(args.out_dividend)
    write_dividend_watchlist(dividend_payers, out_div)
    print(f"[OK] Wrote dividend-payer watchlist ({len(dividend_payers)} tickers) -> {out_div}")


if __name__ == "__main__":
    main()
