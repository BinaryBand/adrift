#!/usr/bin/env python3
"""Enforce a small set of import-boundary rules.

Emits diagnostics in the form:
  path:line: severity: message
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

_ROOT = Path(__file__).parent.parent.parent.resolve()
_DEFAULT_PATHS = ("src", "runbook", "tests")


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    severity: str
    message: str


@dataclass(frozen=True)
class ImportBoundaryRule:
    banned_module: str
    banned_names: tuple[str, ...]
    preferred_modules: tuple[str, ...]
    message: str


RULES = (
    ImportBoundaryRule(
        banned_module="src.web.rss",
        banned_names=("RssEpisode", "RssChannel"),
        preferred_modules=("src.models", "src.models.metadata"),
        message=(
            "Import domain RSS models from src.models or src.models.metadata, "
            "not from src.web.rss."
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check import-boundary rules")
    parser.add_argument("paths", nargs="*", help="Paths to scan")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any violations are found",
    )
    return parser.parse_args()


def _iter_python_files(paths: Iterable[str]) -> Iterator[Path]:
    for raw_path in paths:
        path = (_ROOT / raw_path).resolve()
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        if path.is_dir():
            yield from path.rglob("*.py")


def _check_import_from(node: ast.ImportFrom, file_path: Path) -> list[Diagnostic]:
    if node.module is None:
        return []

    diagnostics: list[Diagnostic] = []
    for rule in RULES:
        if node.module != rule.banned_module:
            continue
        offending = [alias.name for alias in node.names if alias.name in rule.banned_names]
        if not offending:
            continue
        names = ", ".join(sorted(offending))
        preferred = " or ".join(rule.preferred_modules)
        diagnostics.append(
            Diagnostic(
                path=file_path.relative_to(_ROOT).as_posix(),
                line=node.lineno,
                severity="error",
                message=f"{rule.message} Offending import: {names}. Preferred: {preferred}.",
            )
        )
    return diagnostics


def check_file(file_path: Path) -> list[Diagnostic]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=file_path.as_posix())
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            diagnostics.extend(_check_import_from(node, file_path))
    return diagnostics


def check_paths(paths: Iterable[str]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for file_path in sorted(set(_iter_python_files(paths))):
        diagnostics.extend(check_file(file_path))
    return diagnostics


def emit_diagnostics(diagnostics: Iterable[Diagnostic]) -> int:
    error_count = 0
    for diag in diagnostics:
        if diag.severity == "error":
            error_count += 1
        print(f"{diag.path}:{diag.line}: {diag.severity}: {diag.message}")
    return error_count


def main() -> int:
    args = parse_args()
    paths = args.paths or list(_DEFAULT_PATHS)
    diagnostics = check_paths(paths)
    error_count = emit_diagnostics(diagnostics)
    if args.strict and error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())