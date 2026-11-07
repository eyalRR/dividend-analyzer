"""Factory module to instantiate algorithm strategies from AlgorithmVersion enums.
"""
from typing import Dict, Type
from dividend_analyzer.algorithms.versions import AlgorithmVersion
from dividend_analyzer.algorithms.base import BaseAlgorithm
from dividend_analyzer.algorithms.v1_linear import V1LinearAlgorithm
from dividend_analyzer.algorithms.v2_sigmoid import V2SigmoidAlgorithm
from dividend_analyzer.algorithms.v3_exponential import V3ExponentialAlgorithm
from dividend_analyzer.algorithms.v4_penalty import V4PenaltyAlgorithm
from dividend_analyzer.algorithms.v5_dividend_value import V5DividendValueAlgorithm
from dividend_analyzer.algorithms.v6_modern import V6ModernAlgorithm
from dividend_analyzer.algorithms.v7_fundamental_check import V7FundamentalCheckAlgorithm

_ALGORITHM_REGISTRY: Dict[AlgorithmVersion, Type[BaseAlgorithm]] = {
    AlgorithmVersion.V1_LINEAR: V1LinearAlgorithm,
    AlgorithmVersion.V2_SIGMOID: V2SigmoidAlgorithm,
    AlgorithmVersion.V3_EXPONENTIAL: V3ExponentialAlgorithm,
    AlgorithmVersion.V4_PENALTY_WEIGHTED: V4PenaltyAlgorithm,
    AlgorithmVersion.V5_DIVIDEND_VALUE: V5DividendValueAlgorithm,
    AlgorithmVersion.V6_MODERN_CORRECTED: V6ModernAlgorithm,
    AlgorithmVersion.V7_FUNDAMENTAL_CHECK: V7FundamentalCheckAlgorithm,
}

def get_algorithm(version: AlgorithmVersion | str) -> BaseAlgorithm:
    """Retrieve an instantiated algorithm instance by its version enum or string name."""
    if isinstance(version, str):
        try:
            version = AlgorithmVersion(version.lower())
        except ValueError:
            valid_names = [v.value for v in AlgorithmVersion]
            raise ValueError(f"Unknown algorithm version '{version}'. Valid options: {valid_names}")

    algo_class = _ALGORITHM_REGISTRY.get(version)
    if not algo_class:
        raise ValueError(f"No algorithm registered for version '{version}'")

    return algo_class()
