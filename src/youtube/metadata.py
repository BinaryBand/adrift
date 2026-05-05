from dataclasses import dataclass, field
from urllib.parse import urljoin

from src.models import RssChannel, RssEpisode
from src.utils.progress import Callback
from src.utils.regex import (
    YOUTUBE_PLAYLIST_SHORTHAND_REGEX,
    YOUTUBE_PLAYLIST_URL,
    YT_CHANNEL,
    YT_CHANNEL_SHORTHAND,
    re_compile,
)
from src.utils.terminal import emit_info, emit_warning
from src.youtube import ytdlp


def _normalize_youtube_link(url: str) -> str:
    """Normalize various YouTube link formats into a URL yt-dlp can consume.

    Supported inputs:
    - Full channel URLs (https://www.youtube.com/@handle or .../videos)
    - Channel shorthand: yt://@handle
    - Playlist shorthand: yt://#PLAYLIST_ID
    - Full playlist URLs: https://www.youtube.com/playlist?list=ID
    """
    playlist = "videos"

    if (href_match := YT_CHANNEL.match(url)) is not None:
        # Channel URLs without an explicit path should default to the videos tab.
        return urljoin(url, playlist) if href_match.group(3) is None else url

    if (yt_match := YT_CHANNEL_SHORTHAND.match(url)) is not None:
        channel_handle = yt_match.group(1)
        return f"https://www.youtube.com/@{channel_handle}/{playlist}"

    if (playlist_shorthand_match := YOUTUBE_PLAYLIST_SHORTHAND_REGEX.match(url)) is not None:
        playlist_id = playlist_shorthand_match.group(1)
        return f"https://www.youtube.com/playlist?list={playlist_id}"

    if YOUTUBE_PLAYLIST_URL.match(url) is not None:
        return url

    raise ValueError("Invalid YouTube channel or playlist URL")


def _channel_to_rss(channel_info: ytdlp.ChannelInfo, url: str) -> RssChannel:
    """Convert ChannelInfo to RssChannel."""
    channel = RssChannel.from_ytdlp(channel_info.model_dump(), url)
    return channel


def _get_youtube_channel(url: str) -> RssChannel:
    """Fetch YouTube channel and return as RssChannel."""
    if (channel_info := ytdlp.get_channel_info(url)) is not None:
        channel = _channel_to_rss(channel_info, url)
        return channel

    raise ValueError(f"Failed to fetch YouTube channel info from {url}")


def get_youtube_channel(url: str, author: str) -> RssChannel:
    """Fetch RSS channel from a given URL."""
    del author
    normalized_url = _normalize_youtube_link(url)
    return _get_youtube_channel(normalized_url)


def _add_episode_metadata(episode: RssEpisode, author: str) -> RssEpisode:
    """Add pub_date and thumbnail to episode if detailed=True."""
    if episode.pub_date is not None and episode.image is not None:
        return episode

    # Allow tests/offline runs to skip network/video-info fetches
    info = _fetch_video_info(episode.id)
    if info is None:
        return episode

    _maybe_update_pub_date(episode, info)
    _maybe_update_thumbnail(episode, info, author)
    _maybe_update_description(episode, info)

    return episode


def _maybe_update_description(episode: RssEpisode, info: ytdlp.VideoInfo) -> None:
    """Update ``episode.description`` from video info when available."""
    try:
        if desc := getattr(info, "description", None):
            # Preserve existing description if present
            if not episode.description:
                episode.description = desc
    except Exception:
        # Non-fatal: do not break the enrichment pipeline for description errors.
        pass


def _fetch_video_info(video_id: str) -> ytdlp.VideoInfo | None:
    """Wrapper around ytdlp.get_video_info with centralized error handling."""

    try:
        return ytdlp.get_video_info(video_id)
    except Exception as e:
        emit_warning(f"Failed to fetch video info for {video_id}: {e}")
        return None


def _maybe_update_pub_date(episode: RssEpisode, info: ytdlp.VideoInfo) -> None:
    """Update `episode.pub_date` from video info if available."""
    try:
        episode.pub_date = info.upload_date or episode.pub_date
    except Exception:
        # Be tolerant of missing fields on the returned info object
        pass


def _maybe_update_thumbnail(episode: RssEpisode, info: ytdlp.VideoInfo, author: str) -> None:
    """Update ``episode.image`` from video info when available."""
    del author
    try:
        if thumbnail := getattr(info, "thumbnail", None):
            episode.image = thumbnail
    except Exception:
        # Non-fatal: do not break the enrichment pipeline for thumbnail errors.
        pass


def _filter_episodes(episodes: list[RssEpisode], pattern_str: str) -> list[RssEpisode]:
    pattern = re_compile(pattern_str)
    filtered = [ep for ep in episodes if pattern.search(ep.title)]
    emit_info(f"Filtered {len(filtered)} episodes using pattern: {pattern_str}")
    return filtered


def _enrich_episodes(
    episodes: list[RssEpisode], author: str, callback: Callback | None
) -> list[RssEpisode]:
    emit_info("Adding detailed metadata to episodes...")
    result: list[RssEpisode] = []
    for i, ep in enumerate(episodes):
        result.append(_add_episode_metadata(ep, author))
        if callback:
            callback(i + 1, len(episodes))
    return result


@dataclass
class YtFetchOptions:
    filter: str | None = ""
    detailed: bool = True
    callback: Callback | None = field(default=None)
    refresh: bool = False


def _coerce_fetch_options(opts: YtFetchOptions | None) -> YtFetchOptions:
    return opts if opts is not None else YtFetchOptions()


def _post_process_episodes(
    episodes: list[RssEpisode],
    url: str,
    author: str,
    opts: YtFetchOptions,
) -> list[RssEpisode]:
    emit_info(f"Fetched {len(episodes)} episodes from {url}")

    if opts.filter:
        episodes = _filter_episodes(episodes, opts.filter)
    if opts.detailed:
        episodes = _enrich_episodes(episodes, author, opts.callback)
    if opts.callback:
        opts.callback(len(episodes), len(episodes))

    return episodes


def get_youtube_episodes(
    url: str, author: str, opts: YtFetchOptions | None = None
) -> list[RssEpisode]:
    """Fetch RSS episodes from a given URL."""
    fetch_opts = _coerce_fetch_options(opts)
    normalized_url = _normalize_youtube_link(url)
    episodes = ytdlp.get_youtube_videos(
        normalized_url,
        author,
        fetch_opts.callback,
        refresh=fetch_opts.refresh,
    )
    return _post_process_episodes(episodes, url, author, fetch_opts)
