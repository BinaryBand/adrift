# pyright: reportPrivateUsage=false
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from adrift.models.ports import (
    EpisodeCollectorPort,
    EpisodeMergerPort,
    MatchTraceBuilderPort,
    ScoredAlignmentBatchPort,
    ScoredAlignmentPort,
)
from adrift.utils.alignment_pairs import AlignmentResult
from adrift.utils.profiler import profile
from adrift.utils.progress import Callback

from .alignment import align_episodes_with_scores, prepare_alignment_batch
from .merge_adapters import (
    LegacyEpisodeCollectorAdapter,
    LegacyEpisodeMergerAdapter,
    LegacyTraceBuilderAdapter,
)


@dataclass(frozen=True)
class MergeConfigOptions:
    callback: Callback | None = None
    refresh_sources: bool = False
    timings: dict[str, float] | None = None
    on_stage: Callable[[str], None] | None = None
    scored_alignment_port: ScoredAlignmentPort | ScoredAlignmentBatchPort | None = None
    collector_port: EpisodeCollectorPort | None = None
    trace_builder_port: MatchTraceBuilderPort | None = None
    episode_merger_port: EpisodeMergerPort | None = None
    scored_alignment_candidate_port: ScoredAlignmentPort | ScoredAlignmentBatchPort | None = None
    collector_candidate_port: EpisodeCollectorPort | None = None
    trace_builder_candidate_port: MatchTraceBuilderPort | None = None
    episode_merger_candidate_port: EpisodeMergerPort | None = None
    ab_warnings: list[str] | None = None


class MergeConfigOptionOverrides(TypedDict, total=False):
    callback: Callback | None
    refresh_sources: bool
    timings: dict[str, float] | None
    on_stage: Callable[[str], None] | None
    scored_alignment_port: ScoredAlignmentPort | ScoredAlignmentBatchPort | None
    collector_port: EpisodeCollectorPort | None
    trace_builder_port: MatchTraceBuilderPort | None
    episode_merger_port: EpisodeMergerPort | None
    scored_alignment_candidate_port: ScoredAlignmentPort | ScoredAlignmentBatchPort | None
    collector_candidate_port: EpisodeCollectorPort | None
    trace_builder_candidate_port: MatchTraceBuilderPort | None
    episode_merger_candidate_port: EpisodeMergerPort | None
    ab_warnings: list[str] | None


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


def _collect_with_port(
    collector: EpisodeCollectorPort,
    config: PodcastConfig,
    is_reference: bool,
    options: MergeConfigOptions,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    episodes, traces = collector.collect(
        config,
        is_reference=is_reference,
        callback=options.callback,
        refresh_sources=options.refresh_sources,
    )
    return episodes, traces


def _record_ab_warning(options: MergeConfigOptions, message: str) -> None:
    if options.ab_warnings is not None:
        options.ab_warnings.append(message)


def _compare_ab_result(
    stage: str,
    options: MergeConfigOptions,
    primary: object,
    candidate: object,
) -> None:
    if primary != candidate:
        _record_ab_warning(options, f"{stage} A/B mismatch: candidate output differed from primary")


def _resolved_collector_port(options: MergeConfigOptions) -> EpisodeCollectorPort:
    if options.collector_port is not None:
        return options.collector_port
    port = _resolved_scored_alignment_port(options)
    dedup_port = port if isinstance(port, ScoredAlignmentBatchPort) else None
    return LegacyEpisodeCollectorAdapter(dedup_port=dedup_port)


def _resolved_trace_builder_port(options: MergeConfigOptions) -> MatchTraceBuilderPort:
    if options.trace_builder_port is not None:
        return options.trace_builder_port
    return LegacyTraceBuilderAdapter()


def _resolved_episode_merger_port(options: MergeConfigOptions) -> EpisodeMergerPort:
    if options.episode_merger_port is not None:
        return options.episode_merger_port
    return LegacyEpisodeMergerAdapter()


def _collect_feed_sets(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> tuple[list[RssEpisode], list[RssEpisode], list[SourceTrace]]:
    collector = _resolved_collector_port(options)
    candidate_collector = _resolved_collector_candidate_port(options)
    references, reference_traces = _collect_role_with_optional_candidate(
        collector,
        candidate_collector,
        config,
        is_reference=True,
        primary_stage="process_feeds",
        candidate_stage="process_feeds_ab_candidate",
        compare_stage="process_feeds",
        options=options,
    )
    downloads, download_traces = _collect_role_with_optional_candidate(
        collector,
        candidate_collector,
        config,
        is_reference=False,
        primary_stage="process_sources",
        candidate_stage="process_sources_ab_candidate",
        compare_stage="process_sources",
        options=options,
    )

    return references, downloads, [*reference_traces, *download_traces]


def _align_with_selected_port(
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
) -> AlignmentResult:
    port = _resolved_scored_alignment_port(options)
    if port is None:
        return align_episodes_with_scores(
            references,
            downloads,
            show=config.name,
            alignment=config.alignment,
        )
    return _align_with_port(port, references, downloads, config)


def _align_with_port(
    port: ScoredAlignmentPort | ScoredAlignmentBatchPort,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
) -> AlignmentResult:
    if isinstance(port, ScoredAlignmentBatchPort):
        batch = prepare_alignment_batch(
            references,
            downloads,
            request_or_show=config.name,
            alignment=config.alignment,
        )
        return port.align_batch(batch)
    return port.align_with_scores(
        references,
        downloads,
        show=config.name,
        alignment=config.alignment,
    )


def _resolved_scored_alignment_port(
    options: MergeConfigOptions,
) -> ScoredAlignmentPort | ScoredAlignmentBatchPort | None:
    if options.scored_alignment_port is not None:
        return options.scored_alignment_port
    return get_scored_alignment_adapter()


def _run_alignment_ab_candidate(
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
    primary_pairs: list[tuple[int, int]],
    primary_scores: dict[tuple[int, int], float],
) -> None:
    candidate_port = _resolved_alignment_candidate_port(options)
    if candidate_port is None:
        return
    candidate_pairs, candidate_scores = _timed_stage(
        "align_episodes_ab_candidate",
        lambda: _align_with_port(candidate_port, references, downloads, config),
        options,
    )
    _compare_ab_result("align_episodes.pairs", options, primary_pairs, candidate_pairs)
    _compare_ab_result("align_episodes.scores", options, primary_scores, candidate_scores)


def _collect_candidate_episodes(
    candidate_port: EpisodeCollectorPort,
    config: PodcastConfig,
    is_reference: bool,
    stage: str,
    options: MergeConfigOptions,
) -> list[RssEpisode]:
    episodes, _traces = _timed_stage(
        stage,
        lambda: _collect_with_port(candidate_port, config, is_reference, options),
        options,
    )
    return episodes


def _run_candidate_stage(
    candidate_port: _T | None,
    stage_key: str,
    compare_stage: str,
    options: MergeConfigOptions,
    primary_result: object,
    run: Callable[[_T], object],
) -> None:
    if candidate_port is None:
        return
    candidate_result = _timed_stage(stage_key, lambda: run(candidate_port), options)
    _compare_ab_result(compare_stage, options, primary_result, candidate_result)


def _collect_role_with_optional_candidate(
    collector: EpisodeCollectorPort,
    candidate_collector: EpisodeCollectorPort | None,
    config: PodcastConfig,
    *,
    is_reference: bool,
    primary_stage: str,
    candidate_stage: str,
    compare_stage: str,
    options: MergeConfigOptions,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    episodes, traces = _timed_stage(
        primary_stage,
        lambda: _collect_with_port(collector, config, is_reference, options),
        options,
    )
    if candidate_collector is not None:
        candidate_episodes = _collect_candidate_episodes(
            candidate_collector,
            config,
            is_reference,
            candidate_stage,
            options,
        )
        _compare_ab_result(compare_stage, options, episodes, candidate_episodes)
    return episodes, traces


def _merge_config_artifacts(
    config: PodcastConfig,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    options: MergeConfigOptions,
) -> tuple[list[tuple[int, int]], list[ReferenceMatchTrace], list[EpisodeData]]:
    trace_builder = _resolved_trace_builder_port(options)
    episode_merger = _resolved_episode_merger_port(options)
    options = _with_resolved_candidate_ports(options)
    primary_runner = _primary_alignment_runner(options, references, downloads, config)
    shadow_runner = _alignment_shadow_runner(options, references, downloads, config)
    pairs, scores = _align_with_ab_shadow(options, primary_runner, shadow_runner)
    match_traces = _build_match_traces_with_ab(
        trace_builder,
        options,
        references,
        downloads,
        pairs,
        config,
        scores,
    )
    episodes = _merge_episodes_with_ab(episode_merger, options, (references, downloads), pairs)
    return pairs, match_traces, episodes


def _alignment_shadow_runner(
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
) -> Callable[[list[tuple[int, int]], dict[tuple[int, int], float]], None]:
    return lambda pairs, scores: _run_alignment_ab_candidate(
        options,
        references,
        downloads,
        config,
        pairs,
        scores,
    )


def _primary_alignment_runner(
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    config: PodcastConfig,
) -> Callable[[], tuple[list[tuple[int, int]], dict[tuple[int, int], float]]]:
    return lambda: _align_with_selected_port(options, references, downloads, config)


def _build_match_traces_with_ab(
    trace_builder: MatchTraceBuilderPort,
    options: MergeConfigOptions,
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    pairs: list[tuple[int, int]],
    config: PodcastConfig,
    scores: dict[tuple[int, int], float],
) -> list[ReferenceMatchTrace]:
    match_traces = trace_builder.build(references, downloads, pairs, config.name, scores)
    _run_candidate_stage(
        _resolved_trace_builder_candidate_port(options),
        "build_match_traces_ab_candidate",
        "build_match_traces",
        options,
        match_traces,
        lambda port: port.build(references, downloads, pairs, config.name, scores),
    )
    return match_traces


def _merge_episodes_with_ab(
    episode_merger: EpisodeMergerPort,
    options: MergeConfigOptions,
    episode_sets: tuple[list[RssEpisode], list[RssEpisode]],
    pairs: list[tuple[int, int]],
) -> list[EpisodeData]:
    references, downloads = episode_sets
    episodes = _timed_stage(
        "merge_episodes",
        lambda: episode_merger.merge(references, downloads, pairs),
        options,
    )
    candidate_port = _resolved_episode_merger_candidate_port(options)
    if candidate_port is not None:
        candidate_episodes = _timed_stage(
            "merge_episodes_ab_candidate",
            lambda: candidate_port.merge(references, downloads, pairs),
            options,
        )
        _compare_ab_result("merge_episodes", options, episodes, candidate_episodes)
    return episodes


def _align_with_ab_shadow(
    options: MergeConfigOptions,
    align_primary: Callable[[], tuple[list[tuple[int, int]], dict[tuple[int, int], float]]],
    run_shadow: Callable[[list[tuple[int, int]], dict[tuple[int, int], float]], None],
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
    pairs, scores = _timed_stage("align_episodes", align_primary, options)
    run_shadow(pairs, scores)
    return pairs, scores


def _with_resolved_candidate_ports(options: MergeConfigOptions) -> MergeConfigOptions:
    return replace(
        options,
        scored_alignment_candidate_port=_resolved_alignment_candidate_port(options),
        collector_candidate_port=_resolved_collector_candidate_port(options),
        trace_builder_candidate_port=_resolved_trace_builder_candidate_port(options),
        episode_merger_candidate_port=_resolved_episode_merger_candidate_port(options),
    )


def _resolved_alignment_candidate_port(
    options: MergeConfigOptions,
) -> ScoredAlignmentPort | ScoredAlignmentBatchPort | None:
    if options.scored_alignment_candidate_port is not None:
        return options.scored_alignment_candidate_port
    backend = _candidate_backend_name("ADRIFT_AB_ALIGN_CANDIDATE")
    if backend is None:
        return None
    return get_scored_alignment_adapter(backend)


def _resolved_collector_candidate_port(options: MergeConfigOptions) -> EpisodeCollectorPort | None:
    if options.collector_candidate_port is not None:
        return options.collector_candidate_port
    backend = _candidate_backend_name("ADRIFT_AB_COLLECTOR_CANDIDATE")
    if backend is None:
        return None
    if backend == "legacy":
        return LegacyEpisodeCollectorAdapter()
    raise ValueError(f"Unsupported collector candidate backend: {backend}")


def _resolved_trace_builder_candidate_port(
    options: MergeConfigOptions,
) -> MatchTraceBuilderPort | None:
    if options.trace_builder_candidate_port is not None:
        return options.trace_builder_candidate_port
    backend = _candidate_backend_name("ADRIFT_AB_TRACE_CANDIDATE")
    if backend is None:
        return None
    if backend == "legacy":
        return LegacyTraceBuilderAdapter()
    raise ValueError(f"Unsupported trace candidate backend: {backend}")


def _resolved_episode_merger_candidate_port(
    options: MergeConfigOptions,
) -> EpisodeMergerPort | None:
    if options.episode_merger_candidate_port is not None:
        return options.episode_merger_candidate_port
    backend = _candidate_backend_name("ADRIFT_AB_MERGER_CANDIDATE")
    if backend is None:
        return None
    if backend == "legacy":
        return LegacyEpisodeMergerAdapter()
    raise ValueError(f"Unsupported merger candidate backend: {backend}")


def _candidate_backend_name(env_name: str) -> str | None:
    value = os.getenv(env_name, "").strip().lower()
    if not value or value == "none":
        return None
    return value


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
