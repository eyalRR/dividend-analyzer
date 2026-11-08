#!/usr/bin/env python3
"""
test_div_trap_waiver.py -- the dividend-trap gate's cash-backed waiver, case by case.

The gate reads GAAP net income, which a one-off charge can push negative at a company whose
cash flow covers the dividend many times over (Gilead: net income -$3.9B, free cash flow
+$13.8B, dividend $4.1B). The waiver turns that FAIL into a WATCH, but only when the evidence is
solid and the company is the kind this evidence is reliable for. Pure functions, no network:

    python tests/test_div_trap_waiver.py        (exit 0 = all passed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fundamental_check as fc  # noqa: E402

GATE = {c.cid: c for c in fc.build_checks()}["div_trap"]
failures = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{('  -- ' + detail) if (detail and not cond) else ''}")
    if not cond:
        failures.append(name)


def gate(rulebook="default", **kw):
    data = dict(div_yield=0.02, cash_payout=None, net_income=-3.9e9, dividends_paid=-4.1e9,
                fcf=13.8e9, fcf_years_checked=4, fcf_positive_years=4)
    data.update(kw)
    m = fc.Metrics(symbol="T")
    m.rulebook, m.data = rulebook, data
    return GATE.fn(m)


print("the waiver")
st, msg = gate()
check("GILD-like (net loss, FCF 3.4x the dividend, positive 4 of 4 years): WATCH", st == fc.WATCH, f"{st} {msg}")
check("the message says why it was waived and quotes the cover", "waived" in msg and "3.4x" in msg and "4 of 4" in msg, msg)

st, _ = gate(fcf=-301e6, dividends_paid=-1.6e9, net_income=-47e6)
check("APD-like (FCF negative against a $1.6B dividend): still FAIL -- the control", st == fc.FAIL, st)

st, _ = gate(fcf=4.0e9)
check("FCF just below the dividend (0.98x): FAIL -- the rule has a cliff at 1.0x", st == fc.FAIL, st)

st, _ = gate(fcf=4.1e9)
check("FCF exactly equal to the dividend: WATCH", st == fc.WATCH, st)

st, _ = gate(fcf_positive_years=2)
check("covered this year but positive in only 2 of 4 years (a windfall): FAIL", st == fc.FAIL, st)

st, _ = gate(fcf_years_checked=2, fcf_positive_years=2)
check("only 2 years of history: no evidence, so FAIL", st == fc.FAIL, st)

st, _ = gate(fcf=None)
check("free cash flow unknown: FAIL (no evidence is not a waiver)", st == fc.FAIL, st)

print("\nthe other branch of the gate (positive earnings, high yield, payout over 120%)")
st, _ = gate(net_income=100e6, div_yield=0.12, cash_payout=1.5, dividends_paid=-150e6, fcf=400e6)
check("high yield, payout 150%, but FCF covers it 2.7x: WATCH", st == fc.WATCH, st)
st, _ = gate(net_income=100e6, div_yield=0.12, cash_payout=1.5, dividends_paid=-150e6, fcf=50e6)
check("high yield, payout 150%, FCF does not cover it: FAIL", st == fc.FAIL, st)

print("\nscope: only operating companies")
for rb, expected in (("default", fc.WATCH), ("capital_intensive", fc.WATCH), ("pre_revenue", fc.WATCH),
                     ("financials", fc.FAIL), ("reit", fc.FAIL)):
    st, _ = gate(rulebook=rb)
    check(f"{rb:18s} with identical, fully covering numbers -> {expected}", st == expected, st)

print("\nnothing changes where the gate already passed")
st, _ = gate(net_income=500e6, div_yield=0.02, cash_payout=0.3, dividends_paid=-150e6)
check("healthy payer: PASS", st == fc.PASS, st)
st, _ = gate(dividends_paid=0)
check("no dividend paid: PASS", st == fc.PASS, st)
st, _ = gate(div_yield=None)
check("no yield on record: NA", st == fc.NA, st)

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print("all passed")
