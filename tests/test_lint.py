"""Linting tests for the current local toolchain."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

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
        ("config", "path"),
        [("static/rules/jscpd.json", "."), ("static/rules/jscpd.tests.json", "tests")],
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

    PATHS = ["adrift", "tests"]

    def test_ruff_check(self):
        """Fail if ruff reports any lint violations."""
        _ensure_ruff_preflight(self.PATHS)
        result = run_resolved(
            ["python", "-m", "ruff", "check", "adrift", "tests"],
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


class TestImportLinter:
    """Ensure the codebase passes import-linter dependency contracts."""

    def test_import_linter(self):
        """Fail if any import-linter contract is violated."""
        result = run_resolved(
            ["lint-imports", "--config", str(ROOT / "pyproject.toml")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestAstGrep:
    """Ensure the codebase passes the ast-grep AST-pattern gate."""

    @pytest.mark.skipif(
        not ((VENV_BIN / "ast-grep").exists() or which("ast-grep") is not None),
        reason="ast-grep is not installed",
    )
    def test_ast_grep(self):
        """Fail if ast-grep reports any error-severity findings."""
        result = run_resolved(
            ["ast-grep", "scan", "--config", "sgconfig.yml"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def _stray_files(base: Path, allowed_dirs: set[str], allowed_files: set[str]) -> list[str]:
    """Return .py files under ``base`` outside the allowed sub-packages and files."""
    return sorted(
        rel.as_posix()
        for rel in (p.relative_to(base) for p in base.rglob("*.py"))
        if rel.as_posix() not in allowed_files and rel.parts[0] not in allowed_dirs
    )


class TestScaffold:
    """Keep the package and test-tree shape aligned with the scaffold policy."""

    LAYERS = {"adapters", "cli", "core"}

    def test_adrift_top_level_shape(self):
        """Only the declared layers (plus dunder modules) may sit under adrift/."""
        stray = _stray_files(ROOT / "adrift", self.LAYERS, {"__init__.py", "__main__.py"})
        assert not stray, f"Unexpected modules under adrift/: {stray}"

    def test_tests_unit_mirror_shape(self):
        """tests/unit must mirror the adrift top-level layers only."""
        allowed_files = {"__init__.py", "conftest.py", "_fixtures.py"}
        stray = _stray_files(ROOT / "tests" / "unit", self.LAYERS, allowed_files)
        assert not stray, f"Unexpected modules under tests/unit/: {stray}"

    def test_adapters_shape(self):
        """Keep adrift.adapters limited to its stable sub-packages."""
        allowed = {"config", "lint", "process", "reporting"}
        stray = _stray_files(ROOT / "adrift" / "adapters", allowed, {"__init__.py", "errors.py"})
        assert not stray, f"Unexpected modules under adrift/adapters/: {stray}"


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
