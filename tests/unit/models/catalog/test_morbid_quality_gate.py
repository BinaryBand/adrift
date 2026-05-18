"""Strict quality gate for Morbid alignment hard cases.

This pack intentionally mixes known-good matches with hard negatives from
audit output so matcher tuning can improve false-positive behavior without
regressing obvious positives.
"""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from adrift.models import AlignmentConfig, RssEpisode
from adrift.services.catalog import align_episodes_impl

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])
_HARD_PACK = (
    Path(__file__).resolve().parents[3] / "resources" / "alignment" / "morbid_hard_pack.csv"
)
_STRICT_MIN_PRECISION = 0.95
_STRICT_MAX_FALSE_POSITIVE_RATE = 0.05


@dataclass(frozen=True)
class _HardCase:
    should_match: bool
    reference_title: str
    download_title: str
    category: str
    reason: str


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _ep(
    id: str,
    title: str,
    description: str = "",
    pub_date: datetime | None = None,
) -> RssEpisode:
    return RssEpisode(
        id=id,
        title=title,
        author="",
        content=f"https://example.com/{id}.mp3",
        description=description,
        pub_date=pub_date,
        image=None,
    )


def _load_hard_cases() -> list[_HardCase]:
    with _HARD_PACK.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [
            _HardCase(
                should_match=row["label"].strip().lower() in ("1", "true", "t", "yes"),
                reference_title=row["reference_title"].strip(),
                download_title=row["download_title"].strip(),
                category=row["category"].strip(),
                reason=row["reason"].strip(),
            )
            for row in reader
        ]


def _predict_match(case: _HardCase, idx: int) -> bool:
    pub = _dt(2024, 1, 1) if case.should_match else None
    desc = "quality gate positive" if case.should_match else ""
    ref = _ep(id=f"hard-r-{idx}", title=case.reference_title, pub_date=pub, description=desc)
    dl = _ep(id=f"hard-d-{idx}", title=case.download_title, pub_date=pub, description=desc)
    return align_episodes_impl([ref], [dl], "Morbid", _MORBID_ALIGNMENT) == [(0, 0)]


def _scores(cases: list[_HardCase]) -> tuple[float, float]:
    tp = fp = positive_count = 0
    negative_count = 0
    for idx, case in enumerate(cases):
        matched = _predict_match(case, idx)
        if matched:
            positive_count += 1
            if case.should_match:
                tp += 1
            else:
                fp += 1
        if not case.should_match:
            negative_count += 1

    precision = tp / positive_count if positive_count else 1.0
    false_positive_rate = fp / negative_count if negative_count else 0.0
    return precision, false_positive_rate


class TestMorbidQualityGate:
    def test_hard_pack_row_expectations(self) -> None:
        cases = _load_hard_cases()
        assert len(cases) > 0, "Hard-pack CSV should not be empty"

        mismatches: list[str] = []
        for idx, case in enumerate(cases):
            matched = _predict_match(case, idx)
            if matched != case.should_match:
                mismatches.append(
                    f"row={idx} category={case.category} expected={case.should_match} "
                    f"got={matched} reason={case.reason} ref={case.reference_title!r} "
                    f"dl={case.download_title!r}"
                )

        assert mismatches == [], "\n".join(mismatches)

    def test_hard_pack_strict_precision_gate(self) -> None:
        precision, false_positive_rate = _scores(_load_hard_cases())
        assert precision >= _STRICT_MIN_PRECISION
        assert false_positive_rate <= _STRICT_MAX_FALSE_POSITIVE_RATE


@pytest.mark.slow
def test_hard_pack_case_balance() -> None:
    cases = _load_hard_cases()
    positives = sum(1 for case in cases if case.should_match)
    negatives = sum(1 for case in cases if not case.should_match)
    assert positives == 5
    assert negatives == 7
