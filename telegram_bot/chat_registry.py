"""Shared registry of chat IDs that have messaged any of the bots in this project.

Both bot scripts record every chat that talks to them into one file
(broadcast_users.txt), since they share the same bot token and are never
run at the same time. broadcast.py reads this file to know who to message.
"""
from pathlib import Path

BROADCAST_FILE = Path(__file__).parent / "broadcast_users.txt"


def register_chat(chat_id: int) -> None:
    chat_ids = load_chat_ids()
    if chat_id in chat_ids:
        return
    chat_ids.add(chat_id)
    BROADCAST_FILE.write_text(
        "\n".join(str(cid) for cid in sorted(chat_ids)) + "\n", encoding="utf-8"
    )


def load_chat_ids() -> set[int]:
    if not BROADCAST_FILE.exists():
        return set()
    lines = BROADCAST_FILE.read_text(encoding="utf-8").splitlines()
    return {int(line) for line in lines if line.strip()}
