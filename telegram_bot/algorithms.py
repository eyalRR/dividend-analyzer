"""Registry of algorithms telegram_bot.py dispatches a symbol to.

Contains explicit metadata for each engine, including target audience and descriptions.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AlgorithmMetadata:
    key: str
    script_path: str
    title: str
    target_audience_en: str
    target_audience_he: str
    icon: str
    description: str


_ALGORITHMS_DIR = Path(__file__).resolve().parent / "algo_scripts"

ALGORITHM_REGISTRY: dict[str, AlgorithmMetadata] = {
    "dividend_analyzer": AlgorithmMetadata(
        key="dividend_analyzer",
        script_path=str(_ALGORITHMS_DIR / "dividend_analyzer_algo.py"),
        title="Dividend Compounding Engine (V5)",
        target_audience_en="Dividend Growth & Passive Income Investors",
        target_audience_he="משקיעי דיבידנד ותזרים מזומנים",
        icon="💰",
        description="Analyzes dividend sustainability, compound growth, and payout coverage.",
    ),
    "stock_overview": AlgorithmMetadata(
        key="stock_overview",
        script_path=str(_ALGORITHMS_DIR / "stock_overview_algo.py"),
        title="Technical Trend & Volatility Snapshot",
        target_audience_en="Technical Traders & Market Momentum",
        target_audience_he="סוחרים טכניים ותזמון מגמות מחיר",
        icon="📊",
        description="Generates candlestick trends, moving averages, and ATR volatility.",
    ),
    "fundamental_check": AlgorithmMetadata(
        key="fundamental_check",
        script_path=str(_ALGORITHMS_DIR / "fundamental_check_algo.py"),
        title="Deep Solvency & Balance Sheet Audit (V7)",
        target_audience_en="Deep Value & Risk-Averse Investors",
        target_audience_he="משקיעי ערך, איכות מאזן ומניעת סיכונים",
        icon="🔍",
        description="Runs 40+ forensic tests: Piotroski F-score, Altman Z'', and Beneish M-score.",
    ),
}

# Backward compatibility map: name -> script_path
bot_responses_algorithms = {k: v.script_path for k, v in ALGORITHM_REGISTRY.items()}
