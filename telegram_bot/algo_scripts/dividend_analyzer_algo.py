"""Dividend-value dashboard chart. Standalone: `python dividend_analyzer_algo.py SYMBOL`."""

import sys
import tempfile
from pathlib import Path

# telegram_bot/algorithms and dividend-analyzer are sibling repo checkouts
# in the PC dev layout, but on deploy targets this file ends up nested
# inside dividend-analyzer's own telegram_bot/algorithms/ folder --
# resolved relative to this file either way.
_parent = Path(__file__).resolve().parent.parent.parent
DIVIDEND_ANALYZER_PATH = _parent if (_parent / ".claude").exists() else (_parent / "dividend-analyzer")
sys.path.insert(0, str(DIVIDEND_ANALYZER_PATH))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dividend_analyzer import AlgorithmVersion, DataFetcher, get_algorithm
from dividend_analyzer.visualization.charts import plot_stock_dashboard

fetcher = DataFetcher()
algorithm = get_algorithm(AlgorithmVersion.V5_DIVIDEND_VALUE)


def respond(symbol: str) -> str:
    history, info = fetcher.fetch_stock_data(symbol)
    if history is None or history.empty or info is None:
        return f"No data found for '{symbol}'."

    benchmark_yield = fetcher.get_benchmark_dividend_yield()
    result = algorithm.analyze(symbol, history, info, benchmark_yield)

    out_path = Path(tempfile.gettempdir()) / f"{symbol}_dashboard.png"
    fig = plot_stock_dashboard(result, history, output_path=out_path)
    if fig is not None:
        plt.close(fig)
    return f"![{out_path}]"


if __name__ == "__main__":
    print(respond(sys.argv[1]))
