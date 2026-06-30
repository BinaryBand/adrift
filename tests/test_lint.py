"""Linting tests for the current local toolchain."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from shutil import which
from typing import Any, Iterable

import pytest

ROOT: Path = Path(__file__).resolve().parents[1]
VENV_BIN = ROOT / ".venv" / "bin"
_RUFF_PREP_DONE = False


def run_resolved(cmd: Iterable[str], /, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Resolve the command's executable and call ``subprocess.run``."""
    argv = list(cmd)
    executable = argv[0]
    local_executable = VENV_BIN / executable
    if local_executable.exists():
        argv[0] = local_executable.as_posix()
    elif which(executable) is not None:
        argv[0] = which(executable) or executable
    return subprocess.run(argv, cwd=ROOT, check=False, **kwargs)  # type: ignore


def _ruff_autofix_enabled() -> bool:
    if os.environ.get("CI") == "true":
        return False
    return os.environ.get("ADRIFT_RUFF_AUTOFIX", "1") == "1"


def _ensure_ruff_preflight(paths: Iterable[str]) -> None:
    global _RUFF_PREP_DONE
    if _RUFF_PREP_DONE or not _ruff_autofix_enabled():
        return

    fix_result = run_resolved(
        ["python", "-m", "ruff", "check", "--fix", *paths],
        capture_output=True,
        text=True,
    )
    assert fix_result.returncode == 0, fix_result.stdout + fix_result.stderr

    format_result = run_resolved(
        ["python", "-m", "ruff", "format", *paths],
        capture_output=True,
        text=True,
    )
    assert format_result.returncode == 0, format_result.stdout + format_result.stderr

    _RUFF_PREP_DONE = True


class TestCpd:
    """Ensure the codebase passes copy-paste detection checks."""

    @pytest.mark.parametrize(
        "config,path",
        [("rules/jscpd.json", "."), ("rules/jscpd.tests.json", "tests")],
    )
    def test_cpd(self, config, path):
        """Fail if jscpd reports any copy-paste duplication."""
        result = run_resolved(
            ["npx", "jscpd", "--config", config, path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestRuff:
    """Ensure the codebase passes ruff linting and formatting checks."""

    PATHS = ["adrift", "tests", "typings"]

    def test_ruff_check(self):
        """Fail if ruff reports any lint violations."""
        _ensure_ruff_preflight(self.PATHS)
        result = run_resolved(
            ["python", "-m", "ruff", "check", "adrift", "tests", "typings"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_ruff_format(self):
        """Fail if ruff reports any formatting violations."""
        _ensure_ruff_preflight(self.PATHS)
        result = run_resolved(
            [
                "python",
                "-m",
                "ruff",
                "format",
                "--check",
                *self.PATHS,
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestTy:
    """Ensure the codebase passes the current ty gate."""

    def test_ty(self):
        """Fail if ty reports any type-checking violations."""
        result = run_resolved(
            ["ty", "check", "--project", "."],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestLizard:
    """Track the current Lizard complexity gate."""

    def test_lizard(self):
        """Fail once the repo is expected to satisfy the configured Lizard thresholds."""
        cmd = [
            "python",
            "-m",
            "lizard",
            "adrift",
            "-x",
            "adrift/cli/*",
            "-C",
            "8",
            "-L",
            "30",
            "-a",
            "9",
        ]
        result = run_resolved(cmd, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


def _semgrep_runnable() -> bool:
    """Return whether Semgrep is installed *and* actually executes here.

    Semgrep's bundled protobuf has no working C extension on Python 3.14, so the
    binary can be present yet crash on import. Treat that as "unavailable" rather
    than a lint failure -- CI runs Semgrep on a supported interpreter.
    """
    if not ((VENV_BIN / "semgrep").exists() or which("semgrep") is not None):
        return False
    try:
        probe = run_resolved(["semgrep", "--version"], capture_output=True, text=True)
    except OSError:
        return False
    return probe.returncode == 0


class TestSemgrep:
    """Ensure the codebase passes the current Semgrep architecture gate."""

    @pytest.mark.skipif(
        os.environ.get("CI") == "true" or not _semgrep_runnable(),
        reason="Semgrep is already run via semgrep/semgrep-action in CI",
    )
    def test_semgrep(self):
        """Fail if Semgrep reports any architecture or process violations."""
        result = run_resolved(
            ["semgrep", "scan", "--config", "rules/semgrep", "--error"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestVulture:
    """Ensure the codebase passes the current Vulture dead-code gate."""

    PATHS = ["adrift", "tests"]

    def test_vulture(self):
        """Fail if Vulture reports unused code at or above 80% confidence."""
        result = run_resolved(
            ["python", "-m", "vulture", "adrift", "tests", "--min-confidence", "80"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
