"""Railway-oriented pipeline abstraction.

StageResult[T] carries both success and failure forward through a pipeline.
Errors accumulate; nothing is swallowed. The caller sees both the value
and all warnings/errors encountered along the way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from src.domain.errors import PipelineError

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class StageResult(Generic[T]):
    """Represents the result of a pipeline stage.

    Combines:
    - value: The successful output (or a default if errors occurred)
    - warnings: Non-fatal issues encountered
    - errors: Fatal and non-fatal errors that occurred

    The `ok` property determines if the result is acceptable to proceed.
    """

    value: T
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[PipelineError, ...] = field(default_factory=tuple)

    def map(self, f: Callable[[T], U]) -> StageResult[U]:
        """Transform the value if present, preserving warnings/errors.

        Use this to apply pure transformations within a stage.
        """
        return StageResult(f(self.value), self.warnings, self.errors)

    def bind(self, f: Callable[[T], StageResult[U]]) -> StageResult[U]:
        """Chain to the next stage, accumulating errors.

        The next stage is always called with the current value.
        Errors (fatal or non-fatal) accumulate; the caller decides when to stop
        by checking the `ok` property.
        """
        next_stage = f(self.value)
        return StageResult(
            next_stage.value,
            self.warnings + next_stage.warnings,
            self.errors + next_stage.errors,
        )

    @property
    def ok(self) -> bool:
        """True if no fatal errors occurred (warnings are OK to continue)."""
        return not any(e.fatal for e in self.errors)

    @property
    def ok_to_proceed(self) -> bool:
        """Alias for ok. True if safe to proceed to next stage."""
        return self.ok

    def with_warning(self, message: str) -> StageResult[T]:
        """Add a warning without changing the value."""
        return StageResult(self.value, self.warnings + (message,), self.errors)

    def with_error(self, error: PipelineError) -> StageResult[T]:
        """Add an error without changing the value."""
        return StageResult(self.value, self.warnings, self.errors + (error,))

    def summary(self) -> str:
        """Human-readable summary of result status."""
        parts = []
        if self.errors:
            fatal_count = sum(1 for e in self.errors if e.fatal)
            if fatal_count > 0:
                parts.append(f"{fatal_count} fatal error(s)")
            non_fatal_count = len(self.errors) - fatal_count
            if non_fatal_count > 0:
                parts.append(f"{non_fatal_count} non-fatal error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        if not parts:
            return "OK"
        return ", ".join(parts)


__all__ = [
    "StageResult",
]
