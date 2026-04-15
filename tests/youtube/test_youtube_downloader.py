"""Tests for YouTube downloader functionality."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())

import src.youtube.downloader as yt_downloader
from src.models import YtDlpParams
from src.youtube.downloader import (
    _AUDIO_FORMATS_FALLBACK,
    _DOWNLOAD_ATTEMPTS,
    _PLAYER_CLIENTS_STUB_FALLBACK,
    BotDetectionError,
    _build_download_opts,
    _DownloadAttemptConfig,
    _extract_video_id,
    _is_bot_detection_error,
    _ytdlp_download,
    download_video,
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

    @patch(
        "src.youtube.downloader.get_auth_ydl_opts",
        return_value=YtDlpParams.model_validate({"quiet": True}),
    )
    @patch("src.youtube.downloader.yt_dlp.YoutubeDL")
    @patch("pathlib.Path.exists", return_value=True)
    def test_typed_opts_are_converted_to_plain_dict(self, _exists, mock_ydl_cls, _opts):
        mock_ydl_cls.return_value = self._make_ydl_mock("/tmp/abc.m4a")

        result = _ytdlp_download("abc123", Path("/tmp"))

        self.assertEqual(result, Path("/tmp/abc.m4a"))
        opts_arg = mock_ydl_cls.call_args[0][0]
        self.assertIsInstance(opts_arg, dict)
        self.assertEqual(opts_arg.get("quiet"), True)

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


class TestDownloadAttemptSequence(unittest.TestCase):
    """Lock in the _DOWNLOAD_ATTEMPTS sequence and _build_download_opts behaviour.

    These tests exist so that changes to the attempt order or auth strategy
    require an explicit, reviewed update here rather than an accidental diff.
    """

    def test_attempts_start_unauthenticated(self):
        """Unauthenticated for two attempts to avoid cookie-induced format restrictions."""
        unauth = [(a, c, f) for a, c, f in _DOWNLOAD_ATTEMPTS if not a]
        self.assertGreaterEqual(len(unauth), 2, "expected at least 2 unauthenticated attempts")
        first_auth_index = next(i for i, (a, _, _) in enumerate(_DOWNLOAD_ATTEMPTS) if a)
        self.assertGreater(
            first_auth_index,
            0,
            "first attempt must be unauthenticated",
        )

    def test_attempts_include_authenticated_fallback(self):
        """At least one authenticated attempt must exist (for age-restricted content)."""
        auth = [t for t in _DOWNLOAD_ATTEMPTS if t[0]]
        self.assertGreater(len(auth), 0)

    def test_attempts_include_no_format_selector(self):
        """At least one attempt must use no format selector so yt-dlp can choose freely."""
        no_format = [t for t in _DOWNLOAD_ATTEMPTS if t[2] is None]
        self.assertGreater(len(no_format), 0)

    def test_attempts_include_player_client_fallback(self):
        """At least one attempt must use the stub player-client fallback."""
        with_clients = [t for t in _DOWNLOAD_ATTEMPTS if t[1] is not None]
        self.assertGreater(len(with_clients), 0)

    def test_attempt_format_selectors_use_fallback_constant(self):
        """Any non-None format selector must be _AUDIO_FORMATS_FALLBACK (bestaudio/best)."""
        for auth, clients, fmt in _DOWNLOAD_ATTEMPTS:
            if fmt is not None:
                self.assertEqual(
                    fmt,
                    _AUDIO_FORMATS_FALLBACK,
                    f"Unexpected format selector {fmt!r} in attempt ({auth}, {clients}, {fmt})",
                )

    def test_player_client_fallback_constant(self):
        """_PLAYER_CLIENTS_STUB_FALLBACK must contain tv_embedded and web."""
        self.assertIn("tv_embedded", _PLAYER_CLIENTS_STUB_FALLBACK)
        self.assertIn("web", _PLAYER_CLIENTS_STUB_FALLBACK)

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_build_opts_unauthenticated_calls_get_ydl_opts(self, mock_get_ydl):
        _build_download_opts(
            "abc", Path("/tmp"), attempt=_DownloadAttemptConfig(authenticated=False)
        )
        mock_get_ydl.assert_called_once()

    @patch(
        "src.youtube.downloader.get_auth_ydl_opts",
        return_value=YtDlpParams.model_validate({}),
    )
    def test_build_opts_authenticated_calls_get_auth_ydl_opts(self, mock_get_auth):
        _build_download_opts(
            "abc", Path("/tmp"), attempt=_DownloadAttemptConfig(authenticated=True)
        )
        mock_get_auth.assert_called_once_with(use_browser_fallback=True)

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_build_opts_sets_format_when_provided(self, _opts):
        result = _build_download_opts(
            "abc",
            Path("/tmp"),
            attempt=_DownloadAttemptConfig(format_selector="bestaudio/best"),
        )
        self.assertEqual(result["format"], "bestaudio/best")

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_build_opts_omits_format_when_none(self, _opts):
        result = _build_download_opts(
            "abc", Path("/tmp"), attempt=_DownloadAttemptConfig(format_selector=None)
        )
        dumped = result.model_dump(exclude_none=True)
        self.assertNotIn("format", dumped)

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_build_opts_sets_player_clients_when_provided(self, _opts):
        result = _build_download_opts(
            "abc",
            Path("/tmp"),
            attempt=_DownloadAttemptConfig(
                authenticated=False,
                player_clients=["tv_embedded"],
            ),
        )
        self.assertEqual(result["extractor_args"], {"youtube": {"player_client": ["tv_embedded"]}})

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    @patch("src.youtube.downloader.get_auth_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_ytdlp_download_retries_on_format_error(self, mock_auth, mock_unauth):
        """Format errors on early attempts must be swallowed and retried."""
        format_error = Exception("Requested format is not available")
        success_info = {"requested_downloads": [{"filepath": "/tmp/abc.m4a"}]}
        call_count = 0

        def fake_extract_info(url, download):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise format_error
            return success_info

        with (
            patch("src.youtube.downloader.yt_dlp.YoutubeDL") as mock_cls,
            patch("pathlib.Path.exists", return_value=True),
        ):
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value.extract_info.side_effect = fake_extract_info
            mock_cls.return_value = mock_ydl
            result = _ytdlp_download("abc", Path("/tmp"))

        self.assertEqual(result, Path("/tmp/abc.m4a"))
        self.assertEqual(call_count, 3)

    @patch("src.youtube.downloader.get_ydl_opts", return_value=YtDlpParams.model_validate({}))
    @patch("src.youtube.downloader.get_auth_ydl_opts", return_value=YtDlpParams.model_validate({}))
    def test_ytdlp_download_raises_after_all_attempts_fail(self, mock_auth, mock_unauth):
        """If every attempt raises a format error the last exception must propagate."""
        with patch("src.youtube.downloader.yt_dlp.YoutubeDL") as mock_cls:
            mock_ydl = MagicMock()
            mock_ydl.__enter__.return_value.extract_info.side_effect = Exception(
                "Requested format is not available"
            )
            mock_cls.return_value = mock_ydl
            with self.assertRaises(Exception, msg="Requested format is not available"):
                _ytdlp_download("abc", Path("/tmp"))
        self.assertEqual(
            mock_ydl.__enter__.return_value.extract_info.call_count, len(_DOWNLOAD_ATTEMPTS)
        )


if __name__ == "__main__":
    unittest.main()
