"""Tests for the new 4-signal alignment algorithm (SPECS.md §Stage 1-3)."""

import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from src.catalog import _best_thumbnail, align_episodes, merge_episode, sim_date
from src.models.metadata import RssEpisode


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


# ---------------------------------------------------------------------------
# sim_date
# ---------------------------------------------------------------------------


class TestSimDate(unittest.TestCase):
    def test_none_inputs_return_zero(self):
        self.assertEqual(sim_date(None, None), 0.0)
        self.assertEqual(sim_date(_dt(2024, 1, 1), None), 0.0)
        self.assertEqual(sim_date(None, _dt(2024, 1, 1)), 0.0)

    def test_same_date(self):
        d = _dt(2024, 6, 15)
        self.assertEqual(sim_date(d, d), 1.00)

    def test_within_2_days(self):
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 1, 3)), 1.00)
        self.assertEqual(sim_date(_dt(2024, 1, 3), _dt(2024, 1, 1)), 1.00)

    def test_within_10_days(self):
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 1, 8)), 0.70)
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 1, 11)), 0.70)

    def test_within_35_days(self):
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 1, 20)), 0.15)
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 2, 5)), 0.15)

    def test_beyond_35_days(self):
        self.assertEqual(sim_date(_dt(2024, 1, 1), _dt(2024, 3, 1)), 0.00)


# ---------------------------------------------------------------------------
# align_episodes
# ---------------------------------------------------------------------------


class TestAlignEpisodes(unittest.TestCase):
    def test_exact_title_match(self):
        ref = _ep(id="abc", title="Ep 1: Great Stuff", pub_date=_dt(2024, 1, 5))
        dl = _ep(id="xyz", title="Ep 1: Great Stuff", pub_date=_dt(2024, 1, 5))
        pairs = align_episodes([ref], [dl])
        self.assertEqual(pairs, [(0, 0)])

    def test_same_id_match(self):
        """Identical IDs boost score even with a moderate date offset."""
        ref = _ep(id="same_id", title="Episode", pub_date=_dt(2024, 1, 1))
        dl = _ep(id="same_id", title="Episode", pub_date=_dt(2024, 1, 1))
        pairs = align_episodes([ref], [dl])
        self.assertEqual(pairs, [(0, 0)])

    def test_no_match_below_threshold(self):
        """Completely unrelated episodes should not match."""
        ref = _ep(
            id="a",
            title="Science Explained: Quantum Tunneling",
            pub_date=_dt(2024, 1, 1),
        )
        dl = _ep(id="b", title="Cooking Show: Best Pasta Recipes", pub_date=_dt(2024, 6, 1))
        pairs = align_episodes([ref], [dl])
        self.assertEqual(pairs, [])

    def test_greedy_prefers_best_pair(self):
        """The highest-scoring pair is committed first; the second-best gets leftovers."""
        ref1 = _ep(id="r1", title="Weekly Show Episode 1", pub_date=_dt(2024, 1, 7))
        ref2 = _ep(id="r2", title="Weekly Show Episode 2", pub_date=_dt(2024, 1, 14))

        dl1 = _ep(id="d1", title="Weekly Show Episode 1", pub_date=_dt(2024, 1, 7))
        dl2 = _ep(id="d2", title="Weekly Show Episode 2", pub_date=_dt(2024, 1, 14))

        pairs = align_episodes([ref1, ref2], [dl1, dl2])
        self.assertIn((0, 0), pairs)
        self.assertIn((1, 1), pairs)

    def test_no_double_use(self):
        """Each episode may appear in at most one matched pair."""
        ref1 = _ep(id="r1", title="Episode 1: The Start", pub_date=_dt(2024, 1, 1))
        ref2 = _ep(id="r2", title="Episode 1: The Start", pub_date=_dt(2024, 1, 1))
        dl = _ep(id="d1", title="Episode 1: The Start", pub_date=_dt(2024, 1, 1))

        pairs = align_episodes([ref1, ref2], [dl])
        dl_indices = [d for _, d in pairs]
        self.assertEqual(len(dl_indices), len(set(dl_indices)), "Download episode used twice")


# ---------------------------------------------------------------------------
# merge_episode
# ---------------------------------------------------------------------------


class TestMergeEpisode(unittest.TestCase):
    def test_id_prefers_non_url(self):
        ref = _ep(id="https://example.com/ep1")
        dl = _ep(id="yt_abc123")
        result = merge_episode(ref, dl)
        self.assertEqual(result.id, "yt_abc123")

    def test_id_keeps_ref_when_not_url(self):
        ref = _ep(id="short_id")
        dl = _ep(id="https://example.com/dl1")
        result = merge_episode(ref, dl)
        self.assertEqual(result.id, "short_id")

    def test_id_prefers_dl_when_both_non_url(self):
        """Download side (YouTube video ID) beats ref side (RSS GUID) per spec."""
        ref = _ep(id="rss-guid-abc")
        dl = _ep(id="dQw4w9WgXcQ")
        result = merge_episode(ref, dl)
        self.assertEqual(result.id, "dQw4w9WgXcQ")

    def test_title_longest_wins(self):
        ref = _ep(title="Episode 1")
        dl = _ep(title="Episode 1: The Full Title With More Words")
        result = merge_episode(ref, dl)
        self.assertEqual(result.title, "Episode 1: The Full Title With More Words")

    def test_upload_date_earliest_wins(self):
        ref = _ep(pub_date=_dt(2024, 1, 5))
        dl = _ep(pub_date=_dt(2024, 1, 1))
        result = merge_episode(ref, dl)
        self.assertEqual(result.upload_date, _dt(2024, 1, 1))

    def test_description_longest_wins(self):
        ref = _ep(description="Short description.")
        dl = _ep(description="This is a much longer description with more detail and context.")
        result = merge_episode(ref, dl)
        self.assertEqual(result.description, dl.description)

    def test_source_is_union(self):
        ref = _ep(content="https://rss.example.com/ep1.mp3")
        dl = _ep(content="https://yt.example.com/watch?v=abc")
        result = merge_episode(ref, dl)
        self.assertEqual(len(result.source), 2)
        self.assertIn("https://rss.example.com/ep1.mp3", result.source)
        self.assertIn("https://yt.example.com/watch?v=abc", result.source)

    def test_source_deduplicates(self):
        same_url = "https://example.com/ep.mp3"
        ref = _ep(content=same_url)
        dl = _ep(content=same_url)
        result = merge_episode(ref, dl)
        self.assertEqual(len(result.source), 1)


# ---------------------------------------------------------------------------
# _best_thumbnail
# ---------------------------------------------------------------------------


class TestBestThumbnail(unittest.TestCase):
    def test_none_inputs(self):
        self.assertIsNone(_best_thumbnail(None, None))
        self.assertEqual(
            _best_thumbnail("https://ex.com/thumb.jpg", None),
            "https://ex.com/thumb.jpg",
        )
        self.assertEqual(
            _best_thumbnail(None, "https://ex.com/thumb.jpg"),
            "https://ex.com/thumb.jpg",
        )

    def test_maxres_beats_hq(self):
        a = "https://img.youtube.com/vi/abc/maxresdefault.jpg"
        b = "https://img.youtube.com/vi/abc/hqdefault.jpg"
        self.assertEqual(_best_thumbnail(a, b), a)
        self.assertEqual(_best_thumbnail(b, a), a)

    def test_hq_beats_mq(self):
        a = "https://img.youtube.com/vi/abc/hqdefault.jpg"
        b = "https://img.youtube.com/vi/abc/mqdefault.jpg"
        self.assertEqual(_best_thumbnail(a, b), a)

    def test_equal_rank_returns_first(self):
        a = "https://img.youtube.com/vi/abc/hqdefault.jpg"
        b = "https://img.youtube.com/vi/xyz/hqdefault.jpg"
        self.assertEqual(_best_thumbnail(a, b), a)


if __name__ == "__main__":
    unittest.main()
