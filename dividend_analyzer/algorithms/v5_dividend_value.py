"""Version 5: Compounded Dividend Value Model (from ver1/divClaude5.py and ver1/excel.py).
Combines yield and growth into a single 40% weighted Dividend Value metric, backed by safety penalties.
This is the baseline model currently used in your working Excel processing scripts.
"""
import math
from typing import Dict, Tuple, Any
import pandas as pd
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.v3_exponential import (
    payout_ratio_score,
    debt_to_equity_score,
)
from dividend_analyzer.algorithms.v1_linear import V1LinearAlgorithm

def calculate_dividend_value(dividend_yield: float, dividend_growth_rate: float) -> float:
    if dividend_growth_rate < 0:
        return -1.0
    # Faithful to ver1/divClaude5.py logic:
    # Caps growth rate parameter at 0.25 (or decimal 25%)
    growth = dividend_growth_rate / 100.0 if dividend_growth_rate > 1.0 else dividend_growth_rate
    capped_growth = min(growth, 0.25)
    return dividend_yield * ((1.0 + capped_growth) ** 5)

class V5DividendValueAlgorithm(BaseAlgorithm):
    """Compounded Dividend Value baseline algorithm."""

    version = AlgorithmVersion.V5_DIVIDEND_VALUE

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
        raw_7 = self._v1.calculate_metrics(symbol, history, info, benchmark_yield)

        div_yield = raw_7.get("Dividend Yield (%)", 0.0)
        div_growth = raw_7.get("5-Year Dividend Growth Rate (%)", 0.0)
        div_val = calculate_dividend_value(div_yield, div_growth)

        metrics = {
            "Dividend Value (%)": div_val,
            "Dividend Yield (%)": div_yield,
            "Payout Ratio (%)": raw_7.get("Payout Ratio (%)", 0.0),
            "5-Year Dividend Growth Rate (%)": div_growth,
            "5-Year Earnings Growth (%)": raw_7.get("5-Year Earnings Growth (%)", 0.0),
            "Current Debt-to-Equity Ratio": raw_7.get("Current Debt-to-Equity Ratio", 0.0),
            "5-Year EPS Growth Rate (%)": raw_7.get("5-Year EPS Growth Rate (%)", 0.0),
            "Dividend Age (Years)": raw_7.get("Dividend Age (Years)", 0.0),
        }
        return metrics

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        thresholds = {
            "Dividend Value (%)": (benchmark_yield, ">"),
            "Payout Ratio (%)": (50.0, "<"),
            "5-Year Earnings Growth (%)": (5.0, ">"),
            "Current Debt-to-Equity Ratio": (0.5, "<"),
            "5-Year EPS Growth Rate (%)": (5.0, ">"),
            "Dividend Age (Years)": (7.0, ">"),
        }

        weights = {
            "Dividend Value (%)": 0.40,
            "Payout Ratio (%)": 0.15,
            "5-Year Earnings Growth (%)": 0.15,
            "Current Debt-to-Equity Ratio": 0.10,
            "5-Year EPS Growth Rate (%)": 0.10,
            "Dividend Age (Years)": 0.10,
        }

        raw_scores = {}
        for cond, (threshold, comp) in thresholds.items():
            val = metrics.get(cond, 0.0)
            if cond == "Dividend Value (%)":
                raw_scores[cond] = max(-0.5, 1.0 - math.exp(-val / threshold)) if threshold > 0 else 0.0
            elif cond == "Payout Ratio (%)":
                raw_scores[cond] = max(-0.5, payout_ratio_score(val, threshold))
            elif cond == "Current Debt-to-Equity Ratio":
                raw_scores[cond] = max(-0.5, debt_to_equity_score(val, threshold))
            elif cond == "Dividend Age (Years)":
                raw_scores[cond] = max(-0.5, 1.0 - math.exp(-val / threshold)) if threshold > 0 else 0.0
            else:
                if threshold > 0:
                    if comp == ">":
                        raw_scores[cond] = max(-0.5, 1.0 - math.exp(-val / threshold))
                    else:
                        raw_scores[cond] = max(-0.5, math.exp(-val / threshold))
                else:
                    raw_scores[cond] = 0.0

        initial_score = sum(raw_scores[c] * weights[c] for c in weights)

        # Safety penalties
        div_yield = metrics.get("Dividend Yield (%)", 0.0)
        payout = metrics.get("Payout Ratio (%)", 0.0)
        div_growth = metrics.get("5-Year Dividend Growth Rate (%)", 0.0)
        earn_growth = metrics.get("5-Year Earnings Growth (%)", 0.0)
        de_ratio = metrics.get("Current Debt-to-Equity Ratio", 0.0)
        eps_growth = metrics.get("5-Year EPS Growth Rate (%)", 0.0)
        div_age = metrics.get("Dividend Age (Years)", 0.0)

        penalties = 0.0
        if not (0.8 * benchmark_yield <= div_yield <= 8.0):
            penalties += 0.10
        if payout >= 80.0:
            penalties += 0.10
        if not (5.0 <= div_growth <= 25.0):
            penalties += 0.10
        if earn_growth <= 3.0:
            penalties += 0.10
        elif earn_growth > 25.0:
            penalties += 0.05
        if de_ratio >= 2.0:
            penalties += 0.10
        if eps_growth <= 3.0:
            penalties += 0.10
        elif eps_growth > 25.0:
            penalties += 0.05
        if div_age <= 5.0:
            penalties += 0.10

        # High yield bonus incentive
        if div_yield > (2.0 * benchmark_yield):
            penalties -= 0.10

        final_score = max(0.0, initial_score - penalties)

        return raw_scores, initial_score, penalties, final_score, thresholds, weights
