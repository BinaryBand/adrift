"""Typed events emitted by application pipelines."""

from __future__ import annotations

from dataclasses import dataclass

from src.models import RssEpisode


@dataclass(frozen=True)
class OperationStarted:
    """Signals that a new named operation has started."""

    label: str


@dataclass(frozen=True)
class ProgressUpdated:
    """Signals incremental progress for the current operation."""

    current: int
    total: int | None


@dataclass(frozen=True)
class DownloadCompleted:
    """Signals that an episode finished download/upload processing."""

    episode: RssEpisode
    s3_key: str
    sponsors_removed: bool


@dataclass(frozen=True)
class DownloadFailed:
    """Signals that an episode failed before upload completion."""

    episode: RssEpisode
    error: str
    recoverable: bool = True


__all__ = [
    "OperationStarted",
    "ProgressUpdated",
    "DownloadCompleted",
    "DownloadFailed",
]
