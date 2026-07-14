from pathlib import Path

from adrift.core.models import AlignmentConfig
from tests.unit.core.models.catalog._fixtures import (
    run_weighted_case_test,
)

_MORBID_ALIGNMENT = AlignmentConfig(extra_stopwords=["morbid"])
_WEIGHTED_CASES = (
    Path(__file__).resolve().parents[4] / "resources" / "alignment" / "morbid_weighted_cases.csv"
)


def test_morbid_weighted_cases() -> None:
    run_weighted_case_test(_WEIGHTED_CASES, "Morbid", _MORBID_ALIGNMENT)
