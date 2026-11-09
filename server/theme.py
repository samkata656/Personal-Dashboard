"""Remembers which colors the dashboard uses, so the choice survives restarts."""

import json
import os
import threading
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
THEME_FILE = PROJECT_DIR / "data" / "theme.json"
THEMES = ("mono", "neon")
DEFAULT_THEME = "mono"

_lock = threading.Lock()
_current = None


def _load():
    try:
        theme = json.loads(THEME_FILE.read_text(encoding="utf-8"))["theme"]
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_THEME
    return theme if theme in THEMES else DEFAULT_THEME


def read_theme():
    # Kept in memory because the page asks often, and Windows can't replace a file while it's being read.
    global _current
    with _lock:
        if _current is None:
            _current = _load()
        return _current


def set_theme(theme):
    global _current
    if theme not in THEMES:
        raise ValueError(f"Unknown theme: {theme}")
    with _lock:
        THEME_FILE.parent.mkdir(exist_ok=True)
        temporary = THEME_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps({"theme": theme}), encoding="utf-8")
        os.replace(temporary, THEME_FILE)
        _current = theme
