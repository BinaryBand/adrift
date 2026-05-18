"""Unit tests for _score() — the unified scoring function in catalog.alignment.

These tests pin the behaviour of the two scoring branches that were previously
separate functions (_certainty_title_score and _compute_base_score).  They
complement the full alignment integration tests by targeting the logic branch
controlled by the include_date flag directly.
"""

import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("S3_USERNAME", "_test")
os.environ.setdefault("S3_SECRET_KEY", "_test")
os.environ.setdefault("S3_ENDPOINT", "http://localhost")
os.environ.setdefault("S3_REGION", "us-east-1")

from adrift.models import RssEpisode
from adrift.models.catalog.alignment import (
    _CONTAINMENT_BONUS,
    _AlignmentCandidate,
    _score,
    _Sims,
)


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _ep(
    id: str = "x",
    title: str = "Episode",
    description: str = "",
    pub_date: datetime | None = None,
) -> RssEpisode:
    return RssEpisode(
        id=id,
        title=title,
        author="",
        content="http://example.com/ep.mp3",
        description=description or None,
        pub_date=pub_date,
    )


def _candidate(ep: RssEpisode, title: str = "", description: str = "") -> _AlignmentCandidate:
    return _AlignmentCandidate(episode=ep, title=title or ep.title, description=description)


class TestScoreIncludeDateFalse(unittest.TestCase):
    """include_date=False: date signal must be absent from the score."""

    def test_date_mismatch_does_not_lower_score(self):
        # ref is 2020, dl is 2023 — a big date gap.  With include_date=False
        # the score should be the same as when both have no date.
        ref_ep = _ep(pub_date=_dt(2020, 1, 1))
        dl_ep = _ep(pub_date=_dt(2023, 6, 15))
        ref = _candidate(ref_ep, "Denise Huber Part 1")
        dl = _candidate(dl_ep, "Denise Huber Part 1")

        ref_no_date = _candidate(_ep(), "Denise Huber Part 1")
        dl_no_date = _candidate(_ep(), "Denise Huber Part 1")

        score_with_dates = _score(ref, dl, _Sims(1.0), include_date=False)
        score_without_dates = _score(ref_no_date, dl_no_date, _Sims(1.0), include_date=False)
        self.assertAlmostEqual(score_with_dates, score_without_dates, places=6)

    def test_containment_bonus_not_applied_when_include_date_false(self):
        # "Denise Huber" is fully contained in "Disappearance of Denise Huber".
        # The containment bonus must NOT be applied when include_date=False.
        ref_ep = _ep()
        dl_ep = _ep()
        ref = _candidate(ref_ep, "denise huber")
        dl = _candidate(dl_ep, "disappearance of denise huber")

        score_no_date = _score(ref, dl, _Sims(0.8), include_date=False)

        # Without the containment bonus the score should equal a non-contained pair
        # at the same title similarity.
        ref2 = _candidate(_ep(), "episode abc")
        dl2 = _candidate(_ep(), "episode def")
        score_no_containment = _score(ref2, dl2, _Sims(0.8), include_date=False)

        self.assertAlmostEqual(score_no_date, score_no_containment, places=6)


class TestScoreIncludeDateTrue(unittest.TestCase):
    """include_date=True: date signal IS factored in; containment bonus IS applied."""

    def test_perfect_date_match_raises_score(self):
        same_date = _dt(2022, 3, 15)
        ref = _candidate(_ep(pub_date=same_date), "episode abc")
        dl = _candidate(_ep(pub_date=same_date), "episode abc")

        ref_no_date = _candidate(_ep(), "episode abc")
        dl_no_date = _candidate(_ep(), "episode abc")

        score_with_date = _score(ref, dl, _Sims(0.8), include_date=True)
        score_no_date = _score(ref_no_date, dl_no_date, _Sims(0.8), include_date=True)

        # Matching date should boost the score
        self.assertGreater(score_with_date, score_no_date)

    def test_far_date_lowers_score_relative_to_no_date(self):
        ref = _candidate(_ep(pub_date=_dt(2020, 1, 1)), "episode abc")
        dl = _candidate(_ep(pub_date=_dt(2023, 6, 15)), "episode abc")

        ref_no = _candidate(_ep(), "episode abc")
        dl_no = _candidate(_ep(), "episode abc")

        score_far_date = _score(ref, dl, _Sims(0.8), include_date=True)
        score_no_date = _score(ref_no, dl_no, _Sims(0.8), include_date=True)

        # Date is present but far apart — score should be lower than with no date signal,
        # since a 0.0 date score dilutes the weighted average.
        self.assertLess(score_far_date, score_no_date)

    def test_containment_bonus_applied(self):
        # "denise huber" tokens are a subset of "disappearance of denise huber" tokens.
        ref = _candidate(_ep(), "denise huber")
        dl = _candidate(_ep(), "disappearance of denise huber")

        # No shared anchor tokens → no containment; scores differ only by the bonus.
        ref2 = _candidate(_ep(), "gorilla attack jungle")
        dl2 = _candidate(_ep(), "dolphin swim ocean")

        score_with_containment = _score(ref, dl, _Sims(0.8), include_date=True)
        score_without_containment = _score(ref2, dl2, _Sims(0.8), include_date=True)

        # Containment bonus should increase the score
        self.assertGreater(score_with_containment, score_without_containment)
        # And the increment should match the defined constant
        self.assertAlmostEqual(
            score_with_containment - score_without_containment, _CONTAINMENT_BONUS, places=4
        )

    def test_score_capped_at_one(self):
        same_date = _dt(2022, 3, 15)
        ref = _candidate(_ep(id="abc", pub_date=same_date), "episode abc")
        dl = _candidate(_ep(id="abc", pub_date=same_date), "episode abc")
        # Perfect title, same ID, same date — should not exceed 1.0
        result = _score(ref, dl, _Sims(1.0, 1.0), include_date=True)
        self.assertLessEqual(result, 1.0)


if __name__ == "__main__":
    unittest.main()
