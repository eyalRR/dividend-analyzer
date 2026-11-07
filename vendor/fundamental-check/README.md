# fundamental-check

A deterministic pre-trade fundamental sanity check for a single US or Tel Aviv
traded stock. One argument, no flags, no LLM in the loop.

```bash
python fundamental_check.py AAPL
python fundamental_check.py ESLT.TA
python fundamental_check.py 1081124      # TASE security number
```

Prints a markdown report; writes the full detail to `reports/<SYMBOL>_<DATE>.json`.

**Exit codes:** `0` clean, `1` AVOID tripped, `2` unresolvable ticker or under 50%
check coverage.

## Standalone

This folder has **no dependency on the repository it currently sits in**. It imports
nothing from a parent directory, reads no shared config, assumes no folder layout, and
resolves every path from its own location. Copy the directory anywhere and it works:

```bash
pip install yfinance pandas
python fundamental_check.py MSFT
```

Reports are written beside the script, not into the working directory, so running it
from a scheduler or any other cwd behaves identically.

There is no cache: every run fetches fresh from Yahoo Finance, about 10 requests for a
US ticker and 11 for a Tel Aviv one (measured, not estimated). Running a long watchlist
back to back is what trips Yahoo's rate limit, so pace it.

## Files

| File | Purpose |
|---|---|
| `fundamental_check.py` | The whole program. |
| `rulebook.md` | Every threshold and the reasoning behind it. |
| `SKILL.md` | Claude Code skill definition. |
| `reports/` | JSON output, one per symbol per day: every check that ran, every check that was skipped and why (`skipped_checks`, so ran + skipped always equals the checks defined), the fetch time, and the liquidity-waiver reason. Older files in here predate these fields. |

## Input handling

- US or suffixed ticker (`MSFT`, `ESLT.TA`) is used as given.
- A bare symbol with no US listing is retried with `.TA`.
- An all-digit argument is treated as a TASE security number, converted to its Israeli
  ISIN (`IL` + 9-digit zero-padded number + Luhn check digit) and resolved through
  Yahoo's search endpoint, filtered to `quoteType == EQUITY` and `exchange == TLV`.
  Yahoo does not accept raw TASE numbers as symbols, so this step is required.
- **A number can fail even when its ticker works.** Yahoo's search does not index every
  security it serves: Camtek (`1095264`) and Nextgen Biomed (`1083930`) return nothing as
  numbers but run fine as `CAMT.TA` and `NXGN-M.TA`. The tool then says so and exits 2;
  pass the ticker instead.
- **A number can also resolve to a different company than expected.** Read the first line
  of the report, which names the company and the resolution chain.

The resolution chain is printed on the report's first line, so a wrong-company match is
visible rather than silent.

## A note on currency

TASE issuers quote in agorot (ILA) but report financials in whichever currency they
choose — Elbit and Teva both file in USD, Bank Hapoalim in ILS. Every valuation
multiple therefore mixes a quote-side numerator with a statement-side denominator
unless prevented, which inflates P/E by roughly 370x. The script reads quote currency
and statement currency separately, converts market cap into statement currency before
it meets any statement-derived denominator, and prints both currencies in the footer.

## Calibration

`tests/calibration.py` runs the tool on 38 companies of known health -- healthy, mixed and
distressed -- and checks each lands in its expected range. That file is the source of
truth: the companies, the ranges and the reason each one is there live in it, and
`tests/README.md` explains how to read a failure. Run it after changing any threshold.

No tier has ever inverted: no distressed company has passed, and no healthy one has
tripped a gate.

**Known data-source limit.** Some Tel Aviv small and micro-caps return no Yahoo
fundamentals: `MGIC.TA`, `ICCM.TA`, `AUGN.TA`, `BION.TA` and `KDMT.TA` returned empty
statements and zero price history. The script exits 2 cleanly on them. Whether each ticker
was the right one is not verified, and an earlier version of this list was wrong: `NSTS.TA`
was listed as having no data, but NextVision is `NXSN.TA` and it works (Quality 83); and
`AQUA.TA` was listed too, but the security number that came with it, `1170240`, resolves to
Veloryx (`VRYX.TA`), so that pairing was wrong. Check the ticker before concluding that
Yahoo lacks a company.
