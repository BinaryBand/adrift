# cspell: ignore cdist
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, cast

from rapidfuzz import fuzz

from src.app_common import (
    MATCH_TOLERANCE,
    FeedSource,
    PodcastConfig,
    ensure_feed_source,
)
from src.app_runner import normalize_title
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult, SourceTrace
from src.utils.progress import Callback
from src.utils.text import is_youtube_channel, normalize_text
from src.web import rss as _rss
from src.web.rss import RssEpisode
from src.youtube import metadata as _yt_meta


def _similarity_clean(ac: str, bc: str) -> float:
    """Similarity when inputs are already cleaned (lowercased, slugged)."""
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    return r * 0.4 + ts * 0.3 + tset * 0.3


StringSimilarityFn = Callable[[list[str], list[str]], list[list[float]]]


def _cdist_similarity(a: list[str], b: list[str]) -> list[list[float]]:
    from rapidfuzz.process import cdist

    ratio_scores = cdist(a, b, scorer=fuzz.ratio, workers=-1) / 100.0
    token_sort_scores = cdist(a, b, scorer=fuzz.token_sort_ratio, workers=-1) / 100.0
    token_set_scores = cdist(a, b, scorer=fuzz.token_set_ratio, workers=-1) / 100.0
    return (ratio_scores * 0.4 + token_sort_scores * 0.3 + token_set_scores * 0.3).tolist()


def match(
    files: list[str],
    episodes: list[str],
    title: str,
    callback: Callback | None = None,
) -> list[tuple[int, int]]:
    files_clean, episodes_clean = _prepare_match_inputs(files, episodes, title)
    scores = _score_match_pairs(files_clean, episodes_clean, callback)
    matches = _select_unique_matches(scores)
    return _filter_tolerated_matches(matches, scores)


def _prepare_match_inputs(
    files: list[str], episodes: list[str], title: str
) -> tuple[list[str], list[str]]:
    files_clean = [normalize_text(f) for f in files]
    episodes_norm = [normalize_title(title, e) for e in episodes]
    episodes_clean = [normalize_text(e) for e in episodes_norm]
    return files_clean, episodes_clean


def _score_match_pairs(
    files_clean: list[str],
    episodes_clean: list[str],
    callback: Callback | None = None,
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for f_idx, file_name in enumerate(files_clean):
        for e_idx, episode_name in enumerate(episodes_clean):
            scores[(f_idx, e_idx)] = _similarity_clean(file_name, episode_name)

        if callback:
            callback(f_idx + 1, len(files_clean))

    return scores


def _select_unique_matches(
    scores: dict[tuple[int, int], float],
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_files: set[int] = set()
    used_episodes: set[int] = set()
    pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for (f_idx, e_idx), _score in pairs:
        if f_idx in used_files or e_idx in used_episodes:
            continue
        matches.append((f_idx, e_idx))
        used_files.add(f_idx)
        used_episodes.add(e_idx)
    return matches


def _filter_tolerated_matches(
    matches: list[tuple[int, int]], scores: dict[tuple[int, int], float]
) -> list[tuple[int, int]]:
    return [match for match in matches if scores[match] >= MATCH_TOLERANCE]


# ---------------------------------------------------------------------------
# Stage 1 — Similarity helpers (spec §"Stage 1 — Similarity Scoring")
# ---------------------------------------------------------------------------

_THUMBNAIL_RANK = {"maxres": 4, "hq": 3, "mq": 2, "sq": 1}

W_ID = 0.10
W_DATE = 0.30
W_TITLE = 0.50
W_DESC = 0.10
DATE_SCORE_TIERS: tuple[tuple[int, float], ...] = ((2, 1.00), (10, 0.70), (35, 0.15))
SPARSE_TITLE_MIN = 0.98


def _align_datetime_pair(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    if a.tzinfo is not None and b.tzinfo is None:
        return a, b.replace(tzinfo=a.tzinfo)
    if a.tzinfo is None and b.tzinfo is not None:
        return a.replace(tzinfo=b.tzinfo), b
    return a, b


def sim_date(a: datetime | None, b: datetime | None) -> float:
    """Tiered date similarity per the spec."""
    if a is None or b is None:
        return 0.0
    a, b = _align_datetime_pair(a, b)
    delta = abs((a - b).days)
    return next((score for max_days, score in DATE_SCORE_TIERS if delta <= max_days), 0.0)


def _id_similarity(ref: RssEpisode, dl: RssEpisode) -> float:
    return float(bool(ref.id and dl.id and ref.id == dl.id))


@dataclass(frozen=True)
class _AlignmentCandidate:
    episode: RssEpisode
    title: str
    description: str


@dataclass(frozen=True)
class MergeConfigOptions:
    callback: Callback | None = None
    refresh_sources: bool = False
    timings: dict[str, float] | None = None
    on_stage: Callable[[str], None] | None = None


def _normalized_alignment_title(show: str, episode: RssEpisode) -> str:
    title = normalize_title(show, episode.title) if show else episode.title
    return normalize_text(title)


def _normalized_alignment_description(episode: RssEpisode) -> str:
    return normalize_text(episode.description or "")


def _build_alignment_candidates(episodes: list[RssEpisode], show: str) -> list[_AlignmentCandidate]:
    return [
        _AlignmentCandidate(
            episode=episode,
            title=_normalized_alignment_title(show, episode),
            description=_normalized_alignment_description(episode),
        )
        for episode in episodes
    ]


def _has_date_signal(ref: _AlignmentCandidate, dl: _AlignmentCandidate) -> bool:
    return ref.episode.pub_date is not None and dl.episode.pub_date is not None


def _has_description_signal(ref: _AlignmentCandidate, dl: _AlignmentCandidate) -> bool:
    return bool(ref.description and dl.description)


def _weighted_score(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    s_title: float,
    s_desc: float,
) -> float:
    """Metadata-aware similarity score with ID as a small bonus."""
    s_id = _id_similarity(ref.episode, dl.episode)
    has_desc = _has_description_signal(ref, dl)
    if not s_id and not has_desc and s_title < SPARSE_TITLE_MIN:
        return 0.0

    weighted_sum = W_TITLE * s_title
    total_weight = W_TITLE

    opt_sum, opt_total = _compute_optional_weights(ref, dl, s_desc)
    weighted_sum += opt_sum
    total_weight += opt_total

    base_score = weighted_sum / total_weight
    return min(1.0, base_score + (W_ID * s_id))


def _compute_optional_weights(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    s_desc: float,
) -> tuple[float, float]:
    """Return (weighted_sum, total_weight) for optional metadata contributions."""
    weighted = 0.0
    total = 0.0
    has_date = _has_date_signal(ref, dl)
    has_desc = _has_description_signal(ref, dl)
    if has_date:
        weighted += W_DATE * sim_date(ref.episode.pub_date, dl.episode.pub_date)
        total += W_DATE
    if has_desc:
        weighted += W_DESC * s_desc
        total += W_DESC
    return weighted, total


def _build_alignment_scores(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
    *,
    similarity: StringSimilarityFn = _cdist_similarity,
) -> dict[tuple[int, int], float]:
    ref_candidates = _build_alignment_candidates(references, show)
    dl_candidates = _build_alignment_candidates(downloads, show)

    title_matrix, desc_matrix = _build_similarity_matrices(
        ref_candidates,
        dl_candidates,
        similarity,
    )
    return _score_alignment_candidates(
        ref_candidates,
        dl_candidates,
        title_matrix,
        desc_matrix,
    )


def _build_similarity_matrices(
    ref_candidates: list[_AlignmentCandidate],
    dl_candidates: list[_AlignmentCandidate],
    similarity: StringSimilarityFn,
) -> tuple[list[list[float]], list[list[float]]]:
    title_matrix = similarity(
        [candidate.title for candidate in ref_candidates],
        [candidate.title for candidate in dl_candidates],
    )
    desc_matrix = similarity(
        [candidate.description for candidate in ref_candidates],
        [candidate.description for candidate in dl_candidates],
    )
    return title_matrix, desc_matrix


def _score_alignment_candidates(
    ref_candidates: list[_AlignmentCandidate],
    dl_candidates: list[_AlignmentCandidate],
    title_matrix: list[list[float]],
    desc_matrix: list[list[float]],
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(ref_candidates):
        for d_idx, dl in enumerate(dl_candidates):
            scores[(r_idx, d_idx)] = _weighted_score(
                ref,
                dl,
                float(title_matrix[r_idx][d_idx]),
                float(desc_matrix[r_idx][d_idx]),
            )
    return scores


def _sorted_pairs_above_tolerance(
    scores: dict[tuple[int, int], float],
) -> list[tuple[tuple[int, int], float]]:
    ordered_pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [pair for pair in ordered_pairs if pair[1] >= MATCH_TOLERANCE]


def _append_match_if_unused(
    pair: tuple[int, int],
    matches: list[tuple[int, int]],
    used_refs: set[int],
    used_dls: set[int],
) -> None:
    r_idx, d_idx = pair
    if r_idx in used_refs or d_idx in used_dls:
        return
    matches.append((r_idx, d_idx))
    used_refs.add(r_idx)
    used_dls.add(d_idx)


def align_episodes_impl(
    references: list[RssEpisode], downloads: list[RssEpisode], show: str = ""
) -> list[tuple[int, int]]:
    """Core greedy aligner implementation (internal).

    Kept as a private implementation so catalog can delegate to a pluggable
    adapter while still providing a stable default behavior.
    """
    scores = _build_alignment_scores(references, downloads, show)
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()

    for (r_idx, d_idx), _score in _sorted_pairs_above_tolerance(scores):
        _append_match_if_unused((r_idx, d_idx), matches, used_refs, used_dls)

    return matches


def align_episodes(
    references: list[RssEpisode], downloads: list[RssEpisode], show: str = ""
) -> list[tuple[int, int]]:
    """Public alignment entrypoint that delegates to an adapter.

    The default adapter delegates back to `align_episodes_impl` so behavior
    remains unchanged. Local imports are used to avoid circular imports at
    module import time.
    """
    try:
        from src.adapters import get_alignment_adapter

        adapter = get_alignment_adapter()
        return adapter.align_episodes(references, downloads, show)
    except Exception:
        # Fallback to the local implementation on any adapter error.
        return align_episodes_impl(references, downloads, show)


def _thumbnail_rank(url: str | None) -> int:
    if not url:
        return 0
    return max((rank for kw, rank in _THUMBNAIL_RANK.items() if kw in url), default=0)


def _best_thumbnail(a: str | None, b: str | None) -> str | None:
    """Return the higher-resolution thumbnail inferred from URL keywords."""
    candidates = [url for url in (a, b) if url]
    if not candidates:
        return None
    return max(candidates, key=_thumbnail_rank)


def _choose_episode_id(ref: RssEpisode, dl: RssEpisode) -> str:
    if ref.id.startswith("http") or not dl.id.startswith("http"):
        return dl.id
    return ref.id


def _choose_title(ref: RssEpisode, dl: RssEpisode) -> str:
    return max([ref.title, dl.title], key=lambda t: (len(t), t.count(":")))


def _earliest_pub_date(ref: RssEpisode, dl: RssEpisode) -> datetime | None:
    return min((d for d in (ref.pub_date, dl.pub_date) if d is not None), default=None)


def _choose_description(ref: RssEpisode, dl: RssEpisode) -> str:
    return max([ref.description or "", dl.description or ""], key=len)


def _merge_sources(ref: RssEpisode, dl: RssEpisode) -> list[str]:
    return list({url for url in (ref.content, dl.content) if url})


def merge_episode(ref: RssEpisode, dl: RssEpisode) -> EpisodeData:
    """Merge a reference + download episode pair into canonical EpisodeData."""
    return EpisodeData(
        id=_choose_episode_id(ref, dl),
        title=_choose_title(ref, dl),
        description=_choose_description(ref, dl),
        source=_merge_sources(ref, dl),
        thumbnail=_best_thumbnail(ref.image, dl.image),
        upload_date=_earliest_pub_date(ref, dl),
    )


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
    return [merge_episode(references[r], downloads[d]) for r, d in pairs]


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
) -> tuple[list[tuple[int, int]], list[EpisodeData]]:
    pairs = _timed_stage(
        "align_episodes",
        lambda: _align_config_episodes(config_name, references, downloads),
        options,
    )
    episodes = _timed_stage(
        "merge_episodes",
        lambda: _merge_episode_list(references, downloads, pairs),
        options,
    )
    return pairs, episodes


def _coerce_merge_config_options(
    options: MergeConfigOptions | None,
    legacy_kwargs: dict[str, Any],
) -> MergeConfigOptions:
    if options is not None and not legacy_kwargs:
        return options
    if options is not None:
        return MergeConfigOptions(
            callback=legacy_kwargs.get("callback", options.callback),
            refresh_sources=legacy_kwargs.get(
                "refresh_sources",
                options.refresh_sources,
            ),
            timings=legacy_kwargs.get("timings", options.timings),
            on_stage=legacy_kwargs.get("on_stage", options.on_stage),
        )
    return MergeConfigOptions(
        callback=legacy_kwargs.get("callback"),
        refresh_sources=legacy_kwargs.get("refresh_sources", False),
        timings=legacy_kwargs.get("timings"),
        on_stage=legacy_kwargs.get("on_stage"),
    )


def _collect_merge_result_parts(
    config: PodcastConfig,
    options: MergeConfigOptions,
) -> tuple[
    list[RssEpisode],
    list[RssEpisode],
    list[SourceTrace],
    list[tuple[int, int]],
    list[EpisodeData],
]:
    references, downloads, source_traces = _collect_feed_sets(config, options)
    pairs, episodes = _collect_merge_parts(
        config.name,
        references,
        downloads,
        options,
    )
    return references, downloads, source_traces, pairs, episodes


def merge_config(
    config: PodcastConfig,
    options: MergeConfigOptions | None = None,
    **legacy_kwargs: Any,
) -> MergeResult:
    """Fetch, align, and merge episodes for a single podcast config."""
    merged_options = _coerce_merge_config_options(options, legacy_kwargs)
    total_start = perf_counter()

    references, downloads, source_traces, pairs, episodes = _collect_merge_result_parts(
        config,
        merged_options,
    )
    _maybe_record_timing(merged_options.timings, "merge_config_total", total_start)

    return MergeResult(
        config=config,
        references=references,
        downloads=downloads,
        source_traces=source_traces,
        pairs=pairs,
        episodes=episodes,
    )


def merge_episode_pairs(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
) -> list[EpisodeData]:
    """Merge matched reference/download pairs into canonical episodes."""
    pairs = align_episodes(references, downloads, show)
    return [merge_episode(references[r_idx], downloads[d_idx]) for r_idx, d_idx in pairs]


# ---------------------------------------------------------------------------
# Episode collection helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EpisodeFetchContext:
    title: str
    is_reference: bool
    callback: Callback | None = None
    refresh_sources: bool = False


def _legacy_fetch_arg(legacy_args: tuple[object, ...], index: int) -> object | None:
    return legacy_args[index] if len(legacy_args) > index else None


def _coerce_legacy_callback(value: object | None) -> Callback | None:
    if value is None or callable(value):
        return cast(Callback | None, value)
    return None


def _coerce_episode_fetch_context(
    context_or_title: EpisodeFetchContext | str,
    legacy_args: tuple[object, ...],
) -> EpisodeFetchContext:
    if isinstance(context_or_title, EpisodeFetchContext):
        return context_or_title

    return EpisodeFetchContext(
        title=context_or_title,
        is_reference=bool(_legacy_fetch_arg(legacy_args, 0)),
        callback=_coerce_legacy_callback(_legacy_fetch_arg(legacy_args, 1)),
        refresh_sources=bool(_legacy_fetch_arg(legacy_args, 2)),
    )


def _collect_episodes(
    sources: list[FeedSource],
    context_or_title: EpisodeFetchContext | str,
    *legacy_args: object,
) -> list[RssEpisode]:
    """Fetch and deduplicate episodes from a list of FeedSource objects."""
    merged, _traces = _collect_episodes_with_traces(sources, context_or_title, *legacy_args)
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
    context_or_title: EpisodeFetchContext | str,
    *legacy_args: object,
) -> tuple[list[RssEpisode], list[SourceTrace]]:
    """Fetch, trace, and deduplicate episodes from a list of FeedSource objects."""
    context = _coerce_episode_fetch_context(context_or_title, legacy_args)
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

    # Get appropriate adapter for source type
    adapter = get_episode_source_adapter(resolved)

    # Build options dict for adapter
    options = {
        "title": context.title,
        "detailed": context.is_reference,  # is_reference maps to detailed flag for YouTube
        "callback": context.callback,
        "refresh": context.refresh_sources,
    }

    # Delegate to adapter
    return adapter.fetch_episodes(resolved, options)


def _merge_episode_album(
    merged: list[RssEpisode],
    album: list[RssEpisode],
) -> None:
    duplicate_indices = {d_idx for _, d_idx in align_episodes(merged, album)}
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
    source_episodes = _collect_episodes(
        config.references,
        EpisodeFetchContext(
            title=config.name,
            is_reference=True,
            callback=callback,
            refresh_sources=refresh_sources,
        ),
    )

    return source_episodes


# Compatibility aliases: tests may patch these names on the `src.catalog` module.
get_rss_episodes = _rss.get_rss_episodes
get_youtube_episodes = _yt_meta.get_youtube_episodes
