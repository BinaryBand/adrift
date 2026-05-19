# pyright: reportPrivateUsage=false
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import TypedDict, TypeVar, Unpack

from adrift.adapters import get_scored_alignment_adapter
from adrift.models import (
    EpisodeData,
    MergeResult,
    PodcastConfig,
    ReferenceMatchTrace,
    RssEpisode,
    SourceTrace,
)
from adrift.models.ports import ScoredAlignmentPort
from adrift.utils.profiler import profile
from adrift.utils.progress import Callback

from .alignment import align_episodes_with_scores, merge_episode
from .collection import EpisodeFetchContext, _collect_episodes_with_traces
from .merge_trace import _build_match_traces


@dataclass(frozen=True)
class MergeConfigOptions:
    callback: Callback | None = None
    refresh_sources: bool = False
    timings: dict[str, float] | None = None
    on_stage: Callable[[str], None] | None = None
    scored_alignment_port: ScoredAlignmentPort | None = None


class MergeConfigOptionOverrides(TypedDict, total=False):
    callback: Callback | None
    refresh_sources: bool
    timings: dict[str, float] | None
    on_stage: Callable[[str], None] | None
    scored_alignment_port: ScoredAlignmentPort | None


_T = TypeVar("_T")


def _maybe_record_timing(
    timings: dict[str, float] | None,
    key: str,
    started_at: float,
) -> None:
    if timings is not None:
        timings[key] = perf_counter() - started_at


def _timed_stage(key: str, fn: Callable[[], _T], options: MergeConfigOptions) -> _T:
    if options.on_stage:
        options.on_stage(key)
    started_at = perf_counter()
    value = fn()
    _maybe_record_timing(options.timings, key, started_at)
    return value


def _merge_episode_list(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    pairs: list[tuple[int, int]],
) -> list[EpisodeData]:
    return [merge_episode(references[r_idx], downloads[d_idx]) for r_idx, d_idx in pairs]


def _collect_episodes_for_role_with_traces(
    config: PodcastConfig,
    is_reference: bool,
    callback: Callback | None,
    refresh_sources: bool,
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
    )


def _collect_feed_sets(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> tuple[list[RssEpisode], list[RssEpisode], list[SourceTrace]]:
    references, reference_traces = _timed_stage(
        "process_feeds",
        lambda: _collect_episodes_for_role_with_traces(
            config,
            True,
            options.callback,
            options.refresh_sources,
        ),
        options,
    )
    downloads, download_traces = _timed_stage(
        "process_sources",
        lambda: _collect_episodes_for_role_with_traces(
            config,
            False,
            options.callback,
            options.refresh_sources,
        ),
        options,
    )
    return references, downloads, [*reference_traces, *download_traces]


def _align_with_selected_port(
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
    port = _resolved_scored_alignment_port(options)
    if port is not None:
        return port.align_with_scores(
            references,
            downloads,
            show=config.name,
            alignment=config.alignment,
        )
    return align_episodes_with_scores(
        references,
        downloads,
        show=config.name,
        alignment=config.alignment,
    )


def _resolved_scored_alignment_port(options: MergeConfigOptions) -> ScoredAlignmentPort | None:
    if options.scored_alignment_port is not None:
        return options.scored_alignment_port
    return get_scored_alignment_adapter()


def _merge_config_artifacts(
    config: PodcastConfig,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    options: MergeConfigOptions,
) -> tuple[list[tuple[int, int]], list[ReferenceMatchTrace], list[EpisodeData]]:
    pairs, scores = _timed_stage(
        "align_episodes",
        lambda: _align_with_selected_port(options, references, downloads, config),
        options,
    )
    match_traces = _build_match_traces(references, downloads, pairs, config.name, scores=scores)
    episodes = _timed_stage(
        "merge_episodes",
        lambda: _merge_episode_list(references, downloads, pairs),
        options,
    )
    return pairs, match_traces, episodes


@profile
def merge_config(
    config: PodcastConfig,
    options: MergeConfigOptions | None = None,
    **option_overrides: Unpack[MergeConfigOptionOverrides],
) -> MergeResult:
    """Fetch, align, and merge episodes for a single podcast config."""
    if options is None:
        options = MergeConfigOptions(**option_overrides)
    total_start = perf_counter()

    references, downloads, source_traces = _collect_feed_sets(config, options)
    pairs, match_traces, episodes = _merge_config_artifacts(
        config,
        references,
        downloads,
        options,
    )
    _maybe_record_timing(options.timings, "merge_config_total", total_start)
    return MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        source_traces=source_traces,
        match_traces=match_traces,
        pairs=pairs,
        episodes=episodes,
    )


__all__ = ["MergeConfigOptions", "MergeConfigOptionOverrides", "merge_config"]
