"""Unit tests verifying SQLite local data caching operations.
"""
import pytest
import pandas as pd
from pathlib import Path
from dividend_analyzer.data.cache import DataCache

@pytest.fixture
def temp_cache(tmp_path):
    db_file = tmp_path / "test_cache.db"
    return DataCache(db_path=db_file)

def test_info_caching(temp_cache):
    symbol = "AAPL"
    info = {"currentPrice": 220.0, "shortName": "Apple Inc."}
    
    # Cache miss
    assert temp_cache.get_info(symbol) is None

    # Set cache
    temp_cache.set_info(symbol, info)

    # Cache hit
    cached = temp_cache.get_info(symbol)
    assert cached is not None
    assert cached["currentPrice"] == 220.0
    assert cached["shortName"] == "Apple Inc."

def test_history_caching(temp_cache):
    symbol = "MSFT"
    df = pd.DataFrame({"Close": [400.0, 405.0], "Dividends": [0.0, 0.75]})

    assert temp_cache.get_history(symbol, years=5) is None

    temp_cache.set_history(symbol, years=5, df=df)
    cached_df = temp_cache.get_history(symbol, years=5)

    assert cached_df is not None
    assert len(cached_df) == 2
    assert "Dividends" in cached_df.columns

def test_benchmark_caching(temp_cache):
    assert temp_cache.get_benchmark("SPY") is None

    temp_cache.set_benchmark("SPY", 1.45)
    assert temp_cache.get_benchmark("SPY") == 1.45

def test_cache_clear(temp_cache):
    temp_cache.set_info("JNJ", {"currentPrice": 160.0})
    temp_cache.clear()
    assert temp_cache.get_info("JNJ") is None
