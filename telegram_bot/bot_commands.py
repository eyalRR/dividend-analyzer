from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

from algorithms import ALGORITHM_REGISTRY, bot_responses_algorithms
from chat_settings import get_enabled_algorithms

TOGGLE_PREFIX = "toggle:"
SAVE_DATA = "save"
MENU_TEXT = "בחר אילו מנועים ירוצו עבורך (לחץ לשינוי ואז על Save):"


def build_menu(selected: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{'☑ ' if name in selected else '☐ '}{meta.icon} {meta.target_audience_he}",
                callback_data=TOGGLE_PREFIX + name,
            )
        ]
        for name, meta in ALGORITHM_REGISTRY.items()
    ]
    rows.append([InlineKeyboardButton("💾 Save", callback_data=SAVE_DATA)])
    return InlineKeyboardMarkup(rows)


def _config_menu(message: str, chat_id: int):
    return MENU_TEXT, build_menu(get_enabled_algorithms(chat_id))




HELP_TEXT = (
    "שלח סימול מניה (למשל JNJ) או מספר נייר בבורסה בתל אביב (למשל 1081124) "
    "והבוט יריץ את המנועים שנבחרו עבורך.\n\n"
    "קהלי היעד והמנועים הזמינים:\n"
    "• 💰 משקיעי דיבידנד ותזרים (V5 Dividend Compounding)\n"
    "• 📊 סוחרים טכניים ותזמון (Technical Trends & Volatility)\n"
    "• 🔍 משקיעי ערך ואיתנות (V7 Deep Solvency & Health)\n\n"
    "פקודות:\n"
    "/settings - בחירת המנועים המותאמים לך (ולחיצה על שמירה)\n"
    "/start - הצגת תפריט העזרה הזה"
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
