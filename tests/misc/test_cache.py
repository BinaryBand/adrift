"""Tests for the local SQLite-backed cache compatibility wrapper."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.cache import S3Cache


class TestS3Cache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = S3Cache(self.temp_dir.name, "test-prefix")

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

    def test_delete(self):
        """Test deleting from cache."""
        self.cache.set("test_key", "test_value")

        self.cache.delete("test_key")

        self.assertIsNone(self.cache.get("test_key"))

    def test_expired_entry_returns_default(self):
        """Test expired entries are removed on read."""
        self.cache.set("expired", "value", expire=-1)

        self.assertEqual(self.cache.get("expired", default="missing"), "missing")

    def test_contains_dunder_method(self):
        """Test __contains__ method for 'in' operator."""
        self.cache.set("test_key", "value")

        self.assertTrue("test_key" in self.cache)


if __name__ == "__main__":
    unittest.main()
