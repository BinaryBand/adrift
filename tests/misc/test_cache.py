"""Tests for caching utilities.

This file combines tests for:
- JSON helpers stored in S3 (read_s3_json_cache / write_s3_json_cache)
- The unified two-layer cache wrapper (S3Cache)
"""

# cspell:ignore-word dunder

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.models import CacheMetadata
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
    """Test cases for the S3Cache class."""

    def setUp(self):
        """Set up test fixtures."""
        self.patch_cache = patch("src.utils.cache.Cache")
        self.mock_cache_class = self.patch_cache.start()
        self.mock_local_cache = self.mock_cache_class.return_value
        self.cache = S3Cache(".cache/test", "test-prefix")
        self.bucket = "cache"

    def tearDown(self):
        """Clean up test fixtures."""
        self.patch_cache.stop()

    @patch("src.utils.cache.exists")
    def test_get_local_hit(self, mock_exists):
        """Test cache hit from local cache (no S3 access needed)."""
        self.mock_local_cache.get.return_value = "local_value"
        result = self.cache.get("test_key")

        self.assertEqual(result, "local_value")
        self.mock_local_cache.get.assert_called_once_with("test_key")
        mock_exists.assert_not_called()

    @patch("builtins.open", new_callable=mock_open)
    @patch("src.utils.cache.Path")
    @patch("os.close")
    @patch("tempfile.mkstemp")
    @patch("src.utils.cache.pickle")
    @patch("src.utils.cache.download_file")
    @patch("src.utils.cache.exists")
    def test_get_s3_hit(
        self,
        mock_exists,
        mock_download,
        mock_pickle,
        mock_mkstemp,
        mock_close,
        mock_path,
        mock_file,
    ):
        """Test cache miss locally but hit in S3."""
        self.mock_local_cache.get.return_value = None
        mock_exists.return_value = True
        mock_mkstemp.return_value = (123, "/tmp/test.pickle")
        mock_pickle.load.return_value = "s3_value"
        mock_path.return_value = MagicMock()

        result = self.cache.get("test_key")

        self.assertEqual(result, "s3_value")
        self.mock_local_cache.set.assert_called_once_with(
            "test_key", "s3_value", expire=None
        )

    @patch("src.utils.cache.exists")
    def test_get_total_miss(self, mock_exists):
        """Test cache miss in both local and S3 returns default value."""
        self.mock_local_cache.get.return_value = None
        mock_exists.return_value = False

        result = self.cache.get("test_key", default="missing")

        self.assertEqual(result, "missing")

    @patch("src.utils.cache.pickle")
    @patch("builtins.open", new_callable=mock_open)
    @patch("tempfile.TemporaryDirectory")
    @patch("src.utils.cache.upload_cache_file")
    def test_set(self, mock_upload, mock_tempdir, mock_file, mock_pickle):
        """Test setting value in both local cache and S3."""
        mock_tempdir.return_value.__enter__.return_value = "/tmp/testdir"

        self.cache.set("test_key", "test_value", expire=3600)

        self.mock_local_cache.set.assert_called_once_with(
            "test_key", "test_value", expire=3600
        )
        mock_pickle.dump.assert_called_once()
        mock_upload.assert_called_once()

        # Verify metadata is passed
        call_args = mock_upload.call_args[0]
        self.assertEqual(call_args[0], self.bucket)
        self.assertIsInstance(call_args[3], CacheMetadata)
        self.assertIsNotNone(call_args[3].created_at)

    @patch("src.utils.cache.exists")
    @patch("src.utils.cache.delete_file")
    def test_delete(self, mock_delete, mock_exists):
        """Test deleting from both local cache and S3."""
        mock_exists.return_value = True

        self.cache.delete("test_key")

        self.mock_local_cache.delete.assert_called_once_with("test_key")
        mock_delete.assert_called_once()

    def test_get_s3_path_safe_keys(self):
        """Test that unsafe characters in keys are properly encoded."""
        key = (
            "_get_youtube_videos:https://www.youtube.com/@user/videos:Name With Spaces"
        )
        path = self.cache._get_s3_path(key)

        self.assertTrue(path.startswith("test-prefix/_get_youtube_videos/"))
        self.assertTrue(path.endswith(".pickle"))

        # Ensure unsafe characters are not in path
        for char in [":", " ", "@", "?", "#", "\\"]:
            self.assertNotIn(char, path)

        # Verify deterministic
        self.assertEqual(path, self.cache._get_s3_path(key))

    def test_get_s3_path_long_keys(self):
        """Test that very long keys are hashed instead of base64 encoded."""
        long_key = f"long_value:{'x' * 200}"
        path = self.cache._get_s3_path(long_key)

        # Extract encoded portion
        encoded_part = path.split("/")[-1].replace(".pickle", "")

        # Should be SHA256 hex (64 chars)
        self.assertEqual(len(encoded_part), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in encoded_part))

        # Verify deterministic
        self.assertEqual(path, self.cache._get_s3_path(long_key))

    def test_contains_dunder_method(self):
        """Test __contains__ method for 'in' operator."""
        self.mock_local_cache.get.return_value = "value"

        self.assertTrue("test_key" in self.cache)
        self.mock_local_cache.get.assert_called_once_with("test_key")


if __name__ == "__main__":
    unittest.main()
