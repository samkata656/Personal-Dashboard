"""Tests for Claude plan usage: from Anthropic, from the status line, and reading it back for the page."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import claude_statusline
import claude_usage

NOW = 1_800_000_000


def statusline(five_hour=None, seven_day=None):
    limits = {}
    if five_hour:
        limits["five_hour"] = {"used_percentage": five_hour[0], "resets_at": five_hour[1]}
    if seven_day:
        limits["seven_day"] = {"used_percentage": seven_day[0], "resets_at": seven_day[1]}
    return {"model": {"display_name": "Opus"}, "rate_limits": limits}


class UsageTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "data" / "claude-usage.json"
        patcher = mock.patch.object(claude_usage, "USAGE_FILE", self.file)
        patcher.start()
        self.addCleanup(patcher.stop)


class SavingTests(UsageTestCase):
    def test_both_windows_are_saved_and_read_back(self):
        claude_usage.save_from_statusline(statusline((23.5, NOW + 3600), (41, NOW + 86400)), NOW)
        self.assertEqual(claude_usage.read_usage(NOW), {
            "five_hour": {"used": 23.5, "resets_at": NOW + 3600},
            "seven_day": {"used": 41.0, "resets_at": NOW + 86400},
        })

    def test_nothing_known_before_any_update(self):
        self.assertEqual(claude_usage.read_usage(NOW), {"five_hour": None, "seven_day": None})

    def test_update_without_limits_keeps_the_last_numbers(self):
        claude_usage.save_from_statusline(statusline((10, NOW + 3600), (20, NOW + 86400)), NOW)
        self.assertFalse(claude_usage.save_from_statusline({"model": {}}, NOW + 5))
        self.assertFalse(claude_usage.save_from_statusline("not a dict", NOW + 5))
        self.assertEqual(claude_usage.read_usage(NOW)["five_hour"]["used"], 10)

    def test_one_window_missing_keeps_the_other_windows_reading(self):
        claude_usage.save_from_statusline(statusline((10, NOW + 3600), (20, NOW + 86400)), NOW)
        claude_usage.save_from_statusline(statusline(five_hour=(15, NOW + 3600)), NOW + 60)
        usage = claude_usage.read_usage(NOW + 60)
        self.assertEqual((usage["five_hour"]["used"], usage["seven_day"]["used"]), (15, 20))

    def test_window_past_its_reset_time_is_unknown(self):
        claude_usage.save_from_statusline(statusline((90, NOW + 60), (50, NOW + 86400)), NOW)
        usage = claude_usage.read_usage(NOW + 60)
        self.assertIsNone(usage["five_hour"])
        self.assertEqual(usage["seven_day"]["used"], 50)

    def test_old_readings_show_as_unknown(self):
        claude_usage.save_from_statusline(statusline((10, NOW + 86400), (20, NOW + 86400)), NOW)
        self.assertEqual(claude_usage.read_usage(NOW + claude_usage.STALE_SECONDS)["five_hour"]["used"], 10)
        self.assertEqual(claude_usage.read_usage(NOW + claude_usage.STALE_SECONDS + 1),
                         {"five_hour": None, "seven_day": None})

    def test_bad_values_are_ignored(self):
        for bad in ("23", None, True, [1]):
            claude_usage.save_from_statusline(statusline((bad, NOW + 3600)), NOW)
        self.assertFalse(self.file.exists())

    def test_damaged_file_reads_as_unknown(self):
        self.file.parent.mkdir()
        for damaged in ("not json", "[]", '{"five_hour": "x"}', '{"five_hour": {"used": "1", "resets_at": 2}}'):
            self.file.write_text(damaged, encoding="utf-8")
            self.assertEqual(claude_usage.read_usage(NOW), {"five_hour": None, "seven_day": None}, damaged)


API_REPLY = {
    "five_hour": {"utilization": 66.0, "resets_at": "2027-01-15T08:30:00.556588+00:00"},
    "seven_day": {"utilization": 87, "resets_at": "2027-01-20T08:00:00Z"},
    "seven_day_opus": None,
}


class ApiTests(UsageTestCase):
    def setUp(self):
        super().setUp()
        self.credentials = self.file.parent.parent / ".credentials.json"
        patcher = mock.patch.object(claude_usage, "CREDENTIALS_FILE", self.credentials)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_login(self, login):
        self.credentials.write_text(json.dumps({"claudeAiOauth": login}), encoding="utf-8")

    def test_reply_is_turned_into_windows(self):
        windows = claude_usage.windows_from_api(API_REPLY)
        self.assertEqual(windows["five_hour"]["used"], 66.0)
        self.assertAlmostEqual(windows["five_hour"]["resets_at"], 1_800_001_800.556588, places=3)
        self.assertEqual(windows["seven_day"], {"used": 87.0, "resets_at": 1_800_432_000.0})

    def test_odd_replies_give_nothing(self):
        for reply in (None, [], {}, {"five_hour": None}, {"five_hour": {"utilization": "66", "resets_at": "2027-01-15T08:30:00Z"}},
                      {"five_hour": {"utilization": 66, "resets_at": "soon"}}):
            self.assertEqual(claude_usage.windows_from_api(reply), {}, reply)

    def test_time_formats(self):
        self.assertEqual(claude_usage._parse_time("2027-01-15T08:00:00Z"), 1_800_000_000.0)
        self.assertEqual(claude_usage._parse_time("2027-01-15T10:00:00+02:00"), 1_800_000_000.0)
        self.assertEqual(claude_usage._parse_time("2027-01-15T08:00:00"), 1_800_000_000.0)
        self.assertAlmostEqual(claude_usage._parse_time("2027-01-15T08:00:00.5Z"), 1_800_000_000.5)
        self.assertAlmostEqual(claude_usage._parse_time("2027-01-15T08:00:00.123456789Z"), 1_800_000_000.123456, places=5)
        self.assertIsNone(claude_usage._parse_time(None))

    def test_refresh_saves_the_numbers(self):
        self.write_login({"accessToken": "test-token", "expiresAt": (NOW + 3600) * 1000})
        with mock.patch.object(claude_usage, "_fetch", return_value=API_REPLY) as fetch:
            self.assertIsNone(claude_usage.refresh(NOW))
        fetch.assert_called_once_with("test-token")
        usage = claude_usage.read_usage(NOW)
        self.assertEqual((usage["five_hour"]["used"], usage["seven_day"]["used"]), (66.0, 87.0))

    def test_missing_or_expired_login_is_not_sent(self):
        with mock.patch.object(claude_usage, "_fetch") as fetch:
            self.assertIn("No Claude login", claude_usage.refresh(NOW))
            self.write_login({"accessToken": "test-token", "expiresAt": (NOW - 1) * 1000})
            self.assertIn("expired", claude_usage.refresh(NOW))
            self.write_login({"refreshToken": "x"})
            self.assertIn("No Claude login", claude_usage.refresh(NOW))
            self.credentials.write_text("not json", encoding="utf-8")
            self.assertIn("Couldn't read", claude_usage.refresh(NOW))
        fetch.assert_not_called()
        self.assertFalse(self.file.exists())

    def test_refused_login_keeps_the_last_numbers(self):
        claude_usage.save_from_statusline(statusline((10, NOW + 3600), (20, NOW + 86400)), NOW)
        self.write_login({"accessToken": "test-token"})
        refused = claude_usage.urllib.error.HTTPError(claude_usage.USAGE_URL, 401, "Unauthorized", {}, None)
        with mock.patch.object(claude_usage, "_fetch", side_effect=refused):
            self.assertIn("refused", claude_usage.refresh(NOW + 5))
        self.assertEqual(claude_usage.read_usage(NOW + 5)["five_hour"]["used"], 10)

    def test_network_failure_is_described(self):
        self.write_login({"accessToken": "test-token"})
        with mock.patch.object(claude_usage, "_fetch", side_effect=OSError("no internet")):
            self.assertIn("no internet", claude_usage.refresh(NOW))

    def test_slow_down_is_recognised(self):
        self.write_login({"accessToken": "test-token"})
        slow_down = claude_usage.urllib.error.HTTPError(claude_usage.USAGE_URL, 429, "Too Many Requests", {}, None)
        with mock.patch.object(claude_usage, "_fetch", side_effect=slow_down):
            self.assertEqual(claude_usage.refresh(NOW), claude_usage.RATE_LIMITED)


class WaitTests(unittest.TestCase):
    def test_waits_double_while_refused_and_reset_after_success(self):
        waits, wait = [], 0
        for _ in range(5):
            wait = claude_usage.next_wait(claude_usage.RATE_LIMITED, wait)
            waits.append(wait // 60)
        self.assertEqual(waits, [5, 10, 20, 30, 30])
        self.assertEqual(claude_usage.next_wait(None, wait), claude_usage.REFRESH_SECONDS)
        self.assertEqual(claude_usage.next_wait("no internet", wait), claude_usage.RETRY_SECONDS)


class CapturedOutput(io.StringIO):
    def reconfigure(self, **kwargs):
        pass  # The real stdout switches to UTF-8 here; captured text needs nothing.


class StatusLineTests(UsageTestCase):
    def run_statusline(self, stdin_bytes):
        output = CapturedOutput()
        with mock.patch("sys.stdin", io.TextIOWrapper(io.BytesIO(stdin_bytes))), redirect_stdout(output):
            claude_statusline.main()
        return output.getvalue().strip()

    def test_prints_a_short_summary_and_saves(self):
        payload = json.dumps(statusline((23.5, NOW + 3600), (41.2, NOW + 86400))).encode()
        with mock.patch("time.time", return_value=NOW):
            self.assertEqual(self.run_statusline(payload), "session 24% · week 41%")
        self.assertTrue(self.file.exists())

    def test_garbage_input_still_prints_something(self):
        self.assertEqual(self.run_statusline(b"not json"), "Claude usage: waiting for the first reply")
        self.assertFalse(self.file.exists())


if __name__ == "__main__":
    unittest.main()
