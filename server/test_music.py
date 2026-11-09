"""Checks the music reader's own logic, without needing anything to be playing."""

import datetime
import unittest
from types import SimpleNamespace

import music
from music import PlaybackStatus, image_type, pick_session, position_and_duration

NOW = datetime.datetime(2026, 10, 31, 12, 0, 0, tzinfo=datetime.timezone.utc)


def timeline(position, end, updated_seconds_ago=0, start=0):
    return SimpleNamespace(
        position=datetime.timedelta(seconds=position),
        start_time=datetime.timedelta(seconds=start),
        end_time=datetime.timedelta(seconds=end),
        last_updated_time=NOW - datetime.timedelta(seconds=updated_seconds_ago),
    )


def session(status):
    info = SimpleNamespace(playback_status=status)
    return SimpleNamespace(get_playback_info=lambda: info)


class PositionTests(unittest.TestCase):
    def test_playing_adds_time_since_last_report(self):
        self.assertEqual(position_and_duration(timeline(60, 200, 5), True, NOW), (65, 200))

    def test_paused_stays_put(self):
        self.assertEqual(position_and_duration(timeline(60, 200, 5), False, NOW), (60, 200))

    def test_never_runs_past_the_end(self):
        self.assertEqual(position_and_duration(timeline(198, 200, 5), True, NOW), (200, 200))

    def test_ignores_a_nonsense_report_time(self):
        self.assertEqual(position_and_duration(timeline(60, 200, 999999), True, NOW), (60, 200))

    def test_app_with_no_timeline(self):
        self.assertEqual(position_and_duration(timeline(0, 0), True, NOW), (None, None))

    def test_timeline_not_starting_at_zero(self):
        self.assertEqual(position_and_duration(timeline(70, 210, 0, start=10), False, NOW), (60, 200))


class PickSessionTests(unittest.TestCase):
    def test_nothing_open(self):
        self.assertIsNone(pick_session([], None))

    def test_prefers_a_playing_app_over_a_paused_current_one(self):
        paused = session(PlaybackStatus.PAUSED)
        playing = session(PlaybackStatus.PLAYING)
        self.assertIs(pick_session([paused, playing], paused), playing)

    def test_prefers_the_current_app_when_two_are_playing(self):
        first = session(PlaybackStatus.PLAYING)
        current = session(PlaybackStatus.PLAYING)
        self.assertIs(pick_session([first, current], current), current)

    def test_falls_back_to_the_current_app(self):
        paused = session(PlaybackStatus.PAUSED)
        self.assertIs(pick_session([paused], paused), paused)


class ImageTypeTests(unittest.TestCase):
    def test_known_images(self):
        self.assertEqual(image_type(b"\x89PNG\r\n\x1a\nabc"), "image/png")
        self.assertEqual(image_type(b"\xff\xd8\xffabc"), "image/jpeg")

    def test_anything_else_is_refused(self):
        self.assertIsNone(image_type(b"<html><script>"))


class WithoutPackagesTests(unittest.TestCase):
    def test_reports_an_error_instead_of_crashing(self):
        original = music.SessionManager
        music.SessionManager = None
        try:
            with self.assertRaises(RuntimeError):
                music.read_music()
        finally:
            music.SessionManager = original


if __name__ == "__main__":
    unittest.main()
