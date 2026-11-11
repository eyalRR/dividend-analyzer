import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from chat_logger import log_message
from chat_registry import register_chat
from tase_symbols import resolve_symbol

load_dotenv()

# telegram_bot and dividend-analyzer are sibling repo checkouts -- resolved
# relative to this file so it works on any machine without configuration.
_parent = Path(__file__).resolve().parent.parent
DIVIDEND_ANALYZER_PATH = _parent if (_parent / ".claude").exists() else (_parent / "dividend-analyzer")
sys.path.insert(0, str(DIVIDEND_ANALYZER_PATH))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dividend_analyzer import AlgorithmVersion, DataFetcher, get_algorithm
from dividend_analyzer.visualization.charts import plot_stock_dashboard
from stock_snapshot import build_snapshot as build_stock_overview_image

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

fetcher = DataFetcher()
algorithm = get_algorithm(AlgorithmVersion.V5_DIVIDEND_VALUE)

FUNDAMENTAL_CHECK = DIVIDEND_ANALYZER_PATH / ".claude" / "skills" / "fundamental-check" / "fundamental_check.py"
TELEGRAM_MESSAGE_LIMIT = 4000


def build_report_image(symbol: str, history, info) -> Path:
    """Score the symbol and render the dashboard PNG. Runs in a worker thread."""
    benchmark_yield = fetcher.get_benchmark_dividend_yield()
    result = algorithm.analyze(symbol, history, info, benchmark_yield)

    out_path = Path(tempfile.gettempdir()) / f"{symbol}_dashboard.png"
    fig = plot_stock_dashboard(result, history, output_path=out_path)
    if fig is not None:
        plt.close(fig)
    return out_path


def build_stock_overview(symbol: str) -> Path:
    """Weekly/daily candles + change-table + ATR14 snapshot. Runs in a worker thread."""
    out_path = Path(tempfile.gettempdir()) / f"{symbol}_overview.png"
    build_stock_overview_image(symbol, str(out_path))
    return out_path


def run_fundamental_check_report(symbol: str, history, info, timeout: int = 300) -> str:
    """Run the vendored fundamental_check.py skill and return its markdown report text."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    tmp_info_path = tmp_hist_path = None
    try:
        if info:
            fd, tmp_info_path = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            Path(tmp_info_path).write_text(json.dumps(info, default=str), encoding="utf-8")
            env["FUNDCHECK_PREFETCH_INFO"] = tmp_info_path
        if history is not None and not history.empty:
            fd, tmp_hist_path = tempfile.mkstemp(suffix=".pkl")
            os.close(fd)
            history.to_pickle(tmp_hist_path)
            env["FUNDCHECK_PREFETCH_HISTORY"] = tmp_hist_path

        proc = subprocess.run(
            [sys.executable, str(FUNDAMENTAL_CHECK), symbol],
            capture_output=True,
            timeout=timeout,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        lines = [
            ln
            for ln in (proc.stdout or "").splitlines()
            if not ln.startswith("JSON: ") and not ln.startswith("TXT: ")
        ]
        report = "\n".join(lines).strip()
        if not report:
            stderr_lines = (proc.stderr or "").strip().splitlines()
            report = stderr_lines[0] if stderr_lines else "No output from fundamental check."
        return report
    except subprocess.TimeoutExpired:
        return "Fundamental check timed out."
    finally:
        for p in (tmp_info_path, tmp_hist_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


async def send_long_text(update: Update, text: str) -> None:
    for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        await update.message.reply_text(text[i : i + TELEGRAM_MESSAGE_LIMIT])


async def handle_symbol(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    register_chat(chat_id)
    log_message(chat_id, "user", update.message.text)

    raw_symbol = update.message.text.strip().upper()
    if not (1 <= len(raw_symbol) <= 10) or not raw_symbol.replace(".", "").replace("-", "").isalnum():
        reply = "Send a stock ticker symbol, e.g. JNJ, or a TASE security number, e.g. 1081124"
        await update.message.reply_text(reply)
        log_message(chat_id, "bot", reply)
        return

    try:
        symbol = resolve_symbol(raw_symbol)
    except ValueError as exc:
        reply = str(exc)
        await update.message.reply_text(reply)
        log_message(chat_id, "bot", reply)
        return

    await update.message.reply_text(f"Analyzing {symbol}...")
    loop = asyncio.get_running_loop()
    try:
        history, info = await loop.run_in_executor(None, fetcher.fetch_stock_data, symbol)
        if history is None or history.empty or info is None:
            reply = f"No data found for '{symbol}'. Check the ticker symbol."
            await update.message.reply_text(reply)
            log_message(chat_id, "bot", reply)
            return

        chart_path, overview_path, fundamentals_report = await asyncio.gather(
            loop.run_in_executor(None, build_report_image, symbol, history, info),
            loop.run_in_executor(None, build_stock_overview, symbol),
            loop.run_in_executor(None, run_fundamental_check_report, symbol, history, info),
            return_exceptions=True,
        )

        if isinstance(chart_path, Exception):
            raise chart_path
        with open(chart_path, "rb") as photo:
            await update.message.reply_photo(photo.read())
        chart_path.unlink(missing_ok=True)

        # Overview chart is a nice-to-have on top of the dividend dashboard --
        # don't let a failure here (e.g. a transient yfinance hiccup) block
        # the main report, which already succeeded by this point.
        if isinstance(overview_path, Exception):
            logger.warning("Stock overview failed for %s: %s", symbol, overview_path)
        else:
            with open(overview_path, "rb") as photo:
                await update.message.reply_photo(photo.read())
            overview_path.unlink(missing_ok=True)

        if isinstance(fundamentals_report, Exception):
            raise fundamentals_report
        await send_long_text(update, fundamentals_report)
        log_message(chat_id, "bot", fundamentals_report)
    except Exception as exc:
        logger.exception("Failed to build report for %s", symbol)
        reply = f"Couldn't analyze {symbol}: {exc}"
        await update.message.reply_text(reply)
        log_message(chat_id, "bot", reply)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = (
        Application.builder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_symbol))
    app.run_polling()


if __name__ == "__main__":
    main()
