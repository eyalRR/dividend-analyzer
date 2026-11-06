"""Data fetcher module using yfinance with transparent local SQLite caching.
"""
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
import yfinance as yf
import pandas as pd
from dividend_analyzer.data.cache import DataCache
from dividend_analyzer.config import (
    DEFAULT_BENCHMARK_SYMBOL,
    DEFAULT_BENCHMARK_DIVIDEND_YIELD,
)

class DataFetcher:
    """Fetches financial data with caching support."""

    def __init__(self, use_cache: bool = True, cache: Optional[DataCache] = None):
        self.use_cache = use_cache
        self.cache = cache or (DataCache() if use_cache else None)

    def fetch_stock_data(
        self, symbol: str, years: int = 10
    ) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
        """Fetch historical price & dividend data and fundamental info for a ticker."""
        symbol = symbol.strip().upper()

        cached_history = None
        cached_info = None

        if self.use_cache and self.cache:
            cached_history = self.cache.get_history(symbol, years)
            cached_info = self.cache.get_info(symbol)

        if cached_history is not None and cached_info is not None:
            return cached_history, cached_info

        try:
            ticker = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=years * 365)
            
            history = ticker.history(start=start_date, end=end_date)
            if history is not None and not history.empty and hasattr(history.index, "tz_localize"):
                try:
                    if history.index.tz is not None:
                        history.index = history.index.tz_localize(None)
                except Exception:
                    pass

            # Fast info or fallback to basic info
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                info = getattr(ticker, "fast_info", {})
                if hasattr(info, "items"):
                    info = dict(info)
                else:
                    info = {}

            # Cache retrieved data
            if self.use_cache and self.cache:
                if history is not None and not history.empty:
                    self.cache.set_history(symbol, years, history)
                if info:
                    self.cache.set_info(symbol, info)

            return history, info
        except Exception as e:
            print(f"[Warning] Failed to fetch data for {symbol}: {e}")
            return None, None

    def fetch_all_historical_dividends(self, symbol: str) -> Optional[pd.Series]:
        """Fetch all historical dividends without year truncation (for dividend age and aristocrat status)."""
        symbol = symbol.strip().upper()
        try:
            ticker = yf.Ticker(symbol)
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                if hasattr(divs.index, "tz_localize") and divs.index.tz is not None:
                    divs.index = divs.index.tz_localize(None)
                return divs
        except Exception:
            pass
        return None

    def get_benchmark_dividend_yield(
        self, benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL
    ) -> float:
        """Calculate the dividend yield of benchmark index ETF (default: SPY)."""
        benchmark_symbol = benchmark_symbol.upper()

        if self.use_cache and self.cache:
            cached_val = self.cache.get_benchmark(benchmark_symbol)
            if cached_val is not None:
                return cached_val

        try:
            history, _ = self.fetch_stock_data(benchmark_symbol, years=1)
            if history is not None and not history.empty and "Dividends" in history.columns:
                total_dividends = history["Dividends"].sum()
                current_price = history["Close"].iloc[-1]
                if current_price > 0 and total_dividends > 0:
                    yield_val = (total_dividends / current_price) * 100.0
                    if self.use_cache and self.cache:
                        self.cache.set_benchmark(benchmark_symbol, yield_val)
                    return round(yield_val, 2)
        except Exception:
            pass

        return DEFAULT_BENCHMARK_DIVIDEND_YIELD
