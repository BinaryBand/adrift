from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, cast

from adrift.models import AlignmentConfig, RssEpisode
from adrift.models.ports import ScoredAlignmentPort


def _resolve_tolerance(kwargs: dict[str, object]) -> float:
    alignment = kwargs.get("alignment")
    if isinstance(alignment, AlignmentConfig):
        return float(alignment.match_tolerance)
    return float(AlignmentConfig().match_tolerance)


def _episode_rows(items: list[RssEpisode]) -> list[tuple[str, str]]:
    return [((item.title or ""), (item.description or "")) for item in items]


def _to_score_map(score_entries: Any) -> dict[tuple[int, int], float]:
    return {(int(r_idx), int(d_idx)): float(score) for r_idx, d_idx, score in score_entries}


def _to_pair_list(pairs: Any) -> list[tuple[int, int]]:
    return [(int(r_idx), int(d_idx)) for r_idx, d_idx in pairs]


def _load_rust_align_with_scores() -> Any:
    rust_module = importlib.import_module("adrift_rust_align")
    return getattr(rust_module, "align_with_scores")


def _build_align_impl(rust_align_with_scores: Any) -> Any:
    def _align_with_scores_impl(
        *args: object,
        **kwargs: object,
    ) -> tuple[list[tuple[int, int]], dict[tuple[int, int], float]]:
        references = cast(list[RssEpisode], args[0])
        downloads = cast(list[RssEpisode], args[1])
        tolerance = _resolve_tolerance(kwargs)

        pairs, score_entries = rust_align_with_scores(
            _episode_rows(references),
            _episode_rows(downloads),
            tolerance,
        )
        return _to_pair_list(pairs), _to_score_map(score_entries)

    return _align_with_scores_impl


def build_rust_scored_alignment_port() -> ScoredAlignmentPort:
    """Return an adapter object that matches ScoredAlignmentPort."""
    rust_align_with_scores = _load_rust_align_with_scores()
    return cast(
        ScoredAlignmentPort,
        SimpleNamespace(align_with_scores=_build_align_impl(rust_align_with_scores)),
    )
