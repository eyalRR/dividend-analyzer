"""Unit tests verifying all 6 algorithm implementations and factory instantiation.
"""
import pytest

from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.factory import get_algorithm

def test_all_algorithm_instantiations():
    for version in AlgorithmVersion:
        algo = get_algorithm(version)
        assert algo is not None
        assert algo.version == version

def test_v1_linear_scoring(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V1_LINEAR)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)
    
    assert result.symbol == "TEST"
    assert 0.0 <= result.final_score <= 1.0
    assert "Dividend Yield (%)" in result.conditions
    assert "Payout Ratio (%)" in result.conditions

def test_v2_sigmoid_scoring(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V2_SIGMOID)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)

    assert result.symbol == "TEST"
    assert 0.0 <= result.final_score <= 1.0
    assert len(result.raw_scores) == 7

def test_v3_exponential_scoring(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V3_EXPONENTIAL)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)

    assert result.symbol == "TEST"
    assert 0.0 <= result.final_score <= 1.0
    assert result.weights["Dividend Yield (%)"] == 0.25

def test_v4_penalty_scoring(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V4_PENALTY_WEIGHTED)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)

    assert result.symbol == "TEST"
    assert result.initial_score >= 0.0
    assert result.final_score >= 0.0

def test_v5_dividend_value_baseline(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V5_DIVIDEND_VALUE)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)

    assert result.symbol == "TEST"
    assert "Dividend Value (%)" in result.conditions
    assert result.weights["Dividend Value (%)"] == 0.40
    assert 0.0 <= result.final_score <= 1.0

def test_v6_modern_corrected(sample_stock_data):
    df, info = sample_stock_data
    algo = get_algorithm(AlgorithmVersion.V6_MODERN_CORRECTED)
    result = algo.analyze("TEST", df, info, benchmark_yield=1.5)

    assert result.symbol == "TEST"
    assert "Dividend Yield (TTM %)" in result.conditions
    assert 0.0 <= result.final_score <= 1.0

def test_negative_eps_handling(sample_stock_data):
    """Ensure that an unprofitable company does not receive an artificially high payout score."""
    df, info = sample_stock_data
    info_loss = dict(info)
    info_loss["trailingEps"] = -2.50  # Net loss / negative earnings

    algo_v6 = get_algorithm(AlgorithmVersion.V6_MODERN_CORRECTED)
    result = algo_v6.analyze("LOSS", df, info_loss, benchmark_yield=1.5)

    assert result.conditions["Payout Ratio (%)"] >= 100.0  # Penalized
    assert result.penalties > 0.0  # Incurred risk penalty
