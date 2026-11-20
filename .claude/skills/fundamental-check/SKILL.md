---
name: fundamental-check
description: Run a deterministic fundamental sanity check on a single US or Tel Aviv traded stock before opening a position -- profitability, cash generation, leverage, liquidity, dilution and earnings quality -- producing green flags, red flags, a Quality score, a Risk score and a hard AVOID banner when a critical gate trips. Use when asked whether a company's fundamentals are sound, whether it has cash-flow or debt problems, whether a stock is safe to buy on fundamentals, or to vet a ticker that a price-based scan just flagged. Accepts a US ticker (AAPL), a TASE ticker (ESLT.TA), or a TASE security number (1081124). Not a valuation or price-target tool and not a screener -- it judges one company at a time.
---

# Fundamental Check

A pre-trade sanity gate. The strategy pipeline in this repo is entirely price-driven, so a scan can fire an entry on a company that is burning cash, drowning in debt or diluting every quarter. This skill is the check that catches that.

Judges one ticker at a time; for the whole market at once, [`screener/good_fundamental_score/`](../../../screener/good_fundamental_score/) runs this same check over a Finviz-filtered universe and produces one combined report.

Runs with no LLM in the loop: one deterministic Python script, one argument, no flags.

## Usage

```bash
python .claude/skills/fundamental-check/fundamental_check.py AAPL
```

```bash
python .claude/skills/fundamental-check/fundamental_check.py ESLT.TA
```

```bash
python .claude/skills/fundamental-check/fundamental_check.py 1081124
```

The argument is a US ticker, a TASE ticker, or a TASE security number (the number in a Bizportal or Globes URL). Nothing else is accepted -- there are no options.

**Exit codes:** `0` clean, `1` AVOID tripped, `2` unresolvable ticker, insufficient data, or required data missing from Yahoo. On exit `2` for missing data the tool has already waited 30 seconds and retried twice; it then reports `Quality -255 / Risk -255` (sentinels, not scores), `avoid: null` and `status: "error"` in an `*.error.json`, and appends the reason to `fundamental_check_errors.log`. A successful report has `status: "ok"`.

A markdown report prints to stdout. A full JSON -- every metric, threshold, verdict, resolved statement alias and diagnostics -- is written to `reports/<SYMBOL>_<DATE>.json` beside the script, and its path is the last line of output. It lists every check that ran and, separately under `skipped_checks`, every check the code defines that did not, each with the reason (the rulebook it does not apply to, or the AVOID short-circuit). It also records when the data was fetched (`fetched_at`, with a UTC offset) and the reason behind the liquidity waiver (`liquidity_waiver_note`).

## What it produces

- **Quality 0-100** -- profitability, cash generation, growth, capital allocation.
- **Risk 0-100**, higher is more dangerous -- leverage, liquidity, earnings quality.
- **AVOID banner** when any critical gate trips (negative equity (unless cash flow, coverage and a shrinking share count show it comes from buybacks, not losses), equity eroding toward zero, interest coverage below 1.5x (unless operating income and operating cash flow each cover interest at least 1.5x, which waives it to a WATCH), net debt beyond the leverage ceiling with no coverage to service it, time to live under 12 months, negative operating cash flow, dividend paid out of losses or an unfunded high-yield payout (unless free cash flow covers the dividend and was positive in 3 of the last 4 years, for operating companies), dilution over 20% YoY, or failing tradability). Altman Z-score and Beneish M-score are scored leverage/earnings-quality checks, not AVOID-tier gates on their own.
- **Recent news** (`news.py`, same no-LLM/deterministic design, Yahoo's free keyless search endpoint) -- the 5 most recent headlines regardless of age (no cutoff; each carries its own `[date / age]` marker so a stale one is visible rather than hidden), with a regex classifier naming the likely driver (earnings, capital raise/dilution, clinical/regulatory, analyst action, legal) and, when a headline states a signed M&A deal price, flagging **DEAL-PINNED** if the stock is already trading within 4% of it -- the one case where upside is a known number rather than a direction to read fundamentals or momentum into. Informational only, not scored into Quality/Risk: a quiet name moves neither number. The deal-price check only runs for USD-quoted names (a TASE stock's ILS price has no USD deal figure to compare against). Yahoo's search is occasionally loose for widely-covered names -- a sector peer's headline can surface as "the" news item for the ticker you asked about; read the headline, not just the tag.
- **Next earnings date** (`yfinance`'s own `Ticker.calendar`) -- the expected report date (or estimate window) and a day countdown, right after the news section. Also informational, not scored. If yfinance has not yet rolled a just-passed date forward, it renders as "overdue" rather than a negative number.

The two scores are deliberately separate: a high-growth company with a broken balance sheet should not average out to "fine".

## Reading the output

Every flag carries the observed number and the threshold it was judged against. A `WATCH` line is a metric that failed a raw threshold but was waived for a stated reason -- read the reason, it is the interesting part. `NOT APPLICABLE` means the check does not apply to this company's rulebook, not that the company failed it.

When the Sanity Check already trips AVOID, the Deep Dive is skipped and no forensic requests are issued. The report says so, and the Risk score is then based on Sanity Check inputs only.

See [rulebook.md](rulebook.md) for every threshold and why it is set where it is.

## Self-contained

This folder imports nothing from this repo and knows nothing about its conventions. Copy the whole folder (`fundamental_check.py` and its sibling `news.py`) anywhere with `yfinance` and `pandas` installed and it works unchanged -- `news.py` only needs the standard library.
