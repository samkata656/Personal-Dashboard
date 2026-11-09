"""Starts the dashboard server and then OBS. Windows runs this once at login, and then it exits."""

import datetime
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from obs_switcher import OBS_PROCESS, running_process_names

PROJECT_DIR = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = PROJECT_DIR / "server" / "main.py"
LOG_FILE = PROJECT_DIR / "data" / "dashboard.log"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8787

OBS_EXE = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
OBS_ARGS = ["--minimize-to-tray"]  # Keeps OBS's main window out of the way. Its icon is by the clock.

SERVER_WAIT_SECONDS = 30
POLL_SECONDS = 0.5


def log(message):
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"{datetime.datetime.now():%H:%M:%S} Startup: {message}\n")


def server_is_running():
    try:
        socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=1).close()
    except OSError:
        return False
    return True


def start_server():
    """Runs the server with no window. Anything it prints goes to the log, which starts fresh at each login."""
    LOG_FILE.write_text("", encoding="utf-8")
    with LOG_FILE.open("a", encoding="utf-8") as output:
        subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            cwd=PROJECT_DIR,
            env={**os.environ, "PYTHONIOENCODING": "utf-8:backslashreplace"},
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
        )


def wait_for_server():
    """OBS's browser source stays blank if it loads before the server is ready, so wait for the server first."""
    deadline = time.monotonic() + SERVER_WAIT_SECONDS
    while time.monotonic() < deadline:
        if server_is_running():
            return True
        time.sleep(POLL_SECONDS)
    return False


def start_obs():
    # OBS only finds its own files when it's started from its own folder.
    subprocess.Popen([str(OBS_EXE), *OBS_ARGS], cwd=OBS_EXE.parent, stdin=subprocess.DEVNULL)


def main():
    LOG_FILE.parent.mkdir(exist_ok=True)
    try:
        if not server_is_running():
            start_server()
        if not wait_for_server():
            log("the server didn't start in time. Starting OBS anyway.")
        if OBS_PROCESS not in running_process_names():
            start_obs()
    except Exception as error:  # There's no window here, so the log is the only place to report this.
        log(f"something went wrong: {error}")


if __name__ == "__main__":
    main()
