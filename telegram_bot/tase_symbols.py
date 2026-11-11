"""Resolve a Tel Aviv Stock Exchange security number to its Yahoo Finance symbol.

Vendored (trimmed to just the resolver) from
D:\\projects\\AI\\projects\\youtue_strategy_back_tester\\.claude\\skills\\fetch-price-data\\tase_symbols.py
-- see that file for the full writeup. In short: TASE securities are identified
by a security number (`1081124`), not a Yahoo symbol, and Yahoo's search does
not match on the bare digits. The bridge is the ISIN, which is a pure function
of the security number (`IL` + zero-padded number + check digit), and Yahoo's
free search endpoint resolves an ISIN to its symbol:

    1081124 -> IL0010811243 -> ESLT.TA   (Elbit Systems)
     230011 -> IL0002300114 -> BEZQ.TA   (Bezeq)

Resolutions are cached to `tase_symbol_map.json` next to this file, so the
endpoint is hit once per security number, ever.
"""
import json
import os
import re
import tempfile

import requests

_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-snapshot/1.0)"}
_TIMEOUT = 20

_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tase_symbol_map.json")

# Israeli security numbers are at most 9 digits (why the ISIN pads to 9).
_BARE_NUMBER_RE = re.compile(r"^(?:TASE:)?(\d{1,9})$", re.IGNORECASE)
_ISIN_RE = re.compile(r"^IL\d{10}$", re.IGNORECASE)


def _isin_check_digit(body: str) -> str:
    # Letters expand to two digits (A=10..Z=35) BEFORE the Luhn pass -- doing
    # Luhn over the letters-as-single-symbols shifts parity and gives a wrong digit.
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in body.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def tase_number_to_isin(security_number) -> str:
    body = "IL" + str(int(security_number)).zfill(9)
    return body + _isin_check_digit(body)


def _load_map() -> dict:
    try:
        with open(_MAP_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_map(mapping: dict) -> None:
    directory = os.path.dirname(_MAP_PATH) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, indent=1, sort_keys=True)
        os.replace(tmp_path, _MAP_PATH)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _search_yahoo(query: str) -> list:
    resp = requests.get(_SEARCH_URL, params={"q": query, "quotesCount": 10, "newsCount": 0},
                        headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("quotes", []) or []


def resolve_symbol(symbol: str, refresh: bool = False) -> str:
    """Pass-through for ordinary tickers; TASE security number / ISIN -> Yahoo symbol.

    Raises ValueError if Yahoo knows no Tel Aviv listing for it.
    """
    token = str(symbol).strip()
    match = _BARE_NUMBER_RE.match(token)
    if not match and not _ISIN_RE.match(token.upper()):
        return token  # ordinary ticker, untouched

    isin = tase_number_to_isin(match.group(1)) if match else token.upper()

    mapping = _load_map()
    if not refresh and isin in mapping:
        return mapping[isin]["symbol"]

    try:
        quotes = _search_yahoo(isin)
    except Exception as e:
        raise ValueError(f"Yahoo symbol lookup failed for {token} (ISIN {isin}): {e}") from e

    # Prefer the Tel Aviv listing -- an Israeli ISIN can also surface a dual-listed
    # US line, and quietly returning that would be a different security/currency/session.
    tase = [q for q in quotes if str(q.get("symbol", "")).upper().endswith(".TA")]
    chosen = (tase or quotes or [None])[0]
    if not chosen or not chosen.get("symbol"):
        raise ValueError(
            f"No Yahoo listing found for TASE security {token} (ISIN {isin}). "
            "Check the security number, or pass the Yahoo ticker (e.g. ESLT.TA) directly."
        )

    symbol_out = chosen["symbol"]
    mapping[isin] = {
        "symbol": symbol_out,
        "name": chosen.get("longname") or chosen.get("shortname") or "",
        "exchange": chosen.get("exchange", ""),
    }
    try:
        _save_map(mapping)
    except OSError:
        pass
    return symbol_out
