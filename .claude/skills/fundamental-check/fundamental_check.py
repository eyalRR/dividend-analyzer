#!/usr/bin/env python3
"""
fundamental_check.py -- pre-trade fundamental sanity check for a US or Tel Aviv stock.

One argument: a ticker (AAPL, ESLT.TA) or a TASE security number (1081124).
No flags. Prints a markdown report and writes a JSON beside this script.

Exit codes: 0 = clean, 1 = AVOID tripped, 2 = unresolvable / insufficient data.

Self-contained: imports nothing from the surrounding repo.
Requires: yfinance and pandas.
"""

import json
import math
import os
import random
import sys
import time
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

import news

# --------------------------------------------------------------------------
# Paths -- always absolute, so a scheduler invoking us from any cwd behaves
# identically to a shell run from the repo root.
# --------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPORTS_DIR = SCRIPT_DIR / "reports"
ERROR_LOG = SCRIPT_DIR / "fundamental_check_errors.log"

TLV_TZ = ZoneInfo("Asia/Jerusalem")

# Fail closed. If a section the score cannot be trusted without comes back empty -- almost
# always a Yahoo rate limit, because yfinance often returns an empty table instead of raising --
# wait and retry, then refuse to score. A missing company record used to make the tool guess a
# rulebook from the income statement; that sent AAP and BXP (both AVOID) to the bank rulebook,
# which skips 30 of 46 checks, and they came back not-AVOID with Risk 0.
RETRY_WAIT_SECONDS = 30
MAX_RETRIES = 2
SENTINEL_SCORE = -255        # printed/stored for both scores when nothing could be scored

try:
    yf.config.network.retries = 3
except Exception:
    try:
        yf.set_config(retries=3)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Diagnostics -- always collected, surfaced in the JSON rather than the report.
# --------------------------------------------------------------------------
DIAG = {"aliases": {}, "retries": [], "notes": [], "fx": {}, "fetch_calls": 0}


def note(msg):
    DIAG["notes"].append(msg)


# --------------------------------------------------------------------------
# Optional pre-fetched info/history injection -- off by default (no env vars
# set, nothing changes). Set by a caller that already has fresh `info`/
# `history` for this exact symbol (e.g. dividend_analyzer's pipeline, which
# fetches both through its own SQLite-cached DataFetcher) to skip this
# script's own `tk.info` / `tk.history()` calls -- 2 of its ~10 yfinance
# requests per symbol. Every other fetch (statements, cashflow, calendar)
# is unaffected; this script still gets to decide freshness for those.
#
# Checked once, before fetch_core()'s retry loop -- never inside it. A
# retry builds a fresh yf.Ticker per round specifically because a reused one
# can hand back the empty answer it already cached; injecting prefetched
# data into that loop would defeat the same purpose, so a bad prefetch (or
# none) is discarded for good and falls through to fetch_core's own normal
# fresh-Ticker fetch/retry path.
# --------------------------------------------------------------------------
def load_prefetched_info():
    path = os.environ.get("FUNDCHECK_PREFETCH_INFO")
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        note("info: served from caller's pre-fetched data (FUNDCHECK_PREFETCH_INFO)")
        return data
    except Exception as e:
        note(f"FUNDCHECK_PREFETCH_INFO unreadable ({type(e).__name__}); fetching info normally")
        return None


def load_prefetched_history():
    path = os.environ.get("FUNDCHECK_PREFETCH_HISTORY")
    if not path:
        return None
    try:
        hist = pd.read_pickle(path)
        note("history: served from caller's pre-fetched data (FUNDCHECK_PREFETCH_HISTORY)")
        return hist
    except Exception as e:
        note(f"FUNDCHECK_PREFETCH_HISTORY unreadable ({type(e).__name__}); fetching history normally")
        return None


# --------------------------------------------------------------------------
# Network: backoff around yfinance, which rate-limits readily.
# --------------------------------------------------------------------------
def fetch(label, fn, default=None):
    """Call fn() with exponential backoff. Never raises; returns default."""
    delay = 1.0
    for attempt in range(1, 4):
        try:
            DIAG["fetch_calls"] += 1
            return fn()
        except Exception as e:
            name = type(e).__name__
            DIAG["retries"].append(f"{label}: attempt {attempt}/3 after {name}")
            if attempt == 3:
                note(f"{label} unavailable after 3 attempts ({name})")
                return default
            time.sleep(delay + random.random() * 0.5)
            delay *= 4
    return default


# --------------------------------------------------------------------------
# Report file naming -- the exchange is part of the name, so TEVA (US) and
# TEVA.TA (Tel Aviv), which are different securities, never collide.
# --------------------------------------------------------------------------
def file_key(symbol):
    return symbol.replace(".TA", "-TA").replace(".", "-") if symbol.endswith(".TA") \
        else symbol.replace(".", "-") + "-US"


# --------------------------------------------------------------------------
# FX -- fetched once per process, shared across every TASE name in the run.
# --------------------------------------------------------------------------
_FX = {}


def fx_rate(base, quote):
    """Units of `quote` per one `base`."""
    if base == quote:
        return 1.0
    key = f"{base}{quote}"
    if key in _FX:
        return _FX[key]
    pair = f"{base}{quote}=X" if base != "USD" else f"{quote}=X"
    hist = fetch(f"fx {pair}", lambda: yf.Ticker(pair).history(period="5d"))
    rate = None
    if hist is not None and not hist.empty:
        rate = float(hist["Close"].iloc[-1])
        if math.isnan(rate):
            # Same still-forming-bar quirk as the price fetch below: a NaN Close would
            # otherwise slip past every "is None" fallback check and get cached as NaN.
            rate = None
    if rate is None and base == "ILS" and quote == "USD":
        inv = fx_rate("USD", "ILS")
        rate = 1.0 / inv if inv else None
    if rate is None:
        note(f"FX {base}->{quote} unavailable")
        return None
    _FX[key] = rate
    DIAG["fx"][key] = rate
    return rate


def to_usd(value, currency):
    if value is None or currency is None:
        return None
    if currency == "USD":
        return value
    if currency == "ILA":
        value, currency = value / 100.0, "ILS"
    r = fx_rate(currency, "USD")
    return value * r if r else None


# --------------------------------------------------------------------------
# Ticker resolution, including TASE security number -> ISIN -> symbol.
# --------------------------------------------------------------------------
def _isin_check_digit(body):
    """The ISIN check digit: letters expand to two digits (A=10 ... Z=35), then Luhn.

    The expansion happens BEFORE the Luhn pass, so "IL" becomes "1821" and shifts the
    parity of every digit after it -- running Luhn over the letters as single symbols
    gives a different, wrong digit.
    """
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in body.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:  # doubling starts at the rightmost digit, the check digit's own slot
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def tase_number_to_isin(security_number):
    """A TASE security number as its Israeli ISIN: 1081124 -> IL0010811243.

    Yahoo does not accept a raw TASE number as a symbol (1081124.TA returns nothing), but
    its search endpoint resolves the ISIN. Israeli ISINs are "IL" + the number zero-padded
    to 9 digits + the check digit. Copied from the fetch-price-data skill so this tool
    stays self-contained; the two were compared across 100,000 numbers and agree.
    """
    body = "IL" + str(int(security_number)).zfill(9)
    return body + _isin_check_digit(body)


def yahoo_search(query):
    try:
        from curl_cffi import requests as crequests
        sess = crequests.Session(impersonate="chrome")
        r = sess.get("https://query2.finance.yahoo.com/v1/finance/search",
                     params={"q": query, "quotesCount": 10}, timeout=20)
        return r.json().get("quotes", [])
    except Exception as e:
        note(f"search failed for {query}: {type(e).__name__}")
        return []


# resolve()'s existence probe below fetches income_stmt to confirm a symbol has
# data; fetch_core() can reuse it instead of fetching the same statement again.
_PROBE_CACHE = {}


def has_data(symbol):
    t = yf.Ticker(symbol)
    fin = fetch(f"probe {symbol}", lambda: t.income_stmt)
    if fin is not None and not fin.empty:
        _PROBE_CACHE[symbol] = fin
    return fin is not None and not fin.empty


def resolve(user_input):
    """Return (symbol, resolution_chain) or (None, chain) on failure."""
    raw = user_input.strip().upper()
    chain = [raw]

    if raw.isdigit():
        isin = tase_number_to_isin(raw)
        chain.append(isin)
        quotes = yahoo_search(isin)
        good = [q for q in quotes
                if q.get("quoteType") == "EQUITY" and q.get("exchange") == "TLV"]
        if not good:
            rejected = [f"{q.get('symbol')}({q.get('quoteType')}/{q.get('exchange')})"
                        for q in quotes]
            note("search rejected: " + (", ".join(rejected) or "no candidates"))
            chain.append("NO TLV EQUITY MATCH")
            return None, chain
        chain.append(good[0]["symbol"])
        return good[0]["symbol"], chain

    if has_data(raw):
        return raw, chain
    if not raw.endswith(".TA"):
        alt = raw + ".TA"
        chain.append(alt)
        if has_data(alt):
            return alt, chain
    return None, chain


# --------------------------------------------------------------------------
# Statement extraction with alias fallbacks.
# --------------------------------------------------------------------------
ALIAS = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "cost_of_revenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported",
                         "EBIT", "Operating Revenue Less Operating Expenses"],
    "ebit": ["EBIT", "Operating Income", "Total Operating Income As Reported"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": ["Net Income", "Net Income Common Stockholders",
                   "Net Income Including Noncontrolling Interests"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "net_interest_income": ["Net Interest Income"],
    "rnd": ["Research And Development"],
    "sga": ["Selling General And Administration"],
    "pretax": ["Pretax Income"],
    "tax": ["Tax Provision"],
    "diluted_shares": ["Diluted Average Shares", "Basic Average Shares"],
    "diluted_eps": ["Diluted EPS", "Basic EPS"],
    "dep_amort": ["Depreciation And Amortization", "Reconciled Depreciation",
                  "Depreciation Amortization Depletion"],
    # balance sheet
    "total_assets": ["Total Assets"],
    "total_liabilities": ["Total Liabilities Net Minority Interest"],
    "equity": ["Stockholders Equity", "Common Stock Equity",
               "Total Equity Gross Minority Interest"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "cash": ["Cash Cash Equivalents And Short Term Investments",
             "Cash And Cash Equivalents",
             "Cash Cash Equivalents And Federal Funds Sold"],
    "inventory": ["Inventory"],
    "receivables": ["Accounts Receivable", "Receivables",
                    "Gross Accounts Receivable"],
    "payables": ["Accounts Payable", "Payables"],
    "total_debt": ["Total Debt"],
    "net_debt": ["Net Debt"],
    "long_term_debt": ["Long Term Debt"],
    "current_debt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "goodwill": ["Goodwill"],
    "intangibles": ["Other Intangible Assets", "Goodwill And Other Intangible Assets"],
    "retained_earnings": ["Retained Earnings"],
    "working_capital": ["Working Capital"],
    "net_ppe": ["Net PPE"],
    "shares_out": ["Ordinary Shares Number", "Share Issued"],
    "tangible_book": ["Tangible Book Value"],
    # cash flow
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure", "Purchase Of PPE"],
    "fcf": ["Free Cash Flow"],
    "sbc": ["Stock Based Compensation"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "buyback": ["Repurchase Of Capital Stock", "Common Stock Payments"],
}


def pick(df, key, col=0):
    """Fetch a line item by alias list; record which alias resolved."""
    if df is None or getattr(df, "empty", True):
        return None
    if col >= len(df.columns):
        return None
    for alias in ALIAS[key]:
        if alias in df.index:
            try:
                v = df.loc[alias].iloc[col]
            except Exception:
                continue
            if v is not None and pd.notna(v):
                if col == 0:
                    DIAG["aliases"][key] = alias
                return float(v)
    return None


def series(df, key, n=5):
    """Most-recent-first list of up to n annual values."""
    out = []
    for i in range(n):
        out.append(pick(df, key, i))
    return out


def ttm(qdf, key, adf=None):
    """TTM sum of last 4 quarters; falls back to the latest annual figure."""
    if qdf is not None and not getattr(qdf, "empty", True):
        vals = [pick(qdf, key, i) for i in range(min(4, len(qdf.columns)))]
        if len(vals) == 4 and all(v is not None for v in vals):
            return sum(vals), "TTM"
        good = [v for v in vals if v is not None]
        if len(good) >= 2 and adf is not None:
            ann = pick(adf, key, 0)
            if ann is not None:
                return ann, "FY"
    if adf is not None:
        ann = pick(adf, key, 0)
        if ann is not None:
            return ann, "FY"
    return None, None


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def yoy_quarter(qdf, key):
    """(latest quarter, same quarter a year earlier), or (None, None).

    Comparing against the same quarter last year removes seasonality and is more
    current than a fiscal-year figure. If the year-ago column is missing, or is not
    about a year before the latest one (a skipped quarter, a semi-annual reporter),
    there is no honest comparison, so it returns nothing rather than a substitute.
    """
    if qdf is None or getattr(qdf, "empty", True) or len(qdf.columns) < 5:
        return None, None
    try:
        gap = (qdf.columns[0] - qdf.columns[4]).days
    except Exception:
        return None, None
    if not 350 <= gap <= 380:
        return None, None
    return pick(qdf, key, 0), pick(qdf, key, 4)


def safe_div(a, b):
    if a is None or b is None:
        return None
    try:
        if b == 0:
            return None
        return a / b
    except Exception:
        return None


def cagr(newest, oldest, years):
    if newest is None or oldest is None or years <= 0:
        return None
    if oldest <= 0 or newest <= 0:
        return None
    return (newest / oldest) ** (1.0 / years) - 1.0


@dataclass
class Metrics:
    symbol: str = ""
    name: str = ""
    sector: str = ""
    industry: str = ""
    quote_ccy: str = "USD"
    fin_ccy: str = "USD"
    rulebook: str = "default"
    rulebook_basis: str = ""
    price_native: float = None
    price_usd: float = None
    mcap_fin: float = None      # market cap expressed in STATEMENT currency
    mcap_usd: float = None
    dollar_vol: float = None
    shares_quote: float = None
    ttm_label: str = "TTM"
    data: dict = field(default_factory=dict)
    fy_years: list = field(default_factory=list)

    def g(self, k):
        return self.data.get(k)


def build_metrics(symbol, tk, info, fin, qfin, bs, cf, qcf, hist):
    m = Metrics(symbol=symbol)
    m.name = info.get("longName") or info.get("shortName") or symbol
    m.sector = info.get("sector") or ""
    m.industry = info.get("industry") or ""
    m.quote_ccy = info.get("currency") or "USD"
    m.fin_ccy = info.get("financialCurrency") or m.quote_ccy
    if m.fin_ccy == "ILA":
        m.fin_ccy = "ILS"

    try:
        m.fy_years = [str(c.date()) for c in fin.columns[:5]] if fin is not None \
            and not fin.empty else []
    except Exception:
        m.fy_years = []

    # ---- price / market cap, computed rather than trusted -------------
    price = None
    if hist is not None and not hist.empty:
        price = float(hist["Close"].iloc[-1])
        if math.isnan(price):
            # The most recent bar can be still-forming -- real Volume but no Close yet
            # (seen on QLTU.TA: today's row had Volume 24516, Close NaN). `price is None`
            # doesn't catch this (NaN is a float, not None), so it must be cleared explicitly
            # or it silently poisons every downstream "is not None" check (market cap, every
            # multiple) with NaN instead of falling back.
            price = None
    if price is None:
        # history came back empty, or its latest bar hasn't closed yet; info already carries
        # a live quote, at no extra request
        price = info.get("currentPrice") or info.get("regularMarketPrice")
    m.price_native = price
    price_ccy = m.quote_ccy
    price_major = price / 100.0 if (price is not None and price_ccy == "ILA") else price
    major_ccy = "ILS" if price_ccy == "ILA" else price_ccy
    m.price_usd = to_usd(price, price_ccy)

    # info["sharesOutstanding"] is the same figure fast_info reported (0.00% difference
    # on 12 US and Tel Aviv tickers), and fast_info cost four extra requests to get it.
    shares = info.get("sharesOutstanding")
    if not shares:
        shares = pick(bs, "shares_out", 0)
    m.shares_quote = shares

    if price_major is not None and shares:
        mcap_major = price_major * shares
        m.mcap_usd = to_usd(mcap_major, major_ccy)
        # express market cap in the STATEMENT currency before it ever meets a
        # statement-derived denominator
        if major_ccy == m.fin_ccy:
            m.mcap_fin = mcap_major
        elif m.fin_ccy == "USD":
            m.mcap_fin = m.mcap_usd
        else:
            usd = m.mcap_usd
            r = fx_rate("USD", m.fin_ccy)
            m.mcap_fin = usd * r if (usd is not None and r) else None

    if hist is not None and not hist.empty and len(hist) >= 5:
        dv = (hist["Close"] * hist["Volume"]).tail(30)
        dv_native = float(dv.median())
        if price_ccy == "ILA":
            dv_native /= 100.0
        m.dollar_vol = to_usd(dv_native, major_ccy)

    d = {}

    # ---- income statement ---------------------------------------------
    d["revenue"], m.ttm_label = ttm(qfin, "revenue", fin)
    d["gross_profit"], _ = ttm(qfin, "gross_profit", fin)
    d["operating_income"], _ = ttm(qfin, "operating_income", fin)
    d["ebit"], _ = ttm(qfin, "ebit", fin)
    d["ebitda"], _ = ttm(qfin, "ebitda", fin)
    d["net_income"], _ = ttm(qfin, "net_income", fin)
    d["interest_expense"], _ = ttm(qfin, "interest_expense", fin)
    d["net_interest_income"], _ = ttm(qfin, "net_interest_income", fin)
    d["rnd"], _ = ttm(qfin, "rnd", fin)
    d["pretax"], _ = ttm(qfin, "pretax", fin)
    d["tax"], _ = ttm(qfin, "tax", fin)
    d["dep_amort"], _ = ttm(qfin, "dep_amort", fin)
    d["diluted_eps"] = pick(fin, "diluted_eps", 0)
    d["diluted_shares_stmt"] = pick(fin, "diluted_shares", 0)

    # ---- cash flow ------------------------------------------------------
    d["cfo"], _ = ttm(qcf, "cfo", cf)
    d["capex"], _ = ttm(qcf, "capex", cf)
    d["fcf"], _ = ttm(qcf, "fcf", cf)
    d["sbc"], _ = ttm(qcf, "sbc", cf)
    d["dividends_paid"], _ = ttm(qcf, "dividends_paid", cf)
    d["buyback"], _ = ttm(qcf, "buyback", cf)
    if d["fcf"] is None and d["cfo"] is not None and d["capex"] is not None:
        d["fcf"] = d["cfo"] + d["capex"]  # capex is negative in yfinance

    # ---- balance sheet --------------------------------------------------
    for k in ["total_assets", "total_liabilities", "equity", "current_assets",
              "current_liabilities", "cash", "inventory", "receivables",
              "payables", "total_debt", "net_debt", "long_term_debt",
              "current_debt", "goodwill", "intangibles", "retained_earnings",
              "working_capital", "net_ppe", "tangible_book"]:
        d[k] = pick(bs, k, 0)

    # ---- multi-year series ---------------------------------------------
    d["revenue_hist"] = series(fin, "revenue")
    d["ni_hist"] = series(fin, "net_income")
    d["cfo_hist"] = series(cf, "cfo")
    d["fcf_hist"] = series(cf, "fcf")
    d["equity_hist"] = series(bs, "equity")
    d["assets_hist"] = series(bs, "total_assets")
    d["shares_hist"] = series(bs, "shares_out")
    d["gp_hist"] = series(fin, "gross_profit")
    d["recv_hist"] = series(bs, "receivables")
    d["inv_hist"] = series(bs, "inventory")
    d["pay_hist"] = series(bs, "payables")
    d["cl_hist"] = series(bs, "current_liabilities")
    d["ca_hist"] = series(bs, "current_assets")
    d["ltd_hist"] = series(bs, "long_term_debt")
    d["dep_hist"] = series(fin, "dep_amort")
    d["cogs_hist"] = series(fin, "cost_of_revenue")
    d["sga_hist"] = series(fin, "sga")
    d["ppe_hist"] = series(bs, "net_ppe")
    d["div_paid_hist"] = series(cf, "dividends_paid")

    # ---- derived --------------------------------------------------------
    rev = d["revenue"]
    d["gross_margin"] = safe_div(d["gross_profit"], rev)
    d["op_margin"] = safe_div(d["operating_income"], rev)
    d["net_margin"] = safe_div(d["net_income"], rev)
    d["fcf_margin"] = safe_div(d["fcf"], rev)
    d["rnd_intensity"] = safe_div(d["rnd"], rev)

    # EBITDA sanity: EBITDA = EBIT + D&A, and D&A is never negative, so EBITDA
    # below EBIT means the reported figure is corrupt. Camtek's Q4-2025 EBITDA
    # comes back as -42.5M against +31.7M operating income in the same quarter,
    # which dragged TTM EBITDA to 43.8M against a true ~118M and inflated its
    # net-debt/EBITDA to 7.8x. One bad quarter must not poison every leverage
    # ratio, so rebuild it from EBIT plus depreciation.
    if d["ebit"] is not None:
        rebuilt = d["ebit"] + abs(d["dep_amort"] or 0)
        if d["ebitda"] is None or d["ebitda"] < d["ebit"]:
            if d["ebitda"] is not None:
                note(f"EBITDA {d['ebitda']:.0f} below EBIT {d['ebit']:.0f}; "
                     f"rebuilt as EBIT + D&A = {rebuilt:.0f}")
            d["ebitda"] = rebuilt
            d["ebitda_rebuilt"] = True

    equity = d["equity"]
    debt = d["total_debt"]
    cash = d["cash"]
    if d["net_debt"] is None and debt is not None and cash is not None:
        d["net_debt"] = debt - cash

    tax_rate = safe_div(d["tax"], d["pretax"])
    if tax_rate is None or not (0 <= tax_rate <= 0.6):
        tax_rate = 0.21
    d["tax_rate"] = tax_rate
    nopat = d["ebit"] * (1 - tax_rate) if d["ebit"] is not None else None
    invested = None
    if equity is not None and debt is not None:
        invested = equity + debt - (cash or 0)
    d["roic"] = safe_div(nopat, invested)
    d["roe"] = safe_div(d["net_income"], equity)
    d["roa"] = safe_div(d["net_income"], d["total_assets"])

    d["debt_to_equity"] = safe_div(debt, equity)
    # Negative EBITDA must never produce a ratio. Net debt of +50M over EBITDA of
    # -10M is -5.0, and every leverage test here is an upper bound, so a distressed
    # company would read as ultra-low-leverage and sail through. EV/EBITDA below
    # already guards this; these two did not.
    d["ebitda_negative"] = d["ebitda"] is not None and d["ebitda"] <= 0
    d["nd_ebitda"] = (safe_div(d["net_debt"], d["ebitda"])
                      if (d["ebitda"] or 0) > 0 else None)
    ie = abs(d["interest_expense"]) if d["interest_expense"] else None
    if ie is None:
        ie = abs(pick(fin, "interest_expense", 0) or 0) or None
    d["interest_coverage"] = safe_div(d["ebit"], ie)
    _nd_eb = safe_div(d["net_debt"], d["ebitda"])
    if d["interest_coverage"] is None and (d["ebit"] or 0) > 0 \
            and (d["net_debt"] is None or d["net_debt"] <= 0
                 or (_nd_eb is not None and _nd_eb < 1.0)):
        # No reported interest expense and no net debt: the burden is nil, not
        # unknown. Leaving this NA would disable the critical floor AND the
        # fortress waiver on exactly the safest balance sheets.
        d["interest_coverage"] = 999.0
        d["interest_coverage_inferred"] = True

    # Cash-backed waiver for the critical coverage gates. EBIT coverage is the primary test,
    # but Yahoo's EBIT is pretax income plus interest, so every charge below operating income
    # (impairments, restructuring, litigation) lands in it: Teva's operating income is
    # $3.3B and its EBIT $1.2B, because of ~$2.2B of special charges. The waiver applies only
    # when EBIT coverage is under the 1.5x floor AND two independent measures both clear it:
    # operating income over interest, and cash coverage -- (CFO + interest) / interest, which
    # uses neither profit line and assumes CFO is after interest paid, as under US GAAP.
    # Requiring both keeps this from clearing anyone who is merely flattered by one number.
    d["opinc_coverage"] = safe_div(d["operating_income"], ie)
    d["cash_coverage"] = (safe_div(d["cfo"] + ie, ie)
                          if (d["cfo"] is not None and ie) else None)
    d["coverage_effective"] = d["interest_coverage"]
    d["coverage_waived"] = False
    _ec, _oc, _cc = d["interest_coverage"], d["opinc_coverage"], d["cash_coverage"]
    if (_ec is not None and _ec < 1.5 and _oc is not None and _cc is not None
            and _oc >= 1.5 and _cc >= 1.5):
        d["coverage_effective"] = min(_oc, _cc)     # the weaker confirmation is what counts
        d["coverage_waived"] = True
    d["current_ratio"] = safe_div(d["current_assets"], d["current_liabilities"])
    quick_assets = None
    if d["current_assets"] is not None:
        quick_assets = d["current_assets"] - (d["inventory"] or 0)
    d["quick_ratio"] = safe_div(quick_assets, d["current_liabilities"])
    d["cfo_over_cl"] = safe_div(d["cfo"], d["current_liabilities"])
    d["equity_assets"] = safe_div(equity, d["total_assets"])

    if d["tangible_book"] is None and equity is not None:
        d["tangible_book"] = equity - (d["goodwill"] or 0) - (d["intangibles"] or 0)
    d["goodwill_ratio"] = safe_div(d["goodwill"], d["total_assets"])

    d["cfo_ni"] = safe_div(d["cfo"], d["net_income"]) \
        if (d["net_income"] or 0) > 0 else None
    d["accruals"] = safe_div((d["net_income"] or 0) - (d["cfo"] or 0),
                             d["total_assets"])
    if d["cfo"] is not None and d["capex"] is not None:
        d["fcf_sbc"] = d["cfo"] + d["capex"] - abs(d["sbc"] or 0)
    else:
        d["fcf_sbc"] = None
    d["sbc_cfo"] = safe_div(abs(d["sbc"]) if d["sbc"] else None, d["cfo"])

    rh = d["revenue_hist"]
    # Latest quarter vs the same quarter a year earlier. No fallback to the fiscal
    # year: if the comparison is not available the check reports not-available.
    rq, rq_prior = yoy_quarter(qfin, "revenue")
    d["rev_growth"] = (safe_div(rq - rq_prior, rq_prior)
                       if rq is not None and (rq_prior or 0) > 0 else None)
    d["opinc_q"], d["opinc_q_prior"] = yoy_quarter(qfin, "operating_income")
    # Worst-year warning (not scored): any fall in fiscal-year revenue in the last
    # three years. Endpoint math would hide a dip that later recovered.
    d["revenue_fall_note"] = None
    worst = None   # (fall fraction, year label): the WORST fall, not merely the latest
    for i in range(3):
        a_ = rh[i]
        b_ = rh[i + 1] if i + 1 < len(rh) else None
        if a_ is not None and b_ and b_ > 0 and a_ < b_:
            fall = (b_ - a_) / b_
            if worst is None or fall > worst[0]:
                worst = (fall, m.fy_years[i][:4] if i < len(m.fy_years) else "a recent year")
    if worst:
        d["revenue_fall_note"] = (f"Revenue fell {worst[0] * 100:.1f}% in FY{worst[1]} "
                                  f"within the last three years -- growth is not steady")
    d["rev_cagr3"] = cagr(rh[0], rh[3], 3) if len(rh) > 3 else None

    # Capex intensity -- how much of revenue is consumed by capital spending. Not
    # scored on level alone: a growth company can spend 20%+ of revenue on capex and
    # be excellent (Alphabet's AI buildout is ~23% of revenue at 24% revenue growth);
    # a stagnant one spending the same 20%+ just to stand still is the actual problem
    # ("maintenance capex" without growth to show for it). The scored check below
    # pairs this with revenue growth rather than gating on the level by itself.
    d["capex_intensity"] = safe_div(abs(d["capex"]) if d["capex"] is not None else None, rev)

    # Dividend history for a 3y CAGR -- deliberately scored leniently (see the check).
    dph_ = [abs(v) if v is not None else None for v in d["div_paid_hist"]]
    d["div_cagr3"] = cagr(dph_[0], dph_[3], 3) if len(dph_) > 3 else None

    # Shareholder yield -- (dividends + buybacks) / market cap. Reported as CONTEXT
    # only, never scored: dividing by market cap makes this a valuation-sensitive
    # number (Apple and Microsoft, both mega-caps, show low single digits despite
    # returning enormous absolute sums, purely because their market caps are huge),
    # and a LOW yield is entirely correct for a high-ROIC reinvestor -- that is
    # already rewarded by the ROIC check, and this tool deliberately stays a
    # quality/safety check, not a value screen.
    returned = abs(d["dividends_paid"] or 0) + abs(d["buyback"] or 0)
    d["shareholder_yield"] = safe_div(returned, m.mcap_fin) if m.mcap_fin else None
    ch = d["cfo_hist"]
    d["cfo_growth"] = safe_div(ch[0] - ch[1], abs(ch[1])) \
        if ch[0] is not None and ch[1] else None
    sh = d["shares_hist"]
    d["share_change"] = safe_div(sh[0] - sh[1], sh[1]) \
        if sh[0] is not None and sh[1] else None
    eh = d["equity_hist"]
    d["equity_cagr3"] = cagr(eh[0], eh[3], 3) if len(eh) > 3 and eh[3] else None

    fh = [v for v in d["fcf_hist"][:4] if v is not None]
    d["fcf_positive_years"] = sum(1 for v in fh if v > 0)
    d["fcf_years_checked"] = len(fh)

    # dividend
    # Yahoo reports dividendYield already as a percentage number:
    # AAPL 0.32 means 0.32%, POLI.TA 3.81 means 3.81%. Always scale.
    dy = info.get("dividendYield")
    d["div_yield"] = dy / 100.0 if dy is not None else None
    dividends = abs(d["dividends_paid"]) if d["dividends_paid"] else None
    d["cash_payout"] = safe_div(dividends, d["net_income"]) \
        if (d["net_income"] or 0) > 0 else None
    d["div_covered_fcf"] = safe_div(dividends, d["fcf"]) \
        if (d["fcf"] or 0) > 0 else None

    # Time to live: months of cash left at the current TTM burn rate, assuming no
    # new financing -- no dilution, no new debt. Deliberately CFO-gated, not FCF-gated:
    # a regulated utility permanently spends more on capex than it earns operationally,
    # funded by routine debt issuance, which is a financing structure, not distress.
    # Duke Energy has +$12.3B of operating cash flow and still shows -$1.7B of FCF;
    # gating this on FCF alone put Duke and Enlight Renewable at 1.7 and 4.1 months
    # and would have AVOIDed two stable capital-intensive operators. TTM, not the
    # latest single quarter, because one quarter's working-capital swing or one-off
    # capex should not swing a going-concern estimate.
    #
    # "cfo_reversal" already scores the binary "is CFO positive" on its own, so a
    # self-funding company (CFO >= 0) is NA here, not PASS -- crediting the same
    # positive-CFO signal twice would double-count it in the liquidity pillar.
    if (d["cfo"] or 0) < 0 and cash is not None:
        burn = abs(d["fcf"]) if (d["fcf"] or 0) < 0 else abs(d["cfo"])
        d["runway_months"] = (cash / burn) * 12.0 if burn else None
    else:
        d["runway_months"] = None

    # working capital days
    d["dso"] = safe_div(d["receivables"], rev) * 365 if safe_div(d["receivables"], rev) else None
    cogs = d["cogs_hist"][0] if d["cogs_hist"] else None
    d["dio"] = safe_div(d["inventory"], cogs) * 365 if safe_div(d["inventory"], cogs) else None
    d["dpo"] = safe_div(d["payables"], cogs) * 365 if safe_div(d["payables"], cogs) else None
    if None not in (d["dso"], d["dio"], d["dpo"]):
        d["ccc"] = d["dio"] + d["dso"] - d["dpo"]
    else:
        d["ccc"] = None
    ph = d["pay_hist"]
    d["dpo_growth"] = safe_div(ph[0] - ph[1], ph[1]) \
        if ph[0] is not None and ph[1] else None

    # multiples -- all in statement currency, mcap already converted
    d["pe"] = safe_div(m.mcap_fin, d["net_income"]) if (d["net_income"] or 0) > 0 else None
    d["p_fcf"] = safe_div(m.mcap_fin, d["fcf"]) if (d["fcf"] or 0) > 0 else None
    ev = None
    if m.mcap_fin is not None and d["net_debt"] is not None:
        ev = m.mcap_fin + d["net_debt"]
    d["ev_ebitda"] = safe_div(ev, d["ebitda"]) if (d["ebitda"] or 0) > 0 else None
    d["p_b"] = safe_div(m.mcap_fin, equity) if (equity or 0) > 0 else None

    # share count reconciliation
    stmt_sh = d["diluted_shares_stmt"]
    if stmt_sh and m.shares_quote:
        d["share_divergence"] = abs(m.shares_quote - stmt_sh) / stmt_sh
    else:
        d["share_divergence"] = None

    m.data = d
    m.rulebook, m.rulebook_basis = choose_rulebook(m)
    return m


# --------------------------------------------------------------------------
# Rulebook routing
# --------------------------------------------------------------------------
def choose_rulebook(m):
    d = m.data
    sec = (m.sector or "").lower()
    ind = (m.industry or "").lower()

    rev_usd = None
    if d.get("revenue") is not None:
        rev_usd = to_usd(d["revenue"], m.fin_ccy)
    ni = d.get("net_income")

    if "reit" in ind:
        return "reit", "industry label"
    # There is deliberately NO fallback for a missing sector. main() refuses to score a company
    # whose record has no sector (fail closed), so this is never reached without one. The old
    # fallback -- "net interest income row present, therefore a bank" -- matched 97% of non-bank
    # companies and was the way a rate-limited run turned a failing company into a perfect one.
    if "financial" in sec or "bank" in ind or "insurance" in ind:
        return "financials", "sector label"
    if "utilit" in sec or "energy" in sec:
        return "capital_intensive", "sector label"

    if rev_usd is not None and rev_usd < 25e6 and (ni or 0) < 0:
        return "pre_revenue", "revenue < $25M with negative earnings"
    return "default", "sector label"


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
PASS, FAIL, NA, WATCH = "PASS", "FAIL", "NA", "WATCH"

QUALITY_PILLARS = {"profitability": 30, "cash": 30, "growth": 25, "capital": 15}
RISK_PILLARS = {"leverage": 40, "liquidity": 30, "earnings_quality": 30}


def pct(v, nd=1):
    return "n/a" if v is None else f"{v*100:.{nd}f}%"


def num(v, nd=2):
    return "n/a" if v is None else f"{v:.{nd}f}"


def money(v):
    if v is None:
        return "n/a"
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v/div:.2f}{suf}"
    return f"{v:.0f}"


def next_earnings(calendar):
    """{date, end_date, days} for the next expected earnings date, or None.

    `calendar["Earnings Date"]` is sometimes a single date, sometimes a 2-date estimate window
    (not two separate events) -- both are handled. `days` is negative when yfinance has not yet
    rolled a stale date forward past an earnings release that already happened; render that as
    "overdue" rather than a negative countdown, since a negative number reads as a bug.
    """
    dates = calendar.get("Earnings Date") if isinstance(calendar, dict) else None
    if not dates:
        return None
    dates = sorted(set(dates))
    today = dt.datetime.now(TLV_TZ).date()
    return {"date": dates[0], "end_date": dates[-1] if len(dates) > 1 else None,
            "days": (dates[0] - today).days}


def news_marker(ts):
    """[2026-10-17 / 20.8h ago] for a headline's unix publish time, in local (TLV) time.

    Days once the headline clears 24h old -- "0.9d ago" reads worse than "20.8h ago" either
    side of the boundary, so the unit switches at the boundary rather than being fixed.
    """
    if not ts:
        return "[date unknown]"
    when = dt.datetime.fromtimestamp(ts, TLV_TZ)
    age_h = (time.time() - ts) / 3600
    rel = f"{num(age_h / 24, 1)}d ago" if age_h >= 24 else f"{num(age_h, 1)}h ago"
    return f"[{when.strftime('%Y-%m-%d')} / {rel}]"


class Check:
    def __init__(self, cid, label, pillar, side, weight, fn,
                 critical=False, section="sanity", books=None, skip_books=None):
        self.cid, self.label, self.pillar, self.side = cid, label, pillar, side
        self.weight, self.fn, self.critical = weight, fn, critical
        self.section, self.books, self.skip_books = section, books, skip_books

    def applies(self, rulebook):
        if self.books and rulebook not in self.books:
            return False
        if self.skip_books and rulebook in self.skip_books:
            return False
        return True


def _thr(value, threshold, higher_good=True):
    if value is None:
        return NA
    if higher_good:
        return PASS if value >= threshold else FAIL
    return PASS if value <= threshold else FAIL


def _negative_ebitda_state(m):
    """Resolve the negative-EBITDA case before any leverage ratio is compared.

    Returns (result_or_None, nd_ebitda). A company with no earnings before
    interest, tax, D&A and real net debt has nothing to service that debt with --
    that is a solvency failure, not a low ratio. With net cash instead, it is a
    runway question and the cash-runway gate owns it, so this reports NA rather
    than double-counting against the pre-revenue rulebook.
    """
    nd = m.g("nd_ebitda")
    if not m.g("ebitda_negative"):
        return None, nd
    net_debt = m.g("net_debt")
    if net_debt is not None and net_debt > 0:
        return (FAIL, (f"EBITDA {money(m.g('ebitda'))} {m.fin_ccy} is negative with "
                       f"{money(net_debt)} net debt -- no earnings to service it")), nd
    return (NA, (f"EBITDA {money(m.g('ebitda'))} {m.fin_ccy} negative, but net cash "
                 f"-- runway question, not leverage")), nd


def neg_equity_waiver(m):
    """(waived, why_not_or_message) for the negative-equity gate.

    Negative book equity has two very different causes. Accumulated losses destroy equity; a
    cash machine that returns more than it earns (McDonald's, Yum) drives it negative
    through buybacks. (Otis looks like the second kind but is not waived: Yahoo reports no
    interest-expense line for it, so coverage is unknown and the rule fails closed.) The waiver recognises only the second, and needs ALL of: operating cash
    flow and free cash flow positive, free cash flow positive in at least 3 of the last 4
    years, EBIT interest coverage of at least 3x (a company with no reported interest and no
    net debt is inferred at 999x upstream; a missing figure is no evidence and fails), and a
    share count that is actually shrinking -- flat does not qualify, because partnerships with
    near-zero equity and flat units are a different mechanism. Operating companies only.
    """
    if m.rulebook in ("financials", "reit"):
        return False, "financials and REITs keep the strict test"
    cfo, fcf, cov, sh = m.g("cfo"), m.g("fcf"), m.g("interest_coverage"), m.g("share_change")
    yrs, ok = m.g("fcf_years_checked") or 0, m.g("fcf_positive_years") or 0
    if cfo is None or cfo <= 0 or fcf is None or fcf <= 0:
        return False, "operating or free cash flow is not positive"
    if yrs < 3 or ok < 3:
        return False, f"free cash flow positive in only {ok} of {yrs} years"
    if cov is None:
        return False, "interest coverage unknown"
    if cov < 3.0:
        return False, f"interest coverage {cov:.1f}x is under 3x"
    if sh is None or sh >= 0:
        return False, "share count is not shrinking"
    return True, (f"waived: operating cash flow {money(cfo)} and free cash flow {money(fcf)} "
                  f"(positive in {ok} of {yrs} years), interest coverage {cov:.1f}x, shares "
                  f"{pct(sh)} YoY -- negative equity from buybacks, not from losses")


def build_checks():
    C = []
    a = C.append

    # ---------------- Profitability (quality) -------------------------
    a(Check("op_margin", "Operating margin", "profitability", "quality", 10,
            lambda m: (_thr(m.g("op_margin"), 0.10),
                       f"Operating margin {pct(m.g('op_margin'))} (>= 10%)"),
            skip_books={"financials", "pre_revenue"}))
    a(Check("net_margin", "Net margin", "profitability", "quality", 3,
            lambda m: (_thr(m.g("net_margin"), 0.05),
                       f"Net margin {pct(m.g('net_margin'))} (>= 5%, low weight)"),
            skip_books={"financials", "pre_revenue"}))
    a(Check("roic", "ROIC", "profitability", "quality", 10,
            lambda m: (_thr(m.g("roic"), 0.12),
                       f"ROIC {pct(m.g('roic'))} (>= 12%)"),
            skip_books={"financials", "pre_revenue"}))
    a(Check("roa", "ROA", "profitability", "quality", 7,
            lambda m: (_thr(m.g("roa"), 0.05),
                       f"ROA {pct(m.g('roa'))} (>= 5%)"),
            skip_books={"financials", "pre_revenue"}))
    # financials substitutes
    a(Check("fin_roa", "ROA (bank)", "profitability", "quality", 10,
            lambda m: (_thr(m.g("roa"), 0.01),
                       f"ROA {pct(m.g('roa'))} (>= 1% for a bank)"),
            books={"financials"}))
    a(Check("fin_roe", "ROE (bank)", "profitability", "quality", 10,
            lambda m: (_thr(m.g("roe"), 0.10),
                       f"ROE {pct(m.g('roe'))} (>= 10%)"),
            books={"financials"}))
    a(Check("fin_eq_assets", "Equity / assets", "profitability", "quality", 10,
            lambda m: (_thr(m.g("equity_assets"), 0.08),
                       f"Equity/assets {pct(m.g('equity_assets'))} (>= 8%)"),
            books={"financials"}))

    # ---------------- Cash (quality) ----------------------------------
    a(Check("fcf_pos", "FCF positive", "cash", "quality", 10,
            lambda m: (NA if m.g("fcf") is None else
                       (PASS if m.g("fcf") > 0 else FAIL),
                       f"FCF {money(m.g('fcf'))} {m.fin_ccy}"),
            skip_books={"financials"}))
    a(Check("fcf_margin", "FCF margin", "cash", "quality", 8,
            lambda m: (_thr(m.g("fcf_margin"), 0.08),
                       f"FCF margin {pct(m.g('fcf_margin'))} (>= 8%)"),
            skip_books={"financials", "pre_revenue"}))
    # Dropped for banks: their operating cash flow is dominated by deposit and
    # loan flows, not by earnings quality, so this reads as noise. Bank Hapoalim
    # and Bank Leumi scoring 20 points apart on it was the tell.
    a(Check("cfo_ni", "Cash conversion", "cash", "quality", 7,
            lambda m: (_thr(m.g("cfo_ni"), 0.8),
                       f"CFO/NetIncome {num(m.g('cfo_ni'))} (>= 0.8)"),
            skip_books={"financials"}))
    a(Check("fcf_consistency", "FCF consistency", "cash", "quality", 5,
            lambda m: (NA if m.g("fcf_years_checked") < 3 else
                       (PASS if m.g("fcf_positive_years") >= 3 else FAIL),
                       f"FCF positive in {m.g('fcf_positive_years')}/"
                       f"{m.g('fcf_years_checked')} recent years (>= 3)"),
            skip_books={"financials"}))
    a(Check("fcf_sbc", "SBC-adjusted FCF", "cash", "quality", 5,
            lambda m: (NA if m.g("fcf_sbc") is None else
                       (PASS if m.g("fcf_sbc") > 0 else FAIL),
                       f"FCF after stock comp {money(m.g('fcf_sbc'))} {m.fin_ccy}"
                       + (" -- reported FCF is positive only before SBC"
                          if (m.g("fcf") or 0) > 0 and (m.g("fcf_sbc") or 0) <= 0
                          else "")),
            skip_books={"financials"}))

    # ---------------- Growth (quality) --------------------------------
    a(Check("rev_growth", "Revenue growth", "growth", "quality", 10,
            lambda m: (_thr(m.g("rev_growth"), 0.05),
                       f"Revenue {pct(m.g('rev_growth'))} latest quarter vs same quarter "
                       f"last year (>= 5%)")))

    def opinc_growth(m):
        cur, prior = m.g("opinc_q"), m.g("opinc_q_prior")
        if cur is None or prior is None:
            return NA, "Operating income growth n/a (no year-ago quarter)"
        # A percentage off a zero or negative base is meaningless (-5M to +2M), so
        # crossing zero is reported as a state. Only genuinely missing data is NA.
        if prior <= 0:
            if cur > 0:
                return PASS, (f"Operating income turnaround: loss of {money(abs(prior))} "
                              f"{m.fin_ccy} to profit of {money(cur)}")
            return FAIL, (f"Operating income still unprofitable "
                          f"({money(cur)} vs {money(prior)} a year earlier)")
        g = (cur - prior) / prior
        return (PASS if g > 0 else FAIL), (f"Operating income {pct(g)} latest quarter vs "
                                           f"same quarter last year (> 0)")

    a(Check("opinc_growth", "Operating income growth", "growth", "quality", 10,
            opinc_growth, skip_books={"financials", "pre_revenue"}))
    a(Check("cfo_growth", "CFO growth", "growth", "quality", 10,
            lambda m: (NA if m.g("cfo_growth") is None else
                       (PASS if m.g("cfo_growth") > 0 else FAIL),
                       f"CFO {pct(m.g('cfo_growth'))} YoY (> 0)"),
            skip_books={"financials"}))  # bank CFO is loan/deposit flow: JPM read -252%
    a(Check("rev_cagr", "3y revenue CAGR", "growth", "quality", 5,
            lambda m: (NA if m.g("rev_cagr3") is None else
                       (PASS if m.g("rev_cagr3") > 0 else FAIL),
                       f"3y revenue CAGR {pct(m.g('rev_cagr3'))}")))

    def capex_trap(m):
        """FAILs only heavy capex paired with weak growth -- the 'maintenance capex'
        trap (airlines, legacy auto: spend heavily just to stand still), not growth
        capex (Alphabet: ~23% of revenue at 24% revenue growth, which must PASS).
        """
        ci, growth = m.g("capex_intensity"), m.g("rev_growth")
        if ci is None:
            return NA, "Capex intensity n/a"
        msg = f"Capex {pct(ci)} of revenue"
        if ci <= 0.15:
            return PASS, msg + " (<= 15%)"
        if growth is not None and growth >= 0.05:
            return PASS, msg + f", but revenue growth {pct(growth)} funds it -- growth capex, not maintenance"
        return FAIL, msg + " with weak or unknown revenue growth -- capital-intensive without growth to show for it"

    a(Check("capex_trap", "Capex intensity", "profitability", "quality", 5, capex_trap,
            skip_books={"financials", "pre_revenue", "capital_intensive"}))

    # ---------------- Capital allocation (quality) ---------------------
    a(Check("dilution", "Share count trend", "capital", "quality", 10,
            lambda m: (NA if m.g("share_change") is None else
                       (PASS if m.g("share_change") <= 0.01 else FAIL),
                       f"Shares outstanding {pct(m.g('share_change'))} YoY (<= 0)")))
    # Severe dilution has been documented in SKILL.md and rulebook.md as a critical
    # AVOID gate since this skill's first commit, but no such gate existed in code --
    # the check above is scored, not critical, so 20%+ issuance only cost Quality
    # points and could never trip AVOID by itself. Closing that doc/code gap: >20%
    # YoY share growth is a going-concern-level signal (funding operations by selling
    # equity, not earning it) and now trips the same way the leverage and coverage
    # gates do -- weight 0 so it does not double-count against the scored check above.
    a(Check("dilution_crit", "Severe dilution", "capital", "quality", 0,
            lambda m: (NA if m.g("share_change") is None else
                       (FAIL if m.g("share_change") > 0.20 else PASS),
                       f"Shares outstanding {pct(m.g('share_change'))} YoY "
                       f"(critical if > 20%)"),
            critical=True))
    a(Check("div_cover", "Dividend covered by FCF", "capital", "quality", 5,
            lambda m: (NA if m.g("div_covered_fcf") is None else
                       (PASS if m.g("div_covered_fcf") <= 1.0 else FAIL),
                       f"Dividends / FCF {num(m.g('div_covered_fcf'))} (<= 1.0)"),
            skip_books={"financials"}))
    a(Check("fin_div_cover", "Dividend covered by earnings", "capital", "quality", 5,
            lambda m: (NA if m.g("cash_payout") is None else
                       (PASS if m.g("cash_payout") <= 0.8 else FAIL),
                       f"Dividends / net income {pct(m.g('cash_payout'))} (<= 80%)"),
            books={"financials"}))
    def div_not_cut(m):
        """A flat or slow-growing dividend is a capital-allocation PREFERENCE, not a
        flaw -- Apple's 3y dividend CAGR is ~1.3% because it prioritises buybacks, and
        Procter & Gamble's is ~4.4%, both excellent capital allocators. Scoring a
        >5% growth bar would fail both. Only an actual CUT (negative CAGR) fails here.
        """
        c = m.g("div_cagr3")
        if c is None:
            return NA, "Dividend growth n/a (no dividend, or insufficient history)"
        if c >= 0:
            return PASS, f"3y dividend CAGR {pct(c)} (not a cut)"
        return FAIL, f"3y dividend CAGR {pct(c)} (a cut)"

    a(Check("div_not_cut", "Dividend trend", "capital", "quality", 4, div_not_cut))

    # ---------------- Leverage (risk) ---------------------------------
    def neg_equity(m):
        eq = m.g("equity")
        if eq is None:
            return NA, f"Shareholder equity {money(eq)} {m.fin_ccy}"
        msg = f"Shareholder equity {money(eq)} {m.fin_ccy}"
        if eq > 0:
            return PASS, msg
        ok, why = neg_equity_waiver(m)
        if ok:
            return WATCH, f"{msg} -- {why}"
        return FAIL, msg

    a(Check("neg_equity", "Shareholder equity", "leverage", "risk", 12,
            neg_equity, critical=True))
    a(Check("equity_erosion", "Equity trend", "leverage", "risk", 6,
            lambda m: (NA if m.g("equity_cagr3") is None else
                       (PASS if m.g("equity_cagr3") >= -0.15 else FAIL),
                       f"3y equity CAGR {pct(m.g('equity_cagr3'))} (>= -15%)"),
            critical=True))
    a(Check("int_cover", "Interest coverage", "leverage", "risk", 10,
            lambda m: (_thr(m.g("interest_coverage"), 3.0),
                       f"Interest coverage {num(m.g('interest_coverage'))}x (> 3)"),
            skip_books={"financials"}))
    def int_floor(m):
        cov = m.g("interest_coverage")
        if cov is None:
            return NA, "Interest coverage n/a"
        msg = f"Interest coverage {num(cov)}x (floor 1.5)"
        if cov >= 1.5:
            return PASS, msg
        oc, cc = m.g("opinc_coverage"), m.g("cash_coverage")
        if m.g("coverage_waived"):
            return WATCH, (f"EBIT coverage {num(cov)}x is under the 1.5x floor, waived: operating "
                           f"income covers interest {num(oc)}x and cash flow {num(cc)}x -- the EBIT "
                           f"shortfall is charges below operating income, not an inability to pay")
        if oc is not None and cc is not None:
            msg += f"; operating income {num(oc)}x, cash {num(cc)}x -- waiver needs both >= 1.5"
        return FAIL, msg

    a(Check("int_cover_crit", "Interest coverage floor", "leverage", "risk", 0,
            int_floor, critical=True, skip_books={"financials"}))
    a(Check("de", "Debt / equity", "leverage", "risk", 6,
            lambda m: (_thr(m.g("debt_to_equity"), 1.5, higher_good=False),
                       f"Debt/Equity {num(m.g('debt_to_equity'))} (< 1.5)"),
            skip_books={"financials"}))
    def nd_scored(m):
        limit = 4.5 if m.rulebook == "capital_intensive" else 3.0
        neg, nd = _negative_ebitda_state(m)
        if neg is not None:
            return neg
        return (_thr(nd, limit, higher_good=False),
                f"Net debt/EBITDA {num(nd)}x (< {limit})")

    a(Check("nd_ebitda", "Net debt / EBITDA", "leverage", "risk", 6,
            nd_scored, skip_books={"financials"}))
    def nd_ceiling(m):
        """Leverage is fatal when it cannot be serviced, not at a round number.

        Teva sits at 5.11x on GAAP EBITDA -- barely over a 5.0 line -- while
        covering its interest comfortably and generating cash. Tripping AVOID on
        that boundary would condemn every levered turnaround, so the ceiling is
        paired with a servicing test.
        """
        ceiling = 6.0 if m.rulebook == "capital_intensive" else 5.0
        nd, cov = m.g("nd_ebitda"), m.g("coverage_effective")
        tag = " (operating-income/cash-backed)" if m.g("coverage_waived") else ""
        neg, _ = _negative_ebitda_state(m)
        if neg is not None:
            return neg
        if nd is None:
            return NA, "Net debt/EBITDA n/a"
        msg = f"Net debt/EBITDA {num(nd)}x (ceiling {ceiling})"
        if nd <= ceiling:
            return PASS, msg
        # The coverage waiver is bounded. Paired at the same 1.5x floor the
        # dedicated coverage gate uses -- pairing at 3.0 would double-penalize the
        # 1.5-3.0 band where levered turnarounds live -- but only up to 1.5x the
        # ceiling. Beyond that, leverage is fatal whatever today's coverage says:
        # G City covers 1.66x at 13.4x net debt, which leaves no margin for a rate
        # reset or an EBITDA dip.
        hard_ceiling = ceiling * 1.5
        if nd > hard_ceiling and not (cov is not None and cov >= 8.0):
            return FAIL, (msg + f", beyond the {num(hard_ceiling,1)}x hard limit "
                                f"-- coverage of {num(cov)}x cannot absorb a shock")
        if nd > hard_ceiling:
            # Exceptional coverage overrides the hard limit. Camtek carries
            # low-coupon converts: high debt against EBITDA, but 26x coverage.
            return WATCH, (msg + f" -- beyond the hard limit, but interest "
                                 f"coverage of {num(cov)}x{tag} is exceptional")
        if cov is not None and cov >= 1.5:
            return WATCH, (msg + f" -- above ceiling but interest coverage "
                                 f"{num(cov)}x{tag} still services it")
        return FAIL, msg + f", interest coverage {num(cov)}x cannot service it"

    a(Check("nd_ebitda_crit", "Net debt / EBITDA ceiling", "leverage", "risk", 0,
            nd_ceiling, critical=True, skip_books={"financials"}))
    a(Check("tangible_book", "Tangible book value", "leverage", "risk", 6,
            lambda m: (NA if m.g("tangible_book") is None else
                       (PASS if m.g("tangible_book") > 0 else FAIL),
                       f"Tangible book value {money(m.g('tangible_book'))} {m.fin_ccy}"),
            skip_books={"financials"}))

    # ---------------- Liquidity (risk) --------------------------------
    def quick_check(m):
        q, cfocl = m.g("quick_ratio"), m.g("cfo_over_cl")
        if q is None and cfocl is None:
            return NA, "Quick ratio n/a"
        if q is not None and q > 1.0:
            return PASS, f"Quick ratio {num(q)} (> 1.0)"
        if cfocl is not None and cfocl > 0.5:
            return WATCH, (f"Quick ratio {num(q)} below 1.0, waived -- "
                           f"CFO covers {pct(cfocl)} of current liabilities (> 50%)")
        return FAIL, f"Quick ratio {num(q)} (< 1.0) and CFO/CL {num(cfocl)} (< 0.5)"

    def current_check(m):
        c, ic = m.g("current_ratio"), m.g("interest_coverage")
        if c is None and ic is None:
            return NA, "Current ratio n/a"
        if c is not None and c > 1.2:
            return PASS, f"Current ratio {num(c)} (> 1.2)"
        if ic is not None and ic > 15:
            return WATCH, (f"Current ratio {num(c)} below 1.2, waived -- "
                           f"interest coverage {num(ic)}x (> 15)")
        return FAIL, f"Current ratio {num(c)} (< 1.2), no fortress waiver"

    a(Check("quick", "Quick ratio", "liquidity", "risk", 10, quick_check,
            skip_books={"financials"}))
    a(Check("current", "Current ratio", "liquidity", "risk", 8, current_check,
            skip_books={"financials"}))
    a(Check("cfo_reversal", "Operating cash flow", "liquidity", "risk", 12,
            lambda m: (NA if m.g("cfo") is None else
                       (PASS if m.g("cfo") > 0 else FAIL),
                       f"CFO {money(m.g('cfo'))} {m.fin_ccy} over {m.ttm_label}"),
            # A bank's operating cash flow is loan and deposit movements, not earnings:
            # JPMorgan reported -$84B and was AVOIDed on it. Every other cash-flow check
            # already skips financials for this reason; this critical one had been missed.
            critical=True, skip_books={"financials"}))
    def time_to_live(m):
        """Months of cash left at current TTM burn, assuming no new financing.

        The critical floor stays at 12 months (the pre-existing 4-quarter bar) so
        this does not silently loosen AVOID behaviour already calibrated against
        the 38-company regression set. 12-18 months is a new WATCH band: an early
        warning that a raise is likely within the next year or two, useful for
        growth/biotech names that are not yet in going-concern territory but are
        headed there, without changing whether they AVOID today.
        """
        months = m.g("runway_months")
        if months is None:
            return NA, "Time to live n/a (not burning cash on a CFO basis, or no cash data)"
        msg = f"Time to live: {num(months, 1)} months of cash at current burn, no new financing"
        if months < 12:
            return FAIL, msg + " (critical if < 12)"
        if months < 18:
            return WATCH, msg + " -- a raise is likely within 1-2 years (12-18 month band)"
        return PASS, msg + " (>= 18)"

    a(Check("runway", "Time to live", "liquidity", "risk", 10, time_to_live,
            critical=True, skip_books={"financials"}))

    # ---------------- Earnings quality (risk) -------------------------
    a(Check("accruals", "Accruals ratio", "earnings_quality", "risk", 8,
            lambda m: (_thr(m.g("accruals"), 0.10, higher_good=False),
                       f"Accruals (NI-CFO)/assets {pct(m.g('accruals'))} (<= 10%)")))
    def div_trap(m):
        """The critical AVOID gate. Evaluated with NO early return on low yield --
        a 7% yield paid entirely out of losses used to clear this untouched, because
        the old version returned PASS as soon as yield <= 8% without ever looking at
        whether the payment was funded. Loss-funded is checked FIRST, at any yield,
        before the high-yield-plus-high-payout trap is even considered.
        """
        y, payout, ni = m.g("div_yield"), m.g("cash_payout"), m.g("net_income")
        paid = abs(m.g("dividends_paid") or 0)
        if y is None:
            return NA, "Dividend yield n/a"
        if paid <= 0:
            return PASS, "No dividend paid"
        failure = None
        if ni is not None and ni <= 0:
            failure = (f"Yield {pct(y)} paid out of negative earnings "
                       f"(net income {money(ni)}) -- unfunded distribution")
        elif y > 0.08 and payout is not None and payout > 1.2:
            failure = (f"Yield {pct(y)} with cash payout {pct(payout)} "
                       f"-- distribution exceeds earnings (trap: >8% and >120%)")
        if failure is None:
            return PASS, f"Yield {pct(y)} with cash payout {pct(payout)} (covered)"

        # Cash-backed waiver. Both tests above read GAAP net income, which one-off charges can
        # push negative at a company whose cash flow covers the dividend many times over
        # (Gilead: net income -$3.9B, free cash flow +$13.8B, dividend $4.1B). The waiver needs
        # free cash flow to cover the dividend AND to have been positive in at least 3 of the last
        # 4 years, so one year's windfall cannot clear anyone. Scoped to operating companies:
        # for BDCs, asset managers and REITs both payout-vs-earnings and free cash flow are
        # unreliable (a BDC's operating cash flow is portfolio purchases and sales), so those
        # keep the strict test until they have a rulebook of their own.
        fcf, yrs, ok_yrs = m.g("fcf"), m.g("fcf_years_checked") or 0, m.g("fcf_positive_years") or 0
        if (m.rulebook not in ("financials", "reit") and fcf is not None and fcf >= paid
                and yrs >= 3 and ok_yrs >= 3):
            return WATCH, (f"{failure} -- waived: free cash flow {money(fcf)} covers the "
                           f"{money(paid)} dividend {fcf / paid:.1f}x and was positive in "
                           f"{ok_yrs} of {yrs} years, so the net-income test is distorted by "
                           f"charges, not by an unfunded payout")
        return FAIL, failure

    a(Check("div_trap", "Dividend sustainability", "earnings_quality", "risk", 8,
            div_trap, critical=True))
    a(Check("goodwill", "Goodwill load", "earnings_quality", "risk", 5,
            lambda m: (_thr(m.g("goodwill_ratio"), 0.40, higher_good=False),
                       f"Goodwill {pct(m.g('goodwill_ratio'))} of assets (<= 40%)"),
            section="deep", skip_books={"financials"}))
    a(Check("sbc_load", "Stock comp load", "earnings_quality", "risk", 5,
            lambda m: (_thr(m.g("sbc_cfo"), 0.30, higher_good=False),
                       f"Stock comp {pct(m.g('sbc_cfo'))} of CFO (<= 30%)"),
            section="deep"))
    # Skipped for banks: their "receivables" are the loan book, so growth there is
    # lending activity, not channel stuffing.
    a(Check("recv_div", "Receivables vs revenue", "earnings_quality", "risk", 5,
            lambda m: _divergence(m, "recv_hist", "Receivables"),
            section="deep", skip_books={"financials"}))
    a(Check("inv_div", "Inventory vs revenue", "earnings_quality", "risk", 4,
            lambda m: _divergence(m, "inv_hist", "Inventory"),
            section="deep", skip_books={"financials"}))
    a(Check("cash_vs_debt", "Cash vs current debt", "earnings_quality", "risk", 3,
            lambda m: (NA if (m.g("cash") is None or m.g("current_debt") is None)
                       else (PASS if m.g("cash") >= m.g("current_debt") else FAIL),
                       f"Cash {money(m.g('cash'))} vs current debt "
                       f"{money(m.g('current_debt'))}"),
            section="deep", skip_books={"financials"}))

    def altman_check(m):
        z, zone, label = altman(m)
        if z is None:
            return NA, f"Altman Z-score {label}"
        msg = f"Altman Z'' {num(z)} ({zone}; distress < 1.8)"
        # Only the distress zone fails. Z'' leans on book equity, so buyback-heavy
        # companies can score low without being in distress: scored, not a gate.
        return (FAIL if zone == "distress" else (WATCH if zone == "grey" else PASS)), msg

    a(Check("altman", "Altman Z-score", "leverage", "risk", 6, altman_check,
            skip_books={"financials", "pre_revenue"}))

    def beneish_check(m):
        score, verdict = beneish(m)
        if score is None:
            return NA, f"Beneish M-score {verdict}"
        return (FAIL if score > -1.78 else PASS), \
            f"Beneish M-score {num(score)} ({verdict}; flag > -1.78)"

    a(Check("beneish", "Beneish M-score", "earnings_quality", "risk", 5, beneish_check,
            section="deep", skip_books={"pre_revenue"}))

    def div_funding(m):
        """A dividend funded by losses or by more than the company earns.

        Separate from the div_trap AVOID gate on purpose. That gate needs a >8% yield
        AND a >120% payout, so a 7% yield paid out of losses cleared it untouched.
        This scores the funding regardless of yield, but is not critical: a payout above
        earnings is routine for REITs (Realty Income runs ~236% of net income, because
        depreciation is not a cash cost), so making it a gate would flag a sound REIT.
        """
        paid = abs(m.g("dividends_paid") or 0)
        ni, payout = m.g("net_income"), m.g("cash_payout")
        if paid <= 0 or ni is None:
            return NA, "No dividend paid"
        if ni <= 0:
            return FAIL, (f"Dividend of {money(paid)} {m.fin_ccy} paid while net income "
                          f"is {money(ni)}")
        if m.rulebook == "reit":
            return PASS, (f"Dividend payout {pct(payout)} of net income "
                          f"(REIT: judged on FFO, not scored here)")
        return (FAIL if payout > 1.0 else PASS), \
            f"Dividend payout {pct(payout)} of net income (<= 100%)"

    a(Check("div_funding", "Dividend funding", "earnings_quality", "risk", 6, div_funding,
            skip_books={"financials", "pre_revenue"}))

    def share_div_check(m):
        div = m.g("share_divergence")
        if div is None:
            return NA, "Share count divergence n/a"
        msg = (f"Statement vs. live share count differs by {pct(div)} -- "
              f"either real recent dilution/buybacks or a stale quote, and every "
              f"multiple in this report is built on one of these two counts")
        if div > 0.10:
            return FAIL, msg
        return PASS, msg

    a(Check("share_divergence", "Share count reconciliation", "capital", "quality", 4,
            share_div_check))

    def gross_margin_trend(m):
        """Direction, not level. A flat floor would fail Costco (12.8% GM, thin
        margin by design, high quality) exactly the way an absolute net-margin
        floor would -- see the profitability pillar's own note on that. Margin
        COMPRESSION is the actual pricing-power signal, and it is self-relative
        so it means the same thing whether the business runs on 13% or 90% gross
        margin.
        """
        gh = m.g("gp_hist")
        rh = m.g("revenue_hist")
        if len(gh) < 2 or gh[0] is None or gh[1] is None or not rh[0] or not rh[1]:
            return NA, "Gross margin trend n/a"
        gm_now = safe_div(gh[0], rh[0])
        gm_prev = safe_div(gh[1], rh[1])
        if gm_now is None or gm_prev is None:
            return NA, "Gross margin trend n/a"
        delta = gm_now - gm_prev
        msg = f"Gross margin {pct(gm_now)}, {'+' if delta >= 0 else ''}{delta*100:.1f}pp YoY"
        return (FAIL if delta < -0.02 else PASS), msg

    a(Check("gross_margin_trend", "Gross margin trend", "profitability", "quality", 4,
            gross_margin_trend, skip_books={"financials"}))
    return C


def _divergence(m, hist_key, label):
    h = m.g(hist_key)
    rh = m.g("revenue_hist")
    if not h or h[0] is None or not h[1] or rh[0] is None or not rh[1]:
        return NA, f"{label} trend n/a"
    g_item = (h[0] - h[1]) / abs(h[1])
    g_rev = (rh[0] - rh[1]) / abs(rh[1])
    gap = g_item - g_rev
    status = FAIL if gap > 0.15 else PASS
    return status, (f"{label} {pct(g_item)} vs revenue {pct(g_rev)} "
                    f"(gap {pct(gap)}, flag > 15pp)")


# --------------------------------------------------------------------------
# Composite scores
# --------------------------------------------------------------------------
def piotroski(m):
    d, drop = m.data, []
    pts, total = 0, 0

    def add(cond, name, applicable=True):
        nonlocal pts, total
        if not applicable or cond is None:
            drop.append(name)
            return
        total += 1
        if cond:
            pts += 1

    ni, cfo, ta = d["net_income"], d["cfo"], d["total_assets"]
    ah, nih, ch = d["assets_hist"], d["ni_hist"], d["cfo_hist"]
    roa_now = safe_div(ni, ta)
    roa_prev = safe_div(nih[1], ah[1]) if len(ah) > 1 and ah[1] else None

    add(None if ni is None else ni > 0, "ROA positive")
    add(None if cfo is None else cfo > 0, "CFO positive")
    add(None if (roa_now is None or roa_prev is None) else roa_now > roa_prev,
        "ROA improving")
    add(None if (cfo is None or ni is None) else cfo > ni, "Accruals")

    ltd, ltdh = d["long_term_debt"], d["ltd_hist"]
    lev_now = safe_div(ltd, ta)
    lev_prev = safe_div(ltdh[1], ah[1]) if len(ltdh) > 1 and ah[1] else None
    add(None if (lev_now is None or lev_prev is None) else lev_now <= lev_prev,
        "Leverage")

    is_fin = m.rulebook == "financials"
    cr_now = d["current_ratio"]
    cr_prev = safe_div(d["ca_hist"][1], d["cl_hist"][1]) \
        if len(d["ca_hist"]) > 1 and d["cl_hist"][1] else None
    add(None if (cr_now is None or cr_prev is None) else cr_now >= cr_prev,
        "Current ratio", applicable=not is_fin)

    sh = d["shares_hist"]
    add(None if (sh[0] is None or not sh[1]) else sh[0] <= sh[1] * 1.01,
        "No dilution")

    gm_now = d["gross_margin"]
    gm_prev = safe_div(d["gp_hist"][1], d["revenue_hist"][1]) \
        if len(d["gp_hist"]) > 1 and d["revenue_hist"][1] else None
    add(None if (gm_now is None or gm_prev is None) else gm_now >= gm_prev,
        "Gross margin", applicable=not is_fin)

    at_now = safe_div(d["revenue"], ta)
    at_prev = safe_div(d["revenue_hist"][1], ah[1]) \
        if len(ah) > 1 and ah[1] else None
    add(None if (at_now is None or at_prev is None) else at_now >= at_prev,
        "Asset turnover")

    return pts, total, drop


def altman(m):
    if m.rulebook in ("financials", "pre_revenue"):
        return None, None, "not applicable"
    d = m.data
    ta = d["total_assets"]
    if not ta:
        return None, None, "insufficient data"
    x1 = safe_div(d["working_capital"] if d["working_capital"] is not None
                  else (d["current_assets"] or 0) - (d["current_liabilities"] or 0), ta)
    x2 = safe_div(d["retained_earnings"], ta)
    x3 = safe_div(d["ebit"], ta)
    x4 = safe_div(d["equity"], d["total_liabilities"])
    if None in (x1, x2, x3, x4):
        return None, None, "insufficient data"
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "distress" if z < 1.8 else ("grey" if z < 3.0 else "safe")
    return z, zone, "Z''"


def beneish(m):
    """Beneish M-Score, eight-variable form. Returns (score, verdict).

    Every index is the published formula. When an input is missing the index falls back
    to the neutral 1.0 -- but that is recorded in the diagnostics rather than done
    silently, because a score built on defaulted variables is weaker than it looks.
    """
    if m.rulebook == "pre_revenue":
        return None, "not applicable (near-zero revenue makes SGI/GMI undefined)"
    d = m.data
    rh, gph, rch = d["revenue_hist"], d["gp_hist"], d["recv_hist"]
    ah, dph, ltdh = d["assets_hist"], d["dep_hist"], d["ltd_hist"]
    cah, clh = d["ca_hist"], d["cl_hist"]
    ppeh, sgah = d["ppe_hist"], d["sga_hist"]
    if len(rh) < 2 or not rh[1] or rh[0] is None:
        return None, "insufficient data"
    defaulted = []

    def index(name, value):
        if value is None:
            defaulted.append(name)
            return 1.0
        return value

    try:
        dsri = safe_div(safe_div(rch[0], rh[0]), safe_div(rch[1], rh[1]))
        gmi = safe_div(safe_div(gph[1], rh[1]), safe_div(gph[0], rh[0]))
        sgi = safe_div(rh[0], rh[1])
        if any(v is None for v in (dsri, gmi, sgi)):
            return None, "insufficient data"

        # AQI: non-current, non-PPE assets as a share of total assets, year over year.
        def soft_assets(i):
            if cah[i] is None or ppeh[i] is None or not ah[i]:
                return None
            return 1 - (cah[i] + ppeh[i]) / ah[i]
        sa0, sa1 = soft_assets(0), soft_assets(1)
        aqi = index("AQI", safe_div(sa0, sa1) if sa0 is not None and sa1 else None)

        # SGAI: SG&A intensity, year over year.
        sg0, sg1 = sgah[0], sgah[1]
        sgai = index("SGAI", safe_div(safe_div(sg0, rh[0]), safe_div(sg1, rh[1]))
                     if sg0 is not None and sg1 is not None else None)

        # DEPI: depreciation rate, prior year over current year.
        def dep_rate(i):
            if dph[i] is None or ppeh[i] is None or (dph[i] + ppeh[i]) == 0:
                return None
            return dph[i] / (dph[i] + ppeh[i])
        dr0, dr1 = dep_rate(0), dep_rate(1)
        depi = index("DEPI", safe_div(dr1, dr0) if dr0 and dr1 is not None else None)

        # LVGI: (current liabilities + long-term debt) over total assets, year over year.
        def leverage(i):
            if clh[i] is None or ltdh[i] is None or not ah[i]:
                return None
            return (clh[i] + ltdh[i]) / ah[i]
        lv0, lv1 = leverage(0), leverage(1)
        lvgi = index("LVGI", safe_div(lv0, lv1) if lv0 is not None and lv1 else None)

        # TATA uses the cash-flow definition (net income - CFO) / assets, the standard
        # alternative to the balance-sheet accrual build.
        tata = d["accruals"] or 0.0
        mscore = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
                  + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
        verdict = "manipulation flag" if mscore > -1.78 else "clean"
        if defaulted:
            note("Beneish variables defaulted to 1.0 (missing inputs): " + ", ".join(defaulted))
            verdict += f", {len(defaulted)} of 8 inputs defaulted"
        return mscore, verdict
    except Exception:
        return None, "insufficient data"


def ccc_waiver(m):
    """Return (waived, message) for the liquidity pillar."""
    d = m.data
    if d.get("ccc") is None:
        return False, None
    if d["ccc"] > 0:
        return False, None
    # A solvency-impaired company does not earn a liquidity pass. AMC shows a
    # negative CCC (cinema-goers pay upfront) alongside negative equity and 0.02x
    # coverage -- waiving its liquidity pillar would be perverse.
    if (d.get("equity") is not None and d["equity"] <= 0 and not neg_equity_waiver(m)[0]) or \
       (d.get("interest_coverage") is not None and d["interest_coverage"] < 1.5):
        return False, (f"Cash conversion cycle {num(d['ccc'],0)} days is negative, "
                       f"but solvency is impaired -- no liquidity waiver applied")
    cfo_ok = (d.get("cfo") or 0) > 0
    dpo_ok = d.get("dpo_growth") is None or d["dpo_growth"] <= 0.30
    if cfo_ok and dpo_ok:
        return True, (f"Cash conversion cycle {num(d['ccc'],0)} days -- paid before "
                      f"suppliers, liquidity pillar waived")
    return False, (f"Cash conversion cycle {num(d['ccc'],0)} days is negative but "
                   f"driven by payable stretching (DPO {pct(d.get('dpo_growth'))} YoY, "
                   f"CFO {money(d.get('cfo'))}) -- not a strength")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def run_checks(m, checks, section_filter):
    results = []
    for c in checks:
        if not c.applies(m.rulebook):
            continue
        if c.section not in section_filter:
            continue
        try:
            status, msg = c.fn(m)
        except Exception as e:
            status, msg = NA, f"{c.label} errored ({type(e).__name__})"
        results.append({"id": c.cid, "label": c.label, "pillar": c.pillar,
                        "side": c.side, "weight": c.weight, "critical": c.critical,
                        "section": c.section, "status": status, "message": msg})
    return results


def score(m, results, liquidity_waived):
    q_earn = {k: 0.0 for k in QUALITY_PILLARS}
    q_poss = {k: 0.0 for k in QUALITY_PILLARS}
    r_earn = {k: 0.0 for k in RISK_PILLARS}
    r_poss = {k: 0.0 for k in RISK_PILLARS}

    for r in results:
        if r["weight"] == 0 or r["status"] == NA:
            continue
        if r["side"] == "quality":
            q_poss[r["pillar"]] += r["weight"]
            if r["status"] in (PASS, WATCH):
                q_earn[r["pillar"]] += r["weight"]
        else:
            if r["pillar"] == "liquidity" and liquidity_waived:
                continue
            r_poss[r["pillar"]] += r["weight"]
            if r["status"] == FAIL:
                r_earn[r["pillar"]] += r["weight"]
            elif r["status"] == WATCH:
                # A waived check is not the same as a clean pass -- it means a real
                # threshold was crossed and a mitigating factor covers it (TEVA's
                # coverage, Camtek's 26x interest coverage, an Altman grey zone).
                # Crediting it the same as PASS (zero risk) was the bug: a WATCH
                # used to lower Risk exactly as much as a clean PASS. Half credit
                # keeps the mitigation's benefit while still counting the exposure.
                r_earn[r["pillar"]] += r["weight"] * 0.5

    def roll(earn, poss, pillars):
        total, detail = 0.0, {}
        for p, maxpts in pillars.items():
            if poss[p] <= 0:
                detail[p] = None
                continue
            frac = earn[p] / poss[p]
            pts = frac * maxpts
            detail[p] = (pts, maxpts)
            total += pts
        avail = sum(mx for p, mx in pillars.items() if detail.get(p))
        if avail <= 0:
            return None, detail
        return round(total / avail * 100), detail

    quality, qdetail = roll(q_earn, q_poss, QUALITY_PILLARS)
    risk, rdetail = roll(r_earn, r_poss, RISK_PILLARS)
    return quality, risk, qdetail, rdetail


def band_quality(s):
    if s is None:
        return "n/a"
    return ("Strong" if s >= 80 else "Solid" if s >= 65 else
            "Mixed" if s >= 50 else "Weak" if s >= 35 else "Poor")


def band_risk(s):
    if s is None:
        return "n/a"
    return ("Low" if s < 25 else "Moderate" if s < 50 else
            "Elevated" if s < 75 else "Severe")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def _has_rows(x):
    return x is not None and not getattr(x, "empty", True)


def _info_ok(x):
    # A record with no sector is as unusable as an empty one: the sector picks the rulebook.
    return bool(x) and bool(x.get("sector"))


# section -> (how to read it from a Ticker, how to tell it arrived, value to use on failure)
CORE_SECTIONS = {
    "info": (lambda t: t.info, _info_ok, {}),
    "income_stmt": (lambda t: t.income_stmt, _has_rows, None),
    "balance_sheet": (lambda t: t.balance_sheet, _has_rows, None),
    "cashflow": (lambda t: t.cashflow, _has_rows, None),
}


def fetch_core(symbol, tk):
    """Fetch the sections a score cannot be trusted without. Returns (sections, missing).

    Anything missing is retried together after one RETRY_WAIT_SECONDS wait per round, using a
    fresh Ticker each time (a reused one can hand back the empty answer it already cached).

    A caller's pre-fetched info, or income_stmt reused from resolve()'s existence probe, is
    checked ONCE here, before any retry -- never injected into the retry loop itself, which would
    defeat the point of building a fresh Ticker each round. A bad or missing prefetch/probe value
    is simply dropped and falls through to the normal fresh-Ticker fetch/retry path below.
    """
    got = {}
    prefetched_info = load_prefetched_info()
    if prefetched_info is not None and _info_ok(prefetched_info):
        got["info"] = prefetched_info
    probed_fin = _PROBE_CACHE.pop(symbol, None)
    if probed_fin is not None and _has_rows(probed_fin):
        note("income_stmt: reused from ticker-resolution probe (skipped duplicate fetch)")
        got["income_stmt"] = probed_fin
    for attempt in range(MAX_RETRIES + 1):
        pending = [k for k in CORE_SECTIONS if k not in got]
        if attempt:
            note(f"missing {', '.join(pending)}; waiting {RETRY_WAIT_SECONDS}s before "
                 f"retry {attempt}/{MAX_RETRIES}")
            time.sleep(RETRY_WAIT_SECONDS)
            tk = yf.Ticker(symbol)
        for k in pending:
            read, ok, default = CORE_SECTIONS[k]
            value = fetch(k, lambda: read(tk), default)
            if ok(value):
                got[k] = value
        if len(got) == len(CORE_SECTIONS):
            break
    return got, [k for k in CORE_SECTIONS if k not in got]


def fail_closed(user_input, symbol, chain, missing):
    """Refuse to score: reason to the log, stderr and stdout, an error JSON, sentinel scores.

    Exit code 2 ("unscoreable") is what the screener already understands, and it reads the first
    stderr line as the reason. The error JSON gets its own file name so it can never overwrite a
    good report from earlier the same day, and avoid is null, never False: an unknown is not a
    clean bill of health.
    """
    reason = (f"Required data missing for {symbol} after {MAX_RETRIES} retries "
              f"{RETRY_WAIT_SECONDS}s apart: {', '.join(missing)}. Yahoo returned nothing for "
              f"these, usually a rate limit, so retry later. Not scored: guessing from partial "
              f"data can turn a failing company into a perfect one.")
    now = dt.datetime.now(TLV_TZ)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{now.isoformat(timespec='seconds')} | {symbol} | {reason} | "
                     f"notes: {'; '.join(DIAG['notes']) or 'none'}\n")
    except OSError:
        pass                               # an unwritable log must not hide the failure itself
    print(reason, file=sys.stderr)
    for n in DIAG["notes"]:
        print(f"  {n}", file=sys.stderr)
    payload = {
        "status": "error", "error": reason, "missing": missing,
        "input": user_input, "resolution_chain": chain, "symbol": symbol,
        "quality": SENTINEL_SCORE, "risk": SENTINEL_SCORE, "avoid": None,
        "fetched_at": now.isoformat(timespec="seconds"), "diagnostics": DIAG,
    }
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        epath = REPORTS_DIR / f"{file_key(symbol)}_{dt.date.today().isoformat()}.error.json"
        epath.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except OSError:
        epath = None
    print(f"ERROR -- {reason}")
    print(f"QUALITY {SENTINEL_SCORE} / 100      RISK {SENTINEL_SCORE} / 100      "
          f"(sentinel values: nothing was scored)")
    if epath:
        print(f"JSON: {epath}")
    return 2


def main(argv):
    if len(argv) != 2:
        print("usage: fundamental_check.py <TICKER|TASE_NUMBER>", file=sys.stderr)
        print("  exactly one argument, no flags", file=sys.stderr)
        return 2

    user_input = argv[1]
    symbol, chain = resolve(user_input)
    if not symbol:
        print(f"Could not resolve '{user_input}'. Chain: {' -> '.join(chain)}",
              file=sys.stderr)
        for n in DIAG["notes"]:
            print(f"  {n}", file=sys.stderr)
        if user_input.strip().isdigit():
            print("  Yahoo's search has no Tel Aviv equity under that number. Yahoo does not index\n"
                  "  every security it serves: some (Camtek, 1095264) fail as a number although\n"
                  "  their ticker works. Find the company on finance.yahoo.com and run this tool\n"
                  "  with its ticker instead (e.g. fundamental_check.py NXGN-M.TA).", file=sys.stderr)
        return 2

    tk = yf.Ticker(symbol)
    core, missing = fetch_core(symbol, tk)
    if missing:
        return fail_closed(user_input, symbol, chain, missing)
    info, fin, bs, cf = core["info"], core["income_stmt"], core["balance_sheet"], core["cashflow"]
    qfin = fetch("quarterly_income_stmt", lambda: tk.quarterly_income_stmt)
    qcf = fetch("quarterly_cashflow", lambda: tk.quarterly_cashflow)
    hist = load_prefetched_history()
    if hist is None:
        hist = fetch("history", lambda: tk.history(period="3mo"))
    # calendar (next earnings date) and news are purely informational --
    # displayed in the report but never scored into Quality/Risk (see README) --
    # so a caller that doesn't render those sections can skip fetching them.
    if os.environ.get("FUNDCHECK_SKIP_CALENDAR"):
        calendar = {}
    else:
        calendar = fetch("calendar", lambda: tk.calendar, {}) or {}
    fetched_at = dt.datetime.now(TLV_TZ)

    m = build_metrics(symbol, tk, info, fin, qfin, bs, cf, qcf, hist)

    # Recent headlines, and whether one of them is a signed deal price pinning the stock.
    # `pinned()` compares against m.price_usd, so only pass a price when the quote itself is
    # USD -- a TASE name quoted in ILS/ILA has no USD price to compare a $-denominated deal
    # figure against, and passing one in would produce a confident, wrong answer rather than no
    # answer. Never allowed to fail the check: any network/parsing problem is news.py's own
    # concern (see fetch_headlines), not this script's.
    news_price = m.price_usd if m.quote_ccy == "USD" else None
    if os.environ.get("FUNDCHECK_SKIP_NEWS"):
        news_info = {"headlines": [], "classified": None}
    else:
        try:
            news_info = news.annotate(symbol, news_price)
        except Exception as e:
            note(f"news unavailable ({type(e).__name__})")
            news_info = {"headlines": [], "classified": None}

    earnings = next_earnings(calendar)

    checks = build_checks()

    # ---- tradability gate (critical, evaluated outside the pillars) ----
    trade_flags = []
    if m.price_usd is not None and m.price_usd < 2:
        trade_flags.append(f"Price ${num(m.price_usd)} below $2")
    if m.mcap_usd is not None and m.mcap_usd < 100e6:
        trade_flags.append(f"Market cap ${money(m.mcap_usd)} below $100M")
    if m.dollar_vol is not None and m.dollar_vol < 1e6:
        trade_flags.append(f"30d median dollar volume ${money(m.dollar_vol)} below $1M")

    waived, ccc_msg = ccc_waiver(m)

    sanity = run_checks(m, checks, {"sanity"})
    critical_failed = [r for r in sanity if r["critical"] and r["status"] == FAIL]
    avoid = bool(critical_failed) or bool(trade_flags)

    deep = []
    deep_skipped = avoid
    if not deep_skipped:
        deep = run_checks(m, checks, {"deep"})
        critical_failed += [r for r in deep if r["critical"] and r["status"] == FAIL]
        avoid = avoid or bool(critical_failed)

    results = sanity + deep
    quality, risk, qdetail, rdetail = score(m, results, waived)

    # A critical failure IS severe risk by definition. Without this floor the
    # short-circuit works against us: skipping the Deep Dive empties the earnings
    # quality pillar, which DEFLATES the Risk score for exactly the worst names.
    n_crit = len(critical_failed) + len(trade_flags)
    if avoid and risk is not None:
        risk = max(risk, min(100, 60 + 10 * n_crit))

    evaluated = sum(1 for r in results if r["status"] != NA)
    coverage = evaluated / len(results) if results else 0

    # composites
    pio_pts, pio_total, pio_drop = piotroski(m)
    z, zone, zlabel = altman(m)
    mscore, mverdict = (None, "skipped") if deep_skipped else beneish(m)

    # ---- render ---------------------------------------------------------
    out = []
    if avoid:
        reasons = len(critical_failed) + len(trade_flags)
        out.append(f"AVOID -- {reasons} critical check(s) failed")
    chain_str = " -> ".join(chain)
    out.append(f"{m.name} -- input {chain_str}")
    out.append(f"{m.sector or 'sector n/a'} / {m.industry or 'industry n/a'}")
    fy = f"{m.fy_years[-1]}..{m.fy_years[0]}" if m.fy_years else "n/a"
    out.append(f"Rulebook: {m.rulebook} ({m.rulebook_basis}) | FY {fy} | "
               f"Evaluated {evaluated}/{len(results)} checks")
    out.append("")
    if coverage < 0.5:
        out.append(f"INSUFFICIENT DATA -- only {coverage*100:.0f}% of checks evaluable")
        print("\n".join(out))
        return 2
    out.append(f"QUALITY {quality} / 100  ({band_quality(quality)})"
               f"      RISK {risk} / 100  ({band_risk(risk)})")
    if deep_skipped:
        out.append("Risk computed from Sanity Check inputs only (Deep Dive skipped).")
    out.append("")

    def emit(section_results, title):
        out.append(f"--- {title} ---")
        greens = [r for r in section_results if r["status"] == PASS]
        reds = [r for r in section_results if r["status"] == FAIL]
        watches = [r for r in section_results if r["status"] == WATCH]
        nas = [r for r in section_results if r["status"] == NA]
        greens.sort(key=lambda r: -r["weight"])
        reds.sort(key=lambda r: -(r["weight"] + (100 if r["critical"] else 0)))
        if greens:
            out.append("GREEN FLAGS")
            for r in greens:
                out.append(f"  + {r['message']}")
        if reds:
            out.append("RED FLAGS")
            for r in reds:
                tag = " [CRITICAL]" if r["critical"] else ""
                out.append(f"  - {r['message']}{tag}")
        if watches:
            out.append("WATCH")
            for r in watches:
                out.append(f"  ! {r['message']}")
        if nas:
            out.append("NOT APPLICABLE / UNAVAILABLE")
            out.append("  ~ " + ", ".join(r["label"] for r in nas))
        out.append("")

    emit(sanity, "SANITY CHECK")

    if trade_flags:
        out.append("TRADABILITY [CRITICAL]")
        for f in trade_flags:
            out.append(f"  - {f}")
        out.append("")

    extra = []
    if m.g("rnd_intensity") and m.g("rnd_intensity") > 0.15:
        extra.append(f"! R&D is {pct(m.g('rnd_intensity'))} of revenue -- operating "
                     f"margin is depressed by reinvestment, not weak economics")
    if m.g("revenue_fall_note"):
        extra.append("! " + m.g("revenue_fall_note"))
    if ccc_msg:
        extra.append(("! " if waived else "- ") + ccc_msg)
    if m.g("roe") and m.g("roic") and m.g("roe") > m.g("roic") * 2:
        extra.append(f"! ROE {pct(m.g('roe'))} far exceeds ROIC {pct(m.g('roic'))} "
                     f"-- leverage is inflating the headline return")
    if m.g("shareholder_yield") is not None:
        extra.append(f"- Shareholder yield {pct(m.g('shareholder_yield'))} "
                     f"(dividends + buybacks / market cap) -- context only, not scored")
    if extra:
        out.append("CONTEXT")
        out.extend("  " + e for e in extra)
        out.append("")

    out.append("PILLARS")
    qline = "  Quality  " + "  ".join(
        f"{p} {num(v[0],0)}/{v[1]}" for p, v in qdetail.items() if v)
    rline = "  Risk     " + "  ".join(
        f"{p} {num(v[0],0)}/{v[1]}" for p, v in rdetail.items() if v)
    out.append(qline)
    out.append(rline)
    if waived:
        out.append("  (liquidity pillar waived by negative cash conversion cycle)")
    out.append("")

    if deep_skipped:
        out.append("--- DEEP DIVE ---")
        out.append("Deep Dive skipped -- AVOID already tripped. No forensic "
                   "requests issued.")
        out.append("")
    else:
        emit(deep, "DEEP DIVE")
        out.append("COMPOSITES")
        pio_str = f"{pio_pts}/{pio_total}" if pio_total else "n/a"
        if pio_drop:
            pio_str += f" (dropped: {', '.join(pio_drop)})"
        out.append(f"  Piotroski {pio_str}")
        out.append(f"  Altman {zlabel} " +
                   (f"{num(z)} ({zone})" if z is not None else "n/a"))
        out.append(f"  Beneish M " +
                   (f"{num(mscore)} ({mverdict})" if mscore is not None
                    else f"n/a ({mverdict})"))
        out.append("")

    out.append("--- RECENT NEWS ---")
    headlines = news_info.get("headlines") or []
    c = news_info.get("classified")
    if not headlines:
        out.append("  (no headlines found)")
    else:
        if c and c.get("tag") == "deal" and c.get("deal_price") is not None:
            px = c["deal_price"]
            if c.get("pinned"):
                out.append(f"  DEAL-PINNED -- agreed at ${num(px)}/share; price is within 4% of "
                           f"it, so upside is capped and the remaining question is deal-close risk, "
                           f"not direction")
            else:
                out.append(f"  DEAL PENDING -- agreed at ${num(px)}/share (not yet pinned at that "
                           f"price)")
        elif c and c.get("tag") == "roundup":
            out.append("  (most recent item is a market-wide roundup, not news about this name)")
        elif c and c.get("title"):
            tag_label = {"offering": "capital raise / dilution", "trial": "clinical/regulatory",
                        "earnings": "earnings", "analyst": "analyst action",
                        "legal": "legal/regulatory"}.get(c["tag"], "news")
            pub = c.get("publisher")
            marker = news_marker(c.get("ts"))
            out.append(f"  Likely driver ({tag_label}) {marker}" + (f", {pub}" if pub else "")
                       + f": \"{c['title']}\"")
        out.append("  Other recent headlines:")
        for h in headlines:
            tag = " [roundup]" if h.get("roundup") else ""
            out.append(f"    - {news_marker(h.get('ts'))} {h['title']}{tag}")
    out.append("")

    out.append("--- NEXT EARNINGS ---")
    if not earnings:
        out.append("  (no expected date from yfinance)")
    else:
        d, end, days = earnings["date"], earnings["end_date"], earnings["days"]
        when = f"{d}" if not end else f"{d} to {end} (estimated window)"
        if days < 0:
            out.append(f"  {when} -- overdue by {abs(days)}d (yfinance has not rolled this "
                       f"forward yet; a report likely already happened)")
        elif days == 0:
            out.append(f"  {when} -- today")
        else:
            out.append(f"  {when} -- in {days}d")
    out.append("")

    out.append("VALUATION (statement currency " + m.fin_ccy + ")")
    out.append(f"  P/E {num(m.g('pe'),1)}  P/FCF {num(m.g('p_fcf'),1)}  "
               f"EV/EBITDA {num(m.g('ev_ebitda'),1)}  P/B {num(m.g('p_b'),1)}")
    out.append("")

    price_disp = m.price_native / 100 if m.quote_ccy == "ILA" else m.price_native
    disp_ccy = "ILS" if m.quote_ccy == "ILA" else m.quote_ccy
    out.append(f"Price {disp_ccy} {num(price_disp)} (${num(m.price_usd)})  "
               f"Mkt cap ${money(m.mcap_usd)}  30d vol ${money(m.dollar_vol)}")
    out.append(f"Quote ccy {m.quote_ccy} | Statement ccy {m.fin_ccy} | "
               f"multiples computed in {m.fin_ccy}")
    out.append(f"Data fetched: {fetched_at.strftime('%H:%M')} "
               f"{fetched_at.tzname()} (Asia/Jerusalem) | source: yfinance")

    # Every check the code defines that is NOT in `results`, and why. Without this the JSON
    # lists only what ran, so 28 checks skipped for a bank or 6 skipped by the AVOID
    # short-circuit were invisible: results + skipped always equals the checks defined.
    skipped = []
    for c in checks:
        if not c.applies(m.rulebook):
            reason = f"does not apply to the {m.rulebook} rulebook"
        elif c.section == "deep" and deep_skipped:
            reason = "deep dive skipped: AVOID already tripped"
        else:
            continue
        skipped.append({"id": c.cid, "label": c.label, "reason": reason})

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    jpath = REPORTS_DIR / f"{file_key(symbol)}_{dt.date.today().isoformat()}.json"
    payload = {
        "status": "ok",
        "input": user_input, "resolution_chain": chain, "symbol": symbol,
        "name": m.name, "sector": m.sector, "industry": m.industry,
        "rulebook": m.rulebook, "rulebook_basis": m.rulebook_basis,
        "fy_years": m.fy_years, "fiscal_year_range": fy,
        "quote_currency": m.quote_ccy, "financial_currency": m.fin_ccy,
        "quality": quality, "risk": risk, "avoid": avoid,
        "quality_band": band_quality(quality), "risk_band": band_risk(risk),
        "coverage": round(coverage, 3),
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "deep_skipped": deep_skipped,
        "liquidity_waived": waived,
        # the sentence behind liquidity_waived -- also present when a negative cash
        # conversion cycle was deliberately NOT waived (payable stretching, impaired solvency)
        "liquidity_waiver_note": ccc_msg,
        "critical_failures": [r["id"] for r in critical_failed] +
                             [f"tradability:{t}" for t in trade_flags],
        "pillars": {"quality": {k: v[0] if v else None for k, v in qdetail.items()},
                    "risk": {k: v[0] if v else None for k, v in rdetail.items()}},
        "composites": {"piotroski": [pio_pts, pio_total], "piotroski_dropped": pio_drop,
                       "altman": z, "altman_zone": zone, "altman_variant": zlabel,
                       "beneish": mscore, "beneish_verdict": mverdict},
        "checks": results,
        "skipped_checks": skipped,
        "checks_defined": len(checks),
        "metrics": {k: (None if (isinstance(v, float) and
                                 (math.isnan(v) or math.isinf(v))) else v)
                    for k, v in m.data.items() if not isinstance(v, list)},
        "market": {"price_native": m.price_native, "price_usd": m.price_usd,
                   "market_cap_usd": m.mcap_usd, "dollar_volume_usd": m.dollar_vol},
        "news": news_info,
        "next_earnings": earnings,
        "diagnostics": DIAG,
    }
    jpath.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    out.append(f"JSON: {jpath}")

    tpath = jpath.with_suffix(".txt")
    tpath.write_text("\n".join(out), encoding="utf-8")
    out.append(f"TXT: {tpath}")

    print("\n".join(out))
    return 1 if avoid else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
