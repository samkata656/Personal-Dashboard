"""Checks the OBS connection against a pretend OBS, and when the switcher decides to change scene."""

import base64
import hashlib
import json
import socket
import struct
import threading
import unittest

from obs_switcher import GAME_PROCESS, GAME_SCENE, NORMAL_SCENE, OBS_PROCESS, RETRY_SECONDS, Switcher, running_process_names
from obs_websocket import GUID, ObsAuthError, ObsConnection, ObsRequestError, auth_string

PASSWORD = "correct-password"
SALT = "salt123"
CHALLENGE = "challenge456"


class PretendObs:
    """Speaks just enough of OBS's protocol to test the client, including its quirks."""

    def __init__(self, big_reply=False, pings=False):
        self.big_reply = big_reply
        self.pings = pings
        self.requests = []
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        connection, _ = self.listener.accept()
        self.listener.close()
        with connection:
            try:
                self.converse(connection)
            except ConnectionError:
                pass  # The client hung up, which some tests do on purpose.

    def converse(self, connection):
        self.handshake(connection)
        self.send(connection, {"op": 0, "d": {"rpcVersion": 1, "authentication": {"salt": SALT, "challenge": CHALLENGE}}})
        identify = self.receive(connection)
        if identify["d"].get("authentication") != auth_string(PASSWORD, SALT, CHALLENGE):
            connection.sendall(bytes([0x88, 2]) + struct.pack("!H", 4009))
            return
        self.send(connection, {"op": 2, "d": {"negotiatedRpcVersion": 1}})
        while True:
            message = self.receive(connection)
            if message is None:
                return
            self.requests.append(message["d"])
            self.reply(connection, message["d"])

    def reply(self, connection, request):
        if self.pings:
            connection.sendall(bytes([0x89, 0]))
        status = {"result": True, "code": 100}
        if request["requestData"].get("sceneName") == "missing":
            status = {"result": False, "code": 600, "comment": "No source was found"}
        # A reply to someone else's request must be ignored.
        self.send(connection, {"op": 7, "d": {"requestId": "other", "requestStatus": {"result": False, "code": 1}}})
        data = {"padding": "x" * 70000} if self.big_reply else {"ok": True}
        self.send(connection, {"op": 7, "d": {"requestId": request["requestId"], "requestStatus": status, "responseData": data}})

    def handshake(self, connection):
        data = b""
        while b"\r\n\r\n" not in data:
            data += connection.recv(4096)
        key = [line.split(":")[1].strip() for line in data.decode().split("\r\n") if line.startswith("Sec-WebSocket-Key")][0]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        response = f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
        connection.sendall(response.encode())

    def send(self, connection, message):
        payload = json.dumps(message).encode()
        if len(payload) < 126:
            header = bytes([0x81, len(payload)])
        elif len(payload) < 65536:
            header = bytes([0x81, 126]) + struct.pack("!H", len(payload))
        else:
            header = bytes([0x81, 127]) + struct.pack("!Q", len(payload))
        connection.sendall(header + payload)

    def receive(self, connection):
        while True:
            first, second = self.read(connection, 2)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self.read(connection, 2))[0]
            mask = self.read(connection, 4)
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.read(connection, length)))
            opcode = first & 0x0F
            if opcode == 0x8:
                return None
            if opcode == 0x1:
                return json.loads(payload)

    def read(self, connection, count):
        data = b""
        while len(data) < count:
            chunk = connection.recv(count - len(data))
            if not chunk:
                raise ConnectionError
            data += chunk
        return data


class ConnectionTests(unittest.TestCase):
    def test_login_and_request(self):
        obs = PretendObs()
        with ObsConnection("127.0.0.1", obs.port, PASSWORD) as connection:
            self.assertEqual(connection.request("SetCurrentProgramScene", {"sceneName": "Dashboard"}), {"ok": True})
        self.assertEqual(obs.requests[0]["requestType"], "SetCurrentProgramScene")
        self.assertEqual(obs.requests[0]["requestData"], {"sceneName": "Dashboard"})

    def test_wrong_password(self):
        obs = PretendObs()
        with self.assertRaises(ObsAuthError):
            with ObsConnection("127.0.0.1", obs.port, "wrong"):
                pass

    def test_no_password(self):
        obs = PretendObs()
        with self.assertRaises(ObsAuthError):
            with ObsConnection("127.0.0.1", obs.port, None):
                pass

    def test_refused_request_reports_the_code(self):
        obs = PretendObs()
        with ObsConnection("127.0.0.1", obs.port, PASSWORD) as connection:
            with self.assertRaises(ObsRequestError) as caught:
                connection.request("SetCurrentProgramScene", {"sceneName": "missing"})
        self.assertEqual(caught.exception.code, 600)

    def test_large_reply_and_ping(self):
        obs = PretendObs(big_reply=True, pings=True)
        with ObsConnection("127.0.0.1", obs.port, PASSWORD) as connection:
            reply = connection.request("GetSceneList", {"x": 1})
        self.assertEqual(len(reply["padding"]), 70000)

    def test_password_is_never_sent(self):
        obs = PretendObs()
        with ObsConnection("127.0.0.1", obs.port, PASSWORD) as connection:
            connection.request("GetVersion", {"x": 1})
        self.assertNotIn(PASSWORD, json.dumps(obs.requests))

    def test_auth_matches_the_published_formula(self):
        secret = base64.b64encode(hashlib.sha256(b"pw" + b"s").digest())
        expected = base64.b64encode(hashlib.sha256(secret + b"c").digest()).decode()
        self.assertEqual(auth_string("pw", "s", "c"), expected)


class SwitcherTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.result = None
        self.switcher = Switcher(self.record)

    def record(self, scene):
        self.calls.append(scene)
        return self.result

    def test_game_start_and_end(self):
        self.switcher.update({OBS_PROCESS}, 0)
        self.switcher.update({OBS_PROCESS, GAME_PROCESS}, 2)
        self.switcher.update({OBS_PROCESS}, 4)
        self.assertEqual(self.calls, [NORMAL_SCENE, GAME_SCENE, NORMAL_SCENE])

    def test_leaves_manual_choices_alone(self):
        for now in range(0, 20, 2):
            self.switcher.update({OBS_PROCESS}, now)
        self.assertEqual(self.calls, [NORMAL_SCENE])

    def test_league_lobby_does_not_count(self):
        self.switcher.update({OBS_PROCESS, "leagueclient.exe", "leagueclientux.exe", "riotclientservices.exe"}, 0)
        self.assertEqual(self.calls, [NORMAL_SCENE])

    def test_nothing_happens_without_obs(self):
        status = self.switcher.update({GAME_PROCESS}, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(status["obs_running"])

    def test_obs_opened_mid_game_goes_to_minimap(self):
        self.switcher.update({GAME_PROCESS}, 0)
        self.switcher.update({GAME_PROCESS, OBS_PROCESS}, 2)
        self.assertEqual(self.calls, [GAME_SCENE])

    def test_obs_restart_sets_the_scene_again(self):
        self.switcher.update({OBS_PROCESS}, 0)
        self.switcher.update(set(), 2)
        self.switcher.update({OBS_PROCESS}, 4)
        self.assertEqual(self.calls, [NORMAL_SCENE, NORMAL_SCENE])

    def test_failure_retries_after_a_wait_then_recovers(self):
        self.result = "OBS is not ready"
        self.assertEqual(self.switcher.update({OBS_PROCESS}, 0)["problem"], "OBS is not ready")
        self.switcher.update({OBS_PROCESS}, RETRY_SECONDS - 1)
        self.assertEqual(len(self.calls), 1)
        self.result = None
        status = self.switcher.update({OBS_PROCESS}, RETRY_SECONDS)
        self.assertEqual(len(self.calls), 2)
        self.assertIsNone(status["problem"])
        self.assertEqual(status["scene"], NORMAL_SCENE)

    def test_dashboard_stays_during_games_when_minimap_is_off(self):
        switcher = Switcher(self.record, minimap_during_games=False)
        switcher.update({OBS_PROCESS}, 0)
        status = switcher.update({OBS_PROCESS, GAME_PROCESS}, 2)
        switcher.update({OBS_PROCESS}, 4)
        self.assertEqual(self.calls, [NORMAL_SCENE])
        self.assertTrue(status["game_running"])

    def test_minimap_off_still_leaves_minimap_mid_game(self):
        # Turning the minimap off during a game puts the dashboard straight back.
        switcher = Switcher(self.record, minimap_during_games=False)
        switcher.update({OBS_PROCESS, GAME_PROCESS}, 0)
        self.assertEqual(self.calls, [NORMAL_SCENE])

    def test_old_problem_clears_when_the_game_ends(self):
        self.switcher.update({OBS_PROCESS}, 0)
        self.result = "OBS has no such scene"
        self.assertIsNotNone(self.switcher.update({OBS_PROCESS, GAME_PROCESS}, 2)["problem"])
        self.assertIsNone(self.switcher.update({OBS_PROCESS}, 4)["problem"])


class ProcessListTests(unittest.TestCase):
    def test_finds_this_python(self):
        names = running_process_names()
        self.assertGreater(len(names), 5)
        self.assertTrue(any(name.startswith("python") for name in names))
        self.assertTrue(all(name == name.lower() for name in names))


if __name__ == "__main__":
    unittest.main()
