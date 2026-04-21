# pyright: reportPrivateUsage=false
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import TypedDict, TypeVar, Unpack, cast

from src.models import (
    EpisodeData,
    MergeResult,
    PodcastConfig,
    RssEpisode,
    SourceTrace,
)
from src.utils.progress import Callback

from .alignment import align_episodes, merge_episode
from .collection import EpisodeFetchContext, _collect_episodes_with_traces
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


def _merge_config_artifacts(
    config: PodcastConfig,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    options: MergeConfigOptions,
) -> tuple[list[tuple[int, int]], list[SourceTrace], list[EpisodeData]]:
    pairs = _timed_stage(
        "align_episodes",
        lambda: align_episodes(references, downloads, config.name),
        options,
    )
    match_traces = cast(
        list[SourceTrace], _build_match_traces(references, downloads, pairs, config.name)
    )
    episodes = _timed_stage(
        "merge_episodes",
        lambda: _merge_episode_list(references, downloads, pairs),
        options,
    )
    return pairs, match_traces, episodes


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
