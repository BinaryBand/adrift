from datetime import datetime
from typing import Any

from rapidfuzz import fuzz

from src.app_common import (
    MATCH_TOLERANCE,
    FeedSource,
    PodcastConfig,
    ensure_feed_source,
)
from src.app_runner import normalize_title
from src.models.output import EpisodeData
from src.models.pipeline import MergeResult
from src.utils.progress import Callback
from src.utils.text import normalize_text
from src.web import rss as _rss
from src.web.rss import (
    RssEpisode,
)
from src.youtube import metadata as _yt_meta


def _similarity_clean(ac: str, bc: str) -> float:
    """Similarity when inputs are already cleaned (lowercased, slugged)."""
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    return r * 0.4 + ts * 0.3 + tset * 0.3


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


def _description_similarity(ref: RssEpisode, dl: RssEpisode) -> float:
    rc = normalize_text(ref.description or "")
    dc = normalize_text(dl.description or "")
    if not rc and not dc:
        return 0.0
    return _similarity_clean(rc, dc)


def _normalized_alignment_title(show: str, episode: RssEpisode) -> str:
    title = normalize_title(show, episode.title) if show else episode.title
    return normalize_text(title)


def _has_date_signal(ref: RssEpisode, dl: RssEpisode) -> bool:
    return ref.pub_date is not None and dl.pub_date is not None


def _has_description_signal(ref: RssEpisode, dl: RssEpisode) -> bool:
    return bool((ref.description or "").strip() and (dl.description or "").strip())


def _weighted_score(ref: RssEpisode, dl: RssEpisode, show: str = "") -> float:
    """Metadata-aware similarity score with ID as a small bonus."""
    s_id = _id_similarity(ref, dl)
    s_title = _similarity_clean(
        _normalized_alignment_title(show, ref),
        _normalized_alignment_title(show, dl),
    )
    has_date = _has_date_signal(ref, dl)
    has_desc = _has_description_signal(ref, dl)
    if not s_id and not has_desc and s_title < SPARSE_TITLE_MIN:
        return 0.0

    weighted_sum = W_TITLE * s_title
    total_weight = W_TITLE

    # Compute optional contributions (date / description) in a helper
    opt_sum, opt_total = _compute_optional_weights(ref, dl, has_date, has_desc)
    weighted_sum += opt_sum
    total_weight += opt_total

    base_score = weighted_sum / total_weight
    return min(1.0, base_score + (W_ID * s_id))


def _compute_optional_weights(
    ref: RssEpisode, dl: RssEpisode, has_date: bool, has_desc: bool
) -> tuple[float, float]:
    """Return (weighted_sum, total_weight) for optional metadata contributions."""
    weighted = 0.0
    total = 0.0
    if has_date:
        weighted += W_DATE * sim_date(ref.pub_date, dl.pub_date)
        total += W_DATE
    if has_desc:
        weighted += W_DESC * _description_similarity(ref, dl)
        total += W_DESC
    return weighted, total


def _build_alignment_scores(
    references: list[RssEpisode], downloads: list[RssEpisode], show: str = ""
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(references):
        for d_idx, dl in enumerate(downloads):
            scores[(r_idx, d_idx)] = _weighted_score(ref, dl, show)
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


def align_episodes(
    references: list[RssEpisode], downloads: list[RssEpisode], show: str = ""
) -> list[tuple[int, int]]:
    """Greedy cross-alignment of reference and download episode lists.

    Returns a list of ``(ref_idx, dl_idx)`` index pairs for matched episodes
    with score ≥ MATCH_TOLERANCE (θ = 0.75 by default).
    """
    scores = _build_alignment_scores(references, downloads, show)
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()

    for (r_idx, d_idx), _score in _sorted_pairs_above_tolerance(scores):
        _append_match_if_unused((r_idx, d_idx), matches, used_refs, used_dls)

    return matches


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


def merge_config(
    config: PodcastConfig,
    callback: Callback | None = None,
    refresh_sources: bool = False,
) -> MergeResult:
    """Fetch, align, and merge episodes for a single podcast config."""
    references = process_feeds(config, callback, refresh_sources=refresh_sources)
    downloads = process_sources(config, callback, refresh_sources=refresh_sources)
    pairs = align_episodes(references, downloads, config.name)
    episodes = [merge_episode(references[r], downloads[d]) for r, d in pairs]
    return MergeResult(
        config=config,
        references=references,
        downloads=downloads,
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


def _collect_episodes(
    sources: list[FeedSource],
    title: str,
    is_reference: bool,
    callback: Callback | None = None,
    refresh_sources: bool = False,
) -> list[RssEpisode]:
    """Fetch and deduplicate episodes from a list of FeedSource objects."""
    albums = [
        _fetch_source_episodes(source, title, is_reference, callback, refresh_sources)
        for source in sources
    ]

    if not albums:
        return []

    merged: list[RssEpisode] = albums[0]
    for album in albums[1:]:
        _merge_episode_album(merged, album)

    return merged


def _fetch_source_episodes(
    source: FeedSource | dict[str, Any],
    title: str,
    is_reference: bool,
    callback: Callback | None = None,
    refresh_sources: bool = False,
) -> list[RssEpisode]:
    from src.adapters import get_episode_source_adapter

    resolved = ensure_feed_source(source)

    # Get appropriate adapter for source type
    adapter = get_episode_source_adapter(resolved)

    # Build options dict for adapter
    options = {
        "title": title,
        "detailed": is_reference,  # is_reference maps to detailed flag for YouTube
        "callback": callback,
        "refresh": refresh_sources,
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
        config.name,
        False,
        callback,
        refresh_sources=refresh_sources,
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
    title = config.name
    source_episodes = _collect_episodes(
        config.references,
        title,
        True,
        callback,
        refresh_sources=refresh_sources,
    )

    return source_episodes


# Compatibility aliases: tests may patch these names on the `src.catalog` module.
get_rss_episodes = _rss.get_rss_episodes
get_youtube_episodes = _yt_meta.get_youtube_episodes
