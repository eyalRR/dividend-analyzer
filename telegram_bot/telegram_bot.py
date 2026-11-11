import asyncio
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import yfinance as yf
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from algorithms import bot_responses_algorithms
from bot_commands import bot_commands_handler
from chat_logger import log_message
from chat_registry import register_chat
from tase_symbols import resolve_symbol

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4000
ALGORITHM_TIMEOUT = 300
IMAGE_TAG_RE = re.compile(r"!\[([^\]]+)\]")
# "/word" anywhere in the message (optionally "/word@botname")
COMMAND_RE = re.compile(r"(?:^|\s)/(\w+)(?:@\w+)?")


def symbol_exists(symbol: str) -> bool:
    return not yf.Ticker(symbol).history(period="5d").empty


def run_algorithm(script_path: str, symbol: str) -> str:
    """Runs one algorithms/*.py script as a subprocess and returns its stdout text."""
    proc = subprocess.run(
        [sys.executable, script_path, symbol],
        capture_output=True,
        timeout=ALGORITHM_TIMEOUT,
        encoding="utf-8",
        errors="replace",
    )
    text = (proc.stdout or "").strip()
    if not text:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        text = stderr_lines[-1] if stderr_lines else "No output."
    return text


async def send_algorithm_reply(update: Update, text: str) -> None:
    """Sends `text`, converting any `![path/to/image.png]` tags into actual photos."""
    pos = 0
    for match in IMAGE_TAG_RE.finditer(text):
        before = text[pos : match.start()].strip()
        if before:
            await send_long_text(update, before)

        image_path = Path(match.group(1))
        if image_path.is_file():
            with open(image_path, "rb") as photo:
                await update.message.reply_photo(photo.read())
            image_path.unlink(missing_ok=True)
        else:
            logger.warning("Image tag pointed at a missing file: %s", image_path)
        pos = match.end()

    tail = text[pos:].strip()
    if tail:
        await send_long_text(update, tail)


async def send_long_text(update: Update, text: str) -> None:
    for i in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        await update.message.reply_text(text[i : i + TELEGRAM_MESSAGE_LIMIT])


async def run_named_algorithm(loop, name: str, script_path: str, symbol: str) -> tuple[str, str]:
    try:
        text = await loop.run_in_executor(None, run_algorithm, script_path, symbol)
    except subprocess.TimeoutExpired:
        text = f"{name} timed out."
    except Exception as exc:
        logger.exception("Algorithm '%s' failed for %s", name, symbol)
        text = f"{name} failed: {exc}"
    return name, text


async def handle_symbol(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    register_chat(chat_id)
    log_message(chat_id, "user", update.message.text)

    cmd_match = COMMAND_RE.search(update.message.text)
    if cmd_match:
        reply = bot_commands_handler(cmd_match.group(1).lower(), update.message.text)
        await send_long_text(update, reply)
        log_message(chat_id, "bot", reply)
        return

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

    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, symbol_exists, symbol):
        reply = f"No data found for '{symbol}'. Check the ticker symbol."
        await update.message.reply_text(reply)
        log_message(chat_id, "bot", reply)
        return

    await update.message.reply_text(f"Analyzing {symbol}...")

    tasks = [
        run_named_algorithm(loop, name, script_path, symbol)
        for name, script_path in bot_responses_algorithms.items()
    ]
    # Run all algorithms in parallel, but wait for every one of them before
    # sending anything -- so a reply's upload never competes with a
    # still-running algorithm for CPU/network, and replies are sent in
    # registration order rather than whichever happens to finish first.
    results = await asyncio.gather(*tasks)
    for name, text in results:
        try:
            await send_algorithm_reply(update, text)
        except Exception:
            logger.exception("Failed to send '%s' reply for %s", name, symbol)
        log_message(chat_id, "bot", f"[{name}] {text}")


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = (
        Application.builder()
        .token(token)
        .read_timeout(30)
        .write_timeout(30)
        # Photo uploads use this, not write_timeout -- PTB defaults it to 20s,
        # which a ~200KB chart can exceed on a slow uplink.
        .media_write_timeout(120)
        .connect_timeout(30)
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT, handle_symbol))
    app.run_polling()


if __name__ == "__main__":
    main()
