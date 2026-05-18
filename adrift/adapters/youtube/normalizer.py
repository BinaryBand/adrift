"""Normalize raw yt-dlp objects and dicts into typed domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from adrift.utils.image import extract_image_from_ytdlp, extract_image_from_ytdlp_list
from adrift.utils.progress import Callback

extract_image_url = extract_image_from_ytdlp
extract_image_from_list = extract_image_from_ytdlp_list

if TYPE_CHECKING:
    from adrift.models import RssChannel, RssEpisode, YtDlpVideo

_PROGRESS_HOOK_ERRORS = (OSError, RuntimeError, TypeError, ValueError)

# ============================================================================
# Timestamp Conversion (from metadata.py extraction)
# ============================================================================


def unix_timestamp_to_datetime(raw: Any) -> datetime | None:
    """Convert unix timestamp (int, float, or numeric string) to datetime."""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str) and raw.isdigit():
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    return None


def parse_upload_date_string(raw: Any) -> datetime | None:
    """Parse YYYYMMDD format string to datetime."""
    if not isinstance(raw, str) or len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def coerce_str(*values: Any) -> str:
    """Return the first truthy value as a string, or empty string.

    Used to implement fallback chains for string fields in normalized conversions.
    """
    for v in values:
        if v:
            return str(v)
    return ""


def ytdlp_pub_date(data: YtDlpVideo | dict[str, Any]) -> datetime | None:
    """Extract publication date from yt-dlp video data.

    Accepts either a validated YtDlpVideo model or a raw dict; attempts
    to parse timestamp, release_timestamp, or upload_date in that order.
    """
    from adrift.models import YtDlpVideo as YtDlpVideoModel

    mapping: dict[str, Any]
    if isinstance(data, YtDlpVideoModel):
        mapping = data.model_dump()
    else:
        mapping = data

    for key in ("timestamp", "release_timestamp"):
        if dt := unix_timestamp_to_datetime(mapping.get(key)):
            return dt
    return parse_upload_date_string(mapping.get("upload_date"))


def ensure_ytdlp_model(data: YtDlpVideo | dict[str, Any]) -> YtDlpVideo:
    """Ensure data is a YtDlpVideo model; convert dict if needed."""
    from adrift.models import YtDlpVideo as YtDlpVideoModel

    if isinstance(data, YtDlpVideoModel):
        return data
    return YtDlpVideoModel.model_validate(data)


# ============================================================================
# Progress Parsing (from youtube/downloader.py)
# ============================================================================


def make_progress_hook(callback: Callback | None = None):
    """Create a yt-dlp progress_hook callback that reports download progress.

    Returns a hook function that extracts progress tuples (current, total)
    from yt-dlp download dict payloads and invokes the provided callback.
    """
    if callback is None:
        return None

    def progress_hook(download: dict[str, Any]) -> None:
        try:
            progress = extract_progress_update(download)
            if progress is None:
                return
            callback(*progress)
        except _PROGRESS_HOOK_ERRORS:
            pass

    return progress_hook


def extract_progress_update(download: dict[str, Any]) -> tuple[int, int | None] | None:
    """Extract progress tuple from a yt-dlp download dict.

    Returns (current_bytes, total_bytes) or None if progress cannot be determined.
    Handles finished, downloading with byte progress, and fragment progress states.
    """
    status = download.get("status")
    if status == "finished":
        return _finished_progress_update(download)
    if status != "downloading":
        return None

    byte_progress = _byte_progress_update(download)
    if byte_progress is not None:
        return byte_progress
    return _fragment_progress_update(download)


def _coerce_int(value: Any) -> int | None:
    """Safely coerce a value to int, handling bool/float/int/None cases."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _byte_progress_update(download: dict[str, Any]) -> tuple[int, int | None] | None:
    """Extract byte-level progress from download dict."""
    current = _coerce_int(download.get("downloaded_bytes"))
    total = _coerce_int(download.get("total_bytes")) or _coerce_int(
        download.get("total_bytes_estimate")
    )
    if current is None:
        return None
    return current, total


def _fragment_progress_update(download: dict[str, Any]) -> tuple[int, int | None] | None:
    """Extract fragment-level progress from download dict."""
    fragment_index = _coerce_int(download.get("fragment_index"))
    fragment_count = _coerce_int(download.get("fragment_count"))
    if fragment_index is None:
        return None
    return fragment_index, fragment_count


def _finished_progress_update(download: dict[str, Any]) -> tuple[int, int] | None:
    """Extract final progress when download finishes."""
    total = _coerce_int(download.get("total_bytes"))
    if total is None:
        total = _coerce_int(download.get("downloaded_bytes"))
    if total is None:
        total = _coerce_int(download.get("total_bytes_estimate"))
    if total is None:
        return None
    return total, total


# ============================================================================
# Model factory functions (moved from models/metadata.py classmethods)
# ============================================================================


def _extract_channel_image(data: Any) -> str:
    """Extract image URL from avatar/thumbnail data (list or string)."""
    if not data:
        return ""
    if isinstance(data, list):
        return extract_image_from_list(data)
    return extract_image_url(data)


def rss_channel_from_ytdlp(data: "YtDlpVideo | dict[str, Any]", url: str) -> "RssChannel":
    """Create RssChannel from a yt-dlp extract_info response or raw dict."""
    from adrift.models import RssChannel

    model = ensure_ytdlp_model(data)
    return RssChannel(
        title=coerce_str(model.uploader, model.title),
        author=coerce_str(model.uploader_id, "YouTube"),
        subtitle="",
        url=url,
        description=coerce_str(model.description),
        image=coerce_str(
            _extract_channel_image(model.avatar),
            _extract_channel_image(model.thumbnails),
        ),
    )


def rss_episode_from_ytdlp(data: "YtDlpVideo | dict[str, Any]", author: str) -> "RssEpisode":
    """Create RssEpisode from a yt-dlp video entry dict or model."""
    from adrift.models import RssEpisode

    model = ensure_ytdlp_model(data)
    video_id = coerce_str(model.id)
    url = coerce_str(model.url, f"https://youtube.com/watch?v={video_id}")
    availability = coerce_str(model.availability, "public")
    episode = RssEpisode(
        id=video_id,
        title=coerce_str(model.title),
        author=author,
        description=model.description,
        content=url,
        duration=model.duration,
        pub_date=ytdlp_pub_date(model),
    )
    episode._availability = availability
    return episode
