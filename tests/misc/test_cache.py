"""Tests for caching utilities.

This file combines tests for:
- JSON helpers stored in S3 (read_s3_json_cache / write_s3_json_cache)
- The SQLite-backed cache wrapper (S3Cache compatibility API)
"""

# cspell:ignore-word dunder

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.utils.cache import S3Cache, read_s3_json_cache, write_s3_json_cache


class TestReadS3JsonCache(unittest.TestCase):
    """Test cases for read_s3_json_cache function."""

    @patch("src.utils.cache.exists")
    def test_cache_miss(self, mock_exists):
        """Test that None is returned when cache doesn't exist."""
        mock_exists.return_value = False
        result = read_s3_json_cache("test/path.json", "test_id")

        self.assertIsNone(result)
        mock_exists.assert_called_once_with("cache", "test/path.json", False)

    @patch("src.utils.cache.Path")
    @patch("os.close")
    @patch("tempfile.mkstemp")
    @patch("src.utils.cache.download_file")
    @patch("src.utils.cache.exists")
    def test_cache_hit_with_dict(
        self, mock_exists, mock_download, mock_mkstemp, mock_close, mock_path
    ):
        """Test successful cache read with dictionary data."""
        mock_exists.return_value = True
        mock_mkstemp.return_value = (123, "/tmp/test.json")

        test_data = {"key": "value", "number": 42}
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.return_value = json.dumps(test_data)
        mock_path.return_value = mock_path_instance

        result = read_s3_json_cache("test/path.json", "test_id")

        self.assertEqual(result, test_data)
        mock_close.assert_called_once_with(123)
        mock_path_instance.unlink.assert_called_once_with(missing_ok=True)

    @patch("src.utils.cache.Path")
    @patch("os.close")
    @patch("tempfile.mkstemp")
    @patch("src.utils.cache.download_file")
    @patch("src.utils.cache.exists")
    def test_cache_hit_with_list(
        self, mock_exists, mock_download, mock_mkstemp, mock_close, mock_path
    ):
        """Test successful cache read with list data."""
        mock_exists.return_value = True
        mock_mkstemp.return_value = (456, "/tmp/test2.json")

        test_data = [{"id": "1"}, {"id": "2"}]
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.return_value = json.dumps(test_data)
        mock_path.return_value = mock_path_instance

        result = read_s3_json_cache("test/segments.json", "id")

        self.assertEqual(result, test_data)
        self.assertIsInstance(result, list)

    @patch("src.utils.cache.Path")
    @patch("os.close")
    @patch("tempfile.mkstemp")
    @patch("src.utils.cache.delete_file")
    @patch("src.utils.cache.download_file")
    @patch("src.utils.cache.exists")
    def test_cache_read_failure(
        self,
        mock_exists,
        mock_download,
        mock_delete,
        mock_mkstemp,
        mock_close,
        mock_path,
    ):
        """Test that cache is deleted and None returned on read failure."""
        mock_exists.return_value = True
        mock_mkstemp.return_value = (789, "/tmp/test3.json")
        mock_download.side_effect = Exception("Download failed")
        mock_path.return_value = MagicMock()

        result = read_s3_json_cache("test/bad.json", "bad_id")

        self.assertIsNone(result)
        mock_delete.assert_called_once_with("cache", "test/bad.json")


class TestWriteS3JsonCache(unittest.TestCase):
    """Test cases for write_s3_json_cache function."""

    @patch("src.utils.cache.upload_file")
    @patch("src.utils.cache.Path")
    @patch("tempfile.TemporaryDirectory")
    def test_write_dict_cache(self, mock_tempdir, mock_path_cls, mock_upload):
        """Test writing dictionary data to cache."""
        mock_tempdir.return_value.__enter__.return_value = "/tmp/testdir"

        mock_path_instance = MagicMock()
        mock_path = MagicMock()
        mock_path.__truediv__ = MagicMock(return_value=mock_path_instance)
        mock_path_cls.return_value = mock_path

        test_data = {"id": "abc123", "title": "Test Video"}
        write_s3_json_cache("yt-dlp/videos/abc123.json", "abc123", test_data)

        mock_path_instance.write_text.assert_called_once_with(
            json.dumps(test_data), encoding="utf-8"
        )
        mock_upload.assert_called_once()

    @patch("src.utils.cache.upload_file")
    @patch("src.utils.cache.Path")
    @patch("tempfile.TemporaryDirectory")
    def test_write_list_cache(self, mock_tempdir, mock_path_cls, mock_upload):
        """Test writing list data to cache."""
        mock_tempdir.return_value.__enter__.return_value = "/tmp/testdir"

        mock_path_instance = MagicMock()
        mock_path = MagicMock()
        mock_path.__truediv__ = MagicMock(return_value=mock_path_instance)
        mock_path_cls.return_value = mock_path

        test_data = [{"segment": [1.0, 2.0]}, {"segment": [3.0, 4.0]}]
        write_s3_json_cache("sponsorblock/segments/xyz.json", "xyz", test_data)

        mock_path_instance.write_text.assert_called_once_with(
            json.dumps(test_data), encoding="utf-8"
        )
        mock_upload.assert_called_once()


class TestS3Cache(unittest.TestCase):
    """Test cases for the SQLite-backed S3Cache compatibility class."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = S3Cache(self.temp_dir.name, "test-prefix")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_local_hit(self):
        """Test cache hit from SQLite storage."""
        self.cache.set("test_key", "local_value")
        result = self.cache.get("test_key")

        self.assertEqual(result, "local_value")

    def test_get_total_miss(self):
        """Test cache miss returns default value."""

        result = self.cache.get("test_key", default="missing")

        self.assertEqual(result, "missing")

    def test_set(self):
        """Test setting value in SQLite cache."""

        self.cache.set("test_key", "test_value", expire=3600)
        result = self.cache.get("test_key")

        self.assertEqual(result, "test_value")

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
