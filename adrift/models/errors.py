"""Typed error hierarchy for Adrift domain operations.

All domain operations that can fail return explicit error types
via StageResult. This replaces bare Exception catching with intent-specific types.
"""

from __future__ import annotations

from dataclasses import dataclass


class AdriftError(Exception):
    """Base error for all Adrift domain operations.

    All domain errors should inherit from this, making error catching granular
    and explicit rather than catching bare Exception.
    """

    message: str

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class PipelineError(AdriftError):
    """An error that occurs during a pipeline stage.

    Carries context about what operation failed and whether it's fatal.
    Non-fatal errors accumulate in StageResult; fatal errors short-circuit.
    """

    label: str  # e.g., "merge", "download", "align"
    message: str
    fatal: bool = True
    cause: Exception | None = None

    def __str__(self) -> str:
        s = f"{self.label}: {self.message}"
        if self.cause:
            s += f" (caused by: {type(self.cause).__name__})"
        return s


@dataclass(frozen=True)
class FetchError(AdriftError):
    """Failed to fetch content from an external source (RSS feed, YouTube, etc)."""

    source: str  # e.g., "https://example.com/feed.xml"
