from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from typing import Any, Literal

from adrift.models import FeedSource, PodcastConfig, RssEpisode, SourceTrace, ensure_feed_source
from adrift.models.ports import ScoredAlignmentBatchPort
from adrift.utils.profiler import profile, profile_block
from adrift.utils.progress import Callback
from adrift.utils.text import is_youtube_channel

from .alignment import align_episodes, prepare_alignment_batch


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


def _source_type(source: FeedSource) -> Literal["rss", "youtube"]:
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
    dedup_port: ScoredAlignmentBatchPort | None = None,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    """Fetch, trace, and deduplicate episodes from a list of FeedSource objects."""
    with profile_block(f"collection.fetch_sources_{len(sources)}"):
        if len(sources) <= 1:
            albums = [_fetch_source_album(source, context) for source in sources]
        else:
            max_workers = min(8, len(sources))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                albums = list(executor.map(_fetch_source_album, sources, repeat(context)))
    traces = [
        _build_source_trace(source, context, len(album)) for source, album in zip(sources, albums)
    ]

    if not albums:
        return [], traces

    merged: list[RssEpisode] = albums[0]
    for album in albums[1:]:
        _merge_episode_album(merged, album, context.title, dedup_port)

    return merged, traces


def _fetch_source_episodes(
    source: FeedSource | dict[str, Any],
    context: EpisodeFetchContext,
) -> list[RssEpisode]:
    from adrift.adapters import get_episode_source_adapter
    from adrift.models.ports import EpisodeSourceFetchContext

    resolved = ensure_feed_source(source)
    return get_episode_source_adapter(resolved).fetch_episodes(
        resolved,
        EpisodeSourceFetchContext(
            title=context.title,
            detailed=context.is_reference,
            callback=context.callback,
            refresh=context.refresh_sources,
        ),
    )


def _fetch_source_album(source: FeedSource, context: EpisodeFetchContext) -> list[RssEpisode]:
    role = "reference" if context.is_reference else "download"
    source_kind = _source_type(source)
    block_name = f"source_fetch.{role}.{source_kind}"
    with profile_block(block_name):
        return _fetch_source_episodes(source, context)


def _dedup_via_batch_port(
    merged: list[RssEpisode],
    album: list[RssEpisode],
    show: str,
    port: ScoredAlignmentBatchPort,
) -> set[int]:
    with profile_block(f"collection.dedup_batch_port_{len(merged)}vs{len(album)}"):
        batch = prepare_alignment_batch(merged, album, request_or_show=show)
        pairs, _scores = port.align_batch(batch)
        return {d_idx for _, d_idx in pairs}


def _merge_episode_album(
    merged: list[RssEpisode],
    album: list[RssEpisode],
    show: str = "",
    dedup_port: ScoredAlignmentBatchPort | None = None,
) -> None:
    with profile_block(f"collection.merge_album_{len(merged)}base_{len(album)}new"):
        if dedup_port is not None:
            duplicate_indices = _dedup_via_batch_port(merged, album, show, dedup_port)
        else:
            with profile_block(f"collection.align_episodes_{len(merged)}vs{len(album)}"):
                duplicate_indices = {d_idx for _, d_idx in align_episodes(merged, album, show)}
        for index, episode in enumerate(album):
            if index not in duplicate_indices:
                merged.append(episode)


@profile
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


@profile
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
