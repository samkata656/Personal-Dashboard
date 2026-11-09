"""A small client for OBS's built-in WebSocket server (protocol version 5)."""

import base64
import hashlib
import json
import os
import socket
import struct
import uuid

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # fixed value from the WebSocket standard
OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA
MAX_MESSAGE_BYTES = 1024 * 1024
CLOSE_AUTH_FAILED = 4009


class ObsError(Exception):
    pass


class ObsAuthError(ObsError):
    pass


class ObsRequestError(ObsError):
    def __init__(self, code, comment):
        super().__init__(f"{comment} (code {code})")
        self.code = code


def auth_string(password, salt, challenge):
    """Proves we know the password without sending it, as OBS's protocol specifies."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class ObsConnection:
    """Use with "with": connects and logs in on entry, and disconnects on exit."""

    def __init__(self, host, port, password, timeout=3.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.sock = None
        self.buffer = b""

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            self._handshake()
            self._identify()
        except Exception:
            self.sock.close()
            raise
        return self

    def __exit__(self, *exc_info):
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", 1000))
        except OSError:
            pass
        self.sock.close()

    def request(self, request_type, data=None):
        """Sends one request to OBS and returns its reply data. Raises ObsRequestError if OBS refuses."""
        request_id = uuid.uuid4().hex
        payload = {"requestType": request_type, "requestId": request_id}
        if data:
            payload["requestData"] = data
        self._send_message(6, payload)
        while True:
            message = self._receive_message()
            if message["op"] == 7 and message["d"]["requestId"] == request_id:
                reply = message["d"]
                status = reply["requestStatus"]
                if not status["result"]:
                    raise ObsRequestError(status.get("code"), status.get("comment", "OBS refused the request"))
                return reply.get("responseData", {})

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            "GET / HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Protocol: obswebsocket.json\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode())

        while b"\r\n\r\n" not in self.buffer:
            self._read_more()
        head, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        headers = {k.strip().lower(): v.strip() for k, v in (line.split(":", 1) for line in lines[1:] if ":" in line)}
        if " 101 " not in lines[0] + " " or headers.get("sec-websocket-accept") != expected:
            raise ObsError("This isn't an OBS WebSocket server")

    def _identify(self):
        hello = self._receive_message()
        if hello["op"] != 0:
            raise ObsError("OBS sent an unexpected first message")

        identify = {"rpcVersion": 1, "eventSubscriptions": 0}  # no events: this client only sends requests
        authentication = hello["d"].get("authentication")
        if authentication:
            if not self.password:
                raise ObsAuthError("OBS requires a password")
            identify["authentication"] = auth_string(self.password, authentication["salt"], authentication["challenge"])
        self._send_message(1, identify)

        if self._receive_message()["op"] != 2:
            raise ObsError("OBS didn't accept the login")

    def _send_message(self, op, data):
        self._send_frame(OP_TEXT, json.dumps({"op": op, "d": data}).encode())

    def _receive_message(self):
        return json.loads(self._receive_text())

    def _send_frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _receive_text(self):
        parts = []
        while True:
            fin, opcode, payload = self._receive_frame()
            if opcode == OP_CLOSE:
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                if code == CLOSE_AUTH_FAILED:
                    raise ObsAuthError("OBS refused the password")
                raise ObsError(f"OBS closed the connection (code {code})")
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload)
            elif opcode != OP_PONG:
                parts.append(payload)
                if fin:
                    return b"".join(parts).decode("utf-8")

    def _receive_frame(self):
        first, second = self._read_exact(2)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > MAX_MESSAGE_BYTES:
            raise ObsError("OBS sent an unexpectedly large message")
        return bool(first & 0x80), first & 0x0F, self._read_exact(length)

    def _read_exact(self, count):
        while len(self.buffer) < count:
            self._read_more()
        data, self.buffer = self.buffer[:count], self.buffer[count:]
        return data

    def _read_more(self):
        chunk = self.sock.recv(65536)
        if not chunk:
            raise ObsError("OBS closed the connection")
        self.buffer += chunk
