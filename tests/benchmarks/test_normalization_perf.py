"""Title normalization performance benchmarks.

Two scenarios are measured:

cold  — neither the in-memory LRU nor the disk cache holds the result.
        Represents the very first time a title is seen.

warm  — disk cache is pre-populated; only the in-memory LRU is cleared between
        runs.  This is the normal production path: a new process starts, the
        LRU is empty, and every title is resolved from the on-disk cache.
"""

from adrift.utils.title_normalization import normalize_title
from tests.benchmarks._runner import PerfRunner

_SHOW = "Benchmark Show"
_BATCH_SIZE = 300

_TITLE_TEMPLATES = [
    "Episode {n}: The History of Everything",
    "Interview with Guest {n} on Modern Science",
    "Deep Dive Part {n}: Understanding the World",
    "Breaking News {n}: What You Need to Know",
    "The Truth About Subject {n}",
]


def _make_titles(prefix: str) -> list[tuple[str, str]]:
    """Return (show, title) pairs guaranteed unique via *prefix*."""
    return [
        (_SHOW, _TITLE_TEMPLATES[i % len(_TITLE_TEMPLATES)].replace("{n}", f"{prefix}-{i}"))
        for i in range(_BATCH_SIZE)
    ]


def _run_batch(pairs: list[tuple[str, str]]) -> None:
    for show, title in pairs:
        normalize_title(show, title)


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def test_normalize_title_cold(perf: PerfRunner) -> None:
    """Cost of normalizing a fresh batch with no caches warm."""
    # Each timed call gets a unique prefix so titles are never in any cache.
    call_count = [0]

    def _setup() -> None:
        normalize_title.cache_clear()
        call_count[0] += 1

    def _run() -> None:
        _run_batch(_make_titles(f"cold-r{call_count[0]}"))

    perf.run("normalize_title.cold", _run, setup=_setup)


def test_normalize_title_warm_disk(perf: PerfRunner) -> None:
    """Cost of normalizing a batch with the disk cache warm but LRU empty."""
    pairs = _make_titles("warm")

    # Pre-populate the disk cache outside the timed section.
    normalize_title.cache_clear()
    _run_batch(pairs)

    def _setup() -> None:
        normalize_title.cache_clear()

    perf.run("normalize_title.warm_disk", _run_batch, pairs, setup=_setup)
