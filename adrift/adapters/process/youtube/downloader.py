from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from adrift.adapters.process.youtube.auth import YtDlpParams, get_auth_ydl_opts, get_ydl_opts
from adrift.adapters.process.youtube.error_utils import yt_dlp_retry_reason
from adrift.adapters.process.youtube.normalizer import (
    extract_progress_update,
    make_progress_hook,
)
from adrift.core.util.progress import Callback
from adrift.core.util.regex import YOUTUBE_VIDEO_REGEX
from adrift.core.util.terminal import emit_info, emit_warning

# Terminal error reasons that indicate the video cannot be downloaded and should not be retried
_TERMINAL_DOWNLOAD_REASONS = frozenset(
    {
        "members-only video",
        "private video",
        "removed video",
        "video unavailable",
        "geo-restricted video",
        "premiere not yet available",
        "live event not yet started",
    }
)


class BotDetectionError(Exception):
    """Raised when YouTube bot-detection or rate-limiting is encountered."""


class SkippedDownloadError(Exception):
    """Raised when a video cannot be downloaded due to a terminal reason.

    E.g., members-only, private, removed, geo-restricted, etc.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# When True the downloader will raise BotDetectionError on detection so
# callers can handle it; otherwise it logs and returns None.
# Tests rely on the default non-raising behavior so keep this False by default.
PROPAGATE_BOT_DETECTION = False

_MIN_AUDIO_BYTES = 10_240  # files smaller than 10 KB are treated as stub/failed downloads

_BOT_INDICATORS = [
    "This request was detected as a bot",
    "Sign in to confirm you're not a bot",
    "429",
    "Too Many Requests",
    "rate limit",
    "po_token.html",
    "bot detection",
]

_YTDLP_OPERATION_ERRORS = (OSError, RuntimeError, TypeError, ValueError, YtDlpDownloadError)


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    match = YOUTUBE_VIDEO_REGEX.match(url)
    return match.group(4) if match and match.group(4) else None


def _is_bot_detection_error(error_message: str) -> bool:
    """Check if error indicates bot detection or rate limiting."""
    return any(indicator in error_message for indicator in _BOT_INDICATORS)


def _is_terminal_download_reason(error: Exception) -> bool:
    """Check if error indicates a terminal reason that cannot be fixed by retrying."""
    reason = yt_dlp_retry_reason(error, "")
    return reason in _TERMINAL_DOWNLOAD_REASONS


_PLAYER_CLIENTS_STUB_FALLBACK = ["tv_embedded", "web"]
_AUDIO_FORMATS_FALLBACK = "bestaudio/best"

# (authenticated, player_clients, format_selector)
# Unauthenticated attempts first: stale/mismatched browser cookies can cause
# YouTube to serve a restricted format list even for non-age-restricted videos.
# "Sign in" errors from unauthenticated attempts are caught and retried with auth.
