#!/usr/bin/env python3
"""
test_fail_closed.py -- the tool must refuse to score, not guess, when Yahoo returns nothing.

Why this exists: with an empty company record the tool used to pick a rulebook by guessing
("net interest income row present, so a bank"). 97% of non-bank companies have that row, so a
rate-limited run sent AAP and BXP (both AVOID) to the bank rulebook, which skips 30 of 46
checks, and they came back AVOID=False with Risk 0; a healthy utility came back 100/0.

No network, no real waiting: Yahoo is replaced by a fake and time.sleep is recorded instead of
slept. Run it with:  python tests/test_fail_closed.py     (exit 0 = all passed)
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fundamental_check as fc  # noqa: E402

GOOD_INFO = {"sector": "Technology", "industry": "Software", "longName": "Fake Corp"}
GOOD_DF = pd.DataFrame({"2025-12-31": [1.0]}, index=["Total Revenue"])


class Plan:
    """What each section returns on successive calls; the last entry repeats forever."""

    def __init__(self, **sections):
        self.seq = {k: list(v) for k, v in sections.items()}

    def next(self, label):
        s = self.seq[label]
        return s.pop(0) if len(s) > 1 else s[0]


def fake_yf(plan):
    class T:
        def __init__(self, symbol):
            pass

        info = property(lambda self: plan.next("info"))
        income_stmt = property(lambda self: plan.next("income_stmt"))
        balance_sheet = property(lambda self: plan.next("balance_sheet"))
        cashflow = property(lambda self: plan.next("cashflow"))
    return T


def healthy(**overrides):
    base = dict(info=[GOOD_INFO], income_stmt=[GOOD_DF], balance_sheet=[GOOD_DF], cashflow=[GOOD_DF])
    base.update(overrides)
    return Plan(**base)


failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{('  -- ' + detail) if (detail and not cond) else ''}")
    if not cond:
        failures.append(name)


def with_fakes(plan, fn):
    """Run fn() with a fake Yahoo, recorded sleeps, and scratch report/log locations."""
    waits, saved = [], (fc.yf.Ticker, fc.time.sleep, fc.REPORTS_DIR, fc.ERROR_LOG, fc.resolve)
    tmp = Path(tempfile.mkdtemp())
    try:
        fc.yf.Ticker = fake_yf(plan)
        fc.time.sleep = lambda s: waits.append(s)
        fc.REPORTS_DIR, fc.ERROR_LOG = tmp / "reports", tmp / "errors.log"
        fc.resolve = lambda u: ("FAKE", ["FAKE"])
        fc.DIAG["notes"].clear()
        return fn(), waits, tmp
    finally:
        fc.yf.Ticker, fc.time.sleep, fc.REPORTS_DIR, fc.ERROR_LOG, fc.resolve = saved


print("fetch_core")
(got, missing), waits, _ = with_fakes(healthy(), lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("everything present: nothing missing, no waiting", missing == [] and waits == [], f"{missing} {waits}")

(got, missing), waits, _ = with_fakes(healthy(info=[{}, GOOD_INFO]), lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("info empty once, then arrives: retried after one 30s wait, nothing missing",
      missing == [] and waits == [30], f"missing={missing} waits={waits}")

(got, missing), waits, _ = with_fakes(healthy(info=[{}]), lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("info empty every time: gives up after 2 retries, 30s apart",
      missing == ["info"] and waits == [30, 30], f"missing={missing} waits={waits}")

(got, missing), waits, _ = with_fakes(healthy(info=[{"longName": "X"}]), lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("a record with NO SECTOR counts as missing, even though it is not empty", missing == ["info"], str(missing))

(got, missing), waits, _ = with_fakes(healthy(cashflow=[pd.DataFrame()]), lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("an empty cash flow table counts as missing", missing == ["cashflow"], str(missing))

(got, missing), waits, _ = with_fakes(healthy(info=[{}], income_stmt=[pd.DataFrame()]),
                                      lambda: fc.fetch_core("FAKE", fc.yf.Ticker("FAKE")))
check("several sections missing share ONE wait per round (max 60s total, not 60s each)",
      sorted(missing) == ["income_stmt", "info"] and waits == [30, 30], f"{missing} {waits}")

print("\nmain() when data never arrives")


def run_main():
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fc.main(["x", "FAKE"])
    return code, out.getvalue(), err.getvalue()


(code, out, err), waits, tmp = with_fakes(healthy(info=[{}]), run_main)
check("exit code 2 (unscoreable)", code == 2, str(code))
check("stdout shows -255 for both scores", f"QUALITY {fc.SENTINEL_SCORE} / 100" in out and f"RISK {fc.SENTINEL_SCORE} / 100" in out, out[:200])
check("first stderr line is the reason (the screener reads exactly this line)",
      err.splitlines()[0].startswith("Required data missing for FAKE") and "info" in err.splitlines()[0], err[:200])
check("waited twice, 30s each, before giving up", waits == [30, 30], str(waits))
log = (tmp / "errors.log").read_text(encoding="utf-8") if (tmp / "errors.log").exists() else ""
check("an error line was written to the log, with symbol and reason",
      "| FAKE |" in log and "Required data missing" in log and "info" in log, log[:200])
errs = list((tmp / "reports").glob("*.error.json"))
check("error JSON written under its own .error.json name (cannot overwrite a good report)", len(errs) == 1, str(errs))
if errs:
    d = json.loads(errs[0].read_text(encoding="utf-8"))
    check("JSON: status=error, quality=-255, risk=-255", d["status"] == "error" and d["quality"] == -255 and d["risk"] == -255, str(d)[:200])
    check("JSON: avoid is null, never False (unknown is not a clean bill of health)", d["avoid"] is None, repr(d["avoid"]))
    check("JSON: names the missing section", d["missing"] == ["info"], str(d["missing"]))
check("no AVOID banner and no green flags were printed", not out.startswith("AVOID") and "GREEN FLAGS" not in out, out[:120])

print("\nthe guess is gone")
m = fc.Metrics(symbol="X")
m.sector, m.industry = "", ""
m.data = {"net_interest_income": 5.0, "revenue": 100.0, "net_ppe": 90.0, "total_assets": 100.0, "net_income": 10.0}
check("no sector + a 'Net Interest Income' row is NOT routed to financials",
      fc.choose_rulebook(m)[0] != "financials", str(fc.choose_rulebook(m)))
check("no sector + heavy PPE is NOT routed to capital_intensive",
      fc.choose_rulebook(m)[0] != "capital_intensive", str(fc.choose_rulebook(m)))

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
