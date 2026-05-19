from __future__ import annotations

from typing import cast

from adrift.models import EpisodeData, PodcastConfig, ReferenceMatchTrace, RssEpisode, SourceTrace
from adrift.models.ports import ScoredAlignmentBatchPort

from .alignment import merge_episode
from .collection import EpisodeFetchContext, _collect_episodes_with_traces
from .merge_trace import _build_match_traces


class LegacyEpisodeCollectorAdapter:
    def __init__(self, dedup_port: ScoredAlignmentBatchPort | None = None) -> None:
        self._dedup_port = dedup_port

    def collect(
        self,
        config: PodcastConfig,
        *,
        is_reference: bool,
        callback=None,
        refresh_sources: bool = False,
    ) -> tuple[list[RssEpisode], list[SourceTrace]]:
        sources = config.references if is_reference else config.downloads
        return _collect_episodes_with_traces(
            sources,
            EpisodeFetchContext(
                title=config.name,
                is_reference=is_reference,
                callback=callback,
                refresh_sources=refresh_sources,
            ),
            dedup_port=self._dedup_port,
        )


class LegacyTraceBuilderAdapter:
    def build(
        self,
        *args: object,
        **kwargs: object,
    ) -> list[ReferenceMatchTrace]:
        references, downloads, pairs, show, scores = _coerce_trace_build_args(args, kwargs)
        return _build_match_traces(references, downloads, pairs, show, scores=scores)


class LegacyEpisodeMergerAdapter:
    def merge(
        self,
        *args: object,
        **kwargs: object,
    ) -> list[EpisodeData]:
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
    if len(args) == 5:
        references, downloads, pairs, show, scores = args
    else:
        references = kwargs["references"]
        downloads = kwargs["downloads"]
        pairs = kwargs["pairs"]
        show = kwargs["show"]
        scores = kwargs["scores"]
    refs, dls, resolved_pairs = _coerce_episode_lists(references, downloads, pairs)
    return refs, dls, resolved_pairs, cast(str, show), cast(dict[tuple[int, int], float], scores)


def _coerce_episode_merge_args(
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> tuple[list[RssEpisode], list[RssEpisode], list[tuple[int, int]]]:
    if len(args) == 3:
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
        cast(list[RssEpisode], references),
        cast(list[RssEpisode], downloads),
        cast(list[tuple[int, int]], pairs),
    )


__all__ = [
    "LegacyEpisodeCollectorAdapter",
    "LegacyEpisodeMergerAdapter",
    "LegacyTraceBuilderAdapter",
]
