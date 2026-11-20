"""Re-run V7 (fundamental-check) on every symbol in a scores CSV, at low
concurrency, and write old/new side by side for comparison.

Faster than a full export_scores.py rescan when only V7 -- i.e. the
fundamental-check skill itself -- changed: this skips re-scoring V1-V6,
which would otherwise re-fetch unchanged data for no reason. Typically run
right after update_fundamental_skill.py to see the production-wide effect
of a skill update, once its own test suite has already held.

An exit-2 / status "error" result (Yahoo rate-limited even after the
skill's own retries) is left blank here -- never written as a score -- so
it can be retried later. Keep --workers low (<=2): higher concurrency risks
contending with the skill's own rate-limit backoff.

Usage:
    python scripts/rescan_v7.py --source scores_backup_20261108.csv --out scores_v7_rescan.csv --workers 2
"""
import argparse
import concurrent.futures
import csv
import sys
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=str, default="scores.csv")
    parser.add_argument("--out", type=str, default="scores_v7_rescan.csv")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    with open(args.source, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    symbols = [r["symbol"] for r in rows]
    print(f"Re-running V7 on {len(symbols)} symbols (workers={args.workers})...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(check_one, sym): sym for sym in symbols}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            sym = futures[fut]
            done += 1
            res = fut.result()
            results[sym] = res
            if done % 25 == 0 or done == len(symbols):
                print(f"  ...{done}/{len(symbols)} done")

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["symbol", "old_quality", "old_risk", "new_quality", "new_risk", "new_avoid", "error"]
        )
        writer.writeheader()
        for r in rows:
            sym = r["symbol"]
            res = results.get(sym, {})
            writer.writerow(
                {
                    "symbol": sym,
                    "old_quality": r.get("quality", ""),
                    "old_risk": r.get("risk", ""),
                    "new_quality": res.get("quality", ""),
                    "new_risk": res.get("risk", ""),
                    "new_avoid": res.get("avoid", ""),
                    "error": res.get("error", ""),
                }
            )

    failed = [s for s, r in results.items() if r["quality"] is None]
    print(f"[OK] Wrote {out_path}")
    if failed:
        print(f"[INFO] {len(failed)} symbols unscored (retry later): {', '.join(failed)}")


if __name__ == "__main__":
    main()
