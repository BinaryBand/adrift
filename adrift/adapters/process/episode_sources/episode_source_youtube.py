from typing_extensions import override

from adrift.core.models import FeedSource, RssChannel, RssEpisode
from adrift.core.ports import EpisodeSourceFetchContext, EpisodeSourcePort


class YouTubeEpisodeSourceAdapter(EpisodeSourcePort):
    """Adapter for fetching episodes from YouTube channels."""

    @override
    def fetch_episodes(
        self,
        source: FeedSource,
        context: EpisodeSourceFetchContext | None = None,
    ) -> list[RssEpisode]:
        """Fetch episodes from a YouTube channel."""
        from adrift.adapters.process.youtube.metadata import YtFetchOptions, get_youtube_episodes

        resolved_context = context or EpisodeSourceFetchContext()
        url = source.url
        if not url:
            msg = "FeedSource URL is required for YouTube episode fetching"
            raise ValueError(msg)

        filter_regex = source.filters.to_regex() if source.filters else None
        fetch_opts = YtFetchOptions(
            filter=filter_regex,
            detailed=True,  # YouTube always needs detailed metadata for pub_date/thumbnail
            callback=resolved_context.callback,
            refresh=resolved_context.refresh,
        )

        return get_youtube_episodes(url, resolved_context.title, fetch_opts)

    @override
    def fetch_channel(self, source: FeedSource) -> RssChannel:
        """Fetch channel metadata from a YouTube channel."""
        from adrift.adapters.process.youtube.metadata import get_youtube_channel

        url = source.url
        if not url:
            msg = "FeedSource URL is required for YouTube channel fetching"
            raise ValueError(msg)
        title = source.filters.to_regex() if source.filters else ""
        return get_youtube_channel(url, title or "")
