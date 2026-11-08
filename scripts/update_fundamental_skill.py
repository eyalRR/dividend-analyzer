"""Pull an update to the vendored fundamental-check skill from its source
repo, re-apply our pipeline-integration patches on top, and run the skill's
own test suite against the result -- the "update and retest" workflow this
project has repeated by hand several times as the skill got calibrated.

What it does, in order:
  1. Reads fundamental_check.py (and SKILL.md/rulebook.md/README.md/
     .gitignore/tests/*) at the given commit (default: the source repo's
     current HEAD) from SOURCE_REPO.
  2. Re-applies our 4 patches to fundamental_check.py: prefetch injection
     (FUNDCHECK_PREFETCH_INFO/HISTORY), probe-cache reuse, and the
     FUNDCHECK_SKIP_CALENDAR/NEWS flags -- the same patches re-merged by
     hand for commits b4c92f4, 44702da and d141e1c. Each patch anchors on
     exact upstream text; if an anchor isn't found (upstream restructured
     that region), the script stops and says so instead of silently
     producing a broken merge -- that update needs a manual re-merge, same
     as before this script existed.
  3. Writes the merged files into our vendored
     .claude/skills/fundamental-check/ directory.
  4. Runs every tests/test_*.py (offline, instant) plus tests/calibration.py
     (network, ~5 min) against the patched copy, working around the
     Windows-codepage UnicodeDecodeError in calibration.py's own subprocess
     call (PYTHONUTF8=1) rather than patching that file.

Never commits anything -- inspect `git diff` and decide for yourself.

Usage:
    python scripts/update_fundamental_skill.py                  # pull latest, merge, test
    python scripts/update_fundamental_skill.py --commit a08a2b8  # pull a specific commit
    python scripts/update_fundamental_skill.py --skip-calibration  # skip the ~5 min network test
    python scripts/update_fundamental_skill.py --merge-only      # just merge, don't run tests
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDORED_DIR = REPO_ROOT / ".claude" / "skills" / "fundamental-check"
SOURCE_REPO = Path(r"D:\projects\AI\projects\youtue_strategy_back_tester")
SOURCE_SKILL_REL = ".claude/skills/fundamental-check"

PLAIN_FILES = ["SKILL.md", "rulebook.md", "README.md", ".gitignore"]
TEST_FILES = ["tests/README.md", "tests/calibration.py"]  # other tests/test_*.py discovered dynamically


# --------------------------------------------------------------------------
# The 4 patches, as exact (old, new) anchor pairs. Each `old` must appear
# exactly once in the freshly-pulled file; this is what lets a later skill
# update re-merge cleanly instead of silently drifting.
# --------------------------------------------------------------------------
PATCHES = [
    (
        "import json\nimport math\nimport random\nimport sys\nimport time\n",
        "import json\nimport math\nimport os\nimport random\nimport sys\nimport time\n",
    ),
    (
        'def note(msg):\n    DIAG["notes"].append(msg)\n\n\n'
        "# --------------------------------------------------------------------------\n"
        "# Network: backoff around yfinance, which rate-limits readily.\n",
        'def note(msg):\n    DIAG["notes"].append(msg)\n\n\n'
        "# --------------------------------------------------------------------------\n"
        "# Optional pre-fetched info/history injection -- off by default (no env vars\n"
        "# set, nothing changes). Set by a caller that already has fresh `info`/\n"
        "# `history` for this exact symbol (e.g. dividend_analyzer's pipeline, which\n"
        "# fetches both through its own SQLite-cached DataFetcher) to skip this\n"
        "# script's own `tk.info` / `tk.history()` calls -- 2 of its ~10 yfinance\n"
        "# requests per symbol. Every other fetch (statements, cashflow, calendar)\n"
        "# is unaffected; this script still gets to decide freshness for those.\n"
        "#\n"
        "# Checked once, before fetch_core()'s retry loop -- never inside it. A\n"
        "# retry builds a fresh yf.Ticker per round specifically because a reused one\n"
        "# can hand back the empty answer it already cached; injecting prefetched\n"
        "# data into that loop would defeat the same purpose, so a bad prefetch (or\n"
        "# none) is discarded for good and falls through to fetch_core's own normal\n"
        "# fresh-Ticker fetch/retry path.\n"
        "# --------------------------------------------------------------------------\n"
        "def load_prefetched_info():\n"
        '    path = os.environ.get("FUNDCHECK_PREFETCH_INFO")\n'
        "    if not path:\n"
        "        return None\n"
        "    try:\n"
        '        with open(path, "r", encoding="utf-8") as f:\n'
        "            data = json.load(f)\n"
        '        note("info: served from caller\'s pre-fetched data (FUNDCHECK_PREFETCH_INFO)")\n'
        "        return data\n"
        "    except Exception as e:\n"
        '        note(f"FUNDCHECK_PREFETCH_INFO unreadable ({type(e).__name__}); fetching info normally")\n'
        "        return None\n"
        "\n\n"
        "def load_prefetched_history():\n"
        '    path = os.environ.get("FUNDCHECK_PREFETCH_HISTORY")\n'
        "    if not path:\n"
        "        return None\n"
        "    try:\n"
        "        hist = pd.read_pickle(path)\n"
        '        note("history: served from caller\'s pre-fetched data (FUNDCHECK_PREFETCH_HISTORY)")\n'
        "        return hist\n"
        "    except Exception as e:\n"
        '        note(f"FUNDCHECK_PREFETCH_HISTORY unreadable ({type(e).__name__}); fetching history normally")\n'
        "        return None\n"
        "\n\n"
        "# --------------------------------------------------------------------------\n"
        "# Network: backoff around yfinance, which rate-limits readily.\n",
    ),
    (
        "def has_data(symbol):\n"
        "    t = yf.Ticker(symbol)\n"
        '    fin = fetch(f"probe {symbol}", lambda: t.income_stmt)\n'
        "    return fin is not None and not fin.empty\n",
        "# resolve()'s existence probe below fetches income_stmt to confirm a symbol has\n"
        "# data; fetch_core() can reuse it instead of fetching the same statement again.\n"
        "_PROBE_CACHE = {}\n"
        "\n\n"
        "def has_data(symbol):\n"
        "    t = yf.Ticker(symbol)\n"
        '    fin = fetch(f"probe {symbol}", lambda: t.income_stmt)\n'
        "    if fin is not None and not fin.empty:\n"
        "        _PROBE_CACHE[symbol] = fin\n"
        "    return fin is not None and not fin.empty\n",
    ),
    (
        'def fetch_core(symbol, tk):\n'
        '    """Fetch the sections a score cannot be trusted without. Returns (sections, missing).\n'
        "\n"
        "    Anything missing is retried together after one RETRY_WAIT_SECONDS wait per round, using a\n"
        "    fresh Ticker each time (a reused one can hand back the empty answer it already cached).\n"
        '    """\n'
        "    got = {}\n"
        "    for attempt in range(MAX_RETRIES + 1):",
        'def fetch_core(symbol, tk):\n'
        '    """Fetch the sections a score cannot be trusted without. Returns (sections, missing).\n'
        "\n"
        "    Anything missing is retried together after one RETRY_WAIT_SECONDS wait per round, using a\n"
        "    fresh Ticker each time (a reused one can hand back the empty answer it already cached).\n"
        "\n"
        "    A caller's pre-fetched info, or income_stmt reused from resolve()'s existence probe, is\n"
        "    checked ONCE here, before any retry -- never injected into the retry loop itself, which would\n"
        "    defeat the point of building a fresh Ticker each round. A bad or missing prefetch/probe value\n"
        "    is simply dropped and falls through to the normal fresh-Ticker fetch/retry path below.\n"
        '    """\n'
        "    got = {}\n"
        "    prefetched_info = load_prefetched_info()\n"
        "    if prefetched_info is not None and _info_ok(prefetched_info):\n"
        '        got["info"] = prefetched_info\n'
        "    probed_fin = _PROBE_CACHE.pop(symbol, None)\n"
        "    if probed_fin is not None and _has_rows(probed_fin):\n"
        '        note("income_stmt: reused from ticker-resolution probe (skipped duplicate fetch)")\n'
        '        got["income_stmt"] = probed_fin\n'
        "    for attempt in range(MAX_RETRIES + 1):",
    ),
    (
        '    qfin = fetch("quarterly_income_stmt", lambda: tk.quarterly_income_stmt)\n'
        '    qcf = fetch("quarterly_cashflow", lambda: tk.quarterly_cashflow)\n'
        '    hist = fetch("history", lambda: tk.history(period="3mo"))\n'
        '    calendar = fetch("calendar", lambda: tk.calendar, {}) or {}\n'
        "    fetched_at = dt.datetime.now(TLV_TZ)\n",
        '    qfin = fetch("quarterly_income_stmt", lambda: tk.quarterly_income_stmt)\n'
        '    qcf = fetch("quarterly_cashflow", lambda: tk.quarterly_cashflow)\n'
        "    hist = load_prefetched_history()\n"
        "    if hist is None:\n"
        '        hist = fetch("history", lambda: tk.history(period="3mo"))\n'
        "    # calendar (next earnings date) and news are purely informational --\n"
        "    # displayed in the report but never scored into Quality/Risk (see README) --\n"
        "    # so a caller that doesn't render those sections can skip fetching them.\n"
        '    if os.environ.get("FUNDCHECK_SKIP_CALENDAR"):\n'
        "        calendar = {}\n"
        "    else:\n"
        '        calendar = fetch("calendar", lambda: tk.calendar, {}) or {}\n'
        "    fetched_at = dt.datetime.now(TLV_TZ)\n",
    ),
    (
        '    news_price = m.price_usd if m.quote_ccy == "USD" else None\n'
        "    try:\n"
        "        news_info = news.annotate(symbol, news_price)\n"
        "    except Exception as e:\n"
        '        note(f"news unavailable ({type(e).__name__})")\n'
        '        news_info = {"headlines": [], "classified": None}\n',
        '    news_price = m.price_usd if m.quote_ccy == "USD" else None\n'
        '    if os.environ.get("FUNDCHECK_SKIP_NEWS"):\n'
        '        news_info = {"headlines": [], "classified": None}\n'
        "    else:\n"
        "        try:\n"
        "            news_info = news.annotate(symbol, news_price)\n"
        "        except Exception as e:\n"
        '            note(f"news unavailable ({type(e).__name__})")\n'
        '            news_info = {"headlines": [], "classified": None}\n',
    ),
]


def git_show(ref: str, rel_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(SOURCE_REPO), "show", f"{ref}:{SOURCE_SKILL_REL}/{rel_path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show {ref}:{rel_path} failed: {result.stderr.strip()}")
    return result.stdout


def apply_patches(src: str) -> str:
    merged = src
    for i, (old, new) in enumerate(PATCHES, start=1):
        count = merged.count(old)
        if count != 1:
            raise RuntimeError(
                f"Patch {i}/{len(PATCHES)} anchor found {count} times (expected 1) -- "
                "upstream likely restructured this region; re-merge by hand (see this "
                "script's docstring for what each patch does) and update PATCHES here."
            )
        merged = merged.replace(old, new, 1)
    return merged


def list_source_tests(ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(SOURCE_REPO), "ls-tree", "-r", "--name-only", ref,
         f"{SOURCE_SKILL_REL}/tests/"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-tree failed: {result.stderr.strip()}")
    prefix = f"{SOURCE_SKILL_REL}/"
    return [line[len(prefix):] for line in result.stdout.splitlines() if line.strip()]


def pull_and_merge(ref: str) -> None:
    print(f"Pulling fundamental-check at {ref} from {SOURCE_REPO}...")
    fc_src = git_show(ref, "fundamental_check.py")
    print("Re-applying pipeline-integration patches...")
    fc_merged = apply_patches(fc_src)
    (VENDORED_DIR / "fundamental_check.py").write_text(fc_merged, encoding="utf-8")
    print("  [OK] fundamental_check.py merged")

    for rel in PLAIN_FILES:
        try:
            content = git_show(ref, rel)
        except RuntimeError as e:
            print(f"  [SKIP] {rel}: {e}")
            continue
        (VENDORED_DIR / rel).write_text(content, encoding="utf-8")
        print(f"  [OK] {rel}")

    test_paths = list_source_tests(ref)
    for rel in test_paths:
        content = git_show(ref, rel)
        dest = VENDORED_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  [OK] {rel}")


def run_offline_tests() -> bool:
    tests_dir = VENDORED_DIR / "tests"
    test_files = sorted(p for p in tests_dir.glob("test_*.py"))
    all_ok = True
    for t in test_files:
        print(f"\n=== {t.name} ===")
        result = subprocess.run(
            [sys.executable, str(t)], cwd=str(VENDORED_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            print(f"[FAIL] {t.name}")
            all_ok = False
    return all_ok


def run_calibration() -> bool:
    calib = VENDORED_DIR / "tests" / "calibration.py"
    if not calib.exists():
        print("[SKIP] tests/calibration.py not present")
        return True
    print("\n=== tests/calibration.py (network, ~5 min) ===")
    # PYTHONUTF8=1 works around a Windows-codepage UnicodeDecodeError in this
    # script's own subprocess.run call -- not something we patch upstream.
    result = subprocess.run(
        [sys.executable, str(calib)], cwd=str(VENDORED_DIR),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("[FAIL] calibration.py")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", type=str, default="HEAD",
                         help="Commit/ref in the source repo to pull (default: HEAD)")
    parser.add_argument("--merge-only", action="store_true", help="Merge the update but skip all tests")
    parser.add_argument("--skip-calibration", action="store_true", help="Run offline tests only, skip the network calibration run")
    args = parser.parse_args()

    pull_and_merge(args.commit)

    if args.merge_only:
        print("\n[OK] Merged. --merge-only set, skipping tests. Review `git diff` before committing.")
        return

    print("\nRunning offline test suite...")
    offline_ok = run_offline_tests()

    calib_ok = True
    if not args.skip_calibration:
        calib_ok = run_calibration()

    print("\n" + "=" * 60)
    if offline_ok and calib_ok:
        print("[OK] All tests passed. Review `git diff` and commit if satisfied.")
    else:
        print("[FAIL] Something didn't hold -- do not commit yet. See output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
