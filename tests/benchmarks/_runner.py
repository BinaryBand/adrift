"""
Performance benchmark runner.

Baselines are stored as *normalized* values: measured_seconds / calibration_seconds.
Calibration times a fixed CPU-bound operation on the current machine, making the
stored baseline machine-independent — the same baselines.json works everywhere.

Recording a baseline:
    RECORD_PERF_BASELINE=1 pytest tests/benchmarks/

Checking against baseline (default):
    pytest tests/benchmarks/

Adjusting tolerance (default 2.0×):
    PERF_TOLERANCE=3.0 pytest tests/benchmarks/
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any

_BASELINE_PATH = Path(__file__).parent / "baselines.json"
_N_RUNS = 7
_CAL_ITERS = 5_000
_CAL_REPEATS = 3


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def _calibrate_once() -> float:
    start = time.perf_counter()
    for i in range(_CAL_ITERS):
        hashlib.md5(f"cal{i}".encode(), usedforsecurity=False).hexdigest()
    return time.perf_counter() - start


def calibrate() -> float:
    """Return median time (seconds) for a fixed CPU-bound calibration task."""
    return median(_calibrate_once() for _ in range(_CAL_REPEATS))


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def time_fn(
    fn: Callable[..., Any],
    *args: Any,
    n: int = _N_RUNS,
    setup: Callable[[], None] | None = None,
    **kwargs: Any,
) -> dict[str, float]:
    """Run *fn* n times, optionally calling *setup* before each run."""
    samples: list[float] = []
    for _ in range(n):
        if setup is not None:
            setup()
        start = time.perf_counter()
        fn(*args, **kwargs)
        samples.append(time.perf_counter() - start)
    sorted_samples = sorted(samples)
    p95_idx = max(0, int(len(sorted_samples) * 0.95) - 1)
    return {
        "median_s": median(samples),
        "p95_s": sorted_samples[p95_idx],
        "min_s": sorted_samples[0],
        "max_s": sorted_samples[-1],
    }


# ---------------------------------------------------------------------------
# Baseline persistence
# ---------------------------------------------------------------------------


def load_baselines() -> dict[str, Any]:
    if not _BASELINE_PATH.exists():
        return {}
    return json.loads(_BASELINE_PATH.read_text())


def _save_baselines(baselines: dict[str, Any]) -> None:
    _BASELINE_PATH.write_text(json.dumps(baselines, indent=2, sort_keys=True) + "\n")


def record(name: str, stats: dict[str, float], cal: float) -> None:
    """Save *stats* as the new baseline for *name*."""
    baselines = load_baselines()
    baselines[name] = {
        "normalized_median": stats["median_s"] / cal,
        "raw_median_ms": round(stats["median_s"] * 1000, 2),
        "calibration_s": round(cal, 6),
    }
    _save_baselines(baselines)


def check(name: str, stats: dict[str, float], cal: float, tolerance: float) -> None:
    """Assert *stats* is within *tolerance*× of the stored baseline for *name*."""
    baselines = load_baselines()
    if name not in baselines:
        raise AssertionError(
            f"No baseline recorded for '{name}'. "
            "Run: RECORD_PERF_BASELINE=1 pytest tests/benchmarks/"
        )
    b = baselines[name]
    limit_s = b["normalized_median"] * cal * tolerance
    actual_s = stats["median_s"]
    if actual_s > limit_s:
        raise AssertionError(
            f"Perf regression in '{name}': "
            f"{actual_s * 1000:.1f}ms median > {limit_s * 1000:.1f}ms limit "
            f"({b['raw_median_ms']:.1f}ms baseline × {tolerance}×)"
        )


# ---------------------------------------------------------------------------
# PerfRunner — thin wrapper used by the pytest fixture
# ---------------------------------------------------------------------------


class PerfRunner:
    def __init__(self, cal: float, record_mode: bool, tolerance: float) -> None:
        self._cal = cal
        self._record = record_mode
        self._tolerance = tolerance

    def run(
        self,
        name: str,
        fn: Callable[..., Any],
        *args: Any,
        n: int = _N_RUNS,
        setup: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Time *fn* and either record or check against baseline."""
        stats = time_fn(fn, *args, n=n, setup=setup, **kwargs)
        if self._record:
            record(name, stats, self._cal)
        else:
            check(name, stats, self._cal, self._tolerance)
