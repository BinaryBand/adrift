"""YouTube tests module."""

from pathlib import Path
import unittest
import sys


if __name__ == "__main__":
    # Run all YouTube tests in this directory
    print("\n" + "=" * 70)
    print("Running YouTube tests...")
    print("=" * 70 + "\n")

    loader = unittest.TestLoader()
    start_dir = (Path(__file__).parent).as_posix()
    top_level_dir = Path(__file__).parent.parent.as_posix()
    suite = loader.discover(start_dir, pattern="test_*.py", top_level_dir=top_level_dir)

    # Run the tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
