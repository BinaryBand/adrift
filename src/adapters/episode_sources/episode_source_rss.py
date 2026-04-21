from typing import Any

from src.models import FeedSource, RssChannel, RssEpisode
from src.ports import EpisodeSourcePort


class RssEpisodeSourceAdapter(EpisodeSourcePort):
    """Adapter for fetching episodes from RSS feeds."""

    def fetch_episodes(self, source: FeedSource, options: dict[str, Any]) -> list[RssEpisode]:
        """Fetch episodes from an RSS feed."""
        from src.web.rss import get_rss_episodes

        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for RSS episode fetching")

        filter_regex = source.filters.to_regex() if source.filters else None
        r_rules = source.filters.r_rules if source.filters else None
        callback = options.get("callback")

        return get_rss_episodes(url, filter_regex, r_rules, callback)

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from an RSS feed."""
        from src.web.rss import get_rss_channel

        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for RSS channel fetching")
        return get_rss_channel(url)
