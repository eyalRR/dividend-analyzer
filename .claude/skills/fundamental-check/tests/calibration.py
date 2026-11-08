#!/usr/bin/env python3
"""
calibration.py -- regression test for fundamental_check.py.

Runs the tool on ~38 real companies whose health is already known and checks that
each lands in the expected range. Run it after changing ANY threshold or rule:

    python tests/calibration.py                 # every company
    python tests/calibration.py AAPL TEVA.TA    # just these

Exit code 0 = every expectation held, 1 = at least one company drifted.

Self-contained: standard library only, calls the tool as a subprocess, imports
nothing from the surrounding repo. It needs the network (live Yahoo Finance data).
See README.md in this folder for what this is and how to maintain it.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "fundamental_check.py"

# ---------------------------------------------------------------------------
# Expectations. Deliberately RANGES, not exact scores: the data is live and moves
# every quarter, so an exact number would fail for reasons that mean nothing.
#
#   q      = (min, max) Quality      r = (min, max) Risk
#   avoid  = must the AVOID banner (exit code 1) be present?
#   rb     = rulebook that must have been chosen (optional)
#   waived = the liquidity waiver must have fired (optional)
#   why    = what this company is here to prove
# ---------------------------------------------------------------------------
Q_GOOD = (70, 100)
R_LOW = (0, 25)

EXPECT = {
    # --- Tier 1: healthy. High quality, low risk, never flagged. ---
    "MSFT":    dict(q=(90, 100), r=(0, 20), avoid=False, why="gold-standard software model"),
    "GOOGL":   dict(q=Q_GOOD, r=R_LOW, avoid=False, why="net cash, high margins"),
    "NVDA":    dict(q=Q_GOOD, r=R_LOW, avoid=False, why="extreme ROIC"),
    "KLAC":    dict(q=Q_GOOD, r=R_LOW, avoid=False, why="high-margin hardware"),
    "LLY":     dict(q=Q_GOOD, r=R_LOW, avoid=False, why="high growth, heavy R&D"),
    "ISRG":    dict(q=Q_GOOD, r=R_LOW, avoid=False, why="a high P/E must not read as risk"),
    "ANET":    dict(q=Q_GOOD, r=R_LOW, avoid=False, why="fast growth, no debt"),
    "PG":      dict(q=Q_GOOD, r=R_LOW, avoid=False, why="defensive cash machine"),
    "COST":    dict(q=Q_GOOD, r=R_LOW, avoid=False, why="negative working capital operator"),
    "CAMT.TA": dict(q=Q_GOOD, r=R_LOW, avoid=False,
                    why="Yahoo EBITDA is corrupt for one quarter; the tool must repair it"),
    "MTRX.TA": dict(q=Q_GOOD, r=R_LOW, avoid=False, why="clean ILS statements"),
    "NICE.TA": dict(q=Q_GOOD, r=R_LOW, avoid=False, why="quote in agorot, statements in USD"),
    "NVMI.TA": dict(q=(65, 100), r=R_LOW, avoid=False,
                    why="TASE tech; dilution holds quality below 85"),

    # --- Tier 2: mixed / rulebook edge cases. Must NOT be flagged by mistake. ---
    "AAPL":    dict(q=(70, 100), r=(0, 20), avoid=False, waived=True,
                    why="LIQUIDITY WAIVER: current 1.0 / quick 0.85 must not read as risk"),
    "ESLT.TA": dict(q=(55, 90), r=R_LOW, avoid=False,
                    why="defense prime, USD statements, agorot quote"),
    "POLI.TA": dict(q=(45, 100), r=R_LOW, avoid=False, rb="financials",
                    why="bank: no D/E, EBITDA or FCF"),
    "LUMI.TA": dict(q=(35, 100), r=R_LOW, avoid=False, rb="financials",
                    why="bank with a thinner equity cushion"),
    "BAC":     dict(q=(45, 100), r=R_LOW, avoid=False, rb="financials", why="US bank"),
    "JPM":     dict(q=(45, 100), r=R_LOW, avoid=False, rb="financials",
                    why="bank with NEGATIVE operating cash flow (-$84B): loan/deposit flows must not AVOID it"),
    "O":       dict(q=(50, 90), r=(0, 40), avoid=False, rb="reit", why="REIT rulebook"),
    "DUK":     dict(q=(40, 80), r=(10, 55), avoid=False, rb="capital_intensive",
                    why="utility: permanently negative FCF is not a cash runway"),
    "NEE":     dict(q=(40, 80), r=(10, 55), avoid=False, rb="capital_intensive",
                    why="utility: high net debt/EBITDA is structural"),
    "ENLT.TA": dict(q=(30, 80), r=(10, 60), avoid=False, rb="capital_intensive",
                    why="renewables project finance"),
    "TEVA.TA": dict(q=(35, 75), r=(30, 65), avoid=False,
                    why="levered turnaround: EBIT coverage 1.42x is under the floor because of ~$2.2B "
                        "of special charges, but operating income (3.84x) and cash (3.05x) both cover "
                        "interest -- the cash-backed waiver must keep it off AVOID"),
    # The next two exist to exercise the coverage waiver on companies other than Teva, so the
    # rule is not tested by a single name. WS was tried first and dropped: the waiver works on
    # it, but a newer quarter turned its net income negative (-$38M) and the dividend-trap gate
    # now AVOIDs it for an unrelated reason.
    "GPC":     dict(q=(30, 75), r=(20, 65), avoid=False,
                    why="waiver fires (EBIT cov 0.93x; operating income 6.57x, cash 7.59x) AND the "
                        "leverage ceiling goes to WATCH at 5.8x net debt/EBITDA"),
    "VIAV":    dict(q=(35, 80), r=(0, 40), avoid=False,
                    why="waiver alone (EBIT cov 1.37x; operating income 2.78x, cash 3.62x) at 0.3x "
                        "leverage, so the leverage ceiling is not involved"),
    # The next two exercise the dividend-trap waiver: net income is negative because of charges,
    # but free cash flow covers the dividend several times over and was positive in 4 of 4 years.
    "GILD":    dict(q=(35, 90), r=(0, 50), avoid=False,
                    why="DIVIDEND-TRAP WAIVER: net income -$3.9B (acquired R&D charges), but FCF +$13.8B "
                        "covers the $4.1B dividend 3.4x; the waiver must keep it off AVOID"),
    "BC":      dict(q=(35, 85), r=(10, 60), avoid=False,
                    why="both waivers at once: EBIT coverage negative (operating income 2.8x, cash 5.7x) "
                        "AND net income negative with FCF covering the dividend 3.0x"),
    "AMZN":    dict(q=(50, 90), r=(0, 35), avoid=False, why="leases, heavy capex"),
    "DIS":     dict(q=(50, 90), r=(0, 35), avoid=False, why="heavy goodwill"),
    "ICL.TA":  dict(q=(30, 75), r=(0, 35), avoid=False, why="cyclical at a trough"),
    "TSLA":    dict(q=(10, 60), r=(0, 35), avoid=False, why="16% dilution and thin margins"),

    # --- Tier 3: distressed. Must be flagged, exit 1, high risk. ---
    # AMC's job is the gates: negative equity (-$1.89B), dilution 23.8%, coverage 0.76x, Altman
    # Z'' -4.35, Risk 90. Those are unchanged. Its Quality ceiling was raised 30 -> 60 on
    # 2026-11-08 because one strong quarter (revenue +31.6%, operating income +594% vs the
    # year-ago quarter) lifted the growth pillar to 49 without touching any gate -- the
    # single-quarter trade-off documented in rulebook.md. If Quality drifts above 60 while the
    # gates still fire, that is the same noise; if a GATE stops firing, that is a real failure.
    "AMC":     dict(q=(0, 60), r=(70, 100), avoid=True,
                    why="negative equity + dilution: the gates must fire, whatever one quarter does to Quality"),
    "AAP":     dict(q=(0, 45), r=(55, 100), avoid=True,
                    why="CONTROL for the coverage waiver: EBIT cov 0.35x and operating income only "
                        "1.16x, so the waiver must NOT apply even though cash coverage is 3.24x"),
    "APD":     dict(q=(0, 55), r=(60, 100), avoid=True,
                    why="CONTROL for the dividend-trap waiver: net income negative AND free cash flow "
                        "(-$301M) does not cover the $1.6B dividend, so the waiver must NOT apply"),
    "PLUG":    dict(q=(0, 40), r=(70, 100), avoid=True, why="cash burn"),
    "IEP":     dict(q=(0, 30), r=(70, 100), avoid=True, why="dividend paid out of losses"),
    "SPCE":    dict(q=(0, 30), r=(70, 100), avoid=True, rb="pre_revenue",
                    why="pre-revenue, heavy dilution"),
    "MSTR":    dict(q=(0, 30), r=(70, 100), avoid=True, why="negative EBITDA with net debt"),
    "BYND":    dict(q=(0, 40), r=(70, 100), avoid=True, why="cash burn, equity erosion"),
    "OPEN":    dict(q=(0, 40), r=(70, 100), avoid=True, why="negative EBITDA with net debt"),
    "PSEC":    dict(q=(0, 70), r=(60, 100), avoid=True,
                    why="dividend trap (a BDC scored on the bank rulebook)"),
    "GCT.TA":  dict(q=(0, 80), r=(60, 100), avoid=True,
                    why="13x net debt/EBITDA on thin coverage"),
    "EVGN.TA": dict(q=(0, 40), r=(70, 100), avoid=True, rb="pre_revenue",
                    why="negative EBITDA but net cash: the runway gate fires, not leverage"),
    "MTRN.TA": dict(q=(0, 80), r=(70, 100), avoid=True,
                    why="micro-cap: fails all three tradability gates"),
}

PAUSE_SECONDS = 5   # Yahoo rate-limits; be polite between companies
RETRIES = 2


def run_tool(ticker):
    """Run the tool once. Returns (exit_code, parsed_json_or_None)."""
    p = None
    for attempt in range(1, RETRIES + 1):
        p = subprocess.run([sys.executable, str(TOOL), ticker],
                           capture_output=True, text=True, timeout=300)
        report = None
        for line in reversed(p.stdout.splitlines()):
            if line.startswith("JSON: "):
                try:
                    report = json.loads(Path(line[6:].strip()).read_text(encoding="utf-8"))
                except Exception:
                    report = None
                break
        if report is not None or attempt == RETRIES:
            return p.returncode, report
        time.sleep(30)   # most likely a rate limit; wait it out once
    return 2, None


def check(exp, code, rep):
    """Return a list of human-readable failures (empty list = pass)."""
    if rep is None:
        return [f"no report produced (exit {code}) -- data unavailable or rate-limited"]
    if rep.get("status") == "error":
        return [f"tool refused to score (exit {code}): {str(rep.get('error', '?'))[:110]}"]
    fails = []
    q, r, avoid = rep.get("quality"), rep.get("risk"), bool(rep.get("avoid"))
    if "q" in exp and not (q is not None and exp["q"][0] <= q <= exp["q"][1]):
        fails.append(f"Quality {q} outside {exp['q']}")
    if "r" in exp and not (r is not None and exp["r"][0] <= r <= exp["r"][1]):
        fails.append(f"Risk {r} outside {exp['r']}")
    if avoid != exp["avoid"]:
        fails.append(f"AVOID is {avoid}, expected {exp['avoid']}")
    want_code = 1 if exp["avoid"] else 0
    if code != want_code:
        fails.append(f"exit code {code}, expected {want_code}")
    if "rb" in exp and rep.get("rulebook") != exp["rb"]:
        fails.append(f"rulebook '{rep.get('rulebook')}', expected '{exp['rb']}'")
    if exp.get("waived") and not rep.get("liquidity_waived"):
        fails.append("liquidity waiver did not fire")
    return fails


def main(argv):
    names = argv[1:] or list(EXPECT)
    unknown = [n for n in names if n not in EXPECT]
    if unknown:
        print("Not in EXPECT: " + ", ".join(unknown))
        return 2

    failures = {}
    print(f"{'ticker':9s} {'Q':>4s} {'R':>4s}  avoid  result")
    print("-" * 60)
    for i, t in enumerate(names):
        code, rep = run_tool(t)
        fails = check(EXPECT[t], code, rep)
        q = rep.get("quality") if rep else None
        r = rep.get("risk") if rep else None
        av = "yes" if rep and rep.get("avoid") else "no"
        print(f"{t:9s} {str(q):>4s} {str(r):>4s}  {av:5s}  {'ok' if not fails else 'DRIFT'}",
              flush=True)
        for f in fails:
            print(f"            - {f}   [{EXPECT[t]['why']}]")
        if fails:
            failures[t] = fails
        if i < len(names) - 1:
            time.sleep(PAUSE_SECONDS)

    print("-" * 60)
    if failures:
        print(f"{len(failures)} of {len(names)} drifted: {', '.join(failures)}")
        print("Read tests/README.md before editing an expectation -- a failure may be a real bug.")
        return 1
    print(f"all {len(names)} held")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
