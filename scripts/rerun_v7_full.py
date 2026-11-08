"""One-off: recompute V7 (fundamental-check) quality/risk for every symbol in
scores.csv using the freshly-calibrated vendored skill, and write the new
values alongside the old ones for comparison.

Usage:
    python scripts/rerun_v7_full.py
"""
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
    scores_path = Path("scores.csv")
    with scores_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    symbols = [r["symbol"] for r in rows]
    print(f"Re-running V7 fundamental-check on {len(symbols)} symbols...")

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(check_one, sym): sym for sym in symbols}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            sym = futures[fut]
            done += 1
            res = fut.result()
            results[sym] = res
            status = res["error"] or f"quality={res['quality']} risk={res['risk']}"
            if done % 25 == 0 or done == len(symbols):
                print(f"  ...{done}/{len(symbols)} done")

    out_path = Path("scores_v7_recalibrated.csv")
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
        print(f"[INFO] {len(failed)} symbols could not be scored: {', '.join(failed)}")


if __name__ == "__main__":
    main()
