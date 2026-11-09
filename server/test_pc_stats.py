"""Checks the sensor reader against the format this PC's LibreHardwareMonitor really sends."""

import unittest

from pc_stats import parse_number, summarize


def sensor(sensor_id, value):
    return {"SensorId": sensor_id, "Value": value, "Children": []}


class ParseNumberTests(unittest.TestCase):
    def test_comma_decimals(self):
        self.assertEqual(parse_number("4692,5 MHz"), 4692.5)

    def test_dot_decimals(self):
        self.assertEqual(parse_number("51.0 °C"), 51.0)

    def test_whole_numbers(self):
        self.assertEqual(parse_number("769 RPM"), 769)

    def test_missing_values(self):
        self.assertIsNone(parse_number("-"))
        self.assertIsNone(parse_number(""))
        self.assertIsNone(parse_number(None))


class SummarizeTests(unittest.TestCase):
    def test_picks_the_right_sensors(self):
        tree = {"Children": [
            sensor("/intelcpu/0/temperature/10", "50,0 °C"),
            sensor("/intelcpu/0/temperature/0", "99,0 °C"),
            sensor("/intelcpu/0/load/0", "23,5 %"),
            sensor("/intelcpu/0/clock/0", "99,8 MHz"),
            sensor("/intelcpu/0/clock/1", "4600,0 MHz"),
            sensor("/intelcpu/0/clock/2", "4800,0 MHz"),
            sensor("/gpu-amd/0/temperature/0", "55,0 °C"),
            sensor("/gpu-amd/0/temperature/1", "78,0 °C"),
            sensor("/gpu-amd/0/load/0", "7,0 %"),
            sensor("/gpu-amd/0/clock/0", "2738,0 MHz"),
            sensor("/gpu-amd/0/smalldata/0", "3584,0 MB"),
            sensor("/gpu-amd/0/smalldata/1", "12720,0 MB"),
            sensor("/gpu-amd/0/smalldata/2", "16304,0 MB"),
            sensor("/gpu-amd/0/smalldata/6", "335,5 MB"),
            sensor("/gpu-intel-integrated/x/smalldata/0", "456,5 MB"),
            sensor("/ram/data/0", "15,2 GB"),
            sensor("/ram/data/1", "16,6 GB"),
            sensor("/vram/data/2", "24,9 GB"),
        ]}
        stats = summarize(tree)
        self.assertEqual(stats["cpu"], {"temp": 50.0, "usage": 23.5, "clock": 4.7})
        self.assertEqual(stats["gpu"], {"temp": 55.0, "usage": 7.0, "clock": 2.738})
        self.assertEqual(stats["vram"]["used"], 3.5)
        self.assertAlmostEqual(stats["vram"]["total"], 15.922, places=3)
        self.assertEqual(stats["ram"]["used"], 15.2)
        self.assertAlmostEqual(stats["ram"]["total"], 31.8)

    def test_missing_sensors_stay_empty(self):
        stats = summarize({"Children": [sensor("/gpu-amd/0/temperature/0", "55,0 °C")]})
        self.assertEqual(stats["cpu"], {"temp": None, "usage": None, "clock": None})
        self.assertEqual(stats["gpu"], {"temp": 55.0, "usage": None, "clock": None})
        self.assertEqual(stats["vram"], {"used": None, "total": None})
        self.assertEqual(stats["ram"], {"used": None, "total": None})

    def test_vram_needs_both_numbers(self):
        stats = summarize({"Children": [sensor("/gpu-amd/0/smalldata/0", "3584,0 MB")]})
        self.assertEqual(stats["vram"], {"used": None, "total": None})


if __name__ == "__main__":
    unittest.main()
