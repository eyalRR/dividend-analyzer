"""Run the vendored fundamental-check skill on symbols missing quality/risk
scores in scores.csv, and merge the results back in.

fundamental_check.py is a self-contained, deterministic Quality/Risk gauntlet
vendored (unmodified) from youtue_strategy_back_tester's fundamental-check
skill (vendor/fundamental-check/). It is run once per symbol, as its own
subprocess -- same pattern that project's own scan.py orchestrator uses.

Usage:
    python scripts/run_fundamental_check.py
    python scripts/run_fundamental_check.py --limit 10   # quick test run
"""
import argparse
import concurrent.futures
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNDAMENTAL_CHECK = REPO_ROOT / "vendor" / "fundamental-check" / "fundamental_check.py"


def check_one(ticker: str) -> dict:
    """Run fundamental_check.py on one ticker; return a result dict, never raises."""
    row = {"symbol": ticker, "quality": None, "risk": None, "error": None}
    try:
        proc = subprocess.run(
            [sys.executable, str(FUNDAMENTAL_CHECK), ticker],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        row["error"] = "timed out"
        return row

    if proc.returncode == 2:
        first_line = (proc.stderr.strip().splitlines() or ["unresolvable / insufficient data"])[0]
        row["error"] = first_line
        return row

    json_line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("JSON: ")), None)
    if not json_line:
        row["error"] = "no JSON path reported"
        return row

    jpath = Path(json_line[len("JSON: "):].strip())
    try:
        data = json.loads(jpath.read_text(encoding="utf-8"))
        row["quality"] = data["quality"]
        row["risk"] = data["risk"]
    except Exception as e:
        row["error"] = f"could not read report JSON ({type(e).__name__})"
    return row


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
