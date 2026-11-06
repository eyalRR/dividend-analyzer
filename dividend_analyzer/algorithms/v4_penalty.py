"""Version 4: Safety Penalty Scoring System (from ver1/divClaude3.py & ver1/divClaude4.py).
Extends V3 with multi-factor risk deductions and bonus incentives.
"""
from typing import Dict, Tuple
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.v3_exponential import V3ExponentialAlgorithm

class V4PenaltyAlgorithm(V3ExponentialAlgorithm):
    """V3 scoring engine enhanced with safety deduction penalties."""

    version = AlgorithmVersion.V4_PENALTY_WEIGHTED

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        raw_scores, initial_score, _, _, thresholds, weights = super().calculate_scores(
            metrics, benchmark_yield
        )

        div_yield = metrics.get("Dividend Yield (%)", 0.0)
        payout = metrics.get("Payout Ratio (%)", 0.0)
        div_growth = metrics.get("5-Year Dividend Growth Rate (%)", 0.0)
        earn_growth = metrics.get("5-Year Earnings Growth (%)", 0.0)
        de_ratio = metrics.get("Current Debt-to-Equity Ratio", 0.0)
        eps_growth = metrics.get("5-Year EPS Growth Rate (%)", 0.0)
        div_age = metrics.get("Dividend Age (Years)", 0.0)

        penalties = 0.0
        # Yield safety zone: 0.8 * SPY to 8%
        if not (0.8 * benchmark_yield <= div_yield <= 8.0):
            penalties += 0.10
        # Payout ratio danger zone >= 80%
        if payout >= 80.0:
            penalties += 0.10
        # Dividend growth sanity check (5% to 25%)
        if not (5.0 <= div_growth <= 25.0):
            penalties += 0.10
        # Earnings growth stagnation or overheating
        if earn_growth <= 3.0:
            penalties += 0.10
        elif earn_growth > 25.0:
            penalties += 0.05
        # High leverage
        if de_ratio >= 2.0:
            penalties += 0.10
        # EPS growth stagnation or overheating
        if eps_growth <= 3.0:
            penalties += 0.10
        elif eps_growth > 25.0:
            penalties += 0.05
        # Low dividend longevity
        if div_age <= 5.0:
            penalties += 0.10

        # High yield bonus incentive (yield > 2x S&P 500)
        if div_yield > (2.0 * benchmark_yield):
            penalties -= 0.10

        final_score = max(0.0, initial_score - penalties)

        return raw_scores, initial_score, penalties, final_score, thresholds, weights
