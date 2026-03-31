"""Tests for YouTube downloader functionality."""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import unittest
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.youtube.downloader import (
    _extract_video_id,
    _is_bot_detection_error,
    _create_progress_callback,
    _pytubefix_download,
    _ytdlp_download,
    download_video,
)


class TestHelperFunctions(unittest.TestCase):
    """Test helper utility functions."""

    def test_extract_video_id_standard_url(self):
        """Test extracting video ID from standard YouTube URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = _extract_video_id(url)
        self.assertEqual(result, "dQw4w9WgXcQ")

    def test_extract_video_id_with_params(self):
        """Test extracting video ID from URL with parameters."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s"
        result = _extract_video_id(url)
        self.assertEqual(result, "dQw4w9WgXcQ")

    def test_extract_video_id_invalid_url(self):
        """Test that invalid URL returns None."""
        url = "https://example.com/video"
        result = _extract_video_id(url)
        self.assertIsNone(result)

    def test_is_bot_detection_error_with_bot_message(self):
        """Test bot detection with clear bot message."""
        error_msg = "This request was detected as a bot"
        self.assertTrue(_is_bot_detection_error(error_msg))

    def test_is_bot_detection_error_with_429(self):
        """Test bot detection with 429 status code."""
        error_msg = "HTTP Error 429: Too Many Requests"
        self.assertTrue(_is_bot_detection_error(error_msg))

    def test_is_bot_detection_error_with_rate_limit(self):
        """Test bot detection with rate limit message."""
        error_msg = "rate limit exceeded"
        self.assertTrue(_is_bot_detection_error(error_msg))

    def test_is_bot_detection_error_normal_error(self):
        """Test that normal errors don't trigger bot detection."""
        error_msg = "Network connection failed"
        self.assertFalse(_is_bot_detection_error(error_msg))

    def test_create_progress_callback_none(self):
        """Test creating progress callback with None input."""
        result = _create_progress_callback(None)
        self.assertIsNone(result)

    def test_create_progress_callback_with_function(self):
        """Test creating progress callback with function."""
        mock_callback = Mock()
        result = _create_progress_callback(mock_callback)
        self.assertIsNotNone(result)
        self.assertTrue(callable(result))


class TestPytubefixDownload(unittest.TestCase):
    """Test pytubefix download functionality."""

    @patch("src.youtube.downloader.YouTube")
    def test_pytubefix_download_success(self, mock_youtube_class):
        """Test successful download with pytubefix."""
        # Setup mock YouTube object
        mock_yt = Mock()
        mock_stream = Mock()
        mock_stream.download.return_value = "/tmp/video.mp4"

        mock_streams = Mock()
        mock_streams.filter.return_value.order_by.return_value.desc.return_value.first.return_value = mock_stream
        mock_yt.streams = mock_streams

        mock_youtube_class.return_value = mock_yt

        result = _pytubefix_download(
            "https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"), None
        )

        self.assertEqual(result, Path("/tmp/video.mp4"))
        mock_stream.download.assert_called_once()

    @patch("src.youtube.downloader.YouTube")
    def test_pytubefix_download_no_audio_stream(self, mock_youtube_class):
        """Test handling when no audio stream is available."""
        mock_yt = Mock()
        mock_streams = Mock()

        # No audio-only streams
        mock_audio_streams = Mock()
        mock_audio_streams.first.return_value = None
        mock_streams.filter.return_value.order_by.return_value.desc.return_value = (
            mock_audio_streams
        )

        # Fallback to any stream
        mock_fallback_stream = Mock()
        mock_fallback_stream.download.return_value = "/tmp/video.mp4"
        mock_streams.filter.return_value.order_by.return_value.desc.return_value.first.return_value = mock_fallback_stream

        mock_yt.streams = mock_streams
        mock_youtube_class.return_value = mock_yt

        result = _pytubefix_download(
            "https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"), None
        )

        self.assertIsNotNone(result)

    @patch("src.youtube.downloader.YouTube")
    def test_pytubefix_download_callback(self, mock_youtube_class):
        """Test download with progress callback."""
        mock_yt = Mock()
        mock_stream = Mock()
        mock_stream.download.return_value = "/tmp/video.mp4"

        mock_streams = Mock()
        mock_streams.filter.return_value.order_by.return_value.desc.return_value.first.return_value = mock_stream
        mock_yt.streams = mock_streams

        mock_youtube_class.return_value = mock_yt
        mock_callback = Mock()

        result = _pytubefix_download(
            "https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"), mock_callback
        )

        self.assertIsNotNone(result)


class TestYtDlpDownload(unittest.TestCase):
    """Test yt-dlp download functionality."""

    @patch("src.youtube.downloader.get_auth_ydl_opts")
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    @patch("pathlib.Path.exists")
    def test_ytdlp_download_success(self, mock_exists, mock_ydl_class, mock_auth_opts):
        """Test successful download with yt-dlp."""
        mock_auth_opts.return_value = {}
        mock_exists.return_value = True  # Mock file existence check

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "requested_downloads": [{"filepath": "/tmp/video.m4a"}]
        }
        mock_ydl_class.return_value = mock_ydl

        result = _ytdlp_download("test_id", Path("/tmp"))

        self.assertEqual(result, Path("/tmp/video.m4a"))

    @patch("src.youtube.downloader.get_auth_ydl_opts")
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    @patch("pathlib.Path.exists")
    def test_ytdlp_download_with_callback(
        self, mock_exists, mock_ydl_class, mock_auth_opts
    ):
        """Test yt-dlp download with progress callback."""
        mock_auth_opts.return_value = {}
        mock_exists.return_value = True  # Mock file existence check
        mock_callback = Mock()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.return_value = {
            "requested_downloads": [{"filepath": "/tmp/video.m4a"}]
        }
        mock_ydl_class.return_value = mock_ydl

        result = _ytdlp_download("test_id", Path("/tmp"), mock_callback)

        self.assertIsNotNone(result)

    @patch("src.youtube.downloader.get_auth_ydl_opts")
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    def test_ytdlp_download_error(self, mock_ydl_class, mock_auth_opts):
        """Test error handling in yt-dlp download."""
        mock_auth_opts.return_value = {}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value.extract_info.side_effect = Exception(
            "Download failed"
        )
        mock_ydl_class.return_value = mock_ydl

        with self.assertRaises(Exception):
            _ytdlp_download("test_id", Path("/tmp"))


class TestDownloadVideo(unittest.TestCase):
    """Test main download_video function."""

    @patch("src.youtube.downloader._pytubefix_download")
    def test_download_video_success(self, mock_pytubefix):
        """Test successful video download."""
        mock_pytubefix.return_value = Path("/tmp/video.mp4")

        result = download_video("https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"))

        self.assertEqual(result, Path("/tmp/video.mp4"))
        mock_pytubefix.assert_called_once()

    @patch("src.youtube.downloader._pytubefix_download")
    @patch("src.youtube.downloader._ytdlp_download")
    @patch("src.youtube.downloader._TRY_DOWNLOAD_AGE_RESTRICTED", True)
    def test_download_video_fallback_to_ytdlp(self, mock_ytdlp, mock_pytubefix):
        """Test fallback to yt-dlp when pytubefix fails."""
        mock_pytubefix.side_effect = Exception("Pytubefix failed")
        mock_ytdlp.return_value = Path("/tmp/video.m4a")

        result = download_video("https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"))

        self.assertEqual(result, Path("/tmp/video.m4a"))
        mock_ytdlp.assert_called_once_with("dQw4w9WgXcQ", Path("/tmp"), None)

    @patch("src.youtube.downloader._pytubefix_download")
    @patch("src.youtube.downloader._ytdlp_download")
    @patch("src.youtube.downloader._is_bot_detection_error")
    @patch("src.youtube.downloader._wait_with_progress")
    def test_download_video_bot_detection(
        self, mock_wait, mock_bot_check, mock_ytdlp, mock_pytubefix
    ):
        """Test bot detection triggers cooldown."""
        mock_pytubefix.side_effect = Exception("This request was detected as a bot")
        mock_bot_check.return_value = True
        # Also mock yt-dlp to fail so the function returns None
        mock_ytdlp.side_effect = Exception("yt-dlp also failed")

        result = download_video("https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp"))

        self.assertIsNone(result)
        mock_wait.assert_called_once()
        # Verify cooldown time is within expected range
        call_args = mock_wait.call_args[0]
        self.assertGreaterEqual(call_args[0], 3600)
        self.assertLessEqual(call_args[0], 7200)

    @patch("src.youtube.downloader._pytubefix_download")
    def test_download_video_creates_directory(self, mock_pytubefix):
        """Test that output directory is created."""
        mock_pytubefix.return_value = Path("/tmp/video.mp4")

        with patch("pathlib.Path.mkdir") as mock_mkdir:
            download_video(
                "https://youtube.com/watch?v=dQw4w9WgXcQ", Path("/tmp/new_dir")
            )
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


if __name__ == "__main__":
    unittest.main()
