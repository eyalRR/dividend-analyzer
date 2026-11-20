"""Run the fundamental-check skill (dividend_analyzer's V7_FUNDAMENTAL_CHECK
algorithm) on symbols missing quality/risk scores in scores.csv, and merge
the results back in.

Reuses dividend_analyzer.algorithms.v7_fundamental_check.run_fundamental_check,
the same subprocess wrapper the pipeline's v7_fundamental_check algorithm
uses, so this script and `--version v7_fundamental_check` never drift apart.

Usage:
    python scripts/run_fundamental_check.py
    python scripts/run_fundamental_check.py --limit 10   # quick test run
"""
import argparse
import concurrent.futures
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.algorithms.v7_fundamental_check import run_fundamental_check


def check_one(ticker: str) -> dict:
    """Run fundamental_check.py on one ticker; return a result dict, never raises."""
    check = run_fundamental_check(ticker)
    return {
        "symbol": ticker,
        "quality": check["quality"],
        "risk": check["risk"],
        "error": check["error"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=str, default="scores.csv")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="Only check the first N missing symbols (for testing)")
    args = parser.parse_args()

    scores_path = Path(args.scores)
    with scores_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    missing = [r["symbol"] for r in rows if not r.get("quality")]
    if args.limit:
        missing = missing[: args.limit]
    print(f"{len(missing)} symbols missing quality/risk; running fundamental-check on them...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(check_one, sym): sym for sym in missing}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            sym = futures[fut]
            done += 1
            res = fut.result()
            results[sym] = res
            status = res["error"] or f"quality={res['quality']} risk={res['risk']}"
            print(f"  [{done}/{len(missing)}] {sym}: {status}")

    updated = 0
    for r in rows:
        res = results.get(r["symbol"])
        if res and res["quality"] is not None:
            r["quality"] = res["quality"]
            r["risk"] = res["risk"]
            updated += 1

    with scores_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    failed = [sym for sym, res in results.items() if res["quality"] is None]
    print(f"[OK] Updated {updated}/{len(missing)} rows in {scores_path}")
    if failed:
        print(f"[INFO] {len(failed)} symbols could not be scored: {', '.join(failed)}")


if __name__ == "__main__":
    main()
