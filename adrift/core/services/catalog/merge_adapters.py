"""Legacy default adapters implementing the merge collaborator ports."""

from __future__ import annotations

from typing import cast

from adrift.core.models import (
    EpisodeData,
    PodcastConfig,
    ReferenceMatchTrace,
    RssEpisode,
    SourceTrace,
)
from adrift.core.ports import Callback, EpisodeSourceFactoryPort, ScoredAlignmentBatchPort

from .alignment import merge_episode
from .collection import EpisodeFetchContext, _collect_episodes_with_traces
from .merge_trace import _build_match_traces

_TRACE_BUILD_ARITY = 5
_EPISODE_MERGE_ARITY = 3

# Reference/download episode lists plus their aligned index pairs.
_EpisodeMergeArgs = tuple[list[RssEpisode], list[RssEpisode], list[tuple[int, int]]]


class LegacyEpisodeCollectorAdapter:
    """Default ``EpisodeCollectorPort`` wrapping the collection helpers."""

    def __init__(
        self,
        dedup_port: ScoredAlignmentBatchPort | None = None,
        source_factory: EpisodeSourceFactoryPort | None = None,
    ) -> None:
        """Store the optional dedup port and episode-source factory."""
        self._dedup_port = dedup_port
        self._source_factory = source_factory

    def collect(
        self,
        config: PodcastConfig,
        *,
        is_reference: bool,
        callback: Callback | None = None,
        refresh_sources: bool = False,
    ) -> tuple[list[RssEpisode], list[SourceTrace]]:
        """Collect episodes and traces for the reference or download role."""
        sources = config.references if is_reference else config.downloads
        return _collect_episodes_with_traces(
            sources,
            EpisodeFetchContext(
                title=config.name,
                is_reference=is_reference,
                callback=callback,
                refresh_sources=refresh_sources,
                source_factory=self._source_factory,
            ),
            dedup_port=self._dedup_port,
        )


class LegacyTraceBuilderAdapter:
    """Default ``MatchTraceBuilderPort`` delegating to ``_build_match_traces``."""

    def build(
        self,
        *args: object,
        **kwargs: object,
    ) -> list[ReferenceMatchTrace]:
        """Build reference match traces from positional or keyword arguments."""
        references, downloads, pairs, show, scores = _coerce_trace_build_args(args, kwargs)
        return _build_match_traces(references, downloads, pairs, show, scores=scores)


class LegacyEpisodeMergerAdapter:
    """Default ``EpisodeMergerPort`` delegating to ``merge_episode``."""

    def merge(
        self,
        *args: object,
        **kwargs: object,
    ) -> list[EpisodeData]:
        """Merge aligned reference/download episodes into output records."""
        references, downloads, pairs = _coerce_episode_merge_args(args, kwargs)
        return [merge_episode(references[r_idx], downloads[d_idx]) for r_idx, d_idx in pairs]


def _coerce_trace_build_args(
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> tuple[
    list[RssEpisode],
    list[RssEpisode],
    list[tuple[int, int]],
    str,
    dict[tuple[int, int], float],
]:
    if len(args) == _TRACE_BUILD_ARITY:
        references, downloads, pairs, show, scores = args
    else:
        references = kwargs["references"]
        downloads = kwargs["downloads"]
        pairs = kwargs["pairs"]
        show = kwargs["show"]
        scores = kwargs["scores"]
    refs, dls, resolved_pairs = _coerce_episode_lists(references, downloads, pairs)
    return (
        refs,
        dls,
        resolved_pairs,
        cast("str", show),
        cast("dict[tuple[int, int], float]", scores),
    )


def _coerce_episode_merge_args(
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> _EpisodeMergeArgs:
    if len(args) == _EPISODE_MERGE_ARITY:
        references, downloads, pairs = args
    else:
        references = kwargs["references"]
        downloads = kwargs["downloads"]
        pairs = kwargs["pairs"]
    return _coerce_episode_lists(references, downloads, pairs)


def _coerce_episode_lists(
    references: object,
    downloads: object,
    pairs: object,
) -> tuple[list[RssEpisode], list[RssEpisode], list[tuple[int, int]]]:
    return (
        cast("list[RssEpisode]", references),
        cast("list[RssEpisode]", downloads),
        cast("list[tuple[int, int]]", pairs),
    )


__all__ = [
    "LegacyEpisodeCollectorAdapter",
    "LegacyEpisodeMergerAdapter",
    "LegacyTraceBuilderAdapter",
]
