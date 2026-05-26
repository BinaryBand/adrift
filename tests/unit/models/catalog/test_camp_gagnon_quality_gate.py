"""Quality gate for Camp Gagnon alignment using reviewed CSV fixtures.

This test intentionally encodes current expectations:
- reviewed/confirmed rows should align
- rows marked false_positive should not align
"""

from __future__ import annotations

import csv
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pytest

from adrift.models import AlignmentConfig, RssEpisode
from adrift.services.app_common import load_podcasts_config
from adrift.services.catalog import align_episodes_impl

REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_TO_REF_CSV = REPO_ROOT / "docs" / ".dev" / "source_to_ref.csv"
FOR_REVIEW_CSV = REPO_ROOT / "docs" / ".dev" / "for_review.csv"
FIXED_PUB_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
# Current best-achieved floor with this scorer/config family is ~95%.
_MIN_CONFIRMED_POSITIVE_MATCH_RATE = 0.95

_FIXTURES_AVAILABLE = SOURCE_TO_REF_CSV.exists() and FOR_REVIEW_CSV.exists()
_skip_without_fixtures = pytest.mark.skipif(
    not _FIXTURES_AVAILABLE,
    reason="Local dev CSV fixtures not present (docs/.dev/); skipped in CI.",
)


def _camp_gagnon_alignment() -> AlignmentConfig:
    configs = load_podcasts_config([str(REPO_ROOT / "config" / "podcasts.toml")], True)
    for config in configs:
        if config.slug == "camp-gagnon":
            return config.alignment
    raise AssertionError("Camp Gagnon config not found in config/podcasts.toml")


def _episode(idx: int, title: str, description: str, *, role: str) -> RssEpisode:
    return RssEpisode(
        id=f"{role}-{idx}",
        title=title,
        author="",
        content=f"https://example.com/{role}-{idx}.mp3",
        description=description,
        pub_date=FIXED_PUB_DATE,
    )


def _pair_from_row(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    ref_title = row["reference_title"]
    dl_title = row["download_title"]
    return (
        row["source"],
        ref_title,
        dl_title,
        row.get("reference_description", "") or ref_title,
        row.get("download_description", "") or dl_title,
    )


def _load_confirmed_positive_pairs() -> list[tuple[str, str, str, str, str]]:
    """Return (source, ref_title, dl_title, ref_desc, dl_desc) for known positives."""
    pairs: list[tuple[str, str, str, str, str]] = []

    with SOURCE_TO_REF_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            pairs.append(_pair_from_row(row))

    with FOR_REVIEW_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("classification", "").strip().lower() != "false_positive":
                pairs.append(_pair_from_row(row))

    return pairs


def _load_false_positive_pairs() -> list[tuple[str, str, str, str, str]]:
    """Return (source, ref_title, dl_title, ref_desc, dl_desc) for false positives."""
    pairs: list[tuple[str, str, str, str, str]] = []
    with FOR_REVIEW_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("classification", "").strip().lower() == "false_positive":
                pairs.append(_pair_from_row(row))
    return pairs


class TestCampGagnonQualityGate(unittest.TestCase):
    @_skip_without_fixtures
    def test_confirmed_positive_pairs_should_match(self) -> None:
        alignment = _camp_gagnon_alignment()
        positive_pairs = _load_confirmed_positive_pairs()

        self.assertGreater(len(positive_pairs), 0, "Expected at least one positive pair")

        mismatches: list[str] = []
        matches = 0
        for idx, (source, ref_title, dl_title, ref_desc, dl_desc) in enumerate(positive_pairs):
            ref = _episode(idx, ref_title, ref_desc, role="ref")
            dl = _episode(idx, dl_title, dl_desc, role="dl")
            pairs = align_episodes_impl([ref], [dl], "Camp Gagnon", alignment)
            if pairs == [(0, 0)]:
                matches += 1
            else:
                mismatches.append(f"Expected match for {source}: {ref_title!r} <> {dl_title!r}")

        required_matches = math.ceil(len(positive_pairs) * _MIN_CONFIRMED_POSITIVE_MATCH_RATE)
        self.assertGreaterEqual(
            matches,
            required_matches,
            (
                f"Matched {matches}/{len(positive_pairs)} positives; "
                f"required at least {required_matches}."
            )
            + ("\nExamples:\n" + "\n".join(mismatches[:10]) if mismatches else ""),
        )

    @_skip_without_fixtures
    def test_false_positive_pairs_should_not_match(self) -> None:
        alignment = _camp_gagnon_alignment()
        false_positive_pairs = _load_false_positive_pairs()

        self.assertGreater(
            len(false_positive_pairs),
            0,
            "Expected at least one false_positive pair",
        )

        mismatches: list[str] = []
        for idx, (source, ref_title, dl_title, ref_desc, dl_desc) in enumerate(
            false_positive_pairs
        ):
            ref = _episode(idx, ref_title, ref_desc, role="fp-ref")
            dl = _episode(idx, dl_title, dl_desc, role="fp-dl")
            pairs = align_episodes_impl([ref], [dl], "Camp Gagnon", alignment)
            if pairs != []:
                mismatches.append(
                    f"Expected no match for false_positive {source}: {ref_title!r} <> {dl_title!r}"
                )

        self.assertEqual([], mismatches, "\n".join(mismatches))


if __name__ == "__main__":
    unittest.main()
