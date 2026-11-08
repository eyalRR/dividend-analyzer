"""Retry just the symbols that failed (typically rate-limited) in
scores_v7_recalibrated.csv, with low concurrency, and patch the results back
into that file in place.

Usage:
    python scripts/rerun_v7_retry_failed.py
"""
import concurrent.futures
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dividend_analyzer.algorithms.v7_fundamental_check import run_fundamental_check


def check_one(ticker: str) -> dict:
    check = run_fundamental_check(ticker)
    return {
        "symbol": ticker,
        "quality": check["quality"],
        "risk": check["risk"],
        "avoid": check["avoid"],
        "error": check["error"],
    }


def main():
    out_path = Path("scores_v7_recalibrated.csv")
    with out_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    failed = [r["symbol"] for r in rows if r["error"]]
    print(f"Retrying {len(failed)} previously-failed symbols with low concurrency...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        futures = {}
        for sym in failed:
            futures[ex.submit(check_one, sym)] = sym
            time.sleep(1.5)
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            sym = futures[fut]
            done += 1
            res = fut.result()
            results[sym] = res
            if done % 20 == 0 or done == len(failed):
                print(f"  ...{done}/{len(failed)} done")

    for r in rows:
        sym = r["symbol"]
        res = results.get(sym)
        if res:
            r["new_quality"] = res["quality"] if res["quality"] is not None else r["new_quality"]
            r["new_risk"] = res["risk"] if res["risk"] is not None else r["new_risk"]
            r["new_avoid"] = res["avoid"] if res["avoid"] is not None else r["new_avoid"]
            r["error"] = res["error"] or ""

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["symbol", "old_quality", "old_risk", "new_quality", "new_risk", "new_avoid", "error"]
        )
        writer.writeheader()
        writer.writerows(rows)

    still_failed = [r["symbol"] for r in rows if r["error"]]
    print(f"[OK] Updated {out_path}")
    if still_failed:
        print(f"[INFO] {len(still_failed)} symbols still unscoreable: {', '.join(still_failed)}")


if __name__ == "__main__":
    main()
