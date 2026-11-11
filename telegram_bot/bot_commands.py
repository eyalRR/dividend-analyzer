from algorithms import bot_responses_algorithms


def _list_algorithms(message: str) -> str:
    names = list(bot_responses_algorithms)
    lines = [f"{i}. {name}" for i, name in enumerate(names, 1)]
    return "Active algorithms:\n" + "\n".join(lines)


COMMANDS = {
    "settings": _list_algorithms,
    "config": _list_algorithms,
}


def bot_commands_handler(cmd: str, message: str) -> str:
    """Handles a /command found in a user message. `cmd` is the word after the
    slash (lowercase, no '@botname'); `message` is the full original text."""
    handler = COMMANDS.get(cmd)
    if handler is None:
        known = ", ".join("/" + c for c in COMMANDS)
        return f"Unknown command /{cmd}. Available: {known}"
    return handler(message)
