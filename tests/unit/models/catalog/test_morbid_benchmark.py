import csv
import unittest

from adrift.models import AlignmentConfig
from adrift.models.catalog import align_episodes_impl
from tests.unit.models.catalog._fixtures import dt as _dt
from tests.unit.models.catalog._fixtures import ep as _ep

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])


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
