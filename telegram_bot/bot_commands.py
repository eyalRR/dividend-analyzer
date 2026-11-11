from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

from algorithms import bot_responses_algorithms
from chat_settings import get_enabled_algorithms

TOGGLE_PREFIX = "toggle:"
SAVE_DATA = "save"
MENU_TEXT = "Choose algorithms to run (tap to toggle, then Save):"


def build_menu(selected: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(("☑ " if name in selected else "☐ ") + name, callback_data=TOGGLE_PREFIX + name)]
        for name in bot_responses_algorithms
    ]
    rows.append([InlineKeyboardButton("💾 Save", callback_data=SAVE_DATA)])
    return InlineKeyboardMarkup(rows)


def _config_menu(message: str, chat_id: int):
    return MENU_TEXT, build_menu(get_enabled_algorithms(chat_id))




HELP_TEXT = (
    "Send a stock ticker (e.g. JNJ) or a TASE security number (e.g. 1081124) "
    "and I'll run the selected algorithms on it.\n\n"
    "Commands:\n"
    "/settings - choose which algorithms run (then press Save)\n"
    "/start - show this help\n\n"
    "Send /settings and press Save to get started."
)


def help_reply():
    # ReplyKeyboardRemove clears the old Settings keyboard from chats that still have it.
    return HELP_TEXT, ReplyKeyboardRemove()


def _start(message: str, chat_id: int):
    return help_reply()


COMMANDS = {
    "start": _start,
    "settings": _config_menu,
}


def bot_commands_handler(cmd: str, message: str, chat_id: int):
    """Handles a /command found in a user message. `cmd` is the word after the
    slash (lowercase, no '@botname'); `message` is the full original text.
    Returns (text, reply_markup_or_None)."""
    handler = COMMANDS.get(cmd)
    if handler is None:
        known = ", ".join("/" + c for c in COMMANDS)
        return f"Unknown command /{cmd}. Available: {known}", None
    return handler(message, chat_id)
