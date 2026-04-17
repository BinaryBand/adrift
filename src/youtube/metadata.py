from dataclasses import dataclass, field
from urllib.parse import urljoin

from src.models import RssChannel, RssEpisode
from src.utils.progress import Callback
from src.utils.regex import YT_CHANNEL, YT_CHANNEL_SHORTHAND, re_compile
from src.youtube import ytdlp


def _normalize_youtube_link(url: str) -> str:
    playlist: str = "videos"

    href_match = YT_CHANNEL.match(url)
    yt_match = YT_CHANNEL_SHORTHAND.match(url)
    assert href_match or yt_match, "Invalid YouTube channel URL"

    if href_match:
        if href_match.group(3) is None:
            url = urljoin(url, playlist)
    elif yt_match:
        channel_handle = yt_match.group(1)
        url = f"https://www.youtube.com/@{channel_handle}/{playlist}"

    return url


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

    return episode


def _fetch_video_info(video_id: str) -> ytdlp.VideoInfo | None:
    """Wrapper around ytdlp.get_video_info with centralized error handling."""

    try:
        return ytdlp.get_video_info(video_id)
    except Exception as e:
        print(f"WARNING: Failed to fetch video info for {video_id}: {e}")
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
    print(f"Filtered {len(filtered)} episodes using pattern: {pattern_str}")
    return filtered


def _enrich_episodes(
    episodes: list[RssEpisode], author: str, callback: Callback | None
) -> list[RssEpisode]:
    print("Adding detailed metadata to episodes...")
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
    print(f"Fetched {len(episodes)} episodes from {url}")

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


def get_video_info(id: str) -> ytdlp.VideoInfo | None:
    """Fetch video info (backward compatibility wrapper)."""
    return ytdlp.get_video_info(id)
