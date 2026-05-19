from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from rapidfuzz import fuzz

from adrift.models import AlignmentConfig, RssEpisode
from adrift.utils.text import normalize_text
from adrift.utils.title_normalization import normalize_title

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
_NUMBERED_MARKER_PATTERNS = (
    re.compile(r"\\blistener\\s+tales(?:\\s+episode)?\\s+(\\d+)\\b"),
    re.compile(r"\\bpart\\s+(\\d+)\\b"),
    re.compile(r"\\b(?:volume|vol\\.?)\\s*(\\d+)\\b"),
    re.compile(r"\\bepisode\\s+(\\d+)\\b"),
)
_TITLE_CERTAINTY_MIN = 0.97
_METADATA_RESCUE_SUBSET_SIM_MIN = 0.78
_CONTAINMENT_BONUS = 0.08
_DEFAULT_ALIGNMENT = AlignmentConfig()


@dataclass(frozen=True)
class _Markers:
    listener_tales: int | None
    part: int | None
    volume: int | None
    episode: int | None


@dataclass(frozen=True)
class _Candidate:
    episode: RssEpisode
    title: str
    description: str
    anchor_tokens: frozenset[str]
    markers: _Markers


class OptimizedScoredAlignmentAdapter:
    """Scored alignment adapter with precomputed candidate metadata."""

    def align_with_scores(
        self,
        references: list[RssEpisode],
        downloads: list[RssEpisode],
        **kwargs: object,
    ) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
        show = str(kwargs.get("show", ""))
        raw_alignment = kwargs.get("alignment")
        alignment = (
            raw_alignment if isinstance(raw_alignment, AlignmentConfig) else _DEFAULT_ALIGNMENT
        )
        stopwords = _alignment_stopwords(alignment)
        refs = _build_candidates(references, show, stopwords)
        dls = _build_candidates(downloads, show, stopwords)
        title_matrix = _cdist_similarity(_titles(refs), _titles(dls))
        desc_matrix = _description_matrix(refs, dls)
        scores = _score_matrix(refs, dls, title_matrix, desc_matrix, alignment)
        pairs = _select_matches(scores, alignment.match_tolerance)
        return pairs, scores


def _titles(candidates: list[_Candidate]) -> list[str]:
    return [candidate.title for candidate in candidates]


def _alignment_stopwords(alignment: AlignmentConfig) -> frozenset[str]:
    extras = {item.strip().lower() for item in alignment.extra_stopwords if item.strip()}
    return frozenset(_BASE_ANCHOR_STOPWORDS | extras)


def _normalized_title(show: str, episode: RssEpisode) -> str:
    title = normalize_title(show, episode.title) if show else episode.title
    return normalize_text(title)


def _build_candidates(
    episodes: list[RssEpisode],
    show: str,
    stopwords: frozenset[str],
) -> list[_Candidate]:
    return [
        _Candidate(
            episode=episode,
            title=_normalized_title(show, episode),
            description=normalize_text(episode.description or ""),
            anchor_tokens=frozenset(
                token
                for token in _normalized_title(show, episode).split()
                if token not in stopwords
            ),
            markers=_extract_markers(_normalized_title(show, episode)),
        )
        for episode in episodes
    ]


def _extract_markers(title: str) -> _Markers:
    values = [_extract_int(pattern, title) for pattern in _NUMBERED_MARKER_PATTERNS]
    return _Markers(*values)


def _extract_int(pattern: re.Pattern[str], title: str) -> int | None:
    match = pattern.search(title)
    return int(match.group(1)) if match else None


def _cdist_similarity(a: list[str], b: list[str]) -> list[list[float]]:
    from rapidfuzz import process as rapidfuzz_process

    if not a or not b:
        return [[0.0 for _ in b] for _ in a]
    cdist = cast(Any, rapidfuzz_process).cdist
    ratio_scores = cdist(a, b, scorer=fuzz.ratio, workers=-1) / 100.0
    token_sort_scores = cdist(a, b, scorer=fuzz.token_sort_ratio, workers=-1) / 100.0
    token_set_scores = cdist(a, b, scorer=fuzz.token_set_ratio, workers=-1) / 100.0
    return (ratio_scores * 0.4 + token_sort_scores * 0.3 + token_set_scores * 0.3).tolist()


def _description_matrix(refs: list[_Candidate], dls: list[_Candidate]) -> list[list[float]]:
    matrix = [[0.0 for _ in dls] for _ in refs]
    ref_idx = [index for index, candidate in enumerate(refs) if candidate.description]
    dl_idx = [index for index, candidate in enumerate(dls) if candidate.description]
    if not ref_idx or not dl_idx:
        return matrix
    sub_scores = _cdist_similarity(
        [refs[index].description for index in ref_idx],
        [dls[index].description for index in dl_idx],
    )
    _apply_submatrix(matrix, sub_scores, ref_idx, dl_idx)
    return matrix


def _apply_submatrix(
    matrix: list[list[float]],
    sub_scores: list[list[float]],
    ref_idx: list[int],
    dl_idx: list[int],
) -> None:
    for sub_r, ref_index in enumerate(ref_idx):
        for sub_d, dl_index in enumerate(dl_idx):
            matrix[ref_index][dl_index] = float(sub_scores[sub_r][sub_d])


def _score_matrix(
    refs: list[_Candidate],
    dls: list[_Candidate],
    title_matrix: list[list[float]],
    desc_matrix: list[list[float]],
    alignment: AlignmentConfig,
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, ref in enumerate(refs):
        for d_idx, dl in enumerate(dls):
            title_score = float(title_matrix[r_idx][d_idx])
            desc_score = float(desc_matrix[r_idx][d_idx])
            scores[(r_idx, d_idx)] = _pair_score(ref, dl, title_score, desc_score, alignment)
    return scores


def _pair_score(
    ref: _Candidate,
    dl: _Candidate,
    title_score: float,
    desc_score: float,
    alignment: AlignmentConfig,
) -> float:
    if _has_marker_mismatch(ref.markers, dl.markers) or _weak_anchor_reject(ref, dl, title_score):
        return 0.0
    include_date = title_score < _TITLE_CERTAINTY_MIN
    if include_date and _subset_rescue_reject(ref, dl, title_score):
        return 0.0
    return _weighted_score(ref, dl, title_score, desc_score, alignment, include_date)


def _has_marker_mismatch(ref: _Markers, dl: _Markers) -> bool:
    return any(
        r is not None and d is not None and r != d
        for r, d in (
            (ref.listener_tales, dl.listener_tales),
            (ref.part, dl.part),
            (ref.volume, dl.volume),
            (ref.episode, dl.episode),
        )
    )


def _weak_anchor_reject(ref: _Candidate, dl: _Candidate, title_score: float) -> bool:
    return not (ref.anchor_tokens & dl.anchor_tokens) and title_score < 0.75


def _subset_rescue_reject(ref: _Candidate, dl: _Candidate, title_score: float) -> bool:
    if not ref.description or not dl.description:
        return False
    if ref.episode.pub_date is None or dl.episode.pub_date is None:
        return False
    extra = _subset_extra_tokens(ref.anchor_tokens, dl.anchor_tokens)
    if not extra or len(extra) != 1:
        return False
    if not _has_discriminating_extra_token(extra):
        return False
    return _METADATA_RESCUE_SUBSET_SIM_MIN <= title_score < _TITLE_CERTAINTY_MIN


def _subset_extra_tokens(ref: frozenset[str], dl: frozenset[str]) -> frozenset[str] | None:
    if not ref or not dl:
        return None
    if ref.issubset(dl):
        return frozenset(dl - ref)
    if dl.issubset(ref):
        return frozenset(ref - dl)
    return None


def _has_discriminating_extra_token(tokens: frozenset[str]) -> bool:
    return any(
        any(ch.isalpha() for ch in token) and token not in _TEMPORAL_METADATA_TOKENS
        for token in tokens
    )


def _weighted_score(
    ref: _Candidate,
    dl: _Candidate,
    title_score: float,
    desc_score: float,
    alignment: AlignmentConfig,
    include_date: bool,
) -> float:
    weights = alignment.weights
    weighted_sum = weights.title * title_score
    total_weight = weights.title
    if ref.description and dl.description:
        weighted_sum += weights.description * desc_score
        total_weight += weights.description
    if include_date and ref.episode.pub_date and dl.episode.pub_date:
        weighted_sum += weights.date * _date_similarity(
            ref.episode.pub_date,
            dl.episode.pub_date,
            alignment.date_score_tiers,
        )
        total_weight += weights.date
    base = weighted_sum / total_weight
    return min(1.0, base + _containment_bonus(ref, dl, include_date))


def _containment_bonus(ref: _Candidate, dl: _Candidate, include_date: bool) -> float:
    if not include_date:
        return 0.0
    if not ref.anchor_tokens or not dl.anchor_tokens:
        return 0.0
    if len(ref.anchor_tokens) <= len(dl.anchor_tokens):
        contained = len(ref.anchor_tokens) >= 2 and ref.anchor_tokens.issubset(dl.anchor_tokens)
        return _CONTAINMENT_BONUS if contained else 0.0
    contained = len(dl.anchor_tokens) >= 2 and dl.anchor_tokens.issubset(ref.anchor_tokens)
    return _CONTAINMENT_BONUS if contained else 0.0


def _date_similarity(
    ref_date: datetime,
    dl_date: datetime,
    tiers: list[tuple[int, float]],
) -> float:
    ref_aligned, dl_aligned = _align_datetime_pair(ref_date, dl_date)
    delta_days = abs((ref_aligned - dl_aligned).days)
    for max_days, score in tiers:
        if delta_days <= max_days:
            return score
    return 0.0


def _align_datetime_pair(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    if a.tzinfo is not None and b.tzinfo is None:
        return a, b.replace(tzinfo=a.tzinfo)
    if a.tzinfo is None and b.tzinfo is not None:
        return a.replace(tzinfo=b.tzinfo), b
    return a, b


def _select_matches(
    scores: dict[tuple[int, int], float],
    tolerance: float,
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_dls: set[int] = set()
    for (r_idx, d_idx), score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        if score < tolerance or r_idx in used_refs or d_idx in used_dls:
            continue
        matches.append((r_idx, d_idx))
        used_refs.add(r_idx)
        used_dls.add(d_idx)
    return matches


__all__ = ["OptimizedScoredAlignmentAdapter"]
