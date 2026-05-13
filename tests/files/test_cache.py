"""Tests for shared cache adapters."""

import tempfile
import unittest

from adrift.ports.cache import DiskCacheAdapter


class TestDiskCacheAdapter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = DiskCacheAdapter(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_local_hit(self):
        self.cache.set("test_key", "local_value")
        self.assertEqual(self.cache.get("test_key"), "local_value")

    def test_get_total_miss(self):
        self.assertEqual(self.cache.get("missing", default="fallback"), "fallback")

    def test_delete(self):
        self.cache.set("test_key", "test_value")
        self.cache.delete("test_key")
        self.assertIsNone(self.cache.get("test_key"))

    def test_expired_entry_returns_default(self):
        self.cache.set("expired", "value", expire=-1)
        self.assertEqual(self.cache.get("expired", default="missing"), "missing")


if __name__ == "__main__":
    unittest.main()
