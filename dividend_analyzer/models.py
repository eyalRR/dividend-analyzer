"""Data models representing stock analysis results and metric breakdowns.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

@dataclass
class MissingDividend:
    date: str
    expected_amount: Optional[float] = None
    reason: str = "Missed regular dividend schedule"

@dataclass
class StockData:
    """Raw fetched data for a stock."""
    symbol: str
    history: Any  # pd.DataFrame
    info: Dict[str, Any]
    fetched_at: datetime = field(default_factory=datetime.now)

@dataclass
class StockAnalysisResult:
    """Comprehensive result of a stock dividend analysis."""
    symbol: str
    algorithm_version: str
    final_score: float
    initial_score: float = 0.0
    penalties: float = 0.0
    current_price: float = 0.0
    company_name: str = ""
    conditions: Dict[str, float] = field(default_factory=dict)
    raw_scores: Dict[str, float] = field(default_factory=dict)
    thresholds: Dict[str, Tuple[float, str]] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    missing_dividends: List[str] = field(default_factory=list)
    annual_dividends: Dict[int, float] = field(default_factory=dict)
    analysis_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary."""
        return asdict(self)
