import os

import pytest

from tests.benchmarks._runner import PerfRunner, calibrate

_RECORD = os.getenv("RECORD_PERF_BASELINE", "").lower() in ("1", "true")
_TOLERANCE = float(os.getenv("PERF_TOLERANCE", "2.0"))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip all benchmark tests unless RUN_PERF_TESTS or RECORD_PERF_BASELINE is set."""
    if os.getenv("RUN_PERF_TESTS", "").lower() in ("1", "true") or _RECORD:
        return
    skip = pytest.mark.skip(reason="set RUN_PERF_TESTS=1 or RECORD_PERF_BASELINE=1 to run")
    for item in items:
        if "benchmarks" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def perf_calibration() -> float:
    return calibrate()


@pytest.fixture
def perf(perf_calibration: float) -> PerfRunner:
    return PerfRunner(perf_calibration, _RECORD, _TOLERANCE)
