"""Runs the vendored fundamental_check.py skill. Standalone: `python fundamental_check_algo.py SYMBOL`."""

import os
import subprocess
import sys
from pathlib import Path

_parent = Path(__file__).resolve().parent.parent.parent
DIVIDEND_ANALYZER_PATH = _parent if (_parent / ".claude").exists() else (_parent / "dividend-analyzer")
FUNDAMENTAL_CHECK = DIVIDEND_ANALYZER_PATH / ".claude" / "skills" / "fundamental-check" / "fundamental_check.py"


def respond(symbol: str, timeout: int = 300) -> str:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            [sys.executable, str(FUNDAMENTAL_CHECK), symbol],
            capture_output=True,
            timeout=timeout,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return "Fundamental check timed out."

    lines = [
        ln
        for ln in (proc.stdout or "").splitlines()
        if not ln.startswith("JSON: ") and not ln.startswith("TXT: ")
    ]
    report = "\n".join(lines).strip()
    if not report:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        report = stderr_lines[0] if stderr_lines else "No output from fundamental check."
    return report


if __name__ == "__main__":
    print(respond(sys.argv[1]))
