#!/usr/bin/env python
"""Run Lizard complexity checks with VS Code-friendly diagnostics.

Emits diagnostics in the form:
  path:line: severity: message

Severity rules:
- error: metric exceeds ceiling
- warning: metric equals ceiling
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ceiling:
    ccn: int
    length: int
    params: int


@dataclass(frozen=True)
class FunctionMetrics:
    ccn: int
    params: int
    length: int
    start_line: int
    file_path: str


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    severity: str
    message: str


@dataclass(frozen=True)
class MetricCheck:
    label: str
    value: int
    ceiling: int


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


def _is_metric_candidate(line: str) -> bool:
    return bool(line and "@" in line and line[0].isdigit())


def _parse_metric_values(parts: list[str]) -> tuple[int, int, int, int, int] | None:
    if len(parts) < 6:
        return None
    try:
        return (
            int(parts[0]),
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
            int(parts[4]),
        )
    except ValueError:
        return None


def _parse_location(parts: list[str]) -> tuple[int, str] | None:
    location_blob = " ".join(parts[5:])
    try:
        _, span, file_path = location_blob.rsplit("@", 2)
        start_line = int(span.split("-", 1)[0])
    except Exception:
        return None
    return (start_line, file_path)


def parse_metric_line(line: str) -> tuple[int, int, int, int, int, int, str] | None:
    stripped = line.strip()
    if not _is_metric_candidate(stripped):
        return None

    parts = stripped.split()
    metrics = _parse_metric_values(parts)
    if metrics is None:
        return None
    nloc, ccn, token, param, length = metrics

    location = _parse_location(parts)
    if location is None:
        return None
    start_line, file_path = location

    return (nloc, ccn, token, param, length, start_line, file_path)


def to_function_metrics(
    parsed: tuple[int, int, int, int, int, int, str],
) -> FunctionMetrics:
    _, ccn, _, params, length, start_line, file_path = parsed
    return FunctionMetrics(
        ccn=ccn,
        params=params,
        length=length,
        start_line=start_line,
        file_path=Path(file_path).as_posix(),
    )


def parse_lizard_output(output: str) -> list[FunctionMetrics]:
    metrics: list[FunctionMetrics] = []
    for raw_line in output.splitlines():
        parsed = parse_metric_line(raw_line)
        if parsed is None:
            continue
        metrics.append(to_function_metrics(parsed))
    return metrics


def _severity_for(value: int, ceiling: int) -> str | None:
    if value > ceiling:
        return "error"
    if value == ceiling:
        return "warning"
    return None


def _metric_diagnostic(
    metrics: FunctionMetrics, check: MetricCheck
) -> Diagnostic | None:
    severity = _severity_for(check.value, check.ceiling)
    if severity is None:
        return None
    relation = "exceeds" if severity == "error" else "at"
    return Diagnostic(
        path=metrics.file_path,
        line=metrics.start_line,
        severity=severity,
        message=f"{check.label} {check.value} {relation} ceiling {check.ceiling}",
    )


def evaluate_function(metrics: FunctionMetrics, ceiling: Ceiling) -> list[Diagnostic]:
    checks = [
        MetricCheck("CCN", metrics.ccn, ceiling.ccn),
        MetricCheck("function length", metrics.length, ceiling.length),
        MetricCheck("parameter count", metrics.params, ceiling.params),
    ]
    diagnostics: list[Diagnostic] = []
    for check in checks:
        diag = _metric_diagnostic(metrics, check)
        if diag is not None:
            diagnostics.append(diag)
    return diagnostics


def evaluate_metrics(
    metrics_list: list[FunctionMetrics], ceiling: Ceiling
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for metrics in metrics_list:
        diagnostics.extend(evaluate_function(metrics, ceiling))
    return diagnostics


def emit_diagnostics(diagnostics: list[Diagnostic]) -> int:
    error_count = 0
    for diag in diagnostics:
        if diag.severity == "error":
            error_count += 1
        print(f"{diag.path}:{diag.line}: {diag.severity}: {diag.message}")
    return error_count


def check_metrics(output: str, ceiling: Ceiling) -> int:
    metrics_list = parse_lizard_output(output)
    diagnostics = evaluate_metrics(metrics_list, ceiling)
    return emit_diagnostics(diagnostics)


def main() -> int:
    args = parse_args()
    ceiling = Ceiling(ccn=args.ccn, length=args.length, params=args.params)
    output = run_lizard(args.path, args.ccn, args.length, args.params)
    error_count = check_metrics(output, ceiling)
    if args.strict and error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
