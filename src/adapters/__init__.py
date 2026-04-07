"""Adapter implementations for various ports."""

from src.app_common import FeedSource
from src.ports.episode_source import EpisodeSourcePort
from src.utils.text import is_youtube_channel


def get_episode_source_adapter(source: FeedSource) -> EpisodeSourcePort:
    """Get the appropriate episode source adapter for a FeedSource.

    Routes to YouTube adapter if URL is a YouTube channel, otherwise RSS adapter.

    Args:
        source: FeedSource with URL to analyze

    Returns:
        EpisodeSourcePort adapter instance
    """
    url = source.url
    if not url:
        raise ValueError("FeedSource URL is required to determine adapter")

    if is_youtube_channel(url):
        from src.adapters.episode_source_youtube import YouTubeEpisodeSourceAdapter

        return YouTubeEpisodeSourceAdapter()
    else:
        from src.adapters.episode_source_rss import RssEpisodeSourceAdapter

        return RssEpisodeSourceAdapter()
