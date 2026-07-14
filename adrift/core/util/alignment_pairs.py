from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

AlignmentPair = tuple[int, int]
AlignmentPairs = list[AlignmentPair]
AlignmentScores = dict[AlignmentPair, float]
AlignmentResult = tuple[AlignmentPairs, AlignmentScores]

_L = TypeVar("_L")
_R = TypeVar("_R")


def score_alignment_pairs(
    left_items: Sequence[_L],
    right_items: Sequence[_R],
    score_pair: Callable[[_L, _R], float],
) -> AlignmentScores:
    scores: AlignmentScores = {}
    for left_index, left_item in enumerate(left_items):
        for right_index, right_item in enumerate(right_items):
            scores[(left_index, right_index)] = score_pair(left_item, right_item)
    return scores


def select_alignment_pairs(
    scores: AlignmentScores,
    tolerance: float,
) -> AlignmentPairs:
    used_left: set[int] = set()
    used_right: set[int] = set()
    selected: AlignmentPairs = []
    for pair, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        left_index, right_index = pair
        if score < tolerance:
            continue
        if left_index in used_left or right_index in used_right:
            continue
        selected.append(pair)
        used_left.add(left_index)
        used_right.add(right_index)
    return selected


__all__ = [
    "AlignmentPair",
    "AlignmentPairs",
    "AlignmentResult",
    "AlignmentScores",
    "score_alignment_pairs",
    "select_alignment_pairs",
]
