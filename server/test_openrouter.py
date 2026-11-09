"""Checks the OpenRouter sums and the handling of the snapshot and .env files."""

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import env_file
import openrouter
from env_file import parse_env
from openrouter import daily_activity, last_seven_days, record_snapshot, spend_for_day

TODAY = datetime.date(2026, 10, 31)  # a Saturday
YESTERDAY = datetime.date(2026, 10, 30)


class ParseEnvTests(unittest.TestCase):
    def test_reads_values_and_skips_comments(self):
        text = "# a comment\n\nOPENROUTER_MANAGEMENT_KEY=sk-or-abc\nOBS_WEBSOCKET_PASSWORD=p=ss\n"
        self.assertEqual(parse_env(text), {"OPENROUTER_MANAGEMENT_KEY": "sk-or-abc", "OBS_WEBSOCKET_PASSWORD": "p=ss"})

    def test_forgives_spaces_and_quotes(self):
        self.assertEqual(parse_env('KEY = "abc" \n'), {"KEY": "abc"})


class ReadKeyTests(unittest.TestCase):
    def read_with(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_bytes(content)
            with mock.patch.object(env_file, "ENV_FILE", path):
                return env_file.read_secret(openrouter.KEY_NAME, openrouter.KEY_PLACEHOLDER)

    def test_real_key(self):
        self.assertEqual(self.read_with(b"OPENROUTER_MANAGEMENT_KEY=sk-or-abc\n"), "sk-or-abc")

    def test_file_with_a_windows_marker_at_the_start(self):
        self.assertEqual(self.read_with(b"\xef\xbb\xbfOPENROUTER_MANAGEMENT_KEY=sk-or-abc\n"), "sk-or-abc")

    def test_placeholder_counts_as_no_key(self):
        self.assertIsNone(self.read_with(b"OPENROUTER_MANAGEMENT_KEY=paste-your-management-key-here\n"))

    def test_empty_value_counts_as_no_key(self):
        self.assertIsNone(self.read_with(b"OPENROUTER_MANAGEMENT_KEY=\n"))

    def test_missing_file(self):
        with mock.patch.object(env_file, "ENV_FILE", Path("does-not-exist/.env")):
            self.assertIsNone(env_file.read_secret(openrouter.KEY_NAME, openrouter.KEY_PLACEHOLDER))


class SnapshotTests(unittest.TestCase):
    def test_first_reading_of_the_day_is_kept(self):
        self.assertEqual(record_snapshot({}, TODAY, 5.0), {"2026-10-31": 5.0})

    def test_later_readings_change_nothing(self):
        self.assertIsNone(record_snapshot({"2026-10-31": 5.0}, TODAY, 9.0))

    def test_old_snapshots_are_dropped(self):
        kept = record_snapshot({"2026-10-01": 1.0, "2026-10-20": 2.0}, TODAY, 3.0)
        self.assertEqual(kept, {"2026-10-20": 2.0, "2026-10-31": 3.0})

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data" / "usage.json"
            with mock.patch.object(openrouter, "SNAPSHOT_FILE", path):
                openrouter.save_snapshots({"2026-10-31": 5.0})
                self.assertEqual(openrouter.load_snapshots(), {"2026-10-31": 5.0})

    def test_damaged_file_starts_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "usage.json"
            path.write_text("{not json", encoding="utf-8")
            with mock.patch.object(openrouter, "SNAPSHOT_FILE", path):
                self.assertEqual(openrouter.load_snapshots(), {})


class SpendingTests(unittest.TestCase):
    def test_adds_up_rows_for_each_day(self):
        rows = [
            {"date": "2026-10-30", "usage": 1.5, "model": "a"},
            {"date": "2026-10-30", "usage": 0.25, "model": "b"},
            {"date": "2026-10-29 00:00:00", "usage": 2},
            {"date": "2026-10-28", "usage": None},
        ]
        self.assertEqual(daily_activity(rows), {"2026-10-30": 1.75, "2026-10-29": 2.0, "2026-10-28": 0.0})

    def test_today_is_usage_since_the_snapshot(self):
        self.assertEqual(spend_for_day(TODAY, TODAY, {}, {"2026-10-31": 10.0}, 12.5), 2.5)

    def test_today_uses_the_activity_figure_if_it_is_higher(self):
        self.assertEqual(spend_for_day(TODAY, TODAY, {"2026-10-31": 4.0}, {"2026-10-31": 10.0}, 12.5), 4.0)

    def test_today_is_never_negative(self):
        self.assertEqual(spend_for_day(TODAY, TODAY, {}, {"2026-10-31": 10.0}, 9.0), 0.0)

    def test_finished_day_prefers_activity(self):
        snapshots = {"2026-10-30": 5.0, "2026-10-31": 9.0}
        self.assertEqual(spend_for_day(YESTERDAY, TODAY, {"2026-10-30": 3.0}, snapshots, 9.0), 3.0)

    def test_unreported_day_falls_back_to_snapshots(self):
        snapshots = {"2026-10-30": 5.0, "2026-10-31": 9.0}
        self.assertEqual(spend_for_day(YESTERDAY, TODAY, {}, snapshots, 9.0), 4.0)

    def test_unknown_day_is_zero(self):
        self.assertEqual(spend_for_day(YESTERDAY, TODAY, {}, {}, 9.0), 0.0)

    def test_seven_days_with_today_last(self):
        activity = {"2026-10-25": 1.0, "2026-10-30": 2.0, "2026-10-24": 50.0}
        days = last_seven_days(TODAY, activity, {"2026-10-31": 10.0}, 10.5)
        self.assertEqual(days, [["S", 1.0], ["M", 0.0], ["T", 0.0], ["W", 0.0], ["T", 0.0], ["F", 2.0], ["S", 0.5]])


class RefreshTests(unittest.TestCase):
    def test_no_key_reports_offline_without_contacting_anyone(self):
        with mock.patch.object(env_file, "read_secret", return_value=None), \
                mock.patch.object(openrouter, "_fetch") as fetch:
            self.assertFalse(openrouter.refresh())
        fetch.assert_not_called()
        self.assertFalse(openrouter.read_openrouter()["online"])
        self.assertIsNone(openrouter.read_openrouter()["credits"])


if __name__ == "__main__":
    unittest.main()
