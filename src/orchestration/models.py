from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, cast

LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class DownloadRunRequest:
    include: list[str]
    skip_download: bool = False
    skip_update: bool = False
    max_downloads: int | None = None
    workdir: Path | None = None
    log_callback: LogCallback | None = None


@dataclass(frozen=True)
class FailedSeries:
    name: str
    phase: str
    error: str


@dataclass(frozen=True)
class DownloadRunResult:
    total_series: int
    total_episodes_downloaded: int
    failed_series: List[FailedSeries] = field(default_factory=lambda: cast(List[FailedSeries], []))
    bot_detected: bool = False
