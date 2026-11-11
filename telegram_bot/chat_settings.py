"""Per-chat settings: which algorithms are enabled. Stored in chat_settings.json."""
import json
from pathlib import Path

from algorithms import bot_responses_algorithms

SETTINGS_FILE = Path(__file__).resolve().parent / "chat_settings.json"


def _load() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def has_saved_settings(chat_id: int) -> bool:
    return str(chat_id) in _load()


def get_enabled_algorithms(chat_id: int) -> list[str]:
    """Enabled algorithm names for a chat, in registration order (default: all)."""
    saved = _load().get(str(chat_id))
    if saved is None:
        return list(bot_responses_algorithms)
    return [name for name in bot_responses_algorithms if name in saved]


def set_enabled_algorithms(chat_id: int, names: list[str]) -> None:
    data = _load()
    data[str(chat_id)] = [n for n in bot_responses_algorithms if n in names]
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
