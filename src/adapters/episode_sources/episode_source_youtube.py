from src.models import FeedSource, RssChannel, RssEpisode
from src.ports import EpisodeSourceFetchContext, EpisodeSourcePort


class YouTubeEpisodeSourceAdapter(EpisodeSourcePort):
    """Adapter for fetching episodes from YouTube channels."""

    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]:
        """Fetch episodes from a YouTube channel."""
        from src.youtube.metadata import YtFetchOptions, get_youtube_episodes

        resolved_context = context or EpisodeSourceFetchContext()
        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for YouTube episode fetching")

        filter_regex = source.filters.to_regex() if source.filters else None
        fetch_opts = YtFetchOptions(
            filter=filter_regex,
            detailed=resolved_context.detailed,
            callback=resolved_context.callback,
            refresh=resolved_context.refresh,
        )

        return get_youtube_episodes(url, resolved_context.title, fetch_opts)

    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from a YouTube channel."""
        from src.youtube.metadata import get_youtube_channel

        url = source.url
        if not url:
            raise ValueError("FeedSource URL is required for YouTube channel fetching")
        title = source.filters.to_regex() if source.filters else ""
        return get_youtube_channel(url, title or "")
