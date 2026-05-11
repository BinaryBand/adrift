import csv
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from src.catalog import align_episodes_impl
from src.models import AlignmentConfig, RssEpisode

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _ep(
    id: str = "ep1",
    title: str = "Episode 1",
    description: str = "",
    pub_date: datetime | None = None,
    content: str = "https://example.com/ep1.mp3",
    image: str | None = None,
) -> RssEpisode:
    return RssEpisode(
        id=id,
        title=title,
        author="",
        content=content,
        description=description,
        pub_date=pub_date,
        image=image,
    )


class TestMorbidBenchmark(unittest.TestCase):
    def test_benchmark_pairs(self):
        path = "tests/resources/alignment/morbid_benchmark.csv"
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader):
                label = row["label"].strip().lower()
                should_match = label in ("1", "true", "t", "yes")
                ref_title = row["reference_title"].strip()
                dl_title = row["download_title"].strip()

                # Provide a shared pub_date + non-empty description for positive cases
                pub = _dt(2024, 1, 1) if should_match else None
                desc = "benchmark match" if should_match else ""
                ref = _ep(id=f"r{idx}", title=ref_title, pub_date=pub, description=desc)
                dl = _ep(id=f"d{idx}", title=dl_title, pub_date=pub, description=desc)

                pairs = align_episodes_impl([ref], [dl], "Morbid", _MORBID_ALIGNMENT)

                msg = f"Row {idx}: {ref_title!r} <> {dl_title!r}"
                if should_match:
                    self.assertEqual(pairs, [(0, 0)], f"Expected match: {msg}")
                else:
                    self.assertEqual(pairs, [], f"Expected no match: {msg}")


if __name__ == "__main__":
    unittest.main()
