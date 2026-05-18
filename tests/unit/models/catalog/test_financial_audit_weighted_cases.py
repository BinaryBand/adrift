from pathlib import Path

from tests.unit.models.catalog._fixtures import (
    run_weighted_case_test,
)

_WEIGHTED_CASES = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "alignment"
    / "financial_audit_weighted_cases.csv"
)


def test_financial_audit_weighted_cases() -> None:
    run_weighted_case_test(_WEIGHTED_CASES, "Financial Audit")
