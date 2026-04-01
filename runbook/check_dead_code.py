#!/usr/bin/env python
"""Run Vulture dead-code checks with VS Code-friendly diagnostics.

Emits diagnostics in the form:
  path:line: severity: message

Severity rules:
- error:   100% confidence (provably unreachable / unused)
- warning: <100% confidence (possibly unused)

Watch mode (--watch) loops indefinitely, printing begin/end markers so
VS Code's background-task problem matcher can refresh diagnostics on each
pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import subprocess
import sys
import time


_WATCH_INTERVAL_SECONDS = 300  # 5 minutes
_BEGIN_MARKER = "[vulture] Scanning..."
_END_MARKER = "[vulture] Done."


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    severity: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run dead-code checks via vulture")
    parser.add_argument("paths", nargs="*", default=["src"], help="Paths to scan")
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=80,
        help="Minimum confidence percentage to report (default: 80)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when errors are found",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously, emitting begin/end markers for VS Code",
    )
    return parser.parse_args()


def run_vulture(paths: list[str], min_confidence: int) -> str:
    cmd = [
        sys.executable,
        "-m",
        "vulture",
        *paths,
        "--min-confidence",
        str(min_confidence),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1):
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def _parse_confidence(tail: str) -> tuple[str, int]:
    """Extract (message, confidence) from 'some text (N% confidence)'."""
    if "(" in tail and tail.endswith("% confidence)"):
        msg_part, conf_part = tail.rsplit("(", 1)
        confidence = int(conf_part.split("%")[0])
        return msg_part.strip(), confidence
    return tail.strip(), 100


def _parse_diagnostic(raw: str) -> Diagnostic | None:
    """Parse one vulture output line; return None if unparseable."""
    try:
        location, tail = raw.split(": ", 1)
        path_str, line_str = location.rsplit(":", 1)
        line_no = int(line_str)
    except (ValueError, AttributeError):
        return None
    message, confidence = _parse_confidence(tail)
    severity = "error" if confidence == 100 else "warning"
    return Diagnostic(
        path=Path(path_str).as_posix(),
        line=line_no,
        severity=severity,
        message=f"{message} ({confidence}% confidence)",
    )


def parse_vulture_output(output: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for raw_line in output.splitlines():
        diag = _parse_diagnostic(raw_line.strip())
        if diag is not None:
            diagnostics.append(diag)
    return diagnostics


def emit_diagnostics(diagnostics: list[Diagnostic]) -> int:
    error_count = 0
    for diag in diagnostics:
        if diag.severity == "error":
            error_count += 1
        print(f"{diag.path}:{diag.line}: {diag.severity}: {diag.message}")
    return error_count


def run_check(paths: list[str], min_confidence: int) -> int:
    output = run_vulture(paths, min_confidence)
    diagnostics = parse_vulture_output(output)
    return emit_diagnostics(diagnostics)


def main() -> int:
    args = parse_args()
    if not args.watch:
        error_count = run_check(args.paths, args.min_confidence)
        return 1 if args.strict and error_count > 0 else 0

    # Watch mode: scan immediately, then repeat on a fixed interval.
    while True:
        print(_BEGIN_MARKER, flush=True)
        run_check(args.paths, args.min_confidence)
        print(_END_MARKER, flush=True)
        time.sleep(_WATCH_INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
