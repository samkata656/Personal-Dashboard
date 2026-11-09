"""Reads secrets from the .env file. It's read fresh each time, so edits work without a restart."""

from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def parse_env(text):
    """Reads KEY=value lines, ignoring blank lines and # comments."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip("\"'")
    return values


def read_secret(name, placeholder):
    """Returns the value, or None if it's missing or still the placeholder text."""
    try:
        # utf-8-sig copes with the invisible marker some Windows editors add to the start of a file.
        value = parse_env(ENV_FILE.read_text(encoding="utf-8-sig")).get(name, "")
    except (OSError, UnicodeError):
        return None
    return value if value and value != placeholder else None
