"""Version 1: Normalized Linear Scoring Algorithm (from ver2/divClaude.py).
Evaluates 7 conditions and maps each linearly to [-1, 1] based on fixed thresholds.
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
import pandas as pd
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.versions import AlgorithmVersion

class V1LinearAlgorithm(BaseAlgorithm):
    """Linear normalized scoring model."""

    version = AlgorithmVersion.V1_LINEAR

    def calculate_metrics(
        self,
        symbol: str,
        history: pd.DataFrame,
        info: Dict[str, Any],
        benchmark_yield: float = 1.5,
    ) -> Dict[str, float]:
        metrics = {}

        # 1. Dividend Yield (%)
        current_year = datetime.now().year
        last_full_year = current_year - 1
        last_year_divs = 0.0
        if "Dividends" in history.columns:
            last_year_divs = float(history[history.index.year == last_full_year]["Dividends"].sum())

        current_price = float(info.get("currentPrice", 0.0) or (history["Close"].iloc[-1] if "Close" in history.columns else 0.0))
        metrics["Dividend Yield (%)"] = (last_year_divs / current_price * 100.0) if current_price > 0 else 0.0

        # 2. Payout Ratio (%)
        eps = float(info.get("trailingEps", 0.0) or 0.0)
        metrics["Payout Ratio (%)"] = (last_year_divs / eps * 100.0) if eps > 0 else 0.0

        # 3. 5-Year Dividend Growth Rate (%)
        metrics["5-Year Dividend Growth Rate (%)"] = 0.0
        if "Dividends" in history.columns:
            annual_divs = history["Dividends"].groupby(history.index.year).sum()
            annual_divs = annual_divs[annual_divs.index < current_year]
            if len(annual_divs) >= 5:
                start_year, end_year = annual_divs.index[-5], annual_divs.index[-1]
                start_val, end_val = annual_divs[start_year], annual_divs[end_year]
                years = end_year - start_year
                if start_val > 0 and years > 0:
                    cagr = (end_val / start_val) ** (1 / years) - 1
                    metrics["5-Year Dividend Growth Rate (%)"] = cagr * 100.0

        # 4. 5-Year Earnings Growth (%) [Close price CAGR]
        metrics["5-Year Earnings Growth (%)"] = 0.0
        if "Close" in history.columns:
            annual_close = history["Close"].resample("YE").last().dropna()
            annual_close = annual_close[annual_close.index.year < current_year]
            if len(annual_close) >= 5:
                start_val, end_val = annual_close.iloc[-5], annual_close.iloc[-1]
                if start_val > 0:
                    cagr = (end_val / start_val) ** (1 / 5) - 1
                    metrics["5-Year Earnings Growth (%)"] = cagr * 100.0

        # 5. Current Debt-to-Equity Ratio
        de = float(info.get("debtToEquity", 0.0) or 0.0)
        metrics["Current Debt-to-Equity Ratio"] = de / 100.0

        # 6. 5-Year EPS Growth Rate (%)
        metrics["5-Year EPS Growth Rate (%)"] = 0.0
        prev_close = float(info.get("previousClose", 0.0) or 0.0)
        if eps > 0 and prev_close > 0 and "Close" in history.columns and len(history["Close"]) > 0:
            past_close = float(history["Close"].iloc[0])
            past_eps = past_close * eps / prev_close
            if past_eps > 0:
                eps_growth = (eps / past_eps) ** (1 / 5) - 1
                metrics["5-Year EPS Growth Rate (%)"] = eps_growth * 100.0

        # 7. Dividend Age (Years)
        metrics["Dividend Age (Years)"] = 0.0
        if "Dividends" in history.columns:
            div_dates = history[history["Dividends"] > 0].index
            if len(div_dates) > 0:
                age_days = (datetime.now() - div_dates.min()).days
                metrics["Dividend Age (Years)"] = round(age_days / 365.25, 2)

        return metrics

    def calculate_scores(
        self,
        metrics: Dict[str, float],
        benchmark_yield: float = 1.5,
    ) -> Tuple[Dict[str, float], float, float, float, Dict[str, Tuple[float, str]], Dict[str, float]]:
        thresholds = {
            "Dividend Yield (%)": (3.0, ">"),
            "Payout Ratio (%)": (80.0, "<"),
            "5-Year Dividend Growth Rate (%)": (5.0, ">"),
            "5-Year Earnings Growth (%)": (5.0, ">"),
            "Current Debt-to-Equity Ratio": (0.5, "<"),
            "5-Year EPS Growth Rate (%)": (5.0, ">"),
            "Dividend Age (Years)": (10.0, ">"),
        }

        raw_scores = {}
        for cond, val in metrics.items():
            threshold, comp = thresholds[cond]
            if comp == ">":
                score = (val - threshold) / abs(threshold)
            else:
                score = (threshold - val) / abs(threshold)
            # Clamp to [-1, 1]
            raw_scores[cond] = max(-1.0, min(1.0, score))

        # Equal weighting across all 7 metrics, normalized to [0, 1]
        weight = 1.0 / len(metrics)
        weights = {cond: weight for cond in metrics}
        
        # Transform [-1, 1] scores into [0, 1] for final scoring
        normalized_scores = [(s + 1.0) / 2.0 for s in raw_scores.values()]
        final_score = sum(normalized_scores) / len(normalized_scores)

        return raw_scores, final_score, 0.0, final_score, thresholds, weights
