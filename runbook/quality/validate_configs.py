#!/usr/bin/env python3
"""Validate TOML podcast config files using the project's Pydantic models.

Usage: runbook/quality/validate_configs.py [files...]
If no files are provided, all `config/*.toml` files will be validated.

Exits with status 0 when all files validate, or 1 on validation errors.
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import time
import tomllib
from typing import Any, cast

_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, _ROOT.as_posix())


_BEGIN_MARKER = "[toml-validator] Scanning..."
_END_MARKER = "[toml-validator] Done."


def _diag_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _podcast_entry_spans(lines: list[str]) -> list[tuple[int, int]]:
    starts = [i for i, line in enumerate(lines, start=1) if line.strip() == "[[podcasts]]"]
    if not starts:
        return []
    spans: list[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] - 1 if idx + 1 < len(starts) else len(lines)
        spans.append((start, end))
    return spans


def _find_key_line(lines: list[str], start: int, end: int, key: str, default_line: int) -> int:
    key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for line_no in range(start, end + 1):
        if key_pattern.search(lines[line_no - 1]):
            return line_no
    return default_line


def validate_file(path: Path, problems: bool = False) -> int:
    """Validate a single TOML file.

    When *problems* is True emit machine-parseable lines suitable for a
    VS Code problem matcher with the form:

        <path>:<line>:<field>: <message>

    Line numbers are inferred from the affected [[podcasts]] table when possible.
    """
    if not problems:
        print(f"Validating {path}")
    diag_path = _diag_path(path)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []

    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        if problems:
            line_no = int(getattr(e, "lineno", 1) or 1)
            print(f"{diag_path}:{line_no}:parse: {e}")
        else:
            print(f"  ERROR: failed to parse TOML: {e}")
        return 1

    podcasts = raw.get("podcasts")
    if podcasts is None:
        if problems:
            print(f"{diag_path}:1:parse: no [podcasts] table found")
        else:
            print("  ERROR: no [podcasts] table found")
        return 1
    if not isinstance(podcasts, list):
        if problems:
            print(f"{diag_path}:1:parse: [podcasts] must be an array of tables")
        else:
            print("  ERROR: [podcasts] must be an array of tables")
        return 1

    entry_spans = _podcast_entry_spans(lines)
    from pydantic import ValidationError

    from src.app_common import PodcastConfig  # type: ignore

    exit_code = 0
    podcast_entries = cast(list[object], podcasts)
    for i, entry in enumerate(podcast_entries):
        try:
            PodcastConfig.model_validate(entry)
        except ValidationError as e:
            exit_code = 1
            if problems:
                start_line, end_line = (
                    entry_spans[i] if i < len(entry_spans) else (1, max(len(lines), 1))
                )
                for err in cast(Any, e).errors():
                    loc = ".".join(map(str, err.get("loc", []))) or "<root>"
                    msg = err.get("msg", "")
                    key = str(err.get("loc", [""])[0]) if err.get("loc") else ""
                    line_no = (
                        _find_key_line(lines, start_line, end_line, key, start_line)
                        if lines and key
                        else start_line
                    )
                    print(f"{diag_path}:{line_no}:{loc}: {msg}")
            else:
                print(f"  ENTRY {i} invalid:")
                print(e)

    if exit_code == 0 and not problems:
        print(f"  OK: {len(podcast_entries)} entries validated")
    return exit_code


def _scan_files(files: list[Path], problems: bool) -> int:
    overall = 0
    for p in files:
        if not p.exists():
            if not problems:
                print(f"Skipping missing file: {p}")
            continue
        rc = validate_file(p, problems=problems)
        overall = overall or rc
    return overall


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TOML podcast configs")
    parser.add_argument("files", nargs="*", help="TOML config files to validate")
    parser.add_argument(
        "--problems", action="store_true", help="Emit problem-matcher-friendly output"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously and re-validate on a fixed interval",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Watch interval in seconds (default: 3)",
    )
    args = parser.parse_args()

    cfg_dir = _ROOT / "config"
    files = [Path(p) for p in args.files] if args.files else list(cfg_dir.glob("*.toml"))

    if not args.watch:
        sys.exit(_scan_files(files, problems=args.problems))

    while True:
        print(_BEGIN_MARKER, flush=True)
        _scan_files(files, problems=args.problems)
        print(_END_MARKER, flush=True)
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
