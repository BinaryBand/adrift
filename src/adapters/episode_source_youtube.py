from typing import Any

from src.app_common import FeedSource
from src.models.metadata import RssChannel, RssEpisode
from src.ports.episode_source import EpisodeSourcePort


class YouTubeEpisodeSourceAdapter(EpisodeSourcePort):
    """Adapter for fetching episodes from YouTube channels."""

    def fetch_episodes(self, source: FeedSource, options: dict[str, Any]) -> list[RssEpisode]:
        """Fetch episodes from a YouTube channel."""
        from src.catalog import get_youtube_episodes
        from src.youtube.metadata import YtFetchOptions

        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for YouTube episode fetching")

        title = options.get("title", "")
        filter_regex = source.filters.to_regex() if source.filters else None
        callback = options.get("callback")
        detailed = options.get("detailed", True)
        refresh = options.get("refresh", False)
        fetch_opts = YtFetchOptions(
            filter=filter_regex,
            detailed=detailed,
            callback=callback,
            refresh=refresh,
        )

        return get_youtube_episodes(url, title, fetch_opts)

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from a YouTube channel."""
        from src.youtube.metadata import get_youtube_channel

        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for YouTube channel fetching")
        title = source.filters.to_regex() if source.filters else ""
        return get_youtube_channel(url, title or "")
