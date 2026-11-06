"""Shared pytest fixtures across all test suites.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime

@pytest.fixture
def sample_stock_data():
    """Generates synthetic historical price and dividend data for testing."""
    end_date = datetime.now()
    dates = pd.date_range(end=end_date, periods=250 * 5, freq="B")

    # Simulate rising stock price
    close_prices = np.linspace(100.0, 150.0, len(dates))
    df = pd.DataFrame({"Close": close_prices}, index=dates)
    df["Dividends"] = 0.0

    # Inject quarterly dividends over 5 years
    div_dates = pd.date_range(end=end_date, periods=20, freq="QE")
    for d in div_dates:
        nearest_idx = df.index.get_indexer([d], method="nearest")[0]
        df.iloc[nearest_idx, df.columns.get_loc("Dividends")] = 0.75

    info = {
        "currentPrice": 150.0,
        "previousClose": 148.0,
        "trailingEps": 6.00,
        "debtToEquity": 45.0,  # 0.45 ratio
        "shortName": "Test Dividend Corp",
    }
    return df, info
