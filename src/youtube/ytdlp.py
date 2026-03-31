"""
YouTube Data Layer (yt-dlp) integration with typed interfaces.

This module provides a clean, typed interface for fetching YouTube data via yt-dlp.
Similar to the sponsorblock module, it uses Pydantic models for type safety.
"""

from pydantic import BaseModel, ValidationError, field_validator
from typing import Any, cast
from yt_dlp import YoutubeDL
from datetime import datetime
from dateutil import parser
from pathlib import Path
import random
import sys

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.models import RssEpisode, YtDlpParams
from src.utils.cache import S3Cache
from src.utils.progress import Callback
from src.youtube.auth import get_ydl_opts, get_auth_ydl_opts


# Constants
_CACHE = S3Cache(".cache/yt-dlp", "yt-dlp")


class ChannelInfo(BaseModel):
    """Typed channel information from yt-dlp."""

    title: str
    uploader: str | None = None
    uploader_id: str | None = None
    description: str | None = None
    avatar: Any = None  # Can be list[dict] or str
    thumbnails: list[dict] | None = None


class VideoInfo(BaseModel):
    """Typed video information from yt-dlp."""

    id: str
    title: str
    description: str | None = None
    duration: float | None = None
    upload_date: datetime | None = None
    thumbnail: str | None = None
    availability: str | None = None
    url: str | None = None

    @field_validator("upload_date", mode="before")
    @classmethod
    def _normalize_upload_date(cls, value: Any) -> datetime | None:
        try:
            return parser.parse(value)
        except Exception:
            return None


def _fetch_channel_info_raw(url: str, fetch_videos: bool = False) -> dict | None:
    """Fetch raw channel information from yt-dlp."""
    opts: YtDlpParams = get_ydl_opts()
    opts["extract_flat"] = True

    if not fetch_videos:
        opts["playlistend"] = 0  # Don't fetch any video entries

    try:
        with YoutubeDL(cast(Any, opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            return cast(dict, info) if info else None
    except Exception as e:
        print(f"ERROR: Failed to fetch channel info from {url}: {e}")
        return None


def get_channel_info(url: str) -> ChannelInfo | None:
    """Get cached channel info or fetch and cache if not present."""
    cache_key = f"get_youtube_channel:{url}"
    cached = _CACHE.get(cache_key)
    if cached is not None:
        try:
            return ChannelInfo.model_validate(cached)
        except ValidationError as e:
            print(f"WARNING: Invalid cached channel info for {url}: {e}")
            _CACHE.delete(cache_key)

    raw_info = _fetch_channel_info_raw(url, fetch_videos=False)
    if raw_info is None:
        print(f"WARNING: Failed to fetch channel info for {url}")
        return None
    try:
        model = ChannelInfo.model_validate(raw_info)
    except ValidationError as e:
        print(f"WARNING: Failed to parse channel info for {url}: {e}")
        return None

    # Cache for 25-35 days
    expire_days = random.randint(25, 35)
    _CACHE.set(cache_key, raw_info, expire=expire_days * 24 * 3600)
    return model


def _fetch_video_info_raw(video_id: str) -> dict | None:
    """Fetch raw video info using yt-dlp with fallback to authenticated."""
    # Use lazy evaluation to avoid calling get_auth_ydl_opts unless needed
    url = f"https://youtube.com/watch?v={video_id}"

    # First try unauthenticated
    print(f"Fetching video info for {video_id} using unauthenticated yt-dlp")
    try:
        opts = get_ydl_opts()
        with YoutubeDL(cast(Any, opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            return cast(dict, info)
    except Exception as e:
        print(f"WARNING: unauthenticated attempt failed for {video_id}: {e}")

    # Then try authenticated. Request auth options once (allowing a browser
    # fallback) and attempt to fetch using those options.
    print(f"Fetching video info for {video_id} using authenticated yt-dlp")
    try:
        opts = get_auth_ydl_opts(use_browser_fallback=True)
        with YoutubeDL(cast(Any, opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            return cast(dict, info)
    except Exception as e:
        print(f"WARNING: authenticated attempt failed for {video_id}: {e}")

    return None


def get_video_info(video_id: str) -> VideoInfo | None:
    """Fetch video info with caching."""

    cache_key = f"get_video_info:{video_id}"
    cached = _CACHE.get(cache_key)
    if cached is not None:
        try:
            return VideoInfo.model_validate(cached)
        except ValidationError as e:
            print(f"WARNING: Invalid cached video info for {video_id}: {e}")
            _CACHE.delete(cache_key)

    raw_info = _fetch_video_info_raw(video_id)
    try:
        model = VideoInfo.model_validate(raw_info)
    except ValidationError as e:
        print(f"WARNING: Failed to parse video info for {video_id}: {e}")
        return None

    _CACHE.set(cache_key, raw_info)
    return model


def _fetch_channel_videos_raw(
    url: str,
    start: int = 1,
    end: int | None = None,
    reverse: bool = False,
) -> list[dict]:
    """Fetch video entries from a channel/playlist."""
    opts: YtDlpParams = get_ydl_opts()
    opts["extract_flat"] = True
    opts["playlistreverse"] = reverse
    opts["playliststart"] = start
    opts["playlistend"] = end

    try:
        with YoutubeDL(cast(Any, opts)) as ydl:
            channel_info = ydl.extract_info(url, download=False)
            if channel_info is None:
                return []

            return cast(list[dict], channel_info.get("entries", []))
    except Exception as e:
        print(f"ERROR: Failed to fetch videos from {url}: {e}")
        return []


BATCHES = [10, 100, None]


def get_youtube_videos(
    url: str,
    author: str,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    cache_key = f"get_youtube_videos:{url}:{author}"
    stale_episodes: dict[str, RssEpisode] = _CACHE.get(cache_key) or {}

    for i, batch in enumerate(BATCHES):
        has_new = False
        print(f"Fetching {author} videos {i + 1} (size={str(batch)})...")

        # Use ytdlp module to fetch videos
        video_entries = _fetch_channel_videos_raw(url, 1, end=batch, reverse=False)
        for entry in video_entries:
            if (ep := RssEpisode.from_ytdlp(entry, author)).is_public:
                if ep.id not in stale_episodes:
                    print(f"Found new video: {ep.id}")
                    stale_episodes[ep.id] = ep
                    has_new = True

        if callback:
            total = max(batch or 1000, len(stale_episodes))
            callback(0, total)

        if not has_new:
            break

    expire = random.randint(25, 35) * 24 * 3600
    _CACHE.set(cache_key, stale_episodes, expire=expire)

    return list(stale_episodes.values())


if __name__ == "__main__":
    print("yt_dlp module is intended to be imported, not executed directly")
