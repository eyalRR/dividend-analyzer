"""Orchestrate the full pipeline end to end: refresh the S&P 500 + Nasdaq-100
reference list, filter all sources for dividend payers into data/divList.xlsx,
then run the full multi-version scan on the result.

This is a thin wrapper -- each step's real logic lives in its own script:
  1. update_sp500_nasdaq.py  -- refresh data/SP500_Companies.xlsx
  2. add_new_dividend_payers.py -- filter it (+ the added universe) for
     dividend payers, update data/divList.xlsx
  3. export_scores.py        -- run the full scan, write the CSV

Usage:
    python scripts/full_universe_scan.py
    python scripts/full_universe_scan.py --out scores_test.csv --limit 20
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_sp500_nasdaq
import add_new_dividend_payers
import export_scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default="scores.csv")
    parser.add_argument("--divlist", type=str, default="data/divList.xlsx")
    parser.add_argument("--sp500-nasdaq-xlsx", type=str, default="data/SP500_Companies.xlsx")
    parser.add_argument("--years", type=int, default=5, help="Dividend lookback window (default: 5)")
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay between dividend-history requests (seconds)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N symbols at each step (for testing)")
    args = parser.parse_args()

    print("=== Step 1/3: refresh S&P 500 + Nasdaq-100 reference list ===")
    df = update_sp500_nasdaq.fetch_combined_table()
    if args.limit:
        df = df.head(args.limit)
    sp500_nasdaq_path = Path(args.sp500_nasdaq_xlsx)
    update_sp500_nasdaq.write_full_list(df, sp500_nasdaq_path)
    print(f"[OK] Wrote {len(df)} tickers -> {sp500_nasdaq_path}")

    print("\n=== Step 2/3: filter for dividend payers, update divList.xlsx ===")
    divlist_path = Path(args.divlist)
    combined = (
        add_new_dividend_payers.load_sp500_nasdaq(str(sp500_nasdaq_path))
        | add_new_dividend_payers.load_all_stocks(add_new_dividend_payers.UNIVERSE_PY)
        | add_new_dividend_payers.load_csv_tickers(add_new_dividend_payers.SCREENER_CSV)
    )
    existing = add_new_dividend_payers.load_existing_symbols(divlist_path) if divlist_path.exists() else set()
    candidates = sorted(combined - existing)
    if args.limit:
        candidates = candidates[: args.limit]
    print(f"Combined universe: {len(combined)} tickers, {len(candidates)} new candidates to check")

    from dividend_analyzer.data.fetcher import DataFetcher
    fetcher = DataFetcher()
    qualifying = []
    for i, sym in enumerate(candidates, start=1):
        if add_new_dividend_payers.has_recent_dividend(fetcher, sym, args.years, args.sleep):
            qualifying.append(sym)
        if i % 25 == 0 or i == len(candidates):
            print(f"  ...{i}/{len(candidates)} checked, {len(qualifying)} qualifying so far")

    if not divlist_path.exists():
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["symbol", "score", "date"])
        divlist_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(divlist_path)
    if qualifying:
        add_new_dividend_payers.append_symbols(divlist_path, qualifying)
    print(f"[OK] Appended {len(qualifying)} new dividend-paying tickers -> {divlist_path}")

    print("\n=== Step 3/3: run the full scan ===")
    symbols = export_scores.load_symbols_from_xlsx(str(divlist_path))
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Scanning {len(symbols)} symbols from {divlist_path}...")
    rows, fieldnames = export_scores.run_full_scan(symbols)

    import csv
    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] Wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
