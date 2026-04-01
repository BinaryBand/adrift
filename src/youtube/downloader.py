"""
YouTube video downloader with pytubefix and yt-dlp fallback support.
"""

from typing import Any, cast
from pathlib import Path

import yt_dlp
import sys

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

    def _progress_hook(d: dict[str, Any]) -> None:
        if d.get("status") == "downloading" and callback:
            try:
                progress = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                callback(progress, total)
            except Exception:
                pass

    opts: YtDlpParams = get_auth_ydl_opts(use_browser_fallback=True)
    opts["format"] = "bestaudio/best"
    opts["outtmpl"] = (dir / f"{id}.%(ext)s").as_posix()
    opts["postprocessors"] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "192",
        }
    ]

    # Override extractor_args for downloads: use player clients that expose
    # audio-only streams without needing a PoToken.
    # - android_music: YouTube Music client; best for audio-only formats
    # - web: uses browser cookies for authenticated access as fallback
    # (The base opts carry skip:["js"] intended for fast metadata-only fetches;
    # we replace it here so JS-gated formats are included in the download.)
    opts["extractor_args"] = {"youtube": {"player_client": ["android_music", "web"]}}

    if callback:
        opts["progress_hooks"] = [_progress_hook]

    # Download video
    url = f"https://www.youtube.com/watch?v={id}"
    try:
        with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
            info = ydl.extract_info(url, download=True)
            info_dict = cast(dict[str, Any], info)

            if info_dict and "requested_downloads" in info_dict:
                downloads = info_dict["requested_downloads"]
                if downloads:
                    downloaded_file = downloads[0]["filepath"]
                    file_path = Path(downloaded_file)

                    # Check for m4a version (post-processed)
                    m4a_path = file_path.with_suffix(".m4a")
                    if m4a_path.exists():
                        return m4a_path
                    elif file_path.exists():
                        return file_path
                    else:
                        print(f"WARNING: Downloaded file not found: {file_path}")
                        return None

    except Exception as e:
        error_msg = str(e)
        if _is_bot_detection_error(error_msg) and PROPAGATE_BOT_DETECTION:
            raise BotDetectionError(error_msg)
        print(f"WARNING: yt-dlp download failed for {id}: {e}")
        raise

    return None


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

    video_id = _extract_video_id(url)
    if not video_id:
        print(f"WARNING: Could not extract video ID from {url}")
        return None

    try:
        return _ytdlp_download(video_id, dir, callback)
    except BotDetectionError:
        raise
    except Exception as e:
        error_msg = str(e)
        if _is_bot_detection_error(error_msg):
            if PROPAGATE_BOT_DETECTION:
                raise BotDetectionError(error_msg)
        print(f"WARNING: download failed for {url}: {e}")
        return None
