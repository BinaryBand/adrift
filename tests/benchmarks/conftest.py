import os

import pytest

from tests.benchmarks._runner import PerfRunner, calibrate

_RECORD = os.getenv("RECORD_PERF_BASELINE", "").lower() in ("1", "true")
_TOLERANCE = float(os.getenv("PERF_TOLERANCE", "2.0"))


@pytest.fixture(scope="session")
def perf_calibration() -> float:
    return calibrate()


@pytest.fixture
def perf(perf_calibration: float) -> PerfRunner:
    return PerfRunner(perf_calibration, _RECORD, _TOLERANCE)
