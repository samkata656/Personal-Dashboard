"""Switches OBS to the Minimap scene while League of Legends is running, and back to Dashboard after."""

import ctypes
import threading
import time
from ctypes import wintypes

import env_file
from obs_websocket import ObsAuthError, ObsConnection, ObsError, ObsRequestError

OBS_HOST = "127.0.0.1"
OBS_PORT = 4455
PASSWORD_NAME = "OBS_WEBSOCKET_PASSWORD"
PASSWORD_PLACEHOLDER = "paste-your-obs-password-here"

GAME_PROCESS = "league of legends.exe"
OBS_PROCESS = "obs64.exe"
GAME_SCENE = "Minimap"
NORMAL_SCENE = "Dashboard"
# Set to False to keep the dashboard on screen during games instead.
MINIMAP_DURING_GAMES = True

CHECK_SECONDS = 2
RETRY_SECONDS = 10  # After a failed switch, wait a little so OBS isn't pestered while it starts up.
SCENE_NOT_FOUND = 600  # OBS's own error code

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

_status = {"game_running": None, "obs_running": None, "scene": None, "problem": "Starting"}


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.restype = wintypes.BOOL


def running_process_names():
    """Asks Windows for the names of running programs. It only reads names, and never touches the programs."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        names = set()
        found = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            names.add(entry.szExeFile.lower())
            found = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return names
    finally:
        _kernel32.CloseHandle(snapshot)


def wanted_scene(game_running):
    return GAME_SCENE if game_running else NORMAL_SCENE


def switch_scene(scene):
    """Connects to OBS and changes scene. Returns a description of the problem, or None if it worked."""
    password = env_file.read_secret(PASSWORD_NAME, PASSWORD_PLACEHOLDER)
    try:
        with ObsConnection(OBS_HOST, OBS_PORT, password) as obs:
            obs.request("SetCurrentProgramScene", {"sceneName": scene})
    except ObsAuthError:
        return f"OBS refused the password: check {PASSWORD_NAME} in the .env file."
    except ObsRequestError as error:
        if error.code == SCENE_NOT_FOUND:
            return f'OBS has no scene called "{scene}". The name must match exactly, including capital letters.'
        return f"OBS refused the scene change: {error}"
    except (OSError, ObsError, ValueError, KeyError, TypeError, AttributeError) as error:
        return f"Couldn't reach OBS: {error}"
    return None


class Switcher:
    """Decides when to change scene. Changing only when something changes leaves manual choices alone."""

    def __init__(self, switch, minimap_during_games=True):
        self.switch = switch
        self.minimap_during_games = minimap_during_games
        self.applied = None
        self.next_attempt = 0.0
        self.problem = None

    def update(self, names, now):
        game_running = GAME_PROCESS in names
        obs_running = OBS_PROCESS in names
        scene = wanted_scene(game_running and self.minimap_during_games)

        if not obs_running:
            self.applied = None  # OBS starts fresh next time, so set its scene again then.
            self.next_attempt = 0.0
            self.problem = None
        elif scene == self.applied:
            self.problem = None  # A failed switch no longer matters once that scene isn't wanted any more.
        elif now >= self.next_attempt:
            self.problem = self.switch(scene)
            if self.problem is None:
                self.applied = scene
            else:
                self.next_attempt = now + RETRY_SECONDS

        return {"game_running": game_running, "obs_running": obs_running, "scene": self.applied, "problem": self.problem}


def start():
    threading.Thread(target=_run, daemon=True).start()


def read_status():
    return _status


def _run():
    global _status
    switcher = Switcher(switch_scene, MINIMAP_DURING_GAMES)
    last_problem = None
    while True:
        try:
            _status = switcher.update(running_process_names(), time.monotonic())
        except Exception as error:  # This thread must keep running whatever goes wrong.
            _status = {**_status, "problem": f"Unexpected problem: {error}"}
        if _status["problem"] != last_problem:
            last_problem = _status["problem"]
            print(f"OBS: {last_problem or 'no problems now.'}", flush=True)
        time.sleep(CHECK_SECONDS)
