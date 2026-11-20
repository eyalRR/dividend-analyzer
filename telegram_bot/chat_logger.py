"""Per-user chat history logging, text only.

Appends one line per text message to logs/<chat_id>.log. Images are
intentionally not logged -- only text exchanged with each user.
"""
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"


def log_message(chat_id: int, sender: str, text: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{chat_id}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {sender}: {text}\n")
