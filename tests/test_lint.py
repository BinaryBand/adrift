"""Linting tests for the current local toolchain."""

from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which
from typing import Any, Iterable

ROOT: Path = Path(__file__).resolve().parents[1]
VENV_BIN = ROOT / ".venv" / "bin"


def run_resolved(cmd: Iterable[str], /, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Resolve the command's executable and call ``subprocess.run``."""
    argv = list(cmd)
    executable = argv[0]
    local_executable = VENV_BIN / executable
    if local_executable.exists():
        argv[0] = local_executable.as_posix()
    elif which(executable) is not None:
        argv[0] = which(executable) or executable
    return subprocess.run(argv, cwd=ROOT, check=False, **kwargs)


class TestRuff:
    """Ensure the codebase passes ruff linting and formatting checks."""

    PATHS = ["src", "runbook", "tests", "typings"]

    def test_ruff_check(self):
        """Fail if ruff reports any lint violations."""
        result = run_resolved(
            ["python", "-m", "ruff", "check", *self.PATHS],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_ruff_format(self):
        """Fail if ruff reports any formatting violations."""
        result = run_resolved(
            [
                "python",
                "-m",
                "ruff",
                "format",
                "--check",
                "--exclude",
                "runbook/.timer",
                *self.PATHS,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestPyright:
    """Ensure the codebase passes the current Pyright gate."""

    def test_pyright(self):
        """Fail if Pyright reports any type-checking violations."""
        result = run_resolved(
            ["pyright", "--project", "pyrightconfig.json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestLizard:
    """Track the current Lizard complexity gate."""

    def test_lizard(self):
        """Fail once the repo is expected to satisfy the configured Lizard thresholds."""
        result = run_resolved(
            ["python", "-m", "lizard", "src", "-C", "8", "-L", "30", "-a", "4"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


# class TestSemgrep:
#     """Ensure the codebase passes the current Semgrep architecture gate."""

#     def test_semgrep(self):
#         """Fail if Semgrep reports any architecture or process violations."""
#         result = run_resolved(
#             ["poetry", "run", "semgrep", "scan", "--config", ".semgrep.yml", "--error"],
#             capture_output=True,
#             text=True,
#         )
#         assert result.returncode == 0, result.stdout + result.stderr


class TestVulture:
    """Ensure the codebase passes the current Vulture dead-code gate."""

    PATHS = ["src", "tests"]

    def test_vulture(self):
        """Fail if Vulture reports unused code at or above 80% confidence."""
        result = run_resolved(
            ["python", "-m", "vulture", *self.PATHS, "--min-confidence", "80"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
