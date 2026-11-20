# Calibration test

## What this is, for someone new

`fundamental_check.py` scores a company from 0 to 100 on how healthy its finances are,
and flags companies that should be avoided entirely. You run it before buying a stock.

A scoring system like this is only useful if it sorts companies correctly: Microsoft
should score high, a company heading for bankruptcy should score low. Nobody can prove
the rules are right by reading them. So the tool was tested on about 38 real companies
where the answer was already known:

- **Healthy** (Microsoft, Nvidia, Procter & Gamble): score high, never flagged.
- **Middling or unusual** (Apple, banks, utilities, Teva): score in the middle, and must
  not be flagged by mistake.
- **In real trouble** (AMC, Plug Power, Virgin Galactic): score badly and get flagged.

Running that list found real bugs, and they were fixed. For example, the tool believed
Duke Energy was about to run out of cash, and one company's financial data contained an
impossible number that made it look heavily indebted. In the end every company landed
in the right group.

## Why this test exists

Without this folder, that list of companies would exist only as a table in a README and a
throwaway script that was never saved. Suppose someone changes a threshold next month,
for instance "flag companies with debt above 5x earnings" to some other number. Nobody
would know whether that quietly broke the result for a company that used to score
correctly. They would have to remember to redo the whole check by hand, and they
probably would not.

This is a **regression test**, a tripwire. If a future change accidentally breaks
something that used to work, you find out immediately instead of months later, after
acting on a bad score.

The tool is meant to be a safety check before putting money into a stock, so its scores
are only as trustworthy as the tuning behind them. That tuning took real effort, and
without a saved test it can be broken without anyone noticing.

## Running it

```bash
python tests/calibration.py                 # all companies, about 4 minutes
python tests/calibration.py AAPL TEVA.TA    # only these
```

Exit code `0` means every expectation held. Exit code `1` means at least one company
drifted, and the output says which and why.

A second, network-free test covers the fail-closed behaviour (empty company record, retry,
-255 scores, error log, error JSON, and that the old rulebook guess is gone):

```bash
python tests/test_fail_closed.py            # instant: Yahoo is faked, nothing really waits 30s
```

If a calibration company shows "tool refused to score", that is the fail-closed path firing,
usually a Yahoo rate limit: rerun it, and check `fundamental_check_errors.log`.

It is self-contained like the tool itself: standard library only, imports nothing from the
surrounding repository, so the whole folder still works if copied elsewhere. It does need
the network, because it scores live data from Yahoo Finance.

## The one thing to understand before editing it

The data is live and moves every quarter, so expectations are **ranges**, not exact
numbers: "Quality above 70", "must be flagged". An exact number would fail for reasons
that mean nothing. Some ranges will still need widening over time as companies genuinely
change. That is normal.

When a company drifts, work out which of these it is before touching anything:

1. **The company changed.** Its business really did get better or worse. Update the range.
2. **The data changed.** Yahoo altered a value or has a gap. Investigate before trusting
   either the old or the new result. Yahoo has shipped corrupt figures before (see the
   Camtek case in `../rulebook.md`).
3. **A rule broke.** A threshold change altered a company that should not have moved.
   This is what the test exists to catch. Fix the rule, not the expectation.

The worst outcome is loosening an expectation to make a red result go green without
knowing which of the three it was.

## What counts as a real failure

- **Any healthy company getting flagged AVOID, or any distressed company passing.** This
  is a correctness bug in the safety gate, not a tuning issue. A tier flip like this
  should block the change.
- **A few points outside a range.** A calibration signal. Usually a weight to tune.

## Known gaps

- Five Tel Aviv micro-caps (`MGIC.TA`, `ICCM.TA`, `AUGN.TA`, `BION.TA`, `KDMT.TA`) returned
  no data from Yahoo, so they are not in this test. It is not verified that those were the
  right tickers: `NSTS.TA` and `AQUA.TA` were once on this list and turned out to be wrong
  (NextVision is `NXSN.TA`, which works; number `1170240` is Veloryx, `VRYX.TA`). Neither
  `NXSN.TA` nor `VRYX.TA` is in the test yet.
- `PSEC` is a business development company scored on the bank rulebook. Its AVOID is
  correct, but its Quality score is not meaningful. Its range is deliberately wide, and it
  should be tightened once BDCs get their own rulebook.
