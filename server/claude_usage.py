"""Claude plan usage (5-hour session and weekly limits) for the dashboard.

Every 5 minutes the server asks Anthropic for the numbers, using the login that Claude saves on this PC. The limits
are shared by the desktop app, the terminal and claude.ai, so this is right whichever one is used.
Claude Code's status line (terminal only) also saves its readings here, as a backup.
"""

import datetime
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
USAGE_FILE = PROJECT_DIR / "data" / "claude-usage.json"
CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
WINDOWS = ("five_hour", "seven_day")

REFRESH_SECONDS = 5 * 60  # Asking every minute made Anthropic refuse for a while (HTTP 429).
RETRY_SECONDS = 5 * 60
LONGEST_WAIT_SECONDS = 30 * 60  # When refused, each wait doubles up to this, so the block can wear off.
TIMEOUT_SECONDS = 15
STALE_SECONDS = 60 * 60  # Older readings could be wrong, so the page shows "—" instead.
RATE_LIMITED = "Anthropic asked the dashboard to slow down (HTTP 429)."

_status = {"problem": "Starting"}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never follows a redirect, so the login key can only ever be sent to Anthropic itself."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirects)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _window(used, resets_at):
    """Returns {"used", "resets_at"} if both are numbers, otherwise None."""
    if not (_is_number(used) and _is_number(resets_at)):
        return None
    return {"used": float(used), "resets_at": float(resets_at)}


def _parse_time(text):
    """Turns a time like "2026-11-09T14:30:00.556588+00:00" into seconds since 1970, or None."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"Z$", "+00:00", text.strip())
    # Older Python only understands 3 or 6 digits after the seconds' decimal point.
    text = re.sub(r"\.(\d+)", lambda match: "." + match.group(1)[:6].ljust(6, "0"), text, count=1)
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.timestamp()


def windows_from_statusline(data):
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    if not isinstance(limits, dict):
        return {}
    fresh = {}
    for name in WINDOWS:
        raw = limits.get(name) if isinstance(limits.get(name), dict) else {}
        fresh[name] = _window(raw.get("used_percentage"), raw.get("resets_at"))
    return {name: window for name, window in fresh.items() if window}


def windows_from_api(data):
    if not isinstance(data, dict):
        return {}
    fresh = {}
    for name in WINDOWS:
        raw = data.get(name) if isinstance(data.get(name), dict) else {}
        fresh[name] = _window(raw.get("utilization"), _parse_time(raw.get("resets_at")))
    return {name: window for name, window in fresh.items() if window}


def _load():
    try:
        saved = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def _save(fresh, now):
    """Keeps the newest reading of each window. Windows missing from this update keep their last reading."""
    if not fresh:
        return False
    saved = _load()
    saved.update(fresh)
    saved["updated"] = time.time() if now is None else now
    USAGE_FILE.parent.mkdir(exist_ok=True)
    # Each program writes its own temporary file, so the server and Claude Code can't trip over each other.
    temporary = USAGE_FILE.with_name(f"{USAGE_FILE.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(saved), encoding="utf-8")
    os.replace(temporary, USAGE_FILE)
    return True


def save_from_statusline(data, now=None):
    return _save(windows_from_statusline(data), now)


def read_usage(now=None):
    """What the page shows. Old readings, and windows whose reset time has passed, show as unknown."""
    now = time.time() if now is None else now
    saved = _load()
    updated = saved.get("updated")
    if not _is_number(updated) or now - updated > STALE_SECONDS:
        return {name: None for name in WINDOWS}
    result = {}
    for name in WINDOWS:
        stored = saved.get(name) if isinstance(saved.get(name), dict) else {}
        window = _window(stored.get("used"), stored.get("resets_at"))
        result[name] = window if window and window["resets_at"] > now else None
    return result


def read_access_token(now=None):
    """Returns (login key, None), or (None, what's wrong). The key is only ever sent to Anthropic."""
    now = time.time() if now is None else now
    try:
        credentials = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "No Claude login found on this PC: sign in to Claude first."
    except (OSError, ValueError) as error:
        return None, f"Couldn't read the Claude login file: {error}"
    login = credentials.get("claudeAiOauth") if isinstance(credentials, dict) else None
    token = login.get("accessToken") if isinstance(login, dict) else None
    if not isinstance(token, str) or not token:
        return None, "No Claude login found on this PC: sign in to Claude first."
    expires_at = login.get("expiresAt")
    if _is_number(expires_at) and expires_at / 1000 <= now:
        return None, "The Claude login has expired: open Claude (desktop app or terminal) to renew it."
    return token, None


def _fetch(token):
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
        "User-Agent": "Personal-Dashboard",
    })
    with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def _describe(error):
    if isinstance(error, urllib.error.HTTPError):
        if error.code in (401, 403):
            return f"Anthropic refused the Claude login (HTTP {error.code}): open Claude to renew it."
        if error.code == 429:
            return RATE_LIMITED
    return f"Couldn't read Claude usage: {error}"


def refresh(now=None):
    """Asks Anthropic for fresh numbers and saves them. Returns what went wrong, or None if it worked."""
    token, problem = read_access_token(now)
    if problem:
        return problem
    try:
        fresh = windows_from_api(_fetch(token))
    except (OSError, ValueError, http.client.HTTPException) as error:
        return _describe(error)
    if not fresh:
        return "Anthropic's reply had no usage numbers in it."
    try:
        _save(fresh, now)
    except OSError as error:
        return f"Couldn't save Claude usage: {error}"
    return None


def start():
    threading.Thread(target=_run, daemon=True).start()


def read_status():
    return _status


def next_wait(problem, last_wait):
    """How long to wait before asking again. Each refusal in a row doubles the wait."""
    if problem is None:
        return REFRESH_SECONDS
    if problem == RATE_LIMITED:
        return min(max(last_wait * 2, RETRY_SECONDS), LONGEST_WAIT_SECONDS)
    return RETRY_SECONDS


def _run():
    global _status
    last_problem = "Starting"
    wait = 0
    while True:
        try:
            problem = refresh()
        except Exception as error:  # This thread must keep running whatever goes wrong.
            problem = f"Unexpected problem: {error}"
        _status = {"problem": problem}
        if problem != last_problem:
            last_problem = problem
            print(f"Claude usage: {problem or 'connected.'}", flush=True)
        wait = next_wait(problem, wait)
        time.sleep(wait)
