"""Recent headlines for one symbol, and the one fact that caps a move: a signed deal price.

Adapted from a sibling project's market-wide scanner (market_dashboard/inputs/news.py), trimmed
to a single symbol so this skill stays self-contained -- no `config`, no thread pool, same
classification logic. Source: query1.finance.yahoo.com/v1/finance/search, free and keyless.

THE DEAL-PRICE CASE IS THE ONE WORTH CODE RATHER THAN READING. When a company agrees to be
bought at a fixed price, that price is a CAP: the stock walks up to just under it and stops,
because the upside is now a known number and the only remaining question is whether the deal
closes. A fundamentals check that is silent about this will score a deal-pinned stock on
profitability and leverage while missing the one fact that actually bounds its price.

Fetches the 5 most recent headlines regardless of age -- no hard cutoff. A quiet name can
legitimately have nothing newer than a stale item; `age_h` travels with every classified result
specifically so staleness is visible (and discountable) rather than hidden by a filter that would
otherwise show nothing at all for that name. The one filter kept is for a different lie: a
market-wide roundup ("Stock Market Today: Nasdaq Dives 2%") that explains every stock and
therefore none of them -- `classify()` only falls back to one when the symbol has nothing of its
own.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
HEAD = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36")}
TIMEOUT = 15

ROUNDUP = re.compile(
    r"^(stock market today|stocks? to watch|top (midday|premarket|after.hours)"
    r"|stocks making (big )?moves|market wrap|here.s what|movers?:|"
    r"dow jones|s&p 500 today|trending tickers|what to watch)", re.I)

# A corporate action with a fixed price. Deliberately narrow: these phrases mean a NUMBER has
# been agreed, which is what makes the cap real.
DEAL = re.compile(
    r"\b(to be acquired|acquisition of|acquire[sd]?|taken private|take private|"
    r"go(?:ing)? private|merger agreement|definitive agreement|buyout|"
    r"tender offer|all.cash)\b", re.I)

# "$6.05 a share" / "$6.05 per share" / "at $6.05/share"
PER_SHARE = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:per share|/\s*share|a share)", re.I)

# An ANALYST price target is not a cap and must not be read as one -- an unguarded regex would
# pick up the right-looking number for entirely the wrong reason on any ordinary upgrade.
TARGET = re.compile(r"\b(price target|pt raise|pt cut|initiates?|upgrade[sd]?|"
                    r"downgrade[sd]?|maintains?|reiterate[sd]?)\b", re.I)

# other causes worth naming, in the order they are tested
TAGS = [
    ("offering", re.compile(r"\b(convertible notes|offering|secondary|"
                            r"dilution|at.the.market|registered direct|"
                            r"prices? \$?\d)\b", re.I)),
    ("trial", re.compile(r"\b(phase [i1-3]|trial|FDA|approval|clinical|"
                         r"topline|efficacy|endpoint)\b", re.I)),
    ("earnings", re.compile(r"\b(earnings|results|quarter|guidance|revenue|EPS)\b", re.I)),
    ("analyst", TARGET),
    ("legal", re.compile(r"\b(lawsuit|investigation|SEC |probe|settlement|"
                         r"subpoena)\b", re.I)),
]


def fetch_headlines(symbol: str, n: int = 5) -> list[dict]:
    """The `n` most recent headlines for one symbol, newest first -- no age cutoff.

    Network failure or an empty response is a normal, silent outcome here -- this feature must
    never fail the fundamental check over it -- so this returns [] rather than raising.
    """
    q = urllib.parse.urlencode({"q": symbol, "newsCount": n, "quotesCount": 0})
    try:
        req = urllib.request.Request(f"{SEARCH}?{q}", headers=HEAD)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
            data = json.loads(f.read())
    except Exception:
        return []
    rows = []
    for it in data.get("news") or []:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        rows.append({"title": title, "publisher": it.get("publisher") or "",
                     "ts": it.get("providerPublishTime") or 0, "link": it.get("link") or "",
                     "roundup": bool(ROUNDUP.search(title))})
    rows.sort(key=lambda r: -r["ts"])
    return rows[:n]


def deal_price(title: str) -> float | None:
    """The agreed per-share price, when the headline really states one.

    Both halves are required -- deal language AND a per-share figure -- because either alone is
    a false positive waiting to happen: "price target to $6.05" has the figure without the
    agreement, and "to be acquired by X" has the agreement without a number to pin anything to.
    """
    if not DEAL.search(title):
        return None
    if TARGET.search(title) and not PER_SHARE.search(title):
        return None
    m = PER_SHARE.search(title)
    return float(m.group(1)) if m else None


def classify(items: list[dict]) -> dict:
    """The most useful thing said about this name recently.

    A market roundup is only used when the symbol has nothing of its own, and is tagged as one
    so it is never read as the reason this stock moved.
    """
    items = items or []
    own = [i for i in items if not i.get("roundup")]
    items = own or items
    best = {"tag": None, "deal_price": None, "title": None, "ts": 0, "publisher": None}
    for it in items:
        t = it["title"]
        px = deal_price(t)
        if px is not None:
            return {"tag": "deal", "deal_price": px, "title": t,
                    "ts": it["ts"], "publisher": it["publisher"]}
        if best["tag"] is None:
            for name, rx in TAGS:
                if rx.search(t):
                    best = {"tag": name, "deal_price": None, "title": t,
                            "ts": it["ts"], "publisher": it["publisher"]}
                    break
    if best["tag"] is None and items:
        it = items[0]
        best = {"tag": "roundup" if it.get("roundup") else "news",
                "deal_price": None, "title": it["title"],
                "ts": it["ts"], "publisher": it["publisher"]}
    return best


def pinned(price: float | None, deal: float | None, tol: float = 0.04) -> bool:
    """Is the stock already sitting at the agreed price?

    Within a few percent of it, the remaining move is deal-close risk and arbitrage spread, not
    direction -- no momentum or valuation read applies the same way.
    """
    if not price or not deal:
        return False
    return abs(price - deal) / deal <= tol


def annotate(symbol: str, price: float | None = None, n: int = 5) -> dict:
    """{headlines, classified: {tag, title, deal_price, pinned, age_h, publisher}}.

    `classified` is None when the symbol has no headlines at all -- a quiet name, not an error.
    `price` (the stock's current price, same currency the headline's $ figure assumes --
    US-listed names only, since deal prices are quoted in USD) enables the `pinned` check.
    """
    items = fetch_headlines(symbol, n)
    c = classify(items) if items else None
    if c and c.get("title"):
        now = time.time()
        c["age_h"] = round((now - c["ts"]) / 3600, 1) if c.get("ts") else None
        c["pinned"] = pinned(price, c.get("deal_price"))
    else:
        c = None
    return {"headlines": items, "classified": c}
