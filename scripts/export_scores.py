"""Run the full multi-version scan: score a list of tickers across every
AlgorithmVersion (V1-V7) and write a single CSV. This is the canonical
"run the full scan on these symbols" script -- other scripts that need a
scan should call `run_full_scan()` below rather than reimplementing it.

Usage:
    python scripts/export_scores.py MSFT,AAPL,GOOG,ARM --out scores.csv
    python scripts/export_scores.py --from-xlsx data/divList.xlsx --out scores.csv
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.data.fetcher import DataFetcher
from dividend_analyzer.algorithms.factory import get_algorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion


def load_symbols_from_xlsx(xlsx_path: str) -> list[str]:
    """Symbol column from Sheet1 of a watchlist like data/divList.xlsx."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["Sheet1"]
    symbols = [str(r[0]).strip().upper() for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
    wb.close()
    return symbols


def run_full_scan(symbols: list[str]) -> tuple[list[dict], list[str]]:
    """Score every symbol across all AlgorithmVersion entries. Returns (rows, fieldnames)."""
    fetcher = DataFetcher()
    benchmark_yield = fetcher.get_benchmark_dividend_yield()
    versions = list(AlgorithmVersion)

    rows = []
    for i, sym in enumerate(symbols, start=1):
        row = {"symbol": sym, "company_name": "", "price": "", "status": "ok", "quality": "", "risk": ""}
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
                # v7_fundamental_check's final_score is a blend; also surface its two
                # underlying 0-100 scores on their own, same as the good_fundamental
                # screener's quality/risk columns (same skill, so the same meaning).
                if v == AlgorithmVersion.V7_FUNDAMENTAL_CHECK:
                    row["quality"] = res.conditions.get("Quality Score", "")
                    row["risk"] = res.conditions.get("Risk Score", "")
            except Exception as e:
                row[v.value] = ""
                print(f"[WARN] {sym}/{v.value}: {e}")

        rows.append(row)
        if i % 10 == 0 or i == len(symbols):
            print(f"  [{i}/{len(symbols)}] scanned")

    fieldnames = ["symbol", "company_name", "price", "status"] + [v.value for v in versions] + ["quality", "risk"]
    return rows, fieldnames


def main():
    parser = argparse.ArgumentParser(description="Export multi-version dividend scores for a list of tickers to CSV.")
    parser.add_argument("symbols", type=str, nargs="?", default=None,
                         help="Comma-separated ticker symbols (e.g. MSFT,AAPL,GOOG,ARM)")
    parser.add_argument("--from-xlsx", type=str, default=None,
                         help="Read symbols from this watchlist's Sheet1 instead (e.g. data/divList.xlsx)")
    parser.add_argument("--out", type=str, default="scores.csv", help="Output CSV path")
    args = parser.parse_args()

    if args.from_xlsx:
        symbols = load_symbols_from_xlsx(args.from_xlsx)
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        parser.error("provide either a comma-separated symbols list or --from-xlsx")

    rows, fieldnames = run_full_scan(symbols)

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[OK] Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
