"""Tests for the color switch: remembering the choice, and only accepting it from the switch page."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import main
import theme


class ThemeTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "data" / "theme.json"
        for patcher in (mock.patch.object(theme, "THEME_FILE", self.file), mock.patch.object(theme, "_current", None)):
            patcher.start()
            self.addCleanup(patcher.stop)


class RememberingTests(ThemeTestCase):
    def test_black_and_white_until_something_is_chosen(self):
        self.assertEqual(theme.read_theme(), "mono")

    def test_choice_survives_a_restart(self):
        theme.set_theme("neon")
        theme._current = None  # What a restart does.
        self.assertEqual(theme.read_theme(), "neon")

    def test_unknown_theme_is_refused_and_changes_nothing(self):
        theme.set_theme("neon")
        for bad in ("pink", None, 1, ["neon"]):
            with self.assertRaises(ValueError):
                theme.set_theme(bad)
        self.assertEqual(theme.read_theme(), "neon")

    def test_damaged_file_falls_back_to_black_and_white(self):
        self.file.parent.mkdir()
        for damaged in ("not json", "[]", "{}", '{"theme": "pink"}', '{"theme": ["neon"]}'):
            self.file.write_text(damaged, encoding="utf-8")
            theme._current = None
            self.assertEqual(theme.read_theme(), "mono", damaged)


class SwitchRequestTests(ThemeTestCase):
    def setUp(self):
        super().setUp()
        server = main.DashboardServer(("127.0.0.1", 0), main.DashboardHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def request(self, method, body=None, content_type="application/json", path="/api/theme"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(connection.close)
        headers = {"Content-Type": content_type} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()

    def test_page_can_read_the_theme(self):
        status, body = self.request("GET")
        self.assertEqual((status, json.loads(body)), (200, {"theme": "mono"}))

    def test_switching_changes_what_the_page_reads(self):
        status, _ = self.request("POST", '{"theme": "neon"}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.request("GET")[1]), {"theme": "neon"})

    def test_request_type_other_websites_could_send_is_refused(self):
        status, _ = self.request("POST", '{"theme": "neon"}', content_type="text/plain")
        self.assertEqual(status, 415)
        self.assertEqual(theme.read_theme(), "mono")

    def test_bad_requests_are_refused(self):
        for body in ("not json", "[]", "{}", '{"theme": "pink"}', '"neon"', "x" * 2000):
            status, _ = self.request("POST", body)
            self.assertEqual(status, 400, body[:20])
        self.assertEqual(theme.read_theme(), "mono")

    def test_other_addresses_cannot_be_posted_to(self):
        self.assertEqual(self.request("POST", "{}", path="/api/pc")[0], 404)


if __name__ == "__main__":
    unittest.main()
