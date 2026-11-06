"""Abstract base class and contract for all dividend analysis algorithm implementations.
"""
from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from dividend_analyzer.models import StockAnalysisResult
from dividend_analyzer.algorithms.versions import AlgorithmVersion

class BaseAlgorithm(ABC):
    """Abstract Strategy interface for dividend analysis algorithms."""

    version: AlgorithmVersion

    def __init__(self):
        pass

    @abstractmethod
    def calculate_metrics(
        self,
        symbol: str,
        history: pd.DataFrame,
        info: Dict[str, Any],
        benchmark_yield: float = 1.5,
    ) -> Dict[str, float]:
        """Compute the core financial metrics for the ticker."""
        pass

    @abstractmethod
    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        """Compute raw scores, initial score, penalties, final score, thresholds, and weights.
        Returns:
            (raw_scores, initial_score, penalties, final_score, thresholds, weights)
        """
        pass

    def detect_missing_dividends(self, history: Optional[pd.DataFrame]) -> List[str]:
        """Detect irregular or missing dividend payments based on historical intervals."""
        if history is None or history.empty or "Dividends" not in history.columns:
            return []

        dividend_dates = history[history["Dividends"] > 0].index
        if len(dividend_dates) < 2:
            return []

        avg_interval = (dividend_dates[-1] - dividend_dates[0]) / (len(dividend_dates) - 1)
        expected_dates = pd.date_range(start=dividend_dates[0], end=dividend_dates[-1], freq=avg_interval)

        missing_dates = []
        for date in expected_dates:
            if date not in dividend_dates:
                nearest_actual = min(dividend_dates, key=lambda x: abs(x - date))
                if abs(nearest_actual - date) > timedelta(days=30):
                    missing_dates.append(date.strftime("%Y-%m-%d"))

        return missing_dates

    def analyze(
        self,
        symbol: str,
        history: Optional[pd.DataFrame],
        info: Optional[Dict[str, Any]],
        benchmark_yield: float = 1.5,
    ) -> StockAnalysisResult:
        """Run full evaluation and return typed StockAnalysisResult."""
        symbol = symbol.strip().upper()
        if history is None or history.empty or info is None:
            return StockAnalysisResult(
                symbol=symbol,
                algorithm_version=self.version.value,
                final_score=0.0,
                details={"error": f"Missing or incomplete data for {symbol}"},
            )

        metrics = self.calculate_metrics(symbol, history, info, benchmark_yield)
        raw_scores, initial_score, penalties, final_score, thresholds, weights = (
            self.calculate_scores(metrics, benchmark_yield)
        )
        missing_dividends = self.detect_missing_dividends(history)

        annual_dividends = {}
        if "Dividends" in history.columns:
            annual_sum = history["Dividends"].groupby(history.index.year).sum()
            annual_dividends = {int(k): round(float(v), 4) for k, v in annual_sum.items() if v > 0}

        current_price = float(info.get("currentPrice", 0.0) or info.get("regularMarketPrice", 0.0) or 0.0)
        if current_price == 0.0 and "Close" in history.columns and not history["Close"].empty:
            current_price = float(history["Close"].iloc[-1])

        company_name = str(info.get("shortName", "") or info.get("longName", "") or symbol)

        return StockAnalysisResult(
            symbol=symbol,
            algorithm_version=self.version.value,
            final_score=round(final_score, 2),
            initial_score=round(initial_score, 2),
            penalties=round(penalties, 2),
            current_price=round(current_price, 2),
            company_name=company_name,
            conditions={k: round(v, 2) for k, v in metrics.items()},
            raw_scores={k: round(v, 2) for k, v in raw_scores.items()},
            thresholds=thresholds,
            weights=weights,
            missing_dividends=missing_dividends,
            annual_dividends=annual_dividends,
        )
