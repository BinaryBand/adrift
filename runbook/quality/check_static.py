#!/usr/bin/env python3
"""Run Pyright (strict) and Ruff checks with VS Code-friendly diagnostics.

Emits diagnostics in the form:
  path:line: severity: message

Usage: runbook/quality/check_static.py [paths...]
If no paths are provided, the script checks: `src`, `runbook`, `tests`, `typings`.

Options:
  --pyright PATH   Path to a `pyright` executable (defaults to .venv or PATH)
  --ruff PATH      Path to a `ruff` executable (defaults to .venv or PATH)
  --problems       Emit problem-matcher-friendly output (same format as above)
  --strict         Exit non-zero when any issues are found
  --watch          Run continuously and re-check on an interval
  --interval N     Watch interval in seconds (default: 3)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple, cast

_ROOT = Path(__file__).parent.parent.parent.resolve()
_DEFAULT_PATHS = ["src", "runbook", "tests", "typings"]
_WATCH_INTERVAL_SECONDS = 3
_BEGIN_MARKER = "[static-check] Scanning..."
_END_MARKER = "[static-check] Done."


@dataclass(frozen=True)
class Diagnostic:
    path: str
    line: int
    severity: str
    message: str


def _json_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _json_list(value: Any) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def _json_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _json_int(value: Any, default: int = 1) -> int:
    return value if isinstance(value, int) else default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pyright (strict) and ruff checks")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Paths to check",
    )
    parser.add_argument("--pyright", help="Path to pyright executable")
    parser.add_argument("--ruff", help="Path to ruff executable")
    parser.add_argument(
        "--problems",
        action="store_true",
        help="Emit problem-matcher-friendly output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when issues are found",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Run continuously and re-check on an interval",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_WATCH_INTERVAL_SECONDS,
        help="Watch interval in seconds",
    )
    return parser.parse_args()


def _venv_executable(name: str) -> Optional[str]:
    """Look for an executable inside `.venv/` then fall back to PATH."""
    venv = _ROOT / ".venv"
    candidates: List[Path] = []
    if os.name == "nt":
        candidates.append(venv / "Scripts" / name)
        candidates.append(venv / "Scripts" / f"{name}.exe")
    else:
        candidates.append(venv / "bin" / name)
    for p in candidates:
        if p.exists():
            return p.as_posix()
    which = shutil.which(name)
    return which


def _emit(diagnostics: Iterable[Diagnostic]) -> int:
    error_count = 0
    for d in diagnostics:
        if d.severity == "error":
            error_count += 1
        print(f"{d.path}:{d.line}: {d.severity}: {d.message}")
    return error_count


def _excluded_pyright_path(path: Path) -> bool:
    excluded_prefixes = (
        Path("runbook") / "analysis",
        Path("tests"),
    )
    return any(path == prefix or prefix in path.parents for prefix in excluded_prefixes)


def _expand_pyright_paths(paths: Iterable[str]) -> List[str]:
    expanded: List[str] = []
    for raw in paths:
        candidate = (_ROOT / raw).resolve()
        if not candidate.exists():
            continue
        if candidate.is_file():
            rel = candidate.relative_to(_ROOT)
            if rel.suffix == ".py" and not _excluded_pyright_path(rel):
                expanded.append(rel.as_posix())
            continue
        for file_path in candidate.rglob("*.py"):
            rel = file_path.relative_to(_ROOT)
            if not _excluded_pyright_path(rel):
                expanded.append(rel.as_posix())
    return sorted(set(expanded))


def _run_pyright(paths: Iterable[str], exe: Optional[str]) -> Tuple[int, List[Diagnostic]]:
    if exe is None:
        exe = _venv_executable("pyright")
    if exe is None:
        print("pyright: not found; skipping pyright checks", file=sys.stderr)
        return 2, []

    pyright_paths = _expand_pyright_paths(paths)
    if not pyright_paths:
        return 0, []

    cmd = [exe, "--outputjson", *pyright_paths]
    proc = subprocess.run(cmd, cwd=_ROOT, capture_output=True, text=True, check=False)

    if not proc.stdout:
        # No structured output; surface whatever pyright printed.
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return proc.returncode, []

    try:
        payload = cast(dict[str, Any], json.loads(proc.stdout))
    except json.JSONDecodeError:
        print(proc.stdout)
        return proc.returncode, []

    diags: List[Diagnostic] = []

    # General / project-level diagnostics
    for item_value in _json_list(payload.get("generalDiagnostics")):
        item = _json_dict(item_value)
        file_path = _json_str(item.get("file"), "<project>")
        rng = _json_dict(item.get("range"))
        start = _json_dict(rng.get("start"))
        line = _json_int(start.get("line"), 0) + 1
        severity = _json_str(item.get("severity"), "error")
        message = _json_str(item.get("message"))
        diags.append(
            Diagnostic(
                path=Path(file_path).as_posix(),
                line=line,
                severity=severity,
                message=message,
            )
        )

    # Per-file diagnostics
    for file_value in _json_list(payload.get("files")):
        file_item = _json_dict(file_value)
        file_path = _json_str(file_item.get("file")) or _json_str(file_item.get("filePath"))
        messages = _json_list(file_item.get("messages")) or _json_list(file_item.get("diagnostics"))
        for message_value in messages:
            message_item = _json_dict(message_value)
            rng = _json_dict(message_item.get("range"))
            start = _json_dict(rng.get("start"))
            line = _json_int(start.get("line"), -1) + 1
            if line <= 0:
                line = _json_int(message_item.get("line"), 1)
            severity = _json_str(message_item.get("severity"), "error")
            message = _json_str(message_item.get("message"))
            diags.append(
                Diagnostic(
                    path=Path(file_path).as_posix(),
                    line=line,
                    severity=severity,
                    message=message,
                )
            )

    return proc.returncode, diags


def _run_ruff(paths: Iterable[str], exe: Optional[str]) -> Tuple[int, List[Diagnostic]]:
    if exe is None:
        exe = _venv_executable("ruff")
    if exe is None:
        print("ruff: not found; skipping ruff checks", file=sys.stderr)
        return 2, []

    # Prefer JSON format for reliable parsing; fall back to textual output.
    cmd_json = [exe, "check", "--format", "json", *paths]
    proc = subprocess.run(cmd_json, cwd=_ROOT, capture_output=True, text=True, check=False)
    diags: List[Diagnostic] = []
    if proc.stdout:
        try:
            payload = cast(dict[str, Any] | list[Any], json.loads(proc.stdout))
            # Ruff's JSON is a mapping from filename -> list of issues, or a list.
            if isinstance(payload, dict):
                items = _json_list(payload.get("files"))
            else:
                items = _json_list(payload)

            for item_value in items:
                item = _json_dict(item_value)
                # Each item may contain `filename` and `diagnostics` or be an issue directly.
                if "filename" in item and ("diagnostics" in item or "messages" in item):
                    filename = _json_str(item.get("filename"), "<unknown>")
                    issues = _json_list(item.get("diagnostics")) or _json_list(item.get("messages"))
                    for issue_value in issues:
                        issue = _json_dict(issue_value)
                        line = _json_int(issue.get("line"), 1)
                        code = _json_str(issue.get("code")) or _json_str(issue.get("rule"))
                        msg = _json_str(issue.get("message"))
                        severity = "error" if (code and code[:1] in ("E", "F")) else "warning"
                        diags.append(
                            Diagnostic(
                                path=Path(filename).as_posix(),
                                line=line,
                                severity=severity,
                                message=f"{code} {msg}".strip(),
                            )
                        )
                elif all(key in item for key in ("filename", "line", "code", "message")):
                    filename = _json_str(item.get("filename"), "<unknown>")
                    code = _json_str(item.get("code"))
                    severity = "error" if code[:1] in ("E", "F") else "warning"
                    diags.append(
                        Diagnostic(
                            path=Path(filename).as_posix(),
                            line=_json_int(item.get("line"), 1),
                            severity=severity,
                            message=f"{code} {_json_str(item.get('message'))}".strip(),
                        )
                    )
            return proc.returncode, diags
        except Exception:
            # fall through to textual parsing below
            pass

    # Fallback: run text mode and try to parse lines like "path:line:col: CODE message"
    cmd_text = [exe, "check", *paths]
    proc_text = subprocess.run(cmd_text, cwd=_ROOT, capture_output=True, text=True, check=False)
    text_out = proc_text.stdout or proc_text.stderr or ""
    ruff_line_re = re.compile(r"^(?P<path>.*?):(?P<line>\d+):\d+:\s*(?P<code>\w+)\s*(?P<msg>.*)$")
    for raw in text_out.splitlines():
        m = ruff_line_re.match(raw.strip())
        if m:
            code = m.group("code")
            severity = "error" if code and code[0] in ("E", "F") else "warning"
            diags.append(
                Diagnostic(
                    path=Path(m.group("path")).as_posix(),
                    line=int(m.group("line")),
                    severity=severity,
                    message=f"{code} {m.group('msg')}".strip(),
                )
            )
        else:
            # Print anything unparseable so users can see it
            if raw.strip():
                print(raw)

    return proc_text.returncode, diags


def run_checks(
    paths: Iterable[str],
    pyright_exe: Optional[str],
    ruff_exe: Optional[str],
) -> Tuple[int, List[Diagnostic]]:
    all_diags: List[Diagnostic] = []
    # Avoid running pyright over test files by default; tests often use
    # untyped mocks and private helpers which can generate many spurious
    # type-errors. Ruff should still lint tests.
    path_list = list(paths)
    pyright_paths = [p for p in path_list if p != "tests"]
    py_return, py_diags = _run_pyright(pyright_paths, pyright_exe)
    all_diags.extend(py_diags)

    ruff_return, ruff_diags = _run_ruff(path_list, ruff_exe)
    all_diags.extend(ruff_diags)

    # Choose an overall return code: prefer non-tool-found (2) over tool-reported findings (1)
    if py_return == 2 or ruff_return == 2:
        overall = 2
    elif py_return != 0 or ruff_return != 0:
        overall = 1
    else:
        overall = 0
    return overall, all_diags


def main() -> int:
    args = parse_args()
    paths = args.paths or _DEFAULT_PATHS

    if not args.watch:
        overall_rc, diags = run_checks(paths, args.pyright, args.ruff)
        error_count = _emit(diags)
        if args.strict and error_count > 0:
            return 1
        return overall_rc if overall_rc != 2 else 1

    # watch mode
    while True:
        print(_BEGIN_MARKER, flush=True)
        overall_rc, diags = run_checks(paths, args.pyright, args.ruff)
        _emit(diags)
        print(_END_MARKER, flush=True)
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
