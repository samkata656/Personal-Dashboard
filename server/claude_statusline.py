"""Claude Code runs this as its status line. It saves the plan usage for the dashboard and prints a short summary.

Claude Code sends the session details as JSON on stdin. This must never fail loudly: a broken status line is
annoying, and the dashboard simply keeps its last numbers.
"""

import json
import sys

import claude_usage


def summary(data):
    parts = []
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    if isinstance(limits, dict):
        for name, label in (("five_hour", "session"), ("seven_day", "week")):
            used = (limits.get(name) or {}).get("used_percentage") if isinstance(limits.get(name), dict) else None
            if isinstance(used, (int, float)):
                parts.append(f"{label} {used:.0f}%")
    return " · ".join(parts) or "Claude usage: waiting for the first reply"


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # Claude Code reads UTF-8; Windows would otherwise garble the "·".
    try:
        data = json.loads(sys.stdin.buffer.read() or b"{}")
    except ValueError:
        data = {}
    try:
        claude_usage.save_from_statusline(data)
    except OSError:
        pass
    print(summary(data))


if __name__ == "__main__":
    main()
