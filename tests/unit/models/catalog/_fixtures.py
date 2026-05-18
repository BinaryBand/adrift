"""Shared fixtures for weighted-case alignment tests."""

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adrift.models import AlignmentConfig, RssEpisode
from adrift.services.catalog import align_episodes_impl


def dt(year: int, month: int, day: int) -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime(year, month, day, tzinfo=timezone.utc)


def ep(
    id: str = "ep1",
    title: str = "Episode 1",
    description: str = "",
    pub_date: datetime | None = None,
    content: str = "https://example.com/ep1.mp3",
    image: str | None = None,
) -> RssEpisode:
    """Return a minimal RssEpisode for use in alignment tests."""
    return RssEpisode(
        id=id,
        title=title,
        author="",
        content=content,
        description=description,
        pub_date=pub_date,
        image=image,
    )


@dataclass(frozen=True)
class WeightedCase:
    scenario: str
    should_match: bool
    reference_id: str
    download_id: str
    reference_title: str
    download_title: str
    reference_description: str
    download_description: str
    reference_pub_date: datetime | None
    download_pub_date: datetime | None
    reason: str


def parse_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value.strip() else None


def load_weighted_cases(csv_path: Path) -> list[WeightedCase]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [
            WeightedCase(
                scenario=row["scenario"].strip(),
                should_match=row["label"].strip().lower() in ("1", "true", "t", "yes"),
                reference_id=row["reference_id"].strip(),
                download_id=row["download_id"].strip(),
                reference_title=row["reference_title"].strip(),
                download_title=row["download_title"].strip(),
                reference_description=row["reference_description"].strip(),
                download_description=row["download_description"].strip(),
                reference_pub_date=parse_datetime(row["reference_pub_date"]),
                download_pub_date=parse_datetime(row["download_pub_date"]),
                reason=row["reason"].strip(),
            )
            for row in reader
        ]


def make_episode(
    episode_id: str,
    title: str,
    description: str,
    pub_date: datetime | None,
) -> RssEpisode:
    return RssEpisode(
        id=episode_id,
        title=title,
        author="",
        content=f"https://example.com/{episode_id}.mp3",
        description=description,
        pub_date=pub_date,
        image=None,
    )


def run_weighted_case_test(
    csv_path: Path,
    show_name: str,
    config: AlignmentConfig | None = None,
) -> None:
    """Load and run all weighted alignment cases from *csv_path*."""
    cases = load_weighted_cases(csv_path)
    assert len(cases) > 0, "Weighted-case CSV should not be empty"

    mismatches: list[str] = []
    for case in cases:
        ref = make_episode(
            case.reference_id,
            case.reference_title,
            case.reference_description,
            case.reference_pub_date,
        )
        dl = make_episode(
            case.download_id,
            case.download_title,
            case.download_description,
            case.download_pub_date,
        )
        args: list[Any] = [[ref], [dl], show_name]
        if config is not None:
            args.append(config)
        matched = align_episodes_impl(*args) == [(0, 0)]
        if matched != case.should_match:
            mismatches.append(
                f"scenario={case.scenario} expected={case.should_match} got={matched} "
                f"reason={case.reason}"
            )

    assert mismatches == [], "\n".join(mismatches)
