from __future__ import annotations

from typing import cast

from rapidfuzz import fuzz

from adrift.models import AlignmentConfig, RssEpisode
from adrift.utils.alignment_pairs import (
    AlignmentResult,
    AlignmentScores,
    score_alignment_pairs,
    select_alignment_pairs,
)
from adrift.utils.text import normalize_text
from adrift.utils.title_normalization import normalize_title

_DEFAULT_ALIGNMENT = AlignmentConfig()


class OptimizedScoredAlignmentAdapter:
    """Fast, lightweight scored aligner for backend A/B testing."""

    def align_with_scores(
        self,
        *args: object,
        **kwargs: object,
    ) -> AlignmentResult:
        references = cast(list[RssEpisode], args[0])
        downloads = cast(list[RssEpisode], args[1])
        show = str(kwargs.get("show", ""))
        alignment = _resolve_alignment(kwargs.get("alignment"))
        ref_titles = _normalized_titles(references, show)
        dl_titles = _normalized_titles(downloads, show)
        ref_desc = _normalized_descriptions(references)
        dl_desc = _normalized_descriptions(downloads)

        scores = _score_pairs(references, downloads, ref_titles, dl_titles, ref_desc, dl_desc)
        pairs = select_alignment_pairs(scores, alignment.match_tolerance)
        return pairs, scores


def _resolve_alignment(raw_alignment: object) -> AlignmentConfig:
    return raw_alignment if isinstance(raw_alignment, AlignmentConfig) else _DEFAULT_ALIGNMENT


def _normalized_titles(episodes: list[RssEpisode], show: str) -> list[str]:
    if not show:
        return [normalize_text(episode.title) for episode in episodes]
    return [normalize_text(normalize_title(show, episode.title)) for episode in episodes]


def _normalized_descriptions(episodes: list[RssEpisode]) -> list[str]:
    return [normalize_text(episode.description or "") for episode in episodes]


def _score_pairs(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    ref_titles: list[str],
    dl_titles: list[str],
    ref_desc: list[str],
    dl_desc: list[str],
) -> AlignmentScores:
    def _score_pair(reference_index: int, download_index: int) -> float:
        reference = references[reference_index]
        download = downloads[download_index]
        title_score = _ratio(ref_titles[reference_index], dl_titles[download_index])
        description_score = _ratio(ref_desc[reference_index], dl_desc[download_index])
        id_score = 1.0 if reference.id and reference.id == download.id else 0.0
        return (title_score * 0.8) + (description_score * 0.1) + (id_score * 0.1)

    return score_alignment_pairs(range(len(references)), range(len(downloads)), _score_pair)


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return fuzz.token_ratio(left, right) / 100.0


__all__ = ["OptimizedScoredAlignmentAdapter"]
