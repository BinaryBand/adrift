#!/usr/bin/env python
"""Run Lizard complexity checks with VS Code-friendly diagnostics.

Emits diagnostics in the form:
  path:line: severity: message

Severity rules:
- error: metric exceeds ceiling
- warning: metric equals ceiling
"""

from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run complexity checks via lizard")
    parser.add_argument("path", nargs="?", default="src", help="Path to scan")
    parser.add_argument("--ccn", type=int, default=5, help="CCN ceiling")
    parser.add_argument(
        "--length", type=int, default=25, help="Function length ceiling"
    )
    parser.add_argument("--params", type=int, default=4, help="Parameter-count ceiling")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when ceiling errors are found",
    )
    return parser.parse_args()


def run_lizard(path: str, ccn: int, length: int, params: int) -> str:
    cmd = [
        sys.executable,
        "-m",
        "lizard",
        path,
        "-C",
        str(ccn),
        "-L",
        str(length),
        "-a",
        str(params),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1):
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def parse_metric_line(line: str) -> tuple[int, int, int, int, int, int, str] | None:
    stripped = line.strip()
    if not stripped or "@" not in stripped or not stripped[0].isdigit():
        return None

    parts = stripped.split()
    if len(parts) < 6:
        return None

    try:
        nloc = int(parts[0])
        ccn = int(parts[1])
        token = int(parts[2])
        param = int(parts[3])
        length = int(parts[4])
    except ValueError:
        return None

    location_blob = " ".join(parts[5:])
    try:
        _, span, file_path = location_blob.rsplit("@", 2)
        start_line = int(span.split("-", 1)[0])
    except Exception:
        return None

    return (nloc, ccn, token, param, length, start_line, file_path)


def check_metrics(output: str, ccn_max: int, len_max: int, param_max: int) -> int:
    error_count = 0

    for raw_line in output.splitlines():
        parsed = parse_metric_line(raw_line)
        if parsed is None:
            continue

        _, ccn, _, param, fn_length, start_line, file_path = parsed
        display_path = Path(file_path).as_posix()

        if ccn > ccn_max:
            error_count += 1
            print(
                f"{display_path}:{start_line}: error: CCN {ccn} exceeds ceiling {ccn_max}"
            )
        elif ccn == ccn_max:
            print(
                f"{display_path}:{start_line}: warning: CCN {ccn} at ceiling {ccn_max}"
            )

        if fn_length > len_max:
            error_count += 1
            print(
                f"{display_path}:{start_line}: error: function length {fn_length} exceeds ceiling {len_max}"
            )
        elif fn_length == len_max:
            print(
                f"{display_path}:{start_line}: warning: function length {fn_length} at ceiling {len_max}"
            )

        if param > param_max:
            error_count += 1
            print(
                f"{display_path}:{start_line}: error: parameter count {param} exceeds ceiling {param_max}"
            )
        elif param == param_max:
            print(
                f"{display_path}:{start_line}: warning: parameter count {param} at ceiling {param_max}"
            )

    return error_count


def main() -> int:
    args = parse_args()
    output = run_lizard(args.path, args.ccn, args.length, args.params)
    error_count = check_metrics(output, args.ccn, args.length, args.params)
    if args.strict and error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
