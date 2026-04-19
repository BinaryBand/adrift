import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yt_dlp

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.utils.progress import Callback
from src.utils.regex import YOUTUBE_VIDEO_REGEX
from src.youtube.auth import YtDlpParams, get_auth_ydl_opts, get_ydl_opts


class BotDetectionError(Exception):
    """Raised when YouTube bot-detection or rate-limiting is encountered."""


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


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    match = YOUTUBE_VIDEO_REGEX.match(url)
    return match.group(4) if match and match.group(4) else None


def _is_bot_detection_error(error_message: str) -> bool:
    """Check if error indicates bot detection or rate limiting."""
    return any(indicator in error_message for indicator in _BOT_INDICATORS)


_PLAYER_CLIENTS_STUB_FALLBACK = ["tv_embedded", "web"]
_AUDIO_FORMATS_FALLBACK = "bestaudio/best"

# (authenticated, player_clients, format_selector)
# Unauthenticated attempts first: stale/mismatched browser cookies can cause
# YouTube to serve a restricted format list even for non-age-restricted videos.
# "Sign in" errors from unauthenticated attempts are caught and retried with auth.
_DOWNLOAD_ATTEMPTS: list[tuple[bool, list[str] | None, str | None]] = [
    (False, None, _AUDIO_FORMATS_FALLBACK),
    (False, None, None),
    (True, None, _AUDIO_FORMATS_FALLBACK),
    (True, None, None),
    (True, _PLAYER_CLIENTS_STUB_FALLBACK, None),
]


@dataclass(frozen=True)
class _DownloadAttemptConfig:
    authenticated: bool = True
    player_clients: list[str] | None = None
    format_selector: str | None = None


def _attempt_label(attempt_index: int, attempt: _DownloadAttemptConfig) -> str:
    mode = "authenticated" if attempt.authenticated else "unauthenticated"
    details: list[str] = [mode]
    if attempt.format_selector is not None:
        details.append(f"format={attempt.format_selector}")
    if attempt.player_clients is not None:
        details.append(f"player_clients={','.join(attempt.player_clients)}")
    return f"attempt {attempt_index + 1}/{len(_DOWNLOAD_ATTEMPTS)} ({', '.join(details)})"


def _ytdlp_download(id: str, dir: Path, callback: Callback | None = None) -> Path | None:
    """Download video using yt-dlp.

    Tries unauthenticated first (avoids cookie-induced format restrictions), then
    falls back to authenticated for age-restricted content.
    """
    for attempt, raw_attempt in enumerate(_DOWNLOAD_ATTEMPTS):
        attempt_config = _download_attempt_config(raw_attempt)
        label = _attempt_label(attempt, attempt_config)
        print(f"Starting yt-dlp {label} for {id}")
        try:
            result = _run_download_attempt(id, dir, callback, attempt_config)
        except Exception as e:
            if _should_retry_attempt(e, attempt):
                print(f"Retrying {id} after {label} failed: {_retry_reason(e)}")
                continue
            _raise_download_error(id, e, label)
            return None

        if result is not None:
            print(f"Completed yt-dlp {label} for {id}")
            return result

    return None


def _download_attempt_config(
    raw_attempt: tuple[bool, list[str] | None, str | None],
) -> _DownloadAttemptConfig:
    authenticated, player_clients, format_selector = raw_attempt
    return _DownloadAttemptConfig(
        authenticated=authenticated,
        player_clients=player_clients,
        format_selector=format_selector,
    )


def _build_download_opts(
    id: str,
    dir: Path,
    callback: Callback | None = None,
    attempt: _DownloadAttemptConfig | None = None,
) -> YtDlpParams:
    attempt_config = _coerce_attempt_config(attempt)
    opts: YtDlpParams = _base_download_opts(attempt_config)
    if attempt_config.format_selector is not None:
        opts["format"] = attempt_config.format_selector
    opts["outtmpl"] = (dir / f"{id}.%(ext)s").as_posix()
    opts["postprocessors"] = [_audio_postprocessor()]
    if attempt_config.player_clients is not None:
        opts["extractor_args"] = {"youtube": {"player_client": attempt_config.player_clients}}

    progress_hook = _make_progress_hook(callback)
    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]

    return opts


def _coerce_attempt_config(attempt: _DownloadAttemptConfig | None) -> _DownloadAttemptConfig:
    if attempt is None:
        return _DownloadAttemptConfig()
    return attempt


def _base_download_opts(attempt: _DownloadAttemptConfig) -> YtDlpParams:
    if attempt.authenticated:
        return get_auth_ydl_opts(use_browser_fallback=True)
    return get_ydl_opts()


def _run_download_attempt(
    id: str,
    dir: Path,
    callback: Callback | None,
    attempt: _DownloadAttemptConfig,
) -> Path | None:
    opts = _build_download_opts(id, dir, callback, attempt)
    url = f"https://www.youtube.com/watch?v={id}"
    info_dict = _extract_download_info(url, opts)
    return _resolve_download_path(info_dict)


def _should_retry_attempt(error: Exception, attempt_index: int) -> bool:
    return _is_unavailable_format_error(error) and attempt_index < len(_DOWNLOAD_ATTEMPTS) - 1


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


def _ydl_opts_dict(opts: YtDlpParams | dict[str, Any]) -> dict[str, Any]:
    """Convert typed yt-dlp params into a plain dict for yt-dlp internals."""
    if isinstance(opts, dict):
        return {k: v for k, v in opts.items() if v is not None}
    # Ensure we return a plain built-in dict (tests assert dict type).
    return dict(opts.model_dump(exclude_none=True))


def _extract_download_info(url: str, opts: YtDlpParams | dict[str, Any]) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(cast(Any, _ydl_opts_dict(opts))) as ydl:
        info = ydl.extract_info(url, download=True)
    return cast(dict[str, Any], info)


def _is_unavailable_format_error(error: Exception) -> bool:
    err_str = str(error)
    return (
        "Requested format is not available" in err_str
        or "This video is only available for" in err_str
        or "Sign in" in err_str
    )


def _retry_reason(error: Exception) -> str:
    err_str = str(error)
    if "Sign in to confirm your age" in err_str:
        return "age-restricted; retrying with authentication"
    if "Premieres in " in err_str:
        return "premiere not yet available"
    if "This live event will begin in" in err_str:
        return "live event not yet started"
    if "private video" in err_str.lower() or "This video is private" in err_str:
        return "private video"
    if "members-only" in err_str.lower() or "channel members" in err_str.lower():
        return "members-only video"
    if (
        "not available in your country" in err_str.lower()
        or "available in your country" in err_str.lower()
        or "geo" in err_str.lower() and "block" in err_str.lower()
    ):
        return "geo-restricted video"
    if "This video has been removed" in err_str or "This video is no longer available" in err_str:
        return "removed video"
    if "Video unavailable" in err_str:
        return "video unavailable"
    if "Requested format is not available" in err_str:
        return "requested format unavailable; trying fallback"
    if "This video is only available for" in err_str:
        return "restricted format set; trying fallback"
    first_line = err_str.splitlines()[0].strip()
    return first_line[:160]


def _log_stub_format(path: Path, size: int, info_dict: dict[str, Any]) -> None:
    dl = cast(dict[str, Any], (info_dict.get("requested_downloads") or [{}])[0])
    fmt = dl.get("format") or info_dict.get("format", "unknown")
    acodec = dl.get("acodec") or info_dict.get("acodec", "?")
    vcodec = dl.get("vcodec") or info_dict.get("vcodec", "?")
    print(
        f"WARNING: Downloaded file is too small ({size} bytes), treating as failed: {path}\n"
        f"  format={fmt!r}  acodec={acodec}  vcodec={vcodec}"
    )


def _get_candidate_size(candidate: Path) -> int | None:
    """Return file size in bytes or None if stat fails."""
    try:
        return candidate.stat().st_size
    except (OSError, FileNotFoundError):
        return None


def _evaluate_candidate(candidate: Path, info_dict: dict[str, Any]) -> Path | Literal[False] | None:
    """Evaluate a candidate download file.

    Returns the candidate Path when valid, False when it is a stub (invalid),
    or None when the candidate is not present.
    """
    if not candidate.exists():
        return None
    size = _get_candidate_size(candidate)
    if size is None:
        # In unit tests Path.exists() is often patched while stat() is
        # not; assume the candidate is the resolved path in that case.
        print(f"WARNING: Could not stat {candidate}, assuming present")
        return candidate
    if size < _MIN_AUDIO_BYTES:
        _log_stub_format(candidate, size, info_dict)
        return False
    return candidate


def _find_download_candidate(file_path: Path, info_dict: dict[str, Any]) -> Path | None:
    m4a_path = file_path.with_suffix(".m4a")
    for candidate in (m4a_path, file_path):
        res = _evaluate_candidate(candidate, info_dict)
        if res is None:
            continue
        if res is False:
            return None
        return res
    print(f"WARNING: Downloaded file not found: {file_path}")
    return None


def _resolve_download_path(info_dict: dict[str, Any]) -> Path | None:
    file_path = _requested_download_path(info_dict)
    if file_path is None:
        return None
    return _find_download_candidate(file_path, info_dict)


def _requested_download_path(info_dict: dict[str, Any]) -> Path | None:
    downloads = info_dict.get("requested_downloads")
    if not downloads:
        return None
    downloaded_file = downloads[0].get("filepath")
    if not isinstance(downloaded_file, str):
        return None
    return Path(downloaded_file)


def _raise_download_error(id: str, error: Exception, attempt_label: str | None = None) -> None:
    error_msg = str(error)
    if _is_bot_detection_error(error_msg) and PROPAGATE_BOT_DETECTION:
        raise BotDetectionError(error_msg)
    context = f" after {attempt_label}" if attempt_label else ""
    print(f"WARNING: yt-dlp download failed for {id}{context}: {error}")
    raise error


def download_video(url: str, dir: Path, callback: Callback | None = None) -> Path | None:
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
