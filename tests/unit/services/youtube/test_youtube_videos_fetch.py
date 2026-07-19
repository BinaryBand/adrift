"""Tests for get_youtube_episodes with focus on caching, early termination, and completeness."""

import unittest
from unittest.mock import MagicMock, patch

from adrift.adapters.process.youtube.metadata import YtFetchOptions, get_youtube_episodes
from adrift.models import RssEpisode


class TestGetYoutubeVideosCache(unittest.TestCase):
    """Test caching behavior of get_youtube_episodes."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_returns_episodes_from_ytdlp(
        self, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test that get_youtube_episodes calls ytdlp.get_youtube_videos."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        # Mock episodes returned by get_youtube_videos
        mock_episodes = [
            RssEpisode(
                id="dQw4w9WgXcQ",
                title="Test Video 1",
                author="test_author",
                content="https://youtube.com/watch?v=dQw4w9WgXcQ",
                duration=100,
            ),
            RssEpisode(
                id="XqZsoesa55w",
                title="Test Video 2",
                author="test_author",
                content="https://youtube.com/watch?v=XqZsoesa55w",
                duration=200,
            ),
        ]

        mock_get_videos.return_value = mock_episodes

        result = get_youtube_episodes(
            "https://youtube.com/@test", "test_author", YtFetchOptions(detailed=False)
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "dQw4w9WgXcQ")
        self.assertEqual(result[1].id, "XqZsoesa55w")

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_cache_key_format(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test that get_youtube_videos is called with correct parameters."""
        normalized_url = "https://youtube.com/@test/videos"
        mock_normalize.return_value = normalized_url
        mock_get_videos.return_value = []

        get_youtube_episodes("https://youtube.com/@test", "test_author")

        # Verify get_youtube_videos was called with normalized URL and author
        mock_get_videos.assert_called_once()
        call_args = mock_get_videos.call_args
        self.assertEqual(call_args[0][0], normalized_url)
        self.assertEqual(call_args[0][1], "test_author")

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_forwards_refresh_option(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test that refresh is forwarded to the yt-dlp layer."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.return_value = []
