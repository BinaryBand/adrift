# cspell: ignore cdist
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from rapidfuzz import fuzz

from src.app_common import MATCH_TOLERANCE
from src.models import EpisodeData, RssEpisode
from src.utils.progress import Callback
from src.utils.text import normalize_text
from src.utils.title_normalization import normalize_title
from src.settings import DATE_SCORE_TIERS, SPARSE_TITLE_MIN, W_DATE, W_DESC, W_ID, W_TITLE

StringSimilarityFn = Callable[[list[str], list[str]], list[list[float]]]

_THUMBNAIL_RANK = {"maxres": 4, "hq": 3, "mq": 2, "sq": 1}


def _similarity_clean(ac: str, bc: str) -> float:
    """Similarity when inputs are already cleaned (lowercased, slugged)."""
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    return r * 0.4 + ts * 0.3 + tset * 0.3


def _cdist_similarity(a: list[str], b: list[str]) -> list[list[float]]:
    # Extracted helpers keep this function short so complexity gates pass.
    def _pairwise_scores(
        a_list: list[str], b_list: list[str], scorer: Callable[[str, str], float]
    ) -> list[list[float]]:
        return [[scorer(x, y) / 100.0 for y in b_list] for x in a_list]

    def _combine_matrices(
        ratio: list[list[float]], token_sort: list[list[float]], token_set: list[list[float]]
    ) -> list[list[float]]:
        result: list[list[float]] = []
        for i in range(len(ratio)):
            row: list[float] = []
            for j in range(len(ratio[i])):
                row.append(ratio[i][j] * 0.4 + token_sort[i][j] * 0.3 + token_set[i][j] * 0.3)
            result.append(row)
        return result

    try:
        from rapidfuzz.process import cdist  # type: ignore
    except Exception:
        ratio_scores = _pairwise_scores(a, b, fuzz.ratio)
        token_sort_scores = _pairwise_scores(a, b, fuzz.token_sort_ratio)
        token_set_scores = _pairwise_scores(a, b, fuzz.token_set_ratio)
        return _combine_matrices(ratio_scores, token_sort_scores, token_set_scores)

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
    return _score_match_pairs(files_clean, episodes_clean, callback)


def _prepare_match_inputs(
    files: list[str],
    episodes: list[str],
    title: str,
) -> tuple[list[str], list[str]]:
    return (
        [normalize_text(normalize_title(title, item)) for item in files],
        [normalize_text(normalize_title(title, item)) for item in episodes],
    )


def _score_match_pairs(
    files_clean: list[str],
    episodes_clean: list[str],
    callback: Callback | None = None,
) -> list[tuple[int, int]]:
    scores: dict[tuple[int, int], float] = {}
    total = len(files_clean)
    for f_idx, file_name in enumerate(files_clean):
        for e_idx, episode_name in enumerate(episodes_clean):
            scores[(f_idx, e_idx)] = _similarity_clean(file_name, episode_name)
        if callback:
            callback(f_idx + 1, total)

    matches = _select_unique_matches(scores)
    return _filter_tolerated_matches(matches, scores)


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
    """Core greedy aligner implementation (internal)."""
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
    """Public alignment entrypoint that delegates to an adapter."""
    try:
        from src.adapters import get_alignment_adapter

        adapter = get_alignment_adapter()
        return adapter.align_episodes(references, downloads, show)
    except Exception:
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
    return max([ref.title, dl.title], key=lambda title: (len(title), title.count(":")))


def _earliest_pub_date(ref: RssEpisode, dl: RssEpisode) -> datetime | None:
    return min((date for date in (ref.pub_date, dl.pub_date) if date is not None), default=None)


def _choose_description(ref: RssEpisode, dl: RssEpisode) -> str:
    # Ensure a `str` return for the type checker
    return str(max([ref.description or "", dl.description or ""], key=len))


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


def merge_episode_pairs(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
) -> list[EpisodeData]:
    """Merge matched reference/download pairs into canonical episodes."""
    pairs = align_episodes(references, downloads, show)
    return [merge_episode(references[r_idx], downloads[d_idx]) for r_idx, d_idx in pairs]


__all__ = [
    "StringSimilarityFn",
    "align_episodes",
    "align_episodes_impl",
    "match",
    "merge_episode",
    "merge_episode_pairs",
    "sim_date",
    "_best_thumbnail",
    "_build_alignment_scores",
    "_normalized_alignment_title",
]
