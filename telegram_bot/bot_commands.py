from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

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


# Persistent keyboard button shown above the input box; tapping it sends
# BUTTON_TEXT as a normal message, which handle_symbol maps to /settings.
BUTTON_TEXT = "⚙ Settings"
SETTINGS_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(BUTTON_TEXT)]], resize_keyboard=True, is_persistent=False
)


def _start(message: str, chat_id: int):
    return (
        "Send a stock ticker (e.g. JNJ) or a TASE security number (e.g. 1081124).\n"
        "Use the Settings button to choose which algorithms run.",
        SETTINGS_KEYBOARD,
    )


COMMANDS = {
    "start": _start,
    "settings": _config_menu,
    "config": _config_menu,
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
