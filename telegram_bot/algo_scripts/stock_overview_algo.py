"""Weekly/daily candles + change-table + ATR14 snapshot.
Standalone: `python stock_overview_algo.py SYMBOL`.

Target Audience:
- English: Technical Traders & Market Momentum
- Hebrew: סוחרים טכניים ותזמון מגמות מחיר
Focus: Price trends, candlestick patterns, moving averages, and ATR volatility.
"""

import sys
import tempfile
from pathlib import Path

# stock_snapshot.py lives one level up, at the telegram_bot/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_snapshot import build_snapshot


def respond(symbol: str) -> str:
    out_path = Path(tempfile.gettempdir()) / f"{symbol}_overview.png"
    build_snapshot(symbol, str(out_path))
    return f"![{out_path}]"


if __name__ == "__main__":
    print(respond(sys.argv[1]))
