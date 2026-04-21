# pyright: reportPrivateUsage=false
from dataclasses import dataclass

from src.app_common import MATCH_TOLERANCE
from src.models import MatchCandidateTrace, ReferenceMatchTrace, RssEpisode

from .alignment import _build_alignment_scores

_MATCH_DEBUG_CANDIDATE_LIMIT = 3


@dataclass(frozen=True)
class _MatchTraceContext:
    scores: dict[tuple[int, int], float]
    matched_by_reference: dict[int, int]
    matched_by_download: dict[int, int]
    pair_set: set[tuple[int, int]]


_TraceContext = _MatchTraceContext
_RefTrace = ReferenceMatchTrace


def _matched_elsewhere(
    matched_index: int | None,
    expected_index: int,
) -> bool:
    return matched_index not in (None, expected_index)


def _candidate_reason(
    reference_index: int,
    download_index: int,
    score: float,
    context: _MatchTraceContext,
) -> str:
    if (reference_index, download_index) in context.pair_set:
        return "matched"
    if score < MATCH_TOLERANCE:
        return "below_threshold"
    if _matched_elsewhere(
        context.matched_by_download.get(download_index),
        reference_index,
    ):
        return "download_matched_elsewhere"
    if _matched_elsewhere(
        context.matched_by_reference.get(reference_index),
        download_index,
    ):
        return "reference_matched_elsewhere"
    return "not_selected"


def _candidate_indices_for_reference(
    reference_index: int,
    download_count: int,
    scores: dict[tuple[int, int], float],
    matched_download_index: int | None,
) -> list[int]:
    ranked = sorted(
        range(download_count),
        key=lambda download_index: scores[(reference_index, download_index)],
        reverse=True,
    )
    chosen = ranked[:_MATCH_DEBUG_CANDIDATE_LIMIT]
    if matched_download_index is not None and matched_download_index not in chosen:
        chosen.append(matched_download_index)
    return chosen


def _match_candidate_trace(
    reference_index: int,
    download_index: int,
    context: _MatchTraceContext,
) -> MatchCandidateTrace:
    score = context.scores[(reference_index, download_index)]
    return MatchCandidateTrace(
        download_index=download_index,
        score=score,
        reason=_candidate_reason(reference_index, download_index, score, context),
    )


def _match_candidate_traces(
    reference_index: int,
    candidate_indices: list[int],
    context: _MatchTraceContext,
) -> list[MatchCandidateTrace]:
    return [
        _match_candidate_trace(reference_index, download_index, context)
        for download_index in candidate_indices
    ]


def _matched_score(
    reference_index: int,
    matched_download_index: int | None,
    scores: dict[tuple[int, int], float],
) -> float | None:
    if matched_download_index is None:
        return None
    return scores[(reference_index, matched_download_index)]


def _reference_match_trace(
    reference_index: int, download_count: int, context: _TraceContext
) -> _RefTrace:
    matched_download_index = context.matched_by_reference.get(reference_index)
    candidates = _match_candidate_traces(
        reference_index,
        _candidate_indices_for_reference(
            reference_index,
            download_count,
            context.scores,
            matched_download_index,
        ),
        context,
    )
    return ReferenceMatchTrace(
        reference_index=reference_index,
        matched_download_index=matched_download_index,
        matched_score=_matched_score(
            reference_index,
            matched_download_index,
            context.scores,
        ),
        candidates=candidates,
    )


def _empty_match_traces(references: list[RssEpisode]) -> list[ReferenceMatchTrace]:
    return [ReferenceMatchTrace(reference_index=index) for index, _ in enumerate(references)]


def _match_trace_context(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    pairs: list[tuple[int, int]],
    show: str,
) -> _MatchTraceContext:
    return _MatchTraceContext(
        scores=_build_alignment_scores(references, downloads, show),
        matched_by_reference={
            reference_index: download_index for reference_index, download_index in pairs
        },
        matched_by_download={
            download_index: reference_index for reference_index, download_index in pairs
        },
        pair_set=set(pairs),
    )


def _build_match_traces(
    references: list[RssEpisode],
    downloads: list[RssEpisode],
    pairs: list[tuple[int, int]],
    show: str,
) -> list[ReferenceMatchTrace]:
    if not references:
        return []
    if not downloads:
        return _empty_match_traces(references)

    context = _match_trace_context(references, downloads, pairs, show)
    return [
        _reference_match_trace(reference_index, len(downloads), context)
        for reference_index, _ in enumerate(references)
    ]


__all__ = ["_build_match_traces"]
