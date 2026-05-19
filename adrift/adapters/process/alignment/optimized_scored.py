from __future__ import annotations

from typing import cast

from rapidfuzz import fuzz

from adrift.models import AlignmentConfig, RssEpisode
from adrift.utils.text import normalize_text
from adrift.utils.title_normalization import normalize_title

_DEFAULT_ALIGNMENT = AlignmentConfig()


class OptimizedScoredAlignmentAdapter:
    """Fast, lightweight scored aligner for backend A/B testing."""

    def align_with_scores(
        self,
        *args: object,
        **kwargs: object,
    ) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
        references = cast(list[RssEpisode], args[0])
        downloads = cast(list[RssEpisode], args[1])
        show = str(kwargs.get("show", ""))
        alignment = _resolve_alignment(kwargs.get("alignment"))
        ref_titles = _normalized_titles(references, show)
        dl_titles = _normalized_titles(downloads, show)
        ref_desc = _normalized_descriptions(references)
        dl_desc = _normalized_descriptions(downloads)

        scores = _score_pairs(references, downloads, ref_titles, dl_titles, ref_desc, dl_desc)
        pairs = _select_pairs(scores, alignment.match_tolerance)
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
) -> dict[tuple[int, int], float]:
    scores: dict[tuple[int, int], float] = {}
    for r_idx, reference in enumerate(references):
        for d_idx, download in enumerate(downloads):
            title_score = _ratio(ref_titles[r_idx], dl_titles[d_idx])
            description_score = _ratio(ref_desc[r_idx], dl_desc[d_idx])
            id_score = 1.0 if reference.id and reference.id == download.id else 0.0
            scores[(r_idx, d_idx)] = (
                (title_score * 0.8) + (description_score * 0.1) + (id_score * 0.1)
            )
    return scores


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return fuzz.token_ratio(left, right) / 100.0


def _select_pairs(
    scores: dict[tuple[int, int], float],
    tolerance: float,
) -> list[tuple[int, int]]:
    used_refs: set[int] = set()
    used_downloads: set[int] = set()
    matches: list[tuple[int, int]] = []
    for pair, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        reference_index, download_index = pair
        if score < tolerance:
            continue
        if reference_index in used_refs or download_index in used_downloads:
            continue
        matches.append(pair)
        used_refs.add(reference_index)
        used_downloads.add(download_index)
    return matches


__all__ = ["OptimizedScoredAlignmentAdapter"]
