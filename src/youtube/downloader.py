"""
YouTube video downloader with pytubefix and yt-dlp fallback support.
"""

from pytubefix import YouTube
from typing import Any, cast
from pathlib import Path
from tqdm import tqdm

import yt_dlp
import random
import time
import sys

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.utils.progress import Callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.youtube.auth import YtDlpParams, get_auth_ydl_opts


class BotDetectionError(Exception):
    """Raised when YouTube bot-detection or rate-limiting is encountered."""


# When True the downloader will raise BotDetectionError on detection so
# callers can handle it; otherwise the downloader will perform the previous
# cooldown behavior (wait) and continue. Tests rely on the default cooldown
# behavior so keep this False by default.
PROPAGATE_BOT_DETECTION = False


# Constants
_TRY_DOWNLOAD_AGE_RESTRICTED = True
_BOT_COOLDOWN_MIN = 3600  # 1 hour
_BOT_COOLDOWN_MAX = 7200  # 2 hours

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


def _wait_with_progress(seconds: int, reason: str = "Error recovery") -> None:
    """Wait with a progress bar showing minutes elapsed."""
    for _ in tqdm(range(seconds // 60), desc=f"✗ {reason} - Waiting", unit="minutes"):
        time.sleep(60)


def _create_progress_callback(callback: Callback | None):
    """Create a progress callback for pytubefix."""
    if not callback:
        return None

    def _on_progress(stream, _, bytes_remaining) -> None:
        try:
            total = getattr(stream, "filesize", getattr(stream, "filesize_approx", 0))
            downloaded = total - bytes_remaining
            callback(downloaded, total)
        except Exception:
            pass

    return _on_progress


def _pytubefix_download(url: str, dir: Path, callback: Callback | None) -> Path | None:
    """Download video using pytubefix library."""
    yt = YouTube(url)

    # Register progress callback if provided
    progress_callback = _create_progress_callback(callback)
    if progress_callback:
        try:
            cast(Any, yt).register_on_progress_callback(progress_callback)
        except Exception:
            pass

    # Get best audio stream
    streams = yt.streams.filter(only_audio=True).order_by("abr").desc()
    audio_stream = streams.first()

    # Fallback to any stream with audio if no audio-only streams
    if not audio_stream:
        audio_stream = yt.streams.filter().order_by("abr").desc().first()

    if audio_stream:
        downloaded_file = audio_stream.download(dir.as_posix())
        return Path(downloaded_file)

    return None


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
    opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    opts["outtmpl"] = (dir / f"{id}.%(ext)s").as_posix()
    opts["remote_components"] = ["ejs:github"]
    opts["postprocessors"] = [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "192",
        }
    ]

    # Enable remote components for JS challenge solving and remove JS skip
    extractor_args: Any = opts.get("extractor_args", {})
    if isinstance(extractor_args, dict):
        youtube_args: Any = extractor_args.get("youtube", {})
        if isinstance(youtube_args, dict):
            youtube_args.pop("skip", None)
            extractor_args["youtube"] = youtube_args
            opts["extractor_args"] = extractor_args

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
        print(f"WARNING: yt-dlp download failed for {id}: {e}")
        raise

    return None


def download_video(
    url: str, dir: Path, callback: Callback | None = None
) -> Path | None:
    """Download a YouTube video as audio with error handling and fallback.

    Args:
        url: YouTube video URL
        dir: Output directory for downloaded file
        callback: Optional progress callback function

    Returns:
        Path to downloaded file, or None if download failed/skipped
    """
    dir.mkdir(parents=True, exist_ok=True)

    # Try pytubefix first
    bot_cooldown_triggered = False
    try:
        if result := _pytubefix_download(url, dir, callback):
            return result

    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: pytubefix error for {url}: {error_msg}")

        # Handle bot detection: either perform cooldown (back-compat) or
        # raise a dedicated exception when callers request propagation.
        if _is_bot_detection_error(error_msg):
            if PROPAGATE_BOT_DETECTION:
                raise BotDetectionError(error_msg)
            cooldown = random.randint(_BOT_COOLDOWN_MIN, _BOT_COOLDOWN_MAX)
            _wait_with_progress(cooldown, "Bot detection")
            bot_cooldown_triggered = True
        else:
            print(f"WARNING: pytubefix failed for {url}: {e}")

    video_id = _extract_video_id(url)
    if video_id and _TRY_DOWNLOAD_AGE_RESTRICTED:
        try:
            return _ytdlp_download(video_id, dir, callback)
        except BotDetectionError:
            # Propagate if requested
            raise
        except Exception as e:
            error_msg = str(e)
            # If yt-dlp reports a bot-detection-like message, propagate or log
            if _is_bot_detection_error(error_msg):
                if PROPAGATE_BOT_DETECTION:
                    raise BotDetectionError(error_msg)
                if not bot_cooldown_triggered:
                    cooldown = random.randint(_BOT_COOLDOWN_MIN, _BOT_COOLDOWN_MAX)
                    _wait_with_progress(cooldown, "Bot detection")
                    bot_cooldown_triggered = True
            else:
                print(f"WARNING: yt-dlp fallback failed for {video_id}: {e}")

    return None
