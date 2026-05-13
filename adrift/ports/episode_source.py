from dataclasses import dataclass
from typing import Protocol

from src.models import FeedSource, RssChannel, RssEpisode
from src.utils.progress import Callback


@dataclass(frozen=True)
class EpisodeSourceFetchContext:
    title: str = ""
    detailed: bool = True
    callback: Callback | None = None
    refresh: bool = False


class EpisodeSourcePort(Protocol):
    """Port for fetching episodes from various sources (RSS, YouTube, etc.)."""

    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]:
        """Fetch episodes from a given source.

        Args:
            source: FeedSource configuration with URL and optional filters
            context: Typed fetch context for title, callback, detail level, and refresh mode

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
