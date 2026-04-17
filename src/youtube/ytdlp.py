"""
cspell: words playliststart playlistend playlistreverse
YouTube Data Layer (yt-dlp) integration with typed interfaces.

This module provides a clean, typed interface for fetching YouTube data via yt-dlp.
Similar to the SponsorBlock module, it uses Pydantic models for type safety.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

from dateutil import parser
from pydantic import BaseModel, ValidationError, field_validator
from yt_dlp import YoutubeDL

from src.models import RssEpisode, YtDlpParams
from src.models.ytdlp import YtDlpImage
from src.utils.cache import S3Cache
from src.utils.progress import Callback
from src.youtube.auth import get_auth_ydl_opts, get_ydl_opts

# Constants
_CACHE = S3Cache(".cache/yt-dlp", "yt-dlp")

_CHANNEL_CACHE_FIELDS = {
    "title",
    "uploader",
    "uploader_id",
    "description",
    "avatar",
    "thumbnails",
}

_VIDEO_CACHE_FIELDS = {
    "id",
    "title",
    "description",
    "duration",
    "upload_date",
    "thumbnail",
    "availability",
    "url",
    "timestamp",
    "release_timestamp",
    "view_count",
    "like_count",
    "comment_count",
}


class ChannelInfo(BaseModel):
    """Typed channel information from yt-dlp."""

    title: str
    uploader: str | None = None
    uploader_id: str | None = None
    description: str | None = None
    avatar: list[YtDlpImage] | str | None = None
    thumbnails: list[YtDlpImage] | None = None


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


def _trim_channel_cache_payload(raw_info: dict[str, Any]) -> dict[str, Any]:
    return {key: raw_info[key] for key in _CHANNEL_CACHE_FIELDS if key in raw_info}


def _trim_video_cache_payload(raw_info: dict[str, Any]) -> dict[str, Any]:
    return {key: raw_info[key] for key in _VIDEO_CACHE_FIELDS if key in raw_info}


def _ydl_opts_dict(opts: YtDlpParams | dict[str, Any]) -> dict[str, Any]:
    """Convert typed yt-dlp params into a plain dict for yt-dlp internals."""
    if isinstance(opts, dict):
        return {k: v for k, v in opts.items() if v is not None}
    return opts.model_dump(exclude_none=True)


def _fetch_channel_info_raw(url: str, fetch_videos: bool = False) -> dict[str, Any] | None:
    """Fetch raw channel information from yt-dlp."""
    opts: YtDlpParams = get_ydl_opts()
    opts["extract_flat"] = True

    if not fetch_videos:
        opts["playlistend"] = 0  # Don't fetch any video entries

    try:
        with YoutubeDL(cast(Any, _ydl_opts_dict(opts))) as ydl:
            info = ydl.extract_info(url, download=False)
            return cast(dict[str, Any], info) if info else None
    except Exception as e:
        print(f"ERROR: Failed to fetch channel info from {url}: {e}")
        return None


def _video_info_url(video_id: str) -> str:
    return f"https://youtube.com/watch?v={video_id}"


def _extract_info(url: str, opts: YtDlpParams | dict[str, Any]) -> dict[str, Any] | None:
    with YoutubeDL(cast(Any, _ydl_opts_dict(opts))) as ydl:
        info = ydl.extract_info(url, download=False)
        return cast(dict[str, Any], info) if info else None


def _fetch_video_info_attempt(
    video_id: str,
    label: str,
    build_opts: Callable[[], YtDlpParams],
) -> dict[str, Any] | None:
    print(f"Fetching video info for {video_id} using {label} yt-dlp")
    try:
        return _extract_info(_video_info_url(video_id), build_opts())
    except Exception as e:
        print(f"WARNING: {label} attempt failed for {video_id}: {e}")
        return None


def _video_info_attempts() -> list[tuple[str, Callable[[], YtDlpParams]]]:
    return [
        ("unauthenticated", get_ydl_opts),
        (
            "authenticated",
            lambda: get_auth_ydl_opts(use_browser_fallback=True),
        ),
    ]


def get_channel_info(url: str) -> ChannelInfo | None:
    """Get cached channel info or fetch and cache if not present."""
    cache_key = f"get_youtube_channel:{url}"

    # Try cache first
    cached = _load_cached_channel_info(cache_key)
    if cached is not None:
        return cached

    raw_info = _fetch_channel_info_raw(url, fetch_videos=False)
    if raw_info is None:
        print(f"WARNING: Failed to fetch channel info for {url}")
        return None

    return _parse_and_cache_channel(raw_info, cache_key, url)


def _load_cached_channel_info(cache_key: str) -> ChannelInfo | None:
    cached = _CACHE.get(cache_key)
    if cached is None:
        return None
    try:
        return ChannelInfo.model_validate(cached)
    except ValidationError as e:
        print(f"WARNING: Invalid cached channel info for {cache_key}: {e}")
        _CACHE.delete(cache_key)
        return None


def _parse_and_cache_channel(
    raw_info: dict[str, Any], cache_key: str, url: str
) -> ChannelInfo | None:
    try:
        model = ChannelInfo.model_validate(raw_info)
    except ValidationError as e:
        print(f"WARNING: Failed to parse channel info for {url}: {e}")
        return None

    # Cache for 25-35 days
    expire_days = random.randint(25, 35)
    # raw_info should be a dict here; assert to help type-checkers
    assert isinstance(raw_info, dict)
    _CACHE.set(cache_key, _trim_channel_cache_payload(raw_info), expire=expire_days * 24 * 3600)
    return model


def _fetch_video_info_raw(video_id: str) -> dict[str, Any] | None:
    """Fetch raw video info using yt-dlp with fallback to authenticated."""
    for label, build_opts in _video_info_attempts():
        if info := _fetch_video_info_attempt(video_id, label, build_opts):
            return info
    return None


def get_video_info(video_id: str) -> VideoInfo | None:
    """Fetch video info with caching."""
    cache_key = f"get_video_info:{video_id}"

    # Try cache first
    cached = _load_cached_video_info(cache_key)
    if cached is not None:
        return cached

    raw_info = _fetch_video_info_raw(video_id)
    if raw_info is None:
        print(f"WARNING: Failed to fetch video info for {video_id}")
        return None

    return _parse_and_cache_video(raw_info, cache_key, video_id)


def _load_cached_video_info(cache_key: str) -> VideoInfo | None:
    cached = _CACHE.get(cache_key)
    if cached is None:
        return None
    try:
        return VideoInfo.model_validate(cached)
    except ValidationError as e:
        print(f"WARNING: Invalid cached video info for {cache_key}: {e}")
        _CACHE.delete(cache_key)
        return None


def _parse_and_cache_video(
    raw_info: dict[str, Any], cache_key: str, video_id: str
) -> VideoInfo | None:
    try:
        model = VideoInfo.model_validate(raw_info)
    except ValidationError as e:
        print(f"WARNING: Failed to parse video info for {video_id}: {e}")
        return None
    # raw_info should be a dict here; assert to help type-checkers
    assert isinstance(raw_info, dict)
    _CACHE.set(cache_key, _trim_video_cache_payload(raw_info))
    return model


def _fetch_channel_videos_raw(
    url: str,
    start: int = 1,
    end: int | None = None,
    reverse: bool = False,
) -> list[dict[str, Any]]:
    """Fetch video entries from a channel/playlist."""
    opts: YtDlpParams = get_ydl_opts()
    opts["extract_flat"] = True
    opts["playlistreverse"] = reverse
    opts["playliststart"] = start
    opts["playlistend"] = end

    try:
        with YoutubeDL(cast(Any, _ydl_opts_dict(opts))) as ydl:
            channel_info = ydl.extract_info(url, download=False)
            if not channel_info:
                return []

            return cast(list[dict[str, Any]], channel_info.get("entries", []))
    except Exception as e:
        print(f"ERROR: Failed to fetch videos from {url}: {e}")
        return []


BATCHES = [10, 100, None]
YOUTUBE_EPISODE_CACHE_FRESHNESS = timedelta(hours=12)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_cached_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _load_cached_episode_bundle(cache_key: str) -> tuple[dict[str, RssEpisode], datetime | None]:
    cached = _CACHE.get(cache_key)
    if not isinstance(cached, dict):
        return {}, None

    cached_payload = cast(dict[str, object], cached)
    raw_episodes = cached_payload.get("episodes")
    if isinstance(raw_episodes, dict):
        return cast(dict[str, RssEpisode], raw_episodes), _parse_cached_timestamp(
            cached_payload.get("fetched_at")
        )

    return cast(dict[str, RssEpisode], cached_payload), None


def _episode_cache_is_fresh(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return False
    return _utcnow() - fetched_at <= YOUTUBE_EPISODE_CACHE_FRESHNESS


def _fetch_video_batch(
    url: str,
    author: str,
    batch_index: int,
    batch_size: int | None,
) -> list[dict[str, Any]]:
    print(f"Fetching {author} videos {batch_index} (size={str(batch_size)})...")
    return _fetch_channel_videos_raw(url, 1, end=batch_size, reverse=False)


def _add_new_public_episodes(
    video_entries: list[dict[str, Any]],
    author: str,
    episodes: dict[str, RssEpisode],
) -> bool:
    has_new = False
    for entry in video_entries:
        episode = RssEpisode.from_ytdlp(entry, author)
        if not episode.is_public or episode.id in episodes:
            continue
        print(f"Found new video: {episode.id}")
        episodes[episode.id] = episode
        has_new = True
    return has_new


def _report_video_fetch_progress(
    callback: Callback | None,
    batch_size: int | None,
    episode_count: int,
) -> None:
    if callback is None:
        return
    callback(0, max(batch_size or 1000, episode_count))


def _report_cached_video_progress(
    callback: Callback | None,
    episode_count: int,
) -> None:
    if callback is None:
        return
    callback(episode_count, episode_count)


def _cache_youtube_videos(cache_key: str, episodes: dict[str, RssEpisode]) -> None:
    expire = random.randint(25, 35) * 24 * 3600
    _CACHE.set(
        cache_key,
        {
            "fetched_at": _utcnow().isoformat(),
            "episodes": episodes,
        },
        expire=expire,
    )


def _use_cached_youtube_videos(
    episodes: dict[str, RssEpisode],
    author: str,
    callback: Callback | None,
) -> list[RssEpisode]:
    print(f"Using fresh cached YouTube episodes for {author}")
    _report_cached_video_progress(callback, len(episodes))
    return list(episodes.values())


def _should_use_cached_youtube_videos(
    episodes: dict[str, RssEpisode],
    fetched_at: datetime | None,
    refresh: bool,
) -> bool:
    return bool(episodes) and not refresh and _episode_cache_is_fresh(fetched_at)


def _refresh_youtube_videos(
    url: str,
    author: str,
    callback: Callback | None,
    episodes: dict[str, RssEpisode],
) -> list[RssEpisode]:
    for batch_index, batch_size in enumerate(BATCHES, start=1):
        video_entries = _fetch_video_batch(url, author, batch_index, batch_size)
        has_new = _add_new_public_episodes(video_entries, author, episodes)
        _report_video_fetch_progress(callback, batch_size, len(episodes))
        if not has_new:
            break

    return list(episodes.values())


def get_youtube_videos(
    url: str,
    author: str,
    callback: Callback | None = None,
    refresh: bool = False,
) -> list[RssEpisode]:
    cache_key = f"get_youtube_videos:{url}:{author}"
    stale_episodes, fetched_at = _load_cached_episode_bundle(cache_key)

    if _should_use_cached_youtube_videos(stale_episodes, fetched_at, refresh):
        return _use_cached_youtube_videos(stale_episodes, author, callback)

    episodes = _refresh_youtube_videos(url, author, callback, stale_episodes)
    _cache_youtube_videos(cache_key, stale_episodes)
    return episodes


if __name__ == "__main__":
    print("yt_dlp module is intended to be imported, not executed directly")
