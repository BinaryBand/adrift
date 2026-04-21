from dataclasses import dataclass
from typing import Any

from src.models.metadata import RssEpisode
from src.models.pipeline import SourceTrace
from src.models.podcast_config import FeedSource, PodcastConfig, ensure_feed_source
from src.utils.progress import Callback
from src.utils.text import is_youtube_channel

from .alignment import align_episodes


@dataclass(frozen=True)
class EpisodeFetchContext:
    title: str
    is_reference: bool
    callback: Callback | None = None
    refresh_sources: bool = False


def _collect_episodes(
    sources: list[FeedSource],
    context: EpisodeFetchContext,
) -> list[RssEpisode]:
    """Fetch and deduplicate episodes from a list of FeedSource objects."""
    merged, _traces = _collect_episodes_with_traces(sources, context)
    return merged


def _source_has_filters(source: FeedSource) -> bool:
    filters = source.filters
    return bool(filters.include or filters.exclude or filters.r_rules)


def _source_type(source: FeedSource) -> str:
    return "youtube" if is_youtube_channel(source.url) else "rss"


def _build_source_trace(
    source: FeedSource,
    context: EpisodeFetchContext,
    episode_count: int,
) -> SourceTrace:
    return SourceTrace(
        role="reference" if context.is_reference else "download",
        url=source.url,
        source_type=_source_type(source),
        episode_count=episode_count,
        filters=source.filters,
        has_filters=_source_has_filters(source),
    )


def _collect_episodes_with_traces(
    sources: list[FeedSource],
    context: EpisodeFetchContext,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    """Fetch, trace, and deduplicate episodes from a list of FeedSource objects."""
    albums: list[list[RssEpisode]] = []
    traces: list[SourceTrace] = []
    for source in sources:
        album = _fetch_source_episodes(source, context)
        albums.append(album)
        traces.append(_build_source_trace(source, context, len(album)))

    if not albums:
        return [], traces

    merged: list[RssEpisode] = albums[0]
    for album in albums[1:]:
        _merge_episode_album(merged, album)

    return merged, traces


def _fetch_source_episodes(
    source: FeedSource | dict[str, Any],
    context: EpisodeFetchContext,
) -> list[RssEpisode]:
    from src.adapters import get_episode_source_adapter

    resolved = ensure_feed_source(source)
    adapter = get_episode_source_adapter(resolved)
    options = {
        "title": context.title,
        "detailed": context.is_reference,
        "callback": context.callback,
        "refresh": context.refresh_sources,
    }
    return adapter.fetch_episodes(resolved, options)


def _merge_episode_album(
    merged: list[RssEpisode],
    album: list[RssEpisode],
) -> None:
    duplicate_indices = {download_index for _, download_index in align_episodes(merged, album)}
    for index, episode in enumerate(album):
        if index not in duplicate_indices:
            merged.append(episode)


def process_sources(
    config: PodcastConfig,
    callback: Callback | None = None,
    refresh_sources: bool = False,
) -> list[RssEpisode]:
    """Collect and deduplicate download-side episodes (thin wrapper)."""
    episodes = _collect_episodes(
        config.downloads,
        EpisodeFetchContext(
            title=config.name,
            is_reference=False,
            callback=callback,
            refresh_sources=refresh_sources,
        ),
    )
    if callback:
        callback(len(episodes), len(episodes))
    return episodes


def process_feeds(
    config: PodcastConfig,
    callback: Callback | None = None,
    refresh_sources: bool = False,
) -> list[RssEpisode]:
    """Collect and deduplicate reference-side episodes (thin wrapper)."""
    return _collect_episodes(
        config.references,
        EpisodeFetchContext(
            title=config.name,
            is_reference=True,
            callback=callback,
            refresh_sources=refresh_sources,
        ),
    )


__all__ = [
    "EpisodeFetchContext",
    "_collect_episodes",
    "_collect_episodes_with_traces",
    "process_feeds",
    "process_sources",
]