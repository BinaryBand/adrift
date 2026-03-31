#!/usr/bin/env python3
"""Validate TOML podcast config files using the project's Pydantic models.

Usage: runbook/validate_configs.py [files...]
If no files are provided, all `config/*.toml` files will be validated.

Exits with status 0 when all files validate, or 1 on validation errors.
"""

from __future__ import annotations

import sys
from pathlib import Path
import tomllib
import argparse

sys.path.insert(0, Path(__file__).parent.parent.as_posix())
from src.app_common import PodcastData  # type: ignore
from pydantic import ValidationError


def validate_file(path: Path, problems: bool = False) -> int:
    """Validate a single TOML file.

    When *problems* is True emit machine-parseable lines suitable for a
    VS Code problem matcher with the form:

        <path>:<entry_index>:<field>: <message>

    This intentionally omits line numbers (not available from the Pydantic
    model) but allows the Problems panel to show file-level diagnostics.
    """
    print(f"Validating {path}")
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except Exception as e:
        if problems:
            print(f"{path}:0:parse: {e}")
        else:
            print(f"  ERROR: failed to parse TOML: {e}")
        return 1

    podcasts = raw.get("podcasts")
    if podcasts is None:
        if problems:
            print(f"{path}:0:parse: no [podcasts] table found")
        else:
            print("  ERROR: no [podcasts] table found")
        return 1
    if not isinstance(podcasts, list):
        if problems:
            print(f"{path}:0:parse: [podcasts] must be an array of tables")
        else:
            print("  ERROR: [podcasts] must be an array of tables")
        return 1

    exit_code = 0
    for i, entry in enumerate(podcasts):
        try:
            PodcastData.model_validate(entry)
        except ValidationError as e:
            exit_code = 1
            if problems:
                for err in e.errors():
                    loc = ".".join(map(str, err.get("loc", []))) or "<root>"
                    msg = err.get("msg", "")
                    print(f"{path}:{i}:{loc}: {msg}")
            else:
                print(f"  ENTRY {i} invalid:")
                print(e)

    if exit_code == 0 and not problems:
        print(f"  OK: {len(podcasts)} entries validated")
    return exit_code


def main():
    parser = argparse.ArgumentParser(description="Validate TOML podcast configs")
    parser.add_argument("files", nargs="*", help="TOML config files to validate")
    parser.add_argument(
        "--problems", action="store_true", help="Emit problem-matcher-friendly output"
    )
    args = parser.parse_args()

    cfg_dir = Path(__file__).parent.parent / "config"
    files = (
        [Path(p) for p in args.files] if args.files else list(cfg_dir.glob("*.toml"))
    )

    overall = 0
    for p in files:
        if not p.exists():
            print(f"Skipping missing file: {p}")
            continue
        rc = validate_file(p, problems=args.problems)
        overall = overall or rc

    sys.exit(overall)


if __name__ == "__main__":
    main()
