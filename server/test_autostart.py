"""Checks that the login starter only opens what isn't already running, and in the right order."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import autostart


class AutostartTests(unittest.TestCase):
    def run_main(self, server_up, names, wait_result=True):
        self.order = []
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(autostart, "LOG_FILE", Path(folder) / "data" / "dashboard.log"), \
                mock.patch.object(autostart, "server_is_running", return_value=server_up), \
                mock.patch.object(autostart, "wait_for_server", side_effect=lambda: self.order.append("wait") or wait_result), \
                mock.patch.object(autostart, "running_process_names", return_value=names), \
                mock.patch.object(autostart, "start_server", side_effect=lambda: self.order.append("server")), \
                mock.patch.object(autostart, "start_obs", side_effect=lambda: self.order.append("obs")):
            autostart.main()
            log = autostart.LOG_FILE.read_text(encoding="utf-8") if autostart.LOG_FILE.exists() else ""
        return log

    def test_starts_the_server_then_waits_then_starts_obs(self):
        self.run_main(False, set())
        self.assertEqual(self.order, ["server", "wait", "obs"])

    def test_nothing_starts_twice(self):
        self.run_main(True, {autostart.OBS_PROCESS})
        self.assertEqual(self.order, ["wait"])

    def test_obs_still_starts_if_the_server_is_slow(self):
        log = self.run_main(False, set(), wait_result=False)
        self.assertEqual(self.order, ["server", "wait", "obs"])
        self.assertIn("didn't start in time", log)

    def test_failure_goes_to_the_log(self):
        with mock.patch.object(autostart, "OBS_EXE", Path("does-not-exist/obs64.exe")):
            with tempfile.TemporaryDirectory() as folder, \
                    mock.patch.object(autostart, "LOG_FILE", Path(folder) / "dashboard.log"), \
                    mock.patch.object(autostart, "server_is_running", return_value=True), \
                    mock.patch.object(autostart, "running_process_names", return_value=set()):
                autostart.main()
                self.assertIn("something went wrong", autostart.LOG_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
