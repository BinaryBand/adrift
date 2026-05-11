# cspell: ignore cdist
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from rapidfuzz import fuzz

from src.models import AlignmentConfig, EpisodeData, RssEpisode
from src.utils.progress import Callback
from src.utils.text import normalize_text
from src.utils.title_normalization import normalize_title

StringSimilarityFn = Callable[[list[str], list[str]], list[list[float]]]

_THUMBNAIL_RANK = {"maxres": 4, "hq": 3, "mq": 2, "sq": 1}
# Podcast-specific brand words ("morbid", "tales", "listener") are included
# because they appear in nearly every episode title on their respective feeds,
# making them useless as discriminating anchor tokens.
_BASE_ANCHOR_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "of",
    "with",
    "from",
    "for",
    "to",
    "in",
    "on",
    "at",
    "by",
    "episode",
    "part",
    "listener",
    "tales",
    "podcast",
    "mini",
    "special",
    "guest",
    "guests",
    "bonus",
    "volume",
    "vol",
}

_DEFAULT_ALIGNMENT = AlignmentConfig()


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
    except ImportError:
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
    return _filter_tolerated_matches(matches, scores, _DEFAULT_ALIGNMENT.match_tolerance)


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
    matches: list[tuple[int, int]],
    scores: dict[tuple[int, int], float],
    tolerance: float,
) -> list[tuple[int, int]]:
    return [match for match in matches if scores[match] >= tolerance]


def _align_datetime_pair(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    if a.tzinfo is not None and b.tzinfo is None:
        return a, b.replace(tzinfo=a.tzinfo)
    if a.tzinfo is None and b.tzinfo is not None:
        return a.replace(tzinfo=b.tzinfo), b
    return a, b


def sim_date(
    a: datetime | None,
    b: datetime | None,
    date_score_tiers: list[tuple[int, float]] | tuple[tuple[int, float], ...] | None = None,
) -> float:
    """Tiered date similarity per the spec."""
    if a is None or b is None:
        return 0.0
    a, b = _align_datetime_pair(a, b)
    tiers = date_score_tiers or _DEFAULT_ALIGNMENT.date_score_tiers
    delta = abs((a - b).days)
    return next((score for max_days, score in tiers if delta <= max_days), 0.0)


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


_NUMBERED_MARKER_PATTERNS = (
    r"\blistener\s+tales(?:\s+episode)?\s+(\d+)\b",
    r"\bpart\s+(\d+)\b",
    r"\b(?:volume|vol\.?)\s*(\d+)\b",
    r"\bepisode\s+(\d+)\b",
)


def _extract_numbered_marker(pattern: str, title: str) -> int | None:
    m = re.search(pattern, title)
    return int(m.group(1)) if m else None


def _has_structured_number_mismatch(ref_title: str, dl_title: str) -> bool:
    for pattern in _NUMBERED_MARKER_PATTERNS:
        ref_val = _extract_numbered_marker(pattern, ref_title)
        dl_val = _extract_numbered_marker(pattern, dl_title)
        if ref_val is not None and dl_val is not None and ref_val != dl_val:
            return True
    return False


def _coerce_alignment(alignment: AlignmentConfig | None) -> AlignmentConfig:
    return alignment or _DEFAULT_ALIGNMENT


def _alignment_stopwords(alignment: AlignmentConfig) -> frozenset[str]:
    extras = {item.strip().lower() for item in alignment.extra_stopwords if item.strip()}
    return frozenset(_BASE_ANCHOR_STOPWORDS | extras)


def _anchor_tokens(title: str, stopwords: frozenset[str]) -> frozenset[str]:
    return frozenset(t for t in title.split() if t not in stopwords)


def _anchor_token_overlap(ref_title: str, dl_title: str, stopwords: frozenset[str]) -> int:
    return len(_anchor_tokens(ref_title, stopwords) & _anchor_tokens(dl_title, stopwords))


def _has_token_containment(ref_title: str, dl_title: str, stopwords: frozenset[str]) -> bool:
    """True when all anchor tokens of the shorter title appear in the longer AND ≥ 2."""
    ref_tok = _anchor_tokens(ref_title, stopwords)
    dl_tok = _anchor_tokens(dl_title, stopwords)
    if not ref_tok or not dl_tok:
        return False
    if len(ref_tok) <= len(dl_tok):
        return len(ref_tok) >= 2 and ref_tok.issubset(dl_tok)
    return len(dl_tok) >= 2 and dl_tok.issubset(ref_tok)


# When title similarity is at or above this value, date signal is excluded from
# weighting — the date may be unreliable for YouTube backfills of older episodes.
_TITLE_CERTAINTY_MIN = 0.97

# Additive bonus applied when shorter title's anchor tokens are fully contained
# in the longer title.  Helps references with simplified titles match enriched
# download titles (e.g. "Denise Huber Part 1" ↔ "Disappearance of Denise Huber Part 1").
_CONTAINMENT_BONUS = 0.08


class _Sims(NamedTuple):
    """Pre-computed title and description similarity scores for a candidate pair."""

    title: float
    desc: float = 0.0


@dataclass(frozen=True)
class _AlignmentRuntime:
    config: AlignmentConfig
    stopwords: frozenset[str]


class _AlignmentMatrices(NamedTuple):
    title: list[list[float]]
    description: list[list[float]]


@dataclass(frozen=True)
class _AlignmentRequest:
    show: str
    similarity: StringSimilarityFn
    runtime: _AlignmentRuntime


@dataclass(frozen=True)
class _AlignmentScoreFrame:
    refs: list[_AlignmentCandidate]
    dls: list[_AlignmentCandidate]
    matrices: _AlignmentMatrices
    runtime: _AlignmentRuntime


@dataclass(frozen=True)
class _ScoreFrame:
    ref: _AlignmentCandidate
    dl: _AlignmentCandidate
    sims: _Sims
    runtime: _AlignmentRuntime
    include_date: bool


def _is_sparse_title(s_id: float, has_desc: bool, s_title: float, sparse_title_min: float) -> bool:
    return not s_id and not has_desc and s_title < sparse_title_min


def _score(
    ref: "_AlignmentCandidate",
    dl: "_AlignmentCandidate",
    sims: "_Sims",
    include_date: bool | None = None,
) -> float:
    runtime = _AlignmentRuntime(
        config=_DEFAULT_ALIGNMENT,
        stopwords=_alignment_stopwords(_DEFAULT_ALIGNMENT),
    )
    resolved_include_date = (
        include_date if include_date is not None else sims.title < _TITLE_CERTAINTY_MIN
    )
    return _score_with_runtime(
        _ScoreFrame(
            ref=ref,
            dl=dl,
            sims=sims,
            runtime=runtime,
            include_date=resolved_include_date,
        )
    )


def _score_with_runtime(frame: _ScoreFrame) -> float:
    base = _weighted_base_score(frame)
    containment = _containment_bonus(
        frame.ref,
        frame.dl,
        frame.runtime,
        frame.include_date,
    )
    id_bonus = frame.runtime.config.weights.id * _id_similarity(frame.ref.episode, frame.dl.episode)
    return min(1.0, base + id_bonus + containment)


def _weighted_base_score(frame: _ScoreFrame) -> float:
    weights = frame.runtime.config.weights
    weighted_sum = weights.title * frame.sims.title
    total_weight = weights.title
    if _has_description_signal(frame.ref, frame.dl):
        weighted_sum += weights.description * frame.sims.desc
        total_weight += weights.description
    if frame.include_date and _has_date_signal(frame.ref, frame.dl):
        weighted_sum += weights.date * sim_date(
            frame.ref.episode.pub_date,
            frame.dl.episode.pub_date,
            frame.runtime.config.date_score_tiers,
        )
        total_weight += weights.date
    return weighted_sum / total_weight


def _containment_bonus(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    runtime: _AlignmentRuntime,
    include_date: bool,
) -> float:
    has_containment = include_date and _has_token_containment(
        ref.title,
        dl.title,
        runtime.stopwords,
    )
    return _CONTAINMENT_BONUS if has_containment else 0.0


def _weighted_score(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    runtime: _AlignmentRuntime,
) -> float:
    """Metadata-aware similarity score with ID as a small bonus."""
    if _has_structured_number_mismatch(ref.title, dl.title):
        return 0.0

    # Avoid promoting generic title similarities when there is no meaningful token overlap.
    if _anchor_token_overlap(ref.title, dl.title, runtime.stopwords) == 0 and sims.title < 0.75:
        return 0.0

    # Near-perfect title match: date signal is excluded (may be unreliable for
    # YouTube backfills where the upload date can lag RSS publication by months).
    if sims.title >= _TITLE_CERTAINTY_MIN:
        return _score_with_runtime(
            _ScoreFrame(ref=ref, dl=dl, sims=sims, runtime=runtime, include_date=False)
        )

    s_id = _id_similarity(ref.episode, dl.episode)
    has_desc = _has_description_signal(ref, dl)
    if _is_sparse_title(s_id, has_desc, sims.title, runtime.config.sparse_title_min):
        return 0.0

    return _score_with_runtime(
        _ScoreFrame(ref=ref, dl=dl, sims=sims, runtime=runtime, include_date=True)
    )


def _build_similarity_matrices(
    ref_candidates: list[_AlignmentCandidate],
    dl_candidates: list[_AlignmentCandidate],
    similarity: StringSimilarityFn,
) -> _AlignmentMatrices:
    title_matrix = similarity(
        [candidate.title for candidate in ref_candidates],
        [candidate.title for candidate in dl_candidates],
    )
    desc_matrix = similarity(
        [candidate.description for candidate in ref_candidates],
        [candidate.description for candidate in dl_candidates],
    )
    return _AlignmentMatrices(title=title_matrix, description=desc_matrix)


def _score_alignment_candidates(frame: _AlignmentScoreFrame) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(frame.refs):
        for d_idx, dl in enumerate(frame.dls):
            sims = _Sims(
                float(frame.matrices.title[r_idx][d_idx]),
                float(frame.matrices.description[r_idx][d_idx]),
            )
            scores[(r_idx, d_idx)] = _weighted_score(
                ref,
                dl,
                sims,
                frame.runtime,
            )
    return scores


def _resolve_alignment_request(
    request_or_show: _AlignmentRequest | str,
    alignment: AlignmentConfig | None,
) -> _AlignmentRequest:
    if isinstance(request_or_show, _AlignmentRequest):
        return request_or_show

    resolved_alignment = _coerce_alignment(alignment)
    return _AlignmentRequest(
        show=request_or_show,
        similarity=_cdist_similarity,
        runtime=_AlignmentRuntime(
            config=resolved_alignment,
            stopwords=_alignment_stopwords(resolved_alignment),
        ),
    )


def _build_alignment_scores(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    request_or_show: _AlignmentRequest | str = "",
    alignment: AlignmentConfig | None = None,
) -> dict[tuple[int, int], float]:
    request = _resolve_alignment_request(request_or_show, alignment)
    ref_candidates = _build_alignment_candidates(references, request.show)
    dl_candidates = _build_alignment_candidates(downloads, request.show)

    matrices = _build_similarity_matrices(
        ref_candidates,
        dl_candidates,
        request.similarity,
    )
    return _score_alignment_candidates(
        _AlignmentScoreFrame(
            refs=ref_candidates,
            dls=dl_candidates,
            matrices=matrices,
            runtime=request.runtime,
        )
    )


def _sorted_pairs_above_tolerance(
    scores: dict[tuple[int, int], float],
    match_tolerance: float,
) -> list[tuple[tuple[int, int], float]]:
    ordered_pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [pair for pair in ordered_pairs if pair[1] >= match_tolerance]


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
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
    alignment: AlignmentConfig | None = None,
) -> list[tuple[int, int]]:
    """Core greedy aligner implementation (internal)."""
    resolved_alignment = _coerce_alignment(alignment)
    runtime = _AlignmentRuntime(
        config=resolved_alignment,
        stopwords=_alignment_stopwords(resolved_alignment),
    )
    scores = _build_alignment_scores(
        references,
        downloads,
        _AlignmentRequest(show=show, similarity=_cdist_similarity, runtime=runtime),
    )
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()

    for (r_idx, d_idx), _score in _sorted_pairs_above_tolerance(
        scores,
        resolved_alignment.match_tolerance,
    ):
        _append_match_if_unused((r_idx, d_idx), matches, used_refs, used_dls)

    return matches


def align_episodes(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
    alignment: "AlignmentConfig | None" = None,
) -> list[tuple[int, int]]:
    """Public alignment entrypoint that delegates to an adapter."""
    from src.adapters import get_alignment_adapter

    adapter = get_alignment_adapter()
    return adapter.align_episodes(references, downloads, show, alignment)


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
    dates = [d for d in (ref.pub_date, dl.pub_date) if d is not None]
    if len(dates) < 2:
        return dates[0] if dates else None
    a, b = _align_datetime_pair(dates[0], dates[1])
    return a if a <= b else b


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
