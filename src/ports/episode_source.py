from typing import Any, Protocol

from src.models.metadata import RssChannel, RssEpisode
from src.models.podcast_config import FeedSource


class EpisodeSourcePort(Protocol):
    """Port for fetching episodes from various sources (RSS, YouTube, etc.)."""

    def fetch_episodes(self, source: FeedSource, options: dict[str, Any]) -> list[RssEpisode]:
        """Fetch episodes from a given source.

        Args:
            source: FeedSource configuration with URL and optional filters
            options: Dict with fetch options (e.g., callback, regex pattern, rrules)

        Returns:
            List of RssEpisode objects
        """
        ...

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from a given source.

        Args:
            source: FeedSource configuration with URL

        Returns:
            RssChannel with metadata
        """
        ...
