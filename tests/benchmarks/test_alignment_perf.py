"""Alignment scoring-kernel benchmarks.

AlignmentBatch is built outside the timed window so normalize_title and disk
I/O don't contribute variance.  The scorer used is whatever is active at
runtime (Rust extension if compiled, Python prototype otherwise).

Two sizes cover the typical (small feed) and worst-case (large archive) shapes.
"""

from datetime import datetime, timedelta, timezone

from adrift.adapters.process.alignment import RustScoredAlignmentAdapter
from adrift.models import RssEpisode
from adrift.services.catalog.alignment import prepare_alignment_batch
from tests.benchmarks._runner import PerfRunner

_BASE_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)

_TITLE_POOL = [
    "The Truth About {topic} | Part {n}",
    "Deep Dive: {topic} and Why It Matters",
    "Interview: {person} on {topic}",
    "{topic} Explained — Episode {n}",
    "Breaking Down {topic} with {person}",
    "How {topic} Changed Everything | Ep {n}",
    "The Real Story of {topic}",
    "{person} Reveals the Secrets of {topic}",
]
_TOPICS = [
    "AI", "Climate", "History", "Crime", "Science",
    "Politics", "Health", "Finance", "Space", "Culture",
]
_PEOPLE = [
    "Dr. Johnson", "Sarah Williams", "Mark Thompson",
    "Prof. Chen", "Lisa Garcia", "James Okafor",
]

_scorer = RustScoredAlignmentAdapter()


def _make_episode(idx: int, show: str = "") -> RssEpisode:
    topic = _TOPICS[idx % len(_TOPICS)]
    person = _PEOPLE[idx % len(_PEOPLE)]
    template = _TITLE_POOL[idx % len(_TITLE_POOL)]
    title = template.format(n=idx + 1, topic=topic, person=person)
    return RssEpisode(
        id=f"ep-{show or 'bench'}-{idx:04d}",
        title=title,
        author="Benchmark Host",
        content="",
        description=f"In this episode we explore {topic}. Guest: {person}. Episode {idx}.",
        pub_date=_BASE_DATE + timedelta(days=idx * 7),
    )


def _make_episodes(n: int, show: str = "") -> list[RssEpisode]:
    return [_make_episode(i, show) for i in range(n)]


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def test_alignment_50x50(perf: PerfRunner) -> None:
    batch = prepare_alignment_batch(_make_episodes(50), _make_episodes(50, "dl"), "Benchmark Show")
    perf.run("alignment.50x50", _scorer.align_batch, batch)


def test_alignment_150x150(perf: PerfRunner) -> None:
    batch = prepare_alignment_batch(
        _make_episodes(150), _make_episodes(150, "dl"), "Benchmark Show"
    )
    perf.run("alignment.150x150", _scorer.align_batch, batch)
