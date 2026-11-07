# Rulebook

Every threshold the script applies, and why it sits where it does. Thresholds are
deliberately conservative where a miss is expensive and loose where a strict bar
would misclassify a healthy business.

## Critical gates (any one trips AVOID)

| Gate | Trip condition | Why |
|---|---|---|
| Negative shareholder equity | equity < 0 | Liabilities exceed assets. |
| Equity erosion | 3y equity CAGR < -15% | Book value collapsing toward zero, caught before it crosses. |
| Interest coverage floor | EBIT / interest < 1.5x | Earnings barely cover the debt service. |
| Net debt / EBITDA ceiling | > 5.0x (6.0x capital-intensive), see banding below | Leverage past the point of refinancing flexibility. |
| Time to live | **negative CFO** with < 12 months of cash at current burn | Financing risk inside a normal holding period, assuming no new financing. |
| Operating cash flow reversal | TTM CFO < 0 | The business consumed cash over the last year. |
| Dilution | share count +20% YoY | Going-concern-level issuance. |
| Dividend trap | yield > 8% **and** cash payout > 120% | High yield masking a collapsing price and an unfunded payout. |
| Tradability | price < $2, market cap < $100M, or 30d median dollar volume < $1M | Below this, execution and manipulation risk dominate fundamentals. |

Tradability figures are FX-converted to USD, so the gates mean the same thing on
TASE as on NASDAQ.

The dilution row above was documented from this skill's first version but had no matching gate in code until this session -- 20%+ issuance only cost Quality points and could never trip AVOID on its own. It is now a real critical check (`dilution_crit`), companion to the scored `dilution` check the same way `nd_ebitda_crit` companions the scored leverage check: same underlying number, a harder line, zero scoring weight so it does not double-count.

**Dividend trap, corrected.** The gate used to return PASS as soon as yield was <= 8%, without ever checking whether the payment was funded -- a 7% yield paid entirely out of losses cleared it untouched. Loss-funded is now checked first, at any yield, before the high-yield-plus-high-payout condition is even considered.

### Time to live

Months of cash left at the current TTM burn rate, assuming **no new financing** --
no dilution, no new debt. Three states, not two:

| Months | Result |
|---|---|
| < 12 | FAIL, critical -- trips AVOID |
| 12-18 | WATCH -- a raise is likely within 1-2 years, not yet going-concern territory |
| >= 18 | PASS |
| Not burning cash on a CFO basis, or no cash data | `NA` |

The critical floor is unchanged from this check's earlier two-state form (previously
"cash runway," reported in quarters) specifically so it does not silently loosen AVOID
behaviour already calibrated against the regression set. 12-18 months is new: an early
warning for names headed toward a raise that are not there yet.

**Why the burn rate keys on CFO, not FCF.** A regulated utility permanently spends more
on capex than it generates in operating cash flow, funded by debt issuance. That is a
financing structure, not a runway clock. Gating the burn rate on negative FCF instead of
negative CFO reported Duke Energy at "0.3 quarters," and would have reported it at 1.7
months and Enlight Renewable at 4.1 months under a months-based FCF calculation --
tripping AVOID on two stable capital-intensive operators with strongly positive
operating cash flow. The check fires only when **operating** cash flow is negative --
when the business itself consumes cash -- and uses the trailing twelve months, not the
latest single quarter, so one working-capital swing or one-off capex spend cannot swing
a going-concern estimate on its own.

**Why a self-funding company is `NA` here, not `PASS`.** The "operating cash flow
reversal" check already scores CFO > 0 as PASS on its own. Also scoring it here would
double-count the same signal in the liquidity pillar. Burning cash (`BYND`, `OPEN`) can
still show a healthy 18+ month runway and PASS this check while AVOIDing for unrelated
reasons -- the two checks answer different questions and are not meant to agree.

**Skipped for the financials rulebook.** A bank's cash position is its raw material,
not a burn-rate clock, and neither CFO nor cash on a bank's balance sheet follows the
corporate cash-generation-vs-consumption pattern this check is built to read.

### Net debt / EBITDA banding

Leverage is fatal when it cannot be serviced, not at a round number, so the ceiling is
banded rather than binary:

| Condition | Result |
|---|---|
| <= ceiling | PASS |
| above ceiling, coverage >= 1.5x, <= 1.5x ceiling | WATCH |
| above 1.5x ceiling, coverage >= 8x | WATCH -- exceptional coverage overrides |
| otherwise | FAIL (critical) |

Teva at 5.11x with 1.79x coverage is a levered turnaround, not a failure. G City at
13.4x with 1.66x coverage has no margin for a rate reset and fails. Camtek at 7.8x with
26x coverage carries low-coupon converts and passes.

### Negative EBITDA is a state, not a ratio

Net debt of +$50M over EBITDA of -$10M is -5.0, and every leverage test here is an
upper bound, so an unguarded ratio lets a distressed company read as ultra-low-leverage
and pass. Negative EBITDA is therefore resolved before any comparison:

| State | Result |
|---|---|
| EBITDA <= 0 **and** net debt > 0 | FAIL (critical) -- no earnings to service the debt |
| EBITDA <= 0 **and** net cash | `NA` -- a runway question, owned by the cash-runway gate |
| EBITDA > 0 | the banded logic above |

The net-cash branch matters: a pre-revenue biotech with negative EBITDA and no debt has
a runway problem, not a solvency one, and a leverage FAIL there would double-count
against the pre-revenue rulebook. `EVGN.TA` exercises exactly that path -- negative
EBITDA, net cash, NA on leverage, and it still AVOIDs on runway.

### EBITDA sanity

EBITDA = EBIT + D&A, and D&A is never negative, so a reported EBITDA below EBIT is
corrupt. Camtek's Q4-2025 EBITDA arrives as -42.5M against +31.7M operating income in
the same quarter, which dragged TTM EBITDA to 43.8M against a true ~118M and inflated
its leverage ratio to 7.8x. When the invariant breaks, EBITDA is rebuilt as EBIT + D&A
and the substitution is recorded in the JSON diagnostics.

## Quality pillars (100 points)

**Profitability (30)** -- operating margin >= 10%, ROIC >= 12%, ROA >= 5%, net
margin >= 5% at low weight.

Operating margin is raised from the common 8% screen because 8% is weak for a
business with real pricing power. Net margin is deliberately low-weighted: efficient
operators run it near zero on purpose, funnelling gross profit into capex, marketing
and R&D. Operating margin and FCF margin carry the verdict instead.

**Gross margin is scored as a trend, not a level.** A flat floor would fail Costco (12.8% gross margin by design, a thin-margin high-volume retailer that is otherwise one of the highest-quality names this tool scores) exactly the way an absolute net-margin floor would have. Margin *compression* year over year is the actual pricing-power signal -- it means the same thing whether the business runs on 13% or 93% gross margin -- so a fall of more than 2pp fails and anything else passes.

**Capex intensity is scored against growth, not on its own.** Capex/revenue > 15%
fails only when it is paired with revenue growth under 5% -- the "maintenance capex"
trap (an airline or legacy auto spending heavily just to stand still). A flat 15%
ceiling would fail Alphabet, which is spending ~30% of revenue on AI infrastructure
at 24% revenue growth -- growth capex, not maintenance, and one of the strongest
names this tool scores. Skipped for `capital_intensive` (already carved out and
expected to run heavy capex structurally), `financials` (capex is not a meaningful
concept for a bank) and `pre_revenue` (revenue near zero makes the ratio noise).

ROIC is preferred over ROE, which leverage inflates. When ROE exceeds ROIC by more
than 2x the report says so explicitly.

**Cash (30)** -- FCF > 0, FCF margin >= 8%, CFO/NetIncome >= 0.8, FCF positive in
>= 3 of the last 4 years, and SBC-adjusted FCF (CFO - capex - stock comp) > 0.

That last one matters: stock comp is added back to operating cash flow, so a company
can report positive FCF that exists only because dilution is not counted as a cost.

**Growth (25)** -- revenue >= 5% and operating income > 0, each measured as the latest
quarter against the same quarter a year earlier; CFO growth > 0 and a positive 3y revenue
CAGR on fiscal years.

The quarter-vs-year-ago basis is deliberate. Fiscal-year growth can be a year stale: Tesla's
fiscal-year revenue fell 2.9% while its latest quarter is up 25.5%. Comparing to the same
quarter last year removes seasonality. If the year-ago quarter is missing, or is not about a
year before the latest one (a skipped quarter, a semi-annual reporter), the check reports
not-available. It does not fall back to another period.

Operating income growth off a zero or negative base is reported as a state, not a
percentage:

| Operating income | Result | Scoring |
|---|---|---|
| Grew | PASS | full points |
| Loss to profit (**turnaround**) | PASS | full points |
| Declined, or profit to loss | FAIL | zero, stays in the pool |
| Loss to loss (**still unprofitable**) | FAIL | zero, stays in the pool |
| No year-ago quarter | NA | leaves the pool |

Only missing data leaves the scoring pool. Bad data is a failure. Current profitability is
scored separately (operating margin, ROIC), so a turnaround earns the momentum points but
not a pass on the quality of the profit.

A **worst-year warning**, not scored, appears when fiscal-year revenue fell in any of the
last three years. A dip that later recovered is invisible to an endpoint CAGR.

Known trade-off: one quarter is noisy. A single good quarter can lift a distressed company's
Quality score (IEP and AMC each rose by ~13-15 points on one quarter) without touching its
AVOID flag or Risk score.

Diluted EPS growth is deliberately **not** scored. It is trivially manipulated by
buybacks and distorted by one-time tax items and asset sales. Revenue plus CFO is a
cleaner read, and dilution is already scored separately.

**Capital allocation (15)** -- share count flat or shrinking, dividends covered by FCF, and share count reconciliation: the live quote's share count against the most recent statement's diluted count. A gap above 10% means either real recent dilution/buybacks or a stale quote, and every multiple in the report is built on one of those two counts, so it is worth a scored check rather than only a footnote.

**Dividend trend is scored leniently: not-a-cut, not growth-rate.** PASS on a flat or
growing 3-year dividend CAGR, FAIL only on an actual cut. Apple's 3-year dividend CAGR
is ~1.3% and Procter & Gamble's is ~4.4% -- both deliberately prioritise buybacks over
dividend growth, a capital-allocation *preference*, not a flaw, and a growth-rate bar
(e.g. >5%) would fail both of them. `MTRX.TA` shows a real -1.8% cut here, a genuine
distress signal the earlier dividend checks (which only looked at current coverage)
could not see.

**Shareholder yield -- (dividends + buybacks) / market cap -- is reported as CONTEXT
only, never scored.** Dividing by market cap makes it a valuation-sensitive number:
Apple and Microsoft, two of the highest-quality names this tool scores, show 2.0% and
1.3% respectively, purely because their market caps are enormous relative to even
very large absolute buybacks. A low or zero shareholder yield is also the *correct*
behaviour for a high-ROIC reinvestor -- that capital allocation choice is already
rewarded by the ROIC check -- so scoring this against a threshold would penalise
exactly the reinvestment-over-payout decision the rest of this rulebook treats as
good (see the net-margin note above). This tool stays a quality/safety check, not a
value screen, and this metric sits on the value side of that line.

## Risk pillars (100 points, higher is worse)

**Leverage (40)** -- Debt/Equity < 1.5, Net debt/EBITDA < 3.0 (4.5x capital-intensive),
interest coverage > 3x, positive tangible book value.

D/E is loosened from the common 1.0 because a strict bar eliminates capital-intensive
businesses that use debt safely. Negative tangible book value is a red flag but not on
its own critical -- acquisitive and consumer-brand companies commonly carry it. It
escalates only alongside high leverage.

**Leases are not added separately.** A lease is a long-term rent commitment that behaves
like debt, so a lease-adjusted leverage check was once planned. It would have counted them
twice: Yahoo's reported `Total Debt`, which every leverage check here uses, already
includes lease obligations. Measured on Delta, Starbucks, Walmart, Costco and McDonald's,
the gap between `Total Debt` and loans-plus-current-debt equals the reported lease
obligations to the dollar. Not verified for Tel Aviv issuers, which report under IFRS.

**Altman Z'' is a scored leverage check, not only a printed composite.** Distress fails, grey is a WATCH, safe passes. It is dropped for financials and pre-revenue for the same reason it is dropped from the composites section below.

**A WATCH earns half credit on the risk side, not zero.** A waived check (Teva's coverage override, Camtek's exceptional interest coverage, an Altman grey zone) means a real threshold was crossed and a mitigating factor covers it -- it is not the same as a clean PASS. Crediting it identically to PASS was a real scoring bug: a WATCH used to lower the Risk score exactly as much as a clean pass, discarding the very risk information the waiver mechanism exists to preserve. Half credit keeps the benefit of the mitigation while still counting the exposure.

**Liquidity (30)** -- current ratio > 1.2, quick ratio > 1.0, positive CFO, time to live >= 18 months (see below for the 12-18 month WATCH band).

Both ratio tests are `OR` gates, not hard thresholds:

- quick ratio > 1.0 **OR** CFO / current liabilities > 0.5
- current ratio > 1.2 **OR** interest coverage > 15x

This exists because static liquidity ratios are a manufacturing-era instrument.
Apple runs structurally negative working capital on purpose -- it collects instantly
and pays suppliers on 90+ day terms -- and posts a current ratio near 1.0 with a quick
ratio near 0.85 while carrying no refinancing risk at all. A rubric that scores that
as danger is broken.

The whole pillar is waived when the cash conversion cycle is <= 0, **but only when the
cash engine is actually running**: CFO must be positive and DPO must not be expanding
more than 30% YoY. A distressed retailer also shows a negative CCC, for the opposite
reason -- it is stretching payables it cannot afford to settle. In that case the script
reports it as a red flag rather than a waiver.

**Earnings quality (30)** -- accruals <= 10% of assets, dividend sustainability, dividend funding, goodwill <= 40% of assets, stock comp <= 30% of CFO, receivables and inventory not outgrowing revenue by more than 15pp, cash vs current debt, and the Beneish M-score in the deep dive.

**Dividend funding** is separate from the `div_trap` critical gate on purpose. That gate fires on a loss-funded dividend at any yield, or a high yield with a high payout -- but a moderate payout above 100% of earnings with positive earnings is routine for REITs (Realty Income runs ~236% of net income, because depreciation is not a cash cost) and shouldn't be a critical failure. Dividend funding scores that case without gating on it: FAIL when a dividend is paid out of losses (mirrors the critical gate, for the deep-dive earnings-quality pillar), FAIL when payout exceeds 100% of earnings outside the REIT rulebook, PASS otherwise -- and REITs are explicitly judged on FFO, not this check.

## Composite scores

- **Piotroski F-Score** -- nine yes/no year-over-year tests of financial health, printed
  as an at-a-glance summary (`9/9` for Apple) and stored in the JSON. It is **not scored**:
  it has no pass bar and does not move Quality or Risk. Nearly every one of its nine tests
  is already a scored check in its own right (profit, cash flow, cash conversion, leverage,
  liquidity, dilution, gross margin trend), so scoring the total as well would count the
  same signals twice and force a re-calibration. An earlier version of this rulebook said
  "pass at >= 6"; no code ever applied that bar. For banks the tests that do not apply are
  dropped and named, so the score reads `n/k` (Bank Hapoalim: `5/6`), never a silently
  deflated `n/9`.
- **Altman Z''** (four-variable, non-manufacturer form) -- distress below 1.8, safe
  above 3.0. Dropped entirely for financials and for pre-revenue companies, where
  Retained Earnings/TA and Sales/TA make distress mathematically unavoidable.
- **Beneish M-Score** -- manipulation flag above -1.78. All eight published variables are computed (Asset Quality, SG&A and Depreciation indices were hardcoded to a neutral 1.0 in an earlier version; when an input is still genuinely missing today it falls back the same way, but the fallback is now recorded in the diagnostics and the verdict says how many of the eight defaulted, rather than silently presenting a full-input score). Also dropped for pre-revenue companies, where the Sales Growth and Gross Margin indices divide by near-zero revenue and produce a false flag on a company with nothing to manipulate.

## Sector rulebooks

Routed by sector label, with a statement-based fallback when the label is missing
(net interest income present -> financials; PPE > 60% of assets -> capital-intensive).
The report always names the rulebook and how it was chosen.

| Rulebook | Changes |
|---|---|
| **financials** | Skips 28 checks across four groups, listed here because "financials" is the one rulebook that overrides most of the default set rather than adding to it: **(1) corporate leverage/liquidity concepts that don't map to a bank's balance sheet** -- D/E, net debt/EBITDA (scored and critical), interest coverage (scored and critical), current and quick ratio, tangible book value, cash vs. current debt, time to live (a bank's cash position is its inventory, not a burn-rate clock); **(2) cash-flow-statement signals driven by deposit and loan flows, not earnings quality** -- FCF positive, FCF margin, FCF consistency, SBC-adjusted FCF, CFO/NetIncome, dividends-vs-FCF (Bank Hapoalim and Bank Leumi landing 20 points apart on CFO/NetIncome was the tell); **(3) margin/return concepts that don't map to a bank's income statement structure** -- operating margin, net margin, ROIC, gross margin trend, operating-income growth (revenue growth still scores); **(4) two forensic checks specific to a corporate balance sheet** -- goodwill/total-assets (a bank's loan book dwarfs any acquired goodwill by construction, so the ratio would trivially pass regardless of real M&A risk), receivables and inventory divergence (a bank's "receivables" are its loan book, so growth there is lending, not channel stuffing). Capex intensity is also skipped (capex is not a meaningful concept for a bank) and dividend funding is skipped because it scores the same `cash_payout` ratio `fin_div_cover` already scores at a stricter bar -- keeping both would double-count one signal in the same pillar. Substitutes equity/assets >= 8%, ROA >= 1%, ROE >= 10%, dividends/net income <= 80%. The critical dividend-trap gate (loss-funded, or high-yield-plus-high-payout) still applies -- it is not in this skip list. |
| **capital_intensive** (utilities, energy) | Net debt/EBITDA to 4.5x (critical 6.0x). These run structurally levered against predictable long-duration cash flows. |
| **reit** | FFO-style treatment, payout against FFO, net debt against assets. |
| **pre_revenue** | Margin and multiple checks become N/A; runway, burn and dilution dominate. Altman and Beneish dropped. |
| **default** | Everything above. |

## Data handling

- **Currency.** Quote currency and statement currency are read separately and never
  assumed equal. TASE issuers commonly quote in agorot (ILA) while reporting in USD --
  Elbit and Teva both do. Mixing them inflates every multiple by roughly 370x, so
  market cap is converted into statement currency before meeting any statement-derived
  denominator, and ratio operands are currency-asserted.
- **Aliases.** Statement line items shift between periods and restatements, so every
  item is looked up through an alias list. The alias that resolved is recorded in the
  JSON.
- **TTM.** Sum of the last 4 quarters where available; otherwise the latest annual
  figure, labelled `FY` rather than `TTM` so a fallback is never mistaken for a
  trailing figure. Some TASE mid-caps report semi-annually, which makes this necessary.
- **Coverage.** N/A checks drop out of both numerator and denominator. Below 50%
  coverage the script refuses to print a score and exits 2 -- a score built on thin
  data is worse than no score.
- **No cache.** Every run fetches fresh, about 10 Yahoo requests (11 for a Tel Aviv name,
  which also needs a currency rate). An earlier version carried a "market-close aware"
  cache, but it only stored a timestamp stub and never reused any data, so its
  "cache: HIT" footer was a label on a fresh fetch. It was removed, along with the
  exchange-calendar logic that existed only to decide that label. `fast_info` and the
  quarterly balance sheet were also dropped: nothing read the balance sheet, and
  `fast_info`'s share count matched `info`'s to 0.00% on 12 US and Tel Aviv tickers
  while costing four requests.
