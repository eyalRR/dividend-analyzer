"""Local-only helper to broadcast a message to every chat that has talked to the bot.

Not exposed as a Telegram command -- call send_broadcast() from a local
Python session or script, or run this file directly:

    python broadcast.py "message text"
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from telegram import Bot

from chat_registry import load_chat_ids

load_dotenv()


async def _broadcast_async(text: str) -> None:
    chat_ids = load_chat_ids()
    if not chat_ids:
        print("No known chats to broadcast to yet.")
        return

    bot = Bot(os.environ["TELEGRAM_BOT_TOKEN"])
    sent, failed = 0, 0
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except Exception as exc:
            failed += 1
            print(f"Failed to send to {chat_id}: {exc}")
    print(f"Broadcast done: {sent} sent, {failed} failed.")


def send_broadcast(text: str) -> None:
    """Send `text` to every chat ID recorded in broadcast_users.txt."""
    asyncio.run(_broadcast_async(text))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python broadcast.py "message text"')
        sys.exit(1)
    send_broadcast(sys.argv[1])
