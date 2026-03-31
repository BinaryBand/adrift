"""Test runner for PodSmith project."""

from typing import Literal
from pathlib import Path
import argparse
import unittest
import os


TEST_TARGET = Literal["audio", "youtube", "misc", "all"]
DF_TEST_TARGET: TEST_TARGET = "all"


def run_tests(test_target: TEST_TARGET = DF_TEST_TARGET) -> tuple[bool, list, list]:
    """Discover and run tests in the specified target directory.

    Args:
        test_target: Which tests to run ("audio", "youtube", "misc", or "all")

    Returns:
        Tuple of (success, failures, errors)
    """
    os.environ.setdefault("PODSMITH_SKIP_VIDEO_INFO", "1")

    tests_dir = Path(__file__).parent.parent / "tests"
    top_level_dir = tests_dir.parent.as_posix()

    # Determine which directory to scan
    if test_target == "all":
        start_dir = tests_dir.as_posix()
        description = "all tests"
    elif test_target in ("audio", "youtube", "misc"):
        start_dir = (tests_dir / test_target).as_posix()
        description = f"{test_target} tests"
    else:
        print(f"Error: Invalid test target '{test_target}'")
        return False, [], []

    print("\n" + "=" * 70)
    print(f"Running {description}...")
    print("=" * 70 + "\n")

    # Discover tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir, pattern="test_*.py", top_level_dir=top_level_dir)

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful(), result.failures, result.errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unit tests for PodSmith project")
    parser.add_argument(
        "--test-target",
        choices=["audio", "youtube", "misc", "all"],
        default=DF_TEST_TARGET,
        help=f"Which tests to run (default: {DF_TEST_TARGET})",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    tests_passed, test_failures, test_errors = run_tests(args.test_target)

    if tests_passed:
        print("Unit tests:\t✓ PASSED")
    else:
        failure_count = len(test_failures)
        error_count = len(test_errors)
        issues = []
        if failure_count > 0:
            issues.append(f"{failure_count} failure{'s' if failure_count != 1 else ''}")
        if error_count > 0:
            issues.append(f"{error_count} error{'s' if error_count != 1 else ''}")
        print(f"Unit tests:\t✗ FAILED ({', '.join(issues)})")

    print("=" * 70 + "\n")

    return 0 if tests_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
