"""
YouTube video downloader with pytubefix and yt-dlp fallback support.
"""

import sys
from pathlib import Path
from typing import Any, cast

import yt_dlp

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.utils.progress import Callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.youtube.auth import YtDlpParams, get_auth_ydl_opts


class BotDetectionError(Exception):
    """Raised when YouTube bot-detection or rate-limiting is encountered."""


# When True the downloader will raise BotDetectionError on detection so
# callers can handle it; otherwise it logs and returns None.
# Tests rely on the default non-raising behavior so keep this False by default.
PROPAGATE_BOT_DETECTION = False

_BOT_INDICATORS = [
    "This request was detected as a bot",
    "Sign in to confirm you're not a bot",
    "429",
    "Too Many Requests",
    "rate limit",
    "po_token.html",
    "bot detection",
]


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    match = YOUTUBE_VIDEO_REGEX.match(url)
    return match.group(4) if match and match.group(4) else None


def _is_bot_detection_error(error_message: str) -> bool:
    """Check if error indicates bot detection or rate limiting."""
    return any(indicator in error_message for indicator in _BOT_INDICATORS)


def _ytdlp_download(
    id: str, dir: Path, callback: Callback | None = None
) -> Path | None:
    """Download video using yt-dlp with authentication support."""
    opts = _build_download_opts(id, dir, callback)
    url = f"https://www.youtube.com/watch?v={id}"
    try:
        info_dict = _extract_download_info(url, opts)
        return _resolve_download_path(info_dict)
    except Exception as e:
        _raise_download_error(id, e)

    return None


def _build_download_opts(
    id: str, dir: Path, callback: Callback | None = None
) -> YtDlpParams:
    opts: YtDlpParams = get_auth_ydl_opts(use_browser_fallback=True)
    opts["format"] = "bestaudio/best"
    opts["outtmpl"] = (dir / f"{id}.%(ext)s").as_posix()
    opts["postprocessors"] = [_audio_postprocessor()]
    opts["extractor_args"] = {"youtube": {"player_client": ["android_music", "web"]}}

    progress_hook = _make_progress_hook(callback)
    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]

    return opts


def _audio_postprocessor() -> dict[str, str]:
    return {
        "key": "FFmpegExtractAudio",
        "preferredcodec": "m4a",
        "preferredquality": "192",
    }


def _make_progress_hook(callback: Callback | None = None):
    if callback is None:
        return None

    def progress_hook(download: dict[str, Any]) -> None:
        if download.get("status") != "downloading":
            return
        try:
            progress = download.get("downloaded_bytes", 0)
            total = download.get("total_bytes") or download.get("total_bytes_estimate")
            callback(progress, total)
        except Exception:
            pass

    return progress_hook


def _extract_download_info(url: str, opts: YtDlpParams) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
        info = ydl.extract_info(url, download=True)
    return cast(dict[str, Any], info)


def _resolve_download_path(info_dict: dict[str, Any]) -> Path | None:
    file_path = _requested_download_path(info_dict)
    if file_path is None:
        return None

    m4a_path = file_path.with_suffix(".m4a")
    if m4a_path.exists():
        return m4a_path
    if file_path.exists():
        return file_path

    print(f"WARNING: Downloaded file not found: {file_path}")
    return None


def _requested_download_path(info_dict: dict[str, Any]) -> Path | None:
    downloads = info_dict.get("requested_downloads")
    if not downloads:
        return None
    downloaded_file = downloads[0].get("filepath")
    if not isinstance(downloaded_file, str):
        return None
    return Path(downloaded_file)


def _raise_download_error(id: str, error: Exception) -> None:
    error_msg = str(error)
    if _is_bot_detection_error(error_msg) and PROPAGATE_BOT_DETECTION:
        raise BotDetectionError(error_msg)
    print(f"WARNING: yt-dlp download failed for {id}: {error}")
    raise error


def download_video(
    url: str, dir: Path, callback: Callback | None = None
) -> Path | None:
    """Download a YouTube video as audio.

    Args:
        url: YouTube video URL
        dir: Output directory for downloaded file
        callback: Optional progress callback function

    Returns:
        Path to downloaded file, or None if download failed/skipped
    """
    dir.mkdir(parents=True, exist_ok=True)

    video_id = _validated_video_id(url)
    if video_id is None:
        return None

    try:
        return _ytdlp_download(video_id, dir, callback)
    except BotDetectionError:
        raise
    except Exception as e:
        return _handle_download_failure(url, e)


def _validated_video_id(url: str) -> str | None:
    video_id = _extract_video_id(url)
    if not video_id:
        print(f"WARNING: Could not extract video ID from {url}")
        return None
    return video_id


def _handle_download_failure(url: str, error: Exception) -> None:
    error_msg = str(error)
    if _is_bot_detection_error(error_msg) and PROPAGATE_BOT_DETECTION:
        raise BotDetectionError(error_msg)
    print(f"WARNING: download failed for {url}: {error}")
    return None
