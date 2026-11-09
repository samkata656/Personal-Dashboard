"""Reads OpenRouter credits and spending, and saves one usage snapshot per day to a local file."""

import datetime
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import env_file

API_URL = "https://openrouter.ai/api/v1"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SNAPSHOT_FILE = PROJECT_DIR / "data" / "openrouter-usage.json"
KEY_NAME = "OPENROUTER_MANAGEMENT_KEY"
KEY_PLACEHOLDER = "paste-your-management-key-here"

REFRESH_SECONDS = 5 * 60
RETRY_SECONDS = 60  # After a failure, try again sooner so the widget recovers quickly.
TIMEOUT_SECONDS = 15
SNAPSHOT_DAYS_KEPT = 14
DAYS_SHOWN = 7
DAY_LETTERS = "MTWTFSS"

_state = {"online": False, "credits": None, "spent": None, "days": [], "last_updated": None, "problem": "Starting"}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never follows a redirect, so the key can only ever be sent to OpenRouter itself."""

    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirects)


def start():
    threading.Thread(target=_run, daemon=True).start()


def read_openrouter():
    return _state


def load_snapshots():
    try:
        snapshots = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return snapshots if isinstance(snapshots, dict) else {}


def save_snapshots(snapshots):
    SNAPSHOT_FILE.parent.mkdir(exist_ok=True)
    # Writing to a temporary file first means a crash can't leave a half-written snapshot file.
    temporary = SNAPSHOT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshots, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, SNAPSHOT_FILE)


def record_snapshot(snapshots, today, total_usage):
    """Keeps the first reading of each UTC day. Returns a new set of snapshots, or None if unchanged."""
    key = today.isoformat()
    if key in snapshots:
        return None
    oldest_kept = (today - datetime.timedelta(days=SNAPSHOT_DAYS_KEPT)).isoformat()
    kept = {day: usage for day, usage in snapshots.items() if day >= oldest_kept}
    kept[key] = total_usage
    return kept


def daily_activity(rows):
    """Adds up each day's rows. OpenRouter reports one row per model per provider."""
    totals = {}
    for row in rows:
        date = str(row.get("date", ""))[:10]
        totals[date] = totals.get(date, 0.0) + float(row.get("usage") or 0)
    return totals


def spend_for_day(day, today, activity, snapshots, total_usage):
    key = day.isoformat()
    if day == today:
        # OpenRouter only reports finished days, so today comes from the morning snapshot.
        since_snapshot = total_usage - snapshots.get(key, total_usage)
        return max(since_snapshot, activity.get(key, 0.0), 0.0)
    if key in activity:
        return activity[key]
    # A finished day that OpenRouter hasn't reported yet: use the snapshots either side of it.
    next_key = (day + datetime.timedelta(days=1)).isoformat()
    if key in snapshots and next_key in snapshots:
        return max(snapshots[next_key] - snapshots[key], 0.0)
    return 0.0


def last_seven_days(today, activity, snapshots, total_usage):
    """Returns [letter, amount] pairs, oldest first, with today last."""
    days = []
    for days_ago in range(DAYS_SHOWN - 1, -1, -1):
        day = today - datetime.timedelta(days=days_ago)
        days.append([DAY_LETTERS[day.weekday()], spend_for_day(day, today, activity, snapshots, total_usage)])
    return days


def _fetch(path, key):
    request = urllib.request.Request(
        f"{API_URL}/{path}",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": "Personal-Dashboard"},
    )
    with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)["data"]


def _describe(error):
    if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403):
        return f"OpenRouter refused the key (HTTP {error.code}). It must be a valid management key."
    return f"Couldn't read OpenRouter: {error}"


def _set_offline(problem):
    global _state
    if problem != _state["problem"]:
        print(f"OpenRouter: {problem}", flush=True)
    _state = {**_state, "online": False, "credits": None, "spent": None, "days": [], "problem": problem}


def refresh():
    """Fetches fresh numbers. Returns True if everything worked."""
    global _state
    key = env_file.read_secret(KEY_NAME, KEY_PLACEHOLDER)
    if key is None:
        _set_offline(f"No key yet: add {KEY_NAME} to the .env file.")
        return False

    try:
        credits = _fetch("credits", key)
        total_usage = float(credits["total_usage"])
        balance = float(credits["total_credits"]) - total_usage
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        _set_offline(_describe(error))
        return False

    today = datetime.datetime.now(datetime.timezone.utc).date()
    snapshots = load_snapshots()
    updated = record_snapshot(snapshots, today, total_usage)
    if updated is not None:
        snapshots = updated
        try:
            save_snapshots(snapshots)
        except OSError as error:
            print(f"OpenRouter: couldn't save the usage snapshot: {error}", flush=True)

    problem = None
    try:
        activity = daily_activity(_fetch("activity", key))
        days = last_seven_days(today, activity, snapshots, total_usage)
        spent = sum(amount for _, amount in days)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException) as error:
        # The balance is still good, so keep showing it and only blank out the spending.
        problem = _describe(error)
        print(f"OpenRouter: {problem}", flush=True)
        days, spent = [], None

    if _state["problem"] and problem is None:
        print("OpenRouter: connected.", flush=True)
    _state = {
        "online": True,
        "credits": balance,
        "spent": spent,
        "days": days,
        "last_updated": time.time(),
        "problem": problem,
    }
    return problem is None


def _run():
    while True:
        try:
            succeeded = refresh()
        except Exception as error:  # This thread must keep running whatever goes wrong.
            _set_offline(f"Unexpected problem: {error}")
            succeeded = False
        time.sleep(REFRESH_SECONDS if succeeded else RETRY_SECONDS)
