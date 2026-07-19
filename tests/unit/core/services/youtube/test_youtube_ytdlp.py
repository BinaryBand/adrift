"""Tests for YouTube yt-dlp module with focus on caching and error handling."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from adrift.adapters.process.youtube.ytdlp import (
    YOUTUBE_EPISODE_CACHE_FRESHNESS,
    YOUTUBE_RECENT_EPISODE_CHECK_FRESHNESS,
    ChannelInfo,
    VideoInfo,
    _fetch_channel_info_raw,
    _fetch_channel_videos_raw,
    _fetch_video_info_raw,
    _trim_channel_cache_payload,
    _trim_video_cache_payload,
    get_channel_info,
    get_video_info,
    get_youtube_videos,
)
from adrift.core.models import RssEpisode, YtDlpImage, YtDlpParams


def _cached_payload(
    episode: RssEpisode,
    fetched_at: datetime | None = None,
    head_checked_at: datetime | None = None,
) -> dict:
    now = datetime.now(UTC)
    return {
        "fetched_at": (fetched_at or now).isoformat(),
        "head_checked_at": (head_checked_at or now).isoformat(),
        "episodes": {episode.id: episode},
    }


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

        assert video.id == "vid123"
        assert video.title == "Test Video"
        assert video.description == "Test description"
        assert video.duration == 300.5
        assert video.upload_date == datetime(2023, 12, 18)
        assert video.thumbnail == "https://example.com/thumb.jpg"
        assert video.availability == "public"
        assert video.url == "https://youtube.com/watch?v=vid123"

    def test_video_info_with_minimal_data(self):
        """Test VideoInfo model with only required fields."""
        data = {
            "id": "vid123",
            "title": "Test Video",
        }

        video = VideoInfo.model_validate(data)

        assert video.id == "vid123"
        assert video.title == "Test Video"
        assert video.description is None
        assert video.duration is None

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

        assert channel.title == "Test Channel"
        assert channel.uploader == "Test Uploader"
        assert channel.uploader_id == "test_id"
        assert channel.description == "Channel description"
        assert channel.thumbnails is not None
        assert isinstance(channel.thumbnails[0], YtDlpImage)


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

        assert "formats" not in trimmed
        assert "subtitles" not in trimmed
        assert trimmed["id"] == "vid123"
        assert trimmed["view_count"] == 10

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

        assert "entries" not in trimmed
        assert trimmed["title"] == "Channel"


class TestFetchVideoInfoRaw(unittest.TestCase):
    """Test _fetch_video_info_raw with auth fallback logic."""

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_auth_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_successful_unauthenticated_fetch(
        self,
        mock_get_opts: MagicMock,
        mock_get_auth_opts: MagicMock,
        mock_ydl_class: MagicMock,
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

        assert result["id"] == "vid123"
        # Should only call unauthenticated opts
        mock_get_opts.assert_called_once()
        mock_get_auth_opts.assert_not_called()

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_auth_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_fallback_to_authenticated(
        self,
        mock_get_opts: MagicMock,
        mock_get_auth_opts: MagicMock,
        mock_ydl_class: MagicMock,
    ):
        """Test fallback to authenticated when unauthenticated fails."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        mock_ydl = MagicMock()
        # First call (unauthenticated) fails
        # Second call (authenticated) succeeds
        mock_ydl.__enter__.return_value.extract_info.side_effect = [
            RuntimeError("Access denied"),
            {"id": "vid123", "title": "Test Video"},
        ]
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")
        assert result is not None

        assert result["id"] == "vid123"
        # Should try both
        mock_get_opts.assert_called_once()
        mock_get_auth_opts.assert_called_once_with(use_browser_fallback=True)
        # Should have called extract_info twice
        assert mock_ydl.__enter__.return_value.extract_info.call_count == 2

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_auth_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_both_attempts_fail(
        self,
        mock_get_opts: MagicMock,
        mock_get_auth_opts: MagicMock,
        mock_ydl_class: MagicMock,
    ):
        """Test returns None when both auth attempts fail."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = RuntimeError("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")

        assert result is None

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_auth_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_terminal_members_only_failure_skips_authenticated_retry(
        self,
        mock_cache: MagicMock,
        mock_get_opts: MagicMock,
        mock_get_auth_opts: MagicMock,
        mock_ydl_class: MagicMock,
    ):
        """Members-only errors should be marked locked and avoid auth fallback."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = RuntimeError(
            "Join this channel to get access to members-only content"
        )
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")

        assert result is None
        mock_get_auth_opts.assert_not_called()
        assert mock_ydl.__enter__.return_value.extract_info.call_count == 1
        mock_cache.set.assert_called_once()

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_auth_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_terminal_members_only_non_runtime_error_skips_retry(
        self,
        mock_cache: MagicMock,
        mock_get_opts: MagicMock,
        mock_get_auth_opts: MagicMock,
        mock_ydl_class: MagicMock,
    ):
        """Non-RuntimeError exceptions (e.g. yt-dlp DownloadError) trigger the locked guard."""
        mock_get_opts.return_value = {"quiet": True}
        mock_get_auth_opts.return_value = {"cookiesfrombrowser": "firefox"}

        # Simulate yt-dlp DownloadError which is Exception but NOT RuntimeError
        class FakeDownloadError(Exception):
            pass

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = FakeDownloadError(
            "ERROR: [youtube] vid123: Join this channel to get access to members-only content"
        )
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_video_info_raw("vid123")

        assert result is None
        mock_get_auth_opts.assert_not_called()
        assert mock_ydl.__enter__.return_value.extract_info.call_count == 1
        mock_cache.set.assert_called_once()


class TestYtDlpOptsCompatibility(unittest.TestCase):
    """Regression tests for passing typed yt-dlp opts into YoutubeDL."""

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_channel_video_fetch_passes_plain_dict_to_youtubedl(
        self, mock_get_opts: MagicMock, mock_ydl_cls: MagicMock
    ):
        mock_get_opts.return_value = YtDlpParams.model_validate({"quiet": True})
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
        mock_ydl_cls.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://www.youtube.com/@example/videos")

        assert result == []
        assert mock_ydl_cls.called
        opts_arg = mock_ydl_cls.call_args[0][0]
        assert isinstance(opts_arg, dict)
        assert opts_arg.get("extract_flat")


class TestFetchVideoInfo(unittest.TestCase):
    """Test get_video_info caching wrapper."""

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_returns_cached_when_available(self, mock_cache: MagicMock, mock_fetch_raw: MagicMock):
        """Test returns cached data when available."""
        cached_data = {"id": "vid123", "title": "Cached Video"}

        def _cache_get_side_effect(key: str):
            if key == "get_video_info_locked:vid123":
                return None
            if key == "get_video_info:vid123":
                return cached_data
            return None

        mock_cache.get.side_effect = _cache_get_side_effect

        result = get_video_info("vid123")

        assert isinstance(result, VideoInfo)
        assert result is not None
        assert result.id == "vid123"
        assert result.title == "Cached Video"
        assert mock_cache.get.call_args_list[1].args[0] == "get_video_info:vid123"
        mock_fetch_raw.assert_not_called()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_skips_fetch_for_locked_video(self, mock_cache: MagicMock, mock_fetch_raw: MagicMock):
        """Locked videos should short-circuit before fetch attempts."""

        def _cache_get_side_effect(key: str):
            if key == "get_video_info_locked:vid123":
                return {"reason": "members-only video"}
            return None

        mock_cache.get.side_effect = _cache_get_side_effect

        result = get_video_info("vid123")

        assert result is None
        mock_fetch_raw.assert_not_called()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_fetches_and_caches_when_not_cached(
        self, mock_cache: MagicMock, mock_fetch_raw: MagicMock
    ):
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

        assert isinstance(result, VideoInfo)
        assert result is not None
        assert result.id == "vid123"
        assert result.title == "Fresh Video"
        mock_fetch_raw.assert_called_once_with("vid123")
        mock_cache.set.assert_called_once_with(
            "get_video_info:vid123",
            {
                "id": "vid123",
                "title": "Fresh Video",
                "view_count": 12,
            },
        )

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_returns_none_when_fetch_fails(self, mock_cache: MagicMock, mock_fetch_raw: MagicMock):
        """Test returns None when fetch fails."""
        mock_cache.get.return_value = None
        mock_fetch_raw.return_value = None

        result = get_video_info("vid123")

        assert result is None
        mock_cache.set.assert_not_called()


class TestFetchChannelInfoRaw(unittest.TestCase):
    """Test _fetch_channel_info_raw function."""

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_fetch_channel_without_videos(
        self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock
    ):
        """Test fetching channel metadata without video entries."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "title": "Test Channel",
            "uploader": "Test",
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test", fetch_videos=False)
        assert result is not None

        assert result["title"] == "Test Channel"
        # Verify playlistend=0 was set
        opts = mock_get_opts.return_value
        assert opts.extract_flat
        assert opts.playlistend == 0

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_fetch_channel_with_videos(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test fetching channel with video entries."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "title": "Test Channel",
            "entries": [{"id": "vid1"}],
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test", fetch_videos=True)

        assert result is not None
        # Verify playlistend was NOT set (still None — only set when fetch_videos=False)
        opts = mock_get_opts.return_value
        assert opts.playlistend is None

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_returns_none_on_error(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test returns None when fetch fails."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = RuntimeError("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_info_raw("https://youtube.com/@test")

        assert result is None


class TestFetchChannelVideosRaw(unittest.TestCase):
    """Test _fetch_channel_videos_raw function."""

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_fetch_with_default_params(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test fetching with default parameters."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "entries": [
                {"id": "vid1", "title": "Video 1"},
                {"id": "vid2", "title": "Video 2"},
            ]
        }
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        assert len(result) == 2
        assert result[0]["id"] == "vid1"
        # Verify default opts
        opts = mock_get_opts.return_value
        assert opts.extract_flat
        assert not opts.playlistreverse
        assert opts.playliststart == 1
        assert opts.playlistend is None

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_fetch_with_custom_range(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test fetching with custom start/end range."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {"entries": []}
        mock_ydl_class.return_value = mock_ydl

        _fetch_channel_videos_raw("https://youtube.com/@test", start=10, end=25, reverse=True)

        opts = mock_get_opts.return_value
        assert opts.playliststart == 10
        assert opts.playlistend == 25
        assert opts.playlistreverse

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_returns_empty_list_on_error(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test returns empty list when fetch fails."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = RuntimeError("Network error")
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        assert result == []

    @patch("adrift.adapters.process.youtube.ytdlp.YoutubeDL")
    @patch("adrift.adapters.process.youtube.ytdlp.get_ydl_opts")
    def test_handles_none_response(self, mock_get_opts: MagicMock, mock_ydl_class: MagicMock):
        """Test handles None response from yt-dlp."""
        mock_get_opts.return_value = YtDlpParams()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = None
        mock_ydl_class.return_value = mock_ydl

        result = _fetch_channel_videos_raw("https://youtube.com/@test")

        assert result == []


class TestGetCachedChannelInfo(unittest.TestCase):
    """Test get_channel_info with cache expiry."""

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_channel_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_returns_cached_data(self, mock_cache: MagicMock, mock_fetch_raw: MagicMock):
        """Test returns cached data when available."""
        cached_data = {"title": "Cached Channel"}
        mock_cache.get.return_value = cached_data

        result = get_channel_info("https://youtube.com/@test")

        assert isinstance(result, ChannelInfo)
        assert result is not None
        assert result.title == "Cached Channel"
        mock_cache.get.assert_called_once_with("get_youtube_channel:https://youtube.com/@test")
        mock_fetch_raw.assert_not_called()

    @patch("adrift.adapters.process.youtube.ytdlp.random")
    @patch("adrift.adapters.process.youtube.ytdlp._fetch_channel_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_fetches_and_caches_with_expiry(
        self, mock_cache: MagicMock, mock_fetch_raw: MagicMock, mock_random: MagicMock
    ):
        """Test fetches and caches with 25-35 day expiry."""
        mock_cache.get.return_value = None
        fetched_data = {
            "title": "Fresh Channel",
            "entries": [{"id": "vid123"}],
        }
        mock_fetch_raw.return_value = fetched_data
        mock_random.randint.return_value = 30  # 30 days

        result = get_channel_info("https://youtube.com/@test")

        assert isinstance(result, ChannelInfo)
        assert result is not None
        assert result.title == "Fresh Channel"
        mock_fetch_raw.assert_called_once_with("https://youtube.com/@test", fetch_videos=False)
        # Verify cache expiry is 25-35 days
        mock_random.randint.assert_called_once_with(25, 35)
        expected_expire = 30 * 24 * 3600
        mock_cache.set.assert_called_once_with(
            "get_youtube_channel:https://youtube.com/@test",
            {"title": "Fresh Channel"},
            expire=expected_expire,
        )

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_channel_info_raw")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_returns_none_when_fetch_fails(self, mock_cache: MagicMock, mock_fetch_raw: MagicMock):
        """Test returns None when fetch fails."""
        mock_cache.get.return_value = None
        mock_fetch_raw.return_value = None

        result = get_channel_info("https://youtube.com/@test")

        assert result is None


class TestGetYoutubeVideos(unittest.TestCase):
    """Test episode-list caching and refresh behavior."""

    def setUp(self) -> None:
        self.episode = RssEpisode(
            id="vid123",
            title="Cached Video",
            author="Test Channel",
            content="https://youtube.com/watch?v=vid123",
        )

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_returns_fresh_cached_episode_bundle_without_fetching(
        self, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        episode = self.episode
        mock_cache.get.return_value = _cached_payload(episode)

        result = get_youtube_videos("https://youtube.com/@test/videos", "Test Channel")

        assert result == [episode]
        mock_fetch_batch.assert_not_called()
        mock_cache.set.assert_not_called()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_refresh_bypasses_fresh_episode_bundle(
        self, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        episode = self.episode
        mock_cache.get.return_value = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "head_checked_at": datetime.now(UTC).isoformat(),
            "episodes": {episode.id: episode},
        }
        mock_fetch_batch.side_effect = [[{"id": "vid123", "title": "Cached Video"}]]

        result = get_youtube_videos(
            "https://youtube.com/@test/videos",
            "Test Channel",
            refresh=True,
        )

        assert result == [episode]
        mock_fetch_batch.assert_called_once_with(
            "https://youtube.com/@test/videos",
            "Test Channel",
            1,
            10,
        )
        mock_cache.set.assert_called_once()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    def test_legacy_cached_episode_map_is_treated_as_stale(
        self, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        episode = self.episode
        mock_cache.get.return_value = {episode.id: episode}
        mock_fetch_batch.side_effect = [[{"id": "vid123", "title": "Cached Video"}]]

        result = get_youtube_videos("https://youtube.com/@test/videos", "Test Channel")

        assert result == [episode]
        mock_fetch_batch.assert_called_once()
        cached_payload = mock_cache.set.call_args.args[1]
        assert cached_payload["episodes"] == {episode.id: episode}
        assert "fetched_at" in cached_payload
        assert "head_checked_at" in cached_payload

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    @patch("adrift.adapters.process.youtube.ytdlp._utcnow")
    def test_stale_episode_bundle_triggers_refresh(
        self, mock_utcnow: MagicMock, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        fresh_time = datetime(2026, 4, 17, tzinfo=UTC)
        stale_time = fresh_time - YOUTUBE_EPISODE_CACHE_FRESHNESS - timedelta(seconds=1)
        episode = self.episode
        mock_utcnow.return_value = fresh_time
        mock_cache.get.return_value = _cached_payload(
            episode, fetched_at=stale_time, head_checked_at=stale_time
        )
        mock_fetch_batch.side_effect = [[{"id": "vid123", "title": "Cached Video"}]]

        get_youtube_videos("https://youtube.com/@test/videos", "Test Channel")

        mock_fetch_batch.assert_called_once()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    @patch("adrift.adapters.process.youtube.ytdlp._utcnow")
    def test_recent_probe_refreshes_first_batch_without_full_refresh(
        self, mock_utcnow: MagicMock, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        now = datetime(2026, 4, 20, tzinfo=UTC)
        fetched_at = now - timedelta(hours=2)
        head_checked_at = now - YOUTUBE_RECENT_EPISODE_CHECK_FRESHNESS - timedelta(seconds=1)
        episode = self.episode
        mock_utcnow.return_value = now
        mock_cache.get.return_value = _cached_payload(
            episode, fetched_at=fetched_at, head_checked_at=head_checked_at
        )
        mock_fetch_batch.return_value = [{"id": "vid999", "title": "Brand New Video"}]

        result = get_youtube_videos("https://youtube.com/@test/videos", "Test Channel")

        assert {item.id for item in result} == {"vid123", "vid999"}
        mock_fetch_batch.assert_called_once_with(
            "https://youtube.com/@test/videos",
            "Test Channel",
            1,
            10,
        )
        cached_payload = mock_cache.set.call_args.args[1]
        assert cached_payload["fetched_at"] == fetched_at.isoformat()
        assert cached_payload["head_checked_at"] == now.isoformat()

    @patch("adrift.adapters.process.youtube.ytdlp._fetch_video_batch")
    @patch("adrift.adapters.process.youtube.ytdlp._CACHE")
    @patch("adrift.adapters.process.youtube.ytdlp._utcnow")
    def test_recent_probe_is_skipped_when_head_check_is_fresh(
        self, mock_utcnow: MagicMock, mock_cache: MagicMock, mock_fetch_batch: MagicMock
    ):
        now = datetime(2026, 4, 20, tzinfo=UTC)
        episode = self.episode
        mock_utcnow.return_value = now
        mock_cache.get.return_value = _cached_payload(
            episode, fetched_at=(now - timedelta(hours=2)), head_checked_at=now
        )

        result = get_youtube_videos("https://youtube.com/@test/videos", "Test Channel")

        assert result == [episode]
        mock_fetch_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
