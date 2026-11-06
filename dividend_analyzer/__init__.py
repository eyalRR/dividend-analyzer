"""Dividend Analyzer - A professional multi-version dividend stock analysis and portfolio scoring engine.
"""

from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.factory import get_algorithm
from dividend_analyzer.data.fetcher import DataFetcher
from dividend_analyzer.models import StockAnalysisResult

__version__ = "1.0.0"
__all__ = [
    "AlgorithmVersion",
    "get_algorithm",
    "DataFetcher",
    "StockAnalysisResult",
]
