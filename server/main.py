"""The dashboard's local server: serves the page and hands it fresh data. Only this PC can reach it."""

import http.client
import json
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import claude_usage
import music
import obs_switcher
import openrouter
import pc_stats
import theme

HOST = "127.0.0.1"
HOST_IPV6 = "::1"
PORT = 8787
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_THEME_REQUEST_BYTES = 1024


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Only the web folder is ever served, so secrets elsewhere in the project stay private.
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/pc":
            self.send_pc_stats()
        elif path == "/api/music":
            self.send_music()
        elif path == "/api/music/art":
            self.send_music_art()
        elif path == "/api/openrouter":
            self.send_json(200, openrouter.read_openrouter())
        elif path == "/api/obs":
            self.send_json(200, obs_switcher.read_status())
        elif path == "/api/theme":
            self.send_json(200, {"theme": theme.read_theme()})
        elif path == "/api/claude":
            self.send_json(200, claude_usage.read_usage())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] == "/api/theme":
            self.receive_theme()
        else:
            self.send_error(404)

    def receive_theme(self):
        # Browsers won't let other websites send this type of request here, so they can't change the colors.
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Expected JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 <= length <= MAX_THEME_REQUEST_BYTES:
                raise ValueError("Bad request size")
            theme.set_theme(json.loads(self.rfile.read(length))["theme"])
        except (ValueError, KeyError, TypeError) as error:
            self.send_json(400, {"error": str(error)})
        except OSError as error:
            self.send_json(500, {"error": f"Couldn't save the colors: {error}"})
        else:
            self.send_json(200, {"theme": theme.read_theme()})

    def send_pc_stats(self):
        try:
            self.send_json(200, pc_stats.read_pc_stats())
        except (OSError, ValueError, http.client.HTTPException) as error:
            self.send_json(503, {"error": f"LibreHardwareMonitor unavailable: {error}"})

    def send_music(self):
        try:
            self.send_json(200, music.read_music())
        except Exception as error:  # Windows' media service can fail in many different ways.
            self.send_json(503, {"error": f"Media info unavailable: {error}"})

    def send_music_art(self):
        art = music.read_art()
        if art is None:
            self.send_error(404)
            return
        data, content_type = art
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Makes browsers and OBS always pick up the newest version of the page.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, the default would let a second copy start on the same port without any error.
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        # A page that closes mid-request is normal, so only report real problems.
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


class DashboardServerIPv6(DashboardServer):
    address_family = socket.AF_INET6


def start_ipv6_listener():
    """Windows tries "localhost" over IPv6 first and waits if nothing answers, slowing every refresh."""
    try:
        server = DashboardServerIPv6((HOST_IPV6, PORT), DashboardHandler)
    except OSError:
        return  # This PC has no IPv6, so "localhost" goes straight to the main listener.
    threading.Thread(target=server.serve_forever, daemon=True).start()


def main():
    try:
        server = DashboardServer((HOST, PORT), DashboardHandler)
    except OSError:
        print(f"Port {PORT} is already in use. The dashboard may already be running.")
        return 1

    start_ipv6_listener()
    music.start()
    openrouter.start()
    obs_switcher.start()
    claude_usage.start()
    print(f"Dashboard running at http://localhost:{PORT}  (press Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
