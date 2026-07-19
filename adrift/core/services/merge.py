"""Merge use-case for orchestrating config merges with typed results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from adrift.core.models.errors import PipelineError
from adrift.core.models.stage_result import StageResult
from adrift.core.services import catalog
from adrift.core.services.merge_service import (
    MergeRunOptions,
    MergeWriters,
    emit_timings,
    model_payloads,
)
from adrift.core.util.profiler import profile
from adrift.core.util.run_ui import build_merge_callbacks

from collections.abc import Callable

from adrift.core.models import MergeResult, PodcastConfig
from adrift.core.util.run_ui import BaseRunUI


_MERGE_OPERATION_ERRORS = (OSError, RuntimeError, ValueError)
