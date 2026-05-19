"""Development profiling utilities for tracking function execution time."""

from __future__ import annotations

import functools
import sys
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Callable, Generator, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Global registry for collecting profiling data (dev-only)
_profiler_registry: dict[str, list[float]] = {}
_profiler_enabled: bool = False


def enable_profiling() -> None:
    """Enable profiling across all @profile decorated functions and context managers."""
    global _profiler_enabled
    _profiler_enabled = True


def disable_profiling() -> None:
    """Disable profiling."""
    global _profiler_enabled
    _profiler_enabled = False


def get_profile_report() -> dict[str, dict[str, float]]:
    """
    Get a summary report of all profiled functions/blocks.

    Returns dict mapping names to {"total_ms", "count", "avg_ms", "min_ms", "max_ms"}
    """
    if not _profiler_registry:
        return {}

    report = {}
    for name, durations in _profiler_registry.items():
        total_ms = sum(durations) * 1000
        count = len(durations)
        avg_ms = total_ms / count if count else 0
        min_ms = min(durations) * 1000 if durations else 0
        max_ms = max(durations) * 1000 if durations else 0

        report[name] = {
            "total_ms": round(total_ms, 1),
            "count": count,
            "avg_ms": round(avg_ms, 1),
            "min_ms": round(min_ms, 1),
            "max_ms": round(max_ms, 1),
        }

    # Sort by total_ms descending
    return dict(sorted(report.items(), key=lambda x: x[1]["total_ms"], reverse=True))


def print_profile_report(file=sys.stderr) -> None:
    """Print a formatted profiling report to stderr (or specified file)."""
    report = get_profile_report()
    if not report:
        return

    file.write("\n=== Profiling Report ===\n")
    file.write(
        f"{'Name':<40} {'Total (ms)':<12} {'Calls':<8} {'Avg (ms)':<10} {'Min/Max (ms)':<16}\n"
    )
    file.write("-" * 90 + "\n")

    for name, stats in report.items():
        file.write(
            f"{name:<40} {stats['total_ms']:<12.1f} {stats['count']:<8} "
            f"{stats['avg_ms']:<10.1f} {stats['min_ms']:.1f}/{stats['max_ms']:.1f}\n"
        )


def profile(func: F) -> F:
    """
    Decorator to profile a function's execution time (dev-only).

    Usage:
        @profile
        def my_slow_function():
            pass

    Enable with: profiler.enable_profiling()
    Get results: profiler.print_profile_report()
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not _profiler_enabled:
            return func(*args, **kwargs)

        start = perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration = perf_counter() - start
            name = f"{func.__module__}.{func.__qualname__}"
            if name not in _profiler_registry:
                _profiler_registry[name] = []
            _profiler_registry[name].append(duration)

    return wrapper  # type: ignore


@contextmanager
def profile_block(name: str) -> Generator[None, None, None]:
    """
    Context manager to profile a code block (dev-only).

    Usage:
        with profile_block("my_operation"):
            # code here gets timed

    Enable with: profiler.enable_profiling()
    Get results: profiler.print_profile_report()
    """
    if not _profiler_enabled:
        yield
        return

    start = perf_counter()
    try:
        yield
    finally:
        duration = perf_counter() - start
        if name not in _profiler_registry:
            _profiler_registry[name] = []
        _profiler_registry[name].append(duration)


def reset() -> None:
    """Clear all profiling data."""
    global _profiler_registry
    _profiler_registry.clear()
