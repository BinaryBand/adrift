"""Tests for YouTube downloader functionality."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
import src.youtube.downloader as yt_downloader
from src.youtube.downloader import (
    _extract_video_id,
    _is_bot_detection_error,
    _ytdlp_download,
    download_video,
    BotDetectionError,
)


class TestHelperFunctions(unittest.TestCase):
    """Test helper utility functions."""

    def test_extract_video_id_standard_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(_extract_video_id(url), "dQw4w9WgXcQ")

    def test_extract_video_id_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s"
        self.assertEqual(_extract_video_id(url), "dQw4w9WgXcQ")

    def test_extract_video_id_invalid_url(self):
        self.assertIsNone(_extract_video_id("https://example.com/video"))

    def test_extract_video_id_empty_string(self):
        self.assertIsNone(_extract_video_id(""))

    def test_is_bot_detection_direct_message(self):
        self.assertTrue(_is_bot_detection_error("This request was detected as a bot"))

    def test_is_bot_detection_429(self):
        self.assertTrue(_is_bot_detection_error("HTTP Error 429: Too Many Requests"))

    def test_is_bot_detection_rate_limit(self):
        self.assertTrue(_is_bot_detection_error("rate limit exceeded"))

    def test_is_bot_detection_sign_in(self):
        self.assertTrue(_is_bot_detection_error("Sign in to confirm you're not a bot"))

    def test_is_bot_detection_normal_error(self):
        self.assertFalse(_is_bot_detection_error("Network connection failed"))


class TestYtDlpDownload(unittest.TestCase):
    """Test _ytdlp_download."""

    def _make_ydl_mock(self, filepath: str) -> MagicMock:
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "requested_downloads": [{"filepath": filepath}]
        }
        return mock_ydl

    @patch("src.youtube.downloader.get_auth_ydl_opts", return_value={})
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    @patch("pathlib.Path.exists", return_value=True)
    def test_success_returns_path(self, _exists, mock_ydl_cls, _opts):
        mock_ydl_cls.return_value = self._make_ydl_mock("/tmp/abc.m4a")
        result = _ytdlp_download("abc123", Path("/tmp"))
        self.assertEqual(result, Path("/tmp/abc.m4a"))

    @patch("src.youtube.downloader.get_auth_ydl_opts", return_value={})
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    def test_generic_exception_propagates(self, mock_ydl_cls, _opts):
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception("oops")
        mock_ydl_cls.return_value = mock_ydl

        with self.assertRaises(Exception):
            _ytdlp_download("abc123", Path("/tmp"))

    @patch("src.youtube.downloader.get_auth_ydl_opts", return_value={})
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    def test_bot_detection_raises_when_propagate_enabled(self, mock_ydl_cls, _opts):
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception(
            "Sign in to confirm you're not a bot"
        )
        mock_ydl_cls.return_value = mock_ydl

        original = yt_downloader.PROPAGATE_BOT_DETECTION
        yt_downloader.PROPAGATE_BOT_DETECTION = True
        try:
            with self.assertRaises(BotDetectionError):
                _ytdlp_download("abc123", Path("/tmp"))
        finally:
            yt_downloader.PROPAGATE_BOT_DETECTION = original


class TestDownloadVideo(unittest.TestCase):
    """Test the top-level download_video() function."""

    def setUp(self):
        self._orig_propagate = yt_downloader.PROPAGATE_BOT_DETECTION

    def tearDown(self):
        yt_downloader.PROPAGATE_BOT_DETECTION = self._orig_propagate

    @patch("src.youtube.downloader._ytdlp_download")
    def test_success_returns_path(self, mock_dl):
        mock_dl.return_value = Path("/tmp/video.m4a")
        result = download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp"))
        self.assertEqual(result, Path("/tmp/video.m4a"))
        mock_dl.assert_called_once_with("abc1234abcd", Path("/tmp"), None)

    def test_invalid_url_returns_none(self):
        result = download_video("https://example.com/not-youtube", Path("/tmp"))
        self.assertIsNone(result)

    @patch("src.youtube.downloader._ytdlp_download")
    def test_generic_exception_returns_none(self, mock_dl):
        mock_dl.side_effect = Exception("Network error")
        result = download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp"))
        self.assertIsNone(result)

    @patch("src.youtube.downloader._ytdlp_download")
    def test_bot_detection_no_propagate_returns_none(self, mock_dl):
        mock_dl.side_effect = Exception("Sign in to confirm you're not a bot")
        yt_downloader.PROPAGATE_BOT_DETECTION = False
        result = download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp"))
        self.assertIsNone(result)

    @patch("src.youtube.downloader._ytdlp_download")
    def test_bot_detection_with_propagate_raises(self, mock_dl):
        mock_dl.side_effect = Exception("This request was detected as a bot")
        yt_downloader.PROPAGATE_BOT_DETECTION = True
        with self.assertRaises(BotDetectionError):
            download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp"))

    @patch("src.youtube.downloader._ytdlp_download")
    def test_propagated_bot_detection_error_passes_through(self, mock_dl):
        """BotDetectionError raised by _ytdlp_download is always re-raised."""
        mock_dl.side_effect = BotDetectionError("bot")
        with self.assertRaises(BotDetectionError):
            download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp"))

    @patch("src.youtube.downloader._ytdlp_download", return_value=Path("/tmp/v.m4a"))
    def test_creates_output_directory(self, _dl):
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            download_video("https://www.youtube.com/watch?v=abc1234abcd", Path("/tmp/new"))
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


if __name__ == "__main__":
    unittest.main()
