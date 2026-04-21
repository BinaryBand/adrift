# pyright: reportPrivateUsage=false
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypedDict, Unpack

from src.models.metadata import RssEpisode
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult, ReferenceMatchTrace, SourceTrace
from src.models.podcast_config import PodcastConfig
from src.utils.progress import Callback

from .alignment import (
    _best_thumbnail,
    _normalized_alignment_title,
    align_episodes,
    align_episodes_impl,
    match,
    merge_episode,
    merge_episode_pairs,
    sim_date,
)
from .collection import (
    EpisodeFetchContext,
    _collect_episodes,
    _collect_episodes_with_traces,
    process_feeds,
    process_sources,
)
from .merge_trace import _build_match_traces


@dataclass(frozen=True)
class MergeConfigOptions:
    callback: Callback | None = None
    refresh_sources: bool = False
    timings: dict[str, float] | None = None
    on_stage: Callable[[str], None] | None = None


class MergeConfigOptionOverrides(TypedDict, total=False):
    callback: Callback | None
    refresh_sources: bool
    timings: dict[str, float] | None
    on_stage: Callable[[str], None] | None


def _maybe_record_timing(
    timings: dict[str, float] | None,
    key: str,
    started_at: float,
) -> None:
    if timings is not None:
        timings[key] = perf_counter() - started_at


def _timed_stage(key: str, fn: Any, options: MergeConfigOptions) -> Any:
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


def _collect_reference_episodes_with_traces(
    config: PodcastConfig,
    callback: Callback | None,
    refresh_sources: bool,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    return _collect_episodes_with_traces(
        config.references,
        EpisodeFetchContext(
            title=config.name,
            is_reference=True,
            callback=callback,
            refresh_sources=refresh_sources,
        ),
    )


def _collect_download_episodes_with_traces(
    config: PodcastConfig,
    callback: Callback | None,
    refresh_sources: bool,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    return _collect_episodes_with_traces(
        config.downloads,
        EpisodeFetchContext(
            title=config.name,
            is_reference=False,
            callback=callback,
            refresh_sources=refresh_sources,
        ),
    )


def _align_config_episodes(
    config_name: str,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
) -> list[tuple[int, int]]:
    return align_episodes(references, downloads, config_name)


def _collect_feed_sets(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> tuple[list[RssEpisode], list[RssEpisode], list[SourceTrace]]:
    references, reference_traces = _timed_stage(
        "process_feeds",
        lambda: _collect_reference_episodes_with_traces(
            config,
            options.callback,
            options.refresh_sources,
        ),
        options,
    )
    downloads, download_traces = _timed_stage(
        "process_sources",
        lambda: _collect_download_episodes_with_traces(
            config,
            options.callback,
            options.refresh_sources,
        ),
        options,
    )
    return references, downloads, [*reference_traces, *download_traces]


def _collect_merge_parts(
    config_name: str,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    options: MergeConfigOptions,
) -> tuple[list[tuple[int, int]], list[ReferenceMatchTrace], list[EpisodeData]]:
    pairs = _timed_stage(
        "align_episodes",
        lambda: _align_config_episodes(config_name, references, downloads),
        options,
    )
    match_traces = _build_match_traces(references, downloads, pairs, config_name)
    episodes = _timed_stage(
        "merge_episodes",
        lambda: _merge_episode_list(references, downloads, pairs),
        options,
    )
    return pairs, match_traces, episodes


def _collect_merge_result_parts(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> tuple[
    list[RssEpisode],
    list[RssEpisode],
    list[SourceTrace],
    list[tuple[int, int]],
    list[ReferenceMatchTrace],
    list[EpisodeData],
]:
    references, downloads, source_traces = _collect_feed_sets(config, options)
    pairs, match_traces, episodes = _collect_merge_parts(
        config.name,
        references,
        downloads,
        options,
    )
    return references, downloads, source_traces, pairs, match_traces, episodes


def _build_merge_result(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> MergeResult:
    references, downloads, source_traces, pairs, match_traces, episodes = (
        _collect_merge_result_parts(config, options)
    )

    return MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        source_traces=source_traces,
        match_traces=match_traces,
        pairs=pairs,
        episodes=episodes,
    )


def merge_config(
    config: PodcastConfig,
    options: MergeConfigOptions | None = None,
    **option_overrides: Unpack[MergeConfigOptionOverrides],
) -> MergeResult:
    """Fetch, align, and merge episodes for a single podcast config."""
    if options is None:
        options = MergeConfigOptions(**option_overrides)
    total_start = perf_counter()
    merge_result = _build_merge_result(config, options)
    _maybe_record_timing(options.timings, "merge_config_total", total_start)
    return merge_result


__all__ = [
    "EpisodeFetchContext",
    "MergeConfigOptions",
    "MergeConfigOptionOverrides",
    "_best_thumbnail",
    "_build_match_traces",
    "_collect_episodes",
    "_normalized_alignment_title",
    "align_episodes",
    "align_episodes_impl",
    "match",
    "merge_config",
    "merge_episode",
    "merge_episode_pairs",
    "process_feeds",
    "process_sources",
    "sim_date",
]