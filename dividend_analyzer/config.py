"""Configuration settings and constants for Dividend Analyzer.
"""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DB = BASE_DIR / "dividend_cache.db"
DEFAULT_DATA_DIR = BASE_DIR / "data"

# Cache TTL (in seconds)
CACHE_INFO_TTL = 43200       # 12 hours for company info & fundamentals
CACHE_HISTORY_TTL = 14400    # 4 hours for price & dividend history
CACHE_BENCHMARK_TTL = 43200  # 12 hours for benchmark yield

# Benchmarks
DEFAULT_BENCHMARK_SYMBOL = "SPY"
DEFAULT_BENCHMARK_DIVIDEND_YIELD = 1.5  # Fallback percentage if SPY fetch fails

# Default Excel sheet names to look for
SUPPORTED_EXCEL_SHEETS = ["onezero", "pepper", "spy", "nyse", "Sheet1"]
