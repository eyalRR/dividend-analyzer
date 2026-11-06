"""Version 3: Asymmetric Exponential & Quadratic Scoring (from ver1/divClaude2.py).
Introduces the dynamic S&P 500 benchmark and asymmetric risk curves with 7 weighted metrics.
"""
import math
from typing import Dict, Tuple, Any
import pandas as pd
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.v1_linear import V1LinearAlgorithm

def payout_ratio_score(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    if value <= threshold:
        return 1.0 - 0.1 * (value / threshold) ** 2
    else:
        ratio = (value - threshold) / threshold
        return 0.8 * math.exp(-2.0 * (ratio ** 2))

def debt_to_equity_score(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    if value <= threshold:
        return 1.0 - 0.1 * (value / threshold) ** 2
    else:
        ratio = (value - threshold) / threshold
        return 0.8 * math.exp(-2.0 * (ratio ** 2))

class V3ExponentialAlgorithm(BaseAlgorithm):
    """Asymmetric exponential and quadratic scoring algorithm."""

    version = AlgorithmVersion.V3_EXPONENTIAL

    def __init__(self):
        super().__init__()
        self._v1 = V1LinearAlgorithm()

    def calculate_metrics(
        self,
        symbol: str,
        history: pd.DataFrame,
        info: Dict[str, Any],
        benchmark_yield: float = 1.5,
    ) -> Dict[str, float]:
        return self._v1.calculate_metrics(symbol, history, info, benchmark_yield)

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        thresholds = {
            "Dividend Yield (%)": (benchmark_yield, ">"),
            "Payout Ratio (%)": (50.0, "<"),
            "5-Year Dividend Growth Rate (%)": (10.0, ">"),
            "5-Year Earnings Growth (%)": (5.0, ">"),
            "Current Debt-to-Equity Ratio": (0.5, "<"),
            "5-Year EPS Growth Rate (%)": (5.0, ">"),
            "Dividend Age (Years)": (7.0, ">"),
        }

        weights = {
            "Dividend Yield (%)": 0.25,
            "Payout Ratio (%)": 0.15,
            "5-Year Dividend Growth Rate (%)": 0.15,
            "5-Year Earnings Growth (%)": 0.15,
            "Current Debt-to-Equity Ratio": 0.10,
            "5-Year EPS Growth Rate (%)": 0.10,
            "Dividend Age (Years)": 0.10,
        }

        raw_scores = {}
        for cond, val in metrics.items():
            threshold, comp = thresholds[cond]
            if cond == "Payout Ratio (%)":
                score = max(-0.5, payout_ratio_score(val, threshold))
            elif cond == "Current Debt-to-Equity Ratio":
                score = max(-0.5, debt_to_equity_score(val, threshold))
            else:
                if threshold > 0:
                    if comp == ">":
                        score = max(-0.5, 1.0 - math.exp(-val / threshold))
                    else:
                        score = max(-0.5, math.exp(-val / threshold))
                else:
                    score = 0.0
            raw_scores[cond] = score

        initial_score = sum(raw_scores[c] * weights[c] for c in metrics if c in weights)
        final_score = max(0.0, initial_score)

        return raw_scores, initial_score, 0.0, final_score, thresholds, weights
