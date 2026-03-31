from urllib.parse import urljoin
from pathlib import Path
import sys
import os

sys.path.insert(0, Path(__file__).parent.parent.parent.as_posix())
from src.models import RssChannel, RssEpisode
from src.utils.progress import Callback
from src.utils.regex import YT_CHANNEL, YT_CHANNEL_SHORTHAND, re_compile
from src.web.rss import upload_thumbnail
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
    normalized_url = _normalize_youtube_link(url)

    rss_channel = _get_youtube_channel(normalized_url)
    if rss_channel.image:
        img = rss_channel.image
        rss_channel.image = upload_thumbnail(img, author, "channel") or img

    return rss_channel


def _add_episode_metadata(episode: RssEpisode, author: str) -> RssEpisode:
    """Add pub_date and thumbnail to episode if detailed=True."""

    # Allow tests/offline runs to skip network/video-info fetches
    if os.getenv("PODSMITH_SKIP_VIDEO_INFO"):
        return episode

    info = ytdlp.get_video_info(episode.id)
    if info is None:
        print(f"WARNING: Failed to fetch video info for {episode.id}")
        return episode

    episode.pub_date = info.upload_date or episode.pub_date  # Update pub_date

    if thumbnail := info.thumbnail:  # Update thumbnail
        if image := upload_thumbnail(thumbnail, author, episode.id) or thumbnail:
            episode.image = image

    return episode


def get_youtube_episodes(
    url: str,
    author: str,
    filter: str | None = "",
    detailed=True,
    callback: Callback | None = None,
) -> list[RssEpisode]:
    """Fetch RSS episodes from a given URL."""
    normalized_url = _normalize_youtube_link(url)

    episodes = ytdlp.get_youtube_videos(normalized_url, author, callback)
    print(f"Fetched {len(episodes)} episodes from {url}")

    # Apply filter if provided
    if filter is not None and filter != "":
        pattern = re_compile(filter)
        episodes = [ep for ep in episodes if pattern.search(ep.title)]
        print(f"Filtered {len(episodes)} episodes using pattern: {filter}")

    # Add detailed metadata (pub_date, thumbnails) if requested
    if detailed:
        print("Adding detailed metadata to episodes...")
        _episodes = []
        for i, ep in enumerate(episodes):
            _episodes.append(_add_episode_metadata(ep, author))
            if callback:
                callback(i + 1, len(episodes))
        episodes = _episodes

    # Final callback to indicate completion
    if callback:
        callback(len(episodes), len(episodes))

    return episodes


def get_video_info(id: str) -> ytdlp.VideoInfo | None:
    """Fetch video info (backward compatibility wrapper)."""
    return ytdlp.get_video_info(id)
