# cspell: ignore cdist
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple, cast

from rapidfuzz import fuzz

from adrift.models import AlignmentConfig, EpisodeData, RssEpisode
from adrift.utils.profiler import profile
from adrift.utils.progress import Callback
from adrift.utils.text import normalize_text
from adrift.utils.title_normalization import normalize_title

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
_TEMPORAL_METADATA_TOKENS = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


def _similarity_clean(ac: str, bc: str) -> float:
    """Similarity when inputs are already cleaned (lowercased, slugged)."""
    r = fuzz.ratio(ac, bc) / 100.0
    ts = fuzz.token_sort_ratio(ac, bc) / 100.0
    tset = fuzz.token_set_ratio(ac, bc) / 100.0
    return r * 0.4 + ts * 0.3 + tset * 0.3


def _cdist_similarity(a: list[str], b: list[str]) -> list[list[float]]:
    from rapidfuzz import process as rapidfuzz_process

    cdist = cast(Any, rapidfuzz_process).cdist

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


@dataclass(frozen=True)
class AnchorTokens:
    ref: frozenset[str]
    dl: frozenset[str]

    @classmethod
    def from_titles(
        cls,
        ref_title: str,
        dl_title: str,
        stopwords: frozenset[str],
    ) -> "AnchorTokens":
        return cls(
            ref=frozenset(token for token in ref_title.split() if token not in stopwords),
            dl=frozenset(token for token in dl_title.split() if token not in stopwords),
        )

    @property
    def overlap(self) -> int:
        return len(self.ref & self.dl)

    @property
    def containment(self) -> bool:
        """True when shorter anchor token set is a subset of the larger and has >= 2 tokens."""
        if not self.ref or not self.dl:
            return False
        if len(self.ref) <= len(self.dl):
            return len(self.ref) >= 2 and self.ref.issubset(self.dl)
        return len(self.dl) >= 2 and self.dl.issubset(self.ref)

    @property
    def subset_extra_tokens(self) -> frozenset[str] | None:
        if not self.ref or not self.dl:
            return None
        if self.ref.issubset(self.dl):
            return frozenset(self.dl - self.ref)
        if self.dl.issubset(self.ref):
            return frozenset(self.ref - self.dl)
        return None


def _contains_discriminating_subset_extra_token(tokens: frozenset[str]) -> bool:
    return any(
        any(ch.isalpha() for ch in token) and token not in _TEMPORAL_METADATA_TOKENS
        for token in tokens
    )


def _should_reject_weak_anchor_match(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: "_Sims",
    runtime: "_AlignmentRuntime",
) -> bool:
    anchor_tokens = AnchorTokens.from_titles(ref.title, dl.title, runtime.stopwords)
    is_weak_overlap = anchor_tokens.overlap == 0
    is_low_title_similarity = sims.title < 0.75
    return is_weak_overlap and is_low_title_similarity


def _should_reject_metadata_subset_rescue(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: "_Sims",
    runtime: "_AlignmentRuntime",
) -> bool:
    s_id = _id_similarity(ref.episode, dl.episode)
    has_desc = _has_description_signal(ref, dl)
    anchor_tokens = AnchorTokens.from_titles(ref.title, dl.title, runtime.stopwords)
    subset_extra_tokens = anchor_tokens.subset_extra_tokens
    is_zero_id_match = not s_id
    has_date = _has_date_signal(ref, dl)
    has_single_subset_extra = subset_extra_tokens is not None and len(subset_extra_tokens) == 1
    has_discriminating_extra = bool(
        subset_extra_tokens and _contains_discriminating_subset_extra_token(subset_extra_tokens)
    )
    in_subset_rescue_band = _METADATA_RESCUE_SUBSET_SIM_MIN <= sims.title < _TITLE_CERTAINTY_MIN
    return bool(
        is_zero_id_match
        and has_desc
        and has_date
        and has_single_subset_extra
        and has_discriminating_extra
        and in_subset_rescue_band
    )


# When title similarity is at or above this value, date signal is excluded from
# weighting — the date may be unreliable for YouTube backfills of older episodes.
_TITLE_CERTAINTY_MIN = 0.97
_METADATA_RESCUE_SUBSET_SIM_MIN = 0.78

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


@dataclass(frozen=True)
class _AlignmentRequest:
    show: str
    similarity: StringSimilarityFn
    runtime: _AlignmentRuntime


@dataclass(frozen=True)
class _AlignmentState:
    refs: list[_AlignmentCandidate]
    dls: list[_AlignmentCandidate]
    title_matrix: list[list[float]]
    description_matrix: list[list[float]]
    runtime: _AlignmentRuntime


@dataclass(frozen=True)
class _ScoreContext:
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
    context = _ScoreContext(
        runtime=runtime,
        include_date=(
            include_date if include_date is not None else sims.title < _TITLE_CERTAINTY_MIN
        ),
    )
    return _score_with_context(ref, dl, sims, context)


def _score_with_context(
    ref: "_AlignmentCandidate",
    dl: "_AlignmentCandidate",
    sims: "_Sims",
    context: _ScoreContext,
) -> float:
    base = _weighted_base_score(ref, dl, sims, context)
    containment = _containment_bonus(ref, dl, context)
    id_bonus = context.runtime.config.weights.id * _id_similarity(ref.episode, dl.episode)
    return min(1.0, base + id_bonus + containment)


def _weighted_base_score(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    context: _ScoreContext,
) -> float:
    runtime = context.runtime
    weights = runtime.config.weights
    weighted_sum = weights.title * sims.title
    total_weight = weights.title
    if _has_description_signal(ref, dl):
        weighted_sum += weights.description * sims.desc
        total_weight += weights.description
    if context.include_date and _has_date_signal(ref, dl):
        weighted_sum += weights.date * sim_date(
            ref.episode.pub_date,
            dl.episode.pub_date,
            runtime.config.date_score_tiers,
        )
        total_weight += weights.date
    return weighted_sum / total_weight


def _containment_bonus(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    context: _ScoreContext,
) -> float:
    anchor_tokens = AnchorTokens.from_titles(ref.title, dl.title, context.runtime.stopwords)
    has_containment = context.include_date and anchor_tokens.containment
    return _CONTAINMENT_BONUS if has_containment else 0.0


def _alignment_score(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    runtime: _AlignmentRuntime,
) -> float:
    """Metadata-aware similarity score with ID as a small bonus."""
    if _should_reject_alignment(ref, dl, sims, runtime):
        return 0.0
    if sims.title >= _TITLE_CERTAINTY_MIN:
        return _score_high_certainty(ref, dl, sims, runtime)
    return _score_low_certainty(ref, dl, sims, runtime)


def _should_reject_alignment(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    runtime: _AlignmentRuntime,
) -> bool:
    if _has_structured_number_mismatch(ref.title, dl.title):
        return True
    return _should_reject_weak_anchor_match(ref, dl, sims, runtime)


def _score_high_certainty(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    runtime: _AlignmentRuntime,
) -> float:
    return _score_with_context(ref, dl, sims, _ScoreContext(runtime=runtime, include_date=False))


def _score_low_certainty(
    ref: _AlignmentCandidate,
    dl: _AlignmentCandidate,
    sims: _Sims,
    runtime: _AlignmentRuntime,
) -> float:
    s_id = _id_similarity(ref.episode, dl.episode)
    has_desc = _has_description_signal(ref, dl)
    if _is_sparse_title(s_id, has_desc, sims.title, runtime.config.sparse_title_min):
        return 0.0
    if _should_reject_metadata_subset_rescue(ref, dl, sims, runtime):
        return 0.0
    return _score_with_context(ref, dl, sims, _ScoreContext(runtime=runtime, include_date=True))


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


def _score_alignment_candidates(state: _AlignmentState) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(state.refs):
        for d_idx, dl in enumerate(state.dls):
            sims = _Sims(
                float(state.title_matrix[r_idx][d_idx]),
                float(state.description_matrix[r_idx][d_idx]),
            )
            scores[(r_idx, d_idx)] = _alignment_score(
                ref,
                dl,
                sims,
                state.runtime,
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

    title_matrix, description_matrix = _build_similarity_matrices(
        ref_candidates,
        dl_candidates,
        request.similarity,
    )
    return _score_alignment_candidates(
        _AlignmentState(
            refs=ref_candidates,
            dls=dl_candidates,
            title_matrix=title_matrix,
            description_matrix=description_matrix,
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


def _select_matches_from_scores(
    scores: dict[tuple[int, int], float],
    match_tolerance: float,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()

    for (r_idx, d_idx), _score in _sorted_pairs_above_tolerance(scores, match_tolerance):
        _append_match_if_unused((r_idx, d_idx), matches, used_refs, used_dls)

    return matches


def align_episodes_with_scores(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    *,
    show: str = "",
    alignment: AlignmentConfig | None = None,
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
    """Return selected matches together with the full pairwise score map."""
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
    return _select_matches_from_scores(scores, resolved_alignment.match_tolerance), scores


@profile
def align_episodes_impl(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
    alignment: AlignmentConfig | None = None,
) -> list[tuple[int, int]]:
    """Core greedy aligner implementation (internal)."""
    matches, _scores = align_episodes_with_scores(
        references,
        downloads,
        show=show,
        alignment=alignment,
    )
    return matches


def align_episodes(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    show: str = "",
    alignment: "AlignmentConfig | None" = None,
) -> list[tuple[int, int]]:
    """Public alignment entrypoint.

    Kept as a stable wrapper for callers while using the internal implementation
    directly.
    """
    return align_episodes_impl(references, downloads, show, alignment)


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
