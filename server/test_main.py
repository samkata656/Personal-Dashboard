"""Tests that the server only answers requests addressed to this PC itself."""

import unittest

from main import host_allowed


class HostTests(unittest.TestCase):
    def test_this_pcs_own_addresses_are_allowed(self):
        for host in ("localhost:8787", "127.0.0.1:8787", "[::1]:8787", "localhost", "LOCALHOST:8787", "[::1]"):
            self.assertTrue(host_allowed(host), host)

    def test_other_names_and_ports_are_refused(self):
        for host in (None, "", "evil.example:8787", "evil.example", "localhost.evil.example:8787",
                     "localhost:9999", "127.0.0.1:80", "[::2]:8787", "localhost:8787:8787", "localhost:"):
            self.assertFalse(host_allowed(host), host)

    def test_port_the_server_actually_uses_is_the_one_allowed(self):
        self.assertTrue(host_allowed("127.0.0.1:5000", 5000))
        self.assertFalse(host_allowed("127.0.0.1:8787", 5000))


if __name__ == "__main__":
    unittest.main()
