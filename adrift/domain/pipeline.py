"""Railway-oriented pipeline abstraction.

StageResult[T] carries both success and failure forward through a pipeline.
Errors accumulate; nothing is swallowed. The caller sees both the value
and all warnings/errors encountered along the way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from adrift.domain.errors import PipelineError

T = TypeVar("T")


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

    @property
    def ok(self) -> bool:
        """True if no fatal errors occurred (warnings are OK to continue)."""
        return not any(e.fatal for e in self.errors)


__all__ = [
    "StageResult",
]
