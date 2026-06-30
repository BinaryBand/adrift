"""Project-root conftest: auto-format and auto-fix before each test session."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def pytest_configure(config) -> None:
    # Invoke ruff via the current interpreter so it resolves without relying on
    # PATH (the VSCode test runner calls `.venv/bin/python -m pytest` without
    # poetry's PATH), and capture output so it never corrupts the IDE's
    # stdout-based test-discovery protocol.
    for args in (["format"], ["check", "--fix"]):
        subprocess.run(
            [sys.executable, "-m", "ruff", *args, str(ROOT)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
