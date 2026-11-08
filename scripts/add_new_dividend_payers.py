"""Filter candidate tickers for dividend payers and append the qualifying,
not-yet-tracked symbols to data/divList.xlsx.

Combines three sources:
  1. data/SP500_Companies.xlsx (S&P 500 + Nasdaq-100 -- run
     update_sp500_nasdaq.py first to refresh it)
  2. market_dashboard's ALL_STOCKS universe
  3. the good_fundamental screener's ticker column

To score the resulting watchlist, use export_scores.py.

Usage:
    python scripts/add_new_dividend_payers.py
"""
import argparse
import csv
import importlib.util
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.data.fetcher import DataFetcher

UNIVERSE_PY = r"D:\projects\AI\projects\market_dashboard\universe.py"
SCREENER_CSV = (
    r"D:\projects\AI\projects\youtue_strategy_back_tester\screener"
    r"\good_fundamental_score\reports\good_fundamental_2026-11-06.csv"
)
SP500_NASDAQ_XLSX = "data/SP500_Companies.xlsx"


def load_all_stocks(path: str) -> set[str]:
    spec = importlib.util.spec_from_file_location("universe", path)
    universe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(universe)
    return set(universe.ALL_STOCKS)


def load_csv_tickers(path: str) -> set[str]:
    tickers = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row.get("ticker")
            if t:
                tickers.add(t.strip().upper())
    return tickers


def load_sp500_nasdaq(xlsx_path: str) -> set[str]:
    """Symbols from the 'basics' sheet of update_sp500_nasdaq.py's output."""
    path = Path(xlsx_path)
    if not path.exists():
        print(f"[WARN] {path} not found -- run update_sp500_nasdaq.py first; skipping this source")
        return set()
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["basics"]
    syms = {str(r[0]).strip().upper() for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
    wb.close()
    return syms


def load_existing_symbols(xlsx_path: Path) -> set[str]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["Sheet1"]
    syms = {str(r[0]).strip().upper() for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
    wb.close()
    return syms


def has_recent_dividend(fetcher: DataFetcher, symbol: str, years: int, sleep: float) -> bool:
    try:
        divs = fetcher.fetch_all_historical_dividends(symbol)
        time.sleep(sleep)
        if divs is None or divs.empty:
            return False
        cutoff = datetime.now() - timedelta(days=years * 365)
        return divs.index[-1] >= cutoff
    except Exception as e:
        print(f"[WARN] {symbol}: dividend check failed ({e})")
        return False


def append_symbols(xlsx_path: Path, new_symbols: list[str]) -> None:
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Sheet1"]
    for sym in new_symbols:
        ws.append([sym, None, None])
    wb.save(xlsx_path)


def main():
    parser = argparse.ArgumentParser(description="Append dividend-paying tickers from external lists to divList.xlsx")
    parser.add_argument("--target", type=str, default="data/divList.xlsx")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=None, help="Only check the first N candidates (for testing)")
    parser.add_argument("--sp500-nasdaq", type=str, default=SP500_NASDAQ_XLSX,
                         help="Path to update_sp500_nasdaq.py's output (default: data/SP500_Companies.xlsx)")
    args = parser.parse_args()

    target = Path(args.target)

    print("Loading source lists...")
    combined = (
        load_sp500_nasdaq(args.sp500_nasdaq)
        | load_all_stocks(UNIVERSE_PY)
        | load_csv_tickers(SCREENER_CSV)
    )
    print(f"Combined source list: {len(combined)} unique tickers")

    existing = load_existing_symbols(target)
    print(f"Already tracked in {target}: {len(existing)} tickers")

    candidates = sorted(combined - existing)
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"New candidates to check: {len(candidates)}")

    fetcher = DataFetcher()
    qualifying = []
    for i, sym in enumerate(candidates, start=1):
        if has_recent_dividend(fetcher, sym, args.years, args.sleep):
            qualifying.append(sym)
        if i % 25 == 0 or i == len(candidates):
            print(f"  ...{i}/{len(candidates)} checked, {len(qualifying)} qualifying so far")

    append_symbols(target, qualifying)
    print(f"[OK] Appended {len(qualifying)} dividend-paying tickers to {target}")


if __name__ == "__main__":
    main()
