"""Batch-score a list of tickers across all algorithm versions and write a single CSV.

Usage:
    python scripts/export_scores.py MSFT,AAPL,GOOG,ARM --out scores.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.data.fetcher import DataFetcher
from dividend_analyzer.algorithms.factory import get_algorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion


def main():
    parser = argparse.ArgumentParser(description="Export multi-version dividend scores for a list of tickers to CSV.")
    parser.add_argument("symbols", type=str, help="Comma-separated ticker symbols (e.g. MSFT,AAPL,GOOG,ARM)")
    parser.add_argument("--out", type=str, default="scores.csv", help="Output CSV path")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    fetcher = DataFetcher()
    benchmark_yield = fetcher.get_benchmark_dividend_yield()
    versions = list(AlgorithmVersion)

    rows = []
    for sym in symbols:
        row = {"symbol": sym, "company_name": "", "price": "", "status": "ok"}
        for v in versions:
            row[v.value] = ""

        history, info = fetcher.fetch_stock_data(sym)
        if history is None or history.empty or not info:
            row["status"] = "fetch_failed"
            rows.append(row)
            print(f"[WARN] {sym}: failed to fetch data (invalid ticker or no history)")
            continue

        for v in versions:
            try:
                algo = get_algorithm(v)
                res = algo.analyze(sym, history, info, benchmark_yield)
                row[v.value] = round(res.final_score, 4)
                row["company_name"] = res.company_name
                row["price"] = res.current_price
            except Exception as e:
                row[v.value] = ""
                print(f"[WARN] {sym}/{v.value}: {e}")

        rows.append(row)

    fieldnames = ["symbol", "company_name", "price", "status"] + [v.value for v in versions]
    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[OK] Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
