import csv
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from adrift.models import AlignmentConfig, RssEpisode
from adrift.models.catalog import align_episodes_impl

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])
_WEIGHTED_CASES = (
    Path(__file__).resolve().parents[1] / "resources" / "alignment" / "morbid_weighted_cases.csv"
)


@dataclass(frozen=True)
class _WeightedCase:
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


def _parse_datetime(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value.strip() else None


def _load_cases() -> list[_WeightedCase]:
    with _WEIGHTED_CASES.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [
            _WeightedCase(
                scenario=row["scenario"].strip(),
                should_match=row["label"].strip().lower() in ("1", "true", "t", "yes"),
                reference_id=row["reference_id"].strip(),
                download_id=row["download_id"].strip(),
                reference_title=row["reference_title"].strip(),
                download_title=row["download_title"].strip(),
                reference_description=row["reference_description"].strip(),
                download_description=row["download_description"].strip(),
                reference_pub_date=_parse_datetime(row["reference_pub_date"]),
                download_pub_date=_parse_datetime(row["download_pub_date"]),
                reason=row["reason"].strip(),
            )
            for row in reader
        ]


def _episode(
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


def test_morbid_weighted_cases() -> None:
    cases = _load_cases()
    assert len(cases) > 0, "Weighted-case CSV should not be empty"

    mismatches: list[str] = []
    for case in cases:
        ref = _episode(
            case.reference_id,
            case.reference_title,
            case.reference_description,
            case.reference_pub_date,
        )
        dl = _episode(
            case.download_id,
            case.download_title,
            case.download_description,
            case.download_pub_date,
        )
        matched = align_episodes_impl([ref], [dl], "Morbid", _MORBID_ALIGNMENT) == [(0, 0)]
        if matched != case.should_match:
            mismatches.append(
                f"scenario={case.scenario} expected={case.should_match} got={matched} "
                f"reason={case.reason}"
            )

    assert mismatches == [], "\n".join(mismatches)
