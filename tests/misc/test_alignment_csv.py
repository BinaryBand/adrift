"""CSV-backed alignment tests that mirror live align_episodes behavior."""

import csv
import os
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from src.catalog import align_episodes
from src.models.metadata import RssEpisode

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "resources" / "alignment"


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _episode_from_row(row: dict[str, str]) -> RssEpisode:
    return RssEpisode(
        id=row["id"],
        title=row["title"],
        author="",
        content=row["content"],
        description=row["description"] or None,
        pub_date=_parse_datetime(row["pub_date"]),
    )


def _load_episode_rows(filename: str, index_field: str) -> dict[str, list[RssEpisode]]:
    grouped: dict[str, list[tuple[int, RssEpisode]]] = {}
    with open(FIXTURE_DIR / filename, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row["scenario"]
            idx = int(row[index_field])
            grouped.setdefault(scenario, []).append((idx, _episode_from_row(row)))

    episodes_by_scenario: dict[str, list[RssEpisode]] = {}
    for scenario, entries in grouped.items():
        ordered = [episode for _, episode in sorted(entries, key=lambda it: it[0])]
        episodes_by_scenario[scenario] = ordered
    return episodes_by_scenario


def _load_expected_pairs() -> dict[str, list[tuple[int, int]]]:
    grouped: dict[str, list[tuple[int, int]]] = {}
    with open(FIXTURE_DIR / "expected_pairs.csv", "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row["scenario"]
            pair = (int(row["ref_idx"]), int(row["dl_idx"]))
            grouped.setdefault(scenario, []).append(pair)
    for scenario in grouped:
        grouped[scenario].sort()
    return grouped


def _load_scenarios() -> dict[
    str, tuple[list[RssEpisode], list[RssEpisode], list[tuple[int, int]]]
]:
    refs = _load_episode_rows("references.csv", "ref_idx")
    dls = _load_episode_rows("downloads.csv", "dl_idx")
    expected = _load_expected_pairs()

    scenario_names = sorted(set(refs) | set(dls) | set(expected))
    scenarios: dict[str, tuple[list[RssEpisode], list[RssEpisode], list[tuple[int, int]]]] = {}
    for name in scenario_names:
        scenarios[name] = (
            refs.get(name, []),
            dls.get(name, []),
            expected.get(name, []),
        )
    return scenarios


class TestAlignmentCsvFixtures(unittest.TestCase):
    def test_alignment_pairs_match_expected_from_csv(self):
        scenarios = _load_scenarios()
        self.assertGreater(len(scenarios), 0, "CSV scenarios should not be empty")

        for name, (refs, dls, expected_pairs) in scenarios.items():
            with self.subTest(scenario=name):
                actual_pairs = align_episodes(refs, dls, "Financial Audit")
                self.assertEqual(sorted(actual_pairs), sorted(expected_pairs))

    def test_financial_audit_sparse_vs_enriched_behavior(self):
        scenarios = _load_scenarios()

        sparse_refs, sparse_dls, _ = scenarios["financial_audit_sparse_mismatch"]
        enriched_refs, enriched_dls, _ = scenarios["financial_audit_enriched_match"]

        self.assertEqual(align_episodes(sparse_refs, sparse_dls, "Financial Audit"), [(0, 0)])
        self.assertEqual(align_episodes(enriched_refs, enriched_dls, "Financial Audit"), [(0, 0)])


if __name__ == "__main__":
    unittest.main()
