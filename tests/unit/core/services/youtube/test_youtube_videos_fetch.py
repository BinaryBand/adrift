"""Tests for get_youtube_episodes with focus on caching, early termination, and completeness."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from adrift.adapters.process.youtube.metadata import YtFetchOptions, get_youtube_episodes
from adrift.core.models import RssEpisode


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
        assert len(result) == 2
        assert result[0].id == "dQw4w9WgXcQ"
        assert result[1].id == "XqZsoesa55w"

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
        assert call_args[0][0] == normalized_url
        assert call_args[0][1] == "test_author"

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_forwards_refresh_option(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test that refresh is forwarded to the yt-dlp layer."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.return_value = []

        get_youtube_episodes(
            "https://youtube.com/@test",
            "test_author",
            YtFetchOptions(detailed=False, refresh=True),
        )

        assert mock_get_videos.call_args.kwargs["refresh"]


class TestGetYoutubeVideosEarlyTermination(unittest.TestCase):
    """Test early termination logic in get_youtube_episodes."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_returns_empty_when_no_videos(
        self, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test returns empty list when no videos returned."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"
        mock_get_videos.return_value = []

        result = get_youtube_episodes(
            "https://youtube.com/@test",
            "test_author",
            YtFetchOptions(detailed=False),
        )

        # Should return empty list
        assert result == []

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_handles_single_video(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test handles single video case."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"

        mock_episode = RssEpisode(
            id="dQw4w9WgXcQ",
            title="Single Video",
            author="test_author",
            content="https://youtube.com/watch?v=dQw4w9WgXcQ",
            duration=300,
        )

        mock_get_videos.return_value = [mock_episode]

        result = get_youtube_episodes(
            "https://youtube.com/@test",
            "test_author",
            YtFetchOptions(detailed=False),
        )

        assert len(result) == 1
        assert result[0].id == "dQw4w9WgXcQ"


class TestGetYoutubeVideosCompleteness(unittest.TestCase):
    """Test completeness - ensures all new videos are fetched."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_fetches_multiple_videos(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test that multiple videos are processed."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"

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

        result = get_youtube_episodes(
            "https://youtube.com/@test",
            "test_author",
            YtFetchOptions(detailed=False),
        )

        # Should fetch all videos
        assert len(result) == 10
        assert result[0].id == "RgKAFK5djSk"
        assert result[9].id == "JGwWNGJdvx8"


class TestGetYoutubeVideosFilter(unittest.TestCase):
    """Test filtering functionality."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    @patch("adrift.adapters.process.youtube.metadata.re_compile")
    def test_filters_videos_by_pattern(
        self, mock_re_compile: MagicMock, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test that videos are filtered by title pattern."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"

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
            "https://youtube.com/@test",
            "test_author",
            YtFetchOptions(detailed=False, filter="test"),
        )

        # Should only include videos with "test" in title
        assert len(result) == 2
        assert result[0].id == "dQw4w9WgXcQ"
        assert result[1].id == "kJQP7kiw5Fk"


class TestGetYoutubeVideosDetailed(unittest.TestCase):
    """Test detailed metadata functionality."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    @patch("adrift.adapters.process.youtube.metadata._add_episode_metadata")
    def test_adds_detailed_metadata(
        self, mock_add_metadata: MagicMock, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test that detailed metadata is added when detailed=True."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"

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
            "https://youtube.com/@test", "test_author", YtFetchOptions(detailed=True)
        )

        # Should call _add_episode_metadata for each episode
        assert len(result) == 1
        mock_add_metadata.assert_called_once_with(mock_episode, "test_author")

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_skips_detailed_metadata(self, mock_get_videos: MagicMock, mock_normalize: MagicMock):
        """Test that detailed metadata is skipped when detailed=False."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"

        mock_episode = RssEpisode(
            id="e_04ZrNroTo",
            title="Test Video",
            author="test_author",
            content="https://youtube.com/watch?v=e_04ZrNroTo",
            duration=100,
        )

        mock_get_videos.return_value = [mock_episode]

        result = get_youtube_episodes(
            "https://youtube.com/@test", "test_author", YtFetchOptions(detailed=False)
        )
        assert len(result) == 1
        assert result[0].id == "e_04ZrNroTo"


class TestGetYoutubeVideosEdgeCases(unittest.TestCase):
    """Test edge cases and error scenarios."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_returns_empty_when_no_entries(
        self, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test returns empty list when no video entries."""
        mock_normalize.return_value = "https://www.youtube.com/playlist?list=PL12345"
        mock_get_videos.return_value = []

        result = get_youtube_episodes("https://youtube.com/@test", "test_author")

        assert result == []

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_raises_exception_on_network_error(
        self, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Test that network exceptions are propagated."""
        mock_normalize.return_value = "https://youtube.com/@test/videos"
        mock_get_videos.side_effect = Exception("Network error")

        # Should raise exception when underlying call fails
        with pytest.raises(Exception, match="Network error") as context:
            get_youtube_episodes("https://youtube.com/@test", "test_author")

        assert str(context.value) == "Network error"


class TestConcurrentChannelFetch(unittest.TestCase):
    """Concurrent fetches of the same channel must not overlap."""

    @patch("adrift.adapters.process.youtube.metadata._normalize_youtube_link")
    @patch("adrift.adapters.process.youtube.ytdlp.get_youtube_videos")
    def test_same_channel_fetches_serialize(
        self, mock_get_videos: MagicMock, mock_normalize: MagicMock
    ):
        """Two threads fetching one channel (reference + download roles) serialize."""
        import threading  # noqa: PLC0415
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        mock_normalize.return_value = "https://youtube.com/@test/videos"
        active = 0
        max_active = 0
        guard = threading.Lock()

        def fake_fetch(*args: object, **kwargs: object) -> list[RssEpisode]:
            nonlocal active, max_active
            del args, kwargs
            with guard:
                active += 1
                max_active = max(max_active, active)
            threading.Event().wait(0.02)
            with guard:
                active -= 1
            return []

        mock_get_videos.side_effect = fake_fetch
        opts = YtFetchOptions(detailed=False)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(get_youtube_episodes, "https://youtube.com/@test", "author", opts)
                for _ in range(2)
            ]
            for future in futures:
                future.result()

        assert max_active == 1


if __name__ == "__main__":
    unittest.main()
