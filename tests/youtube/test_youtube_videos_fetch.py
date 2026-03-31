"""Tests for get_youtube_episodes with focus on caching, early termination, and completeness."""

from unittest.mock import MagicMock, patch
from pathlib import Path
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.youtube.metadata import get_youtube_episodes
from src.models import RssEpisode


class TestGetYoutubeVideosCache(unittest.TestCase):
    """Test caching behavior of get_youtube_episodes."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_returns_episodes_from_ytdlp(self, mock_get_videos, mock_normalize):
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
            "https://youtube.com/@test", "test_author", detailed=False
        )

        # Should return the episodes
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "dQw4w9WgXcQ")
        self.assertEqual(result[1].id, "XqZsoesa55w")

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_cache_key_format(self, mock_get_videos, mock_normalize):
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


class TestGetYoutubeVideosEarlyTermination(unittest.TestCase):
    """Test early termination logic in get_youtube_episodes."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_returns_empty_when_no_videos(self, mock_get_videos, mock_normalize):
        """Test returns empty list when no videos returned."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.return_value = []

        result = get_youtube_episodes("https://youtube.com/@test", "test_author")

        # Should return empty list
        self.assertEqual(result, [])

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_handles_single_video(self, mock_get_videos, mock_normalize):
        """Test handles single video case."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        mock_episode = RssEpisode(
            id="dQw4w9WgXcQ",
            title="Single Video",
            author="test_author",
            content="https://youtube.com/watch?v=dQw4w9WgXcQ",
            duration=300,
        )

        mock_get_videos.return_value = [mock_episode]

        result = get_youtube_episodes("https://youtube.com/@test", "test_author")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "dQw4w9WgXcQ")


class TestGetYoutubeVideosCompleteness(unittest.TestCase):
    """Test completeness - ensures all new videos are fetched."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_fetches_multiple_videos(self, mock_get_videos, mock_normalize):
        """Test that multiple videos are processed."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        # Mock multiple videos
        videos = [
            "RgKAFK5djSk",
            "9bZkp7q19f0",
            "OPf0YbXqDm0",
            "hq3yfQnllfQ",
            "JGwWNGJdvx8",
            "RgKAFK5djSk",
            "9bZkp7q19f0",
            "OPf0YbXqDm0",
            "hq3yfQnllfQ",
            "JGwWNGJdvx8",
        ]
        mock_episodes = [
            RssEpisode(
                id=f"{videos[i]}",
                title=f"Video {i}",
                author="test_author",
                content=f"https://youtube.com/watch?v={videos[i]}",
                duration=100 + i * 10,
            )
            for i in range(10)
        ]

        mock_get_videos.return_value = mock_episodes

        result = get_youtube_episodes("https://youtube.com/@test", "test_author")

        # Should fetch all videos
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0].id, "RgKAFK5djSk")
        self.assertEqual(result[9].id, "JGwWNGJdvx8")


class TestGetYoutubeVideosFilter(unittest.TestCase):
    """Test filtering functionality."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    @patch("src.youtube.metadata.re_compile")
    def test_filters_videos_by_pattern(
        self, mock_re_compile, mock_get_videos, mock_normalize
    ):
        """Test that videos are filtered by title pattern."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        # Mock regex pattern that matches some videos
        mock_pattern = MagicMock()
        mock_pattern.search.side_effect = lambda title: "test" in title.lower()
        mock_re_compile.return_value = mock_pattern

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
                title="Random Video",
                author="test_author",
                content="https://youtube.com/watch?v=XqZsoesa55w",
                duration=200,
            ),
            RssEpisode(
                id="kJQP7kiw5Fk",
                title="Another Test Video",
                author="test_author",
                content="https://youtube.com/watch?v=kJQP7kiw5Fk",
                duration=150,
            ),
        ]

        mock_get_videos.return_value = mock_episodes

        result = get_youtube_episodes(
            "https://youtube.com/@test", "test_author", filter="test"
        )

        # Should only include videos with "test" in title
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "dQw4w9WgXcQ")
        self.assertEqual(result[1].id, "kJQP7kiw5Fk")


class TestGetYoutubeVideosDetailed(unittest.TestCase):
    """Test detailed metadata functionality."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    @patch("src.youtube.metadata._add_episode_metadata")
    def test_adds_detailed_metadata(
        self, mock_add_metadata, mock_get_videos, mock_normalize
    ):
        """Test that detailed metadata is added when detailed=True."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        mock_episode = RssEpisode(
            id="e_04ZrNroTo",
            title="Test Video",
            author="test_author",
            content="https://youtube.com/watch?v=e_04ZrNroTo",
            duration=100,
        )

        mock_get_videos.return_value = [mock_episode]
        mock_add_metadata.return_value = mock_episode

        result = get_youtube_episodes(
            "https://youtube.com/@test", "test_author", detailed=True
        )

        # Should call _add_episode_metadata for each episode
        self.assertEqual(len(result), 1)
        mock_add_metadata.assert_called_once_with(mock_episode, "test_author")

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_skips_detailed_metadata(self, mock_get_videos, mock_normalize):
        """Test that detailed metadata is skipped when detailed=False."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"

        mock_episode = RssEpisode(
            id="e_04ZrNroTo",
            title="Test Video",
            author="test_author",
            content="https://youtube.com/watch?v=e_04ZrNroTo",
            duration=100,
        )

        mock_get_videos.return_value = [mock_episode]

        result = get_youtube_episodes(
            "https://youtube.com/@test", "test_author", detailed=False
        )

        # Should return episodes without adding metadata
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "e_04ZrNroTo")


class TestGetYoutubeVideosEdgeCases(unittest.TestCase):
    """Test edge cases and error scenarios."""

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_returns_empty_when_no_entries(self, mock_get_videos, mock_normalize):
        """Test returns empty list when no video entries."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.return_value = []

        result = get_youtube_episodes("https://youtube.com/@test", "test_author")

        self.assertEqual(result, [])

    @patch("src.youtube.metadata._normalize_youtube_link")
    @patch("src.youtube.ytdlp.get_youtube_videos")
    def test_raises_exception_on_network_error(self, mock_get_videos, mock_normalize):
        """Test that network exceptions are propagated."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.side_effect = Exception("Network error")

        # Should raise exception when underlying call fails
        with self.assertRaises(Exception) as context:
            get_youtube_episodes("https://youtube.com/@test", "test_author")

        self.assertEqual(str(context.exception), "Network error")


if __name__ == "__main__":
    unittest.main()
