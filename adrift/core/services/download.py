"""Download pipeline use-case with explicit context and typed results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from adrift.core.models import DownloadEpisode, PodcastConfig
from adrift.core.models.errors import PipelineError
from adrift.core.models.stage_result import StageResult
from adrift.core.services.catalog.merge import MergeConfigOptions
from adrift.core.services.context import AppContext
from adrift.core.services.download_process import DownloadQueueItem
from adrift.core.services.events import (
    DownloadCompleted,
    DownloadFailed,
    OperationStarted,
    ProgressUpdated,
)
from adrift.core.util.progress import Callback
from adrift.core.util.run_ui import BaseRunUI
from adrift.core.util.title_normalization import normalize_title

BuildQueueFn = Callable[
    [list[DownloadEpisode], PodcastConfig, "AppContext"],
    list["DownloadQueueItem"],
]

_DOWNLOAD_OPERATION_ERRORS = (OSError, RuntimeError, ValueError)
