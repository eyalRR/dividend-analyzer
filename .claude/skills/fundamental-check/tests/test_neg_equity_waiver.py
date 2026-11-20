#!/usr/bin/env python3
"""
test_neg_equity_waiver.py -- the negative-equity gate's buyback waiver, case by case.

Book equity goes negative either from accumulated losses (distress) or from a cash machine
returning more than it earns (McDonald's, Yum). The waiver recognises only the second.
Pure functions, no network:

    python tests/test_neg_equity_waiver.py        (exit 0 = all passed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fundamental_check as fc  # noqa: E402

GATE = {c.cid: c for c in fc.build_checks()}["neg_equity"]
failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{('  -- ' + detail) if (detail and not cond) else ''}")
    if not cond:
        failures.append(name)


def gate(rulebook="default", **kw):
    data = dict(equity=-1.79e9, cfo=11.3e9, fcf=7.8e9, fcf_years_checked=4, fcf_positive_years=4,
                interest_coverage=7.9, share_change=-0.006)
    data.update(kw)
    m = fc.Metrics(symbol="T")
    m.rulebook, m.data = rulebook, data
    m.fin_ccy = "USD"
    return GATE.fn(m)


print("the waiver")
st, msg = gate()
check("MCD-like (buyback-driven, cash rich): WATCH", st == fc.WATCH, f"{st} {msg}")
check("the message says why", "waived" in msg and "buybacks" in msg and "7.9x" in msg, msg)

print("\ncontrols: each condition on its own")
check("AMC-like (shares +24%, coverage 0.8x, FCF never positive): FAIL",
      gate(cfo=410e6, fcf=168e6, fcf_positive_years=0, interest_coverage=0.8, share_change=0.24)[0] == fc.FAIL)
check("BYND-like (cash burn, shares +496%): FAIL",
      gate(cfo=-110e6, fcf=-120e6, fcf_positive_years=0, share_change=4.96)[0] == fc.FAIL)
check("free cash flow negative: FAIL", gate(fcf=-1e6)[0] == fc.FAIL)
check("operating cash flow negative: FAIL", gate(cfo=-1e6)[0] == fc.FAIL)
check("FCF positive in only 2 of 4 years: FAIL", gate(fcf_positive_years=2)[0] == fc.FAIL)
check("only 2 years of history: FAIL", gate(fcf_years_checked=2, fcf_positive_years=2)[0] == fc.FAIL)
check("coverage 2.9x (under 3x): FAIL", gate(interest_coverage=2.9)[0] == fc.FAIL)
check("coverage exactly 3.0x: WATCH", gate(interest_coverage=3.0)[0] == fc.WATCH)
check("coverage unknown (the Otis case): FAIL -- no evidence is not a waiver",
      gate(interest_coverage=None)[0] == fc.FAIL)
check("coverage inferred 999 (no interest, no net debt): WATCH", gate(interest_coverage=999.0)[0] == fc.WATCH)
check("shares flat (0.0%): FAIL -- must be shrinking", gate(share_change=0.0)[0] == fc.FAIL)
check("shares up 0.3%: FAIL", gate(share_change=0.003)[0] == fc.FAIL)
check("share count unknown: FAIL", gate(share_change=None)[0] == fc.FAIL)

print("\nscope: only operating companies")
for rb, expected in (("default", fc.WATCH), ("capital_intensive", fc.WATCH), ("pre_revenue", fc.WATCH),
                     ("financials", fc.FAIL), ("reit", fc.FAIL)):
    check(f"{rb:18s} with identical numbers -> {expected}", gate(rulebook=rb)[0] == expected)

print("\nnothing changes elsewhere")
check("positive equity: PASS", gate(equity=1e9)[0] == fc.PASS)
check("equity unknown: NA", gate(equity=None)[0] == fc.NA)

print("\nthe liquidity waiver follows")
m = fc.Metrics(symbol="T")
m.rulebook = "default"
m.data = dict(equity=-1.79e9, cfo=11.3e9, fcf=7.8e9, fcf_years_checked=4, fcf_positive_years=4,
              interest_coverage=7.9, share_change=-0.006, ccc=-1, dpo_growth=None)
check("negative CCC + waived negative equity: liquidity waiver applies", fc.ccc_waiver(m)[0] is True)
m.data.update(fcf=-1e6)
check("negative CCC + unwaived negative equity: no liquidity waiver", fc.ccc_waiver(m)[0] is False)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
