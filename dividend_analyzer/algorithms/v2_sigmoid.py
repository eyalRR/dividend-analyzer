"""Version 2: Sigmoid S-Curve Scoring Model (from ver2/x.py and ver2/divClaude3.py).
Maps each condition through a logistic sigmoid function with updated financial thresholds.
"""
import math
from typing import Dict, Tuple, Any
import pandas as pd
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.v1_linear import V1LinearAlgorithm

def sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0

class V2SigmoidAlgorithm(BaseAlgorithm):
    """Sigmoid S-curve scoring model."""

    version = AlgorithmVersion.V2_SIGMOID

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
        # Uses the same metric extraction as V1
        return self._v1.calculate_metrics(symbol, history, info, benchmark_yield)

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        thresholds = {
            "Dividend Yield (%)": (3.0, ">"),
            "Payout Ratio (%)": (50.0, "<"),
            "5-Year Dividend Growth Rate (%)": (10.0, ">"),
            "5-Year Earnings Growth (%)": (5.0, ">"),
            "Current Debt-to-Equity Ratio": (0.5, "<"),
            "5-Year EPS Growth Rate (%)": (5.0, ">"),
            "Dividend Age (Years)": (7.0, ">"),
        }

        raw_scores = {}
        for cond, val in metrics.items():
            threshold, comp = thresholds[cond]
            if comp == ">":
                diff = (val - threshold) / abs(threshold)
            else:
                diff = (threshold - val) / abs(threshold)
            raw_scores[cond] = sigmoid(diff)

        # Equal weighting across metrics
        weight = 1.0 / len(metrics)
        weights = {cond: weight for cond in metrics}
        final_score = sum(raw_scores.values()) / len(raw_scores)

        return raw_scores, final_score, 0.0, final_score, thresholds, weights
