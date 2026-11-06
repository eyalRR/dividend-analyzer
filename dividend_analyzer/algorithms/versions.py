"""Algorithm version definitions and metadata.
"""
from enum import Enum

class AlgorithmVersion(str, Enum):
    """Catalog of historical and modern algorithm versions for dividend analysis."""

    V1_LINEAR = "v1_linear"
    V2_SIGMOID = "v2_sigmoid"
    V3_EXPONENTIAL = "v3_exponential"
    V4_PENALTY_WEIGHTED = "v4_penalty_weighted"
    V5_DIVIDEND_VALUE = "v5_dividend_value"
    V6_MODERN_CORRECTED = "v6_modern_corrected"

    @property
    def display_name(self) -> str:
        names = {
            AlgorithmVersion.V1_LINEAR: "V1: Normalized Linear Scoring",
            AlgorithmVersion.V2_SIGMOID: "V2: Sigmoid S-Curve Model",
            AlgorithmVersion.V3_EXPONENTIAL: "V3: Asymmetric Exponential & Quadratic",
            AlgorithmVersion.V4_PENALTY_WEIGHTED: "V4: Weighted Safety Penalty System",
            AlgorithmVersion.V5_DIVIDEND_VALUE: "V5: Compounded Dividend Value (Baseline)",
            AlgorithmVersion.V6_MODERN_CORRECTED: "V6: Modern Financial Standard (Corrected)",
        }
        return names.get(self, self.value)

    @property
    def description(self) -> str:
        descs = {
            AlgorithmVersion.V1_LINEAR: "Initial 7-metric model with linear normalized scores [-1, 1] against fixed thresholds.",
            AlgorithmVersion.V2_SIGMOID: "S-curve sigmoid normalization across 7 metrics with unweighted averaging.",
            AlgorithmVersion.V3_EXPONENTIAL: "Introduced dynamic S&P 500 benchmark and asymmetric quadratic/exponential curves with 7 weighted metrics.",
            AlgorithmVersion.V4_PENALTY_WEIGHTED: "Adds multi-tier safety deduction penalties for excessive payout, low earnings growth, or high leverage.",
            AlgorithmVersion.V5_DIVIDEND_VALUE: "Combines yield and growth into 5-year compounded Dividend Value (40% weight) with full penalties.",
            AlgorithmVersion.V6_MODERN_CORRECTED: "Production standard: TTM dividend yield, true net income CAGR, true historical diluted EPS, full dividend longevity, and edge-case protection.",
        }
        return descs.get(self, "")
