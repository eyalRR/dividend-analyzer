"""Registry of algorithms telegram_bot.py dispatches a symbol to.

Add a new algorithm by dropping a standalone script in algo_scripts/
(it must accept a symbol as its one CLI argument, print a text response
to stdout, and embed any image file it produced as
`![path/to/image.png]` somewhere in that text) and registering it here.

(The scripts live in algo_scripts/, not algorithms/, so this module
doesn't collide with a same-named package directory.)
"""

from pathlib import Path

_ALGORITHMS_DIR = Path(__file__).resolve().parent / "algo_scripts"

bot_responses_algorithms = {
    "dividend_analyzer": str(_ALGORITHMS_DIR / "dividend_analyzer_algo.py"),
    "stock_overview": str(_ALGORITHMS_DIR / "stock_overview_algo.py"),
    "fundamental_check": str(_ALGORITHMS_DIR / "fundamental_check_algo.py"),
}
