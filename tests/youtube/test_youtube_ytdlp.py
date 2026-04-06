"""Tests for YouTube yt-dlp module with focus on caching and error handling."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.models import YtDlpParams
from src.youtube.ytdlp import (
    ChannelInfo,
    VideoInfo,
    _fetch_channel_info_raw,
    _fetch_channel_videos_raw,
    _fetch_video_info_raw,
    _trim_channel_cache_payload,
    _trim_video_cache_payload,
    get_channel_info,
    get_video_info,
)


class TestPydanticModels(unittest.TestCase):
    """Test Pydantic model validation and parsing."""

    def test_video_info_with_complete_data(self):
        """Test VideoInfo model with all fields."""
        data = {
            "id": "vid123",
            "title": "Test Video",
            "description": "Test description",
            "duration": 300.5,
            "upload_date": "20231218",
            "thumbnail": "https://example.com/thumb.jpg",
            "availability": "public",
            "url": "https://youtube.com/watch?v=vid123",
        }

        video = VideoInfo.model_validate(data)

        self.assertEqual(video.id, "vid123")
        self.assertEqual(video.title, "Test Video")
        self.assertEqual(video.description, "Test description")
        self.assertEqual(video.duration, 300.5)
        self.assertEqual(video.upload_date, datetime(2023, 12, 18))
        self.assertEqual(video.thumbnail, "https://example.com/thumb.jpg")
        self.assertEqual(video.availability, "public")
        self.assertEqual(video.url, "https://youtube.com/watch?v=vid123")

    def test_video_info_with_minimal_data(self):
        """Test VideoInfo model with only required fields."""
        data = {
            "id": "vid123",
            "title": "Test Video",
        }

        video = VideoInfo.model_validate(data)

        self.assertEqual(video.id, "vid123")
        self.assertEqual(video.title, "Test Video")
        self.assertIsNone(video.description)
        self.assertIsNone(video.duration)

    def test_channel_info_model(self):
        """Test ChannelInfo model."""
        data = {
            "title": "Test Channel",
            "uploader": "Test Uploader",
            "uploader_id": "test_id",
            "description": "Channel description",
            "avatar": [{"url": "https://example.com/avatar.jpg"}],
            "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
        }

        channel = ChannelInfo.model_validate(data)

        self.assertEqual(channel.title, "Test Channel")
        self.assertEqual(channel.uploader, "Test Uploader")
        self.assertEqual(channel.uploader_id, "test_id")
        self.assertEqual(channel.description, "Channel description")


class TestCachePayloadTrimming(unittest.TestCase):
    """Test payload trimming before cache persistence."""

    def test_trim_video_cache_payload(self):
        raw = {
            "id": "vid123",
            "title": "Test Video",
            "description": "desc",
            "duration": 22,
            "upload_date": "20231218",
            "thumbnail": "thumb",
            "availability": "public",
            "url": "https://youtube.com/watch?v=vid123",
            "timestamp": 1700000000,
            "release_timestamp": 1700000001,
            "view_count": 10,
            "like_count": 2,
            "comment_count": 1,
            "formats": [{"id": "heavy"}],
            "subtitles": {"en": []},
        }

        trimmed = _trim_video_cache_payload(raw)

        self.assertNotIn("formats", trimmed)
        self.assertNotIn("subtitles", trimmed)
        self.assertEqual(trimmed["id"], "vid123")
        self.assertEqual(trimmed["view_count"], 10)

    def test_trim_channel_cache_payload(self):
        raw = {
            "title": "Channel",
            "uploader": "Uploader",
            "uploader_id": "@uploader",
            "description": "desc",
            "avatar": [{"url": "avatar"}],
            "thumbnails": [{"url": "thumb"}],
            "entries": [{"id": "vid123"}],
        }

        trimmed = _trim_channel_cache_payload(raw)

        self.assertNotIn("entries", trimmed)
        self.assertEqual(trimmed["title"], "Channel")


class TestFetchVideoInfoRaw(unittest.TestCase):
    """Test _fetch_video_info_raw with auth fallback logic."""

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_auth_ydl_opts")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_successful_unauthenticated_fetch(
        self, mock_get_opts, mock_get_auth_opts, mock_ydl_class
    ):
        """Test successful fetch without authentication."""
        mock_get_opts.return_value = {"quiet": True}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "id": "vid123",
            "title": "Test Video",
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")
        assert result is not None

        self.assertEqual(result["id"], "vid123")
        # Should only call unauthenticated opts
        mock_get_opts.assert_called_once()
        mock_get_auth_opts.assert_not_called()

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_auth_ydl_opts")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_fallback_to_authenticated(self, mock_get_opts, mock_get_auth_opts, mock_ydl_class):
        """Test fallback to authenticated when unauthenticated fails."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        mock_ydl = MagicMock()
        # First call (unauthenticated) fails
        # Second call (authenticated) succeeds
        mock_ydl.__enter__.return_value.extract_info.side_effect = [
            Exception("Access denied"),
            {"id": "vid123", "title": "Test Video"},
        ]
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")
        assert result is not None

        self.assertEqual(result["id"], "vid123")
        # Should try both
        mock_get_opts.assert_called_once()
        mock_get_auth_opts.assert_called_once_with(use_browser_fallback=True)
        # Should have called extract_info twice
        self.assertEqual(mock_ydl.__enter__.return_value.extract_info.call_count, 2)

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_auth_ydl_opts")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_both_attempts_fail(self, mock_get_opts, mock_get_auth_opts, mock_ydl_class):
        """Test returns None when both auth attempts fail."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")

        self.assertIsNone(result)


class TestYtDlpOptsCompatibility(unittest.TestCase):
    """Regression tests for passing typed yt-dlp opts into YoutubeDL."""

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_channel_video_fetch_passes_plain_dict_to_youtubedl(self, mock_get_opts, mock_ydl_cls):
        mock_get_opts.return_value = YtDlpParams.model_validate({"quiet": True})
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
        mock_ydl_cls.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://www.youtube.com/@example/videos")

        self.assertEqual(result, [])
        self.assertTrue(mock_ydl_cls.called)
        opts_arg = mock_ydl_cls.call_args[0][0]
        self.assertIsInstance(opts_arg, dict)
        self.assertTrue(opts_arg.get("extract_flat"))


class TestFetchVideoInfo(unittest.TestCase):
    """Test get_video_info caching wrapper."""

    @patch("src.youtube.ytdlp._fetch_video_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_returns_cached_when_available(self, mock_cache, mock_fetch_raw):
        """Test returns cached data when available."""
        cached_data = {"id": "vid123", "title": "Cached Video"}
        mock_cache.get.return_value = cached_data

        result = get_video_info("vid123")

        self.assertIsInstance(result, VideoInfo)
        assert result is not None
        self.assertEqual(result.id, "vid123")
        self.assertEqual(result.title, "Cached Video")
        mock_cache.get.assert_called_once_with("get_video_info:vid123")
        mock_fetch_raw.assert_not_called()

    @patch("src.youtube.ytdlp._fetch_video_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_fetches_and_caches_when_not_cached(self, mock_cache, mock_fetch_raw):
        """Test fetches from API and caches when not in cache."""
        mock_cache.get.return_value = None
        fetched_data = {
            "id": "vid123",
            "title": "Fresh Video",
            "formats": [{"id": "heavy"}],
            "view_count": 12,
        }
        mock_fetch_raw.return_value = fetched_data

        result = get_video_info("vid123")

        self.assertIsInstance(result, VideoInfo)
        assert result is not None
        self.assertEqual(result.id, "vid123")
        self.assertEqual(result.title, "Fresh Video")
        mock_cache.get.assert_called_once_with("get_video_info:vid123")
        mock_fetch_raw.assert_called_once_with("vid123")
        mock_cache.set.assert_called_once_with(
            "get_video_info:vid123",
            {
                "id": "vid123",
                "title": "Fresh Video",
                "view_count": 12,
            },
        )

    @patch("src.youtube.ytdlp._fetch_video_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_returns_none_when_fetch_fails(self, mock_cache, mock_fetch_raw):
        """Test returns None when fetch fails."""
        mock_cache.get.return_value = None
        mock_fetch_raw.return_value = None

        result = get_video_info("vid123")

        self.assertIsNone(result)
        mock_cache.set.assert_not_called()


class TestFetchChannelInfoRaw(unittest.TestCase):
    """Test _fetch_channel_info_raw function."""

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_fetch_channel_without_videos(self, mock_get_opts, mock_ydl_class):
        """Test fetching channel metadata without video entries."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "title": "Test Channel",
            "uploader": "Test",
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test", fetch_videos=False)
        assert result is not None

        self.assertEqual(result["title"], "Test Channel")
        # Verify playlistend=0 was set
        opts = mock_get_opts.return_value
        self.assertEqual(opts["extract_flat"], True)
        self.assertEqual(opts["playlistend"], 0)

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_fetch_channel_with_videos(self, mock_get_opts, mock_ydl_class):
        """Test fetching channel with video entries."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "title": "Test Channel",
            "entries": [{"id": "vid1"}],
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test", fetch_videos=True)

        self.assertIsNotNone(result)
        # Verify playlistend was NOT set
        opts = mock_get_opts.return_value
        self.assertNotIn("playlistend", opts)

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_returns_none_on_error(self, mock_get_opts, mock_ydl_class):
        """Test returns None when fetch fails."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test")

        self.assertIsNone(result)


class TestFetchChannelVideosRaw(unittest.TestCase):
    """Test _fetch_channel_videos_raw function."""

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_fetch_with_default_params(self, mock_get_opts, mock_ydl_class):
        """Test fetching with default parameters."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "entries": [
                {"id": "vid1", "title": "Video 1"},
                {"id": "vid2", "title": "Video 2"},
            ]
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "vid1")
        # Verify default opts
        opts = mock_get_opts.return_value
        self.assertEqual(opts["extract_flat"], True)
        self.assertEqual(opts["playlistreverse"], False)
        self.assertEqual(opts["playliststart"], 1)
        self.assertIsNone(opts["playlistend"])

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_fetch_with_custom_range(self, mock_get_opts, mock_ydl_class):
        """Test fetching with custom start/end range."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
        mock_ydl_class.return_value = mock_ydl

        _fetch_channel_videos_raw("https://youtube.com/@test", start=10, end=25, reverse=True)

        opts = mock_get_opts.return_value
        self.assertEqual(opts["playliststart"], 10)
        self.assertEqual(opts["playlistend"], 25)
        self.assertEqual(opts["playlistreverse"], True)

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_returns_empty_list_on_error(self, mock_get_opts, mock_ydl_class):
        """Test returns empty list when fetch fails."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        self.assertEqual(result, [])

    @patch("src.youtube.ytdlp.YoutubeDL")
    @patch("src.youtube.ytdlp.get_ydl_opts")
    def test_handles_none_response(self, mock_get_opts, mock_ydl_class):
        """Test handles None response from yt-dlp."""
        mock_get_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = None
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        self.assertEqual(result, [])


class TestGetCachedChannelInfo(unittest.TestCase):
    """Test get_channel_info with cache expiry."""

    @patch("src.youtube.ytdlp._fetch_channel_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_returns_cached_data(self, mock_cache, mock_fetch_raw):
        """Test returns cached data when available."""
        cached_data = {"title": "Cached Channel"}
        mock_cache.get.return_value = cached_data

        result = get_channel_info("https://youtube.com/@test")

        self.assertIsInstance(result, ChannelInfo)
        assert result is not None
        self.assertEqual(result.title, "Cached Channel")
        mock_cache.get.assert_called_once_with("get_youtube_channel:https://youtube.com/@test")
        mock_fetch_raw.assert_not_called()

    @patch("src.youtube.ytdlp.random")
    @patch("src.youtube.ytdlp._fetch_channel_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_fetches_and_caches_with_expiry(self, mock_cache, mock_fetch_raw, mock_random):
        """Test fetches and caches with 25-35 day expiry."""
        mock_cache.get.return_value = None
        fetched_data = {
            "title": "Fresh Channel",
            "entries": [{"id": "vid123"}],
        }
        mock_fetch_raw.return_value = fetched_data
        mock_random.randint.return_value = 30  # 30 days

        result = get_channel_info("https://youtube.com/@test")

        self.assertIsInstance(result, ChannelInfo)
        assert result is not None
        self.assertEqual(result.title, "Fresh Channel")
        mock_fetch_raw.assert_called_once_with("https://youtube.com/@test", fetch_videos=False)
        # Verify cache expiry is 25-35 days
        mock_random.randint.assert_called_once_with(25, 35)
        expected_expire = 30 * 24 * 3600
        mock_cache.set.assert_called_once_with(
            "get_youtube_channel:https://youtube.com/@test",
            {"title": "Fresh Channel"},
            expire=expected_expire,
        )

    @patch("src.youtube.ytdlp._fetch_channel_info_raw")
    @patch("src.youtube.ytdlp._CACHE")
    def test_returns_none_when_fetch_fails(self, mock_cache, mock_fetch_raw):
        """Test returns None when fetch fails."""
        mock_cache.get.return_value = None
        mock_fetch_raw.return_value = None

        result = get_channel_info("https://youtube.com/@test")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
