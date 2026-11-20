import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from chat_logger import log_message
from chat_registry import register_chat

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

SAMPLE_IMAGE = Path(__file__).parent / "assets" / "sample.jpg"
RECEIVED_DIR = Path(__file__).parent / "received_images"


async def echo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    register_chat(chat_id)
    log_message(chat_id, "user", update.message.text)

    if update.message.text.strip().lower() == "image":
        await update.message.reply_photo(SAMPLE_IMAGE.read_bytes())
    else:
        await update.message.reply_text(update.message.text)
        log_message(chat_id, "bot", update.message.text)


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return

    register_chat(update.effective_chat.id)

    RECEIVED_DIR.mkdir(exist_ok=True)
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    dest = RECEIVED_DIR / f"{photo.file_unique_id}.jpg"
    await file.download_to_drive(dest)
    await update.message.reply_text("Got your image!")


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    app.run_polling()


if __name__ == "__main__":
    main()
