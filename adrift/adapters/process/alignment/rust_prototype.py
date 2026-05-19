from __future__ import annotations

from adrift.models.alignment_batch import AlignmentBatch, AlignmentEpisodeRecord
from adrift.utils.alignment_pairs import (
    AlignmentResult,
    AlignmentScores,
    score_alignment_pairs,
    select_alignment_pairs,
)


def align_batch(
    batch: AlignmentBatch,
) -> AlignmentResult:
    scores = _score_pairs(batch)
    return select_alignment_pairs(scores, batch.config.match_tolerance), scores


def _score_pairs(batch: AlignmentBatch) -> AlignmentScores:
    return score_alignment_pairs(batch.references, batch.downloads, _score_pair)


def _score_pair(reference: AlignmentEpisodeRecord, download: AlignmentEpisodeRecord) -> float:
    if reference.episode_id and reference.episode_id == download.episode_id:
        return 1.0
    if reference.normalized_title and reference.normalized_title == download.normalized_title:
        return 1.0
    return 0.0


__all__ = ["align_batch"]
